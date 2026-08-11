#!/usr/bin/env python3
"""
Structural checks + the revision loop's control-flow logic are always run, no
credentials needed — the 4 agent calls and both Archive calls are mocked, so this
verifies orchestrator.py's OWN coordination logic (attempt counting, feedback-passing,
the at-cap decision, the risk-floor hard stop firing BEFORE save) independent of
whether any real agent actually behaves as mocked.

A genuine full run needs real ADO + Anthropic + Neon credentials, same tier-3 pattern
as feature_agent's own live run.

Run with:
    python3 test_orchestrator.py
    ADO_ORG=... ADO_PROJECT=... ADO_PAT_BASE64=... ANTHROPIC_API_KEY=... DATABASE_URL=... \\
        REPORTS_DIR=... python3 test_orchestrator.py   # full live run_pipeline()
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import orchestrator as orch  # noqa: E402
from orchestrator import MAX_REVISIONS, _existing_features_for_status_report_agent, run_pipeline  # noqa: E402

TEST_PROJECT_ID = "ai-reports-demo"


def run_structural_checks():
    print("Structural checks (no API/network/DB call):")
    assert callable(run_pipeline)
    print("  PASS  run_pipeline is importable and callable")

    assert MAX_REVISIONS == 1
    print("  PASS  MAX_REVISIONS is 1 (1 initial pass + 1 revision — matches the cost estimate's "
          "'2 critique cycles assumed')")

    features = [{"feature_id": 101, "title": "Build Agentic Dashboard", "status_label": "At Risk"}]
    existing = _existing_features_for_status_report_agent(features)
    assert existing == [{"id": 101, "title": "Build Agentic Dashboard"}]
    print("  PASS  _existing_features_for_status_report_agent translates feature_id -> id "
          "(status_report_agent's _format_existing_features expects 'id', not 'feature_id')")


class _MockPatches:
    """Context manager: monkeypatches every external call orchestrator.py makes, so the
    revision-loop tests below exercise only orchestrator.py's own control flow."""

    def __init__(self, critique_sequence, feature_agent_result=None, status_report_result=None):
        self.critique_sequence = list(critique_sequence)
        self.feature_agent_result = feature_agent_result or [
            {"feature_id": 1, "title": "A", "status_label": "On Track", "short_description": "x",
             "progress_summary": "y", "risk": None, "evidence": []},
        ]
        self.status_report_result = status_report_result or []
        self.synthesize_calls = []
        self.save_calls = []

    async def _fake_ensure_project(self, project_id, name, input_config, database_url):
        pass

    async def _fake_investigate_all_committed_features(self, *args, **kwargs):
        return self.feature_agent_result

    async def _fake_investigate_all_status_reports(self, *args, **kwargs):
        return self.status_report_result

    async def _fake_synthesize_report(self, project_id, week_of, features, enrichments, initiatives,
                                       database_url, skills_root=None, model="claude-sonnet-5",
                                       debug=False, revision_feedback=None):
        self.synthesize_calls.append({"revision_feedback": revision_feedback})
        return {
            "project_id": project_id, "week_of": week_of, "rag_status": "Green",
            "executive_summary": "All good.", "trend_line": "", "curated_features": [],
            "curated_initiatives": [], "features": features, "initiatives": initiatives, "prior_week": None,
        }

    async def _fake_critique_report(self, report, project_id, skills_root=None, model="claude-sonnet-5"):
        return self.critique_sequence.pop(0)

    async def _fake_save_report_snapshot(self, project_id, report, database_url):
        self.save_calls.append({"project_id": project_id, "report": report})
        return {"report_id": 999}

    def __enter__(self):
        self._originals = {
            "_ensure_project": orch._ensure_project,
            "investigate_all_committed_features": orch.investigate_all_committed_features,
            "investigate_all_status_reports": orch.investigate_all_status_reports,
            "synthesize_report": orch.synthesize_report,
            "critique_report": orch.critique_report,
            "_save_report_snapshot": orch._save_report_snapshot,
        }
        orch._ensure_project = self._fake_ensure_project
        orch.investigate_all_committed_features = self._fake_investigate_all_committed_features
        orch.investigate_all_status_reports = self._fake_investigate_all_status_reports
        orch.synthesize_report = self._fake_synthesize_report
        orch.critique_report = self._fake_critique_report
        orch._save_report_snapshot = self._fake_save_report_snapshot
        return self

    def __exit__(self, *exc):
        for name, fn in self._originals.items():
            setattr(orch, name, fn)


def _passed(criteria_all_pass=True, risk_floor_passes=True):
    return {
        "passed": criteria_all_pass and risk_floor_passes,
        "checks": [
            {"criterion": "risk_floor", "passed": risk_floor_passes, "feedback": "x"},
            {"criterion": "grounding_coverage", "passed": True, "feedback": "x"},
            {"criterion": "tone", "passed": criteria_all_pass, "feedback": "needs work" if not criteria_all_pass else "fine"},
        ],
        "overall_feedback": "x",
    }


async def run_revision_loop_tests():
    print("\nRevision loop — mocked control-flow tests (no credentials needed):")

    # 1. Happy path: critique passes on the first attempt.
    with _MockPatches(critique_sequence=[_passed(True, True)]) as m:
        result = await run_pipeline(
            TEST_PROJECT_ID, "Test Project", "2026-08-16", "org", "proj", "pat==",
            "/reports", "postgresql://fake",
        )
    assert result["reviewed"] is True and result["attempts"] == 1
    assert len(m.save_calls) == 1
    assert m.synthesize_calls[0]["revision_feedback"] is None
    print("  PASS  critique passes on attempt 1: reviewed=True, attempts=1, saved once, no revision feedback sent")

    # 2. Revision path: fails once (non-risk-floor), passes on the 2nd attempt.
    with _MockPatches(critique_sequence=[_passed(False, True), _passed(True, True)]) as m:
        result = await run_pipeline(
            TEST_PROJECT_ID, "Test Project", "2026-08-16", "org", "proj", "pat==",
            "/reports", "postgresql://fake",
        )
    assert result["reviewed"] is True and result["attempts"] == 2
    assert len(m.save_calls) == 1
    assert m.synthesize_calls[0]["revision_feedback"] is None
    assert m.synthesize_calls[1]["revision_feedback"] is not None
    assert m.synthesize_calls[1]["revision_feedback"][0]["criterion"] == "tone"
    print("  PASS  one non-risk-floor failure then a pass: attempts=2, reviewed=True, "
          "attempt 2 received attempt 1's failed checks as revision_feedback")

    # 3. At-cap, still failing (non-risk-floor): proceeds and saves, flagged unreviewed.
    with _MockPatches(critique_sequence=[_passed(False, True), _passed(False, True)]) as m:
        result = await run_pipeline(
            TEST_PROJECT_ID, "Test Project", "2026-08-16", "org", "proj", "pat==",
            "/reports", "postgresql://fake", max_revisions=1,
        )
    assert result["reviewed"] is False and result["attempts"] == 2
    assert len(m.save_calls) == 1, "an unreviewed report must still be saved — Review Gate is the real human safety net"
    print("  PASS  still failing (non-risk-floor) at the cap: reviewed=False, attempts capped at 2, "
          "report is STILL saved (flagged unreviewed, not discarded)")

    # 4. risk_floor still failing: hard stop, raise, and — critically — save is NEVER called.
    with _MockPatches(critique_sequence=[_passed(True, False), _passed(True, False)]) as m:
        try:
            await run_pipeline(
                TEST_PROJECT_ID, "Test Project", "2026-08-16", "org", "proj", "pat==",
                "/reports", "postgresql://fake",
            )
            print("  FAIL  expected RuntimeError on a risk_floor failure, got none")
            sys.exit(1)
        except RuntimeError as err:
            assert "risk_floor" in str(err)
            assert len(m.save_calls) == 0, "save_report_snapshot must NEVER be called when risk_floor fails — trustworthiness is unknown"
            print(f"  PASS  risk_floor failure hard-stops with RuntimeError BEFORE save_report_snapshot "
                  f"is ever called (save_calls={len(m.save_calls)}): {err}")


async def run_live_pipeline():
    ado_org = os.environ["ADO_ORG"]
    ado_project = os.environ["ADO_PROJECT"]
    ado_pat_base64 = os.environ["ADO_PAT_BASE64"]
    database_url = os.environ["DATABASE_URL"]
    reports_dir = os.environ["REPORTS_DIR"]

    print("\n" + "=" * 70)
    print("FULL LIVE run_pipeline() — real ADO + real Anthropic + real Neon:")
    print("=" * 70 + "\n")

    result = await run_pipeline(
        project_id=TEST_PROJECT_ID,
        name="AI Reports Demo",
        week_of="2026-08-16",
        ado_org=ado_org,
        ado_project=ado_project,
        ado_pat_base64=ado_pat_base64,
        reports_dir=reports_dir,
        database_url=database_url,
        debug=True,
    )

    print("\n" + "=" * 70)
    print("run_pipeline FULL RAW OUTPUT:")
    print("=" * 70)
    print(json.dumps(result, indent=2))

    expected_keys = {"project_id", "week_of", "report_id", "rag_status", "reviewed", "attempts", "critique", "report"}
    assert set(result.keys()) == expected_keys
    assert set(result["report"].keys()) == {
        "project_id", "week_of", "rag_status", "executive_summary", "trend_line",
        "curated_features", "curated_initiatives", "features", "initiatives", "prior_week",
    }, "run_pipeline's report key must be synthesize_report's COMPLETE output, nested whole"
    print(f"\nPASS  run_pipeline completed end to end: report_id={result['report_id']}, "
          f"rag_status={result['rag_status']}, reviewed={result['reviewed']}, attempts={result['attempts']}")
    print("PASS  'report' key is the full synthesize_report() output nested whole (features/initiatives/prior_week included)")


async def main():
    print("core/orchestrator.py — test suite\n")
    run_structural_checks()
    await run_revision_loop_tests()
    print("\nAll structural and revision-loop checks passed.")

    required_vars = ["ADO_ORG", "ADO_PROJECT", "ADO_PAT_BASE64", "ANTHROPIC_API_KEY", "DATABASE_URL", "REPORTS_DIR"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"\n{', '.join(missing)} not set — skipping the full live run_pipeline() test.")
        return

    await run_live_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
