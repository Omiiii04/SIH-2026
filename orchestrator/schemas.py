"""
Pydantic schemas (request / response DTOs) for the SIH-2026 Orchestrator API.

These are intentionally separate from the SQLAlchemy ORM models so that
API surface and DB layer can evolve independently.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


# ── Enums ──────────────────────────────────────────────────────────────────────

class NodeType(str, Enum):
    """The five specialised AI worker node types."""
    TEXT = "text"
    VISION = "vision"
    REASONING = "reasoning"
    CODE = "code"
    RAG = "rag"


class RequestStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


# ── Inference Request / Response ───────────────────────────────────────────────

class InferenceRequest(BaseModel):
    """Payload sent by the client to the orchestrator."""

    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for multi-turn conversations.",
    )
    node_type: Optional[NodeType] = Field(
        default=None,
        description="Explicit node type override. If omitted, the router decides.",
    )
    prompt: str = Field(..., min_length=1, description="The user prompt.")
    context: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional prior conversation turns for context injection.",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Model-specific parameters (temperature, max_tokens, etc.).",
    )


class InferenceResponse(BaseModel):
    """Response returned to the client after a successful inference."""

    request_id: UUID
    session_id: Optional[str]
    node_type: NodeType
    node_url: str
    response: str
    latency_ms: float
    tokens_used: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Node Health ────────────────────────────────────────────────────────────────

class NodeHealthSchema(BaseModel):
    """Current health status of a single worker node."""

    node_type: NodeType
    node_url: str
    is_online: bool
    latency_ms: Optional[float] = None
    model_loaded: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClusterHealthResponse(BaseModel):
    """Aggregated health of all worker nodes."""

    orchestrator_status: str = "ok"
    nodes: List[NodeHealthSchema]
    healthy_count: int
    total_count: int
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Error ──────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standardised error envelope."""

    detail: str
    code: Optional[str] = None
