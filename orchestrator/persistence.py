"""
orchestrator/persistence.py
───────────────────────────
Phase 4 — High-level write helper that bridges the routing pipeline with
the PostgreSQL + ChromaDB storage layer.

Design Goals
────────────
  • Fire-and-forget: called via ``asyncio.create_task()`` from the router so
    database latency never adds to the user-facing response time.
  • Fault-tolerant: all exceptions are caught and logged; the query response
    is NEVER blocked or corrupted by a DB error.
  • Idempotent: upserts the users row before inserting requests.
  • Both stores written in a single call so callsites stay simple.

Public API
──────────
  persist_success(response, request) → None   (for QueryResponse)
  persist_failure(response, request) → None   (for NodeFailureResponse)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from orchestrator.schemas import (
    NodeFailureResponse,
    QueryRequest,
    QueryResponse,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal PostgreSQL writer
# ─────────────────────────────────────────────────────────────────────────────

async def _write_postgres_success(
    response: QueryResponse,
    request:  QueryRequest,
) -> None:
    """Insert users / requests / routing_decisions rows for a successful query."""
    from database.postgres import get_session, upsert_user
    from orchestrator.models import Request, RoutingDecision

    request_uuid = uuid.UUID(response.request_id)

    async with get_session() as session:
        # 1. Ensure user exists
        await upsert_user(session, response.user_id)

        # 2. Insert request row
        cls = response.classification
        req_row = Request(
            id             = request_uuid,
            user_id        = response.user_id,
            session_id     = response.session_id,
            query          = request.query,
            input_type     = response.input_type.value,
            task_type      = cls.task_type.value    if cls.task_type    else None,
            difficulty     = cls.difficulty.value   if cls.difficulty   else None,
            selected_node  = response.selected_node,
            selected_model = response.selected_model,
            status         = "success",
            latency_ms     = response.total_ms,
            created_at     = datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(req_row)

        # 3. Insert routing_decision row
        routing = response.routing
        rd_row = RoutingDecision(
            request_id          = request_uuid,
            required_capability = cls.required_capability if cls else None,
            selected_node       = routing.selected_node,
            reason              = routing.reason,
            confidence          = cls.confidence if cls else None,
            was_fallback        = routing.was_fallback,
            created_at          = datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(rd_row)

        await session.commit()

    logger.debug("[persist] PostgreSQL: wrote request + routing_decision for %s", response.request_id)


async def _write_postgres_failure(
    response: NodeFailureResponse,
    request:  QueryRequest,
) -> None:
    """Insert users / requests row for a failed query (no routing_decisions row)."""
    from database.postgres import get_session, upsert_user
    from orchestrator.models import Request

    request_uuid = uuid.UUID(response.request_id)

    async with get_session() as session:
        await upsert_user(session, response.user_id)

        req_row = Request(
            id             = request_uuid,
            user_id        = response.user_id,
            session_id     = getattr(request, "session_id", None),
            query          = request.query,
            input_type     = request.input_type.value,
            selected_node  = response.selected_node,
            status         = response.error_type,   # connection_error / timeout / …
            latency_ms     = response.inference_ms,
            created_at     = datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(req_row)
        await session.commit()

    logger.debug("[persist] PostgreSQL: wrote failure request for %s", response.request_id)


# ─────────────────────────────────────────────────────────────────────────────
# Internal ChromaDB writer
# ─────────────────────────────────────────────────────────────────────────────

async def _write_chroma(
    response: QueryResponse,
    request:  QueryRequest,
) -> None:
    """Store a successful interaction in ChromaDB for semantic search."""
    from database.chroma import add_interaction

    ts = datetime.now(timezone.utc).isoformat()
    await add_interaction(
        request_id = response.request_id,
        user_id    = response.user_id,
        session_id = response.session_id,
        query      = request.query,
        response   = response.response,
        node_id    = response.selected_node,
        model      = response.selected_model,
        timestamp  = ts,
    )
    logger.debug("[persist] ChromaDB: stored interaction for request_id=%s", response.request_id)


# ─────────────────────────────────────────────────────────────────────────────
# Public fire-and-forget entry points
# ─────────────────────────────────────────────────────────────────────────────

async def persist_success(
    response: QueryResponse,
    request:  QueryRequest,
) -> None:
    """
    Persist a successful query to both PostgreSQL and ChromaDB.

    All exceptions are caught — this function must never raise.
    Designed to be run as an asyncio background task.
    """
    try:
        await _write_postgres_success(response, request)
    except Exception as exc:
        logger.error("[persist] PostgreSQL write failed for %s: %s", response.request_id, exc)

    try:
        await _write_chroma(response, request)
    except Exception as exc:
        logger.error("[persist] ChromaDB write failed for %s: %s", response.request_id, exc)


async def persist_failure(
    response: NodeFailureResponse,
    request:  QueryRequest,
) -> None:
    """
    Persist a failed/error query to PostgreSQL only (no ChromaDB — no response text).

    All exceptions are caught — this function must never raise.
    Designed to be run as an asyncio background task.
    """
    try:
        await _write_postgres_failure(response, request)
    except Exception as exc:
        logger.error("[persist] PostgreSQL failure-write failed for %s: %s", response.request_id, exc)
