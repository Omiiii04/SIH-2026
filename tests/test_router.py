"""
Tests for the request routing logic in orchestrator.router.
"""

import pytest

from orchestrator.router import route_request
from orchestrator.schemas import InferenceRequest, NodeType


def _req(prompt: str, node_type: NodeType | None = None) -> InferenceRequest:
    """Helper to build a minimal InferenceRequest."""
    return InferenceRequest(prompt=prompt, node_type=node_type)


# ── Explicit override tests ────────────────────────────────────────────────────

def test_explicit_node_type_overrides_heuristics() -> None:
    """If node_type is explicitly set, it must be returned unchanged."""
    req = _req("write a python function", node_type=NodeType.VISION)
    result = route_request(req)
    assert result == NodeType.VISION


# ── Keyword heuristic tests ────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "write a python function to sort a list",
    "debug this JavaScript code",
    "generate a bash script",
    "review my code",
])
def test_code_keywords_route_to_code(prompt: str) -> None:
    assert route_request(_req(prompt)) == NodeType.CODE


@pytest.mark.parametrize("prompt", [
    "describe this image",
    "what is in this photo?",
    "perform OCR on this picture",
])
def test_vision_keywords_route_to_vision(prompt: str) -> None:
    assert route_request(_req(prompt)) == NodeType.VISION


@pytest.mark.parametrize("prompt", [
    "reason step by step about climate change",
    "analyse the causes of World War I",
    "explain why the sky is blue",
])
def test_reasoning_keywords_route_to_reasoning(prompt: str) -> None:
    assert route_request(_req(prompt)) == NodeType.REASONING


@pytest.mark.parametrize("prompt", [
    "search the document for key findings",
    "based on the PDF, summarise section 3",
    "retrieve relevant passages from the knowledge base",
])
def test_rag_keywords_route_to_rag(prompt: str) -> None:
    assert route_request(_req(prompt)) == NodeType.RAG


@pytest.mark.parametrize("prompt", [
    "hello, how are you?",
    "tell me a joke",
    "write a poem about autumn",
    "what is the capital of France?",
])
def test_generic_prompts_route_to_text(prompt: str) -> None:
    """Prompts without specific keywords should fall back to text node."""
    assert route_request(_req(prompt)) == NodeType.TEXT
