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
    """
    Dynamic LAN node registry.

    Maps to the existing PostgreSQL schema.  The real table uses:
      - id UUID PK  (generated at insert time)
      - node_id VARCHAR — the deterministic "NODE-1", "NODE-2" … key
      - hostname, endpoint, lm_studio_url, status — pre-existing columns
      - name, enabled, priority, last_checked, last_success — added via
        migrate_db() on first startup after this version is deployed

    All application code looks up nodes by node_id (the string key),
    not by the UUID primary key.
    """

    __tablename__ = "worker_nodes"

    # Real DB primary key — UUID generated by the application.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Pre-existing real DB columns
    node_id          = Column(String(64),  nullable=False, unique=True, index=True)
    hostname         = Column(String(256), nullable=True)
    endpoint         = Column(String(256), nullable=False, unique=True, index=True)
    lm_studio_url    = Column(String(256), nullable=True)
    status           = Column(String(32),  nullable=False, default="unknown")
    heartbeat_interval = Column(Integer,   nullable=True, default=30)
    registered_at    = Column(DateTime,    default=datetime.utcnow, nullable=False)
    last_heartbeat   = Column(DateTime,    nullable=True)
    last_seen        = Column(DateTime,    nullable=True)

    # New columns — added by migrate_db(); safe to declare here.
    name         = Column(String(128), nullable=True)
    enabled      = Column(Boolean,     nullable=False, server_default="TRUE")
    priority     = Column(Integer,     nullable=False, server_default="1")
    last_checked = Column(DateTime,    nullable=True)
    last_success = Column(DateTime,    nullable=True)

    # Relationships (FK on child side references worker_nodes.node_id)
    models = relationship(
        "WorkerModel",
        back_populates="node",
        lazy="joined",
        cascade="all, delete-orphan",
        foreign_keys="[WorkerModel.node_id]",
    )


# ─────────────────────────────────────────────────────────────────────────────
# worker_models
# ─────────────────────────────────────────────────────────────────────────────

class WorkerModel(Base):
    """
    Models discovered on a worker node.

    The real DB FK column is `worker_node_id` (VARCHAR), referencing
    `worker_nodes.node_id` — NOT the UUID primary key.
    The Python attribute is kept as `node_id` for API compatibility.
    """

    __tablename__ = "worker_models"

    id      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Python attr `node_id` → DB column `worker_node_id` → FK → worker_nodes.node_id
    node_id = Column(
        "worker_node_id",                         # actual DB column name
        String(64),
        ForeignKey("worker_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    model_id       = Column(String(256), nullable=False)
    model_type     = Column(String(64),  nullable=True)
    architecture   = Column(String(64),  nullable=True)
    quantization   = Column(String(64),  nullable=True)
    context_length = Column(Integer,     nullable=True)
    is_loaded      = Column(Boolean,     nullable=True, default=False)
    modalities     = Column(Text,        nullable=True)
    capabilities_str = Column(Text,      nullable=True)
    discovered_at  = Column(DateTime,    default=datetime.utcnow, nullable=False)

    node = relationship(
        "WorkerNode",
        back_populates="models",
        lazy="noload",
        foreign_keys=[node_id],
    )


# ─────────────────────────────────────────────────────────────────────────────
# sessions
# ─────────────────────────────────────────────────────────────────────────────

class Session(Base):
    """
    Persistent conversation session.
    """

    __tablename__ = "sessions"

    id         = Column(String(64),  primary_key=True)
    user_id    = Column(String(128), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title      = Column(String(256), nullable=False)
    created_at = Column(DateTime,    default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime,    default=datetime.utcnow, nullable=False, index=True)

    messages   = relationship("Message", back_populates="session", cascade="all, delete-orphan", lazy="noload")


# ─────────────────────────────────────────────────────────────────────────────
# messages
# ─────────────────────────────────────────────────────────────────────────────

class Message(Base):
    """
    Individual message within a conversation session.
    """

    __tablename__ = "messages"

    id               = Column(String(64),  primary_key=True)
    session_id       = Column(String(64),  ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id          = Column(String(128), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    role             = Column(String(16),  nullable=False)   # user | assistant
    content          = Column(Text,        nullable=False)
    request_id       = Column(String(64),  nullable=True)
    routing_metadata = Column(Text,        nullable=True)   # JSON-encoded routing / inference metadata
    created_at       = Column(DateTime,    default=datetime.utcnow, nullable=False, index=True)

    session = relationship("Session", back_populates="messages", lazy="noload")


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compat re-export used by database/models.py
# ─────────────────────────────────────────────────────────────────────────────

# Legacy names kept so existing re-export in database/models.py doesn't break
RequestLog = Request
ConversationSession = Session

