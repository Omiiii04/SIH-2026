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
_collection: Any = None          # conversation_memory
_rag_collection: Any = None     # rag_documents (file upload RAG)


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def init_chroma() -> None:
    """
    Connect to the ChromaDB HTTP server and create/get the conversation-memory
    collection. Call once at application startup.
    """
    global _client, _collection, _rag_collection
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
        _rag_collection = _client.get_or_create_collection(
            name="rag_documents",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB connected: host=%s port=%s collection=%s + rag_documents",
            cfg.chroma_host, cfg.chroma_port, cfg.chroma_collection,
        )
    except Exception as exc:
        logger.warning("ChromaDB unavailable at startup: %s — memory features disabled.", exc)
        _client = None
        _collection = None
        _rag_collection = None


def close_chroma() -> None:
    """No-op — the HttpClient is stateless; nothing to close."""
    global _client, _collection, _rag_collection
    _client = None
    _collection = None
    _rag_collection = None
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


# ─────────────────────────────────────────────────────────────────────────────
# RAG Document Ingestion & Retrieval
# ─────────────────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """
    Split *text* into overlapping chunks of at most *chunk_size* characters.
    Tries to split on paragraph/sentence boundaries first.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            # Try to find a natural break (newline > space) near the boundary
            break_pos = text.rfind("\n", start, end)
            if break_pos == -1 or break_pos <= start:
                break_pos = text.rfind(" ", start, end)
            if break_pos > start:
                end = break_pos
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap  # overlap for context continuity
    return chunks


def add_document_chunks(
    *,
    doc_id: str,          # unique document identifier (e.g. UUID)
    filename: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    chunk_size: int = 500,
    overlap: int = 100,
) -> int:
    """
    Chunk *text* and upsert each chunk into the ``rag_documents`` collection.

    Returns the number of chunks stored, or 0 if ChromaDB is unavailable.
    """
    if _rag_collection is None:
        logger.warning("[chroma-rag] rag_documents collection not initialised — skipping ingest.")
        return 0

    chunks = _chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        logger.warning("[chroma-rag] No text to index for doc_id=%s", doc_id)
        return 0

    base_meta = {"doc_id": doc_id, "filename": filename, **(metadata or {})}
    ids       = [f"{doc_id}__chunk_{i}" for i in range(len(chunks))]
    metadatas = [{**base_meta, "chunk_index": i, "chunk_count": len(chunks)} for i in range(len(chunks))]

    try:
        _rag_collection.upsert(
            documents=chunks,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("[chroma-rag] Indexed %d chunks for '%s' (doc_id=%s)", len(chunks), filename, doc_id)
        return len(chunks)
    except Exception as exc:
        logger.warning("[chroma-rag] add_document_chunks failed for doc_id=%s: %s", doc_id, exc)
        return 0


def query_documents(
    *,
    query: str,
    n_results: int = 5,
    doc_id: Optional[str] = None,   # restrict to a specific document if provided
) -> List[Dict[str, Any]]:
    """
    Semantic search across indexed document chunks.

    Returns a list of dicts::

        [
          {
            "chunk_id":    "...",
            "text":        "...",
            "doc_id":      "...",
            "filename":    "...",
            "chunk_index": 0,
            "score":       0.91,
          },
          ...
        ]

    Returns [] if ChromaDB is unavailable.
    """
    if _rag_collection is None:
        logger.debug("[chroma-rag] query_documents skipped — collection not initialised.")
        return []

    where = {"doc_id": doc_id} if doc_id else None

    try:
        # ChromaDB raises if n_results > number of items in the collection.
        # Cap it to avoid a silent exception swallowing all results.
        total_in_collection = _rag_collection.count()
        if total_in_collection == 0:
            logger.debug("[chroma-rag] rag_documents collection is empty — no chunks to search.")
            return []
        safe_n = min(n_results, total_in_collection)
        if safe_n != n_results:
            logger.debug(
                "[chroma-rag] Capped n_results from %d → %d (collection only has %d chunks)",
                n_results, safe_n, total_in_collection,
            )

        results = _rag_collection.query(
            query_texts=[query],
            n_results=safe_n,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("[chroma-rag] query_documents failed: %s", exc)
        return []

    if not results or not results.get("ids"):
        return []

    ids       = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    output = []
    for cid, doc, meta, dist in zip(ids, documents, metadatas, distances):
        output.append({
            "chunk_id":    cid,
            "text":        doc,
            "doc_id":      meta.get("doc_id", ""),
            "filename":    meta.get("filename", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "score":       round(1.0 - float(dist), 4),
        })

    return output
