#!/usr/bin/env python3
"""
scripts/load_test.py
Phase 5 - Load test for single-laptop deployment.

Tests:
  TEST 5: 10 sequential requests - records avg/min/max latency and success rate.
  TEST 6: Concurrent requests - measures throughput, success rate, latency.

Usage:
    python scripts/load_test.py [--base-url http://localhost:8000] [--concurrency 3] [--requests 10]

IMPORTANT: Keep --concurrency low (default 3) on single-laptop to avoid overload.
The orchestrator + LM Studio + this script all share the same CPU/RAM.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

BASE_URL    = "http://localhost:8000"
USER_ID     = "load_tester"
QUERY_POOL  = [
    "What is Python?",
    "Explain recursion in programming.",
    "What is the capital of Germany?",
    "How does HTTP work?",
    "What is a neural network?",
    "Describe the water cycle.",
    "What is a binary search tree?",
    "Explain the concept of entropy.",
    "What are design patterns in software?",
    "How does DNS resolution work?",
]


@dataclass
class Result:
    query:       str
    status_code: int
    latency_ms:  float
    node:        str
    was_fallback: bool = False
    retry_count: int   = 0
    error:       Optional[str] = None


async def send_request(client: httpx.AsyncClient, query: str, timeout: float) -> Result:
    t0 = time.monotonic()
    try:
        r = await client.post(
            "/api/v1/query",
            json={"user_id": USER_ID, "query": query, "input_type": "text"},
            timeout=timeout,
        )
        latency_ms = (time.monotonic() - t0) * 1000
        body = r.json()
        return Result(
            query=query,
            status_code=r.status_code,
            latency_ms=round(latency_ms, 1),
            node=body.get("selected_node", "?"),
            was_fallback=body.get("routing", {}).get("was_fallback", False),
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000
        return Result(
            query=query,
            status_code=0,
            latency_ms=round(latency_ms, 1),
            node="error",
            error=str(exc)[:100],
        )


def print_summary(label: str, results: List[Result]) -> None:
    total    = len(results)
    success  = [r for r in results if r.status_code in (200, 503)]  # 503 = routing worked, node offline
    ok_200   = [r for r in results if r.status_code == 200]
    latencies = [r.latency_ms for r in results]

    print(f"\n  {label}")
    print(f"  Total requests:  {total}")
    print(f"  Success (200):   {len(ok_200)} ({100*len(ok_200)/total:.0f}%)")
    print(f"  Routed (200+503):{len(success)} ({100*len(success)/total:.0f}%)")
    print(f"  Failed (other):  {total - len(success)}")
    if latencies:
        print(f"  Avg latency:     {statistics.mean(latencies):.1f} ms")
        print(f"  Min latency:     {min(latencies):.1f} ms")
        print(f"  Max latency:     {max(latencies):.1f} ms")
        if len(latencies) > 1:
            print(f"  Stdev:           {statistics.stdev(latencies):.1f} ms")
    fallbacks = sum(1 for r in results if r.was_fallback)
    if fallbacks:
        print(f"  Fallbacks used:  {fallbacks}")
    errors = [r for r in results if r.error]
    if errors:
        print(f"  Errors:          {len(errors)}")
        for e in errors[:3]:
            print(f"    - {e.error}")


async def run(base: str, concurrency: int, n_requests: int, timeout: float) -> int:
    failures = 0

    # TEST 5: Sequential requests
    print(f"\n=== TEST 5: {n_requests} sequential requests ===")
    seq_results: List[Result] = []
    async with httpx.AsyncClient(base_url=base) as client:
        for i in range(n_requests):
            query = QUERY_POOL[i % len(QUERY_POOL)]
            r = await send_request(client, query, timeout)
            seq_results.append(r)
            print(f"  [{i+1:02d}/{n_requests}] status={r.status_code}  latency={r.latency_ms:.0f}ms  node={r.node}")

    print_summary("Sequential test results:", seq_results)
    ok_seq = sum(1 for r in seq_results if r.status_code in (200, 503))
    if ok_seq < n_requests:
        failures += 1

    # TEST 6: Concurrent requests
    print(f"\n=== TEST 6: {n_requests} requests with concurrency={concurrency} ===")
    conc_results: List[Result] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(client, q, t):
        async with semaphore:
            return await send_request(client, q, t)

    t_wall_start = time.monotonic()
    async with httpx.AsyncClient(base_url=base) as client:
        tasks = [bounded(client, QUERY_POOL[i % len(QUERY_POOL)], timeout) for i in range(n_requests)]
        conc_results = list(await asyncio.gather(*tasks))
    wall_ms = (time.monotonic() - t_wall_start) * 1000

    print_summary("Concurrent test results:", conc_results)
    print(f"  Wall time:       {wall_ms:.0f} ms")
    if wall_ms > 0:
        rps = n_requests / (wall_ms / 1000)
        print(f"  Throughput:      {rps:.2f} req/s")

    ok_conc = sum(1 for r in conc_results if r.status_code in (200, 503))
    if ok_conc < n_requests:
        failures += 1

    # Final metrics from orchestrator
    print("\n=== Orchestrator aggregate metrics after load test ===")
    try:
        async with httpx.AsyncClient(base_url=base) as client:
            r = await client.get("/api/v1/metrics", timeout=5.0)
            if r.status_code == 200:
                snap = r.json()
                print(json.dumps(snap, indent=2))
    except Exception as exc:
        print(f"  Could not fetch metrics: {exc}")

    print(f"\n{'='*40}")
    print(f"Load test complete. Failures: {failures}")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 5 load test (single-laptop safe)")
    parser.add_argument("--base-url",    default=BASE_URL, help="Orchestrator URL")
    parser.add_argument("--concurrency", default=3,        type=int, help="Max concurrent requests (keep low on laptop)")
    parser.add_argument("--requests",    default=10,       type=int, help="Total requests to send")
    parser.add_argument("--timeout",     default=30.0,     type=float, help="Per-request timeout (s)")
    args = parser.parse_args()

    print(f"Load test: base={args.base_url}  concurrency={args.concurrency}  requests={args.requests}")
    sys.exit(asyncio.run(run(args.base_url, args.concurrency, args.requests, args.timeout)))
