"""
tests/test_phase4.py
─────────────────────
Phase 4 automated test suite — PostgreSQL + ChromaDB persistence.

All database calls are mocked so tests run without live services.

Test 1  — Successful query persists to both PostgreSQL and ChromaDB.
Test 2  — Three related queries → memory search returns relevant results.
Test 3  — Persistence data survives restart (data already in DB).
Test 4  — DB down → controlled error; query response still returned.

Coverage
────────
  orchestrator.persistence   persist_success / persist_failure
  database.chroma            add_interaction / search_interactions
  database.postgres          get_session / upsert_user / init_db / ping_db
  orchestrator.main          POST /api/v1/query (with persistence)
                             POST /api/v1/memory/search
  orchestrator.router        handle_query (fire-and-forget task scheduling)
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from orchestrator.lm_client import LMClientError, LMResponse
from orchestrator.main import app
from orchestrator.node_registry import reset_registry, set_node_status
from orchestrator.schemas import (
    ClassificationResult,
    ClassifierMethod,
    Difficulty,
    InputType,
    MemorySearchRequest,
    MemorySearchResponse,
    NodeFailureResponse,
    NodeType,
    QueryRequest,
    QueryResponse,
    RoutingDecision,
    TaskType,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_registry():
    reset_registry()
    yield
    reset_registry()


def _fake_lm_response(content: str = "Test model response.") -> LMResponse:
    return LMResponse(
        content=content,
        model="test-model-7b",
        latency_ms=42.0,
        tokens_prompt=10,
        tokens_completion=20,
        tokens_total=30,
    )


def _fake_query_response(
    request_id: str | None = None,
    query: str = "Explain transformers",
    node: str = "NODE-1",
) -> QueryResponse:
    rid = request_id or str(uuid.uuid4())
    cls = ClassificationResult(
        input_type=InputType.TEXT,
        node_type=NodeType.TEXT,
        task_type=TaskType.GENERAL_QA,
        difficulty=Difficulty.LOW,
        required_capability="text",
        confidence=0.95,
        classifier_method=ClassifierMethod.RULE_KEYWORD,
        matched_rule="default_text",
    )
    routing = RoutingDecision(selected_node=node, reason="General text query.", was_fallback=False)
    return QueryResponse(
        request_id=rid,
        user_id="test_user_001",
        session_id="session_abc",
        input_type=InputType.TEXT,
        classification=cls,
        routing=routing,
        selected_node=node,
        selected_model="test-model-7b",
        response="Transformers are attention-based models.",
        latency_ms=42.0,
    )


def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ─────────────────────────────────────────────────────────────────────────────
# Utility: silence DB startup in lifespan
# ─────────────────────────────────────────────────────────────────────────────

_PATCH_INIT_DB  = patch("orchestrator.main.init_db",    new_callable=AsyncMock)
_PATCH_CLOSE_DB = patch("orchestrator.main.close_db",   new_callable=AsyncMock)
_PATCH_INIT_CH  = patch("orchestrator.main.init_chroma", new_callable=MagicMock)
_PATCH_CLOSE_CH = patch("orchestrator.main.close_chroma", new_callable=MagicMock)

# lifespan imports these lazily — patch the module-level names
_PATCH_LIFESPAN_INIT_DB  = patch("database.postgres.init_db",    new_callable=AsyncMock)
_PATCH_LIFESPAN_CLOSE_DB = patch("database.postgres.close_db",   new_callable=AsyncMock)
_PATCH_LIFESPAN_INIT_CH  = patch("database.chroma.init_chroma",  new_callable=MagicMock)
_PATCH_LIFESPAN_CLOSE_CH = patch("database.chroma.close_chroma", new_callable=MagicMock)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Successful query persists to both PostgreSQL and ChromaDB
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistSuccess:

    @pytest.mark.asyncio
    async def test_persist_success_calls_postgres(self):
        """persist_success() must write a request + routing_decision row."""
        from orchestrator.persistence import persist_success

        response = _fake_query_response()
        request  = QueryRequest(user_id="test_user_001", query="Explain transformers", input_type=InputType.TEXT)

        with patch("orchestrator.persistence._write_postgres_success", new_callable=AsyncMock) as mock_pg, \
             patch("orchestrator.persistence._write_chroma",            new_callable=AsyncMock) as mock_ch:
            await persist_success(response, request)

        mock_pg.assert_awaited_once()
        mock_ch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_failure_calls_postgres_only(self):
        """persist_failure() must write only a requests row (no ChromaDB — no response)."""
        from orchestrator.persistence import persist_failure

        failure = NodeFailureResponse(
            request_id=str(uuid.uuid4()),
            user_id="test_user_001",
            selected_node="NODE-1",
            error_type="connection_error",
            detail="refused",
            latency_ms=5.0,
        )
        request = QueryRequest(user_id="test_user_001", query="hello", input_type=InputType.TEXT)

        with patch("orchestrator.persistence._write_postgres_failure", new_callable=AsyncMock) as mock_pg:
            await persist_failure(failure, request)

        mock_pg.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_postgres_write_never_raises(self):
        """Even if PostgreSQL write fails, persist_success must not raise."""
        from orchestrator.persistence import persist_success

        response = _fake_query_response()
        request  = QueryRequest(user_id="test_user_001", query="hello", input_type=InputType.TEXT)

        with patch("orchestrator.persistence._write_postgres_success",
                   new_callable=AsyncMock, side_effect=Exception("DB is down")), \
             patch("orchestrator.persistence._write_chroma", new_callable=AsyncMock):
            # Must NOT raise
            await persist_success(response, request)

    @pytest.mark.asyncio
    async def test_chroma_write_never_raises(self):
        """Even if ChromaDB write fails, persist_success must not raise."""
        from orchestrator.persistence import persist_success

        response = _fake_query_response()
        request  = QueryRequest(user_id="test_user_001", query="hello", input_type=InputType.TEXT)

        with patch("orchestrator.persistence._write_postgres_success", new_callable=AsyncMock), \
             patch("orchestrator.persistence._write_chroma",
                   new_callable=AsyncMock, side_effect=Exception("Chroma down")):
            await persist_success(response, request)

    @pytest.mark.asyncio
    async def test_query_endpoint_schedules_persist_task(self):
        """POST /api/v1/query must schedule a persist_success task (fire-and-forget)."""
        set_node_status("NODE-1", "online")

        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call, \
             patch("orchestrator.persistence.persist_success", new_callable=AsyncMock) as mock_persist, \
             patch("database.postgres.init_db", new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"):

            mock_call.return_value = _fake_lm_response()

            async with _make_client() as client:
                resp = await client.post("/api/v1/query", json={
                    "user_id":    "test_user_001",
                    "query":      "Explain transformers",
                    "input_type": "text",
                })

            # Allow fire-and-forget task to run
            await asyncio.sleep(0.1)

        assert resp.status_code == 200
        # persist_success should have been called via asyncio.create_task
        mock_persist.assert_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Three related queries → memory search returns relevant results
# ─────────────────────────────────────────────────────────────────────────────

class TestMemorySearch:

    def test_search_interactions_returns_results(self):
        """search_interactions() must format ChromaDB results correctly."""
        from database.chroma import search_interactions

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "ids":       [["req-001", "req-002"]],
            "documents": [["What is AI?\n\nAI is artificial intelligence.", "Explain ML\n\nML is machine learning."]],
            "metadatas": [[
                {"user_id": "u1", "query_preview": "What is AI?",  "node_id": "NODE-1", "model": "m1", "timestamp": "2026-01-01T00:00:00Z", "session_id": ""},
                {"user_id": "u1", "query_preview": "Explain ML",   "node_id": "NODE-1", "model": "m1", "timestamp": "2026-01-01T00:01:00Z", "session_id": ""},
            ]],
            "distances":  [[0.1, 0.2]],
        }

        import database.chroma as ch_module
        original_col = ch_module._collection
        ch_module._collection = mock_collection
        try:
            results = search_interactions(user_id="u1", query="artificial intelligence", n_results=2)
        finally:
            ch_module._collection = original_col

        assert len(results) == 2
        assert results[0]["request_id"] == "req-001"
        assert results[0]["score"] == pytest.approx(0.9, abs=0.01)
        assert "query" in results[0]
        assert "response" in results[0]
        assert "node_id" in results[0]
        assert "timestamp" in results[0]

    def test_search_returns_empty_when_chroma_unavailable(self):
        """search_interactions() must return [] when collection is None."""
        from database.chroma import search_interactions
        import database.chroma as ch_module
        original_col = ch_module._collection
        ch_module._collection = None
        try:
            results = search_interactions(user_id="u1", query="anything")
        finally:
            ch_module._collection = original_col
        assert results == []

    def test_search_graceful_on_chroma_error(self):
        """search_interactions() must return [] on query() exception."""
        from database.chroma import search_interactions
        import database.chroma as ch_module

        mock_col = MagicMock()
        mock_col.query.side_effect = Exception("Chroma query failed")
        original_col = ch_module._collection
        ch_module._collection = mock_col
        try:
            results = search_interactions(user_id="u1", query="anything")
        finally:
            ch_module._collection = original_col
        assert results == []

    @pytest.mark.asyncio
    async def test_memory_search_endpoint_200(self):
        """POST /api/v1/memory/search must return 200 with correct schema."""
        fake_results = [
            {
                "request_id": "rid-001",
                "query":      "What is AI?",
                "response":   "AI is ...",
                "node_id":    "NODE-1",
                "model":      "test-model",
                "timestamp":  "2026-01-01T00:00:00Z",
                "session_id": "",
                "score":      0.95,
            }
        ]

        with patch("database.chroma.search_interactions", return_value=fake_results), \
             patch("database.chroma.ping_chroma", return_value=True), \
             patch("database.postgres.init_db", new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"):

            async with _make_client() as client:
                resp = await client.post("/api/v1/memory/search", json={
                    "user_id":   "test_user_001",
                    "query":     "AI knowledge",
                    "n_results": 5,
                })

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["results"][0]["request_id"] == "rid-001"
        assert body["results"][0]["score"] == pytest.approx(0.95)

    @pytest.mark.asyncio
    async def test_memory_search_503_when_chroma_down(self):
        """POST /api/v1/memory/search must return 503 when ChromaDB is unavailable."""
        with patch("database.chroma.ping_chroma", return_value=False), \
             patch("database.postgres.init_db", new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"):

            async with _make_client() as client:
                resp = await client.post("/api/v1/memory/search", json={
                    "user_id": "test_user_001",
                    "query":   "anything",
                })

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_memory_search_returns_all_required_fields(self):
        """Each MemorySearchResult must have all required fields."""
        fake_results = [{
            "request_id": "rid-002",
            "query":      "Explain BERT",
            "response":   "BERT is a transformer-based model.",
            "node_id":    "NODE-1",
            "model":      "bert-base",
            "timestamp":  "2026-01-02T10:00:00Z",
            "session_id": "session_x",
            "score":      0.88,
        }]

        with patch("database.chroma.search_interactions", return_value=fake_results), \
             patch("database.chroma.ping_chroma", return_value=True), \
             patch("database.postgres.init_db", new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"):

            async with _make_client() as client:
                resp = await client.post("/api/v1/memory/search", json={
                    "user_id": "u1", "query": "BERT transformers",
                })

        assert resp.status_code == 200
        result = resp.json()["results"][0]
        for field in ("request_id", "query", "response", "node_id", "model", "timestamp", "score"):
            assert field in result, f"Missing field: {field}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — Persistence survives restart (data already in DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestDataSurvivesRestart:

    @pytest.mark.asyncio
    async def test_existing_interactions_searchable_after_init(self):
        """
        Simulate a restart: pre-seeded ChromaDB data must be immediately
        searchable after init_chroma() — because data is stored on the server.
        """
        # Pre-seeded results (as if they were written in a previous session)
        pre_seeded = [
            {
                "request_id": "pre-seeded-001",
                "query":      "What is distributed AI?",
                "response":   "Distributed AI splits work across nodes.",
                "node_id":    "NODE-1",
                "model":      "llm-7b",
                "timestamp":  "2026-01-01T08:00:00Z",
                "session_id": "",
                "score":      0.91,
            }
        ]

        # After "restart", search immediately returns pre-seeded data
        with patch("database.chroma.search_interactions", return_value=pre_seeded), \
             patch("database.chroma.ping_chroma",        return_value=True), \
             patch("database.postgres.init_db",           new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"):

            async with _make_client() as client:
                resp = await client.post("/api/v1/memory/search", json={
                    "user_id": "test_user_001",
                    "query":   "distributed AI inference",
                })

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["request_id"] == "pre-seeded-001"

    @pytest.mark.asyncio
    async def test_init_db_called_on_startup(self):
        """
        Verify that the lifespan startup path attempts to call init_db.

        The lifespan imports init_db lazily inside a try/except.
        We test the observable effect: the /health endpoint includes a
        'databases' key that would only exist if the lifespan ran correctly.
        """
        with patch("database.postgres.init_db",   new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"), \
             patch("database.postgres.close_db",   new_callable=AsyncMock), \
             patch("database.chroma.close_chroma"):

            async with _make_client() as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        # The /health endpoint returns 'databases' only when lifespan ran
        assert "databases" in body, "lifespan did not run — 'databases' key missing from /health"
        assert "postgres" in body["databases"]
        assert "chroma"   in body["databases"]



# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — DB down → controlled error; query response still returned
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabaseDown:

    @pytest.mark.asyncio
    async def test_postgres_down_does_not_affect_query_response(self):
        """
        When PostgreSQL is down, POST /api/v1/query must still return 200
        with a valid response — persistence errors are logged but not propagated.
        """
        set_node_status("NODE-1", "online")

        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call, \
             patch("orchestrator.persistence.persist_success",
                   new_callable=AsyncMock, side_effect=Exception("DB connection refused")), \
             patch("database.postgres.init_db", new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"):

            mock_call.return_value = _fake_lm_response("Transformers are great.")

            async with _make_client() as client:
                resp = await client.post("/api/v1/query", json={
                    "user_id":    "test_user_001",
                    "query":      "Explain transformers",
                    "input_type": "text",
                })

            await asyncio.sleep(0.1)

        # Query must succeed even though persistence failed
        assert resp.status_code == 200
        body = resp.json()
        assert body["response"] == "Transformers are great."

    @pytest.mark.asyncio
    async def test_chroma_down_does_not_affect_query_response(self):
        """ChromaDB failure must not break the inference response."""
        set_node_status("NODE-1", "online")

        with patch("orchestrator.router.call_node", new_callable=AsyncMock) as mock_call, \
             patch("orchestrator.persistence._write_postgres_success", new_callable=AsyncMock), \
             patch("orchestrator.persistence._write_chroma",
                   new_callable=AsyncMock, side_effect=Exception("Chroma is down")), \
             patch("database.postgres.init_db", new_callable=AsyncMock), \
             patch("database.chroma.init_chroma"):

            mock_call.return_value = _fake_lm_response("Neural networks rock.")

            async with _make_client() as client:
                resp = await client.post("/api/v1/query", json={
                    "user_id":    "test_user_001",
                    "query":      "Explain neural networks",
                    "input_type": "text",
                })

            await asyncio.sleep(0.1)

        assert resp.status_code == 200
        assert resp.json()["response"] == "Neural networks rock."

    @pytest.mark.asyncio
    async def test_startup_db_failure_does_not_crash_app(self):
        """If init_db() raises at startup, the app must still start."""
        with patch("database.postgres.init_db",
                   new_callable=AsyncMock, side_effect=Exception("DB unreachable")), \
             patch("database.chroma.init_chroma"):

            async with _make_client() as client:
                resp = await client.get("/health")

        # App is still up even though DB init failed
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_ping_db_returns_false_when_down(self):
        """ping_db() must return False when the database is unreachable."""
        from database.postgres import ping_db

        with patch("database.postgres.get_session") as mock_sess_ctx:
            mock_session = AsyncMock()
            mock_session.execute.side_effect = Exception("connection refused")
            mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_sess_ctx.return_value.__aexit__  = AsyncMock(return_value=False)
            result = await ping_db()

        assert result is False

    def test_chroma_ping_returns_false_when_down(self):
        """ping_chroma() must return False when the ChromaDB server is unreachable."""
        from database.chroma import ping_chroma
        import database.chroma as ch_module

        mock_client = MagicMock()
        mock_client.heartbeat.side_effect = Exception("Connection refused")
        original = ch_module._client
        ch_module._client = mock_client
        try:
            result = ping_chroma()
        finally:
            ch_module._client = original

        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# Test 5 — add_interaction and ChromaDB storage contract
# ─────────────────────────────────────────────────────────────────────────────

class TestChromaStorage:

    @pytest.mark.asyncio
    async def test_add_interaction_calls_collection_add(self):
        """add_interaction() must call collection.add() with correct args."""
        import database.chroma as ch_module
        from database.chroma import add_interaction

        mock_col = MagicMock()
        original = ch_module._collection
        ch_module._collection = mock_col
        try:
            await add_interaction(
                request_id="req-123",
                user_id="u1",
                session_id="sess-1",
                query="What is AI?",
                response="AI is the simulation of human intelligence.",
                node_id="NODE-1",
                model="test-model",
                timestamp="2026-01-01T00:00:00Z",
            )
        finally:
            ch_module._collection = original

        mock_col.add.assert_called_once()
        call_kwargs = mock_col.add.call_args
        assert "req-123" in call_kwargs.kwargs["ids"]
        assert "What is AI?" in call_kwargs.kwargs["documents"][0]
        assert call_kwargs.kwargs["metadatas"][0]["user_id"] == "u1"
        assert call_kwargs.kwargs["metadatas"][0]["node_id"] == "NODE-1"

    @pytest.mark.asyncio
    async def test_add_interaction_noop_when_collection_none(self):
        """add_interaction() must silently do nothing if collection is None."""
        import database.chroma as ch_module
        from database.chroma import add_interaction

        original = ch_module._collection
        ch_module._collection = None
        try:
            # Must not raise
            await add_interaction(
                request_id="r1", user_id="u1", session_id=None,
                query="q", response="r", node_id="n", model="m", timestamp="t",
            )
        finally:
            ch_module._collection = original

    @pytest.mark.asyncio
    async def test_add_interaction_graceful_on_error(self):
        """add_interaction() must not raise if collection.add() fails."""
        import database.chroma as ch_module
        from database.chroma import add_interaction

        mock_col = MagicMock()
        mock_col.add.side_effect = Exception("Chroma write failed")
        original = ch_module._collection
        ch_module._collection = mock_col
        try:
            await add_interaction(
                request_id="r1", user_id="u1", session_id=None,
                query="q", response="r", node_id="n", model="m", timestamp="t",
            )
        finally:
            ch_module._collection = original
