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

from orchestrator.config import get_settings
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
    """Build the node registry from current settings."""
    cfg = get_settings()
    return {
        NodeType.TEXT: NodeDescriptor(
            node_type=NodeType.TEXT,
            base_url=cfg.node_text_url,
            description="General-purpose text generation and conversation.",
            capabilities=["chat", "summarisation", "translation", "Q&A"],
        ),
        NodeType.VISION: NodeDescriptor(
            node_type=NodeType.VISION,
            base_url=cfg.node_vision_url,
            description="Multimodal vision-language model for image understanding.",
            capabilities=["image captioning", "visual Q&A", "OCR"],
        ),
        NodeType.REASONING: NodeDescriptor(
            node_type=NodeType.REASONING,
            base_url=cfg.node_reasoning_url,
            description="Advanced reasoning and chain-of-thought model.",
            capabilities=["multi-step reasoning", "analysis", "logical inference"],
        ),
        NodeType.CODE: NodeDescriptor(
            node_type=NodeType.CODE,
            base_url=cfg.node_code_url,
            description="Code generation, debugging, and explanation.",
            capabilities=["code generation", "debugging", "code review", "documentation"],
        ),
        NodeType.RAG: NodeDescriptor(
            node_type=NodeType.RAG,
            base_url=cfg.node_rag_url,
            description="Retrieval-augmented generation over uploaded documents.",
            capabilities=["document Q&A", "semantic search", "knowledge retrieval"],
        ),
    }


# Module-level singleton (re-built on each import; lightweight in Phase 1)
REGISTRY: Dict[NodeType, NodeDescriptor] = build_registry()


def get_node(node_type: NodeType) -> NodeDescriptor:
    """Return the NodeDescriptor for *node_type*, or raise KeyError."""
    return REGISTRY[node_type]


def list_nodes() -> List[NodeDescriptor]:
    """Return all registered node descriptors."""
    return list(REGISTRY.values())
