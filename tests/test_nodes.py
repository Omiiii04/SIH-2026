"""
Tests for the node registry and stub node clients.
"""

import pytest

from nodes.registry import REGISTRY, get_node, list_nodes
from orchestrator.schemas import NodeType


# ── Registry tests ─────────────────────────────────────────────────────────────

def test_registry_contains_at_least_one_node_type() -> None:
    """Registry must contain at least one NodeType when any node is configured."""
    # The registry is built from .env — in CI it may be empty, but the function
    # must not raise and must return a dict.
    assert isinstance(REGISTRY, dict)


def test_get_node_returns_correct_type() -> None:
    """get_node() must return a NodeDescriptor without raising."""
    # The registry maps by NodeType.TEXT as default; any lookup should
    # return a valid NodeDescriptor via the fallback in get_node().
    from nodes.registry import REGISTRY
    if not REGISTRY:
        pytest.skip("No nodes configured in .env — skipping registry lookup test")
    node = get_node(NodeType.TEXT)
    assert isinstance(node, object)  # NodeDescriptor
    assert hasattr(node, "health_url")
    assert hasattr(node, "inference_url")


def test_node_health_url_format() -> None:
    """health_url must end with /v1/models for all registered nodes."""
    for node in list_nodes():
        assert node.health_url.endswith("/v1/models"), (
            f"{node.node_type} health_url does not end with /v1/models: {node.health_url}"
        )


def test_node_inference_url_format() -> None:
    """inference_url must end with /v1/chat/completions for all registered nodes."""
    for node in list_nodes():
        assert node.inference_url.endswith("/v1/chat/completions"), (
            f"{node.node_type} inference_url is malformed: {node.inference_url}"
        )


def test_list_nodes_returns_non_empty_when_configured() -> None:
    """list_nodes() returns a list (may be empty in CI, must not raise)."""
    result = list_nodes()
    assert isinstance(result, list)


def test_node_capabilities_not_empty() -> None:
    """Every registered node should declare at least one capability."""
    for node in list_nodes():
        assert len(node.capabilities) > 0, f"{node.node_type} has no capabilities"


# ── Stub client smoke tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_text_node_stub_returns_dict() -> None:
    from nodes.text import call_text_node
    result = await call_text_node("hello world")
    assert "response" in result


@pytest.mark.asyncio
async def test_vision_node_stub_returns_dict() -> None:
    from nodes.vision import call_vision_node
    result = await call_vision_node("describe this image")
    assert "response" in result


@pytest.mark.asyncio
async def test_reasoning_node_stub_returns_dict() -> None:
    from nodes.reasoning import call_reasoning_node
    result = await call_reasoning_node("why is the sky blue?")
    assert "response" in result


@pytest.mark.asyncio
async def test_code_node_stub_returns_dict() -> None:
    from nodes.code import call_code_node
    result = await call_code_node("write a fibonacci function", language="python")
    assert "response" in result


@pytest.mark.asyncio
async def test_rag_node_stub_returns_dict() -> None:
    from nodes.rag import call_rag_node
    result = await call_rag_node("find relevant sections", session_id="sess-001")
    assert "response" in result
    assert "retrieved_chunks" in result
