"""
database/models.py
──────────────────
Re-exports ORM models for convenient database-layer imports.

Importing from ``database.models`` gives access to both the SQLAlchemy
Base and all table models without needing to import from ``orchestrator.models``
directly (which lives in a different package layer).
"""

from orchestrator.models import (  # noqa: F401  (re-export)
    Base,
    NodeHealth,
    Request,
    RoutingDecision,
    User,
    WorkerNode,
    WorkerModel,
)

# Backward-compatible alias used by older code / tests
RequestLog = Request

__all__ = [
    "Base",
    "User",
    "Request",
    "RequestLog",   # alias
    "RoutingDecision",
    "NodeHealth",
    "WorkerNode",
    "WorkerModel",
]
