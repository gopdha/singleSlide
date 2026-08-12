# Slide Generation Agent

Two genuinely different modes, not one component. Full design reasoning, including the
pptx-Skill investigation and why it came out negative: `docs/DECISION_LOG.md` ("Why
Requirement 17's pptx Skill is superseded" and "Slide Generation Agent — layout
archetypes...").

## Mode 1 — `run_slide_generation_discovery` (once per project, at onboarding)

One agentic call proposes 3 design **PARAMETER** sets (palette/fonts/flex_bounds) — never
raw `.pptx` manipulation. Each is rendered, deterministically, into one of 3 fixed layout
archetypes already implemented in `slide_generation_agent.py`:

- **`single_column_narrative`** — a single full-width column, vertically stacked narrative rows
- **`two_column_metrics_sidebar`** — a left status/metrics sidebar + a right content column
- **`banner_header_grid`** — a full-width colored banner header + tabular grid content

The PM picks one (or rejects all 3 for a fresh attempt) via `ask_human` — the same custom
callable pattern as `discovery_agent`, same reasoning: `AskUserQuestion` is technically
reachable from `claude_agent_sdk.query()` in this environment but unverified when the SDK
runs detached from an interactive session actually watching for it (see CLAUDE.md gotcha
#13). The choice locks `skills/<project_id>/slide-generation-agent/SKILL.md`.

Candidates render against either a real report dict (pass `sample_report=`) or a built-in
synthetic fixture (deliberately varied: one of each of the 4 status labels, a long
`display_text` near the truncation ceiling, a populated initiatives list) — so the PM is
judging real overflow/truncation behavior, not just short placeholder text.

## Mode 2 — `render_report` (every week after)

Fully deterministic. **Zero LLM calls, zero MCP client** — a pure function of
`(report, design)`, same testability tier as `core/rag_rollup.py`. Loads the locked skill,
renders the 3 report slides (Executive Summary, Feature Status, Initiative Status) into
the locked archetype, auto-fitting within the skill's `flex_bounds`:

1. Try the skill's default font size / row spacing / text length.
2. Still overflowing → shrink font size toward `font_size_pt_min`.
3. Still overflowing → shrink row spacing toward `row_height_in_min`.
4. Still overflowing → truncate `display_text` toward `display_text_max_chars_min`.
5. **Still overflowing after all 3 floors are maxed out → raises `SlideFitError`**,
   never silently drops a row or over-truncates further.

This exact lever order matches CLAUDE.md Requirement 15's own listed order (font size, row
height, truncation) — fixed code, not skill-negotiable; only the bound *values* vary per
project's locked template.

### What "escalate to the PM" means today

`review_gate/` doesn't exist yet and nothing in `core/orchestrator.py` calls this agent
yet, so `SlideFitError` simply propagates to the caller — the same way
`critique_agent`'s risk-floor `RuntimeError` already does. No `review_gate` interface was
invented here to catch it prematurely.

## Why no pptx Skill

Investigated before writing any code here, the same way `AskUserQuestion` was investigated
for Discovery Agent. Short version: it doesn't exist in this environment — no `Skill` tool
in `claude_agent_sdk`'s own generated tool schema, and a full search of every
plugin/user/project skill location on the development machine found none. Full writeup:
`docs/DECISION_LOG.md`. python-pptx renders instead — already a dependency
(`mcp_servers/ppt_mcp` uses it to *parse* `.pptx`; this module uses it to *write* one).

## Known limitation: the fit heuristic is approximate, not exact

python-pptx has no real text-layout engine — there's no way to ask it "how many lines will
this text wrap to at this font size in this box" and get PowerPoint's actual answer.
`_estimate_block_height_in` is a deterministic APPROXIMATION (a fixed average-character-
width formula: ~0.5 × font size per glyph), not exact rendering measurement. It's
reproducible — the same content always gets the same fit decision on every run — but not
pixel-exact. Documented rather than hidden.

## What's verified here vs. what needs a real conversation

**Mode 2 (`render_report`) is fully unit-tested** — no credentials, no LLM, no MCP: all 3
archetypes render real non-empty `.pptx` files, the missing-skill `FileNotFoundError`, the
`SlideFitError` overflow case (100 features with long `display_text`), and the
empty-features/empty-initiatives case all pass every run.

**Mode 1 (`run_slide_generation_discovery`)** gets pure unit tests (the fit heuristic,
design-derived helpers, `default_ask_human`'s input validation) plus a scripted-
conversation integration tier — the one agentic call (`_generate_candidates`) mocked,
`write_skill`/`load_skill` left real against a temp `skills_root` — covering the happy
path, the regenerate loop, the cancel path, a candidate that fails to render (dropped, not
fatal), and every candidate failing to render (offers regenerate-or-cancel).

**Genuine tier 3 is deliberately not automated**: actually opening the 3 rendered `.pptx`
candidates and judging them as a PM would is the real acceptance test here. Run it
yourself:
```bash
cd agents/slide_generation_agent
python3 slide_generation_agent.py discover <project_id> [--sample-report-json PATH] [--output-dir PATH] [--skills-root PATH] [--debug]
```
And once a skill is locked, render a real finalized report (e.g. from
`core/orchestrator.py`'s `run_pipeline()` output, saved to JSON):
```bash
python3 slide_generation_agent.py render <project_id> <report_json_path> [--output PATH] [--skills-root PATH] [--debug]
```

## Setup
```bash
cd agents/slide_generation_agent
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```

## Run the tests
```bash
python3 test_slide_generation_agent.py   # no credentials needed at all
```

## Known benign warning
Same asyncio subprocess cleanup-order artifact noted in every other agent's README
(`Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is closed`) may
appear after tests complete successfully — only Mode 1's one agentic call touches this
path; Mode 2 has no async machinery at all.
