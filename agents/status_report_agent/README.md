# Status Report Agent (skill-driven)

Pipeline B. Reads every team lead's submitted weekly status report (via
`ppt_mcp`'s `parse_slide()`) and produces two things per report: narrative
**Other Initiatives** (work with no matching ADO Feature) and flagged
**potential enrichments** (content that plausibly relates to an existing
Feature — a candidate for Synthesis Agent to merge, not a merge already
made here).

## What's skill-defined vs. code-enforced

| Skill-defined (`skills/<project_id>/status-report-agent/SKILL.md`) | Code-enforced (never varies) |
|---|---|
| Submitted-report file naming convention (`report_file_glob`) | Tool-call budget |
| Report-parsing quirks (section phrasing variance, initiative naming habits, matching caveats — skill body, read by the agent) | Prompt injection defense |
| | Output schema |
| | Other Initiatives are narrative-only — no status label, ever |
| | This agent only flags enrichment candidates; it never merges them |

This split mirrors Feature Agent's: the RAG rollup and Synthesis Agent
downstream depend on fixed contracts (label-free Other Initiatives,
enrichment-as-candidate-not-decision) that can't be project-negotiable.
Everything about *how* to read a given project's report conventions can be.

## Two scope boundaries worth understanding before touching this code

**Enrichment vs. merging.** This agent flags that a report mentions
something relating to an existing Feature — it does **not** decide whether
that content duplicates what ADO's own comments already say. It has no
visibility into Feature Agent's investigation findings (only a bare
id/title list of existing Features is passed in), so it's structurally
incapable of making that call correctly. The actual merge — only if ADO's
own comments don't already say it — happens in Synthesis Agent, the only
component with full cross-source visibility. See `docs/DECISION_LOG.md`.

**`color_cues` are supplementary, not authoritative.** `parse_slide()`
returns RGB-classified shape fills as an independent signal. This agent may
note a plain-language `color_signals` entry when a color cue plausibly
aligns with an item, but never uses color to assign a status label (Other
Initiatives don't have one) or to decide an enrichment's relevance. It's
context for the human reviewer and for Synthesis, not a conclusion drawn on
their behalf.

## Skill format
See `skills/ai-reports-demo/status-report-agent/SKILL.md` for a real
example. YAML frontmatter for what code needs to parse (`report_file_glob`);
markdown body for what the agent reads as project-specific report-reading
notes.

## What's verified here vs. what needs your machine
Same tiered pattern as Feature Agent — no Anthropic API key exists in this
sandbox, and no directory of real submitted reports either. Verified here:
structural checks, skill loading (including the loud failure when a project
hasn't been onboarded), the deterministic file listing, and request
construction (validated against the real Anthropic API with a placeholder
key and a real minimal `.pptx` fixture — correctly rejected only for
invalid auth, proving `parse_slide` wiring and schema construction are both
correct).

A full live run needs your real API key + a directory of real submitted
`.pptx` reports (and, optionally, real ADO credentials so enrichment
matching has something to match against — see `feature_agent`).

## Setup
```bash
cd agents/status_report_agent
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac

# ppt_mcp is spawned as a subprocess — its own deps must be installed too:
pip install -r ../../mcp_servers/ppt_mcp/requirements.txt --break-system-packages
```

## Run the tests
```bash
# Structural + skill loading only:
python3 test_status_report_agent.py

# + request construction validation:
export ANTHROPIC_API_KEY="sk-ant-..."
python3 test_status_report_agent.py

# Full live run:
export ANTHROPIC_API_KEY="sk-ant-..."
export STATUS_REPORTS_DIR="/path/to/this/weeks/submitted/reports"
# optional — without these, everything lands as an Other Initiative or a low-confidence guess:
export ADO_ORG="gopdha"
export ADO_PROJECT="AI Reports Demo"
export ADO_PAT_BASE64="<base64 value from mcp_servers/ado_mcp/encode-pat.js>"
python3 test_status_report_agent.py
```

## Known benign warning
An `Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is
closed` message may appear after tests complete successfully — same
asyncio subprocess cleanup-order artifact noted in `feature_agent`'s
README, harmless.

## Usage
```python
from status_report_agent import investigate_all_status_reports

# existing_features: [{"id": ..., "title": ...}, ...] — typically Feature Agent's
# list_committed_features() output, passed in by the Orchestrator.
results = await investigate_all_status_reports(
    reports_dir="/path/to/this/weeks/reports",
    existing_features=existing_features,
    project_id="ai-reports-demo",
)
for r in results:
    print(r["team_lead_id"], "->", len(r["other_initiatives"]), "initiative(s),",
          len(r["potential_enrichments"]), "enrichment candidate(s)")
```

## Before this works for a new project
The Discovery Agent (not yet built) will generate the skill automatically.
Until then, hand-author `skills/<project_id>/status-report-agent/SKILL.md`
following the example — `load_skill()` fails loudly if it's missing, rather
than silently guessing.
