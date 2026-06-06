"""
Critic Module — Hybrid grounding verification for FileMind agent.

Uses deterministic exact-match checks (regex path extraction) + lightweight
LLM semantic verification to validate that the agent's answers are grounded
in the search evidence, not fabricated from parametric knowledge.

Architecture:
  1. Extract all claimed file paths/IDs from the answer (regex)
  2. Check if those paths actually exist in the evidence (deterministic)
  3. If paths match or none claimed, run LLM semantic grounding check
  4. Return verdict: GROUNDED, HALLUCINATED, or INSUFFICIENT

Model: qwen2.5-coder:7b with temperature=0.0, num_predict=20, forced-choice output.
Fallback: rule-based validation if LLM output is malformed.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────
VERDICT_GROUNDED = "GROUNDED"
VERDICT_HALLUCINATED = "HALLUCINATED"
VERDICT_INSUFFICIENT = "INSUFFICIENT"
VALID_VERDICTS = {VERDICT_GROUNDED, VERDICT_HALLUCINATED, VERDICT_INSUFFICIENT}

CRITIC_PROMPT = """You are a fact-checking critic. Your ONLY job is to evaluate whether an answer is grounded in the provided evidence.

EVIDENCE:
{evidence}

ANSWER TO EVALUATE:
{answer}

Respond with EXACTLY ONE of these three labels:
- "GROUNDED": The answer's claims are directly supported by the evidence.
- "HALLUCINATED": The answer contains claims not found in or contradicted by the evidence.
- "INSUFFICIENT": The evidence does not contain enough information to verify the answer.

Do not explain. Do not add text. Output only the label."""


def extract_file_paths(text: str) -> list[str]:
    """Extract file path and file_id references from text."""
    paths = []

    # Windows paths: C:\... or C:/...
    paths.extend(
        re.findall(r"[A-Z]:[\\/][\w.\-_/\\]+\.[a-z]{2,6}", text, re.IGNORECASE)
    )

    # Unix paths: /home/... or ./filemind/...
    paths.extend(
        re.findall(r"(?:^|[\s,/])(/[\w.\-_/]+\.[a-z]{2,6})", text, re.IGNORECASE)
    )

    # file_id references: file_id=123, file:xyz, "file_xyz"
    paths.extend(re.findall(r"file_?id[=:]\s*\w+", text, re.IGNORECASE))
    paths.extend(re.findall(r"file_?\w+\.[a-z]{2,6}", text, re.IGNORECASE))

    # Relative paths with known extensions
    paths.extend(
        re.findall(
            r"[\w\-/\\]+\.(?:py|md|json|txt|yaml|yml|toml|cfg|ini|js|ts|csv|log|db)",
            text,
            re.IGNORECASE,
        )
    )

    return list(set(p.strip() for p in paths if len(p) > 3))


def hybrid_grounding_check(answer: str, evidence: str) -> str:
    """
    Deterministic + LLM hybrid verification for file grounding.

    Step 1: Extract all claimed file paths/IDs from the answer.
    Step 2: Check if those paths exist in the evidence (deterministic).
    Step 3: If paths match or none claimed, run LLM semantic check.

    Returns: GROUNDED, HALLUCINATED, or INSUFFICIENT.
    """
    # Step 1: Extract claimed file references
    claimed_paths = extract_file_paths(answer)
    evidence_paths = extract_file_paths(evidence)

    # Step 2: Deterministic check — do claimed paths exist in evidence?
    if claimed_paths:
        # Normalize paths for comparison (case-insensitive, forward slashes)
        def normalize(p):
            return p.lower().replace("\\", "/")

        claimed_norm = {normalize(p) for p in claimed_paths}
        evidence_norm = {normalize(p) for p in evidence_paths}

        missing = claimed_norm - evidence_norm
        if missing:
            logger.warning(f"Critic: hallucinated file references: {missing}")
            return VERDICT_HALLUCINATED

    # Step 3: LLM semantic check (if paths match or no paths claimed)
    return _llm_semantic_check(answer, evidence)


def _llm_semantic_check(
    answer: str,
    evidence: str,
    model: str = "qwen2.5-coder:7b",
    ollama_url: str = "http://localhost:11434/api/generate",
) -> str:
    """
    Use LLM to check semantic grounding of answer in evidence.

    Uses qwen2.5-coder:7b with strict output constraints for reliability.
    Falls back to rule-based validation if LLM is unavailable.
    """
    try:
        import requests

        prompt = CRITIC_PROMPT.format(evidence=evidence[:2000], answer=answer[:1000])

        response = requests.post(
            ollama_url,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "repeat_penalty": 1.1,
                    "num_predict": 20,
                    "stop": ["\n", "."],
                },
            },
            timeout=15,
        )

        if response.status_code == 200:
            label = response.json().get("response", "").strip().upper()
            if label in VALID_VERDICTS:
                return label

        logger.warning(f"Critic LLM returned malformed verdict: {response.text[:200]}")
    except Exception as e:
        logger.warning(f"Critic LLM unavailable: {e}")

    # Fallback: rule-based validation
    return _rule_based_fallback(answer, evidence)


def _rule_based_fallback(answer: str, evidence: str) -> str:
    """
    Simple keyword/regex-based fallback when LLM critic is unavailable.

    Checks if the answer contains evidence file references or standard
    empty-search response patterns.
    """
    answer_lower = answer.lower()

    # Strong signals of grounding
    grounding_signals = [
        "file_id",
        "file_",
        ".py",
        ".md",
        ".json",
        ".txt",
        "score:",
        "found",
        "no files found",
        "not found in the local",
        "index does not contain",
        "local index",
        "filemind",
        "type=",
        "category=",
        "c:/",
        "path",
    ]

    has_grounding = any(s in answer_lower for s in grounding_signals)

    # Check for empty-search acknowledgment
    empty_ack = any(
        s in answer_lower
        for s in [
            "no files found",
            "not found in the local",
            "index does not contain",
            "nothing was found",
            "no information about",
        ]
    )

    if empty_ack:
        return VERDICT_GROUNDED  # Correctly acknowledging empty evidence

    if has_grounding:
        return VERDICT_GROUNDED  # Likely grounded (heuristic)

    return VERDICT_INSUFFICIENT  # Conservative default


def validate_answer_with_critic(
    answer: str,
    evidence: str,
    query: str = "",
) -> tuple[str, str]:
    """
    Full validation pipeline: deterministic + LLM critic.

    Args:
        answer: The agent's answer to evaluate
        evidence: The search results the answer should be grounded in
        query: Original user query (for logging)

    Returns:
        Tuple of (verdict, reasoning) where verdict is one of
        GROUNDED/HALLUCINATED/INSUFFICIENT and reasoning explains why.
    """
    verdict = hybrid_grounding_check(answer, evidence)

    if verdict == VERDICT_HALLUCINATED:
        claimed = extract_file_paths(answer)
        evidence_paths = extract_file_paths(evidence)
        reasoning = (
            f"Answer contains file references not found in evidence: "
            f"{set(claimed) - set(evidence_paths)}"
        )
    elif verdict == VERDICT_GROUNDED:
        reasoning = "Answer references are consistent with evidence"
    else:
        reasoning = "Evidence insufficient to verify answer"

    logger.info(f"Critic verdict for '{query[:50]}...': {verdict} — {reasoning}")
    return verdict, reasoning
