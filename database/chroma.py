"""
database/chroma.py
──────────────────
Phase 4 — ChromaDB HTTP client wrapper.

Responsibilities
────────────────
  init_chroma()         — connect to the ChromaDB server, create/get collection
  close_chroma()        — noop (stateless client)
  add_interaction()     — store a query+response embedding with rich metadata
  search_interactions() — semantic search across stored interactions
  ping_chroma()         — liveness probe

Design
──────
  • Uses chromadb.HttpClient (client-server mode) so no local embedding
    model is needed on the orchestrator — ChromaDB server runs in Docker.
  • ChromaDB uses its default embedding function (all-MiniLM-L6-v2) on the
    server side — no external API key required.
  • Each document stored = query + "\\n\\n" + response (so both are searchable).
  • Metadata keys: user_id, session_id, request_id, node_id, model, timestamp,
    query_preview (first 120 chars).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from orchestrator.config import get_settings

logger = logging.getLogger(__name__)

_client:     Any = None
_collection: Any = None


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def init_chroma() -> None:
    """
    Connect to the ChromaDB HTTP server and create/get the conversation-memory
    collection. Call once at application startup.
    """
    global _client, _collection
    import chromadb  # local import keeps startup time fast when not installed

    cfg = get_settings()
    try:
        _client = chromadb.HttpClient(host=cfg.chroma_host, port=cfg.chroma_port)
        # Heartbeat will raise if server is unreachable
        _client.heartbeat()
        _collection = _client.get_or_create_collection(
            name=cfg.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB connected: host=%s port=%s collection=%s",
            cfg.chroma_host, cfg.chroma_port, cfg.chroma_collection,
        )
    except Exception as exc:
        logger.warning("ChromaDB unavailable at startup: %s — memory features disabled.", exc)
        _client = None
        _collection = None


def close_chroma() -> None:
    """No-op — the HttpClient is stateless; nothing to close."""
    global _client, _collection
    _client = None
    _collection = None
    logger.info("ChromaDB client released.")


def ping_chroma() -> bool:
    """Return True if ChromaDB is reachable."""
    if _client is None:
        return False
    try:
        _client.heartbeat()
        return True
    except Exception as exc:
        logger.warning("ChromaDB ping failed: %s", exc)
        return False


def _get_collection() -> Any:
    """Return the module-level collection or raise RuntimeError."""
    if _collection is None:
        raise RuntimeError(
            "ChromaDB collection is not initialised. "
            "Call init_chroma() at application startup."
        )
    return _collection


# ─────────────────────────────────────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────────────────────────────────────

async def add_interaction(
    *,
    request_id:  str,
    user_id:     str,
    session_id:  Optional[str],
    query:       str,
    response:    str,
    node_id:     str,
    model:       str,
    timestamp:   str,  # ISO-8601 UTC string
) -> None:
    """
    Embed the concatenated query+response and store it with metadata.

    The document text = query + "\\n\\n" + response so that semantic search
    can match on either part.

    Silently logs and returns if ChromaDB is unavailable.
    """
    if _collection is None:
        logger.debug("[chroma] add_interaction skipped — collection not initialised.")
        return

    doc_text = f"{query}\n\n{response}"
    metadata: Dict[str, Any] = {
        "user_id":       user_id,
        "session_id":    session_id or "",
        "node_id":       node_id,
        "model":         model,
        "timestamp":     timestamp,
        "query_preview": query[:120],
    }

    try:
        _collection.add(
            documents=[doc_text],
            metadatas=[metadata],
            ids=[request_id],
        )
        logger.debug("[chroma] Stored interaction request_id=%s user=%s", request_id, user_id)
    except Exception as exc:
        logger.warning("[chroma] add_interaction failed for request_id=%s: %s", request_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval
# ─────────────────────────────────────────────────────────────────────────────

def search_interactions(
    *,
    user_id:   str,
    query:     str,
    n_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    Retrieve the *n_results* most semantically similar past interactions
    for the given *user_id*.

    Returns a list of dicts::

        [
          {
            "request_id": "...",
            "query":      "...",        # from query_preview metadata
            "response":   "...",        # reconstructed from doc text
            "node_id":    "...",
            "model":      "...",
            "timestamp":  "...",
            "score":      0.92,         # cosine similarity
          },
          ...
        ]

    Returns [] if ChromaDB is unavailable or no results found.
    """
    if _collection is None:
        logger.debug("[chroma] search_interactions skipped — collection not initialised.")
        return []

    try:
        results = _collection.query(
            query_texts=[query],
            n_results=n_results,
            where={"user_id": user_id} if user_id else None,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("[chroma] search_interactions failed: %s", exc)
        return []

    if not results or not results.get("ids"):
        return []

    ids        = results["ids"][0]
    documents  = results["documents"][0]
    metadatas  = results["metadatas"][0]
    distances  = results["distances"][0]

    output = []
    for rid, doc, meta, dist in zip(ids, documents, metadatas, distances):
        # Split document back into query+response parts
        parts = doc.split("\n\n", 1)
        q_text = parts[0] if len(parts) >= 1 else doc
        r_text = parts[1] if len(parts) >= 2 else ""

        output.append({
            "request_id": rid,
            "query":      meta.get("query_preview", q_text[:120]),
            "response":   r_text[:500],   # truncate long responses
            "node_id":    meta.get("node_id", ""),
            "model":      meta.get("model", ""),
            "timestamp":  meta.get("timestamp", ""),
            "session_id": meta.get("session_id", ""),
            "score":      round(1.0 - float(dist), 4),  # cosine → similarity
        })

    return output
