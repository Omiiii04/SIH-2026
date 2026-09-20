"""
Reasoning node client — wraps the chain-of-thought / advanced reasoning LM Studio worker.

Phase 1: stub only. Phase 2 will implement real httpx calls with system-prompt injection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orchestrator.schemas import NodeType
from nodes.registry import get_node

logger = logging.getLogger(__name__)

NODE_TYPE = NodeType.REASONING

# System prompt injected to encourage structured chain-of-thought output.
_SYSTEM_PROMPT = (
    "You are an advanced reasoning assistant. "
    "Think step-by-step before providing your final answer. "
    "Clearly separate your reasoning from the conclusion."
)


async def call_reasoning_node(
    prompt: str,
    context: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send a reasoning request to the reasoning worker node.

    Automatically injects a chain-of-thought system prompt unless
    the caller supplies one in *parameters*.

    Returns a dict with ``response`` and ``tokens_used``.
    Phase 1: stub — no network call.
    """
    node = get_node(NODE_TYPE)
    logger.info("[reasoning] Stub call → %s", node.inference_url)

    # ── Phase 2 TODO ──────────────────────────────────────────────────────────
    # system_msg = (parameters or {}).get("system_prompt", _SYSTEM_PROMPT)
    # Build messages list with system + context + user prompt.

    return {
        "response": f"[reasoning stub] Step-by-step analysis pending. Live in Phase 2.",
        "tokens_used": None,
    }
