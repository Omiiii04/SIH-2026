import pytest
from unittest.mock import AsyncMock, patch

from orchestrator.schemas import QueryRequest, InputType
from orchestrator.router import handle_query
from orchestrator.node_registry import reset_registry, set_node_status, set_node_capability
from orchestrator.schemas import NodeType


def _setup_registry_with_caps():
    """Reset registry and assign capabilities matching the old static layout."""
    reset_registry()
    set_node_capability("NODE-2", "vision",             NodeType.VISION)
    set_node_capability("NODE-3", "reasoning",           NodeType.REASONING)
    set_node_capability("NODE-4", "coding",              NodeType.CODE)
    set_node_capability("NODE-5", "embedding/retrieval", NodeType.RAG)
    for i in range(1, 6):
        set_node_status(f"NODE-{i}", "online")


def _endpoint_to_node_id() -> dict:
    """Build a map of endpoint URL → node_id from the live registry."""
    import orchestrator.node_registry as _reg
    return {entry.endpoint: nid for nid, entry in _reg._REGISTRY.items()}


@pytest.mark.asyncio
async def test_single_inference_request():
    _setup_registry_with_caps()
    call_counts = {f"NODE-{i}": 0 for i in range(1, 6)}

    async def mock_call_node(endpoint, model, query, **kwargs):
        node_map = _endpoint_to_node_id()
        node_id = node_map.get(endpoint, "UNKNOWN")
        if node_id in call_counts:
            call_counts[node_id] += 1

        from orchestrator.lm_client import LMResponse
        return LMResponse(content="mock response", model="mock-model", latency_ms=10.0, tokens_total=10)

    with patch("orchestrator.router.call_node", side_effect=mock_call_node):
        req = QueryRequest(user_id="test", query="Calculate 125 * 42", input_type=InputType.TEXT.value)
        resp = await handle_query(req)

    print(f"Call counts: {call_counts}")
    total_calls = sum(call_counts.values())
    assert total_calls == 1, f"Expected 1 inference call, got {total_calls}. Counts: {call_counts}"
    assert call_counts["NODE-3"] == 1, "Expected NODE-3 (REASONING) to be called once"


@pytest.mark.asyncio
async def test_fallback_inference_request():
    _setup_registry_with_caps()
    call_counts = {f"NODE-{i}": 0 for i in range(1, 6)}

    async def mock_call_node(endpoint, model, query, **kwargs):
        from orchestrator.lm_client import LMResponse, LMClientError
        node_map = _endpoint_to_node_id()
        node_id = node_map.get(endpoint, "UNKNOWN")
        if node_id in call_counts:
            call_counts[node_id] += 1

        if node_id == "NODE-3":
            raise LMClientError(error_type="timeout", detail="mock timeout")

        return LMResponse(content="mock response", model="mock-model", latency_ms=10.0, tokens_total=10)

    with patch("orchestrator.router.call_node", side_effect=mock_call_node):
        req = QueryRequest(user_id="test", query="Calculate 125 * 42", input_type=InputType.TEXT.value)
        resp = await handle_query(req)

    print(f"Call counts: {call_counts}")
    assert call_counts["NODE-3"] == 1, "NODE-3 should be called once and fail"
    # After NODE-3 fails, router falls back to any other available node
    total_calls = sum(call_counts.values())
    assert total_calls == 2, f"Expected 2 inference calls total, got {total_calls}. Counts: {call_counts}"
