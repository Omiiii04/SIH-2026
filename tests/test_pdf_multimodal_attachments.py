"""
tests/test_pdf_multimodal_attachments.py
────────────────────────────────────────
Comprehensive test suite for PDF & Multimodal Attachment Pipeline.

Covers all 12 required test cases:
1. PNG → image modality
2. JPEG → image modality
3. PDF with text → document modality
4. Scanned/image PDF → document + image modality
5. Unsupported file → clean error (HTTP 400 with helpful message)
6. Image query selects vision model
7. Scanned PDF selects vision-capable model
8. Faster text-only model is rejected for scanned PDF
9. Actual file data reaches LM client (rendered page images, OpenAI multimodal payload)
10. Multiple attachments (mixed image + PDF or multiple documents)
11. Response is persisted without binary data in PostgreSQL / ChromaDB
12. Response is visible in session history
"""

import base64
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient
import pymupdf

from orchestrator.main import app
from orchestrator.schemas import (
    Attachment,
    AttachmentKind,
    ClassificationResult,
    InputType,
    NodeRegistryEntry,
    NodeType,
    TaskType,
    Difficulty,
    ClassifierMethod,
    QueryRequest,
    QueryResponse,
    RoutingDecision,
)
from orchestrator.attachments import (
    categorize_attachment,
    process_attachment_bytes,
    normalize_attachment,
    normalize_request,
    MAX_ATTACHMENT_SIZE_BYTES,
)
from orchestrator.classifier import classify
from orchestrator.scheduler import select_best_candidates
from orchestrator.lm_client import _build_messages, _build_payload, LMResponse
from orchestrator.persistence import persist_success

FIXTURE_FLYER_PDF = os.path.join(os.path.dirname(__file__), "fixtures", "winter_internship_2026_2027_flyer.pdf")
FIXTURE_FLYER_PNG = os.path.join(os.path.dirname(__file__), "fixtures", "winter_internship_2026_2027_flyer.png")
FIXTURE_FLYER_JPG = os.path.join(os.path.dirname(__file__), "fixtures", "winter_internship_2026_2027_flyer.jpg")


def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ── 1. PNG → image modality ───────────────────────────────────────────────────

def test_png_attachment_image_modality():
    """Requirement 1: PNG file is classified as image kind with image modality and vision capability."""
    with open(FIXTURE_FLYER_PNG, "rb") as f:
        png_bytes = f.read()

    att = process_attachment_bytes("test_image.png", "image/png", png_bytes)

    assert att.kind == AttachmentKind.IMAGE
    assert att.has_visual_content is True
    assert att.content_type == "image/png"
    assert len(att.data_base64) > 0

    modalities, required_caps = normalize_request("Describe this image", [att])
    assert "text" in modalities
    assert "image" in modalities
    assert "vision" in required_caps


# ── 2. JPEG → image modality ──────────────────────────────────────────────────

def test_jpeg_attachment_image_modality():
    """Requirement 2: JPEG file is classified as image kind with image modality and vision capability."""
    with open(FIXTURE_FLYER_JPG, "rb") as f:
        jpg_bytes = f.read()

    att = process_attachment_bytes("sample.jpeg", "image/jpeg", jpg_bytes)

    assert att.kind == AttachmentKind.IMAGE
    assert att.has_visual_content is True
    assert att.content_type == "image/jpeg"

    modalities, required_caps = normalize_request("What is in this picture?", [att])
    assert "text" in modalities
    assert "image" in modalities
    assert "vision" in required_caps


# ── 3. PDF with text → document modality ──────────────────────────────────────

def test_pdf_with_text_document_modality():
    """Requirement 3: PDF with selectable text extracts document text and requires NO vision capability."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        "Quarterly Financial Report 2026.\nRevenue grew by 24% year-over-year.\nOperating margins improved significantly."
    )
    pdf_bytes = doc.tobytes()

    att = process_attachment_bytes("report.pdf", "application/pdf", pdf_bytes)

    assert att.kind == AttachmentKind.PDF
    assert att.has_visual_content is False
    assert len(att.rendered_pages) == 0
    assert att.extracted_text is not None
    assert "Quarterly Financial Report" in att.extracted_text

    modalities, required_caps = normalize_request("Summarize this document", [att])
    assert modalities == ["text", "document"]
    assert "image" not in modalities
    assert "vision" not in required_caps


# ── 4. Scanned/image PDF → document + image modality ──────────────────────────

def test_scanned_image_pdf_document_and_image_modality():
    """Requirement 4: Scanned/image PDF renders page(s) to image and activates document + image modalities."""
    with open(FIXTURE_FLYER_PDF, "rb") as f:
        flyer_bytes = f.read()

    att = process_attachment_bytes("winter_internship_2026_2027_flyer.pdf", "application/pdf", flyer_bytes)

    assert att.kind == AttachmentKind.PDF
    assert att.has_visual_content is True
    assert len(att.rendered_pages) >= 1
    assert att.page_count == 1

    modalities, required_caps = normalize_request("Tell me what is this?", [att])
    assert "text" in modalities
    assert "document" in modalities
    assert "image" in modalities
    assert "vision" in required_caps


# ── 5. Unsupported file → clean error ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsupported_file_clean_error():
    """Requirement 5: Unsupported file types cleanly rejected with HTTP 400 and helpful message."""
    with pytest.raises(ValueError) as exc_info:
        process_attachment_bytes("executable.exe", "application/x-msdownload", b"MZDummyBinary")
    assert "Unsupported file format" in str(exc_info.value)
    assert "Supported formats" in str(exc_info.value)

    # Test via API multipart endpoint
    async with _make_client() as client:
        resp = await client.post(
            "/api/v1/query",
            data={"query": "Run this file", "user_id": "test-user"},
            files={"attachments": ("bad.exe", b"binarycontent", "application/x-msdownload")},
        )
        assert resp.status_code == 400
        assert "Unsupported file format" in resp.json()["detail"]


# ── 6. Image query selects vision model ───────────────────────────────────────

@pytest.mark.asyncio
async def test_image_query_selects_vision_model():
    """Requirement 6: Image attachment classifies into vision requirement and selects vision model."""
    with open(FIXTURE_FLYER_PNG, "rb") as f:
        png_bytes = f.read()

    att = process_attachment_bytes("flyer.png", "image/png", png_bytes)
    cls = await classify(query="What is this?", input_type=InputType.TEXT, attachments=[att])

    assert cls.required_capability == "vision"
    assert "image" in cls.input_modalities
    assert "vision" in cls.required_capabilities

    mock_registry = {
        "NODE-TEXT": NodeRegistryEntry(
            node_id="NODE-TEXT",
            node_name="Text Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="text-model-4b",
            endpoint="http://node-text:1234",
            status="online",
            supported_input_types=["text"],
            priority=1,
        ),
        "NODE-VISION": NodeRegistryEntry(
            node_id="NODE-VISION",
            node_name="Vision Node",
            capability="vision",
            node_type=NodeType.VISION,
            model="google/gemma-4-4b",
            endpoint="http://node-vision:1234",
            status="online",
            supported_input_types=["image", "text"],
            priority=1,
        ),
    }

    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value={}):
        candidates = select_best_candidates(cls)
        assert len(candidates) == 1
        node, model, score, reason = candidates[0]
        assert node.node_id == "NODE-VISION"


# ── 7. Scanned PDF selects vision-capable model ────────────────────────────────

@pytest.mark.asyncio
async def test_scanned_pdf_selects_vision_capable_model():
    """Requirement 7: Scanned PDF dynamically selects a model with vision capability."""
    with open(FIXTURE_FLYER_PDF, "rb") as f:
        flyer_bytes = f.read()

    att = process_attachment_bytes("winter_internship_2026_2027_flyer.pdf", "application/pdf", flyer_bytes)
    cls = await classify(query="Tell me what is this?", input_type=InputType.TEXT, attachments=[att])

    assert "image" in cls.input_modalities
    assert "vision" in cls.required_capabilities

    mock_registry = {
        "NODE-TEXT": NodeRegistryEntry(
            node_id="NODE-TEXT",
            node_name="Text Only",
            capability="text",
            node_type=NodeType.TEXT,
            model="qwen3-4b-instruct",
            endpoint="http://node-text:1234",
            status="online",
            supported_input_types=["text"],
            priority=1,
        ),
        "NODE-GEMMA": NodeRegistryEntry(
            node_id="NODE-GEMMA",
            node_name="Gemma Vision",
            capability="vision",
            node_type=NodeType.VISION,
            model="google/gemma-4-e4b",
            endpoint="http://localhost:1234",
            status="online",
            supported_input_types=["image", "text"],
            priority=1,
        ),
    }

    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value={}):
        candidates = select_best_candidates(cls)
        assert len(candidates) == 1
        node, model, _, _ = candidates[0]
        assert node.node_id == "NODE-GEMMA"
        assert model == "google/gemma-4-e4b"


# ── 8. Faster text-only model is rejected for scanned PDF ──────────────────────

def test_faster_text_only_model_is_rejected_for_scanned_pdf():
    """
    Requirement 8:
    Node A: Text-only model, ultra-low latency = 15 ms, vision = False
    Node B: Vision model, higher latency = 250 ms, vision = True
    Request: Scanned PDF (requires vision)

    Expected:
    Node A must be rejected in Step 1 before performance scoring.
    Node B must be selected even though it is slower.
    """
    cls = ClassificationResult(
        input_type=InputType.IMAGE,
        node_type=NodeType.VISION,
        task_type=TaskType.VISUAL_QA,
        required_capability="vision",
        input_modalities=["text", "document", "image"],
        required_capabilities=["vision"],
        confidence=1.0,
        classifier_method=ClassifierMethod.RULE_EXPLICIT,
    )

    mock_registry = {
        "NODE-FAST-TEXT": NodeRegistryEntry(
            node_id="NODE-FAST-TEXT",
            node_name="Fast Text Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="fast-text-model",
            endpoint="http://node-fast:1234",
            status="online",
            supported_input_types=["text"],
            priority=1,
        ),
        "NODE-VISION-GEMMA": NodeRegistryEntry(
            node_id="NODE-VISION-GEMMA",
            node_name="Gemma Vision Node",
            capability="vision",
            node_type=NodeType.VISION,
            model="google/gemma-4-e4b",
            endpoint="http://node-vision:1234",
            status="online",
            supported_input_types=["image", "text"],
            priority=1,
        ),
    }

    mock_node_states = {
        "NODE-FAST-TEXT": MagicMock(status="ONLINE", latency_ms=15.0, models_loaded=["fast-text-model"], models_metadata={}),
        "NODE-VISION-GEMMA": MagicMock(status="ONLINE", latency_ms=250.0, models_loaded=["google/gemma-4-e4b"], models_metadata={}),
    }

    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=mock_node_states):
        candidates = select_best_candidates(cls)
        # Fast text node MUST be rejected
        assert len(candidates) == 1
        node, model, score, reason = candidates[0]
        assert node.node_id == "NODE-VISION-GEMMA"
        assert model == "google/gemma-4-e4b"


# ── 9. Actual file data reaches LM client ──────────────────────────────────────

def test_actual_file_data_reaches_lm_client():
    """
    Requirement 9:
    Scanned PDF renders pages to PNG and builds OpenAI-compatible image_url data URLs.
    Raw PDF binary bytes are NEVER sent in image_url.
    """
    with open(FIXTURE_FLYER_PDF, "rb") as f:
        flyer_bytes = f.read()

    att = process_attachment_bytes("flyer.pdf", "application/pdf", flyer_bytes)
    assert len(att.rendered_pages) == 1

    payload = _build_payload(
        model="google/gemma-4-e4b",
        query="Tell me what is this?",
        attachments=[att],
    )

    messages = payload["messages"]
    assert len(messages) == 1
    user_msg = messages[0]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)

    content_parts = user_msg["content"]
    assert len(content_parts) == 2

    # Part 1: text query
    assert content_parts[0]["type"] == "text"
    assert content_parts[0]["text"] == "Tell me what is this?"

    # Part 2: image_url with rendered page PNG
    assert content_parts[1]["type"] == "image_url"
    url = content_parts[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    # Verify it is valid base64 PNG data, not raw PDF bytes
    b64_str = url.split(",", 1)[1]
    decoded_header = base64.b64decode(b64_str)[:8]
    assert decoded_header == b"\x89PNG\r\n\x1a\n"   # Official PNG signature


# ── 10. Multiple attachments ──────────────────────────────────────────────────

def test_multiple_attachments():
    """Requirement 10: Supports multiple attachments (mixed image + PDF with text)."""
    with open(FIXTURE_FLYER_PNG, "rb") as f:
        png_bytes = f.read()

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Architecture Overview Document: Module A interacts with Module B.")
    pdf_bytes = doc.tobytes()

    att_img = process_attachment_bytes("diagram.png", "image/png", png_bytes)
    att_doc = process_attachment_bytes("spec.pdf", "application/pdf", pdf_bytes)

    modalities, required_caps = normalize_request("Compare the diagram with the spec", [att_img, att_doc])
    assert "text" in modalities
    assert "image" in modalities
    assert "document" in modalities
    assert "vision" in required_caps

    payload = _build_payload(
        model="google/gemma-4-e4b",
        query="Compare the diagram with the spec",
        attachments=[att_img, att_doc],
    )

    messages = payload["messages"]
    user_msg = messages[0]
    parts = user_msg["content"]
    # Text part contains both user query and extracted document text
    text_part = parts[0]
    assert "Compare the diagram with the spec" in text_part["text"]
    assert "[Attachment: spec.pdf]" in text_part["text"]
    assert "Architecture Overview Document" in text_part["text"]

    # Image part contains diagram.png
    image_part = parts[1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


# ── 11. Response is persisted without binary data in DB ───────────────────────

@pytest.mark.asyncio
async def test_response_persisted_without_binary_data():
    """Requirement 11: Query response is persisted to PostgreSQL without storing base64 binaries."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    mock_get_sess = MagicMock()
    mock_get_sess.return_value.__aenter__.return_value = mock_session

    req = QueryRequest(
        user_id="user-123",
        query="Tell me what is this?",
        session_id="sess-test-456",
        attachments=[
            Attachment(
                filename="flyer.pdf",
                content_type="application/pdf",
                data_base64="verylongbase64string" * 500,
                rendered_pages=["renderedimagebase64" * 500],
                kind=AttachmentKind.PDF,
                has_visual_content=True,
            )
        ],
    )

    resp = QueryResponse(
        request_id="00000000-0000-0000-0000-000000000001",
        user_id="user-123",
        session_id="sess-test-456",
        input_type=InputType.IMAGE,
        classification=ClassificationResult(
            input_type=InputType.IMAGE,
            node_type=NodeType.VISION,
            task_type=TaskType.VISUAL_QA,
            required_capability="vision",
            confidence=1.0,
            classifier_method=ClassifierMethod.RULE_EXPLICIT,
        ),
        routing=RoutingDecision(selected_node="NODE-1", reason="Vision candidate"),
        selected_node="NODE-1",
        selected_model="google/gemma-4-e4b",
        response="This is an internship flyer.",
        total_ms=120.0,
        classification_ms=5.0,
        routing_ms=2.0,
        inference_ms=113.0,
    )

    with patch("database.postgres.get_session", mock_get_sess), \
         patch("database.postgres.upsert_user", new=AsyncMock()), \
         patch("database.chroma.add_interaction", new=AsyncMock()):
        await persist_success(resp, req)

    # Check added rows
    added_objects = [call.args[0] for call in mock_session.add.call_args_list]
    for obj in added_objects:
        # Verify no huge base64 strings in saved objects
        for attr, val in getattr(obj, "__dict__", {}).items():
            if isinstance(val, str):
                assert "verylongbase64string" not in val
                assert "renderedimagebase64" not in val


# ── 12. Response is visible in UI / Session API ───────────────────────────────

@pytest.mark.asyncio
async def test_response_is_visible_in_sessions_api():
    """Requirement 12: Persisted session appears in /api/v1/sessions."""
    from orchestrator.models import Session
    from datetime import datetime, timezone

    fake_session = Session(
        id="sess-flyer-test",
        user_id="test-user",
        title="Winter Internship Flyer",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    with patch("database.postgres.get_session") as mock_sess_ctx:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [fake_session]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        async with _make_client() as client:
            res = await client.get("/api/v1/sessions?user_id=test-user")
            assert res.status_code == 200
            data = res.json()
            assert "sessions" in data
            assert len(data["sessions"]) == 1
            assert data["sessions"][0]["id"] == "sess-flyer-test"
            assert data["sessions"][0]["title"] == "Winter Internship Flyer"

