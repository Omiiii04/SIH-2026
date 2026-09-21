from __future__ import annotations

import asyncio
import logging
import time
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

import httpx

from orchestrator.config import get_settings
from orchestrator.node_registry import get_registry, set_node_model, set_node_status
from orchestrator.schemas import NodeStatus, NodeStatusEntry

logger = logging.getLogger(__name__)

DEGRADED_THRESHOLD_MS = 2000.0
PROBE_TIMEOUT         = 5.0
WINDOW_SIZE           = 1000

@dataclass
class NodeState:
    node_id:       str
    status:        NodeStatus = NodeStatus.OFFLINE
    latency_ms:    Optional[float] = None
    model_loaded:  Optional[str]   = None
    capacity:      Optional[str]   = None
    last_checked:  Optional[datetime] = None
    last_success:  Optional[datetime] = None

_NODE_STATES: Dict[str, NodeState] = {}

def get_node_states() -> Dict[str, NodeState]:
    return _NODE_STATES

def get_node_status_entries() -> list[NodeStatusEntry]:
    return [
        NodeStatusEntry(
            node_id=s.node_id,
            status=s.status,
            latency_ms=s.latency_ms,
            model_loaded=s.model_loaded,
            capacity=s.capacity,
            last_checked=s.last_checked,
            last_success=s.last_success,
        )
        for s in _NODE_STATES.values()
    ]

def _init_node_states() -> None:
    registry = get_registry()
    for node_id in registry:
        if node_id not in _NODE_STATES:
            _NODE_STATES[node_id] = NodeState(node_id=node_id)

async def _probe(client: httpx.AsyncClient, node_id: str, base_url: str) -> None:
    if not base_url or not base_url.strip():
        _NODE_STATES[node_id] = NodeState(node_id=node_id, status=NodeStatus.OFFLINE, last_checked=datetime.now(timezone.utc))
        set_node_status(node_id, "offline")
        return

    probe_url = f"{base_url.rstrip('/')}/v1/models"
    t0 = time.monotonic()
    now = datetime.now(timezone.utc)
    try:
        resp = await client.get(probe_url, timeout=PROBE_TIMEOUT)
        latency_ms = (time.monotonic() - t0) * 1000
        model_loaded: Optional[str] = None
        capacity: Optional[str] = None
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            if models:
                model_loaded = models[0].get("id")
                # Attempt to extract capacity e.g. "8b", "7.5B"
                if model_loaded:
                    match = re.search(r'([\d\.]+[bB])', model_loaded)
                    if match:
                        capacity = match.group(1).upper() + " Params"
            status = NodeStatus.DEGRADED if latency_ms > DEGRADED_THRESHOLD_MS else NodeStatus.ONLINE
            registry_status = "online"
            last_success = now
            # Sync the live model name into the registry so the router always
            # uses the exact model ID that LM Studio reports.
            if model_loaded:
                set_node_model(node_id, model_loaded)
        else:
            status = NodeStatus.OFFLINE
            registry_status = "offline"
            last_success = _NODE_STATES.get(node_id, NodeState(node_id=node_id)).last_success
        state = _NODE_STATES.get(node_id, NodeState(node_id=node_id))
        _NODE_STATES[node_id] = NodeState(
            node_id=node_id, status=status, latency_ms=round(latency_ms, 1),
            model_loaded=model_loaded, capacity=capacity, last_checked=now,
            last_success=last_success if status != NodeStatus.OFFLINE else state.last_success,
        )
        set_node_status(node_id, registry_status)
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        logger.debug("Health probe failed for %s: %s", node_id, exc)
        old = _NODE_STATES.get(node_id, NodeState(node_id=node_id))
        _NODE_STATES[node_id] = NodeState(
            node_id=node_id, status=NodeStatus.OFFLINE, latency_ms=round(latency_ms, 1),
            model_loaded=None, capacity=None, last_checked=now, last_success=old.last_success,
        )
        set_node_status(node_id, "offline")

_monitor_task: Optional[asyncio.Task] = None

async def _monitor_loop() -> None:
    cfg = get_settings()
    _init_node_states()
    logger.info("Health monitor started (interval=%ds).", cfg.health_check_interval)
    while True:
        try:
            registry = get_registry()
            async with httpx.AsyncClient() as client:
                await asyncio.gather(
                    *[_probe(client, node_id, node.endpoint) for node_id, node in registry.items()],
                    return_exceptions=True,
                )
            logger.debug("Health check done: %s", {nid: s.status.value for nid, s in _NODE_STATES.items()})
        except Exception as exc:
            logger.warning("Monitor loop error: %s", exc)
        await asyncio.sleep(cfg.health_check_interval)

def start_monitor() -> None:
    global _monitor_task
    if _monitor_task is None or _monitor_task.done():
        _monitor_task = asyncio.create_task(_monitor_loop())
        logger.info("Node health monitor task created.")

def stop_monitor() -> None:
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
        logger.info("Node health monitor stopped.")
    _monitor_task = None

@dataclass
class RequestRecord:
    success:        bool
    total_ms:       float
    routing_ms:     float
    inference_ms:   float
    retry_count:    int
    was_fallback:   bool
    final_node:     str
    status:         str

_METRICS: Deque[RequestRecord] = deque(maxlen=WINDOW_SIZE)

def record_request(record: RequestRecord) -> None:
    _METRICS.append(record)

def get_metrics_snapshot() -> dict:
    records = list(_METRICS)
    total = len(records)
    if total == 0:
        return {"total_requests": 0, "successful": 0, "failed": 0, "success_rate": 0.0, "window_size": 0, "total_retries": 0, "fallback_count": 0}
    successes = [r for r in records if r.success]
    n_ok = len(successes)
    latencies = [r.total_ms for r in successes]
    routing   = [r.routing_ms for r in records]
    inference = [r.inference_ms for r in successes]
    return {
        "total_requests":   total,
        "successful":       n_ok,
        "failed":           total - n_ok,
        "success_rate":     round(n_ok / total, 4),
        "avg_latency_ms":   round(sum(latencies) / len(latencies), 1) if latencies else None,
        "min_latency_ms":   round(min(latencies), 1) if latencies else None,
        "max_latency_ms":   round(max(latencies), 1) if latencies else None,
        "avg_routing_ms":   round(sum(routing) / len(routing), 1) if routing else None,
        "avg_inference_ms": round(sum(inference) / len(inference), 1) if inference else None,
        "total_retries":    sum(r.retry_count for r in records),
        "fallback_count":   sum(1 for r in records if r.was_fallback),
        "window_size":      total,
    }
