#!/usr/bin/env python
"""
scripts/test_chroma.py
───────────────────────
SIH-2026  Phase 4  ChromaDB Verification Script
================================================

Verifies that:
  1. The ChromaDB server is reachable.
  2. The conversation_memory collection exists.
  3. A test interaction can be added.
  4. A semantic search returns the just-added interaction.
  5. Metadata (user_id, node_id, model) is stored correctly.

Does NOT require the orchestrator to be running — connects directly
to ChromaDB via the HTTP client.

Usage
-----
  docker compose up -d     # ChromaDB must be running

  python scripts/test_chroma.py
  python scripts/test_chroma.py --host localhost --port 8001
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from datetime import datetime, timezone

_PASS = "\033[92m✓ PASS\033[0m"
_FAIL = "\033[91m✗ FAIL\033[0m"
_INFO = "\033[96m  ●\033[0m"
_HEAD = "\033[1m"
_RST  = "\033[0m"


def h(s: str) -> str:
    return f"{_HEAD}{s}{_RST}"


async def run(host: str, port: int, collection: str) -> int:
    failures = 0

    print(h(f"\n  SIH-2026 Phase 4 — ChromaDB Verification"))
    print(f"  Target : http://{host}:{port}  collection={collection}\n")

    # ── Step 1: Connect ────────────────────────────────────────────────────────
    print(f"{_INFO} Connecting to ChromaDB ...")
    try:
        import chromadb
        client = chromadb.HttpClient(host=host, port=port)
        client.heartbeat()
        print(f"{_PASS}  ChromaDB server is reachable.")
    except Exception as exc:
        print(f"{_FAIL}  Cannot connect to ChromaDB: {exc}")
        print("        Make sure 'docker compose up -d' is running.")
        return 1

    # ── Step 2: Get / create collection ───────────────────────────────────────
    print(f"\n{_INFO} Getting collection '{collection}' ...")
    try:
        col = client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"{_PASS}  Collection ready. Current count: {col.count()} documents.")
    except Exception as exc:
        print(f"{_FAIL}  Collection error: {exc}")
        return 1

    # ── Step 3: Add a test interaction ────────────────────────────────────────
    test_rid   = f"chroma_test_{uuid.uuid4().hex[:8]}"
    test_uid   = "chroma_test_user_001"
    test_query = "Explain what a neural network is."
    test_resp  = "A neural network is a computational model inspired by the human brain."
    test_doc   = f"{test_query}\n\n{test_resp}"
    test_meta  = {
        "user_id":       test_uid,
        "session_id":    "test_session",
        "node_id":       "NODE-TEXT",
        "model":         "test-model-7b",
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "query_preview": test_query[:120],
    }

    print(f"\n{_INFO} Adding test interaction (id={test_rid}) ...")
    try:
        col.add(documents=[test_doc], metadatas=[test_meta], ids=[test_rid])
        print(f"{_PASS}  Document added. Collection count: {col.count()}")
    except Exception as exc:
        print(f"{_FAIL}  add() failed: {exc}")
        failures += 1

    # ── Step 4: Semantic search ────────────────────────────────────────────────
    print(f"\n{_INFO} Running semantic search for: 'what is a neural network?' ...")
    try:
        results = col.query(
            query_texts=["what is a neural network?"],
            n_results=1,
            where={"user_id": test_uid},
            include=["documents", "metadatas", "distances"],
        )
        ids       = results["ids"][0]
        docs      = results["documents"][0]
        metas     = results["metadatas"][0]
        distances = results["distances"][0]

        if ids and test_rid in ids:
            score = round(1.0 - float(distances[0]), 4)
            print(f"{_PASS}  Search returned our test document:")
            print(f"        id={ids[0]}  score={score:.4f}")
            print(f"        metadata: node_id={metas[0].get('node_id')}  model={metas[0].get('model')}")
        else:
            print(f"{_FAIL}  Expected id '{test_rid}' not in results: {ids}")
            failures += 1
    except Exception as exc:
        print(f"{_FAIL}  query() failed: {exc}")
        failures += 1

    # ── Step 5: Verify metadata ────────────────────────────────────────────────
    print(f"\n{_INFO} Verifying metadata fields ...")
    if metas:
        meta = metas[0]
        for key in ("user_id", "session_id", "node_id", "model", "timestamp", "query_preview"):
            if key in meta:
                print(f"        {key:<20} = {str(meta[key])[:60]}")
            else:
                print(f"{_FAIL}  Missing metadata key: '{key}'")
                failures += 1

    # ── Step 6: Clean up test document ────────────────────────────────────────
    print(f"\n{_INFO} Cleaning up test document ...")
    try:
        col.delete(ids=[test_rid])
        print(f"{_PASS}  Test document deleted. Collection count: {col.count()}")
    except Exception as exc:
        print(f"        (cleanup failed, not critical): {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  {'─'*55}")
    if failures == 0:
        print(f"  {_PASS}  All ChromaDB checks passed.\n")
    else:
        print(f"  {_FAIL}  {failures} check(s) failed.\n")

    return 0 if failures == 0 else 1


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 4 ChromaDB verifier")
    p.add_argument("--host",       default="localhost")
    p.add_argument("--port",       type=int, default=8001)
    p.add_argument("--collection", default="conversation_memory")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    sys.exit(asyncio.run(run(args.host, args.port, args.collection)))
