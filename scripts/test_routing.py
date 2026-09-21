#!/usr/bin/env python
"""
scripts/test_routing.py
────────────────────────
SIH-2026  Phase 3 Routing Tester
=================================

Sends a diverse set of requests to the orchestrator and prints a
detailed routing report for each one.

Output per request:
  ─────────────────────────────────────────────────────────────────
  QUERY          Find the bug in this Python code.
  INPUT TYPE     text
  TASK           code_debug
  DIFFICULTY     medium
  CAPABILITY     coding
  CONFIDENCE     97%  (rule:debug_keywords:find the bug)
  SELECTED NODE  NODE-4
  REASON         The request requires debugging and fixing code…
  WAS FALLBACK   No
  MODEL          codellama-7b-instruct
  LATENCY        842 ms
  RESPONSE       The bug is on line 3: missing colon after the…
  ─────────────────────────────────────────────────────────────────

Usage
─────
  # Orchestrator must be running:
  uvicorn orchestrator.main:app --reload --port 8000

  python scripts/test_routing.py
  python scripts/test_routing.py --url http://localhost:8000
  python scripts/test_routing.py --timeout 60
  python scripts/test_routing.py --json
  python scripts/test_routing.py --offline NODE-4   # simulate node offline first
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

# ─────────────────────────────────────────────────────────────────────────────
# ANSI helpers
# ─────────────────────────────────────────────────────────────────────────────

_USE_COLOUR = sys.stdout.isatty()
def _g(s):  return f"\033[92m{s}\033[0m" if _USE_COLOUR else s
def _r(s):  return f"\033[91m{s}\033[0m" if _USE_COLOUR else s
def _y(s):  return f"\033[93m{s}\033[0m" if _USE_COLOUR else s
def _c(s):  return f"\033[96m{s}\033[0m" if _USE_COLOUR else s
def _b(s):  return f"\033[1m{s}\033[0m"  if _USE_COLOUR else s
def _d(s):  return f"\033[2m{s}\033[0m"  if _USE_COLOUR else s

_LINE = "─" * 70


# ─────────────────────────────────────────────────────────────────────────────
# Test cases (mirrors the 6 required spec cases + extras)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RoutingCase:
    name: str
    payload: Dict[str, Any]
    expected_node: str
    description: str = ""


ROUTING_CASES: List[RoutingCase] = [
    RoutingCase(
        name="Case 1 — General Text",
        payload={"user_id": "tester", "query": "What is Python?", "input_type": "text"},
        expected_node="NODE-1",
        description="General knowledge query — should route to NODE-1",
    ),
    RoutingCase(
        name="Case 2 — Code Generation",
        payload={"user_id": "tester", "query": "Write a FastAPI endpoint that returns a JSON response.", "input_type": "text"},
        expected_node="NODE-4",
        description="Code generation — should route to NODE-4",
    ),
    RoutingCase(
        name="Case 3 — Visual QA",
        payload={"user_id": "tester", "query": "Explain what is shown in this image.", "input_type": "image"},
        expected_node="NODE-2",
        description="Image input — should route to NODE-2",
    ),
    RoutingCase(
        name="Case 4 — Hard Reasoning",
        payload={"user_id": "tester",
                 "query": "Prove step by step using formal logic that if all humans are mortal "
                          "and Socrates is human, then Socrates is mortal.",
                 "input_type": "text"},
        expected_node="NODE-3",
        description="Complex multi-step reasoning — should route to NODE-3",
    ),
    RoutingCase(
        name="Case 5 — Embedding / Search",
        payload={"user_id": "tester",
                 "query": "Search the knowledge base and retrieve documents about transformer architecture.",
                 "input_type": "retrieval"},
        expected_node="NODE-5",
        description="Retrieval / embedding — should route to NODE-5",
    ),
    RoutingCase(
        name="Case 6 — Code Debug",
        payload={"user_id": "tester",
                 "query": "Find the bug in this Python code: def add(a, b) return a + b",
                 "input_type": "text"},
        expected_node="NODE-4",
        description="Code debug — should route to NODE-4",
    ),
    RoutingCase(
        name="Case 7 — Summarisation",
        payload={"user_id": "tester",
                 "query": "Summarise the key points of the transformer paper in 3 sentences.",
                 "input_type": "text"},
        expected_node="NODE-1",
        description="Summarisation — should route to NODE-1",
    ),
    RoutingCase(
        name="Case 8 — Math / Proof",
        payload={"user_id": "tester",
                 "query": "Calculate the derivative of f(x) = x³ + 2x² - 5x + 7",
                 "input_type": "text"},
        expected_node="NODE-3",
        description="Mathematics / calculus — should route to NODE-3",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case: RoutingCase
    status_code: int
    body: Dict[str, Any]
    wall_ms: float
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status_code == 200

    @property
    def routing_correct(self) -> bool:
        if not self.is_success:
            return False
        return self.body.get("selected_node") == self.case.expected_node


async def run_case(
    client: httpx.AsyncClient,
    case: RoutingCase,
    base_url: str,
    timeout: float,
) -> CaseResult:
    url = f"{base_url.rstrip('/')}/api/v1/query"
    t0 = time.monotonic()
    try:
        resp = await client.post(url, json=case.payload, timeout=timeout)
        wall_ms = round((time.monotonic() - t0) * 1000, 1)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return CaseResult(case=case, status_code=resp.status_code, body=body, wall_ms=wall_ms)
    except httpx.ConnectError as exc:
        return CaseResult(case=case, status_code=0, body={},
                          wall_ms=round((time.monotonic() - t0) * 1000, 1),
                          error=f"Cannot connect to orchestrator: {exc}")
    except httpx.TimeoutException:
        return CaseResult(case=case, status_code=0, body={},
                          wall_ms=round((time.monotonic() - t0) * 1000, 1),
                          error=f"Timed out after {timeout:.0f}s")
    except Exception as exc:
        return CaseResult(case=case, status_code=0, body={},
                          wall_ms=round((time.monotonic() - t0) * 1000, 1),
                          error=f"{type(exc).__name__}: {exc}")


async def set_node_offline(client: httpx.AsyncClient, base_url: str, node_id: str) -> None:
    """Call PATCH /api/v1/nodes/{id}/status?status=offline before running cases."""
    url = f"{base_url.rstrip('/')}/api/v1/nodes/{node_id}/status?status=offline"
    try:
        resp = await client.patch(url, timeout=5.0)
        if resp.status_code == 200:
            print(f"  {_y('⚠')}  Marked {_b(node_id)} as OFFLINE for this test run.\n")
        else:
            print(f"  {_r('✗')}  Could not mark {node_id} offline: HTTP {resp.status_code}\n")
    except Exception as exc:
        print(f"  {_r('✗')}  Could not reach orchestrator to set status: {exc}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

_LABEL_W = 18


def _trunc(s: str, n: int = 100) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _print_case(r: CaseResult, idx: int, total: int) -> None:
    case = r.case
    print(f"\n  {_b(f'[{idx}/{total}]')} {_c(case.name)}")
    print(_d(f"  {_LINE}"))

    if r.error:
        print(f"  {'QUERY':<{_LABEL_W}} {_trunc(case.payload['query'])}")
        print(f"  {'STATUS':<{_LABEL_W}} {_r('NETWORK ERROR')}")
        print(f"  {'DETAIL':<{_LABEL_W}} {_r(r.error)}")
        return

    body = r.body
    is_ok = r.status_code == 200

    print(f"  {'QUERY':<{_LABEL_W}} {_trunc(case.payload['query'])}")
    print(f"  {'INPUT TYPE':<{_LABEL_W}} {case.payload.get('input_type', 'text')}")

    if is_ok:
        cls = body.get("classification", {})
        routing = body.get("routing", {})

        # Confidence formatting
        conf_val = cls.get("confidence", 0)
        conf_str = f"{conf_val:.0%}" if isinstance(conf_val, (float, int)) else str(conf_val)
        method   = cls.get("classifier_method", "?")
        rule     = cls.get("matched_rule", "?")

        print(f"  {'TASK':<{_LABEL_W}} {cls.get('task_type', '?')}")
        print(f"  {'DIFFICULTY':<{_LABEL_W}} {cls.get('difficulty', '?')}")
        print(f"  {'CAPABILITY':<{_LABEL_W}} {cls.get('required_capability', '?')}")
        print(f"  {'CONFIDENCE':<{_LABEL_W}} {conf_str}  {_d(f'({method}: {rule})')}")

        node = body.get("selected_node", "?")
        routing_ok = node == case.expected_node
        node_label = (_g(node + " ✓") if routing_ok
                      else _y(f"{node} (expected {case.expected_node})"))

        fallback = routing.get("was_fallback", False)
        fallback_label = _y(" [FALLBACK]") if fallback else ""

        print(f"  {'SELECTED NODE':<{_LABEL_W}} {node_label}{fallback_label}")
        print(f"  {'REASON':<{_LABEL_W}} {_trunc(routing.get('reason', '?'), 90)}")
        print(f"  {'MODEL':<{_LABEL_W}} {body.get('selected_model', '?')}")
        print(f"  {'LATENCY':<{_LABEL_W}} {body.get('latency_ms', 0):.0f} ms  "
              f"{_d(f'wall: {r.wall_ms:.0f} ms')}")
        print(f"  {'RESPONSE':<{_LABEL_W}} {_trunc(body.get('response', ''))}")

    else:
        print(f"  {'HTTP STATUS':<{_LABEL_W}} {_r(str(r.status_code))}")
        print(f"  {'ERROR TYPE':<{_LABEL_W}} {body.get('error_type', '?')}")
        print(f"  {'DETAIL':<{_LABEL_W}} {_trunc(body.get('detail', '?'))}")
        routing = body.get("routing", {})
        if routing:
            print(f"  {'REASON':<{_LABEL_W}} {_trunc(routing.get('reason', '?'), 90)}")
        print(f"  {'LATENCY':<{_LABEL_W}} {body.get('latency_ms', 0):.0f} ms")


def _print_summary(results: List[CaseResult]) -> None:
    ok      = sum(1 for r in results if r.is_success)
    correct = sum(1 for r in results if r.routing_correct)
    errors  = sum(1 for r in results if r.error)
    total   = len(results)

    print(f"\n  {_b(_LINE)}")
    print(f"  {_b('ROUTING TEST SUMMARY')}")
    print(f"  {_b(_LINE)}")
    print(f"  Total cases      : {total}")
    print(f"  HTTP 200         : {_g(str(ok))}/{total}")
    print(f"  Routing correct  : {_g(str(correct))}/{ok or total}")
    print(f"  Network errors   : {(_r(str(errors)) if errors else _g('0'))}/{total}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="test_routing.py",
        description="Phase 3 routing tester — sends diverse requests and prints classification details.",
    )
    p.add_argument("--url", default="http://localhost:8000",
                   help="Orchestrator base URL (default: http://localhost:8000)")
    p.add_argument("--timeout", type=float, default=60.0,
                   help="Per-request timeout in seconds (default: 60)")
    p.add_argument("--offline", metavar="NODE_ID",
                   help="Mark a node offline before running (e.g. --offline NODE-4)")
    p.add_argument("--json", action="store_true",
                   help="Output raw JSON instead of human-readable report")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()

    print(_b(f"\n  SIH-2026 Phase 3 Routing Tester"))
    print(_d(f"  Target : {args.url}  |  timeout: {args.timeout}s"))
    print(_d(f"  Cases  : {len(ROUTING_CASES)}\n"))

    async with httpx.AsyncClient(headers={"Content-Type": "application/json"}) as client:

        if args.offline:
            await set_node_offline(client, args.url, args.offline.upper())

        results: List[CaseResult] = []
        for idx, case in enumerate(ROUTING_CASES, 1):
            r = await run_case(client, case, args.url, args.timeout)
            results.append(r)
            if not args.json:
                _print_case(r, idx, len(ROUTING_CASES))

    if args.json:
        out = []
        for r in results:
            out.append({
                "name": r.case.name,
                "expected_node": r.case.expected_node,
                "status_code": r.status_code,
                "wall_ms": r.wall_ms,
                "routing_correct": r.routing_correct,
                "error": r.error,
                "body": r.body,
            })
        print(json.dumps(out, indent=2, default=str))
    else:
        _print_summary(results)

    all_ok = all(r.is_success for r in results)
    return 0 if all_ok else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        sys.exit(130)
