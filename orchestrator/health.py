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

# Map each NodeType to its configured base URL (resolved at call-time from settings)
def _node_url_map() -> dict[NodeType, str]:
    cfg = get_settings()
    return {
        NodeType.TEXT: cfg.node_1_url,
        NodeType.VISION: cfg.node_2_url,
        NodeType.REASONING: cfg.node_3_url,
        NodeType.CODE: cfg.node_4_url,
        NodeType.RAG: cfg.node_5_url,
    }


async def _probe_node(
    client: httpx.AsyncClient,
    node_type: NodeType,
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
            node_type=node_type,
            node_url=base_url,
            is_online=resp.status_code == 200,
            latency_ms=round(latency_ms, 2),
            model_loaded=model_loaded,
        )

    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        logger.warning("Node %s (%s) unreachable: %s", node_type, base_url, exc)
        return NodeHealthSchema(
            node_type=node_type,
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
            _probe_node(client, node_type, url, cfg.http_timeout)
            for node_type, url in url_map.items()
        ]
        results: List[NodeHealthSchema] = await asyncio.gather(*tasks)

    healthy = sum(1 for r in results if r.is_online)

    return ClusterHealthResponse(
        orchestrator_status="ok",
        nodes=results,
        healthy_count=healthy,
        total_count=len(results),
    )
