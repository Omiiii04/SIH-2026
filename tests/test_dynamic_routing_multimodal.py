"""
tests/test_dynamic_routing_multimodal.py
────────────────────────────────────────
Regression tests covering:
1. Model capability discovery via LM Studio native /api/v1/models (authoritative metadata).
2. Gemma vision detection without model-name keyword heuristics.
3. Capability filtering happening BEFORE latency/performance scoring.
4. Multimodal transport (attachments, multipart form data, automatic modality detection).
5. Dynamic multi-node competition and offline fallback without static node assumptions.
6. Empty response validation preventing blank assistant message persistence.
"""

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app
from orchestrator.schemas import (
    ClassificationResult,
    InputType,
    NodeRegistryEntry,
    NodeType,
    TaskType,
    Difficulty,
    ClassifierMethod,
    Attachment,
)
from orchestrator.monitor import NodeState
from orchestrator.scheduler import discover_capabilities, select_best_candidates
from orchestrator.lm_client import LMResponse, LMClientError, _build_payload, _build_messages
from orchestrator.node_manager import discover_models


def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Authoritative Capability Discovery (Native LM Studio Metadata)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_native_lmstudio_metadata_gemma_vision():
    """
    Verify that Gemma is recognized as vision-capable based on LM Studio native
    metadata 'capabilities.vision == true', without relying on model-name substring heuristics.
    """
    mock_native_response = {
        "models": [
            {
                "type": "llm",
                "publisher": "google",
                "key": "google/gemma-4-4b",
                "display_name": "Google Gemma 4 4B",
                "architecture": "gemma4",
                "quantization": {"name": "Q4_K_M"},
                "loaded_instances": [{"id": "google/gemma-4-4b"}],
                "max_context_length": 8192,
                "capabilities": {
                    "vision": True,
                    "trained_for_tool_use": True,
                    "reasoning": {"allowed_options": ["off", "on"], "default": "on"},
                },
            }
        ]
    }

    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_native_response
    mock_client.get.return_value = mock_resp

    models = await discover_models("http://192.168.1.50:1234", client=mock_client)

    assert len(models) == 1
    m = models[0]
    assert m["id"] == "google/gemma-4-4b"
    assert m["capability_source"] == "lmstudio_metadata"
    assert m["capabilities"].get("vision") is True

    # Test discover_capabilities uses this metadata
    entry = NodeRegistryEntry(
        node_id="NODE-1",
        node_name="Node 1",
        capability="text",
        node_type=NodeType.TEXT,
        model="google/gemma-4-4b",
        endpoint="http://192.168.1.50:1234",
        status="online",
        supported_input_types=["text"],
        priority=1,
    )
    caps = discover_capabilities(entry, "google/gemma-4-4b", model_meta=m)
    assert "vision" in caps
    assert "image_reasoning" in caps
    assert "text" in caps


def test_discover_capabilities_precedence_no_keyword_override():
    """
    Test that explicit metadata takes precedence and does NOT infer vision for a
    model with 'vision' in its name if explicit metadata says vision=False.
    """
    entry = NodeRegistryEntry(
        node_id="NODE-1",
        node_name="Node 1",
        capability="text",
        node_type=NodeType.TEXT,
        model="misleading-vision-name",
        endpoint="http://node",
        status="online",
        supported_input_types=["text"],
        priority=1,
    )
    meta_explicit_false = {
        "id": "misleading-vision-name",
        "capabilities": {"vision": False},
        "capability_source": "lmstudio_metadata",
    }
    caps = discover_capabilities(entry, "misleading-vision-name", model_meta=meta_explicit_false)
    assert "vision" not in caps


# ─────────────────────────────────────────────────────────────────────────────
# 2. Critical Regression Test: Capability Filtering BEFORE Latency Scoring
# ─────────────────────────────────────────────────────────────────────────────

def test_capability_filtering_before_latency_scoring():
    """
    Requirement 5:
    Node A: Gemma vision, latency = 100 ms
    Node B: text-only model, latency = 20 ms
    Request: Image request ("What is in this image?")

    Expected:
    Node B MUST be rejected before latency scoring.
    Node A must win even though it is slower.
    """
    registry = {
        "NODE-A": NodeRegistryEntry(
            node_id="NODE-A",
            node_name="Gemma Vision Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="google/gemma-4-4b",
            endpoint="http://node-a:1234",
            status="online",
            supported_input_types=["text"],
            priority=1,
        ),
        "NODE-B": NodeRegistryEntry(
            node_id="NODE-B",
            node_name="Fast Text Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="fast-text-model",
            endpoint="http://node-b:1234",
            status="online",
            supported_input_types=["text"],
            priority=1,
        ),
    }

    states = {
        "NODE-A": NodeState(
            node_id="NODE-A",
            status="online",
            latency_ms=100.0,
            models_loaded=["google/gemma-4-4b"],
            models_metadata={
                "google/gemma-4-4b": {
                    "id": "google/gemma-4-4b",
                    "capabilities": {"vision": True},
                    "capability_source": "lmstudio_metadata",
                }
            },
        ),
        "NODE-B": NodeState(
            node_id="NODE-B",
            status="online",
            latency_ms=20.0,  # 5x faster than Node A!
            models_loaded=["fast-text-model"],
            models_metadata={
                "fast-text-model": {
                    "id": "fast-text-model",
                    "capabilities": {"vision": False},
                    "capability_source": "lmstudio_metadata",
                }
            },
        ),
    }

    cls = ClassificationResult(
        input_type=InputType.IMAGE,
        node_type=NodeType.VISION,
        task_type=TaskType.VISUAL_QA,
        difficulty=Difficulty.MEDIUM,
        required_capability="vision",
        confidence=1.0,
        classifier_method=ClassifierMethod.RULE_EXPLICIT,
        input_modalities=["image", "text"],
        required_capabilities=["vision"],
    )

    with patch("orchestrator.scheduler.get_registry", return_value=registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=states):

        candidates = select_best_candidates(cls)

        # Node B must be completely excluded
        assert len(candidates) == 1
        best_node, best_model, score, reason = candidates[0]
        assert best_node.node_id == "NODE-A"
        assert best_model == "google/gemma-4-4b"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Multi-Node Dynamic Routing & Offline Fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_node_vision_offline_fallback():
    """
    Requirement 6:
    When Node 1 (vision) goes offline, if no other vision node exists,
    Node 2 (text-only) must NOT be selected for an image request.
    Instead, candidates must be empty.
    """
    registry = {
        "NODE-1": NodeRegistryEntry(
            node_id="NODE-1",
            node_name="Vision Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="google/gemma-4-4b",
            endpoint="http://node-1",
            status="offline",  # Offline!
            supported_input_types=["text"],
            priority=1,
        ),
        "NODE-2": NodeRegistryEntry(
            node_id="NODE-2",
            node_name="Text Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="llama-3-8b",
            endpoint="http://node-2",
            status="online",
            supported_input_types=["text"],
            priority=1,
        ),
    }

    states = {
        "NODE-1": NodeState(
            node_id="NODE-1",
            status="offline",
            latency_ms=50.0,
            models_loaded=["google/gemma-4-4b"],
            models_metadata={"google/gemma-4-4b": {"capabilities": {"vision": True}, "capability_source": "lmstudio_metadata"}},
        ),
        "NODE-2": NodeState(
            node_id="NODE-2",
            status="online",
            latency_ms=10.0,
            models_loaded=["llama-3-8b"],
            models_metadata={"llama-3-8b": {"capabilities": {"vision": False}, "capability_source": "lmstudio_metadata"}},
        ),
    }

    cls = ClassificationResult(
        input_type=InputType.IMAGE,
        node_type=NodeType.VISION,
        task_type=TaskType.VISUAL_QA,
        difficulty=Difficulty.MEDIUM,
        required_capability="vision",
        confidence=1.0,
        classifier_method=ClassifierMethod.RULE_EXPLICIT,
        input_modalities=["image", "text"],
        required_capabilities=["vision"],
    )

    with patch("orchestrator.scheduler.get_registry", return_value=registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=states):

        candidates = select_best_candidates(cls)
        # Node-2 must NOT win because it lacks vision!
        assert len(candidates) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Multimodal Transport & Payload Construction
# ─────────────────────────────────────────────────────────────────────────────

def test_lm_client_multimodal_payload_construction():
    """
    Test that an image attachment constructs an OpenAI-compatible multimodal content array
    with data URL base64 format.
    """
    dummy_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    attachment = Attachment(
        filename="red.png",
        content_type="image/png",
        data_base64=dummy_png_b64,
        size_bytes=68,
    )

    payload = _build_payload(
        model="google/gemma-4-4b",
        query="What color is this image?",
        attachments=[attachment],
    )

    assert payload["model"] == "google/gemma-4-4b"
    assert payload["max_tokens"] >= 2048
    messages = payload["messages"]
    assert len(messages) == 1
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert len(user_msg["content"]) == 2
    assert user_msg["content"][0] == {"type": "text", "text": "What color is this image?"}
    assert user_msg["content"][1] == {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{dummy_png_b64}"},
    }


@pytest.mark.asyncio
async def test_api_query_multipart_file_upload():
    """
    Test that POST /api/v1/query accepts multipart/form-data with actual file bytes,
    automatically detects the image modality, and routes to the vision model.
    """
    dummy_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"

    entry = NodeRegistryEntry(
        node_id="NODE-VISION-1",
        node_name="Vision Node",
        capability="text",
        node_type=NodeType.TEXT,
        model="google/gemma-4-4b",
        endpoint="http://node:1234",
        status="online",
        supported_input_types=["text"],
        priority=1,
    )

    candidates = [(entry, "google/gemma-4-4b", 10.0, "Gemma vision selected")]

    with patch("orchestrator.scheduler.select_best_candidates", return_value=candidates), \
         patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call, \
         patch("orchestrator.persistence.persist_success", new_callable=AsyncMock), \
         patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):

        mock_call.return_value = LMResponse(
            content="This image is a red pixel.",
            model="google/gemma-4-4b",
            latency_ms=250.0,
            tokens_prompt=50,
            tokens_completion=10,
            tokens_total=60,
        )

        async with _make_client() as client:
            files = {
                "attachments": ("test.png", dummy_png_bytes, "image/png"),
            }
            data = {
                "user_id": "test-user",
                "query": "What is in this picture?",
            }
            resp = await client.post("/api/v1/query", data=data, files=files)

        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["response"] == "This image is a red pixel."
        assert res_data["selected_node"] == "NODE-VISION-1"
        assert res_data["selected_model"] == "google/gemma-4-4b"

        # Verify call_node received attachments
        call_kwargs = mock_call.call_args.kwargs
        assert len(call_kwargs["attachments"]) == 1
        att = call_kwargs["attachments"][0]
        assert att.filename == "test.png"
        assert att.content_type == "image/png"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Empty Response Validation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_response_validation():
    """
    Requirement 14: If LM Studio returns HTTP 200 but content is empty
    (e.g. tokens exhausted during reasoning trace), it must raise an
    LMClientError(empty_response) and NOT be treated as a successful completion.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "cmpl-123",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",  # Empty!
                    "reasoning_content": "Thinking about the query...",
                },
                "finish_reason": "length",
            }
        ],
        "usage": {"total_tokens": 512},
    }

    with patch("httpx.AsyncClient") as MockClient:
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)

        from orchestrator.lm_client import call_node
        with pytest.raises(LMClientError) as exc_info:
            await call_node(
                endpoint="http://localhost:1234",
                model="google/gemma-4-4b",
                query="Explain something",
            )

        assert exc_info.value.error_type == "empty_response"
        assert "empty content" in exc_info.value.detail
