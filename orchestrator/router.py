"""
orchestrator/router.py
Phase 5 Intelligent Router - retry loop, fault tolerance, metrics.

Pipeline:
  QueryRequest -> classify -> get_online_node_for_capability -> call_node -> [retry] -> Response

Phase 5 additions:
  * Retry loop capped at cfg.http_max_retries (prevents infinite loops)
  * Dead nodes marked OFFLINE immediately; next retry picks different node
  * Per-request metrics: routing_ms, inference_ms, total_ms, retry_count, fallback, final_node
"""

from __future__ import annotations

import asyncio
import logging
import time
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
    method = cls.classifier_method.value
    rule = cls.matched_rule or "unknown"
    reason = f"Routed by {method} (rule: {rule})."
    
    if was_fallback:
        reason += f" Primary node {preferred_node_id} is offline; falling back to {node_id}."
        
    return reason


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


async def handle_query(
    request: QueryRequest,
    timeout: float = 30.0,
) -> Union[QueryResponse, NodeFailureResponse]:
    """
    Phase 5 pipeline: classify -> retry loop -> metrics.

    Retries up to cfg.http_max_retries times across available nodes.
    Dead nodes are marked offline so the next retry picks a different one.
    Records routing_ms, inference_ms, total_ms, retry_count, fallback, status.

    Vision requests use a shorter per-node timeout (15 s) so that a text model
    accidentally receiving an image query fails fast and the fallback chain
    (TEXT / REASONING) is reached quickly.
    """
    from orchestrator.config import get_settings
    from orchestrator.monitor import RequestRecord, record_request

    cfg = get_settings()
    MAX_RETRIES: int = max(1, cfg.http_max_retries)

    request_id = str(uuid.uuid4())
    t_start = time.monotonic()

    logger.info(
        "[%s] user=%s  input_type=%s  query_len=%d",
        request_id, request.user_id, request.input_type, len(request.query),
    )

    # Step 1: classify
    t_class_start = time.monotonic()
    cls: ClassificationResult = await classify(request.query, request.input_type, request_id=request_id)
    classification_ms = (time.monotonic() - t_class_start) * 1000

    logger.info(
        "[%s] Classified -> task=%s  capability=%s  difficulty=%s  confidence=%.2f  method=%s",
        request_id, cls.task_type, cls.required_capability,
        cls.difficulty, cls.confidence, cls.classifier_method,
    )

    ideal_node = get_node_by_type(cls.node_type)
    if ideal_node:
        preferred_node_id = ideal_node.node_id
    else:
        # Fallback to the new IDs if registry somehow didn't return ideal_node
        fallback_map = {
            NodeType.TEXT: "NODE-1",
            NodeType.VISION: "NODE-2",
            NodeType.REASONING: "NODE-3",
            NodeType.CODE: "NODE-4",
            NodeType.RAG: "NODE-5",
        }
        preferred_node_id = fallback_map.get(cls.node_type, "NODE-1")

    # Step 2: retry loop
    tried_nodes: set[str] = set()
    last_exc: LMClientError | None = None
    last_node_id: str = preferred_node_id
    routing: RoutingDecision | None = None

    from orchestrator.scheduler import select_best_candidates

    for attempt in range(MAX_RETRIES):
        candidates = select_best_candidates(cls, skip_ids=tried_nodes)

        # No more fresh nodes (all tried or all offline)
        if not candidates:
            logger.warning(
                "[%s] No fresh online candidates for capability=%s (attempt %d)",
                request_id, cls.required_capability, attempt + 1,
            )
            break

        node, model_name, score, scheduler_reason = candidates[0]
        tried_nodes.add(node.node_id)
        last_node_id = node.node_id
        
        routing = _build_routing_decision(cls, node.node_id, preferred_node_id)
        routing.reason += f" | Scheduler: {scheduler_reason}"

        logger.info(
            "[%s] Attempt %d/%d  node=%s  fallback=%s  score=%.1f",
            request_id, attempt + 1, MAX_RETRIES, node.node_id, routing.was_fallback, score,
        )

        t_call_start = time.monotonic()
        # node.model is populated by the health monitor from GET /v1/models.
        # If it's still empty (node came online between probes), pass "" —
        # LM Studio will use whichever model it currently has loaded.
        # Use a shorter per-node timeout for vision capability:
        # NODE-2 runs a text model that hangs forever on image payloads.
        # 15s is enough for a real vision model; text fallback gets the full timeout.
        node_timeout = 15.0 if (
            cls.required_capability == "vision" and node.node_type == NodeType.VISION
        ) else timeout

        try:
            lm_resp: LMResponse = await call_node(
                endpoint=node.endpoint,
                model=model_name,   # live model id selected by scheduler
                query=request.query,
                parameters=request.parameters,
                timeout=node_timeout,
                request_id=request_id,
                attempt=attempt + 1,
                node_id=node.node_id,
            )
        except LMClientError as exc:
            last_exc = exc
            logger.warning(
                "[%s] Node failure: node=%s  type=%s  detail=%s (attempt %d/%d)",
                request_id, node.node_id, exc.error_type, exc.detail, attempt + 1, MAX_RETRIES,
            )
            if exc.error_type in ("connection_error", "timeout"):
                set_node_status(node.node_id, "offline")
                logger.info("[%s] Marked %s offline.", request_id, node.node_id)
            continue

        # Success
        inference_ms = (time.monotonic() - t_call_start) * 1000
        total_ms     = (time.monotonic() - t_start) * 1000
        routing_ms   = total_ms - inference_ms - classification_ms

        logger.info(
            "[%s] Success  node=%s  latency=%.1f ms  tokens=%s",
            request_id, node.node_id, lm_resp.latency_ms, lm_resp.tokens_total,
        )

        response = QueryResponse(
            request_id=request_id,
            user_id=request.user_id,
            session_id=request.session_id,
            input_type=request.input_type,
            classification=cls,
            routing=routing,
            selected_node=node.node_id,
            selected_model=lm_resp.model,
            response=lm_resp.content,
            total_ms=round(total_ms, 1),
            classification_ms=round(classification_ms, 1),
            routing_ms=round(routing_ms, 1),
            inference_ms=round(inference_ms, 1),
        )

        record_request(RequestRecord(
            success=True,
            total_ms=round(total_ms, 1),
            routing_ms=round(routing_ms, 1),
            inference_ms=round(inference_ms, 1),
            retry_count=attempt,
            was_fallback=routing.was_fallback,
            final_node=node.node_id,
            status="success",
        ))

        try:
            from orchestrator.persistence import persist_success
            asyncio.create_task(persist_success(response, request))
        except Exception as _e:
            logger.debug("[%s] persist_success task creation failed: %s", request_id, _e)

        return response

    # All retries exhausted
    total_ms = (time.monotonic() - t_start) * 1000
    exc_lat = last_exc.latency_ms if last_exc else 0.0
    routing_ms = total_ms - exc_lat - classification_ms
    if routing is None:
        routing = RoutingDecision(
            selected_node=preferred_node_id,
            reason=f"No online node available for capability '{cls.required_capability}'.",
            was_fallback=False,
        )

    exc_type   = last_exc.error_type if last_exc else "no_available_node"
    exc_detail = last_exc.detail     if last_exc else (
        f"No online node available for capability '{cls.required_capability}'."
    )
    exc_lat    = last_exc.latency_ms if last_exc else 0.0

    failure_response = NodeFailureResponse(
        request_id=request_id,
        user_id=request.user_id,
        selected_node=last_node_id,
        error_type=exc_type,
        detail=exc_detail,
        total_ms=round(total_ms, 1),
        classification_ms=round(classification_ms, 1),
        routing_ms=round(routing_ms, 1),
        inference_ms=round(exc_lat, 1),
        routing=routing,
    )

    record_request(RequestRecord(
        success=False,
        total_ms=round(total_ms, 1),
        routing_ms=round(routing_ms, 1),
        inference_ms=0.0,
        retry_count=len(tried_nodes),
        was_fallback=routing.was_fallback,
        final_node=last_node_id,
        status=exc_type,
    ))

    try:
        from orchestrator.persistence import persist_failure
        asyncio.create_task(persist_failure(failure_response, request))
    except Exception as _e:
        logger.debug("[%s] persist_failure task creation failed: %s", request_id, _e)

    return failure_response
