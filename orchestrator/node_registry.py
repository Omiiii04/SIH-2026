"""
orchestrator/node_registry.py
──────────────────────────────
Phase 2 Node Registry — single source of truth for all worker nodes.

Each entry carries:
  node_id, node_name, capability, node_type, model, endpoint,
  supported_input_types, priority

Priority: lower integer = higher priority. Used for future load-balancing.
All values are sourced from settings (→ .env) so no secrets are hardcoded.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from orchestrator.config import get_settings
from orchestrator.schemas import InputType, NodeRegistryEntry, NodeType

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Registry definition
# ─────────────────────────────────────────────────────────────────────────────

def _build_registry() -> Dict[str, NodeRegistryEntry]:
    """
    Build the node registry from current application settings.
    Called once at module import time.
    """
    cfg = get_settings()

    entries = [
        NodeRegistryEntry(
            node_id="NODE-TEXT",
            node_name="Text Generation Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="google/gemma-4-e4b",           # update per actual LM Studio model
            endpoint=cfg.node_text_url,
            status=_status(cfg.node_text_url),
            supported_input_types=[InputType.TEXT.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-VISION",
            node_name="Vision Language Node",
            capability="vision",
            node_type=NodeType.VISION,
            model="llava-1.5-7b",
            endpoint=cfg.node_vision_url,
            status=_status(cfg.node_vision_url),
            supported_input_types=[InputType.IMAGE.value, InputType.TEXT.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-REASONING",
            node_name="Reasoning Node",
            capability="reasoning",
            node_type=NodeType.REASONING,
            model="deepseek-r1-7b",
            endpoint=cfg.node_reasoning_url,
            status=_status(cfg.node_reasoning_url),
            supported_input_types=[InputType.TEXT.value, InputType.REASONING.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-CODE",
            node_name="Code Generation Node",
            capability="coding",
            node_type=NodeType.CODE,
            model="codellama-7b-instruct",
            endpoint=cfg.node_code_url,
            status=_status(cfg.node_code_url),
            supported_input_types=[InputType.TEXT.value, InputType.CODE.value],
            priority=1,
        ),
        NodeRegistryEntry(
            node_id="NODE-RAG",
            node_name="RAG / Embedding Node",
            capability="embedding/retrieval",
            node_type=NodeType.RAG,
            model="nomic-embed-text",
            endpoint=cfg.node_rag_url,
            status=_status(cfg.node_rag_url),
            supported_input_types=[InputType.TEXT.value, InputType.RETRIEVAL.value],
            priority=1,
        ),
    ]

    return {e.node_id: e for e in entries}


def _status(endpoint: str) -> str:
    """Static status: 'not_configured' if endpoint is blank, else 'unknown'."""
    return "not_configured" if not endpoint.strip() else "unknown"


# Module-level singleton
_REGISTRY: Dict[str, NodeRegistryEntry] = _build_registry()

# NodeType → node_id mapping for fast lookup during routing
_TYPE_TO_NODE_ID: Dict[NodeType, str] = {
    e.node_type: e.node_id for e in _REGISTRY.values()
}


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
    """Return the primary NodeRegistryEntry for a given NodeType, or None."""
    node_id = _TYPE_TO_NODE_ID.get(node_type)
    return _REGISTRY.get(node_id) if node_id else None


def get_node_by_id(node_id: str) -> Optional[NodeRegistryEntry]:
    """Return the NodeRegistryEntry for a given node_id, or None."""
    return _REGISTRY.get(node_id)
