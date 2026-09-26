"""
orchestrator/classifier.py
──────────────────────────
Phase 3 Hybrid Classifier for SIH-2026.

Strategy (two-stage pipeline)
──────────────────────────────
Stage 1 — Deterministic rules (always runs first, zero latency):
  a. Non-TEXT explicit input_type  →  immediate capability decision
  b. Pattern / keyword scan        →  fine-grained task_type + difficulty
  c. Returns high-confidence result if a rule fires with strong signal

Stage 2 — LLM classifier (only for ambiguous / low-confidence cases):
  - Sends a compact system prompt to NODE-TEXT (Gemma) asking for JSON
  - Parses the structured response into a ClassificationResult
  - Falls back gracefully to Stage 1 result if the LLM is unavailable

Output (ClassificationResult)
──────────────────────────────
  input_type          : text | image | code | reasoning | retrieval
  task_type           : coding | reasoning | visual_question_answering | …
  difficulty          : low | medium | high
  required_capability : text | vision | reasoning | coding | embedding/retrieval
  confidence          : 0.0 – 1.0
  classifier_method   : rule:* | llm:*
  matched_rule        : human-readable description of what fired
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from orchestrator.schemas import (
    ClassificationResult,
    ClassifierMethod,
    Difficulty,
    InputType,
    NodeType,
    TaskType,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Capability map — NodeType → registry capability string
# ─────────────────────────────────────────────────────────────────────────────

_NODE_TYPE_TO_CAPABILITY: Dict[NodeType, str] = {
    NodeType.TEXT:      "text",
    NodeType.VISION:    "vision",
    NodeType.REASONING: "reasoning",
    NodeType.CODE:      "coding",
    NodeType.RAG:       "embedding/retrieval",
}

# InputType → NodeType (non-TEXT types bypass keyword scan)
_INPUT_TYPE_MAP: Dict[InputType, NodeType] = {
    InputType.IMAGE:     NodeType.VISION,
    InputType.CODE:      NodeType.CODE,
    InputType.REASONING: NodeType.REASONING,
    InputType.RETRIEVAL: NodeType.RAG,
    InputType.TEXT:      NodeType.TEXT,
}

# InputType → fine-grained TaskType default
_INPUT_TYPE_TASK: Dict[InputType, TaskType] = {
    InputType.IMAGE:     TaskType.VISUAL_QA,
    InputType.CODE:      TaskType.CODING,
    InputType.REASONING: TaskType.REASONING,
    InputType.RETRIEVAL: TaskType.DOCUMENT_RETRIEVAL,
    InputType.TEXT:      TaskType.GENERAL_QA,
}


# ─────────────────────────────────────────────────────────────────────────────
# Rule table
# Each entry: (NodeType, TaskType, rule_name, confidence, keyword_patterns)
# Patterns are plain substrings (case-insensitive).
# Rules are evaluated top-to-bottom; first match wins.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _Rule:
    node_type: NodeType
    task_type: TaskType
    rule_name: str
    confidence: float
    keywords: List[str]
    difficulty: Difficulty = Difficulty.MEDIUM


_RULES: List[_Rule] = [

    # ── Vision ────────────────────────────────────────────────────────────────
    _Rule(NodeType.VISION, TaskType.OCR,       "ocr_keywords",    0.97,
          ["ocr", "extract text from", "read text in", "what does the text say"]),

    _Rule(NodeType.VISION, TaskType.VISUAL_QA, "vision_keywords", 0.95,
          ["image", "photo", "picture", "diagram", "screenshot", "chart",
           "figure", "describe this", "what is in", "look at", "shown in",
           "visual", "pixel", "colour", "color", "draw", "painting",
           "illustration", "thumbnail"]),

    # ── Code ─────────────────────────────────────────────────────────────────
    _Rule(NodeType.CODE, TaskType.CODE_DEBUG,  "debug_keywords",  0.97,
          ["find the bug", "debug", "fix the error", "traceback", "exception",
           "error in this", "not working", "broken code", "syntax error"],
          difficulty=Difficulty.MEDIUM),

    _Rule(NodeType.CODE, TaskType.CODE_REVIEW, "review_keywords", 0.93,
          ["review my code", "code review", "refactor", "optimise this code",
           "optimize this code", "improve this code"],
          difficulty=Difficulty.MEDIUM),

    _Rule(NodeType.CODE, TaskType.CODING,      "coding_keywords", 0.92,
          ["write a", "implement", "create a function", "generate code",
           "write code", "build a", "def ", "class ", "script",
           "python", "javascript", "typescript", "java", "c++", "rust",
           "golang", "fastapi", "flask", "django", "api endpoint", "unit test",
           "algorithm", "loop", "recursion", "import ", "variable", "function",
           "program", "code", "sql query", "bash", "shell script"],
          difficulty=Difficulty.MEDIUM),

    # ── Reasoning / Math ─────────────────────────────────────────────────────
    _Rule(NodeType.REASONING, TaskType.MATH, "math_keywords", 0.96,
          ["solve", "calculate", "integral", "derivative", "proof", "theorem",
           "equation", "matrix", "probability", "statistics", "formula",
           "differentiate", "integrate", "modulo", "prime", "factorial"],
          difficulty=Difficulty.HIGH),

    _Rule(NodeType.REASONING, TaskType.LOGICAL_INFERENCE, "logic_keywords", 0.95,
          ["if and only if", "therefore", "deduce", "infer", "imply",
           "syllogism", "premise", "conclusion", "logical", "valid argument",
           "fallacy", "entails", "contrapositive"],
          difficulty=Difficulty.HIGH),

    _Rule(NodeType.REASONING, TaskType.REASONING, "reasoning_keywords", 0.88,
          ["reason", "analyse", "analyze", "why", "explain why",
           "step by step", "step-by-step", "logic", "evaluate",
           "pros and cons", "argue", "critical", "justify", "derive",
           "chain of thought", "hypothesis", "compare", "contrast",
           "cause", "effect", "impact"],
          difficulty=Difficulty.MEDIUM),

    # ── RAG / Retrieval ───────────────────────────────────────────────────────
    _Rule(NodeType.RAG, TaskType.SEMANTIC_SEARCH, "search_keywords", 0.96,
          ["semantic search", "similarity search", "embed", "embedding",
           "vector search", "nearest neighbour", "cosine similarity",
           "find similar"]),

    _Rule(NodeType.RAG, TaskType.DOCUMENT_RETRIEVAL, "retrieval_keywords", 0.92,
          ["document", "file", "pdf", "upload", "search", "retrieve",
           "knowledge base", "based on the", "according to", "in the context",
           "from the text", "in the document", "find in", "look up",
           "passage", "paragraph", "source"],
          difficulty=Difficulty.MEDIUM),

    # ── Summarisation / creative (TEXT) ───────────────────────────────────────
    _Rule(NodeType.TEXT, TaskType.SUMMARIZATION, "summarize_keywords", 0.85,
          ["summarize", "summarise", "summary", "tldr", "tl;dr",
           "in brief", "briefly explain", "key points"],
          difficulty=Difficulty.LOW),

    _Rule(NodeType.TEXT, TaskType.CREATIVE_WRITING, "creative_keywords", 0.82,
          ["write a poem", "write a story", "write an essay", "compose",
           "creative writing", "haiku", "limerick", "short story", "narrative"],
          difficulty=Difficulty.LOW),

    # TEXT / GENERAL_QA is the implicit default (no keywords needed)
]


# ─────────────────────────────────────────────────────────────────────────────
# Difficulty estimation (heuristic on top of rule result)
# ─────────────────────────────────────────────────────────────────────────────

_HIGH_DIFFICULTY_SIGNALS = [
    "complex", "advanced", "expert", "in depth", "detailed", "comprehensive",
    "research", "dissertation", "proof", "formal", "rigorous", "multi-step",
    "multi step",
]
_LOW_DIFFICULTY_SIGNALS = [
    "simple", "quick", "brief", "short", "basic", "easy", "beginner",
    "explain simply", "eli5", "tldr", "one line",
]


def _estimate_difficulty(query_lower: str, base: Difficulty) -> Difficulty:
    """Adjust difficulty up/down based on query signals."""
    if any(s in query_lower for s in _HIGH_DIFFICULTY_SIGNALS):
        return Difficulty.HIGH
    if any(s in query_lower for s in _LOW_DIFFICULTY_SIGNALS):
        return Difficulty.LOW
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Deterministic classifier
# ─────────────────────────────────────────────────────────────────────────────

# Confidence threshold: if Stage 1 confidence >= this, skip LLM
_RULE_CONFIDENCE_THRESHOLD = 0.90


def _classify_by_rules(
    query: str,
    input_type: InputType,
) -> ClassificationResult:
    query_lower = query.lower()
    
    input_modalities = {"text"}
    if input_type == InputType.IMAGE or "image" in query_lower or "picture" in query_lower or "photo" in query_lower:
        input_modalities.add("image")
    elif input_type == InputType.CODE:
        input_modalities.add("code")
        
    tasks = set()
    caps = set()
    best_confidence = 0.55
    best_method = ClassifierMethod.RULE_DEFAULT
    matched_rules = []
    
    best_task = None
    best_cap = None

    if input_type != InputType.TEXT:
        node_type  = _INPUT_TYPE_MAP.get(input_type, NodeType.TEXT)
        task_type  = _INPUT_TYPE_TASK.get(input_type, TaskType.GENERAL_QA)
        capability = _NODE_TYPE_TO_CAPABILITY.get(node_type, "text")
        tasks.add(task_type.value)
        caps.add(capability)
        best_confidence = 1.0
        best_method = ClassifierMethod.RULE_EXPLICIT
        best_task = task_type
        best_cap = capability
        matched_rules.append(f"explicit_input_type:{input_type.value}")

    for rule in _RULES:
        for kw in rule.keywords:
            if kw in query_lower:
                tasks.add(rule.task_type.value)
                rule_cap = _NODE_TYPE_TO_CAPABILITY.get(rule.node_type, "text")
                caps.add(rule_cap)
                if rule.confidence > best_confidence or best_task is None:
                    best_confidence = rule.confidence
                    best_method = ClassifierMethod.RULE_KEYWORD
                    best_task = rule.task_type
                    best_cap = rule_cap
                matched_rules.append(f"{rule.rule_name}:{kw.strip()}")
                
    if not tasks:
        tasks.add(TaskType.GENERAL_QA.value)
        caps.add("text")
        matched_rules.append("default_fallback")
        
    if best_task is None:
        best_task = TaskType.GENERAL_QA
        best_cap = "text"
        
    difficulty = _estimate_difficulty(query_lower, Difficulty.MEDIUM)
    if len(tasks) > 1:
        difficulty = Difficulty.HIGH
        
    primary_task = best_task
    primary_cap = best_cap
    
    _cap_to_node = {
        "text": NodeType.TEXT,
        "vision": NodeType.VISION,
        "coding": NodeType.CODE,
        "reasoning": NodeType.REASONING,
        "embedding/retrieval": NodeType.RAG,
    }
    primary_node = _cap_to_node.get(primary_cap, NodeType.TEXT)

    return ClassificationResult(
        input_type=input_type,
        node_type=primary_node,
        task_type=primary_task,
        difficulty=difficulty,
        required_capability=primary_cap,
        confidence=best_confidence,
        classifier_method=best_method,
        matched_rule=" | ".join(matched_rules),
        input_modalities=list(input_modalities),
        task_types=list(tasks),
        required_capabilities=list(caps)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: LLM classifier (async)
# ─────────────────────────────────────────────────────────────────────────────

_LLM_SYSTEM_PROMPT = """\
You are a request classifier for a distributed AI inference system.
Analyse the user query and return ONLY a JSON object — no markdown, no explanation.

JSON schema:
{
  "input_type": "text" | "image" | "code" | "reasoning" | "retrieval",
  "task_type": "general_qa" | "summarization" | "creative_writing" | "coding" |
               "code_debug" | "code_review" | "visual_question_answering" | "ocr" |
               "reasoning" | "math" | "logical_inference" |
               "document_retrieval" | "semantic_search" | "embedding" |
               "classification" | "unknown",
  "difficulty": "low" | "medium" | "high",
  "required_capability": "text" | "vision" | "coding" | "reasoning" | "embedding/retrieval",
  "confidence": <float between 0.0 and 1.0>
}

Rules:
- image/photo/visual content → input_type=image, required_capability=vision
- code/debug/implement/script → required_capability=coding
- reason/analyse/step-by-step/math/proof → required_capability=reasoning
- search/retrieve/document/pdf/knowledge base → required_capability=embedding/retrieval
- everything else → required_capability=text
- difficulty=high for complex, multi-step, or expert-level tasks
- difficulty=low for simple, short, or factual queries
- confidence reflects how certain you are (1.0 = very certain)
"""


def _parse_llm_json(raw: str) -> Optional[dict]:
    """Extract and validate the JSON blob from the LLM's raw text output."""
    # Strip markdown code fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    # Find first {...} block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    required = {"input_type", "task_type", "difficulty", "required_capability", "confidence"}
    if not required.issubset(data.keys()):
        return None
    return data


def _llm_json_to_result(data: dict, original_input_type: InputType) -> ClassificationResult:
    """Convert the parsed LLM JSON dict into a ClassificationResult."""
    try:
        input_type = InputType(data["input_type"])
    except ValueError:
        input_type = original_input_type

    try:
        task_type = TaskType(data["task_type"])
    except ValueError:
        task_type = TaskType.UNKNOWN

    try:
        difficulty = Difficulty(data["difficulty"])
    except ValueError:
        difficulty = Difficulty.MEDIUM

    capability = data.get("required_capability", "text")

    # Map capability → node_type
    _cap_to_node: Dict[str, NodeType] = {
        "text":                NodeType.TEXT,
        "vision":              NodeType.VISION,
        "coding":              NodeType.CODE,
        "reasoning":           NodeType.REASONING,
        "embedding/retrieval": NodeType.RAG,
    }
    node_type = _cap_to_node.get(capability, NodeType.TEXT)

    confidence = float(data.get("confidence", 0.8))
    confidence = max(0.0, min(1.0, confidence))

    return ClassificationResult(
        input_type=input_type,
        node_type=node_type,
        task_type=task_type,
        difficulty=difficulty,
        required_capability=capability,
        confidence=confidence,
        classifier_method=ClassifierMethod.LLM,
        matched_rule="llm:structured_output",
    )


async def _classify_via_llm(
    query: str,
    input_type: InputType,
    fallback: ClassificationResult,
    request_id: Optional[str] = None,
) -> ClassificationResult:
    """
    Call NODE-TEXT to classify the query as structured JSON.
    Returns fallback if the node is unavailable or the response is unparseable.
    """
    # Import here to avoid circular imports
    from orchestrator.lm_client import LMClientError, call_node
    from orchestrator.node_registry import get_node_by_type

    text_node = get_node_by_type(NodeType.TEXT)
    if text_node is None or not text_node.endpoint:
        logger.warning("LLM classifier: NODE-TEXT not available; using rule fallback")
        return fallback

    try:
        lm_resp = await call_node(
            endpoint=text_node.endpoint,
            model=text_node.model,
            query=query,
            system_prompt=_LLM_SYSTEM_PROMPT,
            parameters={"max_tokens": 128, "temperature": 0.0},
            timeout=15.0,
            request_id=request_id,
        )
        data = _parse_llm_json(lm_resp.content)
        if data is None:
            logger.warning("LLM classifier: could not parse JSON from response; using rule fallback")
            return fallback

        result = _llm_json_to_result(data, input_type)
        logger.info(
            "LLM classifier: task=%s capability=%s confidence=%.2f",
            result.task_type, result.required_capability, result.confidence,
        )
        return result

    except LMClientError as exc:
        logger.warning("LLM classifier failed (%s); using rule fallback", exc.detail)
        # Mark as fallback but keep the content
        fallback.classifier_method = ClassifierMethod.LLM_FALLBACK
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def classify(query: str, input_type: InputType, request_id: Optional[str] = None) -> ClassificationResult:
    """
    Hybrid classifier entry point (async).

    1. Always run Stage 1 (deterministic rules) first.
    2. If Stage 1 confidence < threshold AND query is purely text-type,
       escalate to the LLM classifier.
    3. Return whichever result has higher confidence.

    Parameters
    ----------
    query:      Raw user query string.
    input_type: InputType hint from the QueryRequest.
    """
    stage1 = _classify_by_rules(query, input_type)
    logger.debug(
        "Stage1: node=%s task=%s confidence=%.2f method=%s",
        stage1.node_type, stage1.task_type, stage1.confidence, stage1.classifier_method,
    )

    # Skip LLM if rule was confident enough, or if input_type was explicit
    if (stage1.confidence >= _RULE_CONFIDENCE_THRESHOLD
            or stage1.classifier_method == ClassifierMethod.RULE_EXPLICIT):
        return stage1

    # Escalate to LLM for ambiguous text queries
    logger.info(
        "Stage1 confidence %.2f < %.2f — escalating to LLM classifier",
        stage1.confidence, _RULE_CONFIDENCE_THRESHOLD,
    )
    return await _classify_via_llm(query, input_type, fallback=stage1, request_id=request_id)


def classify_sync(query: str, input_type: InputType) -> ClassificationResult:
    """
    Synchronous rule-only classifier — for use in unit tests and
    contexts where an event loop is not available.
    Never calls the LLM.
    """
    return _classify_by_rules(query, input_type)
