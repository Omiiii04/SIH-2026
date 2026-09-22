import asyncio
import httpx
import pytest
from unittest.mock import AsyncMock, patch

from orchestrator.schemas import QueryRequest, InputType
from orchestrator.router import handle_query
from orchestrator.node_registry import reset_registry, set_node_status

@pytest.mark.asyncio
async def test_single_inference_request():
    reset_registry()
    for i in range(1, 6):
        set_node_status(f"NODE-{i}", "online")

    call_counts = {f"NODE-{i}": 0 for i in range(1, 6)}

    async def mock_call_node(endpoint, model, query, **kwargs):
        # Determine which node was called based on endpoint
        from orchestrator.config import get_settings
        cfg = get_settings()
        node_map = {
            cfg.node_1_url: "NODE-1",
            cfg.node_2_url: "NODE-2",
            cfg.node_3_url: "NODE-3",
            cfg.node_4_url: "NODE-4",
            cfg.node_5_url: "NODE-5",
        }
        node_id = node_map.get(endpoint, "UNKNOWN")
        if node_id in call_counts:
            call_counts[node_id] += 1
            
        from orchestrator.lm_client import LMResponse
        return LMResponse(content="mock response", model="mock-model", latency_ms=10.0, tokens_total=10)

    # We patch call_node
    with patch("orchestrator.router.call_node", side_effect=mock_call_node):
        req = QueryRequest(user_id="test", query="Calculate 125 * 42", input_type=InputType.TEXT.value)
        resp = await handle_query(req)
        
    print(f"Call counts: {call_counts}")
    total_calls = sum(call_counts.values())
    assert total_calls == 1, f"Expected 1 inference call, got {total_calls}. Counts: {call_counts}"
    assert call_counts["NODE-3"] == 1, "Expected NODE-3 (REASONING) to be called once"
    
@pytest.mark.asyncio
async def test_fallback_inference_request():
    reset_registry()
    for i in range(1, 6):
        set_node_status(f"NODE-{i}", "online")

    call_counts = {f"NODE-{i}": 0 for i in range(1, 6)}

    async def mock_call_node(endpoint, model, query, **kwargs):
        from orchestrator.config import get_settings
        from orchestrator.lm_client import LMResponse, LMClientError
        cfg = get_settings()
        node_map = {
            cfg.node_1_url: "NODE-1",
            cfg.node_2_url: "NODE-2",
            cfg.node_3_url: "NODE-3",
            cfg.node_4_url: "NODE-4",
            cfg.node_5_url: "NODE-5",
        }
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
    assert call_counts["NODE-1"] == 1, "NODE-1 should be called as fallback"
    total_calls = sum(call_counts.values())
    assert total_calls == 2, f"Expected 2 inference calls total, got {total_calls}. Counts: {call_counts}"

