#!/usr/bin/env python
"""
scripts/test_nodes.py
─────────────────────
SIH-2026 Distributed Node Connectivity Tester
==============================================

Tests connectivity from Laptop 6 (Orchestrator) to each LM Studio
worker node.  Safe to run at any time — offline nodes are reported
clearly and the program NEVER crashes because of one unreachable node.

Usage
-----
    # From the repo root (with venv active):
    python scripts/test_nodes.py

    # Quick-check only (no inference test):
    python scripts/test_nodes.py --no-inference

    # Test a single node:
    python scripts/test_nodes.py --node NODE-TEXT

    # Set custom timeout (seconds):
    python scripts/test_nodes.py --timeout 5

Output example
--------------
    ╔══════════════════════════════════════════════════════════════════╗
    ║          SIH-2026  Node Connectivity Report                      ║
    ╚══════════════════════════════════════════════════════════════════╝
    NODE-TEXT        ONLINE    320 ms   llama-3-8b-instruct
    NODE-VISION      OFFLINE   —        (not configured)
    NODE-REASONING   OFFLINE   —        (not configured)
    NODE-CODE        OFFLINE   —        (not configured)
    NODE-RAG         OFFLINE   —        (not configured)
    ──────────────────────────────────────────────────────────────────
    Reachable: 1 / 5   |   Offline: 4 / 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx

# ── Make sure the repo root is on sys.path so we can import our packages ──────
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.config import list_node_configs, NodeConfig


# ─────────────────────────────────────────────────────────────────────────────
# ANSI colour helpers  (disabled automatically on Windows when not supported)
# ─────────────────────────────────────────────────────────────────────────────

_USE_COLOUR = sys.stdout.isatty()

def _green(s: str) -> str:  return f"\033[92m{s}\033[0m" if _USE_COLOUR else s
def _red(s: str) -> str:    return f"\033[91m{s}\033[0m" if _USE_COLOUR else s
def _yellow(s: str) -> str: return f"\033[93m{s}\033[0m" if _USE_COLOUR else s
def _cyan(s: str) -> str:   return f"\033[96m{s}\033[0m" if _USE_COLOUR else s
def _bold(s: str) -> str:   return f"\033[1m{s}\033[0m"  if _USE_COLOUR else s
def _dim(s: str) -> str:    return f"\033[2m{s}\033[0m"  if _USE_COLOUR else s


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NodeResult:
    node_id: str
    node_name: str
    endpoint: str
    is_configured: bool

    # Populated after probing
    is_online: bool = False
    latency_ms: Optional[float] = None
    model_loaded: Optional[str] = None
    inference_ok: Optional[bool] = None
    inference_response: Optional[str] = None
    inference_latency_ms: Optional[float] = None
    error: Optional[str] = None

    @property
    def status_label(self) -> str:
        if not self.is_configured:
            return _yellow("NOT CONFIGURED")
        return _green("ONLINE") if self.is_online else _red("OFFLINE")

    @property
    def latency_label(self) -> str:
        if self.latency_ms is None:
            return _dim("—")
        return f"{self.latency_ms:.0f} ms"


# ─────────────────────────────────────────────────────────────────────────────
# Core probe functions
# ─────────────────────────────────────────────────────────────────────────────

async def probe_reachability(
    client: httpx.AsyncClient,
    cfg: NodeConfig,
    timeout: float,
) -> NodeResult:
    """
    Step 1 — GET /v1/models to check reachability and list loaded models.
    Never raises; all errors are captured in NodeResult.error.
    """
    result = NodeResult(
        node_id=cfg.node_id,
        node_name=cfg.node_name,
        endpoint=cfg.endpoint,
        is_configured=cfg.is_configured,
    )

    if not cfg.is_configured:
        result.error = "Endpoint not configured in .env"
        return result

    t0 = time.monotonic()
    try:
        resp = await client.get(cfg.models_url, timeout=timeout)
        latency_ms = (time.monotonic() - t0) * 1000
        result.latency_ms = round(latency_ms, 1)

        if resp.status_code == 200:
            result.is_online = True
            data = resp.json()
            models = data.get("data", [])
            if models:
                result.model_loaded = models[0].get("id", "unknown")
        else:
            result.error = f"HTTP {resp.status_code}"

    except httpx.ConnectError as exc:
        result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result.error = f"Connection refused — is LM Studio running? ({exc})"
    except httpx.TimeoutException:
        result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result.error = f"Timed out after {timeout:.0f}s"
    except Exception as exc:
        result.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result.error = f"Unexpected error: {type(exc).__name__}: {exc}"

    return result


async def probe_inference(
    client: httpx.AsyncClient,
    cfg: NodeConfig,
    result: NodeResult,
    timeout: float,
) -> None:
    """
    Step 2 — POST /v1/chat/completions with a tiny test prompt.
    Only called when the node is already ONLINE.
    Modifies *result* in-place.
    """
    payload = {
        "model": result.model_loaded or cfg.model_name,
        "messages": [{"role": "user", "content": cfg.test_prompt}],
        "max_tokens": 64,
        "temperature": 0.1,
        "stream": False,
    }

    t0 = time.monotonic()
    try:
        resp = await client.post(cfg.chat_url, json=payload, timeout=timeout)
        result.inference_latency_ms = round((time.monotonic() - t0) * 1000, 1)

        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "").strip()
                result.inference_ok = True
                result.inference_response = content[:120]  # truncate for display
            else:
                result.inference_ok = False
                result.error = "Empty choices in response"
        else:
            result.inference_ok = False
            result.error = f"Inference HTTP {resp.status_code}: {resp.text[:100]}"

    except httpx.TimeoutException:
        result.inference_ok = False
        result.inference_latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result.error = f"Inference timed out after {timeout:.0f}s"
    except Exception as exc:
        result.inference_ok = False
        result.inference_latency_ms = round((time.monotonic() - t0) * 1000, 1)
        result.error = f"Inference error: {type(exc).__name__}: {exc}"


async def test_node(
    cfg: NodeConfig,
    timeout: float,
    run_inference: bool,
) -> NodeResult:
    """
    Full test pipeline for one node: reachability → (optionally) inference.
    Uses a single httpx.AsyncClient per node for connection reuse.
    """
    async with httpx.AsyncClient(
        headers={"Content-Type": "application/json"},
        follow_redirects=True,
    ) as client:
        result = await probe_reachability(client, cfg, timeout)

        if result.is_online and run_inference:
            await probe_inference(client, cfg, result, timeout * 3)  # inference gets 3× timeout

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Concurrent runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_tests(
    nodes: List[NodeConfig],
    timeout: float,
    run_inference: bool,
) -> List[NodeResult]:
    """Test all nodes concurrently and return results in original order."""
    tasks = [test_node(cfg, timeout, run_inference) for cfg in nodes]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

_BORDER = "─" * 70
_HEADER = "═" * 70

def print_summary_table(results: List[NodeResult]) -> None:
    """Print the compact one-line-per-node summary table."""
    print()
    print(_bold(f"╔{_HEADER}╗"))
    print(_bold(f"║{'SIH-2026  Node Connectivity Report':^70}║"))
    print(_bold(f"╚{_HEADER}╝"))

    col_id  = 16
    col_st  = 18
    col_lat = 10
    col_mod = 26

    header = (
        f"  {'NODE-ID':<{col_id}}"
        f"{'STATUS':<{col_st}}"
        f"{'LATENCY':<{col_lat}}"
        f"{'MODEL':<{col_mod}}"
    )
    print(_dim(header))
    print(_dim(f"  {_BORDER}"))

    for r in results:
        node_id  = f"{r.node_id:<{col_id}}"
        status   = r.status_label
        latency  = r.latency_label
        model    = r.model_loaded or _dim("(not configured)" if not r.is_configured else "—")

        # Strip ANSI codes for padding calculation
        raw_status_len = len("ONLINE") if r.is_online else (
            len("NOT CONFIGURED") if not r.is_configured else len("OFFLINE")
        )
        padding = col_st - raw_status_len

        print(f"  {node_id}{status}{' ' * padding}{latency:<{col_lat}}{model}")

    print(_dim(f"  {_BORDER}"))

    online  = sum(1 for r in results if r.is_online)
    total   = len(results)
    offline = total - online
    cfg_missing = sum(1 for r in results if not r.is_configured)

    reachable_label = _green(f"{online}/{total}") if online == total else _yellow(f"{online}/{total}")
    offline_label   = _red(str(offline)) if offline else _green("0")

    print(
        f"\n  Reachable: {reachable_label}   "
        f"Offline: {offline_label}/{total}   "
        f"Not configured: {_dim(str(cfg_missing))}/{total}"
    )


def print_inference_results(results: List[NodeResult]) -> None:
    """Print inference test results for ONLINE nodes."""
    from nodes.config import NODE_CONFIGS

    online = [r for r in results if r.is_online]
    if not online:
        print(_yellow("\n  No online nodes to run inference tests against."))
        return

    print(_bold(f"\n  Inference Test Results"))
    print(_dim(f"  {_BORDER}"))

    for r in online:
        if r.inference_ok is None:
            continue  # inference was skipped
        status = _green("✓ PASS") if r.inference_ok else _red("✗ FAIL")
        lat = f"{r.inference_latency_ms:.0f} ms" if r.inference_latency_ms else "—"
        cfg = NODE_CONFIGS.get(r.node_id)
        prompt_preview = cfg.test_prompt if cfg else "—"
        print(f"\n  {_bold(r.node_id)} ({r.node_name})")
        print(f"    Status  : {status}  ({lat})")
        print(f"    Prompt  : {_dim(prompt_preview)}")
        if r.inference_response:
            print(f"    Response: {r.inference_response}")
        if not r.inference_ok and r.error:
            print(f"    Error   : {_red(r.error)}")



def print_error_details(results: List[NodeResult]) -> None:
    """Print error details for OFFLINE or FAILED nodes."""
    failures = [r for r in results if not r.is_online and r.is_configured]
    if not failures:
        return
    print(_bold(f"\n  Error Details (Offline Nodes)"))
    print(_dim(f"  {_BORDER}"))
    for r in failures:
        print(f"  {_bold(r.node_id)}: {_red(r.error or 'Unknown error')}")
        print(f"    Endpoint: {r.endpoint}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="test_nodes.py",
        description="Test connectivity from the orchestrator to all LM Studio worker nodes.",
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0,
        help="Connection timeout per node in seconds (default: 10)",
    )
    parser.add_argument(
        "--no-inference", action="store_true",
        help="Skip the inference test — only check reachability and model list",
    )
    parser.add_argument(
        "--node", type=str, default=None,
        metavar="NODE_ID",
        help="Test a single node by ID, e.g. --node NODE-TEXT",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON (for scripting / CI)",
    )
    return parser.parse_args()


async def main() -> int:
    """Main async entry point. Returns exit code (0 = all configured nodes online)."""
    args = parse_args()

    all_nodes = list_node_configs()  # sorted by laptop_id

    if args.node:
        nodes = [n for n in all_nodes if n.node_id == args.node.upper()]
        if not nodes:
            valid = ", ".join(n.node_id for n in all_nodes)
            print(f"Unknown node '{args.node}'. Valid options: {valid}")
            return 2

    else:
        nodes = all_nodes

    run_inference = not args.no_inference

    print(_bold(f"\n  SIH-2026 Node Tester  |  timeout={args.timeout}s  |  inference={'yes' if run_inference else 'no'}"))
    print(_dim(f"  Probing {len(nodes)} node(s) concurrently…\n"))

    results = await run_tests(nodes, timeout=args.timeout, run_inference=run_inference)

    if args.json:
        output = []
        for r in results:
            output.append({
                "node_id": r.node_id,
                "node_name": r.node_name,
                "endpoint": r.endpoint,
                "is_configured": r.is_configured,
                "is_online": r.is_online,
                "latency_ms": r.latency_ms,
                "model_loaded": r.model_loaded,
                "inference_ok": r.inference_ok,
                "inference_response": r.inference_response,
                "inference_latency_ms": r.inference_latency_ms,
                "error": r.error,
            })
        print(json.dumps(output, indent=2))
        return 0

    print_summary_table(results)
    if run_inference:
        print_inference_results(results)
    print_error_details(results)
    print()

    # Exit code: 0 only if all *configured* nodes are online
    configured = [r for r in results if r.is_configured]
    all_online = all(r.is_online for r in configured)
    return 0 if all_online else 1


if __name__ == "__main__":
    # ── Force UTF-8 on Windows consoles (avoids cp1252 UnicodeEncodeError) ──
    if sys.platform == "win32":
        import io as _io
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
        sys.exit(130)
