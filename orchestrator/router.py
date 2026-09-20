"""
orchestrator/router.py
──────────────────────
Phase 2 Node Router — pure routing logic, completely decoupled from FastAPI.

Pipeline
--------
  QueryRequest
      ↓
  classify(query, input_type)     →  ClassificationResult
      ↓
  get_node_by_type(node_type)     →  NodeRegistryEntry
      ↓
  call_node(endpoint, model, …)   →  LMResponse  (or LMClientError)

This module contains ZERO FastAPI imports; it can be tested standalone.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Union

from orchestrator.classifier import classify
from orchestrator.lm_client import LMClientError, LMResponse, call_node
from orchestrator.node_registry import get_node_by_type
from orchestrator.schemas import (
    ClassificationResult,
    NodeFailureResponse,
    QueryRequest,
    QueryResponse,
)

logger = logging.getLogger(__name__)


async def handle_query(
    request: QueryRequest,
    timeout: float = 30.0,
) -> Union[QueryResponse, NodeFailureResponse]:
    """
    Full request pipeline: classify → select node → call node → return result.

    Returns
    -------
    QueryResponse   on success.
    NodeFailureResponse   when the node is unreachable or returns an error.
    """
    request_id = str(uuid.uuid4())
    logger.info(
        "[%s] user=%s  input_type=%s  query_len=%d",
        request_id, request.user_id, request.input_type, len(request.query),
    )

    # ── Step 1: Classify ──────────────────────────────────────────────────────
    classification: ClassificationResult = classify(request.query, request.input_type)
    logger.info(
        "[%s] Classification → node_type=%s  rule=%s",
        request_id, classification.node_type, classification.matched_rule,
    )

    # ── Step 2: Select node ───────────────────────────────────────────────────
    node = get_node_by_type(classification.node_type)
    if node is None:
        return NodeFailureResponse(
            request_id=request_id,
            user_id=request.user_id,
            selected_node=f"NODE-{classification.node_type.value.upper()}",
            error_type="registry_error",
            detail=f"No node registered for type '{classification.node_type}'.",
            latency_ms=0.0,
        )

    logger.info("[%s] Selected node=%s  endpoint=%s", request_id, node.node_id, node.endpoint)

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
        return NodeFailureResponse(
            request_id=request_id,
            user_id=request.user_id,
            selected_node=node.node_id,
            error_type=exc.error_type,
            detail=exc.detail,
            latency_ms=exc.latency_ms,
        )

    # ── Step 4: Build response ────────────────────────────────────────────────
    logger.info(
        "[%s] Success  node=%s  latency=%.1f ms",
        request_id, node.node_id, lm_resp.latency_ms,
    )

    return QueryResponse(
        request_id=request_id,
        user_id=request.user_id,
        session_id=request.session_id,
        input_type=request.input_type,
        classification=classification,
        selected_node=node.node_id,
        selected_model=lm_resp.model,
        response=lm_resp.content,
        latency_ms=lm_resp.latency_ms,
    )
