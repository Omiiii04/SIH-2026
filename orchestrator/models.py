"""
SQLAlchemy ORM models for the SIH-2026 Orchestrator.

These map to the PostgreSQL tables used for:
  - Request logging
  - Node registry / health snapshots
  - Conversation session metadata
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class RequestLog(Base):
    """Records every inference request routed through the orchestrator."""

    __tablename__ = "request_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(64), nullable=True, index=True)
    node_type = Column(String(32), nullable=False)          # text | vision | reasoning | code | rag
    node_url = Column(String(256), nullable=False)
    prompt_preview = Column(Text, nullable=True)            # first 256 chars of prompt
    status = Column(String(16), nullable=False)             # success | error | timeout
    latency_ms = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NodeHealth(Base):
    """Snapshot of a worker node's health at a point in time."""

    __tablename__ = "node_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_type = Column(String(32), nullable=False, index=True)
    node_url = Column(String(256), nullable=False)
    is_online = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Float, nullable=True)
    model_loaded = Column(String(256), nullable=True)       # model name reported by LM Studio
    checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ConversationSession(Base):
    """Tracks multi-turn conversation sessions."""

    __tablename__ = "conversation_sessions"

    id = Column(String(64), primary_key=True)               # client-supplied or generated UUID str
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    turn_count = Column(Integer, default=0, nullable=False)
    metadata_ = Column("metadata", Text, nullable=True)     # JSON blob for arbitrary session data
