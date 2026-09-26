"""
Health-check utilities for the SIH-2026 Orchestrator.

Probes each worker node's LM Studio endpoint and returns a
ClusterHealthResponse describing the state of the cluster.

Phase 1: structure only — actual HTTP probing is stubbed so that
the orchestrator can start without live nodes being present.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List

import httpx

from orchestrator.config import get_settings
from orchestrator.schemas import ClusterHealthResponse, NodeHealthSchema, NodeType

logger = logging.getLogger(__name__)

# Build url map dynamically from the node registry (populated from .env by
# reconcile_nodes_from_env at startup).  Falls back to parse_node_configs
# so that /health/cluster works even before the async registry is populated.
def _node_url_map() -> dict[str, str]:
    """Return a {node_id: endpoint} map for all currently registered nodes."""
    from orchestrator.node_registry import get_registry
    registry = get_registry()
    if registry:
        return {nid: entry.endpoint for nid, entry in registry.items()}

    # Fallback: read directly from .env (useful before startup completes)
    from orchestrator.env_nodes import parse_node_configs
    return {c.node_id: c.url for c in parse_node_configs()}


async def _probe_node(
    client: httpx.AsyncClient,
    node_id: str,
    base_url: str,
    timeout: float,
) -> NodeHealthSchema:
    """
    Attempt a GET to ``{base_url}/v1/models`` (LM Studio's model-list endpoint).
    Returns a NodeHealthSchema regardless of success/failure.
    """
    probe_url = f"{base_url}/v1/models"
    start = time.monotonic()
    try:
        resp = await client.get(probe_url, timeout=timeout)
        latency_ms = (time.monotonic() - start) * 1000

        model_loaded: str | None = None
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            if models:
                model_loaded = models[0].get("id")

        return NodeHealthSchema(
            node_type=NodeType.TEXT,  # default; real type from model discovery
            node_url=base_url,
            is_online=resp.status_code == 200,
            latency_ms=round(latency_ms, 2),
            model_loaded=model_loaded,
        )

    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        logger.warning("Node %s (%s) unreachable: %s", node_id, base_url, exc)
        return NodeHealthSchema(
            node_type=NodeType.TEXT,
            node_url=base_url,
            is_online=False,
            latency_ms=round(latency_ms, 2),
            model_loaded=None,
        )


async def get_cluster_health() -> ClusterHealthResponse:
    """
    Concurrently probe all worker nodes and return aggregated health.
    """
    cfg = get_settings()
    url_map = _node_url_map()

    async with httpx.AsyncClient() as client:
        tasks = [
            _probe_node(client, node_id, url, cfg.http_timeout)
            for node_id, url in url_map.items()
        ]
        results: List[NodeHealthSchema] = await asyncio.gather(*tasks)

    healthy = sum(1 for r in results if r.is_online)

    return ClusterHealthResponse(
        orchestrator_status="ok",
        nodes=results,
        healthy_count=healthy,
        total_count=len(results),
    )
