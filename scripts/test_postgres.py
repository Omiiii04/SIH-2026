#!/usr/bin/env python
"""
scripts/test_postgres.py
─────────────────────────
SIH-2026  Phase 4  PostgreSQL Verification Script
==================================================

Sends a query to the running orchestrator (default http://localhost:8000)
and then queries PostgreSQL directly to verify that:

  1. A users row was created (or already existed).
  2. A requests row exists with the correct user_id and selected_node.
  3. A routing_decisions row exists linked to that request.

Then queries the node_health table to show current health snapshots.

Usage
-----
  # Orchestrator + Docker services must be running:
  docker compose up -d
  uvicorn orchestrator.main:app --port 8000

  python scripts/test_postgres.py
  python scripts/test_postgres.py --url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_PASS = "\033[92m✓ PASS\033[0m"
_FAIL = "\033[91m✗ FAIL\033[0m"
_INFO = "\033[96m  ●\033[0m"
_HEAD = "\033[1m"
_RST  = "\033[0m"


def h(s: str) -> str:
    return f"{_HEAD}{s}{_RST}"


async def run(base_url: str) -> int:
    failures = 0

    print(h("\n  SIH-2026 Phase 4 — PostgreSQL Verification"))
    print(f"  Target orchestrator : {base_url}\n")

    # ── Step 1: Send a query ───────────────────────────────────────────────────
    payload = {
        "user_id":    "pg_test_user_001",
        "query":      "Explain what a transformer model is in simple terms.",
        "input_type": "text",
    }

    print(f"{_INFO} Sending POST /api/v1/query ...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{base_url.rstrip('/')}/api/v1/query",
                json=payload,
                timeout=60.0,
            )
        except httpx.ConnectError as exc:
            print(f"{_FAIL}  Cannot reach orchestrator: {exc}")
            return 1

    if resp.status_code != 200:
        print(f"{_FAIL}  Orchestrator returned HTTP {resp.status_code}: {resp.text[:200]}")
        # Note: might still have persisted a failure row — continue checks
        failures += 1
    else:
        body = resp.json()
        request_id     = body.get("request_id", "")
        selected_node  = body.get("selected_node", "")
        print(f"{_PASS}  Query successful — request_id={request_id}  node={selected_node}")

    # Small delay to let the fire-and-forget persist task complete
    await asyncio.sleep(1.5)

    # ── Step 2: Connect directly to PostgreSQL ────────────────────────────────
    print(f"\n{_INFO} Connecting to PostgreSQL ...")
    try:
        # Use orchestrator config so we read the same .env
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from orchestrator.config import get_settings
        from sqlalchemy import create_engine, text

        cfg = get_settings()
        # Sync DSN for this script (uses psycopg2 if available, else asyncpg via sync wrapper)
        sync_dsn = (
            f"postgresql+psycopg2://{cfg.postgres_user}:{cfg.postgres_password}"
            f"@{cfg.postgres_host}:{cfg.postgres_port}/{cfg.postgres_db}"
        )
        engine = create_engine(sync_dsn)
        conn   = engine.connect()
        print(f"{_PASS}  Connected to {cfg.postgres_host}:{cfg.postgres_port}/{cfg.postgres_db}")
    except Exception as exc:
        print(f"{_FAIL}  Cannot connect to PostgreSQL: {exc}")
        print("        Make sure 'docker compose up -d' is running and psycopg2 is installed.")
        print("        Install: .venv\\Scripts\\pip install psycopg2-binary")
        return 1

    # ── Step 3: Verify users row ──────────────────────────────────────────────
    print(f"\n{_INFO} Checking users table ...")
    row = conn.execute(
        text("SELECT user_id, created_at FROM users WHERE user_id = :uid"),
        {"uid": payload["user_id"]},
    ).fetchone()

    if row:
        print(f"{_PASS}  users row found: user_id={row[0]}  created_at={row[1]}")
    else:
        print(f"{_FAIL}  No users row for user_id='{payload['user_id']}'")
        failures += 1

    # ── Step 4: Verify requests row ───────────────────────────────────────────
    print(f"\n{_INFO} Checking requests table ...")
    row = conn.execute(
        text("""
            SELECT id, selected_node, status, latency_ms, created_at
            FROM requests
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"uid": payload["user_id"]},
    ).fetchone()

    if row:
        rid, node, stat, lat, ts = row
        print(f"{_PASS}  requests row found:")
        print(f"        id={rid}  node={node}  status={stat}  latency={lat:.1f}ms")
    else:
        print(f"{_FAIL}  No requests row found for user_id='{payload['user_id']}'")
        failures += 1
        rid = None

    # ── Step 5: Verify routing_decisions row ──────────────────────────────────
    print(f"\n{_INFO} Checking routing_decisions table ...")
    if rid:
        row = conn.execute(
            text("""
                SELECT selected_node, required_capability, confidence, was_fallback
                FROM routing_decisions
                WHERE request_id = :rid
            """),
            {"rid": str(rid)},
        ).fetchone()

        if row:
            node, cap, conf, fallback = row
            print(f"{_PASS}  routing_decisions row found:")
            print(f"        node={node}  capability={cap}  confidence={conf:.2f}  fallback={fallback}")
        else:
            print(f"{_FAIL}  No routing_decisions row for request_id={rid}")
            failures += 1
    else:
        print(f"        (skipped — no requests row found)")
        failures += 1

    # ── Step 6: Show node_health rows ─────────────────────────────────────────
    print(f"\n{_INFO} node_health snapshot:")
    rows = conn.execute(
        text("SELECT node_id, status, latency_ms, last_seen FROM node_health ORDER BY node_id")
    ).fetchall()
    if rows:
        for r in rows:
            print(f"        {r[0]:<20} status={r[1]:<12} latency={r[2]}  last_seen={r[3]}")
    else:
        print("        (no rows yet — node health is written on failure / health-check)")

    conn.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  {'─'*55}")
    if failures == 0:
        print(f"  {_PASS}  All PostgreSQL checks passed.\n")
    else:
        print(f"  {_FAIL}  {failures} check(s) failed.\n")

    return 0 if failures == 0 else 1


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 4 PostgreSQL verifier")
    p.add_argument("--url", default="http://localhost:8000", help="Orchestrator URL")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    sys.exit(asyncio.run(run(args.url)))
