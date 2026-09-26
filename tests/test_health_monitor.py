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
async def test_health_check_cycle(mock_registry):
    from orchestrator.monitor import _health_check_cycle
    from orchestrator.node_manager import probe_node
    
    # We want to mock probe_node so we don't actually hit the network or DB
    with patch("orchestrator.monitor.get_registry", return_value=mock_registry), \
         patch("orchestrator.node_manager.probe_node", new_callable=AsyncMock) as mock_probe, \
         patch("orchestrator.monitor.set_node_state") as mock_set_state:
        
        # Make probe_node return mock data
        async def fake_probe(node_id):
            return {"node_id": node_id, "status": "online", "latency_ms": 10.0, "models": ["llama"]}
        mock_probe.side_effect = fake_probe
        
        await _health_check_cycle()
        
        # It should have probed all nodes in the registry
        assert mock_probe.await_count == 2
        mock_probe.assert_any_await("NODE-1")
        mock_probe.assert_any_await("NODE-2")
        
        # It should have updated the state for both nodes
        assert mock_set_state.call_count == 2
