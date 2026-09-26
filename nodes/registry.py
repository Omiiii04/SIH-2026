"""
Node registry for the SIH-2026 distributed inference system.

Provides a central lookup of all registered worker nodes so that
other modules (health checks, router, future load-balancer) have
a single source of truth.

Phase 1: static registry built from settings.
Phase 2: will support dynamic registration / de-registration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from orchestrator.schemas import NodeType


@dataclass
class NodeDescriptor:
    """Describes a single worker node."""

    node_type: NodeType
    base_url: str
    description: str
    capabilities: List[str] = field(default_factory=list)

    @property
    def health_url(self) -> str:
        """LM Studio model-list endpoint used for health probing."""
        return f"{self.base_url}/v1/models"

    @property
    def inference_url(self) -> str:
        """LM Studio chat-completions endpoint used for inference."""
        return f"{self.base_url}/v1/chat/completions"


def build_registry() -> Dict[NodeType, NodeDescriptor]:
    """
    Build the node registry dynamically from .env.

    Previously this function hard-coded exactly 5 nodes keyed by NodeType.
    Now it discovers all NODE_N_URL entries and assigns each the base TEXT
    type (since capabilities are determined per-model, not per-node-number).

    The NodeType key is kept as TEXT for all nodes — the scheduler uses
    model-level capability discovery, not this static type mapping.
    Kept for backward-compat callers that still use NodeType keys.
    """
    from orchestrator.env_nodes import parse_node_configs  # local to avoid circular
    registry: Dict[NodeType, NodeDescriptor] = {}

    # ponytail: build dynamically; fall back to TEXT for all since
    # real capabilities come from /v1/models, not node numbering.
    for c in parse_node_configs():
        # Use TEXT as default key — unique per node via description
        # Existing callers that look up by NodeType.TEXT will get the
        # first configured node (backward-compat behaviour).
        node_type = NodeType.TEXT
        if c.node_id not in registry.values():  # avoid overwriting
            if node_type not in registry:
                registry[node_type] = NodeDescriptor(
                    node_type=node_type,
                    base_url=c.url,
                    description=f"Worker node {c.index} ({c.node_id})",
                    capabilities=["chat", "text_generation"],
                )
    return registry


# Module-level singleton (re-built on each import; lightweight in Phase 1)
REGISTRY: Dict[NodeType, NodeDescriptor] = build_registry()


def get_node(node_type: NodeType) -> NodeDescriptor:
    """
    Return the NodeDescriptor for *node_type*.

    Backward-compat: if the registry doesn't have a node for the exact
    NodeType (because the static TYPE→node mapping no longer exists),
    returns the first available node.  Raises KeyError only if the
    registry is completely empty.
    """
    if node_type in REGISTRY:
        return REGISTRY[node_type]
    if REGISTRY:
        # Fall back to first node — stub functions only use the URL anyway
        return next(iter(REGISTRY.values()))
    raise KeyError(
        f"No nodes registered. Check that NODE_N_URL entries exist in .env."
    )


def list_nodes() -> List[NodeDescriptor]:
    """Return all registered node descriptors."""
    return list(REGISTRY.values())
