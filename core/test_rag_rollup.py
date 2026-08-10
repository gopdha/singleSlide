#!/usr/bin/env python3
"""
Pure unit tests for core/rag_rollup.py — no credentials, no tiering, no network.
compute_rag_rollup() is deterministic with zero I/O, so this is comprehensive
rule/edge-case coverage, run every time with no setup.

Run with:
    python3 test_rag_rollup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rag_rollup import compute_rag_rollup  # noqa: E402


def _feature(feature_id: int, title: str, status_label: str, **extra) -> dict:
    return {"feature_id": feature_id, "title": title, "status_label": status_label, **extra}


def main():
    print("core/rag_rollup.py — test suite\n")
    checks = 0

    # --- Core rule: severity ordering ------------------------------------------------

    result = compute_rag_rollup([_feature(1, "A", "Blocked")])
    assert result["rag_status"] == "Red"
    assert result["reasons"] == [{"feature_id": 1, "title": "A", "status_label": "Blocked"}]
    assert result["needs_human_review"] == []
    assert result["total_features"] == 1
    print("  PASS  single Blocked Feature -> Red")
    checks += 1

    result = compute_rag_rollup([_feature(1, "A", "At Risk")])
    assert result["rag_status"] == "Amber"
    assert result["reasons"][0]["feature_id"] == 1
    print("  PASS  single At Risk Feature (no Blocked) -> Amber")
    checks += 1

    result = compute_rag_rollup([_feature(1, "A", "On Track")])
    assert result["rag_status"] == "Green"
    assert result["reasons"][0]["feature_id"] == 1
    print("  PASS  single On Track Feature (no Blocked/At Risk) -> Green")
    checks += 1

    result = compute_rag_rollup([
        _feature(1, "Blocked One", "Blocked"),
        _feature(2, "At Risk One", "At Risk"),
        _feature(3, "On Track One", "On Track"),
        _feature(4, "NHR One", "Needs Human Review"),
    ])
    assert result["rag_status"] == "Red"
    assert [r["feature_id"] for r in result["reasons"]] == [1]
    assert [r["feature_id"] for r in result["needs_human_review"]] == [4]
    assert result["total_features"] == 4
    print("  PASS  Blocked outranks At Risk/On Track/NHR when all present -> Red, "
          "reasons hold only the Blocked Feature")
    checks += 1

    result = compute_rag_rollup([
        _feature(1, "At Risk One", "At Risk"),
        _feature(2, "On Track One", "On Track"),
        _feature(3, "NHR One", "Needs Human Review"),
    ])
    assert result["rag_status"] == "Amber"
    assert [r["feature_id"] for r in result["reasons"]] == [1]
    assert [r["feature_id"] for r in result["needs_human_review"]] == [3]
    print("  PASS  At Risk outranks On Track/NHR when no Blocked present -> Amber, "
          "reasons hold only the At Risk Feature")
    checks += 1

    # --- Multiple features driving the same status -----------------------------------

    result = compute_rag_rollup([
        _feature(1, "Blocked One", "Blocked"),
        _feature(2, "Blocked Two", "Blocked"),
        _feature(3, "On Track One", "On Track"),
    ])
    assert result["rag_status"] == "Red"
    assert [r["feature_id"] for r in result["reasons"]] == [1, 2]
    print("  PASS  multiple Blocked Features all appear in reasons, in input order")
    checks += 1

    # --- Green with mixed Needs Human Review (the explicitly-confirmed call) ---------

    result = compute_rag_rollup([
        _feature(1, "On Track One", "On Track"),
        _feature(2, "NHR One", "Needs Human Review"),
        _feature(3, "NHR Two", "Needs Human Review"),
    ])
    assert result["rag_status"] == "Green"
    assert [r["feature_id"] for r in result["reasons"]] == [1]
    assert [r["feature_id"] for r in result["needs_human_review"]] == [2, 3]
    assert result["total_features"] == 3
    print("  PASS  On Track + Needs Human Review (no Blocked/At Risk) -> Green — "
          "real evaluated signal exists and NHR doesn't erase it")
    checks += 1

    # --- Unknown: the collapsed edge case ---------------------------------------------

    result = compute_rag_rollup([])
    assert result["rag_status"] == "Unknown"
    assert result["reasons"] == []
    assert result["needs_human_review"] == []
    assert result["total_features"] == 0
    print("  PASS  empty Feature list -> Unknown (not a silent Green), total_features=0")
    checks += 1

    result = compute_rag_rollup([
        _feature(1, "NHR One", "Needs Human Review"),
        _feature(2, "NHR Two", "Needs Human Review"),
        _feature(3, "NHR Three", "Needs Human Review"),
    ])
    assert result["rag_status"] == "Unknown"
    assert result["reasons"] == []
    assert [r["feature_id"] for r in result["needs_human_review"]] == [1, 2, 3]
    assert result["total_features"] == 3
    print("  PASS  all-Needs-Human-Review Feature list -> Unknown (not a silent Green), "
          "and total_features=3 distinguishes this from the empty-list case above")
    checks += 1

    # --- total_features is diagnostic, always len(input), regardless of outcome ------

    for features in (
        [],
        [_feature(1, "A", "On Track")],
        [_feature(1, "A", "Blocked"), _feature(2, "B", "At Risk"), _feature(3, "C", "Needs Human Review")],
    ):
        assert compute_rag_rollup(features)["total_features"] == len(features)
    print("  PASS  total_features always equals len(input), across Unknown/Green/Red cases")
    checks += 1

    # --- Extra fields on input dicts are ignored, not leaked into output -------------

    result = compute_rag_rollup([
        _feature(1, "A", "On Track", short_description="x", progress_summary="y", risk=None, evidence=["z"]),
    ])
    assert result["reasons"] == [{"feature_id": 1, "title": "A", "status_label": "On Track"}]
    assert set(result["reasons"][0].keys()) == {"feature_id", "title", "status_label"}
    print("  PASS  extra FEATURE_SCHEMA fields (short_description, progress_summary, risk, "
          "evidence) are accepted on input and ignored in output — only the 3 needed fields carry through")
    checks += 1

    # --- Loud failure on malformed input ----------------------------------------------

    try:
        compute_rag_rollup([{"feature_id": 1, "title": "A"}])  # missing status_label
        print("  FAIL  expected ValueError for a Feature dict missing status_label, got none")
        sys.exit(1)
    except ValueError as err:
        assert "status_label" in str(err)
        print(f"  PASS  missing status_label fails loudly: {err}")
    checks += 1

    try:
        compute_rag_rollup([_feature(1, "A", "Kinda On Track I Guess")])  # not in the taxonomy
        print("  FAIL  expected ValueError for an unrecognized status_label, got none")
        sys.exit(1)
    except ValueError as err:
        assert "Unrecognized status_label" in str(err)
        print(f"  PASS  unrecognized status_label fails loudly: {err}")
    checks += 1

    print(f"\nAll {checks} checks passed.")


if __name__ == "__main__":
    main()
