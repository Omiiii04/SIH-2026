#!/usr/bin/env python
"""
scripts/test_orchestrator.py
─────────────────────────────
SIH-2026  Orchestrator CLI Tester
===================================

Sends a diverse set of test requests to the running orchestrator's
POST /api/v1/query endpoint and prints a detailed report for each one.

Output format (per request):
  ─────────────────────────────────────────────────────────────
  INPUT        What is a transformer in deep learning?
  TYPE         text
  CLASSIFICATION  NODE-TEXT  (rule: default_fallback)
  SELECTED NODE   NODE-TEXT
  MODEL           google/gemma-4-e4b
  LATENCY         342 ms
  RESPONSE        Transformers are…
  ─────────────────────────────────────────────────────────────

Usage
-----
  # Orchestrator must be running:
  uvicorn orchestrator.main:app --reload --port 8000

  python scripts/test_orchestrator.py
  python scripts/test_orchestrator.py --url http://localhost:8000
  python scripts/test_orchestrator.py --timeout 20
  python scripts/test_orchestrator.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

# ── Windows UTF-8 fix (inside __main__ only — see bottom of file) ─────────────


# ─────────────────────────────────────────────────────────────────────────────
# ANSI helpers
# ─────────────────────────────────────────────────────────────────────────────

_USE_COLOUR = sys.stdout.isatty()

def _green(s: str)  -> str: return f"\033[92m{s}\033[0m" if _USE_COLOUR else s
def _red(s: str)    -> str: return f"\033[91m{s}\033[0m" if _USE_COLOUR else s
def _yellow(s: str) -> str: return f"\033[93m{s}\033[0m" if _USE_COLOUR else s
def _cyan(s: str)   -> str: return f"\033[96m{s}\033[0m" if _USE_COLOUR else s
def _bold(s: str)   -> str: return f"\033[1m{s}\033[0m"  if _USE_COLOUR else s
def _dim(s: str)    -> str: return f"\033[2m{s}\033[0m"  if _USE_COLOUR else s

_RULE = "─" * 70


# ─────────────────────────────────────────────────────────────────────────────
# Test cases
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    name: str
    payload: Dict[str, Any]
    expect_node: str          # expected selected_node value
    expect_success: bool = True


TEST_CASES: List[TestCase] = [
    TestCase(
        name="General Text Query",
        payload={
            "user_id": "tester_001",
            "query": "What is a transformer model in deep learning? Explain briefly.",
            "input_type": "text",
        },
        expect_node="NODE-TEXT",
    ),
    TestCase(
        name="Code Generation",
        payload={
            "user_id": "tester_002",
            "query": "Write a Python function that checks if a string is a palindrome.",
            "input_type": "text",
        },
        expect_node="NODE-CODE",
    ),
    TestCase(
        name="Reasoning / Analysis",
        payload={
            "user_id": "tester_003",
            "query": "Analyse step by step why the transformer architecture outperforms RNNs for NLP.",
            "input_type": "text",
        },
        expect_node="NODE-REASONING",
    ),
    TestCase(
        name="Document Retrieval",
        payload={
            "user_id": "tester_004",
            "query": "Search the document and retrieve the key findings from the introduction section.",
            "input_type": "retrieval",
        },
        expect_node="NODE-RAG",
    ),
    TestCase(
        name="Code Debug",
        payload={
            "user_id": "tester_005",
            "query": "Debug this Python code: for i in range(10) print(i)",
            "input_type": "code",
        },
        expect_node="NODE-CODE",
    ),
    TestCase(
        name="General Knowledge",
        payload={
            "user_id": "tester_006",
            "query": "Tell me about the history of artificial intelligence.",
            "input_type": "text",
        },
        expect_node="NODE-TEXT",
    ),
    TestCase(
        name="Logical Reasoning",
        payload={
            "user_id": "tester_007",
            "query": "If all mammals are warm-blooded and whales are mammals, infer what follows.",
            "input_type": "reasoning",
        },
        expect_node="NODE-REASONING",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Single request runner
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    test_case: TestCase
    status_code: int
    body: Dict[str, Any]
    wall_time_ms: float
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status_code == 200

    @property
    def routing_correct(self) -> bool:
        if not self.is_success:
            return False
        return self.body.get("selected_node") == self.test_case.expect_node


async def run_test_case(
    client: httpx.AsyncClient,
    tc: TestCase,
    base_url: str,
    timeout: float,
) -> TestResult:
    url = f"{base_url.rstrip('/')}/api/v1/query"
    t0 = time.monotonic()
    try:
        resp = await client.post(url, json=tc.payload, timeout=timeout)
        wall_ms = round((time.monotonic() - t0) * 1000, 1)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return TestResult(test_case=tc, status_code=resp.status_code, body=body, wall_time_ms=wall_ms)
    except httpx.ConnectError as exc:
        wall_ms = round((time.monotonic() - t0) * 1000, 1)
        return TestResult(
            test_case=tc, status_code=0, body={},
            wall_time_ms=wall_ms,
            error=f"Cannot connect to orchestrator: {exc}",
        )
    except httpx.TimeoutException:
        wall_ms = round((time.monotonic() - t0) * 1000, 1)
        return TestResult(
            test_case=tc, status_code=0, body={},
            wall_time_ms=wall_ms,
            error=f"Request timed out after {timeout:.0f}s",
        )
    except Exception as exc:
        wall_ms = round((time.monotonic() - t0) * 1000, 1)
        return TestResult(
            test_case=tc, status_code=0, body={},
            wall_time_ms=wall_ms,
            error=f"{type(exc).__name__}: {exc}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def _truncate(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[:n] + "…"


def print_result(r: TestResult, index: int, total: int) -> None:
    tc = r.test_case
    print(f"\n  {_bold(f'[{index}/{total}]')} {_cyan(tc.name)}")
    print(_dim(f"  {_RULE}"))

    # ── network error ─────────────────────────────────────────────────────────
    if r.error:
        print(f"  {'INPUT':<16} {tc.payload['query'][:80]}")
        print(f"  {'STATUS':<16} {_red('NETWORK ERROR')}")
        print(f"  {'DETAIL':<16} {_red(r.error)}")
        return

    body = r.body
    is_ok   = r.status_code == 200
    status  = _green("SUCCESS") if is_ok else _red(f"ERROR (HTTP {r.status_code})")

    print(f"  {'INPUT':<16} {_truncate(tc.payload['query'])}")
    print(f"  {'TYPE':<16} {tc.payload.get('input_type', 'text')}")

    if is_ok:
        cls = body.get("classification", {})
        print(f"  {'CLASSIFICATION':<16} {cls.get('node_type', '?').upper():<14}  "
              f"{_dim('rule: ' + str(cls.get('matched_rule', '?')))}")
        routing_ok = body.get("selected_node") == tc.expect_node
        node_label = body.get("selected_node", "?")
        if routing_ok:
            node_label = _green(node_label + " ✓")
        else:
            node_label = _yellow(f"{node_label} (expected {tc.expect_node})")
        print(f"  {'SELECTED NODE':<16} {node_label}")
        print(f"  {'MODEL':<16} {body.get('selected_model', '?')}")
        print(f"  {'LATENCY':<16} {body.get('latency_ms', 0):.0f} ms  "
              f"{_dim(f'(wall: {r.wall_time_ms:.0f} ms)')}")
        print(f"  {'RESPONSE':<16} {_truncate(body.get('response', ''))}")
    else:
        print(f"  {'STATUS':<16} {status}")
        print(f"  {'ERROR TYPE':<16} {body.get('error_type', '?')}")
        print(f"  {'DETAIL':<16} {_truncate(body.get('detail', '?'))}")
        print(f"  {'NODE':<16} {body.get('selected_node', '?')}")
        print(f"  {'LATENCY':<16} {body.get('latency_ms', 0):.0f} ms")


def print_summary(results: List[TestResult]) -> None:
    ok      = sum(1 for r in results if r.is_success)
    routing = sum(1 for r in results if r.routing_correct)
    errors  = sum(1 for r in results if r.error)
    total   = len(results)

    print(f"\n  {_bold('─' * 70)}")
    print(f"  {_bold('SUMMARY')}")
    print(f"  {_bold('─' * 70)}")
    print(f"  Requests sent    : {total}")
    print(f"  Successful (200) : {_green(str(ok))}/{total}")
    print(f"  Routing correct  : {_green(str(routing))}/{ok if ok else total}")
    print(f"  Network errors   : {(_red(str(errors)) if errors else _green('0'))}/{total}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="test_orchestrator.py",
        description="Send test requests to the SIH-2026 orchestrator and report results.",
    )
    p.add_argument(
        "--url", default="http://localhost:8000",
        help="Orchestrator base URL (default: http://localhost:8000)",
    )
    p.add_argument(
        "--timeout", type=float, default=60.0,
        help="Per-request timeout in seconds (default: 60)",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Output raw JSON results instead of the human-readable report",
    )
    return p.parse_args()


async def main() -> int:
    args = parse_args()

    print(_bold(f"\n  SIH-2026 Orchestrator Tester"))
    print(_dim(f"  Target: {args.url}  |  timeout: {args.timeout}s"))
    print(_dim(f"  Test cases: {len(TEST_CASES)}\n"))

    async with httpx.AsyncClient(
        headers={"Content-Type": "application/json"},
    ) as client:
        results: List[TestResult] = []
        for i, tc in enumerate(TEST_CASES, 1):
            r = await run_test_case(client, tc, args.url, args.timeout)
            results.append(r)
            if not args.json:
                print_result(r, i, len(TEST_CASES))

    if args.json:
        output = []
        for r in results:
            output.append({
                "name": r.test_case.name,
                "status_code": r.status_code,
                "wall_time_ms": r.wall_time_ms,
                "error": r.error,
                "body": r.body,
            })
        print(json.dumps(output, indent=2, default=str))
    else:
        print_summary(results)

    # Exit 0 if all succeeded
    return 0 if all(r.is_success for r in results) else 1


if __name__ == "__main__":
    # ── Force UTF-8 on Windows consoles ──────────────────────────────────────
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    try:
        code = asyncio.run(main())
        sys.exit(code)
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        sys.exit(130)
