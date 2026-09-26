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

def discover_capabilities(entry: NodeRegistryEntry, model: str) -> set[str]:
    """Map model metadata into capabilities. No longer relies solely on static node roles."""
    caps = set()
    model_lower = (model or "").lower()
    
    # Safe defaults for any LLM
    if model_lower:
        caps.update(["text", "text_generation", "summarization", "structured_output"])
    
    # Verified metadata (model inference)
    inferred_caps = set()
    if any(x in model_lower for x in ["vision", "llava", "pixtral", "image", "vl"]):
        inferred_caps.update(["vision", "ocr", "image_reasoning"])
    if any(x in model_lower for x in ["code", "coder", "starcoder", "deepseek-coder"]):
        inferred_caps.update(["coding", "code_review", "debugging"])
    if any(x in model_lower for x in ["math", "reasoning", "qwen2-math"]):
        inferred_caps.update(["reasoning", "math", "logical_inference"])
    if any(x in model_lower for x in ["embed", "nomic", "retrieval"]):
        inferred_caps.update(["embeddings", "retrieval", "embedding/retrieval"])

    caps.update(inferred_caps)
    
    # Explicit admin override / legacy role (only if model didn't infer anything or model is empty)
    # We still allow legacy overrides to satisfy existing tests and setups.
    if entry.capability == "vision" and "vision" not in caps:
        caps.update(["vision", "ocr", "image_reasoning"])
    elif entry.capability == "coding" and "coding" not in caps:
        caps.update(["coding", "code_review", "debugging"])
    elif entry.capability == "reasoning" and "reasoning" not in caps:
        caps.update(["reasoning", "math", "logical_inference"])
    elif entry.capability == "embedding/retrieval" and "retrieval" not in caps:
        caps.update(["retrieval", "embeddings", "embedding/retrieval"])
    elif entry.capability == "text" and "text" not in caps:
        caps.update(["text", "text_generation", "structured_output", "summarization"])

    return caps

def select_best_candidates(
    cls: ClassificationResult,
    skip_ids: set[str] = None
) -> List[Tuple[NodeRegistryEntry, str, float, str]]:
    """
    Returns list of eligible candidates sorted by score (lowest is best).
    Tuple: (Node, ModelName, Score, Reason)
    """
    skip = skip_ids or set()
    registry = get_registry()
    states = get_node_states()
    
    req_caps = set(cls.required_capabilities)
    req_mods = set(cls.input_modalities)
    
    candidates = []
    
    for node_id, entry in registry.items():
        if node_id in skip:
            continue
            
        state = states.get(node_id)
        
        if state:
            status_val = getattr(state.status, "value", state.status)
            latency = state.latency_ms if state.latency_ms is not None else 50.0
            models_loaded = state.models_loaded
        else:
            status_val = entry.status if entry.status != "unknown" else "online"
            latency = 50.0
            models_loaded = [entry.model] if entry.model else []
            
        status_val = str(status_val).upper()
            
        if status_val == "OFFLINE" or entry.status == "not_configured":
            continue

        if not models_loaded:
            # Fallback if no models discovered yet
            models_loaded = [""]
            
        for model in models_loaded:
            # Discover capabilities
            caps = discover_capabilities(entry, model)
            
            # 1. Modality matching
            if "image" in req_mods and "vision" not in caps:
                continue # Hard constraint
                
            # 2. Capability matching
            overlap = len(req_caps.intersection(caps))
            missing = len(req_caps - caps)
            
            # 3. Health & Latency
            health_penalty = 10000.0 if status_val == "DEGRADED" else 0.0
            cap_penalty = missing * 5000.0
            priority_penalty = entry.priority * 100.0
            
            score = latency + health_penalty + cap_penalty + priority_penalty
            
            reason_parts = [f"latency={latency:.1f}ms"]
            if missing > 0:
                reason_parts.append(f"missing_caps={missing}")
            if status_val == "DEGRADED":
                reason_parts.append("DEGRADED")
                
            reason = ", ".join(reason_parts)
            
            full_reason = f"Model '{model}' selected: {reason}. Matched caps: {sorted(list(caps))}"
            candidates.append((score, entry, model, full_reason))
        
    candidates.sort(key=lambda x: x[0])
    
    result = []
    for score, entry, model, full_reason in candidates:
        result.append((entry, model, score, full_reason))
        
    return result
