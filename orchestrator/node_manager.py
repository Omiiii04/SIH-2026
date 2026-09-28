"""
orchestrator/node_manager.py
─────────────────────────────
Dynamic LAN node management.

Public entry points
-------------------
  reconcile_nodes_from_env()   — parse .env, sync with PostgreSQL (every startup)
  sync_registry_from_db()      — rebuild in-memory registry from enabled DB nodes
  discover_models(endpoint)    — GET /v1/models from a node
  probe_node(node_id)          — probe one node, refresh models, return state
"""

from __future__ import annotations

import logging
import uuid
import httpx

from datetime import datetime, timezone
from sqlalchemy import select

from database.postgres import get_session
from database.models import WorkerNode, WorkerModel
from orchestrator.node_registry import (
    _REGISTRY,
    _CAPABILITY_TO_NODE_IDS,
    NodeRegistryEntry,
)
from orchestrator.schemas import NodeType

logger = logging.getLogger(__name__)


def _normalize_endpoint(endpoint: str) -> str:
    return endpoint.strip().rstrip("/")


# ─────────────────────────────────────────────────────────────────────────────
# Reconciliation — runs on every startup and on POST /sync-config
# ─────────────────────────────────────────────────────────────────────────────

async def reconcile_nodes_from_env() -> None:
    """
    Parse .env → compare with PostgreSQL → create / update / disable nodes.

    Rules:
      - Nodes present in .env but missing from DB → created.
      - Nodes in both .env and DB → endpoint/name/priority updated if changed;
        re-enabled if they were previously disabled.
      - Nodes in DB but absent from .env → enabled set to False (disabled).
        Their historical routing/request records are preserved.
      - NODE_N_ENABLED=false in .env → node is stored disabled.
      - No node is ever hard-deleted by this function.

    Re-reads the .env file on every call so that POST /sync-config picks up
    changes made to .env without restarting the orchestrator.
    """
    from orchestrator.env_nodes import parse_node_configs  # local to allow test injection

    configs = parse_node_configs()   # reads from .env file each time
    configured_ids = {c.node_id for c in configs}

    async with get_session() as session:
        result = await session.execute(select(WorkerNode))
        existing: dict[str, WorkerNode] = {
            n.node_id: n for n in result.unique().scalars().all()
        }

        for cfg in configs:
            norm_url = _normalize_endpoint(cfg.url)
            desired_enabled = cfg.enabled   # honour NODE_N_ENABLED from .env

            if cfg.node_id in existing:
                node = existing[cfg.node_id]
                changed = False

                if node.endpoint != norm_url:
                    node.endpoint = norm_url
                    changed = True
                if node.name != cfg.name:
                    node.name = cfg.name
                    changed = True
                if node.priority != cfg.priority:
                    node.priority = cfg.priority
                    changed = True
                # Re-enable if it was disabled but is now back in .env
                # (or keep disabled if NODE_N_ENABLED=false)
                if node.enabled != desired_enabled:
                    node.enabled = desired_enabled
                    changed = True

                if changed:
                    logger.info("Updated node %s (endpoint=%s enabled=%s)",
                                cfg.node_id, norm_url, desired_enabled)
            else:
                # Brand-new node — not in DB yet
                node = WorkerNode(
                    node_id=cfg.node_id,
                    name=cfg.name,
                    endpoint=norm_url,
                    hostname="",
                    lm_studio_url=norm_url,
                    enabled=desired_enabled,
                    status="unknown",
                    priority=cfg.priority,
                )
                session.add(node)
                logger.info("Created node %s → %s (enabled=%s)",
                            cfg.node_id, norm_url, desired_enabled)

        # Disable nodes that have been removed from .env
        for node_id, node in existing.items():
            if node_id not in configured_ids and node.enabled:
                node.enabled = False
                logger.info("Disabled node %s (no longer in .env)", node_id)

        await session.commit()

    await sync_registry_from_db()
    logger.info("Node reconciliation complete: %d configured nodes.", len(configs))


# ─────────────────────────────────────────────────────────────────────────────
# Registry sync — rebuilds the in-memory node registry from DB
# ─────────────────────────────────────────────────────────────────────────────

async def sync_registry_from_db() -> None:
    """
    Read all *enabled* nodes from DB and update the active in-memory registry.
    Disabled nodes are excluded so the scheduler never routes to them.
    """
    async with get_session() as session:
        result = await session.execute(
            select(WorkerNode).where(WorkerNode.enabled == True)  # noqa: E712
        )
        nodes = result.unique().scalars().all()

    new_registry: dict[str, NodeRegistryEntry] = {}
    for n in nodes:
        entry = NodeRegistryEntry(
            node_id=n.node_id,
            node_name=n.name or n.node_id,
            capability="text",          # base default; real caps discovered per-model
            node_type=NodeType.TEXT,    # scheduler uses model-level capability, not this
            model="",
            endpoint=n.endpoint,
            status=n.status or "unknown",
            supported_input_types=["text"],
            priority=n.priority if n.priority is not None else 1,
        )
        new_registry[n.node_id] = entry

    # Atomic replace of the shared registry dict
    _REGISTRY.clear()
    _REGISTRY.update(new_registry)

    _CAPABILITY_TO_NODE_IDS.clear()
    for e in _REGISTRY.values():
        _CAPABILITY_TO_NODE_IDS.setdefault(e.capability, []).append(e.node_id)

    logger.info("Registry synced from DB: %d enabled node(s).", len(_REGISTRY))


# ─────────────────────────────────────────────────────────────────────────────
# Model discovery
# ─────────────────────────────────────────────────────────────────────────────

async def discover_models(
    endpoint: str,
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict]:
    """
    Discover models and their capabilities on a node.
    Primary: GET /api/v1/models (LM Studio native API, provides explicit capabilities).
    Fallback: GET /v1/models (OpenAI compatibility endpoint).
    """
    norm = _normalize_endpoint(endpoint)
    close_client = False
    if client is None:
        client = httpx.AsyncClient()
        close_client = True

    try:
        # 1. Primary: LM Studio native model endpoint
        try:
            resp = await client.get(f"{norm}/api/v1/models", timeout=5.0)
            if resp.status_code == 200:
                body = resp.json()
                models_list = body.get("models")
                if isinstance(models_list, list) and models_list:
                    discovered = []
                    for m in models_list:
                        loaded_instances = m.get("loaded_instances", [])
                        model_id = None
                        if loaded_instances and isinstance(loaded_instances, list):
                            inst = loaded_instances[0]
                            if isinstance(inst, dict):
                                model_id = inst.get("id")
                        if not model_id:
                            model_id = m.get("key") or m.get("id") or "unknown"

                        quant = m.get("quantization")
                        quant_name = quant.get("name") if isinstance(quant, dict) else str(quant or "")
                        caps = m.get("capabilities", {})
                        if not isinstance(caps, dict):
                            caps = {}

                        discovered.append({
                            "id": model_id,
                            "type": m.get("type", "llm"),
                            "publisher": m.get("publisher", ""),
                            "display_name": m.get("display_name", ""),
                            "architecture": m.get("architecture", ""),
                            "quantization": quant_name,
                            "params_string": m.get("params_string", ""),
                            "context_length": m.get("max_context_length"),
                            "is_loaded": bool(loaded_instances),
                            "capabilities": caps,
                            "capability_source": "lmstudio_metadata",
                        })
                    if discovered:
                        logger.debug("Discovered %d model(s) via native /api/v1/models from %s", len(discovered), norm)
                        return discovered
        except Exception as exc:
            logger.debug("Native /api/v1/models failed for %s: %s", norm, exc)

        # 2. Fallback: OpenAI-compatible endpoint
        try:
            resp = await client.get(f"{norm}/v1/models", timeout=5.0)
            if resp.status_code == 200:
                body = resp.json()
                models_data = body.get("data", [])
                discovered = []
                for m in models_data:
                    discovered.append({
                        "id": m.get("id", "unknown"),
                        "type": "llm",
                        "is_loaded": True,
                        "capabilities": {},
                        "capability_source": "inferred",
                    })
                logger.debug("Discovered %d model(s) via /v1/models fallback from %s", len(discovered), norm)
                return discovered
        except Exception as exc:
            logger.warning("discover_models failed for %s: %s", norm, exc)

    finally:
        if close_client:
            await client.aclose()

    return []


# ─────────────────────────────────────────────────────────────────────────────
# Node probe
# ─────────────────────────────────────────────────────────────────────────────

async def probe_node(node_id: str) -> dict:
    """
    Probe a node: measure latency, discover models, update DB + registry.

    Parameters
    ----------
    node_id : The NODE-N string identifier (e.g. "NODE-3").

    Returns
    -------
    dict with keys: node_id, status, latency_ms, models, models_detailed
    """
    import json
    import time
    from orchestrator.node_registry import set_node_model

    async with get_session() as session:
        result = await session.execute(
            select(WorkerNode).where(WorkerNode.node_id == node_id)
        )
        node = result.unique().scalar_one_or_none()
        if not node:
            raise ValueError(f"Node {node_id!r} not found in DB")

        latency_ms = 0.0
        now = datetime.utcnow()  # naive UTC — matches TIMESTAMP WITHOUT TIME ZONE columns
        models_data: list[dict] = []

        try:
            async with httpx.AsyncClient() as client:
                start = time.monotonic()
                models_data = await discover_models(node.endpoint, client=client)
                latency_ms = (time.monotonic() - start) * 1000
                is_online = len(models_data) > 0
        except Exception:
            is_online = False

        node.last_checked = now
        node.status = "online" if is_online else "offline"
        if is_online:
            node.last_success = now

        # Refresh discovered models (delete old, insert new)
        if is_online and models_data:
            await session.execute(
                WorkerModel.__table__.delete().where(
                    WorkerModel.node_id == node_id
                )
            )
            for m in models_data:
                model_id = m.get("id", "unknown")
                session.add(WorkerModel(
                    node_id=node_id,
                    model_id=model_id,
                    model_type=m.get("type"),
                    architecture=m.get("architecture"),
                    quantization=m.get("quantization"),
                    context_length=m.get("context_length"),
                    is_loaded=m.get("is_loaded", True),
                    capabilities_str=json.dumps(m.get("capabilities", {})),
                    discovered_at=now,
                ))

        await session.commit()

    await sync_registry_from_db()

    # Update active model in registry
    active_model = ""
    if models_data:
        loaded = [m.get("id") for m in models_data if m.get("is_loaded")]
        active_model = loaded[0] if loaded else models_data[0].get("id", "")
        if active_model:
            set_node_model(node_id, active_model)

    return {
        "node_id": node_id,
        "status": "online" if is_online else "offline",
        "latency_ms": round(latency_ms, 1),
        "models": [m.get("id") for m in models_data],
        "models_detailed": models_data,
    }
