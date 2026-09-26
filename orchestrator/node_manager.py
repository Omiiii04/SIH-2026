"""
orchestrator/node_manager.py
Dynamic LAN node management and discovery.
"""

import logging
import uuid
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from database.postgres import get_session
from database.models import WorkerNode, WorkerModel
from orchestrator.config import get_settings
from orchestrator.node_registry import _REGISTRY, _TYPE_TO_NODE_ID, _CAPABILITY_TO_NODE_IDS, NodeRegistryEntry
from orchestrator.schemas import NodeType

logger = logging.getLogger(__name__)

def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.strip().rstrip('/')

async def bootstrap_nodes() -> None:
    """Import existing .env nodes into PostgreSQL if the table is empty."""
    async with get_session() as session:
        result = await session.execute(select(WorkerNode).limit(1))
        if result.scalar_one_or_none() is not None:
            # Already bootstrapped, load from DB
            await sync_registry_from_db()
            return
            
        logger.info("Bootstrapping dynamic nodes from .env...")
        cfg = get_settings()
        
        env_nodes = [
            ("NODE-1", "Node 1 (Text)", cfg.node_1_url, 1),
            ("NODE-2", "Node 2 (Vision)", cfg.node_2_url, 1),
            ("NODE-3", "Node 3 (Reasoning)", cfg.node_3_url, 1),
            ("NODE-4", "Node 4 (Coding)", cfg.node_4_url, 1),
            ("NODE-5", "Node 5 (RAG)", cfg.node_5_url, 1),
        ]
        
        for n_id, name, url, priority in env_nodes:
            if not url.strip():
                continue
            norm_url = _normalize_endpoint(url)
            node = WorkerNode(
                id=n_id,
                name=name,
                endpoint=norm_url,
                enabled=True,
                status="unknown",
                priority=priority
            )
            session.add(node)
            
        await session.commit()
        await sync_registry_from_db()

async def sync_registry_from_db() -> None:
    """Read all enabled nodes from DB and update the active registry."""
    async with get_session() as session:
        result = await session.execute(select(WorkerNode).where(WorkerNode.enabled == True))
        nodes = result.scalars().all()
        
    new_registry = {}
    for n in nodes:
        # Re-construct entry
        entry = NodeRegistryEntry(
            node_id=n.id,
            node_name=n.name,
            capability="text", # Base capability, will be discovered fully in scheduler
            node_type=NodeType.TEXT, # Scheduler doesn't rely on this anymore
            model="",
            endpoint=n.endpoint,
            status=n.status,
            supported_input_types=["text"],
            priority=n.priority
        )
        new_registry[n.id] = entry
        
    # Update globals in node_registry safely
    _REGISTRY.clear()
    _REGISTRY.update(new_registry)
    _TYPE_TO_NODE_ID.clear()
    _CAPABILITY_TO_NODE_IDS.clear()
    for e in _REGISTRY.values():
        _CAPABILITY_TO_NODE_IDS.setdefault(e.capability, []).append(e.node_id)
        
    logger.info(f"Registry synced from DB: {len(_REGISTRY)} enabled nodes.")

async def discover_models(endpoint: str) -> list[dict]:
    """Query /v1/models to get models on the node."""
    url = f"{_normalize_endpoint(endpoint)}/v1/models"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
    except Exception as exc:
        logger.warning(f"Failed to discover models at {url}: {exc}")
    return []

async def probe_node(node_id: str) -> dict:
    """Probe an existing node, update its DB record and models, return its new state."""
    async with get_session() as session:
        node = await session.get(WorkerNode, node_id)
        if not node:
            raise ValueError(f"Node {node_id} not found")
            
        models_data = await discover_models(node.endpoint)
        is_online = len(models_data) > 0 or True # Still reachable if models fail? We actually test endpoint
        
        # Test basic reachability if models list is empty
        latency = 0.0
        now = datetime.utcnow()
        try:
            t0 = httpx.Timeout(5.0)
            async with httpx.AsyncClient() as client:
                start = datetime.now()
                resp = await client.get(f"{node.endpoint}/v1/models", timeout=t0)
                latency = (datetime.now() - start).total_seconds() * 1000
                is_online = resp.status_code == 200
        except Exception:
            is_online = False
            
        node.last_checked = now
        node.status = "online" if is_online else "offline"
        if is_online:
            node.last_success = now
            
        # Update models
        if is_online:
            # Delete old models
            await session.execute(WorkerModel.__table__.delete().where(WorkerModel.node_id == node_id))
            for m in models_data:
                model_id = m.get("id", "unknown")
                session.add(WorkerModel(
                    node_id=node_id,
                    model_id=model_id,
                    discovered_at=now
                ))
                
        await session.commit()
        await sync_registry_from_db()
        
        return {
            "node_id": node.id,
            "status": node.status,
            "latency_ms": latency,
            "models": [m.get("id") for m in models_data]
        }
