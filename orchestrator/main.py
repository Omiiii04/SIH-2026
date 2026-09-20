"""
SIH-2026 Orchestrator — FastAPI Application Entry Point.

Routes
------
  GET  /health             → orchestrator liveness probe
  GET  /health/cluster     → probes all worker nodes
  GET  /api/v1/nodes       → lists the node registry
  POST /api/v1/query       → Phase 2 live inference pipeline
  POST /infer              → Phase 1 stub (kept for backward compatibility)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Union
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from orchestrator.config import get_settings
from orchestrator.health import get_cluster_health
from orchestrator.node_registry import list_nodes
from orchestrator.router import handle_query
from orchestrator.schemas import (
    ClusterHealthResponse,
    ErrorResponse,
    InferenceRequest,
    InferenceResponse,
    NodeFailureResponse,
    NodeRegistryEntry,
    NodeType,
    QueryRequest,
    QueryResponse,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
cfg = get_settings()

app = FastAPI(
    title=cfg.app_name,
    version=cfg.app_version,
    description=(
        "Distributed AI inference orchestrator for SIH-2026. "
        "Routes requests to specialised LM Studio worker nodes."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
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
    """Simple liveness endpoint — does NOT probe worker nodes."""
    return {
        "status": "ok",
        "service": cfg.app_name,
        "version": cfg.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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


# ── Node registry route ────────────────────────────────────────────────────────

@app.get(
    "/api/v1/nodes",
    tags=["Registry"],
    summary="List all registered worker nodes",
    response_model=List[NodeRegistryEntry],
)
async def get_nodes() -> List[NodeRegistryEntry]:
    """
    Returns the static node registry.
    Each entry shows node_id, capability, endpoint, model, supported_input_types,
    priority, and current status.
    """
    return list_nodes()


# ── Phase 2: live inference ────────────────────────────────────────────────────

@app.post(
    "/api/v1/query",
    tags=["Inference"],
    summary="Send a query to the appropriate AI worker node",
    responses={
        200: {"model": QueryResponse, "description": "Successful inference"},
        503: {"model": NodeFailureResponse, "description": "Node unavailable or returned an error"},
    },
)
async def query(request: QueryRequest) -> JSONResponse:
    """
    Main Phase 2 inference endpoint.

    Pipeline:
      1. Classify the query (input_type + keyword rules) → NodeType
      2. Look up the node in the registry
      3. Call the LM Studio node via httpx
      4. Return QueryResponse on success, NodeFailureResponse on node failure
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
    from orchestrator.classifier import classify
    from orchestrator.schemas import InputType
    from orchestrator.node_registry import get_node_by_type

    classification = classify(request.prompt, InputType.TEXT)
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
