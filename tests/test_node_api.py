"""
tests/test_node_api.py
──────────────────────
Tests for the dynamic node management API (GET /api/v1/nodes, etc.)
Replaces hardcoded fixed-node tests.
"""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app

def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

@pytest.fixture
def mock_db_nodes():
    from database.models import WorkerNode
    import uuid
    from datetime import datetime
    return [
        WorkerNode(id=uuid.uuid4(), node_id="NODE-1", name="N1", endpoint="http://n1", enabled=True, status="online", priority=1, last_checked=datetime.utcnow()),
        WorkerNode(id=uuid.uuid4(), node_id="NODE-2", name="N2", endpoint="http://n2", enabled=False, status="offline", priority=2, last_checked=datetime.utcnow()),
    ]

@pytest.mark.asyncio
async def test_get_nodes(mock_db_nodes):
    with patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):
        
        # We need to mock the get_session to return our mock nodes
        # But wait, GET /api/v1/nodes reads from orchestrator.node_registry or DB directly?
        # Let's mock the actual endpoint logic. If it reads from DB:
        with patch("database.postgres.get_session") as mock_sess_ctx:
            from unittest.mock import MagicMock
            mock_session = AsyncMock()
            # mock_session.execute().unique().scalars().all() -> mock_db_nodes
            mock_execute = MagicMock()
            mock_execute.unique.return_value.scalars.return_value.all.return_value = mock_db_nodes
            mock_session.execute.return_value = mock_execute
            mock_sess_ctx.return_value.__aenter__.return_value = mock_session
            
            async with _make_client() as client:
                resp = await client.get("/api/v1/nodes")
                
            assert resp.status_code == 200
            data = resp.json()
            nodes = data.get("nodes", data.get("data", []))
            assert len(nodes) >= 1
            
            n1 = next(n for n in nodes if n["node_id"] == "NODE-1")
            assert n1["name"] == "N1"
            assert n1["enabled"] is True

@pytest.mark.asyncio
async def test_sync_nodes_endpoint():
    with patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"), \
         patch("orchestrator.node_manager.reconcile_nodes_from_env", new_callable=AsyncMock) as mock_reconcile:
        
        async with _make_client() as client:
            resp = await client.post("/api/v1/nodes/sync-config")
            
        assert resp.status_code == 200
        mock_reconcile.assert_awaited_once()
        assert resp.json()["reconciled"] is True

@pytest.mark.asyncio
async def test_probe_node_endpoint():
    with patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"), \
         patch("orchestrator.node_manager.probe_node", new_callable=AsyncMock) as mock_probe:
        
        mock_probe.return_value = {"node_id": "NODE-1", "status": "online", "models": ["m1"]}
        
        async with _make_client() as client:
            resp = await client.post("/api/v1/nodes/NODE-1/probe")
            
        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"] == "NODE-1"
        assert data["status"] == "online"
        assert data["models"] == ["m1"]
        mock_probe.assert_awaited_once_with("NODE-1")
