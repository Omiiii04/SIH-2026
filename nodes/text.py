"""
Text node client — wraps the general-purpose text/chat LM Studio worker.

Phase 1: stub only. Phase 2 will implement real httpx calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orchestrator.schemas import NodeType
from nodes.registry import get_node

logger = logging.getLogger(__name__)

NODE_TYPE = NodeType.TEXT


async def call_text_node(
    prompt: str,
    context: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send a chat-completion request to the text worker node.

    Returns a dict with keys:
      - ``response`` (str): model output
      - ``tokens_used`` (int | None): token count if reported

    Phase 1: returns a stub response without making a network call.
    """
    node = get_node(NODE_TYPE)
    logger.info("[text] Stub call → %s", node.inference_url)

    # ── Phase 2 TODO ──────────────────────────────────────────────────────────
    # async with httpx.AsyncClient() as client:
    #     payload = _build_payload(prompt, context, parameters)
    #     resp = await client.post(node.inference_url, json=payload, timeout=...)
    #     ...

    return {
        "response": f"[text stub] prompt received ({len(prompt)} chars). Live in Phase 2.",
        "tokens_used": None,
    }
