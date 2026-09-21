"""
tests/test_connectivity.py
──────────────────────────
Phase 1 connectivity tests covering the four scenarios from the brief.

All scenarios run in-process using httpx mock transports so they work
on any machine — no live LM Studio instance required.

Scenario 1: All five nodes ONLINE   → 5/5 reachable
Scenario 2: NODE-TEXT OFFLINE       → 4/5, NODE-TEXT reported OFFLINE
Scenario 3: NODE-TEXT back ONLINE   → 5/5 again
Scenario 4: Inference on text nodes → valid response returned
"""

from __future__ import annotations

import json
from typing import Optional
from unittest.mock import patch

import httpx
import pytest

# ── Bring repo root onto path (mirrors how scripts/test_nodes.py does it) ─────
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.config import NodeConfig, _make_node_configs
from orchestrator.schemas import NodeType
from scripts.test_nodes import (
    NodeResult,
    probe_reachability,
    probe_inference,
    run_tests,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — fake LM Studio responses
# ─────────────────────────────────────────────────────────────────────────────

def _models_response(model_id: str = "test-model") -> dict:
    """Minimal /v1/models payload that LM Studio returns."""
    return {"object": "list", "data": [{"id": model_id, "object": "model"}]}


def _chat_response(content: str = "Hello from the test model!") -> dict:
    """Minimal /v1/chat/completions payload that LM Studio returns."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13},
    }


def _make_five_nodes(
    node_1_url: str = "http://node-1:1234",
    node_2_url: str = "http://node-2:1234",
    node_3_url: str = "http://node-3:1234",
    node_4_url: str = "http://node-4:1234",
    node_5_url: str = "http://node-5:1234",
):
    """Build a list of NodeConfigs with the given URLs."""
    configs = _make_node_configs(
        node_1_url=node_1_url,
        node_2_url=node_2_url,
        node_3_url=node_3_url,
        node_4_url=node_4_url,
        node_5_url=node_5_url,
    )
    return list(sorted(configs.values(), key=lambda n: n.laptop_id))


# ─────────────────────────────────────────────────────────────────────────────
# Custom ASGI-like transport that simulates LM Studio on specific hosts
# ─────────────────────────────────────────────────────────────────────────────

class FakeLMStudioTransport(httpx.AsyncBaseTransport):
    """
    Intercepts httpx requests and returns canned LM Studio responses.

    Parameters
    ----------
    offline_hosts: set of hostnames that should return a ConnectError.
    """

    def __init__(self, offline_hosts: set[str] | None = None):
        self.offline_hosts = offline_hosts or set()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host

        if host in self.offline_hosts:
            raise httpx.ConnectError(f"[Mock] {host} is offline")

        path = request.url.path

        if path == "/v1/models":
            body = _models_response(f"{host}-model")
            return httpx.Response(200, json=body)

        if path == "/v1/chat/completions":
            body = _chat_response(f"Response from {host}")
            return httpx.Response(200, json=body)

        return httpx.Response(404, text="Not found")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1 — All five nodes ONLINE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario1_all_five_online():
    """5/5 nodes reachable when all LM Studio servers are up."""
    nodes = _make_five_nodes()
    transport = FakeLMStudioTransport(offline_hosts=set())

    async with httpx.AsyncClient(transport=transport) as client:
        results = [await probe_reachability(client, n, timeout=5.0) for n in nodes]

    online = [r for r in results if r.is_online]
    assert len(online) == 5, f"Expected 5 online, got {len(online)}"


@pytest.mark.asyncio
async def test_scenario1_all_nodes_have_model():
    """Every online node must report a model_loaded value."""
    nodes = _make_five_nodes()
    transport = FakeLMStudioTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        results = [await probe_reachability(client, n, timeout=5.0) for n in nodes]

    for r in results:
        assert r.model_loaded is not None, f"{r.node_id} has no model_loaded"


@pytest.mark.asyncio
async def test_scenario1_latency_recorded():
    """Latency must be a non-negative float for all online nodes."""
    nodes = _make_five_nodes()
    transport = FakeLMStudioTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        results = [await probe_reachability(client, n, timeout=5.0) for n in nodes]

    for r in results:
        assert r.latency_ms is not None
        assert r.latency_ms >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2 — NODE-TEXT OFFLINE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario2_node_text_offline():
    """4/5 nodes reachable; NODE-TEXT is OFFLINE."""
    nodes = _make_five_nodes()
    text_host = httpx.URL(nodes[0].endpoint).host  # "node-text"
    transport = FakeLMStudioTransport(offline_hosts={text_host})

    async with httpx.AsyncClient(transport=transport) as client:
        results = [await probe_reachability(client, n, timeout=5.0) for n in nodes]

    by_id = {r.node_id: r for r in results}

    # NODE-TEXT must be OFFLINE
    assert not by_id["NODE-TEXT"].is_online, "NODE-TEXT should be OFFLINE"

    # All others must be ONLINE
    for node_id in ("NODE-VISION", "NODE-REASONING", "NODE-CODE", "NODE-RAG"):
        assert by_id[node_id].is_online, f"{node_id} should be ONLINE"

    online_count = sum(1 for r in results if r.is_online)
    assert online_count == 4, f"Expected 4 online, got {online_count}"


@pytest.mark.asyncio
async def test_scenario2_program_does_not_crash():
    """The tester must complete and return results even when NODE-TEXT is offline."""
    nodes = _make_five_nodes()
    text_host = httpx.URL(nodes[0].endpoint).host
    transport = FakeLMStudioTransport(offline_hosts={text_host})

    async with httpx.AsyncClient(transport=transport) as client:
        # This must not raise
        results = [await probe_reachability(client, n, timeout=5.0) for n in nodes]

    assert len(results) == 5  # we always get one result per node


@pytest.mark.asyncio
async def test_scenario2_offline_node_has_error_message():
    """An offline node must carry an explanatory error string."""
    nodes = _make_five_nodes()
    text_host = httpx.URL(nodes[0].endpoint).host
    transport = FakeLMStudioTransport(offline_hosts={text_host})

    async with httpx.AsyncClient(transport=transport) as client:
        results = [await probe_reachability(client, n, timeout=5.0) for n in nodes]

    text_result = next(r for r in results if r.node_id == "NODE-TEXT")
    assert text_result.error is not None
    assert len(text_result.error) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3 — NODE-TEXT comes back ONLINE
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario3_node_text_recovers():
    """After NODE-TEXT restarts, all 5 nodes are reachable again."""
    nodes = _make_five_nodes()
    # Simulate restart: transport has no offline hosts this time
    transport = FakeLMStudioTransport(offline_hosts=set())

    async with httpx.AsyncClient(transport=transport) as client:
        results = [await probe_reachability(client, n, timeout=5.0) for n in nodes]

    by_id = {r.node_id: r for r in results}
    assert by_id["NODE-TEXT"].is_online, "NODE-TEXT should be back ONLINE"

    online_count = sum(1 for r in results if r.is_online)
    assert online_count == 5, f"Expected 5 online after recovery, got {online_count}"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 4 — Inference test on text-capable nodes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario4_inference_on_text_capable_nodes():
    """
    Every text-capable node (TEXT, REASONING, CODE, RAG) must return a
    valid non-empty inference response.
    """
    # Only text-capable nodes for inference
    text_capable_ids = {"NODE-TEXT", "NODE-REASONING", "NODE-CODE", "NODE-RAG"}
    nodes = [n for n in _make_five_nodes() if n.node_id in text_capable_ids]
    transport = FakeLMStudioTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        for node in nodes:
            reach_result = await probe_reachability(client, node, timeout=5.0)
            assert reach_result.is_online, f"{node.node_id} must be online for inference test"

            await probe_inference(client, node, reach_result, timeout=10.0)

            assert reach_result.inference_ok is True, (
                f"{node.node_id} inference failed: {reach_result.error}"
            )
            assert reach_result.inference_response, f"{node.node_id} returned empty response"
            assert len(reach_result.inference_response) > 0


@pytest.mark.asyncio
async def test_scenario4_inference_response_is_string():
    """Inference response content must be a non-empty string."""
    node = _make_five_nodes()[0]  # NODE-TEXT
    transport = FakeLMStudioTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        result = await probe_reachability(client, node, timeout=5.0)
        await probe_inference(client, node, result, timeout=10.0)

    assert isinstance(result.inference_response, str)
    assert len(result.inference_response.strip()) > 0


@pytest.mark.asyncio
async def test_scenario4_offline_node_skipped_gracefully():
    """Inference is only attempted for online nodes; offline nodes don't crash the runner."""
    nodes = _make_five_nodes()
    text_host = httpx.URL(nodes[0].endpoint).host
    transport = FakeLMStudioTransport(offline_hosts={text_host})

    async with httpx.AsyncClient(transport=transport) as client:
        for node in nodes:
            result = await probe_reachability(client, node, timeout=5.0)
            if result.is_online:
                await probe_inference(client, node, result, timeout=10.0)
                assert result.inference_ok is True
            else:
                # Offline node — inference must NOT have been called
                assert result.inference_ok is None


# ─────────────────────────────────────────────────────────────────────────────
# Unconfigured node tests (real-world: only 1 laptop is set up)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unconfigured_node_is_marked_not_configured():
    """An empty endpoint string must produce is_configured=False and no network call."""
    nodes = _make_node_configs(
        text_url="http://configured:1234",
        vision_url="",   # not set up yet
        reasoning_url="",
        code_url="",
        rag_url="",
    )
    transport = FakeLMStudioTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        results = []
        for cfg in nodes.values():
            results.append(await probe_reachability(client, cfg, timeout=5.0))

    by_id = {r.node_id: r for r in results}
    assert by_id["NODE-TEXT"].is_configured
    assert by_id["NODE-TEXT"].is_online

    for node_id in ("NODE-VISION", "NODE-REASONING", "NODE-CODE", "NODE-RAG"):
        assert not by_id[node_id].is_configured
        assert not by_id[node_id].is_online


@pytest.mark.asyncio
async def test_unconfigured_nodes_do_not_block_configured_ones():
    """4 unconfigured nodes must not prevent the 1 configured node from succeeding."""
    nodes = _make_node_configs(
        text_url="http://configured:1234",
        vision_url="",
        reasoning_url="",
        code_url="",
        rag_url="",
    )
    transport = FakeLMStudioTransport()

    async with httpx.AsyncClient(transport=transport) as client:
        results = [await probe_reachability(client, cfg, timeout=5.0) for cfg in nodes.values()]

    online = [r for r in results if r.is_online]
    assert len(online) == 1
    assert online[0].node_id == "NODE-TEXT"
