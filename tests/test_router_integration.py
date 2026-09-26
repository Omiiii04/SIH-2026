"""
tests/test_router_integration.py
────────────────────────────────
Integration tests for the router, removing fixed-node assumptions.
Replaces the old phase2 and phase3 routing logic tests.
"""
import pytest
from unittest.mock import AsyncMock, patch
import uuid
from httpx import ASGITransport, AsyncClient

from orchestrator.main import app
from orchestrator.schemas import NodeRegistryEntry, NodeType
from orchestrator.lm_client import LMResponse, LMClientError

def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

def _mock_candidates(mock_node_id="NODE-ANY", score=10.0):
    entry = NodeRegistryEntry(
        node_id=mock_node_id,
        node_name="Any Node",
        capability="text",
        node_type=NodeType.TEXT,
        model="llama-3",
        endpoint="http://any",
        status="online",
        supported_input_types=["text"],
        priority=1
    )
    return [(entry, "llama-3", score, "mock scheduler reason")]

@pytest.mark.asyncio
async def test_router_success_flow():
    with patch("orchestrator.router.classify", new_callable=AsyncMock) as mock_classify, \
         patch("orchestrator.scheduler.select_best_candidates", return_value=_mock_candidates()) as mock_scheduler, \
         patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call, \
         patch("orchestrator.persistence.persist_success", new_callable=AsyncMock), \
         patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):
        
        from orchestrator.schemas import ClassificationResult, InputType, TaskType, Difficulty, ClassifierMethod
        mock_classify.return_value = ClassificationResult(
            input_type=InputType.TEXT,
            node_type=NodeType.TEXT,
            task_type=TaskType.GENERAL_QA,
            difficulty=Difficulty.LOW,
            required_capability="text",
            confidence=0.9,
            classifier_method=ClassifierMethod.RULE_KEYWORD,
            matched_rule="default"
        )
        
        mock_call.return_value = LMResponse(
            content="Hello world",
            model="llama-3",
            latency_ms=50.0,
            tokens_prompt=10,
            tokens_completion=20,
            tokens_total=30
        )
        
        async with _make_client() as client:
            resp = await client.post("/api/v1/query", json={
                "user_id": "u1",
                "query": "hello",
                "input_type": "text"
            })
            
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Hello world"
        assert data["selected_node"] == "NODE-ANY"
        assert data["routing"]["reason"] != ""

@pytest.mark.asyncio
async def test_router_retry_on_failure():
    # Setup candidates: NODE-A, then NODE-B
    entry_A = NodeRegistryEntry(node_id="NODE-A", node_name="A", capability="text", node_type=NodeType.TEXT, model="m", endpoint="http://a", status="online", supported_input_types=["text"], priority=1)
    entry_B = NodeRegistryEntry(node_id="NODE-B", node_name="B", capability="text", node_type=NodeType.TEXT, model="m", endpoint="http://b", status="online", supported_input_types=["text"], priority=1)
    
    # First call to scheduler returns NODE-A. Second call returns NODE-B.
    scheduler_side_effect = [
        [(entry_A, "m", 10.0, "reason A")],
        [(entry_B, "m", 10.0, "reason B")]
    ]
    
    # call_node fails on first try, succeeds on second
    call_node_side_effect = [
        LMClientError("connection_error", "refused", 10.0),
        LMResponse(content="Success on retry", model="m", latency_ms=50.0, tokens_prompt=10, tokens_completion=20, tokens_total=30)
    ]
    
    with patch("orchestrator.router.classify", new_callable=AsyncMock) as mock_classify, \
         patch("orchestrator.scheduler.select_best_candidates", side_effect=scheduler_side_effect) as mock_scheduler, \
         patch("orchestrator.router.call_node", side_effect=call_node_side_effect, new_callable=AsyncMock) as mock_call, \
         patch("orchestrator.router.set_node_status") as mock_set_status, \
         patch("orchestrator.persistence.persist_success", new_callable=AsyncMock), \
         patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):
        
        from orchestrator.schemas import ClassificationResult, InputType, TaskType, Difficulty, ClassifierMethod
        mock_classify.return_value = ClassificationResult(
            input_type=InputType.TEXT,
            node_type=NodeType.TEXT,
            task_type=TaskType.GENERAL_QA,
            difficulty=Difficulty.LOW,
            required_capability="text",
            confidence=0.9,
            classifier_method=ClassifierMethod.RULE_KEYWORD,
            matched_rule="default"
        )
        
        async with _make_client() as client:
            resp = await client.post("/api/v1/query", json={"user_id": "u1", "query": "hello", "input_type": "text"})
            
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Success on retry"
        assert data["selected_node"] == "NODE-B"
        
        # Ensure NODE-A was marked offline
        mock_set_status.assert_called_with("NODE-A", "offline")

@pytest.mark.asyncio
async def test_router_exhausts_retries():
    entry_A = NodeRegistryEntry(node_id="NODE-A", node_name="A", capability="text", node_type=NodeType.TEXT, model="m", endpoint="http://a", status="online", supported_input_types=["text"], priority=1)
    
    # Scheduler always returns NODE-A
    scheduler_side_effect = [
        [(entry_A, "m", 10.0, "reason A")],
        [(entry_A, "m", 10.0, "reason A")],
        [(entry_A, "m", 10.0, "reason A")],
        [] # Exhausted
    ]
    
    with patch("orchestrator.router.classify", new_callable=AsyncMock) as mock_classify, \
         patch("orchestrator.scheduler.select_best_candidates", side_effect=scheduler_side_effect) as mock_scheduler, \
         patch("orchestrator.router.call_node", side_effect=LMClientError("connection_error", "refused", 10.0), new_callable=AsyncMock) as mock_call, \
         patch("orchestrator.router.set_node_status"), \
         patch("orchestrator.persistence.persist_failure", new_callable=AsyncMock), \
         patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):
        
        from orchestrator.schemas import ClassificationResult, InputType, TaskType, Difficulty, ClassifierMethod
        mock_classify.return_value = ClassificationResult(
            input_type=InputType.TEXT,
            node_type=NodeType.TEXT,
            task_type=TaskType.GENERAL_QA,
            difficulty=Difficulty.LOW,
            required_capability="text",
            confidence=0.9,
            classifier_method=ClassifierMethod.RULE_KEYWORD,
            matched_rule="default"
        )
        
        async with _make_client() as client:
            resp = await client.post("/api/v1/query", json={"user_id": "u1", "query": "hello", "input_type": "text"})
            
        # Router returns 503 with an error object when retries are exhausted
        assert resp.status_code == 503
        data = resp.json()
        assert "error_type" in data
        assert data["error_type"] == "connection_error"
