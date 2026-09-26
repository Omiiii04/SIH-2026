"""
orchestrator/models.py
──────────────────────
SQLAlchemy 2.x ORM models for the SIH-2026 Phase 4 persistence layer.

Tables
------
  users            — unique caller identities
  requests         — one row per routed query (structured source of truth)
  routing_decisions — one row per successful routing decision (FK → requests)
  node_health      — rolling node health snapshots (upserted per node_id)

All timestamps are UTC-naive to stay consistent with PostgreSQL's
timestamptz-less TIMESTAMP type used by default.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ─────────────────────────────────────────────────────────────────────────────
# users
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    """Unique caller identity — created on first query from that user_id."""

    __tablename__ = "users"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(String(128), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    requests = relationship("Request", back_populates="user", lazy="noload")

    def __repr__(self) -> str:
        return f"<User user_id={self.user_id!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# requests
# ─────────────────────────────────────────────────────────────────────────────

class Request(Base):
    """Records every inference request routed through the orchestrator."""

    __tablename__ = "requests"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(String(128), ForeignKey("users.user_id", ondelete="CASCADE"),
                            nullable=False, index=True)
    session_id     = Column(String(128), nullable=True, index=True)
    query          = Column(Text,        nullable=False)
    input_type     = Column(String(32),  nullable=False)   # text | image | code | reasoning | retrieval
    task_type      = Column(String(64),  nullable=True)    # from Phase 3 classifier
    difficulty     = Column(String(16),  nullable=True)    # low | medium | high
    selected_node  = Column(String(64),  nullable=True)    # e.g. NODE-CODE
    selected_model = Column(String(256), nullable=True)    # model name from LM Studio
    status         = Column(String(16),  nullable=False, default="success")  # success | error | timeout
    latency_ms     = Column(Float,       nullable=True)
    created_at     = Column(DateTime,    default=datetime.utcnow, nullable=False, index=True)

    user             = relationship("User",            back_populates="requests", lazy="noload")
    routing_decision = relationship("RoutingDecision", back_populates="request",  lazy="noload",
                                    uselist=False)

    def __repr__(self) -> str:
        return f"<Request id={self.id} node={self.selected_node!r} status={self.status!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# routing_decisions
# ─────────────────────────────────────────────────────────────────────────────

class RoutingDecision(Base):
    """Stores the routing metadata for each successful request."""

    __tablename__ = "routing_decisions"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id           = Column(UUID(as_uuid=True), ForeignKey("requests.id", ondelete="CASCADE"),
                                  nullable=False, unique=True, index=True)
    required_capability  = Column(String(64),  nullable=True)
    selected_node        = Column(String(64),  nullable=False)
    reason               = Column(Text,        nullable=True)
    confidence           = Column(Float,       nullable=True)
    was_fallback         = Column(Boolean,     nullable=False, default=False)
    created_at           = Column(DateTime,    default=datetime.utcnow, nullable=False)

    request = relationship("Request", back_populates="routing_decision", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<RoutingDecision request_id={self.request_id} "
            f"node={self.selected_node!r} fallback={self.was_fallback}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# node_health
# ─────────────────────────────────────────────────────────────────────────────

class NodeHealth(Base):
    """
    Rolling health snapshot — upserted on each health check or when a node
    goes offline due to a failed inference call.

    One row per node_id (unique constraint enforced).
    """

    __tablename__ = "node_health"
    __table_args__ = (UniqueConstraint("node_id", name="uq_node_health_node_id"),)

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id    = Column(String(64),  nullable=False, index=True)
    status     = Column(String(16),  nullable=False, default="unknown")  # online | offline | unknown
    latency_ms = Column(Float,       nullable=True)
    last_seen  = Column(DateTime,    default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<NodeHealth node={self.node_id!r} status={self.status!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# worker_nodes
# ─────────────────────────────────────────────────────────────────────────────

class WorkerNode(Base):
    """Dynamic LAN Node Registry."""

    __tablename__ = "worker_nodes"

    id           = Column(String(64), primary_key=True) # e.g. NODE-01
    name         = Column(String(128), nullable=False)
    endpoint     = Column(String(256), nullable=False, unique=True, index=True)
    enabled      = Column(Boolean, nullable=False, default=True)
    status       = Column(String(32), nullable=False, default="unknown")
    priority     = Column(Integer, nullable=False, default=1)
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_checked = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)

    models = relationship("WorkerModel", back_populates="node", lazy="joined", cascade="all, delete-orphan")


# ─────────────────────────────────────────────────────────────────────────────
# worker_models
# ─────────────────────────────────────────────────────────────────────────────

class WorkerModel(Base):
    """Models discovered on a worker node."""

    __tablename__ = "worker_models"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id        = Column(String(64), ForeignKey("worker_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id       = Column(String(256), nullable=False)
    model_type     = Column(String(64), nullable=True)
    architecture   = Column(String(64), nullable=True)
    quantization   = Column(String(64), nullable=True)
    context_length = Column(Integer, nullable=True)
    loaded_state   = Column(String(64), nullable=True)
    discovered_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    node = relationship("WorkerNode", back_populates="models", lazy="noload")


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compat re-export used by database/models.py
# ─────────────────────────────────────────────────────────────────────────────

# Legacy names kept so existing re-export in database/models.py doesn't break
RequestLog = Request
ConversationSession = None  # removed in Phase 4; use requests + session_id column
