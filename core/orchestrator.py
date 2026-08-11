"""
core/orchestrator.py — coordination only, zero content decisions (CLAUDE.md's core
architectural principle). Wires Feature Agent -> Status Report Agent -> Synthesis Agent
-> Critique Agent (bounded revision loop) -> Archive into one real end-to-end weekly
pipeline run. Every signature here was traced from each component's actual current
source, not assumed — see docs/DECISION_LOG.md for what that tracing found (the
existing_features id/feature_id shape mismatch, the ensure_project-before-save FK
requirement) and the design decisions made building this component (the revision-loop
cap, the risk-floor-hard-stop convention, trend_line's storage resolution).
"""
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
from mcp_client import open_mcp_client  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "feature_agent"))
from feature_agent import investigate_all_committed_features  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "status_report_agent"))
from status_report_agent import investigate_all_status_reports  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "synthesis_agent"))
from synthesis_agent import synthesize_report  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "agents" / "critique_agent"))
from critique_agent import critique_report  # noqa: E402

ARCHIVE_SERVER_PATH = Path(__file__).parent.parent / "archive" / "server.py"

# Matches docs/DECISION_LOG.md's cost estimate, which already assumed "2 critique
# cycles": 1 initial Synthesis+Critique pass + at most 1 revision.
MAX_REVISIONS = 1


def _existing_features_for_status_report_agent(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """status_report_agent's existing_features param expects {"id":..., "title":...} —
    the shape feature_agent's OWN list_committed_features() (the deterministic listing
    step) produces, NOT investigate_all_committed_features()'s final output, which uses
    'feature_id' per FEATURE_SCHEMA. Traced directly from status_report_agent's
    _format_existing_features, not assumed — passing investigate_all_committed_features's
    output straight through would KeyError inside status_report_agent."""
    return [{"id": f["feature_id"], "title": f["title"]} for f in features]


async def _ensure_project(project_id: str, name: str, input_config: dict[str, Any], database_url: str) -> None:
    async with open_mcp_client(
        command=sys.executable, args=[str(ARCHIVE_SERVER_PATH)], env={"DATABASE_URL": database_url},
    ) as client:
        result = await client.call("ensure_project", {"project_id": project_id, "name": name, "input_config": input_config})
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"ensure_project failed for '{project_id}': {result['error']}")


async def _save_report_snapshot(project_id: str, report: dict[str, Any], database_url: str) -> dict[str, Any]:
    async with open_mcp_client(
        command=sys.executable, args=[str(ARCHIVE_SERVER_PATH)], env={"DATABASE_URL": database_url},
    ) as client:
        result = await client.call("save_report_snapshot", {"project_id": project_id, "report": report})
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"save_report_snapshot failed for '{project_id}': {result['error']}")
    return result


async def run_pipeline(
    project_id: str,
    name: str,
    week_of: str,
    ado_org: str,
    ado_project: str,
    ado_pat_base64: str,
    reports_dir: str,
    database_url: str,
    skills_root: Optional[str] = None,
    model: str = "claude-sonnet-5",
    max_revisions: int = MAX_REVISIONS,
    debug: bool = False,
) -> dict[str, Any]:
    """The one real end-to-end weekly run. Coordination only — every content decision
    (Feature status, curation, prose, critique verdict) is made by the component that
    owns it; this function only sequences calls, translates shapes between components,
    and applies the loud-failure/hard-stop rules documented in docs/DECISION_LOG.md.

    Returns {project_id, week_of, report_id, rag_status, reviewed: bool, attempts: int,
    critique: {...}, report: {...}} — `report` is synthesize_report()'s COMPLETE output
    nested whole (including features, initiatives, prior_week), not a trimmed subset;
    Review Gate (not yet built) will need the full picture, not just summary fields.
    """
    input_config = {"ado_org": ado_org, "ado_project": ado_project, "reports_dir": reports_dir}

    # Step 0: ensure_project MUST run before save_report_snapshot — project_id is an FK
    # on weekly_reports. Run it first, not last, so a DB connectivity problem fails fast,
    # before any real (billed) API calls happen.
    await _ensure_project(project_id, name, input_config, database_url)
    if debug:
        print(f"[orchestrator debug] ensure_project('{project_id}') done\n")

    # Step 1: Feature Agent. Per-item failures are already absorbed here (downgraded to
    # Needs Human Review, never raised) — nothing extra needed at this level.
    features = await investigate_all_committed_features(
        ado_org, ado_project, ado_pat_base64, project_id, skills_root, model,
    )
    if debug:
        print(f"[orchestrator debug] feature_agent: {len(features)} Feature(s) investigated\n")

    # Step 2: Status Report Agent — shape-translate existing_features first.
    existing_features = _existing_features_for_status_report_agent(features)
    status_reports = await investigate_all_status_reports(
        reports_dir, existing_features, project_id, skills_root, model,
    )
    if debug:
        print(f"[orchestrator debug] status_report_agent: {len(status_reports)} report(s) investigated\n")

    # Step 3: flatten across every team lead's report — Synthesis needs the combined
    # view (Requirement 9's fan-in), not one report at a time.
    enrichments = [e for r in status_reports for e in r["potential_enrichments"]]
    initiatives = [i for r in status_reports for i in r["other_initiatives"]]

    # Step 4: Synthesis + Critique, bounded revision loop.
    report: dict[str, Any] = {}
    critique_result: dict[str, Any] = {}
    revision_feedback: Optional[list[dict[str, Any]]] = None
    attempt = 0
    while True:
        attempt += 1
        report = await synthesize_report(
            project_id, week_of, features, enrichments, initiatives, database_url,
            skills_root, model, debug=debug, revision_feedback=revision_feedback,
        )
        critique_result = await critique_report(report, project_id, skills_root, model)
        if debug:
            print(f"[orchestrator debug] attempt {attempt}: critique passed={critique_result['passed']}\n")

        if critique_result["passed"]:
            break

        risk_floor_check = next(c for c in critique_result["checks"] if c["criterion"] == "risk_floor")
        if not risk_floor_check["passed"]:
            # Structurally should be impossible: curate_report's own validation runs on
            # every call (including revisions) and raises before ever returning a report
            # with a risk-floor violation. If critique's independent re-check disagrees,
            # that disagreement — not any content judgment — is the problem. Hard stop,
            # BEFORE save_report_snapshot is ever reached below: the report's
            # trustworthiness is unknown, and it must never be persisted in that state.
            # See docs/DECISION_LOG.md ("a code-enforced check failing after independent
            # re-verification is a bug, not a content judgment call").
            raise RuntimeError(
                "critique_report's risk_floor re-check failed even though synthesize_report "
                "completed successfully — curate_report's own validation should have caught "
                "this first. This indicates a real bug (a disagreement between curate_report's "
                "and critique_report's risk-floor logic), not expected critique variance. "
                f"Refusing to save. checks: {critique_result['checks']}"
            )

        if attempt > max_revisions:
            break

        revision_feedback = [c for c in critique_result["checks"] if not c["passed"]]
        if debug:
            print(f"[orchestrator debug] revising (attempt {attempt + 1}/{max_revisions + 1}), "
                  f"feedback: {revision_feedback}\n")

    reviewed = critique_result["passed"]

    # Step 5: persist. Always reached when we get here (the risk-floor hard stop above
    # raises before this point, so it never does) — Review Gate (Requirement 18) is the
    # real human safety net; a report that never fully passed critique should still
    # reach a human, flagged, not vanish.
    save_result = await _save_report_snapshot(project_id, report, database_url)
    if debug:
        print(f"[orchestrator debug] save_report_snapshot: report_id={save_result['report_id']}\n")

    return {
        "project_id": project_id,
        "week_of": week_of,
        "report_id": save_result["report_id"],
        "rag_status": report["rag_status"],
        "reviewed": reviewed,
        "attempts": attempt,
        "critique": critique_result,
        "report": report,
    }
