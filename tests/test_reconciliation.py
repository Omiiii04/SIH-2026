"""
tests/test_reconciliation.py
────────────────────────────
Tests for orchestrator.node_manager.reconcile_nodes_from_env() and sync logic.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select
from database.models import WorkerNode
from orchestrator.env_nodes import NodeEnvConfig

@pytest.fixture
def mock_env_nodes():
    return [
        NodeEnvConfig(index=1, node_id="NODE-1", url="http://10.0.0.1:1234", name="Node 1", priority=1, enabled=True),
        NodeEnvConfig(index=2, node_id="NODE-2", url="http://10.0.0.2:1234", name="Node 2", priority=2, enabled=False),
    ]

@pytest.mark.asyncio
async def test_reconcile_creates_new_nodes(mock_env_nodes):
    from orchestrator.node_manager import reconcile_nodes_from_env
    from orchestrator.node_registry import _REGISTRY
    
    with patch("orchestrator.env_nodes.parse_node_configs", return_value=mock_env_nodes), \
         patch("database.postgres.get_session") as mock_sess_ctx, \
         patch("orchestrator.node_manager.sync_registry_from_db", new_callable=AsyncMock):
        
        mock_session = AsyncMock()
        mock_execute = AsyncMock()
        mock_execute.unique.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_execute
        mock_sess_ctx.return_value.__aenter__.return_value = mock_session
        
        await reconcile_nodes_from_env()
        
        assert mock_session.add.call_count == 2
        added_nodes = [call.args[0] for call in mock_session.add.call_args_list]
        n1 = next(n for n in added_nodes if n.node_id == "NODE-1")
        assert n1.endpoint == "http://10.0.0.1:1234"
        assert n1.enabled is True
        
        n2 = next(n for n in added_nodes if n.node_id == "NODE-2")
        assert n2.enabled is False

@pytest.mark.asyncio
async def test_reconcile_updates_existing_nodes(mock_env_nodes):
    from orchestrator.node_manager import reconcile_nodes_from_env
    
    # Existing DB state
    n1_existing = WorkerNode(node_id="NODE-1", endpoint="http://old", name="old", priority=10, enabled=False)
    n2_existing = WorkerNode(node_id="NODE-2", endpoint="http://10.0.0.2:1234", enabled=True)
    
    with patch("orchestrator.env_nodes.parse_node_configs", return_value=mock_env_nodes), \
         patch("database.postgres.get_session") as mock_sess_ctx, \
         patch("orchestrator.node_manager.sync_registry_from_db", new_callable=AsyncMock):
        
        mock_session = AsyncMock()
        mock_execute = AsyncMock()
        mock_execute.unique.return_value.scalars.return_value.all.return_value = [n1_existing, n2_existing]
        mock_session.execute.return_value = mock_execute
        mock_sess_ctx.return_value.__aenter__.return_value = mock_session
        
        await reconcile_nodes_from_env()
        
        # It should have updated n1 inline
        assert n1_existing.endpoint == "http://10.0.0.1:1234"
        assert n1_existing.name == "Node 1"
        assert n1_existing.enabled is True
        
        # It should have updated n2 inline
        assert n2_existing.enabled is False

@pytest.mark.asyncio
async def test_sync_registry_from_db():
    from orchestrator.node_manager import sync_registry_from_db
    from orchestrator.node_registry import _REGISTRY
    
    n3 = WorkerNode(node_id="NODE-3", endpoint="http://n3", enabled=True, name="N3")
    n4 = WorkerNode(node_id="NODE-4", endpoint="http://n4", enabled=False, name="N4")
    
    with patch("database.postgres.get_session") as mock_sess_ctx:
        mock_session = AsyncMock()
        mock_execute = AsyncMock()
        # Query in sync_registry_from_db filters for enabled=True, but let's assume the mock just returns n3
        mock_execute.unique.return_value.scalars.return_value.all.return_value = [n3]
        mock_session.execute.return_value = mock_execute
        mock_sess_ctx.return_value.__aenter__.return_value = mock_session
        
        await sync_registry_from_db()
        
    assert "NODE-3" in _REGISTRY
    assert "NODE-4" not in _REGISTRY
