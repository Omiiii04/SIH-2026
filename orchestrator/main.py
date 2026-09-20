"""
SIH-2026 Orchestrator — FastAPI Application Entry Point.

Routes
------
  GET  /health                    → orchestrator liveness probe
  GET  /health/cluster            → probes all worker nodes
  GET  /api/v1/nodes              → lists the node registry
  PATCH /api/v1/nodes/{id}/status → runtime node status override
  POST /api/v1/query              → Phase 2/3 live inference pipeline
  POST /api/v1/memory/search      → Phase 4 semantic memory search
  POST /infer                     → Phase 1 stub (deprecated)
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
    NodeFailureResponse,
    NodeRegistryEntry,
    NodeType,
    QueryRequest,
    QueryResponse,
    RoutingDecision,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Settings ───────────────────────────────────────────────────────────────────
cfg = get_settings()


# ── Lifespan (startup / shutdown) ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise databases on startup, dispose them on shutdown."""

    # ── Startup ────────────────────────────────────────────────────────────────
    logger.info("=== SIH-2026 Orchestrator starting up ===")

    # PostgreSQL
    try:
        from database.postgres import init_db
        await init_db()
        logger.info("PostgreSQL: tables ready.")
    except Exception as exc:
        logger.warning("PostgreSQL unavailable at startup: %s — persistence disabled.", exc)

    # ChromaDB
    try:
        from database.chroma import init_chroma
        init_chroma()
    except Exception as exc:
        logger.warning("ChromaDB unavailable at startup: %s — memory search disabled.", exc)

    yield  # ── Application running ───────────────────────────────────────────

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("=== SIH-2026 Orchestrator shutting down ===")
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


# ── App ────────────────────────────────────────────────────────────────────────
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
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health routes ──────────────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Health"],
    summary="Orchestrator liveness probe",
)
async def health_check() -> dict:
    """Simple liveness endpoint — does NOT probe worker nodes or databases."""
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


# ── Node registry routes ───────────────────────────────────────────────────────

@app.get(
    "/api/v1/nodes",
    tags=["Registry"],
    summary="List all registered worker nodes",
    response_model=List[NodeRegistryEntry],
)
async def get_nodes() -> List[NodeRegistryEntry]:
    """Returns the node registry with current status for each node."""
    return list_nodes()


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


# ── Phase 2/3: live inference ──────────────────────────────────────────────────

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
      1. Classify the query (hybrid: rules → LLM fallback)
      2. Select the best available online node for the required capability
      3. Call the LM Studio node via httpx
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


# ── Phase 4: Semantic Memory Search ───────────────────────────────────────────

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

    Example::

        POST /api/v1/memory/search
        {
          "user_id": "user_001",
          "query": "What did I ask about distributed AI?",
          "n_results": 5
        }
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


# ── Phase 1 stub (kept for backward compatibility) ─────────────────────────────

@app.post(
    "/infer",
    tags=["Inference (Phase 1 stub)"],
    summary="[DEPRECATED] Phase 1 routing stub — use /api/v1/query instead",
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


# ── Dev server entry-point ─────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "orchestrator.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
        log_level="info",
    )
