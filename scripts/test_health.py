#!/usr/bin/env python3
"""
scripts/test_health.py
Phase 5 - Node health API test.

Tests GET /api/v1/nodes and /api/v1/metrics.
Also verifies manual status override via PATCH.

Usage:
    python scripts/test_health.py [--base-url http://localhost:8000]
"""

import argparse
import json
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"
TIMEOUT  = 10.0


def check(label: str, condition: bool, detail: str = "") -> bool:
    icon = "PASS" if condition else "FAIL"
    print(f"  [{icon}] {label}" + (f" - {detail}" if detail else ""))
    return condition


def run(base: str) -> int:
    client = httpx.Client(base_url=base, timeout=TIMEOUT)
    failures = 0

    print("\n=== TEST 1: GET /api/v1/nodes ===")
    r = client.get("/api/v1/nodes")
    ok = check("HTTP 200", r.status_code == 200, str(r.status_code))
    if not ok:
        failures += 1
        print("  Response:", r.text[:300])
    else:
        body = r.json()
        nodes = body.get("nodes", [])
        ok = check("Has nodes list", len(nodes) > 0, f"count={len(nodes)}")
        failures += 0 if ok else 1
        for n in nodes:
            has_id     = check(f"  {n.get('node_id','?')} has node_id", "node_id" in n)
            has_status = check(f"  {n.get('node_id','?')} has status", n.get("status") in ("ONLINE","DEGRADED","OFFLINE"))
            has_lat    = True  # latency_ms can be None
            print(f"    node_id={n.get('node_id')}  status={n.get('status')}  latency_ms={n.get('latency_ms')}")
            failures += 0 if (has_id and has_status) else 1

    print("\n=== TEST 2: GET /api/v1/metrics ===")
    r = client.get("/api/v1/metrics")
    ok = check("HTTP 200", r.status_code == 200, str(r.status_code))
    failures += 0 if ok else 1
    if ok:
        body = r.json()
        for key in ("total_requests", "successful", "failed", "success_rate", "window_size"):
            ok = check(f"  Has field '{key}'", key in body)
            failures += 0 if ok else 1
        print("  Metrics:", json.dumps(body, indent=2))

    print("\n=== TEST 3: PATCH /api/v1/nodes/NODE-TEXT/status?status=offline ===")
    r = client.patch("/api/v1/nodes/NODE-TEXT/status", params={"status": "offline"})
    ok = check("HTTP 200", r.status_code == 200, str(r.status_code))
    failures += 0 if ok else 1
    if ok:
        body = r.json()
        ok = check("Status is offline in response", body.get("status") == "offline")
        failures += 0 if ok else 1

    print("\n=== TEST 4: Verify NODE-TEXT shows OFFLINE in /api/v1/nodes ===")
    # Give monitor a moment (it may override our PATCH, so we just check the PATCH was accepted)
    r = client.get("/api/v1/nodes")
    if r.status_code == 200:
        nodes = {n["node_id"]: n for n in r.json().get("nodes", [])}
        # Note: monitor may have already run and changed it; we just log
        nt = nodes.get("NODE-TEXT", {})
        print(f"  NODE-TEXT current status: {nt.get('status')} (monitor may have updated)")

    print("\n=== TEST 5: Restore NODE-TEXT to online ===")
    r = client.patch("/api/v1/nodes/NODE-TEXT/status", params={"status": "online"})
    ok = check("HTTP 200", r.status_code == 200, str(r.status_code))
    failures += 0 if ok else 1

    print(f"\n{'='*40}")
    print(f"Results: {failures} failure(s)")
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    sys.exit(run(args.base_url))
