# Feature Agent (skill-driven)

Pipeline A. Investigates every ADO work item matching a project's
skill-defined entry criteria and produces an executive-level status update
per item, grounded in cited evidence.

## What's skill-defined vs. code-enforced

| Skill-defined (`skills/<project_id>/feature-agent/SKILL.md`) | Code-enforced (never varies) |
|---|---|
| Entry criteria (Tag, State, PI field, or anything else) | 4-turn investigation budget |
| Hierarchy (Feature→Story, Epic→Feature→Story, Bug-linked, etc.) | Prompt injection defense |
| Field name mappings (e.g. non-standard Story Points field) | Output schema |
| Project-specific quirks/heuristics (skill body, read by the agent) | Status taxonomy: On Track / At Risk / Blocked / Needs Human Review |

This split exists because the RAG rollup and Synthesis Agent downstream
depend on a fixed, known label set and cost/time guarantees — those can't
be project-negotiable, or the whole pipeline's guarantees break. Everything
about *how* to investigate a given project's specific ADO structure can be.

## Status taxonomy
Four levels, not three — `Needs Human Review` was added deliberately so the
agent can honestly say "the evidence was genuinely ambiguous" instead of
being forced to guess between the other three. It does **not** participate
in the deterministic RAG rollup (see `core/rag_rollup.py`, not yet built) —
it's surfaced separately at Review Gate.

## Skill format
See `skills/ai-reports-demo/feature-agent/SKILL.md` for a real example.
YAML frontmatter for what code needs to parse (`entry_criteria`,
`hierarchy`, `fields`); markdown body for what the agent reads as
project-specific investigation notes.

## What's verified here vs. what needs your machine
Same pattern as every other agentic component in this project — no
Anthropic API key or `dev.azure.com` access exists in this sandbox.
Verified here: structural checks, skill loading (including the loud
failure when a project hasn't been onboarded), the WIQL builder, and
request construction (validated against the real Anthropic API with a
placeholder key — correctly rejected only for invalid auth).

A full live run needs your real API key + real ADO org/PAT.

## Setup
```bash
cd agents/feature_agent
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```

## Run the tests
```bash
# Structural + skill loading only:
python3 test_feature_agent.py

# + request construction validation:
export ANTHROPIC_API_KEY="sk-ant-..."
python3 test_feature_agent.py

# Full live run:
export ANTHROPIC_API_KEY="sk-ant-..."
export ADO_ORG="gopdha"
export ADO_PROJECT="AI Reports Demo"
export ADO_PAT_BASE64="<base64 value from mcp_servers/ado_mcp/encode-pat.js>"
python3 test_feature_agent.py
```

## Known benign warning
An `Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is
closed` message may appear after tests complete successfully — an asyncio
subprocess cleanup-order artifact, doesn't affect correctness or exit code.

## Usage
```python
from feature_agent import investigate_all_committed_features

results = await investigate_all_committed_features(
    org="gopdha", project="AI Reports Demo", pat_base64="...",
    project_id="ai-reports-demo",
)
for r in results:
    print(r["title"], "->", r["status_label"])
```

## Before this works for a new project
The Discovery Agent (not yet built) will generate the skill automatically.
Until then, hand-author `skills/<project_id>/feature-agent/SKILL.md`
following the example — `load_skill()` fails loudly if it's missing,
rather than silently guessing.
