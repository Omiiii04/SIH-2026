"""
tests/test_phase2.py
─────────────────────
Phase 2 automated tests for:
  1. Classifier (rule-based classification)
  2. Router (end-to-end via mocked LM client)
  3. POST /api/v1/query FastAPI endpoint (via ASGI test client)
  4. Node failure / structured error handling
  5. Node registry API
"""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.classifier import classify
from orchestrator.lm_client import LMClientError, LMResponse
from orchestrator.main import app
from orchestrator.schemas import InputType, NodeType, QueryRequest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fake_lm_response(content: str = "Test response from the model.") -> LMResponse:
    return LMResponse(
        content=content,
        model="test-model",
        latency_ms=42.0,
        tokens_prompt=10,
        tokens_completion=20,
        tokens_total=30,
    )


async def _post_query(client: AsyncClient, payload: Dict[str, Any]) -> Any:
    return await client.post("/api/v1/query", json=payload)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Classifier unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestClassifier:
    """Pure unit tests — no network, no FastAPI."""

    def test_text_query_routes_to_text(self):
        result = classify("Explain transformers", InputType.TEXT)
        assert result.node_type == NodeType.TEXT

    def test_image_input_type_routes_to_vision(self):
        result = classify("anything", InputType.IMAGE)
        assert result.node_type == NodeType.VISION

    def test_code_input_type_routes_to_code(self):
        result = classify("anything", InputType.CODE)
        assert result.node_type == NodeType.CODE

    def test_reasoning_input_type_routes_to_reasoning(self):
        result = classify("anything", InputType.REASONING)
        assert result.node_type == NodeType.REASONING

    def test_retrieval_input_type_routes_to_rag(self):
        result = classify("anything", InputType.RETRIEVAL)
        assert result.node_type == NodeType.RAG

    @pytest.mark.parametrize("query", [
        "write a python function to sort a list",
        "debug this javascript code",
        "implement a recursive algorithm",
        "what is a syntax error in C++",
    ])
    def test_code_keywords_classify_to_code(self, query: str):
        result = classify(query, InputType.TEXT)
        assert result.node_type == NodeType.CODE, f"'{query}' should → CODE, got {result.node_type}"

    @pytest.mark.parametrize("query", [
        "reason step by step about quantum mechanics",
        "analyse the causes of inflation",
        "explain why the sky is blue logically",
    ])
    def test_reasoning_keywords_classify_to_reasoning(self, query: str):
        result = classify(query, InputType.TEXT)
        assert result.node_type == NodeType.REASONING

    @pytest.mark.parametrize("query", [
        "search the document for key results",
        "based on the pdf, what does section 3 say?",
        "retrieve relevant passages from the knowledge base",
    ])
    def test_rag_keywords_classify_to_rag(self, query: str):
        result = classify(query, InputType.TEXT)
        assert result.node_type == NodeType.RAG

    @pytest.mark.parametrize("query", [
        "hello how are you",
        "tell me a joke",
        "what is the capital of France?",
        "Explain transformers",
        "summarise the history of India",
    ])
    def test_general_queries_default_to_text(self, query: str):
        result = classify(query, InputType.TEXT)
        assert result.node_type == NodeType.TEXT

    def test_classification_result_has_matched_rule(self):
        result = classify("write a python script", InputType.TEXT)
        assert result.matched_rule is not None
        assert len(result.matched_rule) > 0

    def test_explicit_input_type_bypasses_keywords(self):
        """Even a code-heavy query should go to VISION if input_type=IMAGE."""
        result = classify("debug this python function", InputType.IMAGE)
        assert result.node_type == NodeType.VISION


# ─────────────────────────────────────────────────────────────────────────────
# 2. Router unit tests (mock call_node)
# ─────────────────────────────────────────────────────────────────────────────

class TestRouter:
    """Test handle_query() with call_node mocked out."""

    @pytest.mark.asyncio
    async def test_text_query_selects_node_text(self):
        req = QueryRequest(user_id="u1", query="Explain transformers", input_type=InputType.TEXT)
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response()
            from orchestrator.router import handle_query
            result = await handle_query(req)

        from orchestrator.schemas import QueryResponse
        assert isinstance(result, QueryResponse)
        assert result.selected_node == "NODE-TEXT"

    @pytest.mark.asyncio
    async def test_image_query_selects_node_vision(self):
        req = QueryRequest(user_id="u1", query="describe this photo", input_type=InputType.IMAGE)
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("I see a cat.")
            from orchestrator.router import handle_query
            result = await handle_query(req)

        from orchestrator.schemas import QueryResponse
        assert isinstance(result, QueryResponse)
        assert result.selected_node == "NODE-VISION"

    @pytest.mark.asyncio
    async def test_code_query_selects_node_code(self):
        req = QueryRequest(user_id="u1", query="write a python function", input_type=InputType.TEXT)
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("def my_func(): pass")
            from orchestrator.router import handle_query
            result = await handle_query(req)

        from orchestrator.schemas import QueryResponse
        assert isinstance(result, QueryResponse)
        assert result.selected_node == "NODE-CODE"

    @pytest.mark.asyncio
    async def test_reasoning_query_selects_node_reasoning(self):
        req = QueryRequest(user_id="u1", query="analyse why the economy collapsed step by step", input_type=InputType.TEXT)
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("Step 1...")
            from orchestrator.router import handle_query
            result = await handle_query(req)

        from orchestrator.schemas import QueryResponse
        assert isinstance(result, QueryResponse)
        assert result.selected_node == "NODE-REASONING"

    @pytest.mark.asyncio
    async def test_node_failure_returns_node_failure_response(self):
        """When call_node raises LMClientError, router returns NodeFailureResponse."""
        req = QueryRequest(user_id="u1", query="Explain transformers", input_type=InputType.TEXT)
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = LMClientError(
                error_type="connection_error",
                detail="Connection refused",
                latency_ms=15.0,
            )
            from orchestrator.router import handle_query
            result = await handle_query(req)

        from orchestrator.schemas import NodeFailureResponse
        assert isinstance(result, NodeFailureResponse)
        assert result.error_type == "connection_error"
        assert result.selected_node == "NODE-TEXT"
        assert result.latency_ms == 15.0

    @pytest.mark.asyncio
    async def test_timeout_error_returns_node_failure_response(self):
        req = QueryRequest(user_id="u1", query="Explain transformers", input_type=InputType.TEXT)
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = LMClientError(
                error_type="timeout",
                detail="Timed out after 30s",
                latency_ms=30010.0,
            )
            from orchestrator.router import handle_query
            result = await handle_query(req)

        from orchestrator.schemas import NodeFailureResponse
        assert isinstance(result, NodeFailureResponse)
        assert result.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_response_contains_request_id(self):
        req = QueryRequest(user_id="u1", query="hello world", input_type=InputType.TEXT)
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response()
            from orchestrator.router import handle_query
            result = await handle_query(req)

        assert result.request_id is not None
        assert len(result.request_id) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. POST /api/v1/query  — FastAPI integration tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


class TestQueryEndpoint:

    @pytest.mark.asyncio
    async def test_text_query_returns_200(self, client):
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("Transformers use attention mechanisms.")
            resp = await _post_query(client, {
                "user_id": "user_001",
                "query": "Explain transformers",
                "input_type": "text",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert body["selected_node"] == "NODE-TEXT"
        assert "response" in body
        assert body["response"] == "Transformers use attention mechanisms."

    @pytest.mark.asyncio
    async def test_image_query_returns_200_and_selects_vision(self, client):
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("I see a mountain.")
            resp = await _post_query(client, {
                "user_id": "user_002",
                "query": "What is in this image?",
                "input_type": "image",
            })

        assert resp.status_code == 200
        assert resp.json()["selected_node"] == "NODE-VISION"

    @pytest.mark.asyncio
    async def test_code_query_returns_200_and_selects_code(self, client):
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("def reverse(s): return s[::-1]")
            resp = await _post_query(client, {
                "user_id": "user_003",
                "query": "write a python function to reverse a string",
                "input_type": "text",
            })

        assert resp.status_code == 200
        assert resp.json()["selected_node"] == "NODE-CODE"

    @pytest.mark.asyncio
    async def test_reasoning_query_selects_reasoning_node(self, client):
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("Step 1: Consider the premises...")
            resp = await _post_query(client, {
                "user_id": "user_004",
                "query": "reason step by step about why water boils",
                "input_type": "text",
            })

        assert resp.status_code == 200
        assert resp.json()["selected_node"] == "NODE-REASONING"

    @pytest.mark.asyncio
    async def test_node_unavailable_returns_503(self, client):
        """When call_node fails, the endpoint must return 503 — not 500."""
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = LMClientError(
                error_type="connection_error",
                detail="Connection refused — LM Studio not running",
                latency_ms=5.0,
            )
            resp = await _post_query(client, {
                "user_id": "user_005",
                "query": "Explain transformers",
                "input_type": "text",
            })

        assert resp.status_code == 503
        body = resp.json()
        assert body["error_type"] == "connection_error"
        assert "detail" in body
        assert body["selected_node"] == "NODE-TEXT"

    @pytest.mark.asyncio
    async def test_response_shape_is_complete(self, client):
        """QueryResponse must have all required fields."""
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response("Hello!")
            resp = await _post_query(client, {
                "user_id": "user_006",
                "query": "hello",
                "input_type": "text",
            })

        body = resp.json()
        required = {"request_id", "user_id", "selected_node", "selected_model",
                    "response", "latency_ms", "classification", "input_type"}
        missing = required - body.keys()
        assert not missing, f"Missing fields: {missing}"

    @pytest.mark.asyncio
    async def test_classification_block_in_response(self, client):
        """The classification sub-object must include node_type and matched_rule."""
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response()
            resp = await _post_query(client, {
                "user_id": "u1",
                "query": "write a python script",
                "input_type": "text",
            })

        cls = resp.json()["classification"]
        assert "node_type" in cls
        assert cls["node_type"] == "code"
        assert "matched_rule" in cls

    @pytest.mark.asyncio
    async def test_latency_is_positive_number(self, client):
        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _fake_lm_response()
            resp = await _post_query(client, {
                "user_id": "u1",
                "query": "hello",
                "input_type": "text",
            })

        assert resp.json()["latency_ms"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. GET /api/v1/nodes
# ─────────────────────────────────────────────────────────────────────────────

class TestNodeRegistry:

    @pytest.mark.asyncio
    async def test_nodes_endpoint_returns_200(self, client):
        resp = await client.get("/api/v1/nodes")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_nodes_endpoint_returns_five_nodes(self, client):
        resp = await client.get("/api/v1/nodes")
        nodes = resp.json()
        assert len(nodes) == 5

    @pytest.mark.asyncio
    async def test_all_node_ids_present(self, client):
        resp = await client.get("/api/v1/nodes")
        node_ids = {n["node_id"] for n in resp.json()}
        assert node_ids == {
            "NODE-TEXT", "NODE-VISION", "NODE-REASONING", "NODE-CODE", "NODE-RAG"
        }

    @pytest.mark.asyncio
    async def test_each_node_has_required_fields(self, client):
        resp = await client.get("/api/v1/nodes")
        required = {"node_id", "node_name", "capability", "node_type", "model",
                    "endpoint", "status", "supported_input_types", "priority"}
        for node in resp.json():
            missing = required - node.keys()
            assert not missing, f"{node['node_id']} missing: {missing}"

    @pytest.mark.asyncio
    async def test_node_priority_is_integer(self, client):
        resp = await client.get("/api/v1/nodes")
        for node in resp.json():
            assert isinstance(node["priority"], int)
