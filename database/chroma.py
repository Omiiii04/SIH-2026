"""
ChromaDB client wrapper for the SIH-2026 semantic memory layer.

Stores and retrieves conversation embeddings per session.

Phase 1: client configuration only — no live ChromaDB connection required.
Phase 2: ``get_client()`` will establish a real HTTP connection to ChromaDB.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orchestrator.config import get_settings

logger = logging.getLogger(__name__)

# Module-level lazy client (initialised on first use in Phase 2)
_client: Any = None
_collection: Any = None


def get_client() -> Any:
    """
    Return the ChromaDB HttpClient singleton.
    Creates the client on first call.

    Phase 2 implementation (uncomment when ChromaDB is available)::

        import chromadb
        global _client
        if _client is None:
            cfg = get_settings()
            _client = chromadb.HttpClient(host=cfg.chroma_host, port=cfg.chroma_port)
        return _client
    """
    # ── Phase 2 TODO ────────────────────────────────────────────────────────
    logger.warning("ChromaDB client requested but not yet initialised (Phase 1 stub).")
    return None


def get_collection() -> Any:
    """
    Return (or create) the primary conversation-memory collection.

    Phase 2 will call::

        client = get_client()
        cfg = get_settings()
        return client.get_or_create_collection(cfg.chroma_collection)
    """
    # ── Phase 2 TODO ────────────────────────────────────────────────────────
    return None


async def add_memory(
    session_id: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Embed *text* and store it in the conversation-memory collection
    tagged with *session_id*.

    Phase 1: no-op stub.
    """
    logger.debug("[chroma] add_memory stub: session=%s, text_len=%d", session_id, len(text))


async def query_memory(
    session_id: str,
    query_text: str,
    n_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    Retrieve the *n_results* most semantically similar memory chunks
    for the given *session_id*.

    Returns a list of dicts with keys ``text`` and ``metadata``.
    Phase 1: returns empty list.
    """
    logger.debug("[chroma] query_memory stub: session=%s", session_id)
    return []
