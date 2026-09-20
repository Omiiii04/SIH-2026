"""
SIH-2026 Orchestrator — FastAPI Application Entry Point.

Exposes:
  GET  /health          → lightweight liveness probe (no DB, no node calls)
  GET  /health/cluster  → full cluster health (pings each worker node)
  POST /infer           → route an inference request to the correct worker node

Phase 1: routing logic and health structure are wired up.
         Actual node HTTP calls are deferred to Phase 2.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.config import get_settings
from orchestrator.health import get_cluster_health
from orchestrator.router import route_request
from orchestrator.schemas import (
    ClusterHealthResponse,
    ErrorResponse,
    InferenceRequest,
    InferenceResponse,
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


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Health"],
    summary="Orchestrator liveness probe",
    response_description="Returns HTTP 200 when the orchestrator process is running.",
)
async def health_check() -> dict:
    """
    Simple liveness endpoint — does **not** probe worker nodes.
    Used by load-balancers and CI checks to verify the process is up.
    """
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
    """
    Probes every registered worker node and returns their health status.
    This call performs real network I/O to each node's LM Studio endpoint.
    """
    return await get_cluster_health()


@app.post(
    "/infer",
    tags=["Inference"],
    summary="Route an inference request to the appropriate worker node",
    response_model=InferenceResponse,
    status_code=status.HTTP_200_OK,
    responses={503: {"model": ErrorResponse}},
)
async def infer(request: InferenceRequest) -> InferenceResponse:
    """
    Phase 1 stub:
    - Determines the target NodeType via the router.
    - Returns a placeholder response (no live node call yet).

    Phase 2 will replace the stub with an actual httpx call to the worker.
    """
    node_type = route_request(request)
    cfg_local = get_settings()

    node_url_map = {
        "text": cfg_local.node_text_url,
        "vision": cfg_local.node_vision_url,
        "reasoning": cfg_local.node_reasoning_url,
        "code": cfg_local.node_code_url,
        "rag": cfg_local.node_rag_url,
    }
    node_url = node_url_map[node_type.value]

    logger.info("Routing request to node_type=%s url=%s", node_type, node_url)

    # ── Phase 2 TODO: replace stub with real httpx call ──────────────────────
    stub_response = (
        f"[Phase 1 stub] Request routed to '{node_type.value}' node at {node_url}. "
        "Live inference will be enabled in Phase 2."
    )

    return InferenceResponse(
        request_id=uuid.uuid4(),
        session_id=request.session_id,
        node_type=node_type,
        node_url=node_url,
        response=stub_response,
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
