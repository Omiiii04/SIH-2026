"""
tests/test_discovery.py
───────────────────────
Tests for model and capability discovery.
"""
import pytest
from orchestrator.scheduler import discover_capabilities
from orchestrator.schemas import NodeRegistryEntry, NodeType

def _mock_entry(capability: str = "text"):
    return NodeRegistryEntry(
        node_id="NODE-1",
        node_name="Node 1",
        capability=capability,
        node_type=NodeType.TEXT,
        model="",
        endpoint="http://fake",
        status="online",
        supported_input_types=["text"],
        priority=1
    )

def test_discover_capabilities_defaults():
    # Any LLM inherently gets text capabilities
    caps = discover_capabilities(_mock_entry(), "unknown-model-7b")
    assert "text" in caps
    assert "text_generation" in caps

def test_discover_capabilities_vision():
    caps = discover_capabilities(_mock_entry(), "llava-v1.5-7b")
    assert "vision" in caps
    assert "ocr" in caps
    assert "image_reasoning" in caps

def test_discover_capabilities_coding():
    caps = discover_capabilities(_mock_entry(), "deepseek-coder-v2")
    assert "coding" in caps
    assert "code_review" in caps

def test_discover_capabilities_reasoning():
    caps = discover_capabilities(_mock_entry(), "qwen2-math-7b")
    assert "reasoning" in caps
    assert "math" in caps

def test_discover_capabilities_embedding():
    caps = discover_capabilities(_mock_entry(), "nomic-embed-text")
    assert "embeddings" in caps
    assert "retrieval" in caps

def test_legacy_capability_fallback():
    # If the model name doesn't contain a hint, it falls back to the legacy configured capability
    caps = discover_capabilities(_mock_entry(capability="vision"), "unknown-model")
    assert "vision" in caps
    assert "ocr" in caps

def test_legacy_capability_ignored_if_overridden_by_model():
    # Model name infers coding, legacy config was text. The node should support both (since default is text + inferred is coding)
    caps = discover_capabilities(_mock_entry(capability="text"), "starcoder-7b")
    assert "coding" in caps
    assert "text" in caps

def test_multiple_modalities_in_model():
    # "pixtral-math-coder" (hypothetical model with many keywords)
    caps = discover_capabilities(_mock_entry(), "pixtral-math-coder")
    assert "vision" in caps
    assert "math" in caps
    assert "coding" in caps
