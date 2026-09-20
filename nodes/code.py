"""
Code node client — wraps the code-generation / debugging LM Studio worker.

Phase 1: stub only. Phase 2 will implement real httpx calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orchestrator.schemas import NodeType
from nodes.registry import get_node

logger = logging.getLogger(__name__)

NODE_TYPE = NodeType.CODE

_SYSTEM_PROMPT = (
    "You are an expert software engineer. "
    "Provide clear, well-commented, production-quality code. "
    "If asked to debug, explain the root cause before showing the fix."
)


async def call_code_node(
    prompt: str,
    language: Optional[str] = None,
    context: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send a code-related request to the code worker node.

    Args:
        prompt:   User's code question, bug description, or feature request.
        language: Optional programming language hint (e.g. "python", "rust").
        context:  Prior conversation turns for multi-turn coding sessions.
        parameters: Model-specific overrides.

    Returns a dict with ``response`` and ``tokens_used``.
    Phase 1: stub — no network call.
    """
    node = get_node(NODE_TYPE)
    lang_hint = f" [language={language}]" if language else ""
    logger.info("[code] Stub call%s → %s", lang_hint, node.inference_url)

    # ── Phase 2 TODO ──────────────────────────────────────────────────────────
    # Inject language hint into system prompt, build messages, call httpx.

    return {
        "response": f"[code stub] Code generation for: '{prompt[:60]}'{lang_hint}. Live in Phase 2.",
        "tokens_used": None,
    }
