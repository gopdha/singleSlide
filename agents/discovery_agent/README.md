# Discovery Agent

Generates project-specific skills through a real PM conversation — architecturally
different from every other agent in this repo, which take structured input and return
structured output in one shot with no human mid-run. Full design reasoning:
`docs/DECISION_LOG.md` ("Discovery Agent's interaction model...").

## Scope

Generates **`feature-agent`** and **`status-report-agent`** skills only — both have real
consumers today and can be genuinely validated against real data. The slide-template
skill (Requirement 14's 3-candidate flow) is **explicitly deferred**: it needs
`slide_generation_agent` to actually render candidates for the PM to pick from, which
doesn't exist yet. Nothing here stubs a fake renderer to fake-complete that flow.

## Why a custom `ask_human` callable, not the Agent SDK's `AskUserQuestion`

`AskUserQuestion` is technically *reachable* from a `claude_agent_sdk.query()` call in
this environment (confirmed via a captured `SystemMessage` during an earlier gotcha
investigation — see `CLAUDE.md` gotcha #13) — but reachable in the tool list doesn't
prove it behaves correctly when `query()` runs detached from an interactive session
actually watching for an answer. That's the same failure shape as gotcha #10
(something that looks available but silently hangs with no clear diagnostic). Not worth
betting Discovery's entire interaction model on an unverified assumption.

The deeper reason: Discovery's flow isn't one continuous agentic reasoning loop — it's
deterministic Python orchestration (like `core/orchestrator.py`) with real deterministic
actions (sample real ADO data, parse a real sample report) interleaved with human
questions. A plain `ask_human(question, options=None) -> str` callable — `input()`-based
for real use, a scripted queue of canned answers for tests — keeps the Python code in
control of sequencing, and is directly, deterministically testable.

## What "inspect real ADO structure" actually calls

No new ADO MCP tool. Reuses the exact two tools `feature_agent.py` already verified
(`wit_query` action `wiql`, `wit_work_item` action `get_batch`), just with a broader,
unfiltered query — then computes the real value distribution locally in Python. No
"list all Tags" tool exists anywhere in this codebase's verified surface, and none is
assumed here.

**Hierarchy (`child_types`, `child_relation`) and `story_points_field` are
conversational-only, not data-sampled** — this codebase has never traced a verified way
to fetch an item's relations outside `feature_agent`'s own opaque agentic investigation
loop. Building new relations-fetching logic here would be exactly the "assume a
convenient tool exists" trap this project's discipline exists to avoid.

**Known-unverified detail, flagged for the first real run**: Azure DevOps's real
convention for multi-value fields like Tags is semicolon-separated (`"Committed;
Stretch"`), not comma-separated — `_value_frequency` splits on `;`. No prior component
in this codebase needed to split Tags client-side, so this hasn't been live-verified
against a real multi-tag item yet.

## Conversation flow

**`feature-agent`**: work item type → sample real items of that type → ask which field
marks "reportable" (Tag/State/other) → sample real observed values for that field, show
the PM the actual distribution → pick the value (operator is derived, not asked — Tags
gets `CONTAINS`, everything else gets `=`) → child types / relation name / Story Points
field (asked directly, not sampled) → **validate**: draft the skill into a throwaway
temp `skills_root`, run the real `list_committed_features()` against it, show the PM the
real titles found, loop back to re-pick the value if it's wrong → draft body prose (one
agentic call) → PM reviews → persist.

**`status-report-agent`**: PM provides one real sample report path → `parse_slide()`
called directly (already fully deterministic, no LLM in `ppt_mcp` — this is the
grounding step *and* the validation step at once) → PM confirms the extracted
sections look right → file-naming convention → draft body prose → PM reviews → persist.

**Cost**: 2 real Anthropic calls total for a full run (one body-draft per skill).
Everything else — ADO sampling, `parse_slide`, the validation re-check — is free.

## What's verified here vs. what needs a real conversation

Pure unit tests (WIQL-sampling helpers, value-frequency counting, operator derivation,
`default_ask_human`'s input-validation logic) and a scripted-conversation integration
tier (a queue of canned answers + every external call mocked, `write_skill`/`load_skill`
left real against a temp directory) run every time, no credentials needed — proving the
conversation flow, the validate-reject-retry loop, and persistence mechanics actually
work.

**Genuine tier 3 is deliberately not automated** — it needs a live human conversation,
not just credentials. Run it yourself:
```bash
cd agents/discovery_agent
python3 discovery_agent.py <project_id> <ado_org> <ado_project> <ado_pat_base64> <sample_report_path> [--skills-root PATH] [--debug]
```
Confirm it *feels right* as a real onboarding conversation — that's the acceptance test
here, not something CI or an automated suite can verify.

## Setup
```bash
cd agents/discovery_agent
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```

## Run the tests
```bash
python3 test_discovery_agent.py   # no credentials needed at all
```

## Known benign warning
Same asyncio subprocess cleanup-order artifact noted in every other agent's README
(`Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is closed`) may
appear after tests complete successfully.
