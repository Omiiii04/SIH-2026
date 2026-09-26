"""
SIH-2026 Orchestrator - FastAPI Application Entry Point.

Routes
------
  GET  /health                    -> orchestrator liveness probe
  GET  /health/cluster            -> probes all worker nodes
  GET  /api/v1/nodes              -> Phase 5 node status (ONLINE/DEGRADED/OFFLINE + latency)
  GET  /api/v1/metrics            -> Phase 5 aggregate request metrics
  PATCH /api/v1/nodes/{id}/status -> runtime node status override
  POST /api/v1/query              -> Phase 2/3/5 live inference pipeline
  POST /api/v1/memory/search      -> Phase 4 semantic memory search
  POST /infer                     -> Phase 1 stub (deprecated)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Union
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from orchestrator.config import get_settings
from orchestrator.health import get_cluster_health
from orchestrator.node_registry import list_nodes, set_node_status
from orchestrator.router import handle_query
from orchestrator.schemas import (
    ClusterHealthResponse,
    ErrorResponse,
    InferenceRequest,
    InferenceResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MetricsResponse,
    NodeFailureResponse,
    NodeRegistryEntry,
    NodeStatusResponse,
    NodeType,
    QueryRequest,
    QueryResponse,
    RoutingDecision,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

cfg = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise databases and health monitor on startup, clean up on shutdown."""

    logger.info("=== SIH-2026 Orchestrator starting up ===")

    # PostgreSQL
    try:
        from database.postgres import init_db
        await init_db()
        logger.info("PostgreSQL: tables ready.")
    except Exception as exc:
        logger.warning("PostgreSQL unavailable at startup: %s -- persistence disabled.", exc)

    # ChromaDB
    try:
        from database.chroma import init_chroma
        init_chroma()
    except Exception as exc:
        logger.warning("ChromaDB unavailable at startup: %s -- memory search disabled.", exc)

    # Phase 5: start background health monitor
    try:
        from orchestrator.node_manager import bootstrap_nodes
        await bootstrap_nodes()
        logger.info("Phase 2.5: Dynamic nodes bootstrapped.")
        
        from orchestrator.monitor import start_monitor
        start_monitor()
        logger.info("Phase 5: node health monitor started.")
    except Exception as exc:
        logger.warning("Health monitor or bootstrap failed: %s", exc)

    yield

    logger.info("=== SIH-2026 Orchestrator shutting down ===")

    # Phase 5: stop monitor
    try:
        from orchestrator.monitor import stop_monitor
        stop_monitor()
    except Exception:
        pass

    try:
        from database.postgres import close_db
        await close_db()
    except Exception:
        pass
    try:
        from database.chroma import close_chroma
        close_chroma()
    except Exception:
        pass


app = FastAPI(
    title=cfg.app_name,
    version=cfg.app_version,
    description=(
        "Distributed AI inference orchestrator for SIH-2026. "
        "Routes requests to specialised LM Studio worker nodes "
        "with PostgreSQL + ChromaDB persistence."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Health routes

@app.get("/health", tags=["Health"], summary="Orchestrator liveness probe")
async def health_check() -> dict:
    """Simple liveness endpoint -- does NOT probe worker nodes or databases."""
    from database.postgres import ping_db
    from database.chroma import ping_chroma

    try:
        pg_ok = await ping_db()
    except Exception:
        pg_ok = False

    try:
        ch_ok = ping_chroma()
    except Exception:
        ch_ok = False

    return {
        "status": "ok",
        "service": cfg.app_name,
        "version": cfg.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "databases": {
            "postgres": "ok" if pg_ok else "unavailable",
            "chroma":   "ok" if ch_ok else "unavailable",
        },
    }


@app.get(
    "/health/cluster",
    tags=["Health"],
    summary="Full cluster health check",
    response_model=ClusterHealthResponse,
)
async def cluster_health() -> ClusterHealthResponse:
    """Probes every registered worker node concurrently."""
    return await get_cluster_health()


# Phase 5 Node status + metrics routes

@app.get(
    "/api/v1/nodes",
    tags=["Phase 5 Monitoring"],
    summary="Node health status and capabilities",
)
async def get_node_statuses() -> dict:
    """
    Returns full node statuses including dynamic DB nodes and multiple models.
    """
    from orchestrator.monitor import get_node_status_entries
    from database.postgres import get_session
    from database.models import WorkerNode
    from sqlalchemy import select
    from orchestrator.scheduler import discover_capabilities

    # Fetch DB nodes to augment status
    db_nodes_map = {}
    async with get_session() as session:
        result = await session.execute(select(WorkerNode))
        for n in result.scalars().all():
            db_nodes_map[n.id] = {
                "name": n.name,
                "endpoint": n.endpoint,
                "enabled": n.enabled,
                "models": [m.model_id for m in n.models]
            }

    entries = get_node_status_entries()
    
    # Fallback to db nodes if monitor hasn't run yet
    if not entries:
        from orchestrator.schemas import NodeStatus, NodeStatusEntry
        for nid, ninfo in db_nodes_map.items():
            if ninfo["enabled"]:
                entries.append(NodeStatusEntry(
                    node_id=nid,
                    status=NodeStatus.ONLINE if ninfo["models"] else NodeStatus.OFFLINE,
                    latency_ms=None
                ))

    # Format the combined response
    formatted_nodes = []
    for e in entries:
        nid = e.node_id
        ninfo = db_nodes_map.get(nid, {})
        models = ninfo.get("models", [])
        
        # Merge monitor models if DB is lacking
        from orchestrator.monitor import _NODE_STATES
        state = _NODE_STATES.get(nid)
        if state and state.models_loaded:
            models = list(set(models + state.models_loaded))
            
        caps = set()
        from orchestrator.node_registry import _REGISTRY, NodeRegistryEntry
        registry_entry = _REGISTRY.get(nid) or NodeRegistryEntry(node_id=nid, endpoint=ninfo.get("endpoint", ""), status="unknown", node_name=ninfo.get("name", ""), capability="", node_type="", model="", supported_input_types=[])
        for m in models:
            caps.update(discover_capabilities(registry_entry, m))
            
        formatted_nodes.append({
            "node_id": nid,
            "name": ninfo.get("name", nid),
            "endpoint": ninfo.get("endpoint", ""),
            "enabled": ninfo.get("enabled", True),
            "status": e.status,
            "latency_ms": e.latency_ms,
            "models": models,
            "capabilities": sorted(list(caps)),
            "last_checked": e.last_checked,
            "last_success": e.last_success
        })
        
    return {"nodes": formatted_nodes}


@app.get(
    "/api/v1/metrics",
    tags=["Phase 5 Monitoring"],
    summary="Aggregate request metrics (rolling window)",
    response_model=MetricsResponse,
)
async def get_metrics() -> MetricsResponse:
    """
    Returns aggregate statistics over the last 1000 requests:
    latency (avg/min/max), success rate, retry count, fallback count.
    """
    from orchestrator.monitor import get_metrics_snapshot
    snap = get_metrics_snapshot()
    return MetricsResponse(**snap)


from pydantic import BaseModel
class AddNodeRequest(BaseModel):
    name: str
    endpoint: str
    priority: int = 1

@app.post(
    "/api/v1/nodes",
    tags=["Phase 2.5 Registry"],
    summary="Add a new dynamic LAN node",
)
async def add_node(req: AddNodeRequest) -> dict:
    from orchestrator.node_manager import _normalize_endpoint, probe_node, sync_registry_from_db
    from database.postgres import get_session
    from database.models import WorkerNode
    from sqlalchemy import select
    import uuid

    norm_endpoint = _normalize_endpoint(req.endpoint)
    if not norm_endpoint.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid endpoint URL")

    async with get_session() as session:
        # Check duplicate
        result = await session.execute(select(WorkerNode).where(WorkerNode.endpoint == norm_endpoint))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Node with this endpoint already exists")

        node_id = f"NODE-{uuid.uuid4().hex[:6].upper()}"
        node = WorkerNode(
            id=node_id,
            name=req.name,
            endpoint=norm_endpoint,
            enabled=True,
            priority=req.priority
        )
        session.add(node)
        await session.commit()
    
    probe_result = await probe_node(node_id)
    return {"message": "Node added successfully", "node_id": node_id, "probe": probe_result}

@app.post(
    "/api/v1/nodes/{node_id}/probe",
    tags=["Phase 2.5 Registry"],
    summary="Manually probe a node and refresh models",
)
async def api_probe_node(node_id: str) -> dict:
    from orchestrator.node_manager import probe_node
    try:
        return await probe_node(node_id.upper())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post(
    "/api/v1/nodes/{node_id}/enable",
    tags=["Phase 2.5 Registry"],
    summary="Enable a disabled node",
)
async def enable_node(node_id: str) -> dict:
    from database.postgres import get_session
    from database.models import WorkerNode
    from orchestrator.node_manager import probe_node
    
    node_id = node_id.upper()
    async with get_session() as session:
        node = await session.get(WorkerNode, node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        node.enabled = True
        await session.commit()
    
    probe_result = await probe_node(node_id)
    return {"message": "Node enabled", "node_id": node_id, "probe": probe_result}

@app.post(
    "/api/v1/nodes/{node_id}/disable",
    tags=["Phase 2.5 Registry"],
    summary="Disable an active node",
)
async def disable_node(node_id: str) -> dict:
    from database.postgres import get_session
    from database.models import WorkerNode
    from orchestrator.node_manager import sync_registry_from_db
    from orchestrator.node_registry import set_node_status
    
    node_id = node_id.upper()
    async with get_session() as session:
        node = await session.get(WorkerNode, node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        node.enabled = False
        await session.commit()
        
    set_node_status(node_id, "offline")
    await sync_registry_from_db()
    return {"message": "Node disabled", "node_id": node_id}

@app.delete(
    "/api/v1/nodes/{node_id}",
    tags=["Phase 2.5 Registry"],
    summary="Soft-delete (disable) a node",
)
async def delete_node(node_id: str) -> dict:
    # Soft delete is just disable for now to preserve history
    return await disable_node(node_id)

@app.get(
    "/api/v1/nodes/{node_id}",
    tags=["Phase 2.5 Registry"],
    summary="Get single dynamic LAN node",
)
async def get_node(node_id: str) -> dict:
    from database.postgres import get_session
    from database.models import WorkerNode
    from orchestrator.monitor import _NODE_STATES
    from orchestrator.scheduler import discover_capabilities
    
    node_id = node_id.upper()
    async with get_session() as session:
        node = await session.get(WorkerNode, node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
            
    models = [m.model_id for m in node.models]
    state = _NODE_STATES.get(node_id)
    if state and state.models_loaded:
        models = list(set(models + state.models_loaded))
        
    caps = set()
    from orchestrator.node_registry import _REGISTRY, NodeRegistryEntry
    registry_entry = _REGISTRY.get(node_id) or NodeRegistryEntry(node_id=node_id, endpoint=node.endpoint, status=node.status, node_name=node.name, capability="", node_type="", model="", supported_input_types=[])
    for m in models:
        caps.update(discover_capabilities(registry_entry, m))
        
    return {
        "node_id": node.id,
        "name": node.name,
        "endpoint": node.endpoint,
        "enabled": node.enabled,
        "status": state.status if state else node.status,
        "latency_ms": state.latency_ms if state else None,
        "models": models,
        "capabilities": sorted(list(caps)),
    }

@app.patch(
    "/api/v1/nodes/{node_id}/status",
    tags=["Registry"],
    summary="Update the runtime status of a node",
)
async def patch_node_status(node_id: str, status: str) -> dict:
    """
    Manually set a node's status to 'online', 'offline', 'unknown', or
    'not_configured'. Useful for testing fallback routing without shutting
    down a physical laptop.

    Example: PATCH /api/v1/nodes/NODE-CODE/status?status=offline
    """
    ok = set_node_status(node_id.upper(), status)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
    return {"node_id": node_id.upper(), "status": status}


# Phase 2/3/5 live inference

@app.post(
    "/api/v1/query",
    tags=["Inference"],
    summary="Send a query to the appropriate AI worker node",
    responses={
        200: {"model": QueryResponse,      "description": "Successful inference"},
        503: {"model": NodeFailureResponse, "description": "Node unavailable or returned an error"},
    },
)
async def query(request: QueryRequest) -> JSONResponse:
    """
    Main inference endpoint.

    Pipeline:
      1. Classify the query (hybrid: rules -> LLM fallback)
      2. Select the best available online node for the required capability
      3. Call the LM Studio node via httpx (with retry up to http_max_retries)
      4. Persist result to PostgreSQL + ChromaDB (fire-and-forget)
      5. Return QueryResponse on success, NodeFailureResponse on node failure
    """
    result = await handle_query(request, timeout=cfg.http_timeout)

    if isinstance(result, NodeFailureResponse):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=result.model_dump(mode="json"),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result.model_dump(mode="json"),
    )


# Phase 4: Semantic Memory Search

@app.post(
    "/api/v1/memory/search",
    tags=["Memory"],
    summary="Search past interactions using natural language",
    response_model=MemorySearchResponse,
)
async def memory_search(request: MemorySearchRequest) -> MemorySearchResponse:
    """
    Semantic search over past interactions for a given user.

    Uses ChromaDB cosine similarity to find the most relevant previous
    queries and responses. Only interactions from ``user_id`` are returned.
    """
    try:
        from database.chroma import search_interactions, ping_chroma
        if not ping_chroma():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ChromaDB semantic memory is currently unavailable.",
            )

        raw = search_interactions(
            user_id=request.user_id,
            query=request.query,
            n_results=request.n_results,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("memory_search error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory search failed: {exc}",
        )

    results = [MemorySearchResult(**r) for r in raw]
    return MemorySearchResponse(
        user_id=request.user_id,
        query=request.query,
        total=len(results),
        results=results,
    )


# Phase 1 stub (kept for backward compatibility)

@app.post(
    "/infer",
    tags=["Inference (Phase 1 stub)"],
    summary="[DEPRECATED] Phase 1 routing stub -- use /api/v1/query instead",
    response_model=InferenceResponse,
    deprecated=True,
)
async def infer(request: InferenceRequest) -> InferenceResponse:
    """Retained for backward compatibility. Prefer POST /api/v1/query."""
    from orchestrator.classifier import classify_sync
    from orchestrator.schemas import InputType
    from orchestrator.node_registry import get_node_by_type

    classification = classify_sync(request.prompt, InputType.TEXT)
    node = get_node_by_type(classification.node_type)
    node_url = node.endpoint if node else ""

    return InferenceResponse(
        request_id=uuid.uuid4(),
        session_id=request.session_id,
        node_type=classification.node_type,
        node_url=node_url,
        response="[Phase 1 stub] Use POST /api/v1/query for live inference.",
        latency_ms=0.0,
    )


if __name__ == "__main__":
    uvicorn.run(
        "orchestrator.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
        log_level="info",
    )
