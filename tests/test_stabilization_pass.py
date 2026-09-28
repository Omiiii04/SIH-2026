"""
tests/test_stabilization_pass.py
Regression tests for SIH-2026 stabilization pass.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from orchestrator.main import app
from orchestrator.schemas import InputType, QueryRequest


@pytest.mark.asyncio
async def test_case_a_input_type_auto_normalizes_to_text():
    """Case A: input_type='auto' + text query -> accepted and normalized to text."""
    req = QueryRequest(user_id="test-user", query="hi", input_type="auto")
    assert req.input_type == InputType.TEXT

    req_none = QueryRequest(user_id="test-user", query="hi", input_type=None)
    assert req_none.input_type == InputType.TEXT

    req_empty = QueryRequest(user_id="test-user", query="hi", input_type="")
    assert req_empty.input_type == InputType.TEXT


@pytest.mark.asyncio
async def test_case_b_invalid_input_type_raises_422():
    """Case B: invalid random string for input_type raises 422, not silently converted."""
    with pytest.raises(ValueError):
        QueryRequest(user_id="test-user", query="hi", input_type="invalid_random_string")

    with pytest.raises(ValueError):
        QueryRequest(user_id="test-user", query="hi", input_type="imag")

    # Over HTTP API
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/query",
            json={"user_id": "test-user", "query": "hi", "input_type": "invalid_random_string"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body


@pytest.mark.asyncio
async def test_case_c_what_is_an_image_without_attachment_is_text():
    """Case C: 'What is an image?' with NO attachment -> text request, not vision."""
    from orchestrator.classifier import classify
    cls = await classify("What is an image?", InputType.TEXT, attachments=[])
    assert "image" not in cls.input_modalities
    assert cls.required_capability != "vision"
    assert "vision" not in cls.required_capabilities


@pytest.mark.asyncio
async def test_case_d_png_requires_vision_and_rejects_text_model():
    """Case D: 'What is in this image?' with actual PNG -> vision-required request, text model rejected."""
    import os
    from unittest.mock import patch, MagicMock
    from orchestrator.attachments import process_attachment_bytes, normalize_request, AttachmentKind
    from orchestrator.classifier import classify
    from orchestrator.scheduler import select_best_candidates
    from orchestrator.schemas import NodeRegistryEntry, NodeType

    png_path = os.path.join(os.path.dirname(__file__), "fixtures", "winter_internship_2026_2027_flyer.png")
    with open(png_path, "rb") as f:
        png_bytes = f.read()

    att = process_attachment_bytes("flyer.png", "image/png", png_bytes)
    assert att.kind == AttachmentKind.IMAGE
    assert att.has_visual_content is True

    modalities, required_caps = normalize_request("What is in this image?", [att])
    assert "image" in modalities
    assert "vision" in required_caps

    cls = await classify("What is in this image?", InputType.IMAGE, attachments=[att])
    assert "image" in cls.input_modalities
    assert cls.required_capability == "vision"

    # Verify scheduler candidate selection
    mock_registry = {
        "NODE-FAST-TEXT": NodeRegistryEntry(
            node_id="NODE-FAST-TEXT",
            node_name="Fast Text Node",
            capability="text",
            node_type=NodeType.TEXT,
            model="qwen-2.5-7b",
            endpoint="http://fast-text:1234",
            status="online",
            supported_input_types=["text"],
            priority=1,
        ),
        "NODE-VISION": NodeRegistryEntry(
            node_id="NODE-VISION",
            node_name="Vision Node",
            capability="vision",
            node_type=NodeType.VISION,
            model="gemma-3-4b-it",
            endpoint="http://vision-node:1234",
            status="online",
            supported_input_types=["text", "image"],
            priority=1,
        ),
    }

    with patch("orchestrator.scheduler.get_registry", return_value=mock_registry), \
         patch("orchestrator.scheduler.get_node_states", return_value={
             "NODE-FAST-TEXT": MagicMock(status="ONLINE", latency_ms=10.0, models_loaded=["qwen-2.5-7b"], models_metadata={}),
             "NODE-VISION": MagicMock(status="ONLINE", latency_ms=150.0, models_loaded=["gemma-3-4b-it"], models_metadata={
                 "gemma-3-4b-it": {"capability_source": "lmstudio_metadata", "capabilities": {"vision": True}}
             }),
         }):
        candidates = select_best_candidates(cls)
        # Fast text model must be eliminated BEFORE latency scoring
        node_ids = [c[0].node_id for c in candidates]
        assert "NODE-FAST-TEXT" not in node_ids
        assert "NODE-VISION" in node_ids
        assert candidates[0][0].node_id == "NODE-VISION"


@pytest.mark.asyncio
async def test_case_e_text_pdf_routes_to_document_text():
    """Case E: PDF with selectable text -> document/text path, does not require vision."""
    import pymupdf
    from orchestrator.attachments import inspect_and_process_pdf, normalize_request, AttachmentKind
    from orchestrator.classifier import classify

    # Generate a pure text PDF in-memory
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "This is a document with full selectable text describing distributed AI architectures.")
    pdf_bytes = doc.tobytes()
    doc.close()

    att = inspect_and_process_pdf(pdf_bytes, "sample_text.pdf")
    assert att.kind == AttachmentKind.PDF
    assert att.has_visual_content is False
    assert att.rendered_pages == []
    assert att.extracted_text is not None and "distributed AI architectures" in att.extracted_text

    modalities, required_caps = normalize_request("Summarize this document", [att])
    assert "document" in modalities
    assert "image" not in modalities
    assert "vision" not in required_caps

    cls = await classify("Summarize this document", InputType.TEXT, attachments=[att])
    assert "image" not in cls.input_modalities
    assert cls.required_capability != "vision"


@pytest.mark.asyncio
async def test_case_f_scanned_pdf_routes_to_vision():
    """Case F: Scanned/image PDF -> document + image/vision path, vision required."""
    import os
    from orchestrator.attachments import inspect_and_process_pdf, normalize_request, AttachmentKind
    from orchestrator.classifier import classify

    pdf_path = os.path.join(os.path.dirname(__file__), "fixtures", "winter_internship_2026_2027_flyer.pdf")
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    att = inspect_and_process_pdf(pdf_bytes, "flyer.pdf")
    assert att.kind == AttachmentKind.PDF
    # Flyer has raster images and minimal text -> visual PDF
    assert att.has_visual_content is True
    assert len(att.rendered_pages) > 0

    modalities, required_caps = normalize_request("Analyze this flyer", [att])
    assert "document" in modalities
    assert "image" in modalities
    assert "vision" in required_caps

    cls = await classify("Analyze this flyer", InputType.TEXT, attachments=[att])
    assert "image" in cls.input_modalities
    assert cls.required_capability == "vision"


@pytest.mark.asyncio
async def test_case_g_delete_one_chat_other_chats_remain():
    """Case G: delete one chat -> other chats remain intact."""
    from datetime import datetime
    from unittest.mock import patch, AsyncMock, MagicMock
    from orchestrator.models import Session

    sess_a = Session(id="sess-A", user_id="u1", title="Chat A", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    sess_b = Session(id="sess-B", user_id="u1", title="Chat B", created_at=datetime.utcnow(), updated_at=datetime.utcnow())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("database.postgres.get_session") as mock_sess_ctx:
            mock_session = AsyncMock()
            mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # When querying sess-B to delete
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sess_b
            mock_session.execute = AsyncMock(return_value=mock_result)

            resp = await client.delete("/api/v1/sessions/sess-B?user_id=u1")
            assert resp.status_code == 200
            assert resp.json()["deleted"] is True

            # Verify session.delete was called with sess_b, NOT sess_a
            mock_session.delete.assert_called_once_with(sess_b)
            mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_case_h_clear_all_chats_only_deletes_current_user():
    """Case H: clear all chats -> only current user's chats deleted, other users untouched."""
    from datetime import datetime
    from unittest.mock import patch, AsyncMock, MagicMock
    from orchestrator.models import Session

    sess_u1_1 = Session(id="sess-1", user_id="user-1", title="User 1 Chat 1", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    sess_u1_2 = Session(id="sess-2", user_id="user-1", title="User 1 Chat 2", created_at=datetime.utcnow(), updated_at=datetime.utcnow())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("database.postgres.get_session") as mock_sess_ctx:
            mock_session = AsyncMock()
            mock_sess_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_sess_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            # Query returns only user-1 sessions
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [sess_u1_1, sess_u1_2]
            mock_session.execute = AsyncMock(return_value=mock_result)

            resp = await client.delete("/api/v1/sessions?user_id=user-1")
            assert resp.status_code == 200
            assert resp.json()["deleted"] is True
            assert resp.json()["count"] == 2

            # Only user-1's sessions deleted
            assert mock_session.delete.call_count == 2
            mock_session.commit.assert_awaited_once()
