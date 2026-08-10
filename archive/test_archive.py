#!/usr/bin/env python3
"""
Structural checks (schema.sql content, importability) always run — no DB needed.
The full live tier needs a real Postgres connection (local or Neon), not an
Anthropic API key — Archive has no LLM in it anywhere, it's pure persistence.

Run with:
    python3 test_archive.py
    DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require" python3 test_archive.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "common"))
from mcp_client import open_mcp_client  # noqa: E402

ARCHIVE_DIR = Path(__file__).parent
SCHEMA_PATH = ARCHIVE_DIR / "schema.sql"
SERVER_PATH = ARCHIVE_DIR / "server.py"
TEST_PROJECT_ID = "archive-test-project"


def run_structural_checks():
    print("Structural checks (no DB connection):")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    # Strip '-- ...' line comments before substring-checking column/constraint absence —
    # otherwise a comment explaining *why* something is absent (which necessarily mentions
    # its name) trips a false positive.
    schema_sql_no_comments = "\n".join(line.split("--", 1)[0] for line in schema_sql.splitlines())

    for table in ("projects", "preference_profiles", "weekly_reports", "feature_snapshots", "initiative_snapshots"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema_sql, f"missing table {table}"
    print("  PASS  schema.sql defines all 5 expected tables")

    initiative_table_start = schema_sql_no_comments.index("CREATE TABLE IF NOT EXISTS initiative_snapshots")
    initiative_table_body = schema_sql_no_comments[initiative_table_start:schema_sql_no_comments.index(");", initiative_table_start)]
    assert "status_label" not in initiative_table_body, \
        "initiative_snapshots must have no status_label column, by design"
    print("  PASS  initiative_snapshots has no status_label column (narrative-only, as designed)")

    assert "template_id" not in schema_sql_no_comments, "no template_id FK anywhere — templates are Skills, not DB rows"
    print("  PASS  no template_id foreign key anywhere (templates are Skills, not DB rows)")

    assert "TEXT[]" in schema_sql_no_comments, "evidence columns should be native TEXT[], not JSONB"
    print("  PASS  evidence columns use TEXT[] (not JSONB)")

    assert SERVER_PATH.exists()
    server_src = SERVER_PATH.read_text(encoding="utf-8")
    for tool in ("ensure_project", "get_prior_week_report", "save_report_snapshot",
                 "save_preference_profile", "list_available_inputs"):
        assert f'name="{tool}"' in server_src, f"server.py missing @mcp.tool for {tool}"
    print("  PASS  server.py declares all 5 tools")

    assert "mcp.server.mcpserver import MCPServer" in server_src, \
        "server.py must use the verified mcp>=2.0.0 import path (see CLAUDE.md gotcha #9)"
    print("  PASS  server.py uses the verified MCPServer import path")


async def run_live_checks(database_url: str):
    import asyncpg

    print(f"\nFull config detected — running live checks against Postgres...\n")

    # Clean slate: a prior failed run may have left this test project behind.
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute("DELETE FROM projects WHERE project_id = $1", TEST_PROJECT_ID)
    finally:
        await conn.close()

    try:
        async with open_mcp_client(command=sys.executable, args=[str(SERVER_PATH)],
                                    env={"DATABASE_URL": database_url}) as client:
            # 1. ensure_project — first call creates, second call upserts (no duplicate)
            r1 = await client.call("ensure_project", {
                "project_id": TEST_PROJECT_ID, "name": "Archive Test Project",
                "input_config": {"ado_org": "test-org", "ado_project": "Test Project"},
            })
            assert r1["project_id"] == TEST_PROJECT_ID and r1["created"] is True
            r2 = await client.call("ensure_project", {
                "project_id": TEST_PROJECT_ID, "name": "Archive Test Project (renamed)",
                "input_config": {"ado_org": "test-org", "ado_project": "Test Project"},
            })
            assert r2["created"] is False
            print("  PASS  ensure_project creates once, upserts on repeat (no duplicate project)")

            # 2. list_available_inputs reflects stored input_config
            inputs = await client.call("list_available_inputs", {"project_id": TEST_PROJECT_ID})
            assert inputs["input_config"]["ado_org"] == "test-org"
            print("  PASS  list_available_inputs reflects the stored input_config")

            missing = await client.call("list_available_inputs", {"project_id": "no-such-project"})
            assert "error" in missing
            print("  PASS  list_available_inputs errors loudly for an unknown project_id")

            # 3. save_preference_profile upserts (same profile_id on repeat)
            p1 = await client.call("save_preference_profile", {
                "project_id": TEST_PROJECT_ID, "profile": {"tone": "concise"},
            })
            p2 = await client.call("save_preference_profile", {
                "project_id": TEST_PROJECT_ID, "profile": {"tone": "detailed"},
            })
            assert p1["profile_id"] == p2["profile_id"]
            print("  PASS  save_preference_profile upserts in place (stable profile_id, not duplicated)")

            # 4. No approved report yet -> get_prior_week_report is null
            prior = await client.call("get_prior_week_report", {"project_id": TEST_PROJECT_ID})
            assert prior is None
            print("  PASS  get_prior_week_report returns null before any report is approved")

            # 5. save_report_snapshot — full week's data, one transactional write
            report_v1 = {
                "week_of": "2026-08-02",
                "rag_status": "Amber",
                "executive_summary": "Steady progress with one at-risk item.",
                "curated_features": [{"ado_feature_id": 101, "display_text": "On track", "status_label": "On Track"}],
                "curated_initiatives": [{"title": "Vendor Contract Renewal", "display_text": "Wrapped up."}],
                "features": [
                    {"feature_id": 101, "title": "Build Agentic Dashboard", "short_description": "Dashboard work",
                     "status_label": "At Risk", "progress_summary": "Core screens done, demo pending.",
                     "risk": "Vendor API instability", "evidence": ["comment: vendor sandbox unstable"]},
                ],
                "initiatives": [
                    {"title": "Vendor Contract Renewal", "narrative_summary": "Paperwork wrapped up.",
                     "evidence": ["Wrapped up the vendor contract renewal paperwork this week."]},
                ],
            }
            saved = await client.call("save_report_snapshot", {"project_id": TEST_PROJECT_ID, "report": report_v1})
            report_id_v1 = saved["report_id"]
            print(f"  PASS  save_report_snapshot wrote report_id={report_id_v1}")

            # Still not approved -> still null
            prior = await client.call("get_prior_week_report", {"project_id": TEST_PROJECT_ID})
            assert prior is None
            print("  PASS  get_prior_week_report still returns null — saving does not imply approval")

            # 6. Simulate Review Gate approval directly (no approve tool exists yet — Review
            # Gate isn't built). This is test-only DB access, not something a real caller does.
            conn = await asyncpg.connect(database_url)
            try:
                await conn.execute(
                    "UPDATE weekly_reports SET pm_approved_at = now() WHERE report_id = $1", report_id_v1
                )
            finally:
                await conn.close()

            prior = await client.call("get_prior_week_report", {"project_id": TEST_PROJECT_ID})
            assert prior is not None
            assert prior["report_id"] == report_id_v1
            assert prior["rag_status"] == "Amber"
            assert len(prior["features"]) == 1 and prior["features"][0]["status_label"] == "At Risk"
            assert prior["features"][0]["evidence"] == ["comment: vendor sandbox unstable"]
            assert len(prior["initiatives"]) == 1
            assert "status_label" not in prior["initiatives"][0]
            print("  PASS  get_prior_week_report returns full data once approved — features, "
                  "initiatives, and evidence round-trip correctly; initiatives stay label-free")

            # 7. Re-save the SAME week (a rerun) — should upsert (same report_id), reset approval
            report_v2 = dict(report_v1)
            report_v2["rag_status"] = "Green"
            report_v2["features"] = [
                {"feature_id": 101, "title": "Build Agentic Dashboard", "short_description": "Dashboard work",
                 "status_label": "On Track", "progress_summary": "Demo delivered.", "risk": None, "evidence": []},
            ]
            resaved = await client.call("save_report_snapshot", {"project_id": TEST_PROJECT_ID, "report": report_v2})
            assert resaved["report_id"] == report_id_v1, "re-saving the same week must upsert, not create a new row"
            print("  PASS  re-saving the same (project_id, week_of) upserts the same report_id")

            prior = await client.call("get_prior_week_report", {"project_id": TEST_PROJECT_ID})
            assert prior is None, "pm_approved_at must reset to NULL when an approved week is re-saved"
            print("  PASS  pm_approved_at resets to NULL on re-save, as designed")

            # Re-approve and confirm the old feature row was replaced, not accumulated
            conn = await asyncpg.connect(database_url)
            try:
                await conn.execute(
                    "UPDATE weekly_reports SET pm_approved_at = now() WHERE report_id = $1", report_id_v1
                )
            finally:
                await conn.close()
            prior = await client.call("get_prior_week_report", {"project_id": TEST_PROJECT_ID})
            assert prior["rag_status"] == "Green"
            assert len(prior["features"]) == 1 and prior["features"][0]["status_label"] == "On Track"
            print("  PASS  feature_snapshots were replaced wholesale on re-save (no duplicate/stale rows)")

    finally:
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute("DELETE FROM projects WHERE project_id = $1", TEST_PROJECT_ID)
        finally:
            await conn.close()
        print(f"\nTest data cleaned up (project_id='{TEST_PROJECT_ID}' deleted, cascades to children).")

    print("\nPASS  live Archive checks completed against a real Postgres connection.")


async def main():
    print("Archive MCP Server — test suite\n")
    run_structural_checks()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("\nDATABASE_URL not set — skipping live checks.")
        print("Structural checks passed.")
        return

    await run_live_checks(database_url)


if __name__ == "__main__":
    asyncio.run(main())
