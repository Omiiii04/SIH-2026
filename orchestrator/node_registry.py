"""
orchestrator/node_registry.py
──────────────────────────────
Phase 3 Node Registry — single source of truth for all worker nodes.

New in Phase 3:
  * set_node_status(node_id, status)   — allows runtime online/offline marking
  * get_nodes_by_capability(cap)       — returns ALL nodes for a capability,
                                         sorted by priority (for fallback routing)
  * Nodes carry capability string that maps to ClassificationResult.required_capability

Priority: lower integer = higher priority. Used for fallback selection.
All endpoint values are sourced from settings (→ .env).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from orchestrator.config import get_settings
from orchestrator.schemas import InputType, NodeRegistryEntry, NodeType

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Capability → fallback NodeType order
# When the primary node for a capability is offline, try these in order.
# ─────────────────────────────────────────────────────────────────────────────

_CAPABILITY_FALLBACK_ORDER: Dict[str, List[NodeType]] = {
    "text":                [NodeType.TEXT, NodeType.REASONING],
    "vision":              [NodeType.VISION],                        # no text fallback for images
    "coding":              [NodeType.CODE, NodeType.TEXT],
    "reasoning":           [NodeType.REASONING, NodeType.TEXT],
    "embedding/retrieval": [NodeType.RAG, NodeType.TEXT],
}


# ─────────────────────────────────────────────────────────────────────────────
# Registry builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_registry() -> Dict[str, NodeRegistryEntry]:
    cfg = get_settings()

    entries = [
        NodeRegistryEntry(
            node_id="NODE-1",
            node_name="Node 1 (Orchestrator)",
            capability="text",
            node_type=NodeType.TEXT,
            model="",          # populated dynamically from /v1/models on first health probe
            endpoint=cfg.node_1_url,
            status=_initial_status(cfg.node_1_url),
            supported_input_types=[InputType.TEXT.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-2",
            node_name="Node 2",
            capability="vision",
            node_type=NodeType.VISION,
            model="",          # populated dynamically from /v1/models on first health probe
            endpoint=cfg.node_2_url,
            status=_initial_status(cfg.node_2_url),
            supported_input_types=[InputType.IMAGE.value, InputType.TEXT.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-3",
            node_name="Node 3",
            capability="reasoning",
            node_type=NodeType.REASONING,
            model="",          # populated dynamically from /v1/models on first health probe
            endpoint=cfg.node_3_url,
            status=_initial_status(cfg.node_3_url),
            supported_input_types=[InputType.TEXT.value, InputType.REASONING.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-4",
            node_name="Node 4",
            capability="coding",
            node_type=NodeType.CODE,
            model="",          # populated dynamically from /v1/models on first health probe
            endpoint=cfg.node_4_url,
            status=_initial_status(cfg.node_4_url),
            supported_input_types=[InputType.TEXT.value, InputType.CODE.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-5",
            node_name="Node 5",
            capability="embedding/retrieval",
            node_type=NodeType.RAG,
            model="",          # populated dynamically from /v1/models on first health probe
            endpoint=cfg.node_5_url,
            status=_initial_status(cfg.node_5_url),
            supported_input_types=[InputType.TEXT.value, InputType.RETRIEVAL.value],
            priority=1,
        ),
    ]
    return {e.node_id: e for e in entries}


def _initial_status(endpoint: str) -> str:
    return "not_configured" if not endpoint.strip() else "unknown"


# Module-level singleton (mutable for runtime status updates)
_REGISTRY: Dict[str, NodeRegistryEntry] = _build_registry()

_TYPE_TO_NODE_ID: Dict[NodeType, str] = {
    e.node_type: e.node_id for e in _REGISTRY.values()
}

_CAPABILITY_TO_NODE_IDS: Dict[str, List[str]] = {}
for _e in _REGISTRY.values():
    _CAPABILITY_TO_NODE_IDS.setdefault(_e.capability, []).append(_e.node_id)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_registry() -> Dict[str, NodeRegistryEntry]:
    """Return the full registry dict."""
    return _REGISTRY


def list_nodes() -> List[NodeRegistryEntry]:
    """Return all nodes sorted by priority."""
    return sorted(_REGISTRY.values(), key=lambda n: n.priority)


def get_node_by_type(node_type: NodeType) -> Optional[NodeRegistryEntry]:
    """Return the NodeRegistryEntry for a given NodeType, or None."""
    node_id = _TYPE_TO_NODE_ID.get(node_type)
    return _REGISTRY.get(node_id) if node_id else None


def get_node_by_id(node_id: str) -> Optional[NodeRegistryEntry]:
    """Return the NodeRegistryEntry for a given node_id, or None."""
    return _REGISTRY.get(node_id)


def get_nodes_by_capability(capability: str) -> List[NodeRegistryEntry]:
    """
    Return all nodes that match *capability*, sorted by priority.
    Used by the Phase 3 router for fallback selection.
    """
    node_ids = _CAPABILITY_TO_NODE_IDS.get(capability, [])
    nodes = [_REGISTRY[nid] for nid in node_ids if nid in _REGISTRY]
    return sorted(nodes, key=lambda n: n.priority)


def get_online_node_for_capability(capability: str) -> Optional[NodeRegistryEntry]:
    """
    Return the highest-priority ONLINE node for a required capability.
    Falls back through _CAPABILITY_FALLBACK_ORDER when the primary is offline.
    Returns None if no suitable online node exists.
    """
    fallback_types = _CAPABILITY_FALLBACK_ORDER.get(capability, [])

    for node_type in fallback_types:
        node_id = _TYPE_TO_NODE_ID.get(node_type)
        if not node_id:
            continue
        node = _REGISTRY.get(node_id)
        if node and node.status not in ("offline", "not_configured"):
            return node

    return None


def set_node_status(node_id: str, status: str) -> bool:
    """
    Update the runtime status of a node.

    Parameters
    ----------
    node_id: Registry key e.g. "NODE-TEXT"
    status:  "online" | "offline" | "unknown" | "not_configured"

    Returns True if the node was found and updated.
    """
    node = _REGISTRY.get(node_id)
    if node is None:
        logger.warning("set_node_status: unknown node_id=%s", node_id)
        return False
    # NodeRegistryEntry is a Pydantic model; update via model_copy
    _REGISTRY[node_id] = node.model_copy(update={"status": status})
    logger.info("Node status updated: %s → %s", node_id, status)
    return True


def set_node_model(node_id: str, model: str) -> bool:
    """
    Update the active model name for a node (discovered live from /v1/models).

    Called by the health monitor after each successful probe so that the
    router always sends the exact model ID that LM Studio reports, regardless
    of what is hardcoded in config.

    Parameters
    ----------
    node_id: Registry key e.g. "NODE-TEXT"
    model:   The model identifier returned by GET /v1/models → data[0].id

    Returns True if the node was found and updated.
    """
    if not model:
        return False
    node = _REGISTRY.get(node_id)
    if node is None:
        logger.warning("set_node_model: unknown node_id=%s", node_id)
        return False
    if node.model != model:
        _REGISTRY[node_id] = node.model_copy(update={"model": model})
        logger.info("Node model updated: %s → %s", node_id, model)
    return True


def reset_registry() -> None:
    """
    Rebuild the registry from settings (clears any runtime status overrides).
    Useful in tests.
    """
    global _REGISTRY
    _REGISTRY = _build_registry()
    logger.debug("Registry reset to initial state.")
