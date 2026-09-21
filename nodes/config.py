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
# Node Definitions
# ─────────────────────────────────────────────────────────────────────────────
# Endpoints are injected at runtime from settings (→ .env).
# This function is called by build_node_configs() below.

def _make_node_configs(
    node_1_url: str,
    node_2_url: str,
    node_3_url: str,
    node_4_url: str,
    node_5_url: str,
) -> Dict[str, NodeConfig]:
    """
    Build the ordered dict of all five node configs given their base URLs.
    """
    return {
        "NODE-1": NodeConfig(
            node_id="NODE-1",
            node_name="Node 1 (Orchestrator)",
            capability="text",
            node_type=NodeType.TEXT,
            model_name="",   # discovered live from GET /v1/models at health-probe time
            endpoint=node_1_url,
            supported_input_types=["text"],
            laptop_id=1,
            description="General-purpose chat, summarisation, Q&A, and translation.",
            test_prompt="In exactly 5 words, what is your purpose?",
        ),
        "NODE-2": NodeConfig(
            node_id="NODE-2",
            node_name="Node 2",
            capability="vision",
            node_type=NodeType.VISION,
            model_name="",   # discovered live from GET /v1/models at health-probe time
            endpoint=node_2_url,
            supported_input_types=["image", "text_image"],
            laptop_id=2,
            description="Multimodal image understanding, OCR, and visual Q&A.",
            test_prompt="Describe what you can do in one sentence.",
        ),
        "NODE-3": NodeConfig(
            node_id="NODE-3",
            node_name="Node 3",
            capability="reasoning",
            node_type=NodeType.REASONING,
            model_name="",   # discovered live from GET /v1/models at health-probe time
            endpoint=node_3_url,
            supported_input_types=["text"],
            laptop_id=3,
            description="Step-by-step chain-of-thought reasoning and logical inference.",
            test_prompt="What is 2 + 2? Think step by step.",
        ),
        "NODE-4": NodeConfig(
            node_id="NODE-4",
            node_name="Node 4",
            capability="coding",
            node_type=NodeType.CODE,
            model_name="",   # discovered live from GET /v1/models at health-probe time
            endpoint=node_4_url,
            supported_input_types=["text", "code"],
            laptop_id=4,
            description="Code generation, debugging, review, and documentation.",
            test_prompt="Write a Python one-liner to reverse a string.",
        ),
        "NODE-5": NodeConfig(
            node_id="NODE-5",
            node_name="Node 5",
            capability="embedding/retrieval",
            node_type=NodeType.RAG,
            model_name="",   # discovered live from GET /v1/models at health-probe time
            endpoint=node_5_url,
            supported_input_types=["text"],
            laptop_id=5,
            description="Retrieval-augmented generation over uploaded documents.",
            test_prompt="Summarise what retrieval-augmented generation means.",
        ),
    }


def build_node_configs() -> Dict[str, NodeConfig]:
    """
    Build node configs using URLs from the application settings (→ .env).
    Call this at module init time.
    """
    from orchestrator.config import get_settings  # local import to avoid circular deps
    cfg = get_settings()
    return _make_node_configs(
        node_1_url=cfg.node_1_url,
        node_2_url=cfg.node_2_url,
        node_3_url=cfg.node_3_url,
        node_4_url=cfg.node_4_url,
        node_5_url=cfg.node_5_url,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level registry (populated on first import)
# ─────────────────────────────────────────────────────────────────────────────
NODE_CONFIGS: Dict[str, NodeConfig] = build_node_configs()


def get_node_config(node_id: str) -> NodeConfig:
    """Return a NodeConfig by its node_id string (e.g. 'NODE-TEXT')."""
    return NODE_CONFIGS[node_id]


def list_node_configs() -> List[NodeConfig]:
    """Return all node configs in laptop order (Laptop 1 → 5)."""
    return sorted(NODE_CONFIGS.values(), key=lambda n: n.laptop_id)
