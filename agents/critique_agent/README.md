# Critique Agent (skill-driven)

Evaluator half of Requirement 13's evaluator-optimizer pattern. Reviews
`synthesize_report()`'s full output against a rubric split the same way Synthesis
Agent's own responsibilities are: code-enforced where a check is mechanically
verifiable, skill-defined where it's genuine style judgment. Full reasoning:
`docs/DECISION_LOG.md` ("Naming a recurring convention: verify mechanically-checkable
claims in code, never trust the agent's self-report").

## What's skill-defined vs. code-enforced

| Code-enforced (never varies, computed before the LLM call) | Skill-defined (`skills/<project_id>/critique-agent/SKILL.md`) |
|---|---|
| `risk_floor` — re-runs `common/risk_floor.py`'s `check_risk_floor`, the SAME logic `curate_report` already ran once | Tone matching RAG severity |
| `grounding_coverage` — every risk-floor-labeled curated Feature's title must appear in `executive_summary` | Conciseness / no filler phrases |
| | `trend_line` meaningfully connects to `prior_week` |
| | No jargon/ticket-number bleed, leads with the headline |

**`risk_floor` is re-checked here, not just trusted from Synthesis's first pass**,
specifically for the revision case: a bounded revise loop (built later, in
`core/orchestrator.py`) could ask Synthesis to rewrite, and the rewrite could drop
something the original pass got right. Imported from `common/risk_floor.py`, not
reimplemented — there is exactly one definition of this check anywhere in the codebase.

**`grounding_coverage` is a coverage check, not a hallucination check.** It confirms
critical items didn't get silently dropped from the prose; it cannot catch Part C
inventing a reference to something that isn't real. True citation verification was
considered (Part C self-reports what it referenced, `critique_agent` verifies each
citation) and deferred — see `docs/BACKLOG.md` item 10 — because it requires changing
`synthesis_agent`'s `WRITE_SUMMARY_SCHEMA` and re-verifying Part C live, more blast
radius on an already-shipped component than this build took on. As a cheap partial
mitigation, Part C's system prompt now asks for verbatim title usage at least once per
reference, reducing (not eliminating) false positives from paraphrased titles.

**The final `passed` is always computed in code**, from the full merged checks list
(code-enforced + skill-defined) — never trusted from the model, even for its own
skill-defined checks. Same instinct as `curate_report` never trusting the model to
self-certify the risk floor.

## Scope — what this is NOT

This module produces **one critique verdict per call**. It does not call Synthesis
Agent again, does not decide whether to revise, and does not cap revision attempts —
that's orchestration logic, belongs in `core/orchestrator.py` when it's built, same
reasoning as `synthesize_report` not calling `save_report_snapshot` itself.

## Signature

```python
async def critique_report(
    report: dict[str, Any], project_id: str, skills_root: str | None = None,
    model: str = "claude-sonnet-5", max_turns: int = 3,
) -> dict[str, Any]
```
`report` is exactly `synthesize_report()`'s output — uses `report['features']` (for the
risk-floor re-check), `report['rag_status']`, `report['executive_summary']`,
`report['trend_line']`, `report['curated_features']`, `report['curated_initiatives']`,
and `report['prior_week']`. Zero tools, no `mcp_servers` — everything needed is already
in `report`; unlike `synthesis_agent`, this component never talks to Archive itself
(that's `synthesize_report`'s job, done once, and `prior_week` rides along in its output).

Returns `{"passed": bool, "checks": [{"criterion", "passed", "feedback"}, ...],
"overall_feedback": str}`. Re-run this on every revision, not just the first pass.

## What's verified here vs. what needs your machine
Code-enforced checks (`_risk_floor_check`, `_grounding_coverage_check`): full unit
coverage, always run, no credentials. Structural checks (schema shape, skill loading)
also always run. The full agentic call needs a real `ANTHROPIC_API_KEY` for
request-construction validation and the live run — no `DATABASE_URL` needed anywhere
in this component.

## Setup
```bash
cd agents/critique_agent
pip install -r requirements.txt --break-system-packages   # omit the flag on Windows/Mac
```
No `mcp` package in `requirements.txt` — this is the first agent component with zero
external tool/DB dependencies, so it doesn't need it.

## Run the tests
```bash
# Code-check + structural checks only:
python3 test_critique_agent.py

# + request construction validation:
export ANTHROPIC_API_KEY="sk-ant-..."
python3 test_critique_agent.py

# + live run (a well-formed report AND a deliberately risk-floor-violating one):
export ANTHROPIC_API_KEY="sk-ant-..."
python3 test_critique_agent.py
```

## Known benign warning
Same asyncio subprocess cleanup-order artifact noted in every other agent's README
(`Exception ignored in: BaseSubprocessTransport.__del__` / `Event loop is closed`) may
appear after tests complete successfully.

## Usage
```python
from critique_agent import critique_report

verdict = await critique_report(report, project_id="ai-reports-demo")
if not verdict["passed"]:
    for check in verdict["checks"]:
        if not check["passed"]:
            print(f"{check['criterion']}: {check['feedback']}")
    # core/orchestrator.py (not yet built) decides whether/how to revise from here
```
