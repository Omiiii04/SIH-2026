"""
orchestrator/scheduler.py
Phase 6 Intelligent Scheduler
"""

import logging
from typing import List, Tuple

from orchestrator.schemas import ClassificationResult, NodeRegistryEntry
from orchestrator.node_registry import get_registry
from orchestrator.monitor import get_node_states, NodeState

logger = logging.getLogger(__name__)

def discover_capabilities(
    entry: NodeRegistryEntry,
    model: str,
    model_meta: dict | None = None,
) -> set[str]:
    """
    Map model metadata into capabilities.
    Precedence:
      1. Explicit LM Studio native capability metadata (lmstudio_metadata)
      2. Configured admin override (entry.capability)
      3. Inferred substring heuristics (only when explicit metadata is unavailable)
    """
    caps = set()
    model_lower = (model or "").lower()

    # Look up metadata from monitor state if not passed directly
    if model_meta is None:
        states = get_node_states()
        state = states.get(entry.node_id)
        if state and state.models_metadata:
            model_meta = state.models_metadata.get(model)

    # 1. Authoritative LM Studio metadata
    if model_meta and model_meta.get("capability_source") == "lmstudio_metadata":
        explicit_caps = model_meta.get("capabilities", {})
        if explicit_caps.get("vision") is True:
            caps.update(["vision", "ocr", "image_reasoning"])
        if explicit_caps.get("trained_for_tool_use") is True:
            caps.update(["tool_use"])
        if explicit_caps.get("reasoning"):
            caps.update(["reasoning", "math", "logical_inference"])
        if model_lower:
            caps.update(["text", "text_generation", "summarization", "structured_output"])
        # Explicit metadata is authoritative — do not run string heuristics
        return caps

    # 2. Configured override (e.g. mock entry in unit tests / admin override)
    if entry.capability == "vision":
        caps.update(["vision", "ocr", "image_reasoning"])
    elif entry.capability == "coding":
        caps.update(["coding", "code_review", "debugging"])
    elif entry.capability == "reasoning":
        caps.update(["reasoning", "math", "logical_inference"])
    elif entry.capability == "embedding/retrieval":
        caps.update(["retrieval", "embeddings", "embedding/retrieval"])

    # 3. Inferred heuristics (fallback only when explicit metadata unavailable)
    if any(x in model_lower for x in ["vision", "llava", "pixtral", "image", "vl"]):
        caps.update(["vision", "ocr", "image_reasoning"])
    if any(x in model_lower for x in ["code", "coder", "starcoder", "deepseek-coder"]):
        caps.update(["coding", "code_review", "debugging"])
    if any(x in model_lower for x in ["math", "reasoning", "qwen2-math"]):
        caps.update(["reasoning", "math", "logical_inference"])
    if any(x in model_lower for x in ["embed", "nomic", "retrieval"]):
        caps.update(["embeddings", "retrieval", "embedding/retrieval"])

    if model_lower or entry.capability == "text":
        caps.update(["text", "text_generation", "summarization", "structured_output"])

    return caps


def select_best_candidates(
    cls: ClassificationResult,
    skip_ids: set[str] = None
) -> List[Tuple[NodeRegistryEntry, str, float, str]]:
    """
    Returns list of eligible candidates sorted by score (lowest is best).
    Tuple: (Node, ModelName, Score, Reason)

    CRITICAL: Capability filtering occurs BEFORE performance/latency scoring.
    Incompatible models are rejected unconditionally regardless of latency.
    """
    skip = skip_ids or set()
    registry = get_registry()
    states = get_node_states()

    req_caps = set(cls.required_capabilities)
    req_mods = set(cls.input_modalities)

    eligible_candidates = []

    for node_id, entry in registry.items():
        if node_id in skip:
            continue

        state = states.get(node_id)
        if state:
            status_val = getattr(state.status, "value", state.status)
            latency = state.latency_ms if state.latency_ms is not None else 50.0
            models_loaded = state.models_loaded
            models_meta = state.models_metadata
        else:
            status_val = entry.status if entry.status != "unknown" else "online"
            latency = 50.0
            models_loaded = [entry.model] if entry.model else []
            models_meta = {}

        status_val = str(status_val).upper()
        if status_val == "OFFLINE" or entry.status == "not_configured":
            continue

        if not models_loaded:
            models_loaded = [""]

        for model in models_loaded:
            model_meta = models_meta.get(model)
            caps = discover_capabilities(entry, model, model_meta=model_meta)

            # ─────────────────────────────────────────────────────────────
            # STEP 1: HARD CAPABILITY FILTERING (BEFORE SCORING)
            # ─────────────────────────────────────────────────────────────

            # Hard constraint 1: Image modality requires vision capability
            if "image" in req_mods and "vision" not in caps:
                logger.debug(
                    "Node %s (model '%s') rejected: lacks vision capability for image modality",
                    node_id, model,
                )
                continue

            # Hard constraint 2: Explicit required capabilities
            if req_caps:
                # If vision is explicitly required, model MUST have vision
                if "vision" in req_caps and "vision" not in caps:
                    continue

            # ─────────────────────────────────────────────────────────────
            # STEP 2: PERFORMANCE SCORING (ONLY FOR ELIGIBLE CANDIDATES)
            # ─────────────────────────────────────────────────────────────
            missing_caps = len(req_caps - caps) if req_caps else 0
            health_penalty = 10000.0 if status_val == "DEGRADED" else 0.0
            cap_penalty = missing_caps * 5000.0
            priority_penalty = entry.priority * 100.0
            unloaded_penalty = 50000.0 if (model_meta and not model_meta.get("is_loaded", True)) else 0.0

            score = latency + health_penalty + cap_penalty + priority_penalty + unloaded_penalty

            reason_parts = [f"latency={latency:.1f}ms"]
            if missing_caps > 0:
                reason_parts.append(f"missing_caps={missing_caps}")
            if status_val == "DEGRADED":
                reason_parts.append("DEGRADED")
            reason_str = ", ".join(reason_parts)

            full_reason = f"Model '{model}' selected: {reason_str}. Matched caps: {sorted(list(caps))}"
            eligible_candidates.append((score, entry, model, full_reason))

    # Sort eligible candidates by score ascending (lowest score wins)
    eligible_candidates.sort(key=lambda x: x[0])

    return [(entry, model, score, reason) for score, entry, model, reason in eligible_candidates]
