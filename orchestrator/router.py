"""
orchestrator/router.py
──────────────────────
Phase 3 Intelligent Router — pure pipeline, zero FastAPI imports.

Pipeline
────────
  QueryRequest
      ↓
  classify(query, input_type)            →  ClassificationResult
      ↓
  get_online_node_for_capability(cap)    →  NodeRegistryEntry  (or fallback)
      ↓
  build_routing_decision(node, cls)      →  RoutingDecision
      ↓
  call_node(endpoint, model, …)          →  LMResponse  (or LMClientError)
      ↓
  QueryResponse | NodeFailureResponse

Key Phase 3 additions:
  * Uses required_capability (not raw NodeType) for node selection
  * Consults capability fallback order when preferred node is offline
  * Attaches a RoutingDecision with human-readable reason + was_fallback flag
  * Never selects a node whose status == "offline" | "not_configured"
"""

from __future__ import annotations

import logging
import uuid
from typing import Union

from orchestrator.classifier import classify
from orchestrator.lm_client import LMClientError, LMResponse, call_node
from orchestrator.node_registry import (
    get_node_by_type,
    get_online_node_for_capability,
    set_node_status,
)
from orchestrator.schemas import (
    ClassificationResult,
    Difficulty,
    NodeFailureResponse,
    NodeType,
    QueryRequest,
    QueryResponse,
    RoutingDecision,
    TaskType,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Routing reason generator
# ─────────────────────────────────────────────────────────────────────────────

_TASK_REASON: dict[TaskType, str] = {
    TaskType.CODING:              "The request requires code generation.",
    TaskType.CODE_DEBUG:          "The request requires debugging and fixing code.",
    TaskType.CODE_REVIEW:         "The request requires code review and refactoring.",
    TaskType.VISUAL_QA:           "The request requires visual understanding of an image.",
    TaskType.OCR:                 "The request requires OCR / text extraction from an image.",
    TaskType.REASONING:           "The request requires multi-step analytical reasoning.",
    TaskType.MATH:                "The request requires mathematical computation or proof.",
    TaskType.LOGICAL_INFERENCE:   "The request requires formal logical inference.",
    TaskType.DOCUMENT_RETRIEVAL:  "The request requires document retrieval from a knowledge base.",
    TaskType.SEMANTIC_SEARCH:     "The request requires semantic / vector similarity search.",
    TaskType.EMBEDDING:           "The request requires embedding generation.",
    TaskType.SUMMARIZATION:       "The request requires text summarisation.",
    TaskType.CREATIVE_WRITING:    "The request is a creative writing task.",
    TaskType.GENERAL_QA:          "The request is a general knowledge question.",
    TaskType.CLASSIFICATION:      "The request is a classification task.",
    TaskType.UNKNOWN:             "The task type could not be determined; routing to the general text node.",
}

_DIFFICULTY_QUALIFIER: dict[Difficulty, str] = {
    Difficulty.LOW:    " This is a straightforward query.",
    Difficulty.MEDIUM: "",
    Difficulty.HIGH:   " This is a complex, high-difficulty query.",
}


def _build_routing_reason(
    cls: ClassificationResult,
    node_id: str,
    preferred_node_id: str,
    was_fallback: bool,
) -> str:
    base = _TASK_REASON.get(cls.task_type, "Routing to the best available node.")
    qualifier = _DIFFICULTY_QUALIFIER.get(cls.difficulty, "")
    method_note = (
        f" (classified by {cls.classifier_method.value}, confidence={cls.confidence:.0%})"
    )
    if was_fallback:
        fallback_note = (
            f" Primary node {preferred_node_id} is offline; "
            f"falling back to {node_id}."
        )
        return base + qualifier + method_note + fallback_note
    return base + qualifier + method_note


def _build_routing_decision(
    cls: ClassificationResult,
    node_id: str,
    preferred_node_id: str,
) -> RoutingDecision:
    was_fallback = node_id != preferred_node_id
    return RoutingDecision(
        selected_node=node_id,
        reason=_build_routing_reason(cls, node_id, preferred_node_id, was_fallback),
        was_fallback=was_fallback,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def handle_query(
    request: QueryRequest,
    timeout: float = 30.0,
) -> Union[QueryResponse, NodeFailureResponse]:
    """
    Full Phase 3 request pipeline.

    Returns
    -------
    QueryResponse       on successful inference.
    NodeFailureResponse when no suitable node is available or inference fails.
    """
    request_id = str(uuid.uuid4())
    logger.info(
        "[%s] user=%s  input_type=%s  query_len=%d",
        request_id, request.user_id, request.input_type, len(request.query),
    )

    # ── Step 1: Hybrid classification ─────────────────────────────────────────
    cls: ClassificationResult = await classify(request.query, request.input_type)
    logger.info(
        "[%s] Classified → task=%s  capability=%s  difficulty=%s  confidence=%.2f  method=%s",
        request_id, cls.task_type, cls.required_capability,
        cls.difficulty, cls.confidence, cls.classifier_method,
    )

    # ── Step 2: Node selection (capability-based, offline-aware) ──────────────
    # Determine the "ideal" node (ignoring online status) for the reason string
    ideal_node = get_node_by_type(cls.node_type)
    preferred_node_id = ideal_node.node_id if ideal_node else f"NODE-{cls.node_type.value.upper()}"

    # Get the best available online node for the required capability
    node = get_online_node_for_capability(cls.required_capability)

    if node is None:
        reason = (
            f"No online node available for capability '{cls.required_capability}'. "
            f"All candidate nodes are offline or not configured."
        )
        routing = RoutingDecision(
            selected_node=preferred_node_id,
            reason=reason,
            was_fallback=False,
        )
        logger.warning("[%s] No online node for capability=%s", request_id, cls.required_capability)
        return NodeFailureResponse(
            request_id=request_id,
            user_id=request.user_id,
            selected_node=preferred_node_id,
            error_type="no_available_node",
            detail=reason,
            latency_ms=0.0,
            routing=routing,
        )

    routing = _build_routing_decision(cls, node.node_id, preferred_node_id)
    logger.info(
        "[%s] Selected node=%s  fallback=%s  endpoint=%s",
        request_id, node.node_id, routing.was_fallback, node.endpoint,
    )

    # ── Step 3: Call LM Studio ────────────────────────────────────────────────
    try:
        lm_resp: LMResponse = await call_node(
            endpoint=node.endpoint,
            model=node.model,
            query=request.query,
            parameters=request.parameters,
            timeout=timeout,
        )
    except LMClientError as exc:
        logger.warning(
            "[%s] Node failure: node=%s  type=%s  detail=%s",
            request_id, node.node_id, exc.error_type, exc.detail,
        )
        # Mark node as offline in registry so subsequent requests use a different node
        if exc.error_type in ("connection_error", "timeout"):
            set_node_status(node.node_id, "offline")
            logger.info("[%s] Marked %s as offline in registry", request_id, node.node_id)

        return NodeFailureResponse(
            request_id=request_id,
            user_id=request.user_id,
            selected_node=node.node_id,
            error_type=exc.error_type,
            detail=exc.detail,
            latency_ms=exc.latency_ms,
            routing=routing,
        )

    # ── Step 4: Build response ────────────────────────────────────────────────
    logger.info(
        "[%s] Success  node=%s  latency=%.1f ms  tokens=%s",
        request_id, node.node_id, lm_resp.latency_ms, lm_resp.tokens_total,
    )

    return QueryResponse(
        request_id=request_id,
        user_id=request.user_id,
        session_id=request.session_id,
        input_type=request.input_type,
        classification=cls,
        routing=routing,
        selected_node=node.node_id,
        selected_model=lm_resp.model,
        response=lm_resp.content,
        latency_ms=lm_resp.latency_ms,
    )
