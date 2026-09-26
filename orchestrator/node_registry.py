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

from orchestrator.schemas import InputType, NodeRegistryEntry, NodeType

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Capability → fallback NodeType order
# When the primary node for a capability is offline, try these in order.
# ─────────────────────────────────────────────────────────────────────────────

_CAPABILITY_FALLBACK_ORDER: Dict[str, List[NodeType]] = {
    "text":                [NodeType.TEXT, NodeType.REASONING],
    # Vision falls back to TEXT/REASONING when NODE-2 is offline or times out.
    # Text nodes cannot process image pixels, but can still respond to the
    # filename/description text that was sent as the query.
    "vision":              [NodeType.VISION, NodeType.TEXT, NodeType.REASONING],
    "coding":              [NodeType.CODE, NodeType.TEXT],
    "reasoning":           [NodeType.REASONING, NodeType.TEXT],
    "embedding/retrieval": [NodeType.RAG, NodeType.TEXT],
}


# ─────────────────────────────────────────────────────────────────────────────
# Registry builder
# ─────────────────────────────────────────────────────────────────────────────


def _build_registry() -> Dict[str, NodeRegistryEntry]:
    """
    Returns empty dict — registry is now populated dynamically by
    node_manager.sync_registry_from_db() during application startup.

    Kept so existing callers of reset_registry() still compile.
    """
    return {}


def _initial_status(endpoint: str) -> str:
    return "not_configured" if not endpoint.strip() else "unknown"


# Module-level singleton — starts empty, populated by reconcile_nodes_from_env()
# → sync_registry_from_db() at application startup.
_REGISTRY: Dict[str, NodeRegistryEntry] = {}

_TYPE_TO_NODE_ID: Dict[NodeType, str] = {}

_CAPABILITY_TO_NODE_IDS: Dict[str, List[str]] = {}


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


def get_online_node_for_capability(
    capability: str,
    skip_ids: set[str] | None = None,
) -> Optional[NodeRegistryEntry]:
    """
    Return the highest-priority ONLINE node for a required capability.
    Falls back through _CAPABILITY_FALLBACK_ORDER when the primary is offline.
    Nodes whose IDs appear in *skip_ids* are excluded (used by the router retry
    loop to bypass already-attempted nodes regardless of their registry status).
    Returns None if no suitable online node exists.
    """
    fallback_types = _CAPABILITY_FALLBACK_ORDER.get(capability, [])
    _skip = skip_ids or set()

    for node_type in fallback_types:
        node_id = _TYPE_TO_NODE_ID.get(node_type)
        if not node_id:
            continue
        if node_id in _skip:
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


def set_node_capability(node_id: str, capability: str, node_type: "NodeType | None" = None) -> bool:
    """
    Override the capability (and optionally node_type) for a registry entry.
    Used in tests to simulate nodes with specific capabilities.
    """
    from orchestrator.schemas import NodeType as _NT
    node = _REGISTRY.get(node_id)
    if node is None:
        logger.warning("set_node_capability: unknown node_id=%s", node_id)
        return False
    update: dict = {"capability": capability}
    if node_type is not None:
        update["node_type"] = node_type
    _REGISTRY[node_id] = node.model_copy(update=update)
    _rebuild_indexes()
    return True


def _rebuild_indexes() -> None:
    """Rebuild _TYPE_TO_NODE_ID and _CAPABILITY_TO_NODE_IDS from _REGISTRY."""
    global _TYPE_TO_NODE_ID, _CAPABILITY_TO_NODE_IDS
    _TYPE_TO_NODE_ID = {e.node_type: e.node_id for e in _REGISTRY.values()}
    _CAPABILITY_TO_NODE_IDS = {}
    for e in _REGISTRY.values():
        _CAPABILITY_TO_NODE_IDS.setdefault(e.capability, []).append(e.node_id)



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
    Rebuild the registry from the current .env (clears any runtime status overrides).
    Useful in tests and after sync-config calls.
    """
    global _REGISTRY, _TYPE_TO_NODE_ID, _CAPABILITY_TO_NODE_IDS
    from orchestrator.env_nodes import parse_node_configs
    from orchestrator.schemas import NodeType, InputType

    new: Dict[str, NodeRegistryEntry] = {}
    for c in parse_node_configs():
        new[c.node_id] = NodeRegistryEntry(
            node_id=c.node_id,
            node_name=c.name or c.node_id,
            capability="text",
            node_type=NodeType.TEXT,
            model="",
            endpoint=c.url,
            status="unknown",
            supported_input_types=[InputType.TEXT.value],
            priority=c.priority,
        )

    _REGISTRY.clear()
    _REGISTRY.update(new)
    _TYPE_TO_NODE_ID.clear()
    _TYPE_TO_NODE_ID.update({e.node_type: e.node_id for e in new.values()})
    _CAPABILITY_TO_NODE_IDS.clear()
    for e in new.values():
        _CAPABILITY_TO_NODE_IDS.setdefault(e.capability, []).append(e.node_id)
    logger.debug("Registry reset: %d node(s) from .env.", len(new))
