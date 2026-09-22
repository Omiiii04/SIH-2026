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


class InputType(str, Enum):
    """
    What kind of input the user is sending.
    The classifier maps this (+ query keywords) → NodeType.
    """
    TEXT = "text"
    IMAGE = "image"
    CODE = "code"
    REASONING = "reasoning"
    RETRIEVAL = "retrieval"


class TaskType(str, Enum):
    """Fine-grained task category returned by the Phase 3 classifier."""
    GENERAL_QA            = "general_qa"
    SUMMARIZATION         = "summarization"
    CREATIVE_WRITING      = "creative_writing"
    CODING                = "coding"
    CODE_DEBUG            = "code_debug"
    CODE_REVIEW           = "code_review"
    VISUAL_QA             = "visual_question_answering"
    OCR                   = "ocr"
    REASONING             = "reasoning"
    MATH                  = "math"
    LOGICAL_INFERENCE     = "logical_inference"
    DOCUMENT_RETRIEVAL    = "document_retrieval"
    SEMANTIC_SEARCH       = "semantic_search"
    EMBEDDING             = "embedding"
    CLASSIFICATION        = "classification"
    UNKNOWN               = "unknown"


class Difficulty(str, Enum):
    """Estimated difficulty of the task."""
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class RequestStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class NodeStatus(str, Enum):
    """Phase 5 three-state node health classification."""
    ONLINE   = "ONLINE"
    DEGRADED = "DEGRADED"   # reachable but high latency
    OFFLINE  = "OFFLINE"


class ClassifierMethod(str, Enum):
    """Which classification path was taken."""
    RULE_EXPLICIT   = "rule:explicit_input_type"
    RULE_KEYWORD    = "rule:keyword_match"
    RULE_DEFAULT    = "rule:default_fallback"
    LLM             = "llm:structured_output"
    LLM_FALLBACK    = "llm:fallback_on_rule_failure"


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


# ── Phase 2: /api/v1/query ─────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """Request body for POST /api/v1/query."""

    user_id: str = Field(..., min_length=1, description="Caller identifier.")
    query: str = Field(..., min_length=1, description="The user's question or instruction.")
    input_type: InputType = Field(
        default=InputType.TEXT,
        description="Hint about the nature of the input (text / image / code / reasoning / retrieval).",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for multi-turn conversations.",
    )
    parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Model-specific overrides (temperature, max_tokens, etc.).",
    )


class ClassificationResult(BaseModel):
    """Output of the Phase 3 hybrid classifier."""

    # Core fields (Phase 2 compatible)
    input_type: InputType
    node_type: NodeType
    matched_rule: Optional[str] = None          # which rule / keyword fired

    # Phase 3 additions
    task_type: TaskType = TaskType.UNKNOWN
    difficulty: Difficulty = Difficulty.MEDIUM
    required_capability: str = "text"           # matches NodeRegistryEntry.capability
    confidence: float = 1.0                     # 0.0–1.0
    classifier_method: ClassifierMethod = ClassifierMethod.RULE_DEFAULT


class RoutingDecision(BaseModel):
    """Explains why a specific node was chosen."""
    selected_node: str
    reason: str
    was_fallback: bool = False    # True when the primary node was offline


class QueryResponse(BaseModel):
    """Response envelope for POST /api/v1/query."""

    request_id: str
    user_id: str
    session_id: Optional[str] = None
    input_type: InputType
    classification: ClassificationResult
    routing: RoutingDecision
    selected_node: str          # node_id  e.g. "NODE-TEXT"  (mirrors routing.selected_node)
    selected_model: str
    response: str
    total_ms: float
    classification_ms: float
    routing_ms: float
    inference_ms: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NodeFailureResponse(BaseModel):
    """Returned when the selected node is unavailable or returns an error."""

    request_id: str
    user_id: str
    selected_node: str
    error_type: str             # "connection_error" | "timeout" | "http_error" | "node_not_configured"
    detail: str
    total_ms: float
    classification_ms: float
    routing_ms: float
    inference_ms: float
    routing: Optional[RoutingDecision] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Phase 2: Node Registry ─────────────────────────────────────────────────────

class NodeRegistryEntry(BaseModel):
    """Full descriptor for one worker node as exposed by the registry API."""

    node_id: str
    node_name: str
    capability: str
    node_type: NodeType
    model: str
    endpoint: str
    status: str                 # "online" | "offline" | "not_configured"
    supported_input_types: List[str]
    priority: int               # lower = higher priority (1 = primary)


# ── Phase 4: Semantic Memory ───────────────────────────────────────────────────

class MemorySearchRequest(BaseModel):
    """Request body for POST /api/v1/memory/search."""

    user_id:   str = Field(..., min_length=1, description="Caller identifier.")
    query:     str = Field(..., min_length=1, description="Natural-language search query.")
    n_results: int = Field(default=5, ge=1, le=20, description="Max results to return.")


class MemorySearchResult(BaseModel):
    """One past interaction returned by the semantic memory search."""

    request_id: str
    query:      str
    response:   str
    node_id:    str
    model:      str
    timestamp:  str
    session_id: str = ""
    score:      float = Field(description="Cosine similarity score (0–1, higher = more relevant).")


class MemorySearchResponse(BaseModel):
    """Response envelope for POST /api/v1/memory/search."""

    user_id:  str
    query:    str
    total:    int
    results:  List[MemorySearchResult]


# ── Phase 5: Node Status + Metrics ────────────────────────────────────────────

class NodeStatusEntry(BaseModel):
    """Phase 5 node status entry for GET /api/v1/nodes."""
    node_id:          str
    status:           NodeStatus
    latency_ms:       Optional[float] = None
    model_loaded:     Optional[str]   = None
    capacity:         Optional[str]   = None
    last_checked:     Optional[datetime] = None
    last_success:     Optional[datetime] = None


class NodeStatusResponse(BaseModel):
    """Response for GET /api/v1/nodes."""
    nodes: List[NodeStatusEntry]


class MetricsResponse(BaseModel):
    """Response for GET /api/v1/metrics."""
    total_requests:     int
    successful:         int
    failed:             int
    success_rate:       float           # 0.0–1.0
    avg_latency_ms:     Optional[float] = None
    min_latency_ms:     Optional[float] = None
    max_latency_ms:     Optional[float] = None
    avg_routing_ms:     Optional[float] = None
    avg_inference_ms:   Optional[float] = None
    total_retries:      int = 0
    fallback_count:     int = 0
    window_size:        int             # how many requests are in the rolling window

