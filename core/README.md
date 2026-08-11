# core/

`rag_rollup.py` — deterministic RAG rollup, zero dependencies (stdlib only). See its own
module docstring and `docs/DECISION_LOG.md` ("core/rag_rollup.py — the 'Unknown' status...").

## `orchestrator.py`

The first component that wires everything into one real end-to-end pipeline run:
Feature Agent → Status Report Agent → Synthesis Agent → Critique Agent (bounded revision
loop) → Archive. Coordination only, per `CLAUDE.md`'s core architectural principle — it
makes zero content decisions; every judgment call belongs to the component that owns it.

Every call in `run_pipeline` was wired against each component's actual current source,
not assumed — two real integration issues surfaced doing that:

- **`status_report_agent`'s `existing_features` param expects `{"id":..., "title":...}`**,
  the shape `feature_agent`'s own deterministic listing step produces — NOT
  `investigate_all_committed_features()`'s final output, which uses `feature_id` per
  `FEATURE_SCHEMA`. `_existing_features_for_status_report_agent` translates this;
  passing Feature Agent's output straight through would `KeyError` inside Status
  Report Agent.
- **`ensure_project` must run before `save_report_snapshot`** — `weekly_reports.project_id`
  is a foreign key. Runs as step 0, before any billed API calls, so a DB connectivity
  problem fails fast rather than after a full (expensive) pipeline run.

### The revision loop

`MAX_REVISIONS = 1` — one initial Synthesis+Critique pass, at most one revision (2 total
cycles), matching `docs/DECISION_LOG.md`'s cost estimate, which already assumed "2
critique cycles." On a failed critique, the full list of failed `checks` is passed as
`revision_feedback` to `synthesize_report` (threaded to both Part B and Part C — a
failed check can be curation-shaped or prose-shaped, and it's cheaper to let each part
ignore what's irrelevant than to classify which check belongs to which part).

**At the cap, the outcome depends on which check is still failing:**
- Still failing on `risk_floor` → **hard stop, `RuntimeError`, `save_report_snapshot` is
  never called.** `curate_report` already validates the floor on every call (including
  revisions) and raises before returning a violating report — so `critique_report`
  independently re-checking and still failing means the two implementations disagree,
  which is a real bug, not content-quality variance. The report's trustworthiness is
  unknown; it must never be persisted in that state. See `docs/DECISION_LOG.md` ("a
  code-enforced check failing after independent re-verification is a bug, not a content
  judgment call").
- Still failing only on `grounding_coverage` and/or skill-defined checks (tone,
  conciseness, `trend_line`, etc.) → **proceeds.** The report is saved, `reviewed: False`
  in the return value, full critique verdict attached. Requirement 18's mandatory human
  Review Gate is the real safety net here — a report that never fully passed critique
  should still reach a human, flagged, not vanish.

### Return shape

`run_pipeline`'s `report` key is `synthesize_report()`'s **complete** output, nested
whole — `features`, `initiatives`, `prior_week` included, not a trimmed summary. Review
Gate (not yet built) needs the full picture.

## Setup
```bash
pip install -r core/requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```
Only `orchestrator.py` needs these (transitively, via the 4 agent modules it imports) —
`rag_rollup.py` needs nothing beyond the standard library.

## Run the tests
```bash
# Structural + mocked revision-loop control-flow tests (no credentials):
python3 core/test_orchestrator.py
python3 core/test_rag_rollup.py
```
A genuine full `run_pipeline` live run needs real `ADO_ORG`/`ADO_PROJECT`/
`ADO_PAT_BASE64` + `ANTHROPIC_API_KEY` + `DATABASE_URL` + a real reports directory — same
tier-3 pattern as `feature_agent`'s own live run, run by the project owner, not in CI.
