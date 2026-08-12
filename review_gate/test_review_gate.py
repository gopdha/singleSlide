#!/usr/bin/env python3
"""
Structural checks (report/report_id pairing validation, default_ask_human's input
validation) always run — no credentials needed. The scripted-conversation integration
tier mocks render_report and both archive calls, proving the approve path, the
reject-requires-notes loop, the SlideFitError-auto-reject path (confirmed to route
through the SAME approve_report call a human rejection uses, not a separate mechanism),
and both call shapes (in-process chaining vs. standalone fetch) actually work.

Genuine tier 3 is NOT automated — it needs a live human decision on a real rendered
deck. Run review_gate.py directly yourself; see README.md.

Run with:
    python3 test_review_gate.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import review_gate as rg  # noqa: E402
from review_gate import default_ask_human, run_review_gate  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "slide_generation_agent"))
from slide_generation_agent import SlideFitError  # noqa: E402

TEST_PROJECT_ID = "review-gate-test-project"
FAKE_DATABASE_URL = "postgresql://fake"

SAMPLE_REPORT = {
    "project_id": TEST_PROJECT_ID, "week_of": "2026-08-16", "rag_status": "Amber",
    "executive_summary": "Steady progress with one at-risk item.", "trend_line": "",
    "curated_features": [{"feature_id": 1, "title": "Build Agentic Dashboard", "status_label": "At Risk", "display_text": "x"}],
    "curated_initiatives": [], "features": [], "initiatives": [], "prior_week": None,
}


async def run_pure_unit_tests():
    print("Pure unit tests (no credentials, no mocking):")

    try:
        await run_review_gate(TEST_PROJECT_ID, FAKE_DATABASE_URL, report=SAMPLE_REPORT, report_id=None)
        print("  FAIL  expected ValueError when report is given without report_id, got none")
        sys.exit(1)
    except ValueError as err:
        assert "together" in str(err).lower()
        print(f"  PASS  report given without report_id raises ValueError: {err}")

    try:
        await run_review_gate(TEST_PROJECT_ID, FAKE_DATABASE_URL, report=None, report_id=42)
        print("  FAIL  expected ValueError when report_id is given without report, got none")
        sys.exit(1)
    except ValueError as err:
        assert "together" in str(err).lower()
        print(f"  PASS  report_id given without report raises ValueError: {err}")


def run_default_ask_human_tests():
    print("\ndefault_ask_human — input-validation logic (monkeypatched stdin):")
    import builtins

    original_input = builtins.input
    try:
        answers = iter(["2"])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Pick one:", options=["Approve", "Reject"]) == "Reject"
        print("  PASS  numeric selection returns the corresponding option")

        answers = iter(["nonsense", "Approve"])
        builtins.input = lambda prompt="": next(answers)
        assert default_ask_human("Pick one:", options=["Approve", "Reject"]) == "Approve"
        print("  PASS  invalid input is rejected and re-prompted, never silently accepted")
    finally:
        builtins.input = original_input


class _ScriptedAskHuman:
    """Same instinct as discovery_agent's own test helper — records every question asked
    and pops canned answers in sequence."""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.questions_asked: list[tuple] = []

    def __call__(self, question, options=None):
        self.questions_asked.append((question, options))
        if not self.answers:
            raise AssertionError(f"Ran out of scripted answers at question: {question!r}")
        return self.answers.pop(0)


class _MockPatches:
    """Monkeypatches render_report and both archive calls — the real report/report_id
    pairing logic, the reject-requires-notes loop, and the SlideFitError routing all run
    for real; only the render and the network are faked."""

    def __init__(self, render_result=None, render_raises=None, unreviewed_result=None):
        self.render_result = render_result or Path("/fake/output.pptx")
        self.render_raises = render_raises
        self.unreviewed_result = unreviewed_result
        self.render_calls: list[dict] = []
        self.approve_calls: list[dict] = []
        self.get_unreviewed_calls: list[str] = []

    def _fake_render_report(self, report, project_id, skills_root=None, output_path=None, debug=False):
        self.render_calls.append({"report": report, "project_id": project_id, "output_path": output_path})
        if self.render_raises:
            raise self.render_raises
        return self.render_result

    async def _fake_get_latest_unreviewed_report(self, project_id, database_url):
        self.get_unreviewed_calls.append(project_id)
        return self.unreviewed_result

    async def _fake_approve_report(self, report_id, approved, notes, database_url):
        self.approve_calls.append({"report_id": report_id, "approved": approved, "notes": notes})
        return {"report_id": report_id, "pm_approved_at": "2026-08-16T12:00:00" if approved else None, "review_notes": notes}

    def __enter__(self):
        self._originals = {
            "render_report": rg.render_report,
            "_get_latest_unreviewed_report": rg._get_latest_unreviewed_report,
            "_approve_report": rg._approve_report,
        }
        rg.render_report = self._fake_render_report
        rg._get_latest_unreviewed_report = self._fake_get_latest_unreviewed_report
        rg._approve_report = self._fake_approve_report
        return self

    def __exit__(self, *exc):
        for name, fn in self._originals.items():
            setattr(rg, name, fn)


async def run_integration_tests():
    print("\nrun_review_gate — scripted-conversation integration tests:")

    # 1. Approve path, in-process chaining (report+report_id given directly)
    scripted = _ScriptedAskHuman(["Approve", "Looks good."])
    with _MockPatches() as mocks:
        result = await run_review_gate(
            TEST_PROJECT_ID, FAKE_DATABASE_URL, report=SAMPLE_REPORT, report_id=101, ask_human=scripted,
        )
    assert result["approved"] is True and result["pm_approved_at"] is not None
    assert len(mocks.render_calls) == 1 and mocks.render_calls[0]["report"] is SAMPLE_REPORT
    assert mocks.approve_calls[0] == {"report_id": 101, "approved": True, "notes": "Looks good."}
    assert len(mocks.get_unreviewed_calls) == 0, "in-process chaining must not touch Archive's fetch tool"
    print("  PASS  approve path (in-process chaining): renders the given report directly, "
          "no Archive fetch, approve_report called with approved=True")

    # 2. Reject path — notes required, loops on blank/whitespace-only input until given
    scripted2 = _ScriptedAskHuman(["Reject", "", "  ", "Trend line is missing context."])
    with _MockPatches() as mocks2:
        result2 = await run_review_gate(
            TEST_PROJECT_ID, FAKE_DATABASE_URL, report=SAMPLE_REPORT, report_id=102, ask_human=scripted2,
        )
    assert result2["approved"] is False
    assert mocks2.approve_calls[0]["notes"] == "Trend line is missing context."
    assert mocks2.approve_calls[0]["approved"] is False
    print("  PASS  reject path: blank/whitespace-only notes are re-prompted until real "
          "notes are given, never silently accepting an unexplained rejection")

    # 3. SlideFitError -> automatic reject through the SAME approve_report path, not a
    # separate mechanism — no ask_human question should even be asked
    scripted3 = _ScriptedAskHuman([])  # must NOT be consulted at all
    with _MockPatches(render_raises=SlideFitError("Feature Status slide: does not fit")) as mocks3:
        result3 = await run_review_gate(
            TEST_PROJECT_ID, FAKE_DATABASE_URL, report=SAMPLE_REPORT, report_id=103, ask_human=scripted3,
        )
    assert result3["approved"] is False and result3["rendered_path"] is None
    assert len(mocks3.approve_calls) == 1
    assert mocks3.approve_calls[0]["approved"] is False
    assert "could not render" in mocks3.approve_calls[0]["notes"].lower()
    assert "does not fit" in mocks3.approve_calls[0]["notes"]
    assert len(scripted3.questions_asked) == 0, "a SlideFitError must auto-reject without ever asking the PM approve/reject"
    print("  PASS  SlideFitError auto-rejects through the exact same approve_report(approved=False) "
          "call a human rejection uses — not a separate mechanism, and never asks the PM a question first")

    # 4. Standalone fetch — report/report_id both omitted, fetched from Archive
    fetched = {**{k: v for k, v in SAMPLE_REPORT.items() if k not in ("features", "initiatives", "prior_week")}, "report_id": 104}
    scripted4 = _ScriptedAskHuman(["Approve", ""])
    with _MockPatches(unreviewed_result=fetched) as mocks4:
        result4 = await run_review_gate(TEST_PROJECT_ID, FAKE_DATABASE_URL, ask_human=scripted4)
    assert result4["report_id"] == 104
    assert mocks4.get_unreviewed_calls == [TEST_PROJECT_ID]
    assert "report_id" not in mocks4.render_calls[0]["report"], \
        "the fetched report_id key must not leak into the report dict passed to render_report"
    print("  PASS  standalone mode (no report/report_id given): fetches the latest unreviewed "
          "report from Archive, strips report_id out of the report dict before rendering")

    # 5. Standalone fetch, nothing pending -> loud RuntimeError, never a silent no-op
    with _MockPatches(unreviewed_result=None):
        try:
            await run_review_gate(TEST_PROJECT_ID, FAKE_DATABASE_URL)
            print("  FAIL  expected RuntimeError when nothing is pending, got none")
            sys.exit(1)
        except RuntimeError as err:
            assert "nothing to review" in str(err).lower()
            print(f"  PASS  standalone mode with nothing pending raises RuntimeError: {err}")


async def main():
    print("Review Gate — test suite\n")
    await run_pure_unit_tests()
    run_default_ask_human_tests()
    await run_integration_tests()
    print("\nAll pure unit and scripted-conversation integration tests passed.")
    print("\nGenuine tier 3 (a real human decision on a real rendered deck) is NOT automated "
          "— run: python3 review_gate.py <project_id> <database_url>")


if __name__ == "__main__":
    asyncio.run(main())
