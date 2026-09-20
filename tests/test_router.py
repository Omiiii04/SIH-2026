"""
tests/test_router.py
─────────────────────
Unit tests for request classification / routing logic.

Phase 1 used a function called route_request(); Phase 2 replaced it with
the classify() function in orchestrator.classifier. These tests now cover
the same routing scenarios via the new classifier interface.
"""

import pytest

from orchestrator.classifier import classify
from orchestrator.schemas import InputType, NodeType


def _classify_text(prompt: str) -> NodeType:
    """Helper: classify a plain-text prompt and return the target NodeType."""
    return classify(prompt, InputType.TEXT).node_type


# ── Explicit input_type override tests ────────────────────────────────────────

def test_explicit_image_input_type_routes_to_vision() -> None:
    """If input_type=IMAGE, must route to VISION regardless of query text."""
    result = classify("write a python function to sort a list", InputType.IMAGE)
    assert result.node_type == NodeType.VISION


def test_explicit_code_input_type_routes_to_code() -> None:
    result = classify("explain the history of Rome", InputType.CODE)
    assert result.node_type == NodeType.CODE


def test_explicit_reasoning_input_type_routes_to_reasoning() -> None:
    result = classify("what is 2+2", InputType.REASONING)
    assert result.node_type == NodeType.REASONING


def test_explicit_retrieval_input_type_routes_to_rag() -> None:
    result = classify("hello world", InputType.RETRIEVAL)
    assert result.node_type == NodeType.RAG


# ── Keyword heuristic tests ────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt", [
    "write a python function to sort a list",
    "debug this JavaScript code",
    "generate a bash script",
    "review my code",
])
def test_code_keywords_route_to_code(prompt: str) -> None:
    assert _classify_text(prompt) == NodeType.CODE


@pytest.mark.parametrize("prompt", [
    "describe this image",
    "what is in this photo?",
    "perform OCR on this picture",
])
def test_vision_keywords_route_to_vision(prompt: str) -> None:
    assert _classify_text(prompt) == NodeType.VISION


@pytest.mark.parametrize("prompt", [
    "reason step by step about climate change",
    "analyse the causes of World War I",
    "explain why the sky is blue",
])
def test_reasoning_keywords_route_to_reasoning(prompt: str) -> None:
    assert _classify_text(prompt) == NodeType.REASONING


@pytest.mark.parametrize("prompt", [
    "search the document for key findings",
    "based on the pdf, summarise section 3",
    "retrieve relevant passages from the knowledge base",
])
def test_rag_keywords_route_to_rag(prompt: str) -> None:
    assert _classify_text(prompt) == NodeType.RAG


@pytest.mark.parametrize("prompt", [
    "hello, how are you?",
    "tell me a joke",
    "write a poem about autumn",
    "what is the capital of France?",
])
def test_generic_prompts_route_to_text(prompt: str) -> None:
    """Prompts without specific keywords should fall back to the TEXT node."""
    assert _classify_text(prompt) == NodeType.TEXT
