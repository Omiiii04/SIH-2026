"""
Shared pytest fixtures for the SIH-2026 test suite.

Uses httpx.AsyncClient with FastAPI's ASGI transport so tests run
entirely in-process — no live network, no live database required.
"""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Speed up health/cluster tests by reducing the node probe timeout ──────────
# Worker nodes are not available in CI / local test runs.
# Setting HTTP_TIMEOUT=2 makes unreachable-node probes fail in ~2s instead of 30s.
os.environ.setdefault("HTTP_TIMEOUT", "2")

from orchestrator.main import app  # noqa: E402  (import after env patch)


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """
    Yield an async HTTP client wired directly to the FastAPI ASGI app.
    No real server is started; requests go through the ASGI transport.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac
