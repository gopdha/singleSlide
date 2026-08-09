# SingleSlide

AI-generated weekly executive leadership report — 3 slides (Executive
Summary, Feature Status, Initiative Status), built from Azure DevOps and
team lead weekly status reports.

This is a fresh repo, started after a significant architecture redesign
from the original 3-input/1-slide concept. See `docs/` for the full
design rationale once it's rewritten to match current status (in
progress — docs lag the build intentionally, written once things
stabilize).

## Architecture summary
- **Two input sources**: ADO (Features) + Weekly Status Reports (team lead PPTs, Other Initiatives)
- **Skills-driven**: what varies per project (ADO entry criteria, hierarchy, report conventions, slide template) lives in generated `SKILL.md` files, not hardcoded assumptions
- **Deterministic where reproducibility matters, agentic where only judgment works**: RAG rollup, turn caps, taxonomy, and injection defense are fixed in code; investigation strategy, narrative tone, and curation are agentic
- **Hierarchical/supervisory + parallel fan-out + evaluator-optimizer** hybrid pattern (see the architecture-pattern fitness review in project history)

## Repo layout
```
mcp_servers/    ado_mcp (Node.js, official MS package) + ppt_mcp (Python)
common/         shared mcp_client.py + skill_loader.py, used by every agent
skills/         generated per-project SKILL.md files
agents/         feature_agent, status_report_agent, synthesis_agent,
                critique_agent, slide_generation_agent, discovery_agent
core/           rag_rollup.py (deterministic), orchestrator.py (coordination)
archive/        Python port of archive-mcp (Postgres/Neon)
review_gate/    PM approval UI/flow
config/         config templates
tests/          integration tests
docs/           PRD, Architecture, System Design (rewrite pending)
```

## Build status
| Component | Status |
|---|---|
| `mcp_servers/ado_mcp` | ✅ Carried over as-is, previously verified against a real ADO org |
| `mcp_servers/ppt_mcp` | ✅ Carried over as-is, previously verified end-to-end |
| `common/mcp_client.py` | ✅ Built |
| `common/skill_loader.py` | ✅ Built, tested (round-trip + loud-failure-on-missing-skill) |
| `agents/feature_agent` | ✅ Built, skill-driven, structural + request-construction validated |
| `agents/status_report_agent` | ⬜ Not started |
| `archive/` | ⬜ Not started (Python port of the old Node archive-mcp) |
| `core/rag_rollup.py` | ⬜ Not started |
| `agents/synthesis_agent` | ⬜ Not started |
| `agents/critique_agent` | ⬜ Not started |
| `agents/slide_generation_agent` | ⬜ Not started |
| `core/orchestrator.py` | ⬜ Not started |
| `agents/discovery_agent` | ⬜ Not started |
| `review_gate/` | ⬜ Not started |

## Next steps
1. `agents/status_report_agent` — Pipeline B, fan-out across team leads' reports, semantic dedup of overlapping Other Initiatives (belongs in Synthesis Agent, per design discussion)
2. `archive/` — Python port
3. `core/rag_rollup.py` — label-based (Blocked→Red, At Risk→Amber), excludes Needs Human Review
4. `agents/synthesis_agent` — narrative + curation + dedup + prior-week continuity
5. `agents/critique_agent` — rubric-based revision loop
6. `agents/slide_generation_agent` — skills-based, 3 slides, bounded auto-fit
7. `core/orchestrator.py` — wire it all together
8. `agents/discovery_agent` — generates all 3 skill files during onboarding, validates before locking in
9. `review_gate/`
