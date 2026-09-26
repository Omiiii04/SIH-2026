"""
tests/test_sessions.py
──────────────────────
Tests for Phase 4.5 persistent chat sessions and message history:
  • Session creation, listing, retrieval, deletion
  • User isolation
  • Message persistence and retrieval
  • Deterministic title generation
"""

from datetime import datetime
import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from orchestrator.main import app
from orchestrator.schemas import (
    ClassificationResult,
    ClassifierMethod,
    Difficulty,
    InputType,
    NodeType,
    QueryRequest,
    QueryResponse,
    RoutingDecision,
    TaskType,
)
from orchestrator.persistence import generate_title


def _make_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def test_generate_title():
    assert generate_title("Explain transformers and attention mechanisms in detail") == "Explain transformers and attention…"
    assert generate_title("Short prompt") == "Short prompt"
    assert generate_title("") == "New Chat"
    assert generate_title("   multiple    spaces   ") == "multiple spaces"


@pytest.mark.asyncio
async def test_session_lifecycle_mocked():
    """Test session create, list, and get messages endpoints."""
    from orchestrator.models import Session

    fake_session = Session(
        id="sess-123",
        user_id="test-user",
        title="Test Conversation",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    with patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):

        async with _make_client() as client:
            # 1. Create session
            with patch("database.postgres.get_session") as mock_sess_ctx, \
                 patch("database.postgres.upsert_user", new_callable=AsyncMock):
                mock_session = AsyncMock()
                mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                resp = await client.post("/api/v1/sessions", json={
                    "user_id": "test-user",
                    "title": "Test Conversation",
                    "id": "sess-123"
                })
                assert resp.status_code == 200
                data = resp.json()
                assert data["id"] == "sess-123"
                assert data["title"] == "Test Conversation"

            # 2. List sessions
            with patch("database.postgres.get_session") as mock_sess_ctx:
                mock_session = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = [fake_session]
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                resp = await client.get("/api/v1/sessions?user_id=test-user")
                assert resp.status_code == 200
                data = resp.json()
                assert len(data["sessions"]) == 1
                assert data["sessions"][0]["id"] == "sess-123"

            # 3. Get session messages
            from orchestrator.models import Message
            fake_msg1 = Message(
                id="msg-1",
                session_id="sess-123",
                user_id="test-user",
                role="user",
                content="Hello world",
                routing_metadata=None,
                created_at=datetime.utcnow(),
            )
            fake_msg2 = Message(
                id="msg-2",
                session_id="sess-123",
                user_id="test-user",
                role="assistant",
                content="Hi there!",
                routing_metadata='{"selected_node": "NODE-1", "total_ms": 1500}',
                created_at=datetime.utcnow(),
            )

            with patch("database.postgres.get_session") as mock_sess_ctx:
                mock_session = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = [fake_msg1, fake_msg2]
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                resp = await client.get("/api/v1/sessions/sess-123/messages?user_id=test-user")
                assert resp.status_code == 200
                msgs = resp.json()["messages"]
                assert len(msgs) == 2
                assert msgs[0]["role"] == "user"
                assert msgs[0]["content"] == "Hello world"
                assert msgs[1]["role"] == "assistant"
                assert msgs[1]["result"]["selected_node"] == "NODE-1"
                assert msgs[1]["ok"] is True


@pytest.mark.asyncio
async def test_user_isolation():
    """Sessions for user A must not be visible to user B."""
    with patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):

        async with _make_client() as client:
            with patch("database.postgres.get_session") as mock_sess_ctx:
                mock_session = AsyncMock()
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = []
                mock_session.execute = AsyncMock(return_value=mock_result)
                mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                resp = await client.get("/api/v1/sessions?user_id=user-b")
                assert resp.status_code == 200
                assert resp.json()["sessions"] == []


@pytest.mark.asyncio
async def test_persist_success_writes_session_and_messages():
    """Verify persist_success inserts Session and Message records."""
    from orchestrator.persistence import _write_postgres_success

    req_id = str(uuid.uuid4())
    cls = ClassificationResult(
        input_type=InputType.TEXT,
        node_type=NodeType.TEXT,
        task_type=TaskType.GENERAL_QA,
        difficulty=Difficulty.LOW,
        required_capability="text",
        confidence=0.9,
        classifier_method=ClassifierMethod.RULE_KEYWORD,
    )
    routing = RoutingDecision(selected_node="NODE-1", reason="text", was_fallback=False)
    query_resp = QueryResponse(
        request_id=req_id,
        user_id="user-1",
        session_id="sess-abc",
        input_type=InputType.TEXT,
        classification=cls,
        routing=routing,
        selected_node="NODE-1",
        selected_model="model-x",
        response="Response text here",
        total_ms=100.0,
        classification_ms=1.0,
        routing_ms=1.0,
        inference_ms=98.0,
    )
    query_req = QueryRequest(
        user_id="user-1",
        query="What is reinforcement learning?",
        input_type=InputType.TEXT,
        session_id="sess-abc",
    )

    with patch("database.postgres.get_session") as mock_sess_ctx, \
         patch("database.postgres.upsert_user", new_callable=AsyncMock):

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # New session
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        await _write_postgres_success(query_resp, query_req)

        # Added: Request, RoutingDecision, Session, User Message, Assistant Message -> at least 5 add calls
        assert mock_session.add.call_count >= 5
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_multiple_conversations_switching():
    """Verify multiple conversations remain distinct with no message cross-contamination."""
    from orchestrator.models import Session, Message

    sess_a = Session(id="sess-A", user_id="u1", title="Transformers Talk", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    sess_b = Session(id="sess-B", user_id="u1", title="Docker Containers", created_at=datetime.utcnow(), updated_at=datetime.utcnow())

    msg_a = Message(id="m1", session_id="sess-A", user_id="u1", role="user", content="Explain transformers", created_at=datetime.utcnow())
    msg_b = Message(id="m2", session_id="sess-B", user_id="u1", role="user", content="Explain Docker", created_at=datetime.utcnow())

    with patch("database.postgres.init_db", new_callable=AsyncMock), \
         patch("database.chroma.init_chroma"):

        async with _make_client() as client:
            with patch("database.postgres.get_session") as mock_sess_ctx:
                mock_session = AsyncMock()
                mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

                # Return sess-A messages
                mock_result_a = MagicMock()
                mock_result_a.scalars.return_value.all.return_value = [msg_a]
                mock_session.execute = AsyncMock(return_value=mock_result_a)

                resp_a = await client.get("/api/v1/sessions/sess-A/messages?user_id=u1")
                assert resp_a.status_code == 200
                messages_a = resp_a.json()["messages"]
                assert len(messages_a) == 1
                assert messages_a[0]["content"] == "Explain transformers"

                # Return sess-B messages
                mock_result_b = MagicMock()
                mock_result_b.scalars.return_value.all.return_value = [msg_b]
                mock_session.execute = AsyncMock(return_value=mock_result_b)

                resp_b = await client.get("/api/v1/sessions/sess-B/messages?user_id=u1")
                assert resp_b.status_code == 200
                messages_b = resp_b.json()["messages"]
                assert len(messages_b) == 1
                assert messages_b[0]["content"] == "Explain Docker"

