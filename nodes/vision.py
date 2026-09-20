"""
Vision node client — wraps the multimodal vision-language LM Studio worker.

Phase 1: stub only. Phase 2 will implement real httpx calls with base64 image encoding.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from orchestrator.schemas import NodeType
from nodes.registry import get_node

logger = logging.getLogger(__name__)

NODE_TYPE = NodeType.VISION


async def call_vision_node(
    prompt: str,
    image_b64: Optional[str] = None,
    context: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Send an image + prompt to the vision worker node.

    Args:
        prompt:     Text instruction / question about the image.
        image_b64:  Base64-encoded image string (JPEG or PNG).
        context:    Prior conversation turns.
        parameters: Model-specific overrides (temperature, etc.).

    Returns a dict with ``response`` and ``tokens_used``.
    Phase 1: stub — no network call.
    """
    node = get_node(NODE_TYPE)
    has_image = image_b64 is not None
    logger.info("[vision] Stub call → %s (image=%s)", node.inference_url, has_image)

    # ── Phase 2 TODO ──────────────────────────────────────────────────────────
    # Build OpenAI-compatible vision payload with image_url content type.

    return {
        "response": f"[vision stub] prompt='{prompt[:60]}' image={'yes' if has_image else 'no'}. Live in Phase 2.",
        "tokens_used": None,
    }
