#!/usr/bin/env python3
"""
Code-enforced checks (_risk_floor_check, _grounding_coverage_check) are pure — full unit
coverage, always run, no credentials. critique_report as a whole follows the same 3-tier
pattern as Synthesis Agent's Parts B/C: structural checks always run; request
construction validated with a placeholder ANTHROPIC_API_KEY; full live run needs a real
key. No DATABASE_URL needed anywhere here — critique_report takes synthesize_report's
already-fetched output, it never touches Archive itself.

Run with:
    python3 test_critique_agent.py
    ANTHROPIC_API_KEY=sk-ant-fake python3 test_critique_agent.py
    ANTHROPIC_API_KEY=... python3 test_critique_agent.py       # live run
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from critique_agent import (  # noqa: E402
    CRITIQUE_SCHEMA,
    _grounding_coverage_check,
    _risk_floor_check,
    critique_report,
)

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "common"))
from risk_floor import RISK_FLOOR_LABELS  # noqa: E402
from skill_loader import load_skill  # noqa: E402

SKILLS_ROOT = str(Path(__file__).parent.parent.parent / "skills")
TEST_PROJECT_ID = "ai-reports-demo"


def _feature(feature_id: int, status_label: str, title: str) -> dict:
    return {"feature_id": feature_id, "title": title, "status_label": status_label}


def _curated(feature_id: int, status_label: str, title: str) -> dict:
    return {"feature_id": feature_id, "title": title, "status_label": status_label, "display_text": "x"}


def run_code_check_tests():
    print("Code-enforced checks — pure unit tests:")

    # --- _risk_floor_check ---
    features = [_feature(1, "Blocked", "A"), _feature(2, "On Track", "B")]
    curated = [_curated(1, "Blocked", "A"), _curated(2, "On Track", "B")]
    result = _risk_floor_check(features, curated)
    assert result == {"criterion": "risk_floor", "passed": True,
                       "feedback": "All Blocked/At Risk/Needs Human Review Features are present in curated_features."}
    print("  PASS  risk_floor passes when every Blocked/At Risk/NHR Feature is present")

    features = [_feature(1, "Blocked", "A"), _feature(2, "Needs Human Review", "B"), _feature(3, "On Track", "C")]
    curated = [_curated(3, "On Track", "C")]  # both 1 and 2 dropped
    result = _risk_floor_check(features, curated)
    assert result["criterion"] == "risk_floor" and result["passed"] is False
    assert "1" in result["feedback"] and "2" in result["feedback"]
    print("  PASS  risk_floor fails and names every missing feature_id when Blocked/NHR are dropped")

    # On Track may legitimately be absent — not a failure
    features = [_feature(1, "On Track", "A")]
    result = _risk_floor_check(features, [])
    assert result["passed"] is True
    print("  PASS  risk_floor does not require On Track Features to be present")

    # --- _grounding_coverage_check ---
    curated = [_curated(1, "Blocked", "Vendor Integration Overhaul"), _curated(2, "On Track", "Internal Cleanup")]
    summary = "Vendor Integration Overhaul is Blocked on legal sign-off. Internal Cleanup work continues."
    result = _grounding_coverage_check(curated, summary)
    assert result["passed"] is True
    print("  PASS  grounding_coverage passes when every risk-floor Feature's title is named")

    curated = [_curated(1, "Blocked", "Vendor Integration Overhaul"), _curated(2, "On Track", "Internal Cleanup")]
    summary = "Internal Cleanup work continues on schedule."  # Blocked item never named
    result = _grounding_coverage_check(curated, summary)
    assert result["passed"] is False
    assert "Vendor Integration Overhaul" in result["feedback"]
    print("  PASS  grounding_coverage fails when a Blocked/At Risk/NHR Feature's title is never mentioned")

    # On Track titles are not required to be individually named
    curated = [_curated(1, "On Track", "Internal Cleanup")]
    result = _grounding_coverage_check(curated, "Everything is progressing well this week.")
    assert result["passed"] is True
    print("  PASS  grounding_coverage does not require On Track Feature titles to be named")

    # Case-insensitive match
    curated = [_curated(1, "At Risk", "Build Agentic Dashboard")]
    summary = "the build agentic dashboard effort is running behind schedule."
    result = _grounding_coverage_check(curated, summary)
    assert result["passed"] is True
    print("  PASS  grounding_coverage matches case-insensitively")


def run_structural_checks():
    print("\nStructural checks (no API/network call):")
    assert callable(critique_report)
    print("  PASS  critique_report is importable and callable")

    checks_props = CRITIQUE_SCHEMA["properties"]["checks"]["items"]["properties"]
    assert set(checks_props.keys()) == {"criterion", "passed", "feedback"}
    assert set(CRITIQUE_SCHEMA["required"]) == {"checks", "overall_feedback"}
    print("  PASS  CRITIQUE_SCHEMA has the expected shape (criterion/passed/feedback per check)")

    assert RISK_FLOOR_LABELS == {"Blocked", "At Risk", "Needs Human Review"}
    print("  PASS  imports the shared RISK_FLOOR_LABELS from common/risk_floor.py (not a local redefinition)")

    skill = load_skill(TEST_PROJECT_ID, "critique-agent", SKILLS_ROOT)
    assert skill.body.strip()
    print("  PASS  example critique-agent skill loads correctly")

    try:
        load_skill("nonexistent-project", "critique-agent", SKILLS_ROOT)
        print("  FAIL  expected FileNotFoundError for a project with no skill, got none")
        sys.exit(1)
    except FileNotFoundError:
        print("  PASS  missing skill fails loudly (no silent fallback to a default)")


def _sample_report(executive_summary: str, curated_features: list[dict], features: list[dict]) -> dict:
    return {
        "project_id": TEST_PROJECT_ID, "week_of": "2026-08-16", "rag_status": "Red",
        "executive_summary": executive_summary, "trend_line": "",
        "curated_features": curated_features, "curated_initiatives": [],
        "features": features, "initiatives": [], "prior_week": None,
    }


async def run_live_checks():
    print("\nFull config detected — running live critique_report checks against the real Anthropic API...\n")

    # A genuinely good report (grounded, on-topic, no filler) — modeled on synthesis_agent's
    # own real live output from earlier in this project.
    features = [
        _feature(101, "At Risk", "Build Agentic Dashboard"),
        _feature(205, "Blocked", "Vendor Integration Overhaul"),
        _feature(310, "On Track", "Internal Tooling Cleanup"),
    ]
    good_curated = [
        _curated(101, "At Risk", "Build Agentic Dashboard"),
        _curated(205, "Blocked", "Vendor Integration Overhaul"),
        _curated(310, "On Track", "Internal Tooling Cleanup"),
    ]
    good_summary = (
        "Overall status is Red, driven by Vendor Integration Overhaul, which is Blocked on legal "
        "sign-off for the vendor data-sharing addendum. Build Agentic Dashboard is At Risk, running "
        "behind schedule ahead of Friday's demo. Internal Tooling Cleanup is On Track."
    )
    good_report = _sample_report(good_summary, good_curated, features)

    result = await critique_report(good_report, TEST_PROJECT_ID, SKILLS_ROOT)
    print("=" * 70)
    print("critique_report FULL RAW OUTPUT (well-formed report):")
    print("=" * 70)
    print(json.dumps(result, indent=2))

    code_check_names = {"risk_floor", "grounding_coverage"}
    result_criteria = {c["criterion"] for c in result["checks"]}
    assert code_check_names.issubset(result_criteria), "both code-enforced checks must be present in the output"
    assert len(result["checks"]) > len(code_check_names), "skill-defined checks must also be present"
    assert next(c for c in result["checks"] if c["criterion"] == "risk_floor")["passed"] is True
    assert next(c for c in result["checks"] if c["criterion"] == "grounding_coverage")["passed"] is True
    print(f"\nPASS  well-formed report: risk_floor and grounding_coverage both passed, "
          f"{len(result['checks']) - len(code_check_names)} skill-defined check(s) also present")

    # A report with a real code-check violation (risk_floor): curated_features drops the
    # Blocked Feature entirely — not mocked, this exercises the real merged-output path.
    bad_curated = [_curated(310, "On Track", "Internal Tooling Cleanup")]  # 101 and 205 both dropped
    bad_report = _sample_report(good_summary, bad_curated, features)

    bad_result = await critique_report(bad_report, TEST_PROJECT_ID, SKILLS_ROOT)
    print("\n" + "=" * 70)
    print("critique_report FULL RAW OUTPUT (risk-floor-violating report):")
    print("=" * 70)
    print(json.dumps(bad_result, indent=2))

    assert bad_result["passed"] is False, "overall passed must be False when a code-enforced check fails"
    risk_floor_result = next(c for c in bad_result["checks"] if c["criterion"] == "risk_floor")
    assert risk_floor_result["passed"] is False
    assert "CODE-ENFORCED CHECK(S) FAILED" in bad_result["overall_feedback"]
    print("\nPASS  risk-floor violation in curated_features correctly fails the overall verdict, "
          "and overall_feedback leads with the code-enforced failure, not buried in prose")


async def main():
    print("Critique Agent — test suite\n")
    run_code_check_tests()
    run_structural_checks()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nANTHROPIC_API_KEY not set — skipping request validation and live checks.")
        print("Code-check and structural checks passed.")
        return

    print("\nRunning a request-construction check (expects a clean failure at Anthropic auth):\n")
    features = [_feature(1, "On Track", "A")]
    curated = [_curated(1, "On Track", "A")]
    placeholder_report = _sample_report("Everything is on track.", curated, features)
    try:
        await critique_report(placeholder_report, TEST_PROJECT_ID, SKILLS_ROOT, model="claude-sonnet-5")
        print("Unexpected: call succeeded — if this is a real key, proceeding to the full live run below.\n")
        await run_live_checks()
    except RuntimeError as err:
        if "invalid ANTHROPIC_API_KEY" in str(err):
            print(f"Got expected failure (this is success for a structural check): {err}")
            print("\nRequest construction validated. Code-check and structural checks passed.")
        else:
            raise


if __name__ == "__main__":
    asyncio.run(main())
