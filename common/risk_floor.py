"""
Shared risk-floor check (CLAUDE.md requirement #12, extended to Needs Human Review — see
docs/DECISION_LOG.md "Synthesis Agent — three-way split..."). Used in two places:
synthesis_agent.curate_report (the first pass) and critique_agent.critique_report (the
re-check, including after a revision — see docs/DECISION_LOG.md's note on never trusting
an agent's self-report for a mechanically-checkable claim). Pulled out here rather than
duplicated once a second caller needed the exact same logic.
"""
from typing import Any

RISK_FLOOR_LABELS = {"Blocked", "At Risk", "Needs Human Review"}


def check_risk_floor(features: list[dict[str, Any]], curated_features: list[dict[str, Any]]) -> set[int]:
    """Returns the feature_ids that violate the floor — present in `features` with a
    risk-floor status_label, but missing from `curated_features`. An empty set means the
    floor holds. Only On Track Features may ever be legitimately absent."""
    must_appear = {f["feature_id"] for f in features if f["status_label"] in RISK_FLOOR_LABELS}
    present = {f["feature_id"] for f in curated_features}
    return must_appear - present
