"""
review_gate/review_gate.py — Requirement 18's mandatory human approval gate. A human sees
the ACTUAL RENDERED SLIDE (not raw JSON/text) and must approve or reject with notes before
a report counts as final. Almost no new logic of its own — mostly integration of things
that already work: agents/slide_generation_agent's render_report() (Mode 2, fully
deterministic) does the actual rendering; archive/server.py's approve_report (new — see
docs/DECISION_LOG.md) records the decision. Every signature here was traced from each
component's actual current source before writing this, same discipline as
core/orchestrator.py's build — including confirming core/orchestrator.py's run_pipeline()
report shape is a strict superset of what render_report() needs, so no translation is
required between them (unlike the feature_id/id mismatch caught earlier in this build).

CLI is the intentional FINAL form here, not a placeholder for a future GUI/web app — the
same custom ask_human callable pattern as discovery_agent and slide_generation_agent, same
reasoning (AskUserQuestion investigated and rejected — see CLAUDE.md gotcha #13).

"Edit" (Requirement 18) means the PM's free-text notes are captured and attached to the
record via approve_report's new review_notes column — NOT inline editing of the rendered
slide content itself. That's explicitly out of scope.

Two call shapes, both real:
- run_review_gate(project_id, database_url, report=..., report_id=...) — the in-process
  chaining case, right after core/orchestrator.py's run_pipeline(): zero extra Archive
  round-trip, since run_pipeline()'s report dict already has everything render_report()
  needs.
- run_review_gate(project_id, database_url) alone — the standalone case: a PM running this
  as its own CLI invocation later, independent of when the pipeline ran. Fetches the
  latest pending report via archive's new get_latest_unreviewed_report tool.

A SlideFitError from render_report() (Requirement 16's escalation) is treated as an
automatic reject — routed through the exact same approve_report(approved=False, notes=...)
path a human rejection takes, not a separate mechanism. A report that can't even render
can't be shown to a human to judge, so "can't approve, here's why" is the honest
translation, not a crash.
"""
import asyncio
import sys
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
from mcp_client import open_mcp_client  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "slide_generation_agent"))
from slide_generation_agent import SlideFitError, render_report  # noqa: E402

ARCHIVE_SERVER_PATH = Path(__file__).parent.parent / "archive" / "server.py"


# =============================================================================
# ask_human — identical pattern to discovery_agent's/slide_generation_agent's,
# not cross-imported (established precedent — see docs/DECISION_LOG.md)
# =============================================================================

def default_ask_human(question: str, options: Optional[list[str]] = None) -> str:
    print(f"\n{question}")
    if options:
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        while True:
            raw = input("> ").strip()
            if raw in options:
                return raw
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1]
            print(f"Please enter one of: {', '.join(options)} (or its number).")
    return input("> ").strip()


# =============================================================================
# Archive calls
# =============================================================================

async def _get_latest_unreviewed_report(project_id: str, database_url: str) -> Optional[dict[str, Any]]:
    async with open_mcp_client(
        command=sys.executable, args=[str(ARCHIVE_SERVER_PATH)], env={"DATABASE_URL": database_url},
    ) as client:
        result = await client.call("get_latest_unreviewed_report", {"project_id": project_id})
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"get_latest_unreviewed_report failed for '{project_id}': {result['error']}")
    return result


async def _approve_report(report_id: int, approved: bool, notes: str, database_url: str) -> dict[str, Any]:
    async with open_mcp_client(
        command=sys.executable, args=[str(ARCHIVE_SERVER_PATH)], env={"DATABASE_URL": database_url},
    ) as client:
        result = await client.call("approve_report", {"report_id": report_id, "approved": approved, "notes": notes})
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"approve_report failed for report_id={report_id}: {result['error']}")
    return result


# =============================================================================
# run_review_gate — the one real Review Gate run
# =============================================================================

async def run_review_gate(
    project_id: str,
    database_url: str,
    report: Optional[dict[str, Any]] = None,
    report_id: Optional[int] = None,
    ask_human: Callable[..., str] = default_ask_human,
    skills_root: Optional[str] = None,
    output_dir: Optional[Path] = None,
    debug: bool = False,
) -> dict[str, Any]:
    """report/report_id must be given together (in-process chaining) or neither
    (standalone — fetches the latest pending report for project_id). Renders it, runs the
    approve/reject conversation (reject requires non-empty notes — loops until given,
    never lets a rejection go unexplained, same instinct as gotcha #15's caveat
    guarantee), persists the decision via approve_report, returns the outcome.

    Raises ValueError if report/report_id are given inconsistently (one without the
    other). Raises RuntimeError if standalone and nothing is pending.
    """
    if (report is None) != (report_id is None):
        raise ValueError("Pass both report and report_id together, or neither (to fetch the latest unreviewed report).")

    if report is None:
        fetched = await _get_latest_unreviewed_report(project_id, database_url)
        if fetched is None:
            raise RuntimeError(f"No unreviewed report found for project '{project_id}'. Nothing to review.")
        report_id = fetched["report_id"]
        report = {k: v for k, v in fetched.items() if k != "report_id"}
        if debug:
            print(f"[review_gate debug] fetched latest unreviewed report: report_id={report_id}, week_of={report.get('week_of')}\n")

    out_dir = Path(output_dir) if output_dir else Path(__file__).parent
    output_path = out_dir / f"{project_id}_{report.get('week_of', 'report')}_review.pptx"

    try:
        rendered_path = render_report(report, project_id, skills_root=skills_root, output_path=output_path, debug=debug)
    except SlideFitError as err:
        # Requirement 16's escalation reaches a real human-facing surface here for the
        # first time (see docs/DECISION_LOG.md — no review_gate existed to catch this
        # before now). A report that can't even render can't be shown to a human to
        # judge, so this is an automatic reject through the SAME approve_report path a
        # human rejection takes below, not a separate mechanism.
        print(f"\nCould not render report_id={report_id}: {err}\nAuto-rejecting — this cannot be shown to a human to judge.")
        result = await _approve_report(report_id, False, f"Auto-rejected: could not render — {err}", database_url)
        return {
            "project_id": project_id, "report_id": report_id, "week_of": report.get("week_of"),
            "rendered_path": None, "approved": False, "notes": result["review_notes"],
            "pm_approved_at": result["pm_approved_at"],
        }

    decision = ask_human(
        f"Rendered report_id={report_id} (week_of={report.get('week_of')}, rag_status={report['rag_status']}) "
        f"to: {rendered_path}\nOpen it and review the actual slides. Approve or reject?",
        options=["Approve", "Reject"],
    )
    approved = decision == "Approve"

    if approved:
        notes = ask_human("Any notes to record with this approval? (blank to skip)")
    else:
        notes = ""
        while not notes.strip():
            notes = ask_human("What should change? (required — this is the only record of why this was rejected)")

    result = await _approve_report(report_id, approved, notes, database_url)
    if debug:
        print(f"[review_gate debug] approve_report: {result}\n")

    return {
        "project_id": project_id, "report_id": report_id, "week_of": report.get("week_of"),
        "rendered_path": rendered_path, "approved": approved, "notes": notes,
        "pm_approved_at": result["pm_approved_at"],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Review Gate — the mandatory human approval step. Run this yourself; see README.md.")
    parser.add_argument("project_id")
    parser.add_argument("database_url")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--skills-root", default=None)
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    async def _main():
        result = await run_review_gate(
            args.project_id, args.database_url, skills_root=args.skills_root,
            output_dir=Path(args.output_dir) if args.output_dir else None, debug=args.debug,
        )
        print(f"\nDone. report_id={result['report_id']} approved={result['approved']} pm_approved_at={result['pm_approved_at']}")

    asyncio.run(_main())
