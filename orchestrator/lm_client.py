"""
orchestrator/lm_client.py
──────────────────────────
Async LM Studio HTTP client for SIH-2026.

Responsibilities
----------------
* POST to ``/v1/chat/completions`` on the selected node.
* Enforce a per-request timeout.
* Translate all httpx errors into a typed ``LMClientError``.
* Return a ``LMResponse`` with the model's text and token usage.

This module does NOT make routing decisions — it only executes the call.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result / Error types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LMResponse:
    """Successful response from an LM Studio node."""
    content: str
    model: str
    latency_ms: float
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    tokens_total: Optional[int] = None


class LMClientError(Exception):
    """
    Raised when the LM Studio call cannot be completed.

    Attributes
    ----------
    error_type: one of "connection_error" | "timeout" | "http_error" |
                        "node_not_configured" | "empty_response" | "unknown"
    detail:     human-readable description
    latency_ms: how long was spent before the error occurred
    """

    def __init__(self, error_type: str, detail: str, latency_ms: float = 0.0):
        super().__init__(detail)
        self.error_type = error_type
        self.detail = detail
        self.latency_ms = latency_ms


# ─────────────────────────────────────────────────────────────────────────────
# Payload helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_messages(
    query: str,
    system_prompt: Optional[str] = None,
    context: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Construct the messages list for the chat/completions payload."""
    messages: List[Dict[str, Any]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if context:
        messages.extend(context)

    messages.append({"role": "user", "content": query})
    return messages


def _build_payload(
    model: str,
    query: str,
    system_prompt: Optional[str] = None,
    context: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the full chat/completions request body."""
    params = parameters or {}
    payload: Dict[str, Any] = {
        "messages": _build_messages(query, system_prompt, context),
        "max_tokens":   params.get("max_tokens",   512),
        "temperature":  params.get("temperature",  0.7),
        "top_p":        params.get("top_p",        0.95),
        "stream":       False,
    }
    # Only include model key when a non-empty model ID is available.
    # LM Studio uses the currently-loaded model when the field is absent.
    # Sending model="" causes HTTP 400 "Invalid model identifier".
    if model:
        payload["model"] = model
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Main client function
# ─────────────────────────────────────────────────────────────────────────────

async def call_node(
    *,
    endpoint: str,
    model: str,
    query: str,
    system_prompt: Optional[str] = None,
    context: Optional[List[Dict[str, Any]]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
    request_id: Optional[str] = None,
    attempt: Optional[int] = None,
    node_id: Optional[str] = None,
) -> LMResponse:
    """
    Send a chat-completion request to the LM Studio node at *endpoint*.

    Parameters
    ----------
    endpoint:      Base URL of the LM Studio server, e.g. "http://192.168.1.101:1234"
    model:         Model identifier to pass in the payload.
    query:         The user's query text.
    system_prompt: Optional system-level instruction injected before the user message.
    context:       Optional prior conversation turns (list of {role, content} dicts).
    parameters:    Optional model overrides (temperature, max_tokens, top_p…).
    timeout:       Per-request timeout in seconds.

    Returns
    -------
    LMResponse on success.

    Raises
    ------
    LMClientError with a typed error_type on any failure.
    """
    if not endpoint or not endpoint.strip():
        raise LMClientError(
            error_type="node_not_configured",
            detail="Node endpoint is not configured. Set the corresponding URL in .env.",
        )

    chat_url = f"{endpoint.rstrip('/')}/v1/chat/completions"
    payload = _build_payload(model, query, system_prompt, context, parameters)

    prefix = f"[{request_id}] " if request_id else ""
    attempt_str = f" (Attempt {attempt})" if attempt else ""
    n_id = f" (node={node_id})" if node_id else ""
    
    logger.info("%sLM call → %s%s%s  model=%s  query_len=%d", prefix, chat_url, n_id, attempt_str, model, len(query))

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(
            headers={"Content-Type": "application/json"},
            follow_redirects=True,
        ) as client:
            resp = await client.post(chat_url, json=payload, timeout=timeout)

        latency_ms = round((time.monotonic() - t0) * 1000, 1)

        if resp.status_code != 200:
            raise LMClientError(
                error_type="http_error",
                detail=f"Node returned HTTP {resp.status_code}: {resp.text[:200]}",
                latency_ms=latency_ms,
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise LMClientError(
                error_type="empty_response",
                detail="Node returned an empty choices list.",
                latency_ms=latency_ms,
            )

        content = choices[0].get("message", {}).get("content", "").strip()
        usage = data.get("usage", {})
        actual_model = data.get("model", model)

        logger.info(
            "%sLM response received  node=%s  latency=%.1f ms  tokens=%s",
            prefix, endpoint, latency_ms, usage.get("total_tokens"),
        )

        return LMResponse(
            content=content,
            model=actual_model,
            latency_ms=latency_ms,
            tokens_prompt=usage.get("prompt_tokens"),
            tokens_completion=usage.get("completion_tokens"),
            tokens_total=usage.get("total_tokens"),
        )

    except LMClientError:
        raise  # already typed — re-raise as-is

    except httpx.ConnectError as exc:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        raise LMClientError(
            error_type="connection_error",
            detail=f"Cannot connect to node at {endpoint}. Is LM Studio running? ({exc})",
            latency_ms=latency_ms,
        ) from exc

    except httpx.TimeoutException as exc:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        raise LMClientError(
            error_type="timeout",
            detail=f"Node at {endpoint} did not respond within {timeout:.0f}s.",
            latency_ms=latency_ms,
        ) from exc

    except Exception as exc:
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        raise LMClientError(
            error_type="unknown",
            detail=f"{type(exc).__name__}: {exc}",
            latency_ms=latency_ms,
        ) from exc
