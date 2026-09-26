"""
orchestrator/env_nodes.py
─────────────────────────
Parse NODE_N_URL (+ optional NAME/PRIORITY/ENABLED) from the .env file.

This is the single source of truth for desired node configuration.
All other modules import `parse_node_configs()` from here.

Design:
  - Reads from the actual .env file (via python-dotenv) so that
    POST /api/v1/nodes/sync-config picks up .env changes without
    modifying Python source code or restarting the process.
  - Falls back to os.environ when .env cannot be located (CI, containers).
  - Accepts an explicit `env` dict for unit tests.
  - Handles sparse indexes: NODE_1, NODE_4, NODE_9 → 3 nodes.
  - No hardcoded maximum.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

# Matches NODE_<digits>_URL (case-insensitive)
_NODE_URL_RE = re.compile(r'^NODE_(\d+)_URL$', re.IGNORECASE)

# Location of the .env file — resolved relative to this file's project root.
_ENV_FILE = Path(__file__).parent.parent / ".env"


@dataclass
class NodeEnvConfig:
    """
    Parsed configuration for one node from .env.

    Attributes
    ----------
    index:    numeric index from the env key (1, 2, 8, 14 …)
    node_id:  deterministic identifier "NODE-N" — stable across restarts
    url:      normalized base URL (no trailing slash, http/https only)
    name:     NODE_N_NAME, default "Node N"
    priority: NODE_N_PRIORITY, default 1
    enabled:  NODE_N_ENABLED, default True
    """
    index:    int
    node_id:  str
    url:      str
    name:     str   = ""
    priority: int   = 1
    enabled:  bool  = True


def parse_node_configs(env: dict[str, str] | None = None) -> list[NodeEnvConfig]:
    """
    Discover all NODE_N_URL entries and return sorted NodeEnvConfig list.

    Parameters
    ----------
    env : optional dict for testing — bypasses file/os.environ lookup.

    Reading priority (when env is None):
      1. .env file (re-read on every call so sync-config picks up edits)
      2. os.environ (fallback for CI / container environments)
    """
    if env is not None:
        source = env
    else:
        source = _load_env_file()

    configs: list[NodeEnvConfig] = []

    for key, value in source.items():
        m = _NODE_URL_RE.match(key)
        if not m:
            continue
        idx = int(m.group(1))
        url = _normalize_url(value)
        if not url:
            continue  # empty or invalid scheme — skip silently

        name     = source.get(f"NODE_{idx}_NAME", f"Node {idx}")
        priority = _safe_int(source.get(f"NODE_{idx}_PRIORITY", "1"), default=1)
        enabled  = _parse_bool(source.get(f"NODE_{idx}_ENABLED", "true"))

        configs.append(NodeEnvConfig(
            index=idx,
            node_id=f"NODE-{idx}",
            url=url,
            name=name,
            priority=priority,
            enabled=enabled,
        ))

    return sorted(configs, key=lambda c: c.index)


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────

def _load_env_file() -> dict[str, str]:
    """
    Load .env file values merged with os.environ.
    os.environ takes precedence (allows CI to override .env).
    Returns a flat str→str dict.
    """
    merged: dict[str, str] = {}

    if _ENV_FILE.is_file():
        try:
            from dotenv import dotenv_values  # provided by python-dotenv (pydantic-settings dep)
            file_vals = dotenv_values(_ENV_FILE)
            merged.update({k: v for k, v in file_vals.items() if v is not None})
        except ImportError:
            pass  # python-dotenv not available; fall through to os.environ

    # os.environ wins over .env file values (CI/container override)
    merged.update(os.environ)
    return merged


def _normalize_url(raw: str) -> str:
    """Strip whitespace and trailing slash; reject non-http(s) schemes."""
    url = raw.strip().rstrip("/")
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    return url


def _safe_int(value: str, *, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _parse_bool(value: str) -> bool:
    return value.strip().lower() not in ("false", "0", "no", "off")
