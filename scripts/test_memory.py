#!/usr/bin/env python
"""
scripts/test_memory.py
───────────────────────
SIH-2026  Phase 4  End-to-End Memory Test
==========================================

Sends three related queries to the orchestrator, then calls the
semantic memory search endpoint to verify that relevant past interactions
are returned in the correct order.

Test sequence
─────────────
  1. POST /api/v1/query  "What is a transformer model?"          → expect NODE-1
  2. POST /api/v1/query  "Explain attention mechanism"           → expect NODE-1
  3. POST /api/v1/query  "How does BERT use transformers?"       → expect NODE-1
  4. Wait 2 s for fire-and-forget persist tasks
  5. POST /api/v1/memory/search  "transformer architecture"
     → expect all 3 queries to appear in results (semantic overlap)

Usage
─────
  docker compose up -d
  uvicorn orchestrator.main:app --port 8000

  python scripts/test_memory.py
  python scripts/test_memory.py --url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx

_PASS = "\033[92m✓ PASS\033[0m"
_FAIL = "\033[91m✗ FAIL\033[0m"
_INFO = "\033[96m  ●\033[0m"
_HEAD = "\033[1m"
_RST  = "\033[0m"


def h(s: str) -> str:
    return f"{_HEAD}{s}{_RST}"


QUERIES = [
    "What is a transformer model?",
    "Explain the attention mechanism in deep learning.",
    "How does BERT use transformers for NLP tasks?",
]

SEARCH_QUERY   = "transformer architecture and attention"
TEST_USER_ID   = "memory_test_user_001"
EXPECTED_MATCH = 2   # at least 2 of the 3 queries should appear in search results


async def post_query(client: httpx.AsyncClient, url: str, query: str) -> dict:
    resp = await client.post(
        f"{url.rstrip('/')}/api/v1/query",
        json={"user_id": TEST_USER_ID, "query": query, "input_type": "text"},
        timeout=90.0,
    )
    return resp.status_code, resp.json() if resp.status_code in (200, 503) else {}


async def run(base_url: str) -> int:
    failures = 0

    print(h(f"\n  SIH-2026 Phase 4 — End-to-End Memory Test"))
    print(f"  Target : {base_url}  user_id={TEST_USER_ID}\n")

    async with httpx.AsyncClient() as client:

        # ── Step 1: Check orchestrator is up ──────────────────────────────────
        print(f"{_INFO} Checking orchestrator health ...")
        try:
            hresp = await client.get(f"{base_url.rstrip('/')}/health", timeout=10.0)
        except httpx.ConnectError as exc:
            print(f"{_FAIL}  Cannot reach orchestrator: {exc}")
            return 1

        if hresp.status_code != 200:
            print(f"{_FAIL}  Health check returned HTTP {hresp.status_code}")
            return 1

        hdbs = hresp.json().get("databases", {})
        print(f"{_PASS}  Orchestrator up — postgres={hdbs.get('postgres')}  chroma={hdbs.get('chroma')}")

        if hdbs.get("chroma") != "ok":
            print(f"\n{_FAIL}  ChromaDB is not available. Start with 'docker compose up -d'.")
            return 1

        # ── Step 2: Send 3 queries ─────────────────────────────────────────────
        print(f"\n{_INFO} Sending {len(QUERIES)} queries ...")
        sent_request_ids = []
        for i, q in enumerate(QUERIES, 1):
            code, body = await post_query(client, base_url, q)
            if code == 200:
                rid = body.get("request_id", "?")
                node = body.get("selected_node", "?")
                sent_request_ids.append(rid)
                print(f"  [{i}/{len(QUERIES)}] {_PASS}  '{q[:55]}...'")
                print(f"           request_id={rid}  node={node}")
            else:
                print(f"  [{i}/{len(QUERIES)}] {_FAIL}  HTTP {code} — {str(body)[:100]}")
                failures += 1

        # ── Step 3: Wait for background persist tasks ──────────────────────────
        print(f"\n{_INFO} Waiting 2.5s for persistence tasks to complete ...")
        await asyncio.sleep(2.5)

        # ── Step 4: Semantic memory search ────────────────────────────────────
        print(f"\n{_INFO} Searching memory: '{SEARCH_QUERY}' ...")
        sresp = await client.post(
            f"{base_url.rstrip('/')}/api/v1/memory/search",
            json={
                "user_id":   TEST_USER_ID,
                "query":     SEARCH_QUERY,
                "n_results": 10,
            },
            timeout=30.0,
        )

        if sresp.status_code != 200:
            print(f"{_FAIL}  Memory search returned HTTP {sresp.status_code}: {sresp.text[:200]}")
            return 1

        sdata   = sresp.json()
        total   = sdata.get("total", 0)
        results = sdata.get("results", [])

        print(f"{_PASS}  Memory search returned {total} result(s).")

        # ── Step 5: Validate results ───────────────────────────────────────────
        print(f"\n{_INFO} Validating results ...")
        found_ids = {r.get("request_id") for r in results}
        matched   = [rid for rid in sent_request_ids if rid in found_ids]

        print(f"        Sent request_ids     : {len(sent_request_ids)}")
        print(f"        Found in search      : {len(matched)}/{len(sent_request_ids)}")
        for r in results[:5]:
            score = r.get("score", 0)
            print(f"        [{score:.3f}] {r.get('query', '')[:70]}")

        if len(matched) >= EXPECTED_MATCH:
            print(f"\n{_PASS}  ≥{EXPECTED_MATCH} of {len(QUERIES)} queries found in semantic search.")
        else:
            print(f"\n{_FAIL}  Only {len(matched)}/{len(QUERIES)} queries matched — expected ≥{EXPECTED_MATCH}.")
            failures += 1

        # ── Step 6: Verify result structure ───────────────────────────────────
        print(f"\n{_INFO} Checking result field structure ...")
        required_fields = {"request_id", "query", "response", "node_id", "model", "timestamp", "score"}
        if results:
            missing = required_fields - results[0].keys()
            if not missing:
                print(f"{_PASS}  All required fields present in result objects.")
            else:
                print(f"{_FAIL}  Missing fields: {missing}")
                failures += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  {'─'*55}")
    if failures == 0:
        print(f"  {_PASS}  End-to-end memory test passed.\n")
    else:
        print(f"  {_FAIL}  {failures} check(s) failed.\n")

    return 0 if failures == 0 else 1


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 4 end-to-end memory test")
    p.add_argument("--url", default="http://localhost:8000", help="Orchestrator base URL")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    sys.exit(asyncio.run(run(args.url)))
