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
    text_url: str,
    vision_url: str,
    reasoning_url: str,
    code_url: str,
    rag_url: str,
) -> Dict[str, NodeConfig]:
    """
    Build the ordered dict of all five node configs given their base URLs.
    """
    return {
        "NODE-TEXT": NodeConfig(
            node_id="NODE-TEXT",
            node_name="Text Generation Node",
            capability="text",
            node_type=NodeType.TEXT,
            model_name="llama-3-8b-instruct",          # update to match your LM Studio model
            endpoint=text_url,
            supported_input_types=["text"],
            laptop_id=1,
            description="General-purpose chat, summarisation, Q&A, and translation.",
            test_prompt="In exactly 5 words, what is your purpose?",
        ),
        "NODE-VISION": NodeConfig(
            node_id="NODE-VISION",
            node_name="Vision Language Node",
            capability="vision",
            node_type=NodeType.VISION,
            model_name="llava-1.5-7b",                  # update to match your LM Studio model
            endpoint=vision_url,
            supported_input_types=["image", "text_image"],
            laptop_id=2,
            description="Multimodal image understanding, OCR, and visual Q&A.",
            test_prompt="Describe what you can do in one sentence.",
        ),
        "NODE-REASONING": NodeConfig(
            node_id="NODE-REASONING",
            node_name="Reasoning Node",
            capability="reasoning",
            node_type=NodeType.REASONING,
            model_name="deepseek-r1-7b",                # update to match your LM Studio model
            endpoint=reasoning_url,
            supported_input_types=["text"],
            laptop_id=3,
            description="Step-by-step chain-of-thought reasoning and logical inference.",
            test_prompt="What is 2 + 2? Think step by step.",
        ),
        "NODE-CODE": NodeConfig(
            node_id="NODE-CODE",
            node_name="Code Generation Node",
            capability="coding",
            node_type=NodeType.CODE,
            model_name="codellama-7b-instruct",         # update to match your LM Studio model
            endpoint=code_url,
            supported_input_types=["text", "code"],
            laptop_id=4,
            description="Code generation, debugging, review, and documentation.",
            test_prompt="Write a Python one-liner to reverse a string.",
        ),
        "NODE-RAG": NodeConfig(
            node_id="NODE-RAG",
            node_name="RAG / Embedding Node",
            capability="embedding/retrieval",
            node_type=NodeType.RAG,
            model_name="nomic-embed-text",              # update to match your LM Studio model
            endpoint=rag_url,
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
        text_url=cfg.node_text_url,
        vision_url=cfg.node_vision_url,
        reasoning_url=cfg.node_reasoning_url,
        code_url=cfg.node_code_url,
        rag_url=cfg.node_rag_url,
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
