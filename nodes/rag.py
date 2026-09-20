"""
RAG node client — wraps the retrieval-augmented generation LM Studio worker.

Phase 1: stub only.
Phase 2 will implement:
  - ChromaDB semantic search to fetch relevant document chunks.
  - Context injection into the LM Studio prompt.
  - Result logging.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orchestrator.schemas import NodeType
from nodes.registry import get_node

logger = logging.getLogger(__name__)

NODE_TYPE = NodeType.RAG


async def call_rag_node(
    prompt: str,
    session_id: Optional[str] = None,
    context: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a retrieval-augmented generation request.

    Flow (Phase 2):
      1. Embed the prompt via a local embedding model.
      2. Query ChromaDB for the top-k relevant chunks.
      3. Inject retrieved chunks as context into the LM Studio prompt.
      4. Call the RAG worker node and return the grounded response.

    Returns a dict with ``response``, ``tokens_used``, and ``retrieved_chunks``.
    Phase 1: stub — no network or ChromaDB call.
    """
    node = get_node(NODE_TYPE)
    logger.info("[rag] Stub call (session=%s) → %s", session_id, node.inference_url)

    # ── Phase 2 TODO ──────────────────────────────────────────────────────────
    # chunks = await chroma_client.query(prompt, n_results=5)
    # augmented_prompt = build_rag_prompt(prompt, chunks)
    # response = await call_lm_studio(node.inference_url, augmented_prompt, parameters)

    return {
        "response": f"[rag stub] Will retrieve relevant docs and answer: '{prompt[:60]}'. Live in Phase 2.",
        "tokens_used": None,
        "retrieved_chunks": [],
    }
