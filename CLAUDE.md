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
17. Slide rendering uses **Claude Agent SDK Skills**: the built-in `pptx`
    skill plus a project-specific generated skill for the locked template.
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
review_gate/    PM approval UI/flow
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
| `archive/` | ✅ **Done, fully live-verified** against a real Neon Postgres — schema, migration, and all 5 tools exercised over the real MCP protocol (upsert idempotency, the approved-only prior-week filter, approval-reset-on-resave, wholesale snapshot replacement). No new gotchas found — the `mcp` package API was pre-verified against gotcha #9 before writing `server.py`, rather than discovered the hard way |
| `core/rag_rollup.py` | ⬜ Not started — **next up** (old `rag-rules-engine` used raw metrics — this version rolls up Feature status *labels* instead, different logic) |
| `agents/synthesis_agent` | ⬜ Not started (must handle: prior-week fetch, cross-report initiative dedup, overflow curation with risk-floor rule, narrative writing) |
| `agents/critique_agent` | ⬜ Not started |
| `agents/slide_generation_agent` | ⬜ Not started (Skills-based, 3 slides, bounded auto-fit) |
| `core/orchestrator.py` | ⬜ Not started |
| `agents/discovery_agent` | ⬜ Not started |
| `review_gate/` | ⬜ Not started |

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
