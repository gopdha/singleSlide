# Synthesis Agent (three parts, skill-driven)

Turns a week's investigated Features, flagged enrichments, and raw (possibly duplicated
across team leads) Other Initiatives into the finalized Feature Status, Initiative
Status, and Executive Summary content. Full reasoning for the three-way split, the
Needs-Human-Review risk-floor extension, and `trend_line`'s deferred storage:
`docs/DECISION_LOG.md` ("Synthesis Agent — three-way split...").

## The three parts

| Part | Function | LLM? | Tools? |
|---|---|---|---|
| A | `merge_feature_enrichments(features, enrichments)` | No — pure, deterministic | — |
| B | `curate_report(features, initiatives, rag_rollup_result, prior_week, ...)` | Yes, one call | Zero — all data passed in |
| C | `write_executive_summary(curated_features, curated_initiatives, rag_rollup_result, prior_week, ...)` | Yes, one call | Zero |

`synthesize_report(...)` ties all three together, fetching Archive's `prior_week`
exactly once (before Part B) and passing it to both B and C — never re-fetched.

## Part A — why it's separate from Part B

Merging Status Report Agent's `potential_enrichments` onto a Feature's `evidence`/`risk`
is genuinely reproducible: a `difflib.SequenceMatcher` overlap check against the same
inputs always gives the same output. Keeping it out of the agentic curation step means
the evidence-merge trail stays fully auditable even though curation (Part B) and
prose-writing (Part C) don't. Rules, precisely:

- Matches a Feature only by `related_feature_id` (never `related_feature_title_guess`
  — that fuzzy matching already happened once, inside `status_report_agent`).
- Only `match_confidence == "high"` qualifies.
- Overlap is checked against a **raw, unprefixed** text pool that grows as the call
  proceeds — so two team leads submitting near-duplicate enrichments for the same
  Feature don't both get merged, only the first. (Checking against the final,
  `"[Status report] "`-prefixed evidence list would dilute the similarity ratio enough
  to weaken this — caught by a test, fixed before shipping.)
- Qualifying enrichments always append to `evidence`; only fill `risk` if it's
  currently `None`, and only with the enrichment's raw `excerpt` — verbatim, never
  summarized (that would be judgment, contradicting Part A being non-agentic).

## Part B — the risk floor, enforced in code

`curate_report` does two jobs in one call because both need the same full context
(the complete Feature/Initiative list, plus `prior_week` for continuity judgment):
semantic dedup of Other Initiatives across every team lead's report, and
continuity-aware overflow curation for slides 2/3.

**After the call returns, code — not the prompt — enforces Requirement 12's floor,
extended to `Needs Human Review`:**
```python
RISK_FLOOR_LABELS = {"Blocked", "At Risk", "Needs Human Review"}
```
Every Feature carrying one of these three labels must appear in `curated_features`, or
`curate_report` raises `RuntimeError` — same loud-failure posture as `rag_rollup`'s
`ValueError`. Only `On Track` Features may be omitted or condensed for overflow.
Initiatives have no floor: `curated_initiatives` may trim anything from
`deduped_initiatives`, which is itself archived in full regardless.

## Part C — pure prose, no new judgment

Writes `executive_summary` and `trend_line` from Part B's **already-validated** output
only — no `features`/`initiatives` raw data, no re-fetching `prior_week`. `trend_line`
is a short continuity callout (e.g. "Improved from Amber to Green since last week"),
empty string when `prior_week` is null. Not archived yet — see the Decision Log entry;
storage is deferred to `core/orchestrator.py`'s build.

## A known naming inconsistency, worked around here

`archive/server.py`'s `get_prior_week_report` returns Features keyed `ado_feature_id`;
everywhere else in this pipeline uses `feature_id`. `synthesize_report` normalizes this
once, immediately after fetching `prior_week`, before it reaches Parts B or C — not
fixed at the source (`archive/` is already shipped and live-verified). Logged as
`docs/BACKLOG.md` item 9. If you ever consume `prior_week` directly from Archive without
going through `synthesize_report`, you'll hit the raw `ado_feature_id` key.

## What's skill-defined vs. code-enforced

Minimal skill, as expected for cross-cutting logic rather than project-specific
investigation strategy: `skills/<project_id>/synthesis-agent/SKILL.md` carries only
tone/curation-priority prose for Parts B and C's system prompts — no frontmatter fields
parsed by code (unlike `feature-agent`'s `entry_criteria`).

| Code-enforced (never varies) | Skill-defined |
|---|---|
| The risk floor (`RISK_FLOOR_LABELS`, validated after every `curate_report` call) | Curation priorities when trimming On Track Features |
| Part A's merge/overlap rules | Executive Summary tone and phrasing conventions |
| Output schemas for Parts B and C | Continuity-narration style (Part C) |

## What's verified here vs. what needs your machine
Part A: comprehensive pure unit tests, always run, no credentials — including a
regression test for the prefix-dilution bug found during this build. Structural checks
(schema shape, the extended risk-floor set, skill loading) also always run. Parts B/C
need a real `ANTHROPIC_API_KEY` for request-construction validation and the live run;
the full `synthesize_report` path additionally needs a real `DATABASE_URL` (Archive) —
Parts B/C alone don't, since `prior_week` is just a plain argument to them.

## Setup
```bash
cd agents/synthesis_agent
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```

## Run the tests
```bash
# Part A + structural checks only:
python3 test_synthesis_agent.py

# + request construction validation:
export ANTHROPIC_API_KEY="sk-ant-..."
python3 test_synthesis_agent.py

# + live Part B/C run (no DB needed):
export ANTHROPIC_API_KEY="sk-ant-..."
python3 test_synthesis_agent.py

# + full live synthesize_report path (needs Archive too):
export ANTHROPIC_API_KEY="sk-ant-..."
export DATABASE_URL="postgresql://user:pass@host/dbname?sslmode=require"
python3 test_synthesis_agent.py
```

## Known benign warning
Same asyncio subprocess cleanup-order artifact noted in every other agent's README
(`Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is closed`) may
appear after tests complete successfully.

## Usage
```python
from synthesis_agent import synthesize_report

report = await synthesize_report(
    project_id="ai-reports-demo", week_of="2026-08-16",
    features=merged_or_raw_features, enrichments=all_potential_enrichments,
    initiatives=all_raw_other_initiatives, database_url="postgresql://...",
)
# report has: project_id, week_of, rag_status, executive_summary, trend_line,
# curated_features, curated_initiatives, features (full, Part-A-merged),
# initiatives (full deduped list). Not yet saved to Archive — that's
# core/orchestrator.py's job, after Critique Agent's revision loop.
```
