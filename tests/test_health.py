"""
Tests for the /health and /health/cluster endpoints.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health must return HTTP 200."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_shape(client: AsyncClient) -> None:
    """GET /health must include status, service, version, and timestamp keys."""
    response = await client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
    assert "service" in body
    assert "version" in body
    assert "timestamp" in body


@pytest.mark.asyncio
async def test_health_cluster_returns_200(client: AsyncClient) -> None:
    """
    GET /health/cluster must return HTTP 200.

    Worker nodes will not be reachable in CI, but the endpoint should
    still return 200 and report all nodes as offline (is_online=False).
    """
    response = await client.get("/health/cluster")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_cluster_response_shape(client: AsyncClient) -> None:
    """GET /health/cluster response must conform to ClusterHealthResponse schema."""
    response = await client.get("/health/cluster")
    body = response.json()

    assert body["orchestrator_status"] == "ok"
    assert "nodes" in body
    assert isinstance(body["nodes"], list)
    assert "healthy_count" in body
    assert "total_count" in body
    # Five worker nodes are registered
    assert body["total_count"] == 5


@pytest.mark.asyncio
async def test_health_cluster_all_nodes_present(client: AsyncClient) -> None:
    """All five node types must appear in the cluster health response."""
    response = await client.get("/health/cluster")
    node_types = {n["node_type"] for n in response.json()["nodes"]}
    assert node_types == {"text", "vision", "reasoning", "code", "rag"}
