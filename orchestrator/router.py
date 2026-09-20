"""
Request router for the SIH-2026 Orchestrator.

Responsibilities
----------------
* Decide which worker node should handle an InferenceRequest.
* Apply simple heuristics / keyword matching when no explicit node_type is set.
* Delegate actual HTTP forwarding to individual node modules (future phase).
* Log routing decisions to PostgreSQL (future phase).

This module is intentionally lightweight for Phase 1 — no live node calls yet.
"""

from __future__ import annotations

import logging
from typing import Optional

from orchestrator.schemas import InferenceRequest, NodeType

logger = logging.getLogger(__name__)

# ── Keyword heuristics ─────────────────────────────────────────────────────────
# Maps a NodeType to a list of trigger keywords found in the prompt.
# Evaluated in priority order; first match wins.
_ROUTING_RULES: list[tuple[NodeType, list[str]]] = [
    (NodeType.CODE, ["code", "function", "debug", "script", "python", "javascript", "compile", "error in code"]),
    (NodeType.VISION, ["image", "photo", "picture", "describe this", "what is in", "ocr", "visual"]),
    (NodeType.REASONING, ["reason", "analyse", "analyze", "explain why", "step by step", "logic", "infer"]),
    (NodeType.RAG, ["document", "file", "pdf", "search", "retrieve", "knowledge base", "based on the"]),
    (NodeType.TEXT, []),  # default fallback
]


def route_request(request: InferenceRequest) -> NodeType:
    """
    Determine the appropriate NodeType for a given InferenceRequest.

    Priority:
    1. Explicit ``node_type`` set by the client.
    2. Keyword heuristic over the prompt text.
    3. Default fallback → NodeType.TEXT
    """
    if request.node_type is not None:
        logger.debug("Explicit node_type=%s supplied; skipping heuristics.", request.node_type)
        return request.node_type

    prompt_lower = request.prompt.lower()

    for node_type, keywords in _ROUTING_RULES:
        if not keywords:
            # This is the explicit fallback entry — use it.
            logger.debug("No keyword matched; routing to fallback node_type=%s", node_type)
            return node_type
        if any(kw in prompt_lower for kw in keywords):
            logger.debug("Keyword match → routing to node_type=%s", node_type)
            return node_type

    # Should never reach here because TEXT has an empty keyword list above,
    # but kept as a safety net.
    return NodeType.TEXT
