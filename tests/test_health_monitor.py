"""
tests/test_health_monitor.py
────────────────────────────
Tests for the background health monitor task.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
def mock_registry():
    from orchestrator.schemas import NodeRegistryEntry, NodeType
    return {
        "NODE-1": NodeRegistryEntry(node_id="NODE-1", node_name="N1", capability="text", node_type=NodeType.TEXT, model="m1", endpoint="http://n1", status="online", supported_input_types=["text"], priority=1),
        "NODE-2": NodeRegistryEntry(node_id="NODE-2", node_name="N2", capability="text", node_type=NodeType.TEXT, model="m2", endpoint="http://n2", status="offline", supported_input_types=["text"], priority=1),
    }

@pytest.mark.asyncio
async def test_probe_updates_state(mock_registry):
    from orchestrator.monitor import _probe, get_node_states
    import httpx
    from datetime import datetime, timezone
    
    # We want to mock the httpx client get call
    client = AsyncMock(spec=httpx.AsyncClient)
    
    # Create a mock response
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "llama-3-8b"}]}
    client.get.return_value = mock_resp
    
    with patch("orchestrator.monitor.set_node_status") as mock_set_status, \
         patch("orchestrator.monitor.set_node_model") as mock_set_model:
        
        await _probe(client, "NODE-1", "http://n1")
        
        # Verify httpx client was called
        client.get.assert_awaited_once_with("http://n1/v1/models", timeout=5.0)
        
        # Verify state was updated
        states = get_node_states()
        assert "NODE-1" in states
        assert states["NODE-1"].status.value == "online"
        assert "llama-3-8b" in states["NODE-1"].models_loaded
        
        # Verify registry was updated
        mock_set_status.assert_called_with("NODE-1", "online")
        mock_set_model.assert_called_with("NODE-1", "llama-3-8b")
