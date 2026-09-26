"""
Node configuration for the SIH-2026 distributed AI inference system.

This is the single authoritative definition of all five worker nodes.
Edit this file whenever a new laptop joins or changes its IP/model.

Each NodeConfig entry represents one physical laptop running LM Studio.
The `endpoint` is the LM Studio API server URL (OpenAI-compatible).
Leave `endpoint` as an empty string or omit from .env when the laptop
is not yet available — the tester will mark it OFFLINE gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from orchestrator.schemas import NodeType


# ─────────────────────────────────────────────────────────────────────────────
# Node Configuration Schema
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NodeConfig:
    """
    Full specification for a single AI worker node (one physical laptop).

    Attributes
    ----------
    node_id:               Short machine-readable ID, e.g. "NODE-TEXT"
    node_name:             Human-readable label shown in the UI / logs
    capability:            Primary role of this node
    node_type:             Enum key used by the orchestrator router
    model_name:            Name of the LM Studio model loaded on this laptop
    endpoint:              Base URL of the LM Studio API server
    supported_input_types: What kinds of input this node accepts
    laptop_id:             Physical laptop number (1–5)
    description:           One-line description for display/docs
    test_prompt:           A small prompt used for connectivity smoke-tests
    """

    node_id: str
    node_name: str
    capability: str
    node_type: NodeType
    model_name: str
    endpoint: str
    supported_input_types: List[str]
    laptop_id: int
    description: str
    test_prompt: str = "Say hello in exactly 5 words."

    # ── Derived URL helpers ───────────────────────────────────────────────────
    @property
    def models_url(self) -> str:
        """LM Studio GET /v1/models — lists loaded models."""
        return f"{self.endpoint}/v1/models"

    @property
    def chat_url(self) -> str:
        """LM Studio POST /v1/chat/completions — runs inference."""
        return f"{self.endpoint}/v1/chat/completions"

    @property
    def is_configured(self) -> bool:
        """True when an endpoint URL has been set (laptop is in use)."""
        return bool(self.endpoint and self.endpoint.strip())


# ─────────────────────────────────────────────────────────────────────────────
# Node Definitions — dynamic from .env
# ─────────────────────────────────────────────────────────────────────────────
# All NODE_N_URL entries from .env are discovered dynamically.
# Node capability is NOT derived from the node number (NODE-6 is not
# automatically "vision" or "code").  Capabilities are discovered from
# the model metadata returned by GET /v1/models.

def build_node_configs() -> Dict[str, NodeConfig]:
    """
    Build node configs from .env using parse_node_configs().

    The NODE-N identifier is deterministic from the env key index.
    Capability starts as "text" (the safe default); real capabilities
    are discovered per-model by the scheduler's discover_capabilities().

    Works with any number of nodes — NODE_1 through NODE_N, sparse
    indexes included.
    """
    from orchestrator.env_nodes import parse_node_configs  # local to avoid circular import
    result: Dict[str, NodeConfig] = {}
    for c in parse_node_configs():
        result[c.node_id] = NodeConfig(
            node_id=c.node_id,
            node_name=c.name or c.node_id,
            capability="text",          # base default — real caps from model metadata
            node_type=NodeType.TEXT,    # placeholder; scheduler uses model-level caps
            model_name="",             # filled in by health monitor
            endpoint=c.url,
            supported_input_types=["text"],
            laptop_id=c.index,
            description=f"Worker node {c.index} — capabilities discovered via /v1/models",
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Module-level registry (populated on first import)
# ─────────────────────────────────────────────────────────────────────────────
NODE_CONFIGS: Dict[str, NodeConfig] = build_node_configs()


def get_node_config(node_id: str) -> NodeConfig:
    """Return a NodeConfig by its node_id string (e.g. 'NODE-3')."""
    return NODE_CONFIGS[node_id]


def list_node_configs() -> List[NodeConfig]:
    """Return all node configs sorted by laptop_id (index)."""
    return sorted(NODE_CONFIGS.values(), key=lambda n: n.laptop_id)
