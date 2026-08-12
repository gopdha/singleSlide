# Archive MCP Server

Persistence for SingleSlide, over Postgres (Neon-compatible). Designed fresh for the
current pipeline — not a port of anything that existed before this repo. Full schema
and tool-signature reasoning: `docs/DECISION_LOG.md` ("Archive schema design
decisions" and "Archive schema — additional confirmed design choices").

## Schema

```
projects (project_id PK, caller-supplied)
   │
   ├── 1:1 ── preference_profiles (project_id UNIQUE FK)
   │
   └── 1:N ── weekly_reports (project_id FK, UNIQUE(project_id, week_of))
                  │
                  ├── 1:N ── feature_snapshots (report_id FK, UNIQUE(report_id, ado_feature_id))
                  │
                  └── 1:N ── initiative_snapshots (report_id FK)
```

Full DDL in `schema.sql`. Five things worth knowing before touching this schema:

- **`weekly_reports.trend_line`** (added post-launch, via `core/orchestrator.py`'s build —
  see `docs/DECISION_LOG.md`) holds Synthesis Part C's short continuity callout vs. the
  prior week. `NOT NULL DEFAULT ''` — empty string, not null, when there was no prior
  week to compare against. `schema.sql` has both the `CREATE TABLE` column and a
  standalone idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, since the table
  already existed in deployed databases before this column did.
- **`weekly_reports.review_notes`** (added post-launch, via `review_gate/`'s build — see
  `docs/DECISION_LOG.md`) holds the PM's free-text Review Gate notes, written by
  `approve_report` on both approve and reject. `NOT NULL DEFAULT ''`, same idempotent
  `CREATE TABLE` column + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern as
  `trend_line`. This is Backlog item 2's "PM correction feedback loop" resolved
  narrowly — free-text notes only, not a structured `pm_edits` diff (still deferred).
- **`feature_snapshots`/`initiative_snapshots` vs. `curated_features`/`curated_initiatives`
  are deliberately different things.** The snapshot tables hold every Feature/Initiative
  investigated that week, full detail — what `get_prior_week_report` needs for continuity.
  `curated_*` (on `weekly_reports`) is the final, ordered, possibly flex-bound-condensed
  subset that actually rendered on the slide. Don't collapse them.
- **No `template_id` foreign key anywhere.** Slide templates are Skills (Requirement 17)
  — the locked template lives as a `SKILL.md` file under
  `skills/<project_id>/slide-generation-agent/`, looked up by `project_id` via
  `skill_loader.py`, same as every other skill. Not report-instance data.
- **`initiative_snapshots` has no `status_label` column, period** — not nullable, not
  unused, structurally absent. Other Initiatives are narrative-only by design (see
  `status_report_agent`'s own schema and its test suite for the same enforcement one
  layer up).

## What's skill-defined vs. code-enforced

Nothing here is skill-defined — Archive is pure persistence with a fixed schema and
fixed tool contracts. The skill/code boundary that applies to Feature Agent and Status
Report Agent doesn't apply here; there's no per-project investigation strategy to vary.

## The 7 tools

```
ensure_project(project_id, name, input_config) -> {project_id, created}
get_prior_week_report(project_id) -> full prior APPROVED week (features + initiatives), or null
save_report_snapshot(project_id, report) -> {report_id}   # one transactional write
get_latest_unreviewed_report(project_id) -> latest report pending Review Gate, or null
approve_report(report_id, approved, notes="") -> {report_id, pm_approved_at, review_notes}
save_preference_profile(project_id, profile) -> {profile_id}
list_available_inputs(project_id) -> {project_id, input_config}
```

`get_latest_unreviewed_report` and `approve_report` exist for `review_gate/` (added when
that component was built — see `docs/DECISION_LOG.md`). `get_latest_unreviewed_report` is
deliberately leaner than `get_prior_week_report` — no `feature_snapshots`/
`initiative_snapshots` join — since `render_report()` never reads those fields.
`approve_report` is the only tool that can set `pm_approved_at`; `save_report_snapshot`
can only ever *reset* it to `NULL`, never grant approval.

Each has a plain async `_impl` function (importable directly, no MCP protocol needed)
plus a thin `@mcp.tool()`-decorated wrapper that catches exceptions and returns
`{"error": str(exc)}` instead of letting them raise through MCP — same split as
`mcp_servers/ppt_mcp/server.py`'s `parse_slide_file()`/`parse_slide()`.

## Setup
```bash
cd archive
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```

## Apply the schema
```bash
DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require" python3 migrate.py
```
Safe to re-run — every statement is `CREATE TABLE IF NOT EXISTS`.

## Run the tests
```bash
# Structural only (no DB):
python3 test_archive.py

# Full live run against a real Postgres (local or Neon):
DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require" python3 test_archive.py
```
Unlike Feature Agent and Status Report Agent, Archive's tier 2 needs a real Postgres
connection, not an Anthropic API key — there's no LLM involved anywhere in this
component, it's pure deterministic persistence. Tier 2 spins up `server.py` as a real
subprocess and calls each tool over the actual MCP protocol via
`common/mcp_client.py` (not by importing the `_impl` functions directly) — the same
gotcha #9/#10 class of bug (an MCP server that's subtly broken at the wiring level,
not the logic level) is exactly what a full protocol round-trip catches and a direct
function-call test wouldn't.

## Known benign warning
Same asyncio subprocess cleanup-order artifact noted in `feature_agent`'s README
(`Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is closed`)
may appear after tests complete successfully.

## Usage
```python
from common.mcp_client import open_mcp_client

async with open_mcp_client(command=sys.executable, args=["archive/server.py"],
                            env={"DATABASE_URL": "postgresql://..."}) as client:
    result = await client.call("ensure_project", {
        "project_id": "ai-reports-demo", "name": "AI Reports Demo",
        "input_config": {"ado_org": "gopdha", "ado_project": "AI Reports Demo"},
    })
```
