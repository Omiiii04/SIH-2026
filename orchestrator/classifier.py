"""
orchestrator/classifier.py
──────────────────────────
Input Analyser + Task Classifier for SIH-2026.

Phase 2: deterministic rule-based classification.
Phase 3: will be replaced by an embedding-based classifier.

Responsibilities
----------------
1. Inspect the ``input_type`` hint provided by the client.
2. Scan the query text for domain-specific keywords.
3. Return a ``ClassificationResult`` that drives the node router.

Priority order (first match wins):
  1. explicit input_type override  (IMAGE / CODE / REASONING / RETRIEVAL)
  2. keyword scan of query text
  3. default → TEXT / NODE-TEXT
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from orchestrator.schemas import ClassificationResult, InputType, NodeType

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rule tables
# Each entry: (NodeType, rule_name, keyword_list)
# Evaluated in order; first match wins.
# ─────────────────────────────────────────────────────────────────────────────

_KEYWORD_RULES: List[Tuple[NodeType, str, List[str]]] = [
    (
        NodeType.CODE,
        "coding_keywords",
        [
            "code", "function", "def ", "class ", "bug", "debug", "script",
            "python", "javascript", "typescript", "java", "c++", "rust", "golang",
            "compile", "syntax error", "implement", "algorithm", "loop", "recursion",
            "api endpoint", "unit test", "import ", "variable", "exception",
        ],
    ),
    (
        NodeType.VISION,
        "vision_keywords",
        [
            "image", "photo", "picture", "diagram", "screenshot", "chart",
            "figure", "describe this", "what is in", "look at", "ocr",
            "visual", "pixel", "colour", "color", "draw",
        ],
    ),
    (
        NodeType.REASONING,
        "reasoning_keywords",
        [
            "reason", "analyse", "analyze", "why", "explain why", "step by step",
            "step-by-step", "logic", "infer", "deduce", "compare", "evaluate",
            "pros and cons", "argue", "critical", "justify", "derive",
            "chain of thought", "hypothesis", "theorem", "proof",
        ],
    ),
    (
        NodeType.RAG,
        "retrieval_keywords",
        [
            "document", "file", "pdf", "upload", "search", "retrieve",
            "knowledge base", "based on the", "according to", "in the context",
            "from the text", "in the document", "find in", "look up",
        ],
    ),
    # TEXT is the default — no keywords needed
]

# InputType → NodeType direct mapping (overrides keyword scan)
_INPUT_TYPE_MAP: dict[InputType, NodeType] = {
    InputType.IMAGE:     NodeType.VISION,
    InputType.CODE:      NodeType.CODE,
    InputType.REASONING: NodeType.REASONING,
    InputType.RETRIEVAL: NodeType.RAG,
    InputType.TEXT:      NodeType.TEXT,   # will still go through keyword scan
}


def classify(query: str, input_type: InputType) -> ClassificationResult:
    """
    Classify a user query and return the target node type.

    Parameters
    ----------
    query:      The raw user query string.
    input_type: The ``input_type`` field from the QueryRequest.

    Returns
    -------
    ClassificationResult with node_type, input_type, and matched_rule.
    """

    # ── Step 1: non-TEXT explicit input_type bypasses keyword scan ────────────
    if input_type != InputType.TEXT:
        node_type = _INPUT_TYPE_MAP[input_type]
        logger.debug(
            "Classified via explicit input_type=%s → node_type=%s",
            input_type, node_type,
        )
        return ClassificationResult(
            input_type=input_type,
            node_type=node_type,
            confidence="rule-based",
            matched_rule=f"explicit_input_type:{input_type.value}",
        )

    # ── Step 2: keyword scan on query text ────────────────────────────────────
    query_lower = query.lower()
    for node_type, rule_name, keywords in _KEYWORD_RULES:
        for kw in keywords:
            if kw in query_lower:
                logger.debug(
                    "Classified via keyword '%s' (rule=%s) → node_type=%s",
                    kw, rule_name, node_type,
                )
                return ClassificationResult(
                    input_type=input_type,
                    node_type=node_type,
                    confidence="rule-based",
                    matched_rule=f"{rule_name}:{kw.strip()}",
                )

    # ── Step 3: default fallback ──────────────────────────────────────────────
    logger.debug("No rule matched — defaulting to NODE-TEXT")
    return ClassificationResult(
        input_type=input_type,
        node_type=NodeType.TEXT,
        confidence="rule-based",
        matched_rule="default_fallback",
    )
