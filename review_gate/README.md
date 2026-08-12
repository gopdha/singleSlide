# Review Gate

Requirement 18's mandatory human approval step: a human sees the **actual rendered
slide** (not raw JSON/text) and must approve or reject with notes before a report counts
as final. The last component in the pipeline, and deliberately the smallest — almost no
new logic of its own, mostly integration of things that already work. Full design
reasoning (the traced signatures, the archive tool decisions, the SlideFitError routing):
`docs/DECISION_LOG.md`.

## What this is NOT

**Not a placeholder for a future GUI/web app.** CLI is the intentional final form here —
same reasoning as `discovery_agent`'s and `slide_generation_agent`'s custom `ask_human`
callable: `AskUserQuestion` is technically reachable from `claude_agent_sdk.query()` in
this environment but unverified when the SDK runs detached from an interactive session
(CLAUDE.md gotcha #13). Not that it matters here anyway — this component makes no LLM
calls at all (see below).

**Not inline slide editing.** "Edit" (Requirement 18) means the PM's free-text notes are
captured and attached to the record — via `approve_report`'s `review_notes` column — not
that a PM can modify the rendered deck's content through this tool. Out of scope,
explicitly.

## Two call shapes

```python
# In-process chaining — right after core/orchestrator.py's run_pipeline():
result = await run_pipeline(...)
await run_review_gate(project_id, database_url, report=result["report"], report_id=result["report_id"])

# Standalone — a PM running this on its own, independent of when the pipeline ran:
await run_review_gate(project_id, database_url)
```
`report`/`report_id` must be given together or neither. Standalone mode fetches the
latest pending report via Archive's new `get_latest_unreviewed_report` tool, raising
loudly if nothing is pending — never silently no-ops.

## What's actually new here vs. integrated

**Zero new business logic that matters — this is the point.** `render_report()`
(`agents/slide_generation_agent`, Mode 2, fully deterministic) does the actual rendering;
this module just calls it. Two genuinely new pieces, both in `archive/`:

- **`approve_report(report_id, approved, notes="")`** — the only tool that can *set*
  `pm_approved_at`. `save_report_snapshot` can only ever *reset* it to `NULL` (confirmed
  by reading its SQL directly before writing any of this) — there was no reuse path.
- **`get_latest_unreviewed_report(project_id)`** — needed for the standalone call shape.
  Deliberately leaner than `get_prior_week_report` (no `feature_snapshots`/
  `initiative_snapshots` join), since `render_report()` never reads those fields.

Plus a new `weekly_reports.review_notes TEXT NOT NULL DEFAULT ''` column — Backlog item
2's "PM correction feedback loop" resolved narrowly (free-text notes only, not a
structured `pm_edits` diff, which stays deferred) now that this component is the real
consumer, not speculative scope.

## Why no shape translation was needed

Traced directly, not assumed: `core/orchestrator.py`'s `run_pipeline()` return dict nests
`synthesize_report()`'s complete output under `result["report"]`. `render_report()` reads
exactly `rag_status`, `executive_summary`, `trend_line` (optional), `curated_features`,
`curated_initiatives`, `week_of` (optional, filename only) — every field `run_pipeline()`
already provides. Unlike the `feature_id`/`id` mismatch caught earlier in this build
(between `feature_agent` and `status_report_agent`), this integration point needed no
adapter function at all.

## `SlideFitError` routes through the exact same path as a human rejection

`render_report()` can raise `SlideFitError` (Requirement 16's escalation — content didn't
fit even at the tightest flex bounds). `run_review_gate` catches it and calls
`approve_report(report_id, approved=False, notes=<the error>)` — the identical call a
real human rejection makes, not a separate mechanism. A report that can't even render
can't be shown to a human to judge, so "can't approve, here's why" is the honest
translation. The PM never even sees an approve/reject question in this case; it's
resolved before `ask_human` is ever called.

## What's verified here vs. what needs a real conversation

Pure unit tests (the report/report_id pairing validation, `default_ask_human`'s input
validation) and a scripted-conversation integration tier (both archive calls and
`render_report` mocked — approve path, reject-requires-notes loop, the `SlideFitError`
auto-reject routing, the standalone-fetch path, the nothing-pending path) run every time,
no credentials needed.

**Genuine tier 3 is deliberately not automated** — it needs a real human decision on a
real rendered deck, not just credentials. Run it yourself, e.g. right after a live
`core/orchestrator.py` run for `project_id="singleslide"` (the first project with both a
real report and a locked template):
```bash
cd review_gate
python3 review_gate.py singleslide "postgresql://user:pass@host/dbname?sslmode=require" [--output-dir PATH] [--skills-root PATH] [--debug]
```

## Setup
```bash
cd review_gate
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```
No `claude-agent-sdk` — a genuine, real difference from every other agent in this repo:
`render_report()` (Mode 2) makes zero LLM calls, so nothing here needs it either.

## Run the tests
```bash
python3 test_review_gate.py   # no credentials needed at all
```

## Known benign warning
Same asyncio subprocess cleanup-order artifact noted in every other agent's README
(`Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is closed`) may
appear after tests complete successfully — from the Archive MCP subprocess, not an LLM
call (there isn't one here).
