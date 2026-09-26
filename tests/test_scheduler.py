"""
tests/test_scheduler.py
───────────────────────
Tests for capability-based scheduling logic.
"""
import pytest
from orchestrator.scheduler import select_best_candidates
from orchestrator.schemas import ClassificationResult, NodeRegistryEntry, NodeType, InputType, TaskType, Difficulty, ClassifierMethod
from orchestrator.monitor import NodeState

@pytest.fixture
def mock_registry():
    return {
        "NODE-TEXT": NodeRegistryEntry(node_id="NODE-TEXT", node_name="Text Node", capability="text", node_type=NodeType.TEXT, model="llama-3", endpoint="http://x", status="online", supported_input_types=["text"], priority=1),
        "NODE-VISION": NodeRegistryEntry(node_id="NODE-VISION", node_name="Vision Node", capability="text", node_type=NodeType.TEXT, model="llava-v1.5", endpoint="http://y", status="online", supported_input_types=["text"], priority=1),
        "NODE-CODE": NodeRegistryEntry(node_id="NODE-CODE", node_name="Code Node", capability="text", node_type=NodeType.TEXT, model="starcoder", endpoint="http://z", status="online", supported_input_types=["text"], priority=2),
    }

@pytest.fixture
def mock_states():
    # Only some nodes have states reported by the health monitor
    return {
        "NODE-TEXT": NodeState(node_id="NODE-TEXT", status="online", latency_ms=45.0, models_loaded=["llama-3"]),
        "NODE-VISION": NodeState(node_id="NODE-VISION", status="online", latency_ms=60.0, models_loaded=["llava-v1.5"]),
        "NODE-CODE": NodeState(node_id="NODE-CODE", status="online", latency_ms=30.0, models_loaded=["starcoder"]),
    }

def _create_classification(caps: list[str], mods: list[str]) -> ClassificationResult:
    return ClassificationResult(
        input_type=InputType.TEXT,
        node_type=NodeType.TEXT,
        task_type=TaskType.GENERAL_QA,
        difficulty=Difficulty.LOW,
        required_capability=",".join(caps),
        confidence=0.9,
        classifier_method=ClassifierMethod.RULE_KEYWORD,
        matched_rule="mock",
        required_capabilities=caps,
        input_modalities=mods,
    )

def test_select_best_candidates_vision(mock_registry, mock_states):
    from unittest.mock import patch
    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=mock_states):
        
        cls = _create_classification(["vision"], ["image"])
        candidates = select_best_candidates(cls)
        
        assert len(candidates) > 0
        best_node, best_model, score, reason = candidates[0]
        assert best_node.node_id == "NODE-VISION"
        assert best_model == "llava-v1.5"

def test_select_best_candidates_code_prioritizes_code_model(mock_registry, mock_states):
    from unittest.mock import patch
    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=mock_states):
        
        cls = _create_classification(["coding"], ["text"])
        candidates = select_best_candidates(cls)
        
        assert len(candidates) > 0
        best_node, best_model, score, reason = candidates[0]
        assert best_node.node_id == "NODE-CODE"
        assert best_model == "starcoder"

def test_select_best_candidates_skips_offline_nodes(mock_registry, mock_states):
    mock_states["NODE-TEXT"].status = "offline"
    
    from unittest.mock import patch
    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=mock_states):
        
        cls = _create_classification(["text"], ["text"])
        candidates = select_best_candidates(cls)
        
        assert len(candidates) > 0
        best_node = candidates[0][0]
        assert best_node.node_id != "NODE-TEXT" # Should pick something else since it's offline

def test_select_best_candidates_health_penalty(mock_registry, mock_states):
    # NODE-CODE has latency 30, but is degraded
    mock_states["NODE-CODE"].status = "degraded"
    
    from unittest.mock import patch
    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=mock_states):
        
        cls = _create_classification(["coding"], ["text"])
        candidates = select_best_candidates(cls)
        
        # Even though NODE-CODE has coding caps, the degraded penalty should push it down
        # Wait, if no other node has coding caps, cap_penalty is 5000 * 1 = 5000 for other nodes.
        # Health penalty is 10000.
        # Score for NODE-CODE = 30 + 10000 = 10030
        # Score for NODE-TEXT = 45 + 5000 = 5045 (missing coding cap)
        # So NODE-TEXT should win!
        best_node = candidates[0][0]
        assert best_node.node_id == "NODE-TEXT"

def test_select_best_candidates_skip_ids(mock_registry, mock_states):
    from unittest.mock import patch
    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value=mock_states):
        
        cls = _create_classification(["text"], ["text"])
        candidates = select_best_candidates(cls, skip_ids={"NODE-TEXT"})
        
        assert len(candidates) > 0
        best_node = candidates[0][0]
        assert best_node.node_id != "NODE-TEXT" # Should pick the next best text node
