# SingleSlide — Project Context

**Read this file fully before making changes.** This project went through
extensive design iteration before any code was written; the reasoning behind
decisions matters as much as the decisions themselves — several early
approaches were deliberately abandoned, and re-proposing them wastes time.
Deeper reasoning lives in `docs/DECISION_LOG.md` and `docs/BACKLOG.md`;
this file is the load-bearing summary.

## What this is
An AI-generated weekly executive leadership report: **3 output slides**
(Executive Summary, Feature Status, Initiative Status), built from **2 input
sources** (Azure DevOps + team lead Weekly Status Reports). Personal
portfolio/showcase project. Owner is learning Python — code should be clean
and idiomatic, not just functional, since it doubles as a learning resource.

## Requirements (current, authoritative — supersedes anything in old docs/)
1. Two input sources only: ADO + Weekly Status Reports. No Excel — dropped
   deliberately (see Decision Log).
2. Retrieval is dynamic: query what's actually reportable in ADO this week
   and whatever status reports were submitted — never assume a fixed pull.
3. Output is 3 slides: Executive Summary, Feature Status, Initiative Status.
4. **Feature Agent** investigates every ADO item matching a project's
   skill-defined entry criteria (originally scoped as "Committed"-tagged
   Features; PI concept explicitly dropped — "any Committed item needs to
   be reported," no PI filtering).
5. Status taxonomy: **On Track / At Risk / Blocked / Needs Human Review**
   (4 levels — the 4th was added deliberately so the agent can honestly say
   "evidence was ambiguous" instead of being forced to guess).
6. Every status must cite evidence — a specific comment, date slip, or
   story-point count. Never a generic justification.
7. **Status Report Agent** identifies Other Initiatives — work mentioned in
   team lead reports with no corresponding ADO Feature — narrative-only,
   **no status label** (not risk-bearing, doesn't participate in rollup).
8. Cross-source enrichment: if a status report mentions a risk on an
   existing Feature, merge it into that Feature's update only if ADO's own
   comments don't already say it (avoid redundant text).
9. Multiple team leads submit reports (fan-out/fan-in across all of them).
   Overlapping Other Initiatives across different leads must be
   semantically deduped/merged — this happens in **Synthesis Agent**
   (it's the only component with full cross-report visibility).
10. RAG rollup is a **deterministic pure function**, fed by Feature status
    labels only: any Blocked → Red, any At Risk → Amber, else Green.
    `Needs Human Review` is explicitly **excluded** from rollup — surfaced
    separately at Review Gate, never forces Amber.
11. Synthesis Agent writes the Executive Summary and curates overflow when
    too many items exist for a slide, referencing the prior week's report
    (via Archive) for continuity.
12. **Hard rule, not agent-negotiable**: Blocked and At Risk items can
    never be trimmed from overflow — only On Track items may be condensed.
13. Critique Agent runs a bounded revision loop (evaluator-optimizer
    pattern) against a rubric: grounding, conciseness, tone, and the
    risk-floor rule specifically.
14. First-run: 3 slide template candidates generated, PM picks one — this
    is the one-time human judgment call on visual/executive quality.
    Nothing re-judges "does this look right" automatically every week
    after.
15. Template locked from week 2 onward. Weekly content **auto-adjusts
    within defined flex bounds** (font size, row height, truncation) to
    fit — the template's fixed design (colors, fonts, layout structure,
    slide count/order) never changes.
16. Escalate to the PM, don't silently degrade, if content doesn't fit even
    at the tightest allowed flex bounds.
17. Slide rendering: no built-in `pptx` Skill exists in this environment
    (investigated and confirmed absent — see "Known gotchas" #16; superseded
    the same way Excel and the PI concept were, see Decision Log).
    **python-pptx renders directly**, deterministically; a project-specific
    generated skill (`slide-generation-agent`) still holds the locked
    template's design parameters (palette/fonts/layout archetype/flex
    bounds), same skill/code boundary as the other two skills.
18. Review Gate is mandatory and human — PM sees the actual rendered slide
    (not raw text/JSON) and must approve/edit. No autonomous publishing.

## The core architectural principle
**Deterministic where reproducibility matters, agentic where only judgment
works.** Never negotiable, never skill-overridable, enforced in code:
- Turn budget caps (cost/time control)
- Prompt injection defense (retrieved text is data, never instructions)
- Output schemas (structured contracts between components)
- The status taxonomy itself (downstream components depend on a fixed label set)
- The RAG rollup (pure function, no LLM)

Genuinely agentic, by design:
- Investigation strategy (what to check, in what order, when to stop)
- Narrative tone and phrasing
- Curation judgment (what to include/trim, within the hard rules above)

## Skills-driven design (why, and the boundary)
What varies per project (ADO entry criteria, hierarchy, field names, status
report conventions, slide template) lives in generated `SKILL.md` files
under `skills/<project_id>/<agent-name>/`, not hardcoded assumptions —
because these things genuinely differ per project (some track Epics, some
link Bugs to Stories, some use a PI field, some don't) and it was wrong to
assume our first project's setup was universal.

**What belongs in a skill vs. code:**
| Skill-defined (varies per project) | Code-enforced (never varies) |
|---|---|
| Entry criteria (Tag/State/PI field/whatever) | Turn budget cap |
| Hierarchy traversal plan | Prompt injection defense |
| Field name mappings | Output schema |
| Decision heuristics for *this* project's structure | Status taxonomy |

Skill files have YAML frontmatter (for code to parse directly — e.g.
`list_committed_features()` builds its WIQL from `entry_criteria`) plus a
markdown body (prose the agent reads as project-specific investigation
notes). See `common/skill_loader.py` and the real example at
`skills/ai-reports-demo/feature-agent/SKILL.md`.

**Discovery Agent** (not yet built) generates all 3 skills per project
during onboarding by inspecting the real ADO structure and a sample status
report, asking the PM clarifying questions, then **validating the
generated skill against real data before locking it in** — shows the PM
the actual investigation trace, not just the generated prose.

## Multi-agent architecture pattern
Confirmed via a fitness review against Anthropic's own "Building Effective
AI Agents" architecture guide (see Decision Log for the full mapping): this
project is a **hierarchical/supervisory + parallel fan-out + evaluator-
optimizer hybrid** — specifically matches the paper's "hierarchical systems
with parallel processing" pattern. Orchestrator delegates, never decides
content; Feature Agents fan out in parallel (independent, no shared state);
Synthesis↔Critique is a capped generator-evaluator loop.

Estimated cost: **~$0.29/run** at current Sonnet pricing for a typical
8-Feature week (Feature Agent investigation is ~70% of total cost — the
one place worth optimizing if cost ever matters). See Decision Log for the
full breakdown.

## Repo layout
```
mcp_servers/    ado_mcp (Node.js, official MS package — no Python equivalent
                exists) + ppt_mcp (Python)
common/         mcp_client.py (shared MCP client — every agent uses this,
                not its own connection code) + skill_loader.py
skills/         generated per-project SKILL.md files
agents/         feature_agent, status_report_agent, synthesis_agent,
                critique_agent, slide_generation_agent, discovery_agent
core/           rag_rollup.py (deterministic), orchestrator.py (coordination
                only — fan-out/fan-in, retries, sequencing, zero content
                decisions)
archive/        Persistence MCP server over Postgres/Neon — designed fresh for
                the current pipeline, not a port of anything pre-existing
review_gate/    PM approval — CLI, the intentional final form (not a placeholder
                for a future GUI/web app), same ask_human pattern as discovery_agent/
                slide_generation_agent
config/         config templates
tests/          integration tests
docs/           this file + DECISION_LOG.md + BACKLOG.md
```

## Build status
| Component | Status |
|---|---|
| `common/mcp_client.py`, `common/skill_loader.py` | ✅ Done, tested |
| `mcp_servers/ado_mcp`, `mcp_servers/ppt_mcp` | ✅ Carried over, previously verified (`ppt_mcp` needed a real fix during Status Report Agent's live verification — see "Known gotchas" below) |
| `agents/feature_agent` | ✅ **Done, fully live-verified** against a real ADO org and real Anthropic API — see "Known gotchas" below for 3 real bugs found and fixed during this |
| `agents/status_report_agent` | ✅ **Done, fully live-verified** against a real Anthropic API and a real fixture report (exercised both Other-Initiative identification and enrichment-flagging, both `match_confidence` values) — see "Known gotchas" below for 2 real bugs found and fixed during this |
| `archive/` | ✅ **Done, fully live-verified** against a real Neon Postgres — schema, migration, and all 7 tools exercised over the real MCP protocol (upsert idempotency, the approved-only prior-week filter, approval-reset-on-resave, wholesale snapshot replacement). Gained three post-launch additions, each with an idempotent migration statement and a full suite re-verification after: a `trend_line` column and a fix to `rag_status`'s `CHECK` constraint during `core/orchestrator.py`'s build (it never included `Unknown` — see "Known gotchas" #11), and — during `review_gate/`'s build — a `review_notes` column plus two new tools, `approve_report` (the only tool that can *set* `pm_approved_at`; `save_report_snapshot` can only ever reset it to `NULL`) and `get_latest_unreviewed_report` (deliberately leaner than `get_prior_week_report` — no snapshot joins, since `render_report()` doesn't need them) |
| `core/rag_rollup.py` | ✅ **Done, fully tested** — pure function, 13 unit tests covering the severity ordering, the collapsed Unknown edge case (empty list vs. all-Needs-Human-Review), Green-with-mixed-NHR, and loud failure on malformed input. No credentials needed, no tiering |
| `agents/synthesis_agent` | ✅ **Done, fully live-verified**, including three full re-verifications after later touches — the `common/risk_floor.py` extraction + `prior_week`-in-return-dict addition (for `agents/critique_agent`), the `revision_feedback` threading through Parts B/C (for `core/orchestrator.py`), and the internal-error-string leak fix (`merge_feature_enrichments` no longer spreads unknown Feature keys + a `FORBIDDEN_VOCABULARY_RULE` on both Part B/C prompts — see "Known gotchas" #12) — no regressions any time. Against a real Anthropic API and real Neon Postgres: Part A's merge logic (regression-tested for a real overlap-dilution bug found during this build), Part B's risk floor (both a real live run honoring it AND a mocked-agent test proving the code-level safety net actually fires when violated), Part C's prose, and the full `synthesize_report` path confirmed to call `archive.get_prior_week_report` exactly once per run, not once per Part |
| `agents/critique_agent` | ✅ **Done, fully live-verified** against a real Anthropic API — a well-formed report (`passed: true`, all 2 code-enforced + 5 skill-defined checks passed) and a deliberately risk-floor-violating one (`passed: false`, driven by the real model path, not mocked) both confirmed. The violating case proved code-enforced and skill-defined checks are genuinely independent: `risk_floor` failed while all 5 skill-defined checks passed on their own merits (the prose itself was well-written even though the underlying data was broken) — `overall_feedback` correctly led with the code-enforced failure regardless |
| `core/orchestrator.py` | ✅ **Done, fully live-verified end to end** — real ADO org, real Anthropic API, and real Neon Postgres together for the first time in this project, all 4 agents + Archive in one real `run_pipeline()` run, `report_id` persisted. Found and fixed 2 real cross-component bugs only a genuine end-to-end run could surface (see "Known gotchas" #11-12) — neither was reachable by any single component's own isolated live verification. Also 7/7 mocked control-flow tests covering all 4 revision-loop branches, and 2 real integration issues found by tracing actual signatures rather than assuming (`status_report_agent`'s `existing_features` shape, the `ensure_project`-before-`save_report_snapshot` FK requirement). Worth noting honestly: even after both fixes, the live run still ended `reviewed: False` — not a bug, but real evidence that a rigorous 5-criterion skill-defined rubric doesn't always converge within one revision; `MAX_REVISIONS` may be worth revisiting once more real runs establish a pattern, per Backlog's "revisit once real usage shows what matters" posture |
| `agents/slide_generation_agent` | 🟨 **Implemented, tier-1 + scripted-conversation tests all pass** (33 checks: the fit heuristic's full ladder including invalid-bounds rejection and the SlideFitError raise-at-cap, `_validate_flex_bounds`'s own unit tests plus a forced-violation regression test, a structural check that the design prompt states its real numeric anchor, design-derived helpers, `default_ask_human`, and Mode 1's happy-path/regenerate-loop/cancel-path/partial-candidate-failure/all-candidates-failure conversations). **Two consecutive live runs of Mode 1 found and fixed real bugs, same failure category both times** — see "Known gotchas" #17 (a candidate's self-contradictory `flex_bounds` crashed mid-render instead of being rejected up front) and #18 (the real root cause underneath #17: the design prompt never told the model the actual numeric constant it needed to satisfy, so validation kept correctly rejecting a value the model had no way to get right). Live conversation not yet re-attempted since #18's fix — **needs the project owner to re-run it, not something this session can verify**. Two genuinely different modes: **Mode 1** (`run_slide_generation_discovery`, once per project) — one agentic call proposes 3 design PARAMETER sets (palette/fonts/flex_bounds), never raw file manipulation; each is rendered deterministically into one of 3 fixed layout archetypes (`single_column_narrative`, `two_column_metrics_sidebar`, `banner_header_grid`) already implemented in code; PM picks via `ask_human` (discovery_agent's pattern, not AskUserQuestion — same reasoning). **Mode 2** (`render_report`, every week after) — fully deterministic, zero LLM, zero MCP, same testability tier as `core/rag_rollup.py`: loads the locked skill, renders the 3 slides, auto-fits within flex_bounds (font size → row height → truncation, Requirement 15's own lever order), raises `SlideFitError` (Requirement 16's escalation) if content genuinely can't fit. Investigated and found the built-in `pptx` Skill referenced in the original Requirement 17 does not exist in this environment — see "Known gotchas" #16 — so python-pptx renders directly (already a dependency via `ppt_mcp`'s parsing side). **Mode 2's own render_report is fully unit-tested here** (all 3 archetypes, the SlideFitError overflow case, the empty-features/empty-initiatives case); genuine tier 3 for Mode 1 (opening the 3 rendered .pptx candidates and judging them as a PM would) — **needs the project owner to run it, not something this session can verify** |
| `agents/discovery_agent` | 🟨 **Implemented, tier-1 + scripted-conversation integration tests all pass** (22 checks: WIQL-sampling helpers, `default_ask_human`'s input validation, `_normalize_field_name`/`_resolve_field`/`_append_caveats`, and full happy-path/reject-retry-loop/cancel-path/field-name-normalization/caveat-guarantee conversations for both skills, real `write_skill`/`load_skill` round-tripping, zero credentials needed). Generates `feature-agent` and `status-report-agent` skills only — slide-template skill explicitly deferred (needs `slide_generation_agent`, not built). Architecturally new: a real PM conversation via a custom `ask_human` callable, not a one-shot structured call — `AskUserQuestion` investigated and deliberately rejected (see "Known gotchas" #13). **The first genuine live attempt already found and fixed two real bugs**: a free-text answer ("Tag" vs. the expected "Tags") crashed the run (#14, fixed with a deliberately narrow scope — only that one question became closed-choice, not a blanket conversion), and a PM's legitimate override of a failed sanity check left no trace in the persisted skill (#15, fixed with a deterministic caveat-guarantee, extending this project's "verify mechanically, never trust self-report" convention to free text). Live conversation not yet re-attempted since either fix — **needs the project owner to re-run it, not something this session can verify** |
| `review_gate/` | 🟨 **Implemented, tier-1 + scripted-conversation tests all pass** (9 checks: the report/`report_id` pairing validation, `default_ask_human`'s input validation, and the approve path/reject-requires-notes loop/`SlideFitError`-auto-reject routing/standalone-fetch path/nothing-pending path, all with `render_report` and Archive's two new tools mocked). The smallest component by design — almost no new logic, mostly integration: `render_report()` (Mode 2, already fully deterministic) does the rendering, `archive`'s new `approve_report`/`get_latest_unreviewed_report` tools do the persistence. Every signature traced directly from source before designing anything, confirming `core/orchestrator.py`'s `run_pipeline()` report shape is a strict superset of what `render_report()` needs — no adapter needed, unlike the `feature_id`/`id` mismatch caught earlier in this build. `SlideFitError` (Requirement 16's escalation) routes through the *same* `approve_report(approved=False, ...)` call a human rejection makes, confirmed by a dedicated test asserting `ask_human` is never even consulted in that case. CLI is the intentional final form, not a placeholder. Genuine tier 3 (a real human decision on a real rendered deck) — **needs the project owner to run it, not something this session can verify**; requires `project_id="singleslide"` to first have a real persisted report (it already has all 3 skills, including the locked template, but a `run_pipeline()` live run for that project specifically hadn't been confirmed as of this component's build) |

## Known gotchas (learned the hard way — don't rediscover these)
1. **ADO MCP's `@project` WIQL macro doesn't reliably resolve** when calling
   tools directly and programmatically (outside the Agent SDK's own
   tool-use loop). Use the literal project name as a quoted string instead.
2. **The ADO MCP server wraps some tool results in an untrusted-content
   delimiter banner** (`<<hash>> [UNTRUSTED ... CONTENT] <<hash>>\n{json}\n<</hash>>`)
   as its own prompt-injection defense. An LLM inside the Agent SDK's loop
   handles this natively; plain Python code calling a tool directly does
   not — `common/mcp_client.py`'s `call()` strips this wrapper before
   attempting JSON parsing. If you add a new direct (non-agentic) MCP call
   anywhere, this is already handled by the shared client — don't reinvent it.
3. **`wit_work_item`'s `get_batch` (and every other action) requires an
   explicit `project` parameter**, even though it's not marked `required`
   in the schema — omitting it triggers the tool to attempt an interactive
   "project selection prompt" (MCP elicitation), which fails with `Client
   does not support form elicitation` since our client doesn't implement
   that flow. Always pass `project` explicitly.
4. **WIQL queries only ever return work item IDs**, never field values,
   regardless of what's in the `SELECT` clause — this is real ADO REST API
   behavior. Always do a follow-up `get_batch` call to hydrate Title/Tags/
   whatever fields you actually need.
5. **Claude Agent SDK's `max_turns` counts every assistant turn, including
   the final structured-answer turn** — not just tool-call turns. If your
   system prompt tells the agent "you have N tool calls," it needs N+1
   turns available, or it will hit `error_max_turns` before ever producing
   output. Feature Agent uses `max_turns=5` for a 4-tool-call budget (3
   flexible + 1 reserved for the final answer).
6. **Python's `claude-agent-sdk` PyPI package versions independently from
   the npm package** `@anthropic-ai/claude-agent-sdk` — don't copy a
   version pin from one to the other's requirements.txt (this caused a
   real install failure: pinned `>=0.3.0` based on the npm version, but
   PyPI hadn't reached that yet).
7. **The Python Agent SDK reports some errors via `ResultMessage.is_error`
   with `subtype` still `"success"`**, not by raising an exception —
   opposite of the JS SDK's behavior (which raises during iteration).
   Check `message.is_error` before checking `subtype`.
8. **Base64 is not encryption.** If a PAT or API key ever gets pasted into
   a chat/log/anywhere, treat it as compromised regardless of encoding —
   base64 decodes in one line.
9. **`mcp>=2.0.0` renamed/relocated `FastMCP`** from `mcp.server.fastmcp` to
   `mcp.server.mcpserver.MCPServer` — same API surface (`name=`, `.tool()`
   decorator, `.run_stdio_async()`), different import path. `ppt_mcp/server.py`
   was written against the old path and its own `requirements.txt` pin
   (`mcp==2.0.0`) didn't catch this, because the pin was correct — the
   *package's* public API changed under that version. Broke silently: the
   server process died on import every time it was spawned, with no
   exception surfaced anywhere near the caller (see gotcha #10). Fixed with
   a one-line import change; watch for this again if `mcp` gets upgraded
   further.
10. **A custom local MCP server that crashes on startup import doesn't
    surface as a clean connection error inside the Agent SDK.** The
    server's status just stays `pending`, and the model — unable to find
    the tool — spends its entire turn budget on repeated tool-discovery
    lookups that keep coming back empty, ultimately failing with
    `error_max_turns`. That failure mode looks identical to "the turn
    budget is too low" (gotcha #5) but has a completely different root
    cause. Before raising `max_turns` to fix an `error_max_turns` on a
    *new* MCP integration, first verify the server actually starts
    standalone (`python3 server.py`) or connects via a direct
    `common/mcp_client.py` call — cost real time chasing the wrong fix here
    during Status Report Agent's live verification.
11. **`archive`'s `weekly_reports.rag_status` `CHECK` constraint only allowed
    `('Red', 'Amber', 'Green')`**, silently missing `Unknown` — because
    `archive/` shipped before `core/rag_rollup.py` existed and added that
    4th value. Every prior live test of `synthesis_agent`/`critique_agent`
    used fixtures that guaranteed a Red/Amber/Green result, so nothing
    caught the gap until `core/orchestrator.py`'s first genuine end-to-end
    live run — a real Feature legitimately landed on `Needs Human Review`
    (feature_agent hit `error_max_turns` investigating it), correctly
    rolled up to `Unknown`, and `save_report_snapshot` failed on a
    `CHECK` constraint violation at the very last step, after every
    upstream stage had already succeeded. Fixed with a DROP+ADD
    `CONSTRAINT` in `schema.sql` (Postgres has no `ADD CONSTRAINT IF NOT
    EXISTS`) alongside the pattern already established for `trend_line`'s
    `ADD COLUMN IF NOT EXISTS`. A reminder that a component being
    "fully live-verified" only means verified against the scenarios its
    own tests happened to exercise — a downstream component's later
    addition (a new enum value, in this case) can silently invalidate an
    earlier one's constraints with no test anywhere catching it until a
    real run produces the untested value.
12. **A raw internal error string can leak two full hops downstream into
    executive-facing prose before anything catches it.** `feature_agent`'s
    per-item failure path adds a real exception string (e.g. `"...
    error_max_turns"`) under an `error` key on the Feature dict — reasonable
    for operator visibility on `feature_agent`'s own output. But
    `synthesis_agent.merge_feature_enrichments` used to spread `**feature`
    when reconstructing its output, so that key rode along into Part B's
    prompt, and the model (reasonably, given what it saw) wrote it straight
    into `curated_features` and then `executive_summary`. `critique_agent`
    caught it — but only after spending the pipeline's one allowed revision
    on it. Fixed at the one place all Feature data funnels through before
    reaching any LLM prompt: `merge_feature_enrichments` now reconstructs
    its output from only the canonical `FEATURE_SCHEMA` fields, never a
    `**feature` spread. Worth the general lesson: passing "just pass
    everything through" dicts between a deterministic stage and an agentic
    one is a real injection path for internal implementation detail, not
    just a style nitpick.
13. **`AskUserQuestion` (and the rest of the ambient Claude Code CLI tool
    surface — `Bash`, `Edit`, `Write`, etc.) is technically reachable from
    a `claude_agent_sdk.query()` call in this environment**, even when
    `allowed_tools` doesn't list it — because `claude_agent_sdk` shells
    out to a real Claude Code CLI installation on this machine, which
    exposes its whole tool catalog as deferred tools regardless of the
    allowlist. Confirmed directly from a captured `SystemMessage` during
    gotcha #10's investigation (`'tools': ['Task', 'AskUserQuestion',
    'Bash', ...]`). Considered using `AskUserQuestion` to drive Discovery
    Agent's PM conversation natively inside an agentic loop — rejected:
    reachability in the tool list doesn't prove it behaves correctly when
    `query()` runs detached from an interactive session actually watching
    for it, and that's the exact failure shape gotcha #10 already
    documented (something that looks available but silently hangs or
    fails with no clear diagnostic). Not worth betting Discovery Agent's
    entire interaction model on an unverified assumption when a strictly
    safer, directly-testable alternative existed (a custom `ask_human`
    callable — see `agents/discovery_agent`). Different in kind from every
    other gotcha above: investigated and avoided before writing any code,
    not discovered broken after the fact — worth recording for that
    reason alone.
14. **A free-text question matched against a small closed dict is a real
    crash risk, even when every individual answer is reasonable.** The
    very first real interactive run of `agents/discovery_agent` crashed:
    asked "a Tag, a State, or something else?", the PM reasonably typed
    "Tag" (singular) — but `_FIELD_MAP` only recognized "Tags" (plural),
    matched exactly, so it resolved to the nonexistent ADO field
    `System.Tag`, sampled zero real values, and correctly refused to
    proceed on nothing (the loud-failure design worked exactly as
    intended — this was a real input-handling gap, not a validation
    bug). Fixed two ways together, deliberately not just one: (1) that
    specific question became a closed-choice prompt (`["Tag", "State",
    "Something else"]`, with "Something else" triggering a free-text
    follow-up) — chosen narrowly for *this one question*, not applied as
    a blanket policy, because every other free-text question in the flow
    either has no downstream exact-match logic at all (`child_types`,
    `child_relation` — read only as prose by feature_agent's own agentic
    loop) or already had a retry/sanity-check safety net (`work_item_type`
    on a zero-sample result, `story_points_field` on an all-empty sample)
    — converting those too would be solving a risk that doesn't exist
    there. (2) `_normalize_field_name` normalizes case/plural variants of
    the two well-known field names regardless of which path text arrives
    by (the closed choice, or the "Something else" escape hatch), and —
    critically — the *persisted* skill stores the canonical `"Tags"`, not
    whatever the PM literally typed: `feature_agent.py`'s own
    `_resolve_field` is exact-match too, so an unnormalized value in the
    written skill would have silently broken every future weekly
    `feature_agent` run for that project, not just this one Discovery
    session.
15. **A flagged-and-overridden sanity check is invisible if the override
    doesn't survive into the one place a future reader would see it.**
    Same live session as gotcha #14: the `story_points_field` sanity
    check correctly fired (empty on every sample) and the PM correctly
    chose to keep the value anyway (reasonable — only one real sample
    existed) — but the persisted skill body stated the field as unhedged
    fact, with no trace that it was ever flagged. The check ran, found
    something real, and the PM's judgment call about it evaporated the
    moment `run_feature_agent_discovery` returned. Fixed by collecting
    such overrides into a `discovery_caveats` list, passed into the
    body-drafting context (so the model *can* weave it in naturally), and
    then — the part that actually matters — `_append_caveats`
    deterministically guarantees every caveat lands in the persisted body
    regardless of whether the drafting call included it, via a fixed
    `## Discovery caveats` section. This is the same "verify
    mechanically-checkable claims in code, never trust the agent's
    self-report" convention (`docs/DECISION_LOG.md`), extended one step
    further: not just validating a structured field the model returned,
    but guaranteeing a specific piece of free text can't be silently
    dropped from prose at all.
16. **The "pptx" Skill referenced in the original Requirement 17 does not
    exist in this environment** — investigated the same way AskUserQuestion
    was investigated for Discovery Agent (gotcha #13), before writing any of
    `agents/slide_generation_agent`, not discovered broken after the fact.
    Three findings: (1) `claude_agent_sdk`'s own generated tool schema
    (`sdk-tools.d.ts` — auto-generated from the real CLI, "DO NOT MODIFY BY
    HAND") has no `Skill` tool definition at all, and zero occurrences of
    "pptx"/"docx"/"xlsx" anywhere in the file — the only skill-adjacent
    entry is `ProposeSkills`, an unrelated mechanism for proposing *new*
    user-level skills from observed patterns. (2) `ClaudeAgentOptions.skills`
    (the real SDK mechanism for enabling skills) discovers skills from
    filesystem `SKILL.md` files under user/project settings and installed
    plugins — its own docstring confirms this, not a built-in registry. (3)
    A full search of every plugin marketplace skill, user-level skill, and
    this project's own `.claude/` directory on the development machine found
    29 installed skills (discord, telegram, frontend-design, skill-creator,
    etc.) and zero pptx/docx/xlsx/office-document skill anywhere. A stronger
    finding than AskUserQuestion's "reachable but unverified" — genuinely
    absent, with no invocation path in the tool schema either. Superseded
    the same way Excel and the PI concept were (see Decision Log): Slide
    Generation Agent uses python-pptx directly (already a dependency —
    `mcp_servers/ppt_mcp` uses it to PARSE `.pptx`; this uses it to WRITE
    one) for fully deterministic rendering, with exactly one agentic call
    (design PARAMETER selection at onboarding, never raw file manipulation).
17. **A candidate's `flex_bounds` can be internally self-contradictory, and
    the only place that caught it was deep inside the render code, mid-
    draw.** The first real live run of `agents/slide_generation_agent`'s
    Mode 1 crashed the whole discovery session: a candidate proposed
    `row_height_in_min` (0.28) above the code's own default row padding —
    a `ValueError` raised from inside `_fit_rows` at render time, with no
    PM-facing message, ending the session. Fixed two ways together: (1)
    `_validate_flex_bounds` now checks every candidate's `flex_bounds` for
    internal consistency (all 3 levers — font size, row height, character
    truncation) immediately after `_generate_candidates`'s agentic call
    returns, before any render is attempted — the "verify mechanically-
    checkable claims in code" convention (`docs/DECISION_LOG.md`), just not
    applied here until this run surfaced the gap. (2) The 3 previously
    inconsistent hardcoded row-padding defaults scattered across
    `_draw_row_list`/`_draw_narrative_block`/`_draw_table_slide` (0.14 vs.
    0.1) were consolidated into one shared `DEFAULT_ROW_PADDING_IN` — that
    inconsistency is exactly what let an invalid candidate look "accidentally
    valid" against one drawer's default while violating another's. A bad
    candidate now fails the **whole batch**, deliberately not a silent
    per-candidate drop — see `docs/DECISION_LOG.md` for why this is a
    different case from the already-existing "one candidate hits
    `SlideFitError`, drop it and continue" handling, not the same situation
    twice.
18. **Validating a constraint in code doesn't help if the prompt never told
    the model the actual number it needs to satisfy.** A second live Mode 1
    run hit the same failure category as gotcha #17 — `_validate_flex_bounds`
    caught it correctly, whole-batch-failed as designed — but with a
    different guessed `row_height_in_min` (0.24, vs. the first run's 0.28),
    both wildly above the real `DEFAULT_ROW_PADDING_IN` (0.12). Root cause:
    `DESIGN_SYSTEM_PROMPT` described the constraint in prose ("a real
    compression from a comfortable default row spacing") but never stated
    the actual number being compared against. Unlike `font_size_pt_min` and
    `display_text_max_chars_min` — each compared against a value the model
    proposes itself in the *same* response (`body_size_pt`,
    `display_text_max_chars_default`), trivially self-satisfiable —
    `row_height_in_min`'s comparison point lives only in code. The model
    was blind-guessing at an anchor it was never shown, so the check was
    always going to keep failing regardless of how many more live attempts
    were run. Fixed by turning `DESIGN_SYSTEM_PROMPT` into an f-string that
    interpolates the real `DEFAULT_ROW_PADDING_IN` value directly (never a
    second, separately hardcoded number that could drift from the actual
    constant), plus a concrete target range. A code-level check catching a
    violation correctly is not the same as the constraint being satisfiable
    by the party being asked to meet it — when a check keeps failing across
    multiple live runs, verify the prompt actually states what's being
    checked before assuming the model is unreliable.

## Coding conventions established so far
- Python throughout except `ado_mcp` (forced Node.js — no Python
  equivalent to the official Microsoft package exists)
- `async`/`await` throughout for MCP and Agent SDK calls
- Every agent's tests include: structural checks (always run, no
  credentials needed), request-construction validation (placeholder API
  key — confirms the request reaches the real API and fails only on auth,
  proving the config itself is correct), and full live-run instructions
  (needs real credentials, run by the project owner, not in CI/sandbox)
- Debug flags (`debug=True` params) on deterministic retrieval functions,
  printing raw responses — this pattern found 3 of the 4 real ADO bugs
  above; keep using it for new integrations rather than guessing
