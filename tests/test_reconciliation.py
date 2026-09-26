"""
tests/test_reconciliation.py
────────────────────────────
Tests for orchestrator.node_manager.reconcile_nodes_from_env() and sync logic.
"""
import pytest
from unittest.mock import AsyncMock, patch
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
    from database.postgres import get_session
    
    with patch("orchestrator.env_nodes.parse_node_configs", return_value=mock_env_nodes), \
         patch("database.postgres.init_db", new_callable=AsyncMock):
        
        await reconcile_nodes_from_env()
        
        async with get_session() as session:
            res = await session.execute(select(WorkerNode))
            nodes = res.scalars().all()
            
            assert len(nodes) == 2
            n1 = next(n for n in nodes if n.node_id == "NODE-1")
            assert n1.endpoint == "http://10.0.0.1:1234"
            assert n1.enabled is True
            
            n2 = next(n for n in nodes if n.node_id == "NODE-2")
            assert n2.enabled is False
            
        assert "NODE-1" in _REGISTRY
        assert "NODE-2" not in _REGISTRY # Disabled node is excluded from registry

@pytest.mark.asyncio
async def test_reconcile_updates_existing_nodes(mock_env_nodes):
    from orchestrator.node_manager import reconcile_nodes_from_env
    from database.postgres import get_session
    
    with patch("orchestrator.env_nodes.parse_node_configs", return_value=mock_env_nodes):
        await reconcile_nodes_from_env()
        
    updated_env = [
        NodeEnvConfig(index=1, node_id="NODE-1", url="http://10.0.0.9:1234", name="Node 1 Updated", priority=5, enabled=True),
    ]
    with patch("orchestrator.env_nodes.parse_node_configs", return_value=updated_env):
        await reconcile_nodes_from_env()
        
        async with get_session() as session:
            res = await session.execute(select(WorkerNode))
            nodes = res.scalars().all()
            
            n1 = next(n for n in nodes if n.node_id == "NODE-1")
            assert n1.endpoint == "http://10.0.0.9:1234"
            assert n1.name == "Node 1 Updated"
            assert n1.priority == 5
            
            n2 = next(n for n in nodes if n.node_id == "NODE-2")
            assert n2.enabled is False # Was removed from env, so it got disabled

@pytest.mark.asyncio
async def test_sync_registry_from_db():
    from orchestrator.node_manager import sync_registry_from_db
    from orchestrator.node_registry import _REGISTRY
    from database.postgres import get_session
    
    async with get_session() as session:
        session.add(WorkerNode(node_id="NODE-3", endpoint="http://n3", enabled=True))
        session.add(WorkerNode(node_id="NODE-4", endpoint="http://n4", enabled=False))
        await session.commit()
        
    await sync_registry_from_db()
    
    assert "NODE-3" in _REGISTRY
    assert "NODE-4" not in _REGISTRY
