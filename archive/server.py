#!/usr/bin/env python3
"""
Archive MCP Server — persistence for SingleSlide, over Postgres (Neon-compatible).
Schema and tool design: docs/DECISION_LOG.md ("Archive schema design decisions" and
"Archive schema — additional confirmed design choices").

Each tool has a plain async implementation function (importable and directly testable,
no MCP protocol needed) plus a thin @mcp.tool()-decorated wrapper that catches exceptions
and returns {"error": str(exc)} instead of letting them raise through MCP — same pattern
as mcp_servers/ppt_mcp/server.py's parse_slide_file()/parse_slide() split.

Run standalone (stdio transport) with:
    DATABASE_URL="postgresql://..." python3 server.py
"""
import asyncio
import os
import sys
from datetime import date, datetime
from typing import Any, Optional

import asyncpg
# mcp>=2.0.0 renamed/relocated FastMCP to mcp.server.mcpserver.MCPServer — same API
# surface (name=, .tool() decorator, .run_stdio_async()), different import path.
# Verified against this environment's installed mcp==2.0.0 before use (see CLAUDE.md
# gotcha #9 — don't assume this package's API surface is stable across versions).
from mcp.server.mcpserver import MCPServer as FastMCP

mcp = FastMCP(name="archive-mcp")

_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Registers automatic dict/list <-> jsonb (de)serialization so callers never
    have to json.dumps/loads the JSONB columns (input_config, profile,
    curated_features, curated_initiatives) by hand."""
    import json

    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:  # re-check inside the lock — avoid a duplicate pool on a race
                database_url = os.environ["DATABASE_URL"]
                _pool = await asyncpg.create_pool(database_url, init=_init_connection)
    return _pool


def _iso(value: Any) -> Any:
    """datetime/date -> ISO string for JSON-safe tool results; passes through anything else."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


# ---------------------------------------------------------------------------
# ensure_project
# ---------------------------------------------------------------------------

async def ensure_project_impl(project_id: str, name: str, input_config: dict[str, Any]) -> dict[str, Any]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO projects (project_id, name, input_config)
            VALUES ($1, $2, $3)
            ON CONFLICT (project_id) DO UPDATE
                SET name = EXCLUDED.name,
                    input_config = EXCLUDED.input_config,
                    updated_at = now()
            RETURNING project_id, (xmax = 0) AS created
            """,
            project_id, name, input_config,
        )
        return {"project_id": row["project_id"], "created": row["created"]}


@mcp.tool(
    name="ensure_project",
    description="Get-or-create a project by its caller-supplied project_id (the same slug "
                "used under skills/<project_id>/ — never derived here). Upserts name and "
                "input_config on every call. Returns {project_id, created}.",
)
async def ensure_project(project_id: str, name: str, input_config: dict[str, Any]) -> dict[str, Any]:
    try:
        return await ensure_project_impl(project_id, name, input_config)
    except Exception as exc:  # noqa: BLE001 — surfaced to the MCP client as a tool error
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# get_prior_week_report
# ---------------------------------------------------------------------------

async def get_prior_week_report_impl(project_id: str) -> Optional[dict[str, Any]]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        report_row = await conn.fetchrow(
            """
            SELECT report_id, week_of, rag_status, executive_summary, trend_line,
                   curated_features, curated_initiatives, pm_approved_at
            FROM weekly_reports
            WHERE project_id = $1 AND pm_approved_at IS NOT NULL
            ORDER BY week_of DESC
            LIMIT 1
            """,
            project_id,
        )
        if report_row is None:
            return None

        report_id = report_row["report_id"]
        feature_rows = await conn.fetch(
            """
            SELECT ado_feature_id, title, short_description, status_label,
                   progress_summary, risk, evidence
            FROM feature_snapshots
            WHERE report_id = $1
            ORDER BY ado_feature_id
            """,
            report_id,
        )
        initiative_rows = await conn.fetch(
            """
            SELECT title, narrative_summary, evidence
            FROM initiative_snapshots
            WHERE report_id = $1
            ORDER BY title
            """,
            report_id,
        )

    return {
        "report_id": report_row["report_id"],
        "week_of": _iso(report_row["week_of"]),
        "rag_status": report_row["rag_status"],
        "executive_summary": report_row["executive_summary"],
        "trend_line": report_row["trend_line"],
        "curated_features": report_row["curated_features"],
        "curated_initiatives": report_row["curated_initiatives"],
        "pm_approved_at": _iso(report_row["pm_approved_at"]),
        "features": [
            {
                "ado_feature_id": r["ado_feature_id"],
                "title": r["title"],
                "short_description": r["short_description"],
                "status_label": r["status_label"],
                "progress_summary": r["progress_summary"],
                "risk": r["risk"],
                "evidence": list(r["evidence"]),
            }
            for r in feature_rows
        ],
        "initiatives": [
            {"title": r["title"], "narrative_summary": r["narrative_summary"], "evidence": list(r["evidence"])}
            for r in initiative_rows
        ],
    }


@mcp.tool(
    name="get_prior_week_report",
    description="The most recent APPROVED weekly report for this project (pm_approved_at "
                "IS NOT NULL, latest week_of), with its full feature and initiative "
                "snapshots. Returns null if no report has ever been approved yet.",
)
async def get_prior_week_report(project_id: str) -> Optional[dict[str, Any]]:
    try:
        return await get_prior_week_report_impl(project_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# save_report_snapshot
# ---------------------------------------------------------------------------

async def save_report_snapshot_impl(project_id: str, report: dict[str, Any]) -> dict[str, Any]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            report_row = await conn.fetchrow(
                """
                INSERT INTO weekly_reports
                    (project_id, week_of, rag_status, executive_summary, trend_line,
                     curated_features, curated_initiatives, pm_approved_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NULL)
                ON CONFLICT (project_id, week_of) DO UPDATE
                    SET rag_status = EXCLUDED.rag_status,
                        executive_summary = EXCLUDED.executive_summary,
                        trend_line = EXCLUDED.trend_line,
                        curated_features = EXCLUDED.curated_features,
                        curated_initiatives = EXCLUDED.curated_initiatives,
                        pm_approved_at = NULL
                RETURNING report_id
                """,
                project_id,
                date.fromisoformat(report["week_of"]),
                report["rag_status"],
                report["executive_summary"],
                report["trend_line"],
                report["curated_features"],
                report["curated_initiatives"],
            )
            report_id = report_row["report_id"]

            await conn.execute("DELETE FROM feature_snapshots WHERE report_id = $1", report_id)
            await conn.execute("DELETE FROM initiative_snapshots WHERE report_id = $1", report_id)

            for f in report["features"]:
                await conn.execute(
                    """
                    INSERT INTO feature_snapshots
                        (report_id, ado_feature_id, title, short_description, status_label,
                         progress_summary, risk, evidence)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    report_id, f["feature_id"], f["title"], f["short_description"],
                    f["status_label"], f["progress_summary"], f["risk"], f["evidence"],
                )

            for i in report["initiatives"]:
                await conn.execute(
                    """
                    INSERT INTO initiative_snapshots (report_id, title, narrative_summary, evidence)
                    VALUES ($1, $2, $3, $4)
                    """,
                    report_id, i["title"], i["narrative_summary"], i["evidence"],
                )

    return {"report_id": report_id}


@mcp.tool(
    name="save_report_snapshot",
    description="One transactional write for a full week's data: upserts weekly_reports "
                "keyed on (project_id, week_of) — resetting pm_approved_at to NULL if that "
                "week already existed and was approved — then replaces its "
                "feature_snapshots/initiative_snapshots wholesale. Returns {report_id}.",
)
async def save_report_snapshot(project_id: str, report: dict[str, Any]) -> dict[str, Any]:
    try:
        return await save_report_snapshot_impl(project_id, report)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# get_latest_unreviewed_report
# ---------------------------------------------------------------------------

async def get_latest_unreviewed_report_impl(project_id: str) -> Optional[dict[str, Any]]:
    """Deliberately leaner than get_prior_week_report_impl — no feature_snapshots/
    initiative_snapshots join. review_gate/render_report() never reads features/
    initiatives (only rag_status/executive_summary/trend_line/curated_features/
    curated_initiatives), so there's no reason to fetch data nobody consumes."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT report_id, week_of, rag_status, executive_summary, trend_line,
                   curated_features, curated_initiatives
            FROM weekly_reports
            WHERE project_id = $1 AND pm_approved_at IS NULL
            ORDER BY week_of DESC
            LIMIT 1
            """,
            project_id,
        )
    if row is None:
        return None
    return {
        "report_id": row["report_id"],
        "week_of": _iso(row["week_of"]),
        "rag_status": row["rag_status"],
        "executive_summary": row["executive_summary"],
        "trend_line": row["trend_line"],
        "curated_features": row["curated_features"],
        "curated_initiatives": row["curated_initiatives"],
    }


@mcp.tool(
    name="get_latest_unreviewed_report",
    description="The most recent weekly report for this project still pending Review Gate "
                "(pm_approved_at IS NULL, latest week_of) — enough to render, not the full "
                "feature/initiative snapshots. Returns null if nothing is pending.",
)
async def get_latest_unreviewed_report(project_id: str) -> Optional[dict[str, Any]]:
    try:
        return await get_latest_unreviewed_report_impl(project_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# approve_report
# ---------------------------------------------------------------------------

async def approve_report_impl(report_id: int, approved: bool, notes: str = "") -> dict[str, Any]:
    """Sets pm_approved_at iff approved (a reject leaves it NULL — still 'pending' by the
    column's existing semantics, so a rejected report never masquerades as the approved
    prior week via get_prior_week_report). notes is always written, approve or reject —
    Review Gate's own conversation enforces non-empty notes on reject; this tool is a
    thin, honest primitive that doesn't duplicate that policy."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE weekly_reports
            SET pm_approved_at = CASE WHEN $2 THEN now() ELSE NULL END,
                review_notes = $3
            WHERE report_id = $1
            RETURNING report_id, pm_approved_at, review_notes
            """,
            report_id, approved, notes,
        )
    if row is None:
        raise ValueError(f"No weekly_reports row found for report_id {report_id}.")
    return {"report_id": row["report_id"], "pm_approved_at": _iso(row["pm_approved_at"]), "review_notes": row["review_notes"]}


@mcp.tool(
    name="approve_report",
    description="Records a PM's Review Gate decision for report_id — sets pm_approved_at to "
                "now() if approved, leaves it NULL (still pending) if not — and always writes "
                "notes. Errors loudly if report_id doesn't exist.",
)
async def approve_report(report_id: int, approved: bool, notes: str = "") -> dict[str, Any]:
    try:
        return await approve_report_impl(report_id, approved, notes)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# save_preference_profile
# ---------------------------------------------------------------------------

async def save_preference_profile_impl(project_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO preference_profiles (project_id, profile)
            VALUES ($1, $2)
            ON CONFLICT (project_id) DO UPDATE
                SET profile = EXCLUDED.profile, updated_at = now()
            RETURNING profile_id
            """,
            project_id, profile,
        )
        return {"profile_id": row["profile_id"]}


@mcp.tool(
    name="save_preference_profile",
    description="Upsert keyed on project_id (one profile per project — re-running "
                "Discovery updates in place, never duplicates). Returns {profile_id}.",
)
async def save_preference_profile(project_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    try:
        return await save_preference_profile_impl(project_id, profile)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# list_available_inputs
# ---------------------------------------------------------------------------

async def list_available_inputs_impl(project_id: str) -> dict[str, Any]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT input_config FROM projects WHERE project_id = $1", project_id)
    if row is None:
        raise ValueError(f"No project found for project_id '{project_id}'. Call ensure_project first.")
    return {"project_id": project_id, "input_config": row["input_config"]}


@mcp.tool(
    name="list_available_inputs",
    description="Read-only reflection of a project's stored input_config. Errors loudly "
                "if project_id doesn't exist rather than silently returning empty — a "
                "caller asking about a project's inputs should already have ensure_project'd it.",
)
async def list_available_inputs(project_id: str) -> dict[str, Any]:
    try:
        return await list_available_inputs_impl(project_id)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
