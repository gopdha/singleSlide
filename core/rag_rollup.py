"""
core/rag_rollup.py — deterministic RAG rollup. No LLM, no agent loop, no I/O.

Rolls up Feature status LABELS (feature_agent's output) into a single Red/Amber/Green/
Unknown signal for the Executive Summary — different logic from the pre-repo
"rag-rules-engine" concept, which worked over raw schedule/budget metrics, not
agent-produced labels. See docs/DECISION_LOG.md ("core/rag_rollup.py — the 'Unknown'
status, and a correction on its provenance") for the full reasoning, including why
`Unknown` exists and a correction on where that idea actually came from.

Rule (CLAUDE.md requirement #10, generalized to cover two edge cases as one):
  1. Any Blocked        -> Red
  2. Else any At Risk   -> Amber
  3. Else any On Track  -> Green
  4. Else (no confidently-labeled Feature at all — zero Features, or every one is
     Needs Human Review) -> Unknown

Needs Human Review is excluded from the calculation entirely — it never forces Amber
or any other status. It's surfaced separately (`needs_human_review` below) for Review
Gate and Synthesis Agent's narration, exactly as CLAUDE.md requires. A Feature list
mixing On Track with some Needs Human Review (no Blocked/At Risk) still resolves to
Green — real evaluated signal exists, and NHR items don't erase it.

This module deliberately does NOT synthesize a narrative string (e.g. "Red — Feature
#12 is Blocked"). Turning `reasons` into prose is narrative tone and phrasing, which
CLAUDE.md's architecture table assigns to the agentic side (Synthesis Agent), not the
deterministic side. This hands over structured facts; Synthesis writes the sentence.
"""
from typing import Any, Literal, TypedDict

RagStatus = Literal["Red", "Amber", "Green", "Unknown"]

_VALID_STATUS_LABELS = {"On Track", "At Risk", "Blocked", "Needs Human Review"}


class FeatureRef(TypedDict):
    feature_id: int
    title: str
    status_label: str


class RagRollupResult(TypedDict):
    rag_status: RagStatus
    reasons: list[FeatureRef]
    needs_human_review: list[FeatureRef]
    total_features: int


def _to_ref(feature: dict[str, Any]) -> FeatureRef:
    missing = [key for key in ("feature_id", "title", "status_label") if key not in feature]
    if missing:
        raise ValueError(f"Feature dict is missing required key(s) {missing}: {feature!r}")

    status_label = feature["status_label"]
    if status_label not in _VALID_STATUS_LABELS:
        raise ValueError(
            f"Unrecognized status_label {status_label!r} on feature_id={feature.get('feature_id')!r} "
            f"— expected one of {sorted(_VALID_STATUS_LABELS)}."
        )

    return FeatureRef(feature_id=feature["feature_id"], title=feature["title"], status_label=status_label)


def compute_rag_rollup(features: list[dict[str, Any]]) -> RagRollupResult:
    """Pure function — no I/O, no LLM, deliberately sync (nothing here ever awaits
    anything, unlike the rest of this repo's async/await convention, which exists
    specifically for MCP and Agent SDK calls).

    Reads only feature_id/title/status_label from each dict — the full FEATURE_SCHEMA
    shape (short_description, progress_summary, risk, evidence, ...) is fine to pass in
    as-is; extra keys are ignored. Raises ValueError on a missing required key or a
    status_label outside the 4-value taxonomy — a mislabeled Feature silently
    corrupting the one number leadership anchors decisions to is worse than failing
    loudly.
    """
    refs = [_to_ref(feature) for feature in features]

    blocked = [ref for ref in refs if ref["status_label"] == "Blocked"]
    at_risk = [ref for ref in refs if ref["status_label"] == "At Risk"]
    on_track = [ref for ref in refs if ref["status_label"] == "On Track"]
    needs_human_review = [ref for ref in refs if ref["status_label"] == "Needs Human Review"]

    if blocked:
        rag_status: RagStatus = "Red"
        reasons = blocked
    elif at_risk:
        rag_status = "Amber"
        reasons = at_risk
    elif on_track:
        rag_status = "Green"
        reasons = on_track
    else:
        rag_status = "Unknown"
        reasons = []

    return RagRollupResult(
        rag_status=rag_status,
        reasons=reasons,
        needs_human_review=needs_human_review,
        total_features=len(refs),
    )
