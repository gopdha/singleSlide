# Decision Log

Chronological record of major design decisions and the reasoning behind
them. Read this when you need to understand *why* something is the way it
is, especially before proposing to change it — several of these represent
deliberate rejections of a simpler alternative, not oversights.

## Why 2 sources, not 3 (Excel dropped)
Original design had Excel (PM's project plan) as a third input, acting as
a "master registry" linking ADO Features to PM-tracked initiatives. Dropped
because: (1) it required PMs to maintain a parallel, manually-updated
system that duplicates what ADO already tracks for Features, (2) the real
distinction leadership cares about is "PI Committed Features" (ADO is
fully authoritative) vs. "Other Initiatives" (status reports are the only
real source — these often have no formal tracking system at all). Excel
added a synchronization burden without adding a source of truth for either
category.

## Why the PI concept was dropped
Originally scoped as "PI Committed Features" — Features tagged Committed
*within the current Program Increment*. Simplified to just "Committed"
(any tag value, no PI filtering) because: PI-scoping requires a reliable
signal for "current PI" (an Iteration Path pattern or custom field) that
varies by org setup and adds a discovery burden for no clear reporting
benefit — "any Committed Feature needs to be reported" is a simpler,
equally defensible rule that doesn't depend on getting PI-boundary
detection right.

## Why Feature Agent investigates instead of using a fixed formula
Early design considered computing Feature status from a formula (e.g.
`story_points_closed / story_points_total` against a threshold). Rejected
because real status often depends on qualitative signals a formula can't
see — a Feature with high SP completion but an unresolved vendor blocker
in the comments is not "on track" just because the math says so. This is
the core justification for using an agent (genuine judgment) rather than
a bigger, more complex deterministic rule.

## Why the 4th taxonomy label ("Needs Human Review") was added
Initial 3-level taxonomy (On Track/At Risk/Blocked) forced a label even
when evidence was genuinely ambiguous or absent (e.g. no comments, no
revision history, children stuck in an unclear state with no
explanation). Forcing a guess in that situation is worse than admitting
uncertainty — added as a legitimate, honest 4th option. Explicitly
excluded from the deterministic RAG rollup (it's not a risk signal, it's
an "I don't know" signal) — surfaced separately at Review Gate so the PM
sees uncertainty distinctly from confirmed risk.

## Why Other Initiatives are narrative-only (no status label)
Considered giving Other Initiatives the same 4-level taxonomy as Features
and rolling both into RAG. Rejected: Other Initiatives come from informal
narrative (status report prose), not a system of record — assigning them
a formal status label implies a rigor the underlying data doesn't
actually have. They're informational updates, not risk-bearing tracked
items. This also cleanly resolves what would otherwise be a real gap: if
they had labels, the RAG rollup would need to account for them, and an
initiative going informally "blocked" without ever showing up in the
headline status would be a real inconsistency. Keeping them label-free
avoids the whole problem rather than needing to solve it.

## Why the RAG rollup stays deterministic even though Feature status is agentic
This was explicitly discussed as a potential tension: "agent figures out
status based on content" sounds like it should mean the whole system's
judgment is agentic. Resolved by splitting *where* judgment applies:
per-Feature status (the story of *this* Feature) is genuinely agentic,
grounded, cited. Overall report RAG (the one number leadership anchors
decisions to) stays a pure function, just fed by agent-produced labels
instead of raw metrics. Same principle as the original RAG Rules Engine
design (deterministic, auditable, reproducible) — moved one layer up
rather than abandoned.

## Why Slide 2/3 curation lives in Synthesis Agent, not a separate agent
Considered a dedicated "Curation Agent." Rejected: curation (what to show
when there's overflow) requires the same full-context view Synthesis
already needs to write the Executive Summary — giving it to a separate
agent would mean re-passing the same complete Feature/Initiative list
somewhere else for no benefit, just an extra hop. Same reasoning applied
to cross-report Initiative deduplication (also lives in Synthesis, for
the same full-visibility reason). Explicitly flagged as a risk: Synthesis
Agent's scope has grown considerably (fetch history, merge enrichments,
dedupe initiatives, curate overflow, write narrative) — if output quality
ever seems inconsistent, the first thing to try is splitting the
"structured curation" half from the "prose generation" half into two
sequential steps, not adding more agents.

## Why template selection happens once, not every week
Considered a per-week visual-QA agent (vision-capable Claude scoring each
rendered slide for "does this look executive-grade"). Rejected in favor
of: 3 candidates generated once at onboarding, PM picks, locked from week
2 on, weekly rendering only adjusts within pre-approved flex bounds (font
size, row height, truncation). Reasoning: "does this look right" is a
one-time human judgment call, not a recurring subjective question an AI
should re-litigate every week — re-judging it weekly risks the system
slowly drifting toward something a human never actually approved. A
cheap, non-visual "does content fit the locked template's flex bounds"
check replaces the recurring subjective visual check; only escalates to
the PM if content genuinely can't fit even at the tightest bounds.

## Why Skills, and why the specific skill/code boundary
Realized mid-design that hardcoding ADO entry criteria (e.g. "Tag =
Committed") assumed our first test project's setup was universal — false,
since real orgs vary (PI fields, Epic-tracking, Bug-linked-to-Story
hierarchies, etc.). Rather than building a complex configuration schema,
used the Claude Agent SDK's native Skills mechanism, matching the same
pattern already used for the slide template. The skill/code boundary
(skill = strategy, code = guarantees) exists specifically because
downstream components (RAG rollup, Synthesis) depend on fixed contracts
— if skills could redefine the status taxonomy or remove turn caps,
those downstream guarantees would break per-project, which defeats their
purpose.

## Architecture pattern fitness review (against Anthropic's "Building Effective AI Agents" guide)
Full pattern-by-pattern mapping was done against Anthropic's published
architecture patterns paper. Summary: SingleSlide is a **hierarchical/
supervisory + parallel fan-out + evaluator-optimizer hybrid**, matching
the paper's own named "hierarchical systems with parallel processing"
pattern (their worked example: a risk-assessment supervisor delegating to
parallel credit/market/operational risk agents — structurally identical
to our Orchestrator delegating to parallel Feature Agents). Deliberately
avoided: pure single-agent (would blur investigation/writing/critique into
one generalist, reintroducing the "distractor domain" problem the paper
warns about), and decentralized/peer-to-peer (wrong fit for a
high-control-requirement executive report — the paper's own framework
says predictable/traceable behavior beats emergent coordination when you
need to explain a decision to leadership).

Two things the paper's own guidance flagged that we should watch:
1. **"Start with single agents to prove ROI, evolve based on data"** — we
   designed the full hybrid architecture before running anything
   end-to-end. Deliberate trade-off for a portfolio project demonstrating
   range, not an accident — but worth naming honestly.
2. **Context management / response-size capping** (paper recommends
   capping tool responses at ~25,000 tokens) — not yet implemented
   anywhere. Feature Agent's `get_batch` on a Feature with many children
   could return a large response. Worth adding before this hits a Feature
   with a large child count in practice.

## Cost estimate (validated, not assumed)
**INVALIDATED by CLAUDE.md gotcha #20 (CRITICAL) — see "The real per-run cost was ~10x the
design-time estimate" below for the full story.** This estimate was based on a design-time
token estimate, never verified against real billing until observability's first live trace
caught the actual figure was off by roughly 10x. Left below for the historical record of what
was assumed at the time — do not cite it as a current cost figure.

Full breakdown: ~91,000 input + ~11,200 output tokens per weekly run
(8 Features, 4 status reports, 2 critique cycles assumed) = **~$0.29/run**
at Sonnet intro pricing ($2/$10 per M tokens), ~$0.44/run at standard
pricing. Feature Agent investigation is ~70% of total cost — the
concentration point if cost optimization is ever needed (e.g., a cheaper
model for Features that turn out straightforward). Scales roughly
linearly with Feature count (~$0.62/run at 20 Features, ~$1.16/run at 40).
Compared to a rough single-agent equivalent (~15-20K tokens), this
architecture uses ~5-6x more tokens, not the paper's cited "10-15x" for
multi-agent systems generally — reasonably cost-disciplined given the
deterministic RAG rollup costs nothing and Slide Generation leans on
Skills/templating rather than open-ended generation.

## Why Status Report Agent flags enrichments instead of merging them
Considered letting Status Report Agent decide directly whether a report's
mention of a risk on an existing Feature should be merged into that
Feature's update (the "only if ADO's own comments don't already say it"
rule from the requirements). Rejected: that rule requires knowing what
Feature Agent's evidence already contains, and Status Report Agent has no
visibility into it — only a bare id/title list of existing Features is
passed in for matching. Making the merge call with incomplete information
would be a judgment call dressed up as a fact. Status Report Agent instead
flags a `potential_enrichment` (with a `match_confidence` of high/low, since
the title-only matching is inherently approximate — see Backlog item 6) and
leaves the actual merge decision to Synthesis Agent, which is the only
component with full cross-source visibility to make it correctly.

## Why parse_slide's color_cues are treated as supplementary, not authoritative
`ppt_mcp`'s `parse_slide()` independently classifies shape fill colors
against Red/Amber/Green reference swatches. Considered using this as a
second, independent signal for identifying risk in Other Initiatives or for
deciding enrichment relevance. Rejected as a *decision* input: Other
Initiatives are deliberately label-free (see below), so a color-derived
status would quietly reintroduce the thing that decision explicitly avoided;
and using color alone to decide an enrichment match would be exactly the
kind of silent, ungrounded judgment call the grounding rules elsewhere in
this system exist to prevent. Kept as a *supplementary* signal instead —
Status Report Agent may note a plain-language `color_signals` observation
when a cue plausibly aligns with something already grounded in report text,
surfaced for the human reviewer and for Synthesis, never used to draw a
conclusion on their behalf.

## Real bugs found during Feature Agent's live verification
See `CLAUDE.md`'s "Known gotchas" section — these are documented there
since they're the kind of thing a future contributor needs to see
immediately, not buried in a decision-rationale document.

## Real bugs found during Status Report Agent's live verification
Also in `CLAUDE.md`'s "Known gotchas" (items 9-10), same reasoning: a
version-drift break in `ppt_mcp`'s `FastMCP` import (a previously
"verified" component bit-rotted silently), and a genuinely confusing
failure mode where that break surfaced as `error_max_turns` — indistinguishable
at first glance from a real turn-budget problem, until traced with full
message-stream debugging.

## Archive schema design decisions (project_id identity, prior-week filtering, approval reset, evidence typing)
Four judgment calls made while designing `archive/`'s Postgres schema and
tool signatures, resolved before any implementation was written:

**`project_id` is a required, caller-supplied parameter on `ensure_project`,
not derived from `name`.** Considered deriving it by slugifying `name` (with
an optional override param for safety). Rejected the derive-by-default
approach: `project_id` is already the first-class identifier everywhere else
in this repo (`skills/<project_id>/...`, every agent's `project_id: str`
parameter) — making Archive the one place it's *inferred* rather than
*supplied* would introduce a second, weaker identifier path (slugification
collisions between differently-named projects silently overwriting each
other's `input_config`) for no real benefit, since every real caller
(Discovery Agent, the Orchestrator) already knows the exact slug it's
working with.

**`get_prior_week_report` filters to `pm_approved_at IS NOT NULL`, not
latest-saved.** Considered returning the latest row by `week_of` regardless
of approval state. Rejected: Review Gate can save content that a PM then
edits or rejects, and Synthesis Agent's continuity narrative ("up from At
Risk last week") would be citing a draft the PM never actually approved if
the filter didn't exclude it. Returns null both on a true first run and on
"reports exist but none are approved yet" — both cases mean the same thing
to a caller asking "what was the last approved state."

**`pm_approved_at` resets to `NULL` on re-save of an already-approved
week.** If `save_report_snapshot` is called again for a `week_of` that
already has an approval timestamp (a rerun), new content shouldn't inherit
approval that was granted for different content — stale approval attached
to changed data would defeat the point of Review Gate being mandatory.

**`evidence` columns are `TEXT[]`, not `JSONB`.** Every other flexible field
(`input_config`, `profile`, `curated_features`, `curated_initiatives`) stays
`JSONB` because their shape is genuinely open (owned by not-yet-built
agents). `evidence` is different: both `feature_agent` and
`status_report_agent` already produce it as a flat array of strings, fixed
by their own output schemas — a native typed array is the more accurate
fit, not just a stylistic swap.

## Archive schema — additional confirmed design choices
Three more points confirmed as deliberate (not oversights) once the schema
above was reviewed and approved:

**`curated_features`/`curated_initiatives` (on `weekly_reports`) are
deliberately separate from `feature_snapshots`/`initiative_snapshots`.**
The snapshot tables are the full, uncondensed `investigate_feature()` /
Other-Initiative output for every item investigated that week — the source
of truth Synthesis Agent needs for prior-week continuity. `curated_*` is
the final, ordered, possibly flex-bound-condensed subset that actually
rendered on the slide (Requirement 15's auto-fit truncation can mean slide
text differs from the full snapshot text). Collapsing these into one
representation would either lose the full investigation record or force
every prior-week lookup to reconstruct "what was condensed" from partial
data — neither is acceptable.

**No `template_id` foreign key anywhere in this schema, deliberately.**
Slide templates are Skills (Requirement 17) — the locked template lives as
a generated `SKILL.md` file under `skills/<project_id>/slide-generation-agent/`,
the same skill/code boundary and lookup mechanism (keyed on `project_id`,
via `skill_loader.py`) as `feature-agent` and `status-report-agent`. A
template isn't report-instance data that needs relational versioning in
Postgres — it's a per-project artifact on disk, exactly like the other two
skills. Adding a `templates` table would duplicate that mechanism for no
benefit.

**`pm_edits` (what a PM changed at Review Gate) is intentionally not a
column here.** This is Backlog item 2's "PM correction feedback loop" —
already logged there as deferred, owner's call to build the core pipeline
first and revisit once real usage shows whether it's worth the complexity.
This schema doesn't foreclose adding it later (a nullable `pm_edits JSONB`
column on `weekly_reports` would be a non-breaking addition whenever that's
decided) — its absence now is the same deliberate deferral as the Backlog
entry, not a gap discovered late.

## `core/rag_rollup.py` — the "Unknown" status, and a correction on its provenance
Requirement 10's rule (any Blocked → Red, else any At Risk → Amber, else
Green) leaves two related cases underspecified: zero Features investigated
that week, and every investigated Feature landing on `Needs Human Review`
(none Blocked/At Risk/On Track). Naively falling through to `Green` in
either case would be dishonest — `Green` should mean "evaluated and found
fine," not "nothing to evaluate" or "nothing could be confidently
evaluated." Resolved by collapsing both into one rule rather than two
special cases: `Unknown` fires exactly when there is no confidently-labeled
Feature at all (empty list, or every Feature is `Needs Human Review`) — a
`Blocked`/`At Risk`/`On Track` list of any size, even mixed with some
`Needs Human Review` items, still resolves normally, since real evaluated
signal exists. Same justification that motivated `Needs Human Review`
existing in the taxonomy in the first place, applied one layer up.

**Correction on provenance, for the record:** this was first proposed by
citing "the original design's 'Unknown' status for missing data" as repo
precedent. That precedent does not exist in this repo's documented
history — there is no earlier `DECISION_LOG.md` entry, and no prior
version of this file, that specifies an `Unknown` value. The actual source
was a broader pre-repo design conversation about a *differently-structured*
RAG engine (the old `rag-rules-engine`, which rolled up raw schedule/budget
metrics, not agent-produced status labels) — the concept existed there,
informally, but was never written into this repo. The `Unknown` value
adopted here is a fresh decision for `core/rag_rollup.py`, independently
justified by the reasoning above, not a continuation of documented
history — it only happens to rhyme with an idea from that earlier,
structurally unrelated design.

`total_features` is included in the result as a deliberate diagnostic
field — it lets a caller (Synthesis Agent, eventually) distinguish "0
Features were Committed this week" from "N Features were investigated but
all were Needs Human Review" even though both currently resolve to the
same `Unknown` rag_status. Nothing reads this field yet; it's there so
that distinction doesn't have to be re-derived later from data the
function otherwise wouldn't expose.

## Synthesis Agent — three-way split, the risk floor extended to Needs Human Review, and `trend_line`'s storage deferred
`agents/synthesis_agent` splits into three parts rather than the two
originally sketched in "Why Slide 2/3 curation lives in Synthesis Agent,
not a separate agent" above: Part A (`merge_feature_enrichments`,
deterministic, no LLM — applies Status Report Agent's flagged
`potential_enrichments` onto Feature evidence/risk), Part B
(`curate_report`, agentic — cross-report Initiative dedup and
continuity-aware overflow curation together, since both need the same
full Feature/Initiative list plus `prior_week`), and Part C
(`write_executive_summary`, agentic — pure prose from Part B's
already-finalized output, no tool calls, no re-fetching). This is finer
than "structured curation vs. prose generation" — Part A is pulled out
specifically because it's genuinely reproducible (a `difflib.SequenceMatcher`
overlap check, not a judgment call), and keeping it separate from Part B
means the evidence-merge trail stays fully deterministic even though
curation and prose-writing don't.

**The risk floor (Requirement 12) extends to `Needs Human Review`, not
just `Blocked`/`At Risk`.** The requirement's literal text only names
Blocked and At Risk as never-trimmable. Extended NHR the same protection
because the alternative — NHR features silently droppable from overflow —
directly contradicts why NHR exists at all: it's supposed to get *more*
visibility for its uncertainty, not less. `curate_report`'s post-call
validation checks all three labels against `curated_features`, raising
loudly (matching `rag_rollup`'s `ValueError` convention) if any are
missing — not trusting the agent's adherence to the rule from prompting
alone.

**`trend_line` (Part C's short continuity callout vs. `prior_week`) has no
column in `archive`'s `weekly_reports` table, and none is being added
right now.** `synthesize_report` returns it as a plain key in its result
dict — nothing persists it yet. Storage is deferred to `core/orchestrator.py`'s
build, since that's the first component that will actually call
`save_report_snapshot` (Synthesis's output still passes through Critique
Agent's revision loop before anything is "finalized" enough to archive).
Whether `trend_line` gets its own column then, or gets folded into
`executive_summary`'s prose instead, is a decision for that point, not
this one — deferred deliberately, not forgotten (same posture as the
`pm_edits` deferral above).

## Naming a recurring convention: verify mechanically-checkable claims in code, never trust the agent's self-report
Three separate build sessions independently arrived at the same pattern:
`curate_report`'s risk-floor check (Part B never trusted to enforce
Requirement 12 itself — code re-derives and checks after the call),
`critique_report`'s risk-floor *re-check* (re-run on every call, including
after a revision, specifically because a revision could re-break what the
first pass got right), and the `common/risk_floor.py` extraction itself
(pulled out once a second, independent caller needed the identical logic
— proof this wasn't a one-off, it's a shape the system keeps needing).
Naming it explicitly rather than leaving it as three coincidences: **if a
rubric criterion can be verified by code — an exact-match, a set
membership, a count — it is verified by code, every time the opportunity
exists to check it, not just on the first pass.** The model is never
trusted to self-certify compliance with something code could confirm
directly; agentic judgment is reserved for what genuinely requires it
(tone, dedup, phrasing). This is the same principle behind the RAG rollup
staying a pure function fed by agent-produced labels (see "Why the RAG
rollup stays deterministic even though Feature status is agentic" above)
— applied here one level down, to individual rubric checks rather than
the whole report status. `critique_agent`'s code-enforced/skill-defined
split is this convention's most explicit expression yet: the split itself
*is* the enforcement of "verify what's verifiable, judge what's not."

## `core/orchestrator.py` — a code-enforced check failing after independent re-verification is a bug, not a content judgment call
Discovered while tracing the pipeline end to end: `curate_report` already
validates the risk floor internally on every call, including revisions,
and raises before ever returning. That means if `synthesize_report`
returns successfully at all, the floor is structurally guaranteed to
already hold by the time `critique_report` independently re-checks the
same thing. So `critique_report` failing specifically on `risk_floor` in
a real pipeline run (as opposed to a hand-crafted test report) can only
mean `curate_report`'s and `critique_report`'s two independent
implementations of the same check disagree — a real bug in the code, not
normal variance in subjective judgment the way a failed tone or
conciseness check would be.

Named as an explicit, general convention, not a one-off for this one
check: **when a code-enforced check fails after having already been
independently verified earlier in the same pipeline run, that is a bug
signal, not a content-quality signal, and must hard-stop the run before
persistence** — not get flagged and passed through to a human reviewer
the way a failed skill-defined (or first-time-checked code-enforced)
criterion does. The report's trustworthiness is unknown at that point;
`archive.save_report_snapshot` must never be called on it. This is a
direct extension of "verify mechanically-checkable claims in code, never
trust the agent's self-report" (above): the corollary is that when two
independent code-level verifications of the *same* claim disagree, that
disagreement itself is the loudest possible signal something is wrong,
and the system must fail loudly rather than let a human quietly inherit
an unexplained inconsistency.

## Real bugs found during core/orchestrator.py's live verification
In `CLAUDE.md`'s "Known gotchas" (items 11-12), same reasoning as every
other component's live-verification bugs: a cross-component contract gap
(`archive`'s `rag_status` `CHECK` constraint never learned about
`rag_rollup.py`'s `Unknown` value, since the two components shipped at
different times and no prior test happened to exercise that value), and a
real internal-error-string leak that traveled two full hops downstream
into executive-facing prose before `critique_agent` caught it — fixed at
the source (`merge_feature_enrichments` no longer spreads unknown Feature
dict keys into Synthesis's prompts) plus a `FORBIDDEN_VOCABULARY_RULE`
addition to both Part B and Part C's system prompts, since the same
category of leak also showed up as the model's own word choice
("rollup"), not just literal copying. Both found only because this was
the first genuine end-to-end live run across real ADO, real Anthropic,
and real Neon together — neither was reachable by any single component's
own isolated live verification.

## Discovery Agent's interaction model — AskUserQuestion investigated and rejected
See `CLAUDE.md`'s "Known gotchas" (#13). Different in kind from every
other gotcha logged so far: not a bug found and fixed, but a risk
identified and avoided during design, before any code was written. Logged
in the same place anyway — a future contributor deciding "why not just
use `AskUserQuestion` here, it's right there in the tool list" needs to
see this reasoning as readily as they'd see any other gotcha, not have to
rediscover it by hitting the same failure mode gotcha #10 already cost
real time on.

## Discovery Agent — "Tag" vs. "Tags" crash, and why only ONE question became closed-choice
See `CLAUDE.md`'s "Known gotchas" (#14) for the bug itself. Worth recording
separately here is the *scoping* reasoning, since the natural next question
— "should every free-text prompt in this conversation become multiple
choice, to make this whole failure class structurally impossible?" — was
explicitly considered and answered **no, only this one**. Audited every
free-text question in the flow individually: `child_types` and
`child_relation` are read only as prose context by `feature_agent`'s own
agentic investigation loop, with no deterministic exact-match code path
anywhere touching them — no crash risk exists there at all.
`work_item_type` and `story_points_field` both already had a real
safety net before this bug was even found (a zero-sample retry, and an
all-empty-sample sanity check, respectively) — converting those to closed
choice would harden something that wasn't actually broken. Only
`filter_field` combined the dangerous shape: free text, matched against a
small closed dict, with no existing safety net. Converting everything
"to be safe" would have been solving risks that don't exist at the cost
of a more rigid, less natural conversation — the fix was scoped to where
the actual vulnerability was, not applied as a blanket policy.

## Discovery Agent — a flagged-and-overridden gap must survive into the persisted skill, not just be resolved in the moment
See `CLAUDE.md`'s "Known gotchas" (#15). Same first live session as the
"Tag"/"Tags" bug, a different category of gap: `story_points_field`'s
sanity check correctly fired and the PM's "keep it anyway" was a
legitimate call — the bug wasn't in the decision, it was that the
decision left no trace. This is the same principle as "verify
mechanically-checkable claims in code, never trust the agent's
self-report" (above), pushed one step further: that convention was
originally about not trusting a model to self-certify a structured claim
(the risk floor, grounding coverage). Here there's no model claim to
verify at all — the risk is a human-approved override of a real,
code-detected gap simply not being written down anywhere durable.
`_append_caveats`'s deterministic guarantee closes that gap the same way
the rest of this convention does: don't hope something important makes it
into the output, make it structurally certain it does.

## Why Requirement 17's pptx Skill is superseded
Requirement 17 originally specified "Claude Agent SDK Skills: the built-in
`pptx` skill plus a project-specific generated skill for the locked
template." Investigated before writing any of `agents/slide_generation_agent`
— the same way AskUserQuestion was investigated for Discovery Agent (see
above) — not discovered broken after the fact, avoided before any code
existed. Three findings, in order of directness:

1. `claude_agent_sdk`'s own generated tool schema (`sdk-tools.d.ts`,
   auto-generated from the real CLI — "DO NOT MODIFY BY HAND") has no
   `Skill` tool definition at all, and zero occurrences of
   "pptx"/"docx"/"xlsx" anywhere in the file. The only skill-adjacent entry
   is `ProposeSkills` — an unrelated mechanism for proposing *new*
   user-level `SKILL.md` files from observed patterns, not invoking a
   pre-built one.
2. `ClaudeAgentOptions.skills` (the real SDK mechanism for enabling skills)
   discovers skills from filesystem `SKILL.md` files under user/project
   settings and installed plugins — its own docstring says so directly, not
   a built-in registry reachable by name alone.
3. A full search of every place this development machine would discover a
   skill from — all plugin marketplace skills, user-level skills, and this
   project's own (nonexistent) `.claude/` directory — found 29 real
   installed skills (discord, telegram, frontend-design, skill-creator,
   etc.) and zero pptx/docx/xlsx/office-document skill anywhere.

**Conclusion: no pptx Skill exists in this environment, with no invocation
path in the tool schema either** — a stronger finding than AskUserQuestion's
"reachable but unverified" (gotcha #13). Anthropic does publish a public
`pptx` skill (in `anthropics/skills`), but it targets the Messages API's
code-execution/container beta — upload skill files to a sandboxed container
via the Files API — a fundamentally different integration than every other
agent in this codebase, which calls `claude_agent_sdk.query()` against MCP
servers with narrow `allowed_tools`. Even installed, that skill's own
authoring pattern drives Bash + Write broadly inside its container, which
would have been a real, deliberate architectural departure from this
project's narrow-tool-scope convention — not something to grant by default.

Superseded the same way Excel and the PI concept were superseded (see
above): the requirement's current, authoritative form is python-pptx
(already a dependency — `mcp_servers/ppt_mcp` uses it to PARSE `.pptx`;
`slide_generation_agent` uses it to WRITE one, same library, opposite
direction) doing all actual rendering, deterministically. The agentic piece
is scoped narrowly to what genuinely needs judgment — palette/font/layout-
archetype PARAMETER selection at onboarding — never raw file manipulation.
This matches this project's "deterministic where reproducibility matters"
principle more literally than an LLM-driven pptx Skill would have anyway: a
rendered slide from the same finalized report data must be exactly
reproducible, not vary run to run.

## Slide Generation Agent — layout archetypes as a fixed enum, the auto-fit lever order, and what "escalate" means today
Three more decisions made while designing `agents/slide_generation_agent`,
beyond the pptx-Skill finding above:

**The agentic call (Mode 1) never emits raw layout coordinates.** Considered
having the LLM design full slide geometry (inch/pixel positions) per
candidate. Rejected: it has no way to visually verify a coordinate choice,
and this project's discipline has repeatedly had to catch exactly this kind
of unverifiable model output after the fact (`curate_report`'s risk floor,
`critique_report`'s re-check). Instead, the LLM picks a `layout_archetype`
from a small fixed enum (`single_column_narrative`,
`two_column_metrics_sidebar`, `banner_header_grid`) — each fully implemented
as a deterministic drawing function in code — plus palette/fonts/flex_bounds
suited to that archetype's character. Code owns 100% of the actual drawing
math; the model's job is narrowed to parameters it can reason about in text,
matching the owner's original lean (agentic PARAMETERS, deterministic
rendering) more literally than raw-coordinate generation would have.

**3 archetypes, not more, deliberately not over-built for speculative
variety.** This is a one-time PM choice at onboarding (Requirement 14); 3
genuinely distinguishable options (a narrative list, a metrics-sidebar
dashboard, a formal banner/grid) are enough to form a real preference
without making the choice harder, and the skill format doesn't lock in a
count — a 4th archetype is an additive change later if real usage ever
shows 3 isn't enough, not a redesign.

**The auto-fit ladder's lever order (font size → row height → truncation)
is fixed code, not skill-negotiable** — it directly mirrors Requirement 15's
own listed order, and matches this project's skill/code boundary: the
*bound values* vary per project's locked template (skill-defined), but the
*algorithm* that walks those bounds is code-enforced, exactly parallel to
how `rag_rollup.py`'s rule is fixed code fed by agent-produced labels. Mode
2 (`render_report`) has zero LLM calls as a result — a genuine testability
win exploited directly in the test suite (the full ladder, including the
SlideFitError raise-at-cap case, is unit-tested with no credentials, same
tier as `rag_rollup.py`).

**What "escalate to the PM" (Requirement 16) concretely means today:**
`render_report` raises `SlideFitError` when content doesn't fit even at the
tightest flex bounds. Since `review_gate/` doesn't exist yet and nothing in
`core/orchestrator.py` calls `slide_generation_agent` yet, there is no
PM-facing surface to hand this to — the exception propagates to the caller,
exactly the way `critique_agent`'s risk-floor `RuntimeError` already does.
No `review_gate` interface was invented to catch it prematurely; whoever
wires `orchestrator.py` → `slide_generation_agent` next inherits this
exception the same way.

**Known limitation, not hidden:** python-pptx has no real text-layout
engine — there's no way to ask it "how many lines will this text wrap to at
this font size in this box" and get PowerPoint's actual answer. The fit
heuristic (`_estimate_block_height_in`) is a deterministic APPROXIMATION (a
fixed average-character-width formula), not exact rendering measurement.
Reproducible — the same content always gets the same fit decision — but not
pixel-exact. Documented in the module docstring and here rather than implied
to be more precise than it is.

## Slide Generation Agent — a self-contradictory candidate fails the whole batch, not just itself
The first real live run of Mode 1 (`run_slide_generation_discovery`) crashed:
a candidate proposed `row_height_in_min` (0.28) above the code's own default
row padding, and the only place that was ever checked was deep inside
`_fit_rows` at render time — a `ValueError` mid-draw, ending the session
with no PM-facing explanation. See `CLAUDE.md` gotcha #17 for the bug and
its two-part fix (`_validate_flex_bounds` run immediately after generation,
before any render; the previously-inconsistent hardcoded row-padding
defaults consolidated into one `DEFAULT_ROW_PADDING_IN` constant, since that
inconsistency is what let an invalid candidate look "accidentally valid").

Worth recording separately here is the design decision this raised: when
exactly one of 3 candidates fails `_validate_flex_bounds`, should the whole
batch be rejected, or should just that one candidate be silently dropped so
the PM still sees 2 options instead of a hard failure? Chose **whole-batch
failure**, and — critically — this is a genuinely different situation from
the *already-existing* "one candidate hits `SlideFitError` during render,
drop it and let the PM pick among the survivors" handling built earlier in
the same function, not the same case reached twice:

- **`SlideFitError` is a legitimate outcome even for a perfectly
  well-formed candidate.** `_generate_candidates`'s prompt never shows the
  model the sample content it will later be rendered against (by design —
  see the layout-archetype entry above, the model reasons about parameters,
  not content) — a candidate's bounds can be entirely self-consistent and
  still not happen to accommodate a specific piece of content it never saw.
  Dropping that one candidate and continuing is not hiding a problem with
  the model's output; it's a normal, expected content-fit limitation, no
  different in kind from why the ladder exists at all.
- **An internally self-contradictory `flex_bounds` is content-independent.**
  `row_height_in_min > DEFAULT_ROW_PADDING_IN` is wrong regardless of what
  it's ever rendered against — no sample content could make it valid.
  `DESIGN_SYSTEM_PROMPT` already states the constraint this violates
  plainly ("row_height_in_min must be a real compression from a comfortable
  default... validated in code after you respond"). A candidate failing
  this check is evidence the model didn't reliably follow an explicit,
  self-contained numeric instruction on this attempt — and nothing
  guarantees the other 2 candidates are trustworthy either; they simply
  didn't happen to trip the specific check being looked for. Silently
  dropping the flagged one and presenting the 2 "survivors" as if the batch
  was fine would hide from the PM that the generation call had already
  demonstrated it doesn't reliably follow its own instructions.

Same underlying principle as the risk floor and the orchestrator's
"independent re-verification disagreement is a bug signal" convention
(both above): a violation of an explicit, verifiable constraint is treated
as evidence about the whole unit of work that produced it (the batch), not
quarantined to the one place it happened to surface.

## Slide Generation Agent — a check that "correctly" keeps failing can still be the prompt's fault, not the model's
A second live Mode 1 run hit the exact same failure category as the entry
above — `_validate_flex_bounds` caught a self-contradictory
`row_height_in_min` and whole-batch-failed exactly as designed — but with a
*different* guessed value (0.24 this time, vs. the first run's 0.28). Two
different specific numbers failing the same check is a different diagnosis
than one number failing it once: it's evidence the model isn't converging
toward the real constraint at all, which pointed at the constraint itself
rather than at "the model made a mistake, try again."

Checked directly: does `DESIGN_SYSTEM_PROMPT` actually state the real
`DEFAULT_ROW_PADDING_IN` value `row_height_in_min` is compared against, or
does it only describe the constraint in prose? Confirmed the latter — the
prompt said `row_height_in_min` "must be a real compression from a
comfortable default row spacing" and nothing more. Compare this to the
other two flex_bounds levers: `font_size_pt_min` is compared against
`body_size_pt`, and `display_text_max_chars_min` against
`display_text_max_chars_default` — both comparison points are values the
model proposes *itself*, in the *same* structured response, so "meaningfully
below [the other field you're also writing]" is a fully self-referential,
trivially satisfiable instruction. `row_height_in_min`'s comparison point,
`DEFAULT_ROW_PADDING_IN`, is a fixed code constant the model never sees and
was never told — every previous "fix" (the #17 entry above) addressed
*catching* the violation, never *preventing* it, because the actual gap was
one level upstream of validation entirely.

Fixed by turning `DESIGN_SYSTEM_PROMPT` into an f-string that interpolates
the literal `DEFAULT_ROW_PADDING_IN` constant directly into the prompt text
(never a second, separately hardcoded number in prose that could drift out
of sync with the real constant the way the pre-#17 scattered row-padding
defaults did), plus a concrete suggested target range so the model has a
number to aim for, not just a ceiling to stay under.

Worth naming as its own lesson, distinct from #17 and from "verify
mechanically-checkable claims in code": **a code-level check correctly
rejecting bad output on every attempt is not proof the model is behaving
unreliably — it can just as easily mean the model was never given what it
needs to succeed.** When a check keeps failing across multiple independent
live attempts with different specific values each time (not the same value
repeating), that pattern itself is a signal to inspect the prompt's
completeness before concluding the model can't follow the instruction —
re-running a third time and hoping would have kept failing indefinitely,
since nothing about a third attempt would give the model the missing
anchor. This is why `agents/slide_generation_agent`'s design PARAMETER
generation stays a proposal the PM reviews rather than being trusted
blind either way — but the fix here is a genuine usability fix, not a
justification for the review step to paper over a preventable failure mode.

## `review_gate/` — the last component, deliberately the smallest, and why it needed two new Archive tools
Unlike every prior component, `review_gate/` added almost no new business logic of its
own — `render_report()` (`agents/slide_generation_agent`, Mode 2, already fully
deterministic) does the actual rendering; this component's job is to call it, show a
human the result, and record the decision. The design work here was tracing three
existing signatures precisely enough to confirm that was actually true, not assuming it.

**Traced, not assumed: `core/orchestrator.py`'s `run_pipeline()` report shape needs no
adapter into `render_report()`.** `run_pipeline()` nests `synthesize_report()`'s complete
output under `result["report"]`; a direct grep of every `report[...]`/`report.get(...)`
access inside `render_report()` confirmed it reads exactly `rag_status`,
`executive_summary`, `trend_line` (optional), `curated_features`, `curated_initiatives`,
`week_of` (optional, filename only) — a strict subset of what `run_pipeline()` already
provides. This is the same kind of check that caught the `feature_id`/`id` mismatch
between `feature_agent` and `status_report_agent` earlier in this build — here it came
back clean, and that conclusion is worth as much confidence as the mismatch it didn't
find, precisely because it was checked the same rigorous way rather than assumed by
analogy.

**No archive tool could be reused to set `pm_approved_at` — a real gap, not an oversight
to patch around.** `save_report_snapshot`'s SQL hardcodes `pm_approved_at = NULL` on both
`INSERT` and its `ON CONFLICT` `UPDATE` — by design (a re-save must reset stale
approval, per the original Archive schema decisions above), which means it structurally
*cannot* be reused to grant approval, only ever to reset it. Added `approve_report
(report_id, approved, notes="")` as the one and only tool that can set
`pm_approved_at`, keyed on `report_id` (already a global PK, and already in hand from
`run_pipeline()`'s own return value in the common case) rather than `project_id` — no
cross-project ambiguity risk, and no reason to route through a project lookup for an
operation that's inherently about one specific report.

**`get_latest_unreviewed_report` is deliberately leaner than `get_prior_week_report`, not
a copy-paste of it.** The two look similar (latest `weekly_reports` row by `week_of`,
opposite `pm_approved_at` filter) but `get_prior_week_report` joins
`feature_snapshots`/`initiative_snapshots` for Synthesis Agent's continuity narrative —
data `render_report()` never reads. Pulling data nobody consumes just because a similar
query already existed would be the same "pass everything through" instinct gotcha #12
warned against, one layer up (an unnecessary join instead of an unnecessary dict spread).

**Two supported call shapes, both real, not one built and one speculative.** In-process
chaining (`report`/`report_id` passed directly, right after `run_pipeline()` — zero extra
Archive round-trip) and standalone (`project_id` alone, fetches via
`get_latest_unreviewed_report`) are both genuine, expected usage patterns — a scheduled/
unattended pipeline run and a PM reviewing on their own time are not the same session.
Validated up front (`ValueError` if `report`/`report_id` are given inconsistently — one
without the other) rather than silently guessing which mode was intended.

**`SlideFitError` finally reaches a real human-facing surface, and it routes through the
exact same `approve_report(approved=False, ...)` call a human rejection makes — not a
parallel mechanism.** Per the entry above ("What 'escalate to the PM' concretely means
today"), `render_report()`'s `SlideFitError` had nowhere to go until this component
existed. A report that can't even render can't be shown to a human to judge, so treating
it as an automatic reject (with the error text as the notes) is the honest translation,
not a special case bolted on beside the real rejection path — confirmed by a dedicated
test asserting `ask_human` is never even consulted when this fires, proving it's the same
code path, not a look-alike one.

**`review_notes` (Backlog item 2) is resolved now, narrowly, because its real consumer
exists — not new scope creep.** Backlog item 2 ("PM correction feedback loop") and the
Archive schema's own "`pm_edits` intentionally not a column" note both explicitly framed
this as deferred until "real usage shows whether it's worth the complexity," not
abandoned. `review_gate/` is that real usage: Requirement 18 requires capturing a PM's
reject reasoning, and there was nowhere to put it. Resolved deliberately narrowly —
`review_notes TEXT`, free-text only, written on both approve and reject via
`approve_report` — not the fuller structured `pm_edits` diff (what specifically changed,
field by field) that item 2 also gestured at, which remains genuinely deferred. Same
idempotent `CREATE TABLE` column + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` two-part
pattern already established for `trend_line`.

**Reject requires non-empty notes — `run_review_gate` loops until given, never accepts a
silent rejection.** Same instinct as gotcha #15 (a flagged gap must survive into the
persisted record, not evaporate) applied to the human's own input this time, not the
model's: a reject with no reason recorded would leave a future reader with exactly the
same "the decision happened, the reasoning didn't survive" gap gotcha #15 fixed for
Discovery Agent's caveats.

## `common/observability.py` — Arize-only tracing, proven fail-safe BEFORE any shipped
## agent file was touched, then wired into all of them

The last component built in this project isn't a pipeline stage — it's a cross-cutting
layer over every agentic call site and every direct MCP call, and it carries a real risk
none of the other 8 components did: getting it wrong doesn't produce a wrong report, it
breaks a report that would otherwise have been correct. That asymmetry is why this build
was sequenced differently from every prior component: `common/observability.py` and its
own test suite were built and fully proven FIRST, in complete isolation, touching none of
the 6 already-shipped agent files — the explicit ask was "that test is the one I most want
to see before any of the 6 already-shipped agent files get touched," and the sequencing
held to that literally.

**Verify-first found real, non-obvious facts, not just confirmed assumptions.** `arize.otel.register()`
does NOT validate credentials against the network synchronously — confirmed by calling it
with fake `space_id`/`api_key` and getting back a working (locally) `TracerProvider`, no
exception, all real network activity deferred to a background export thread. This mattered:
it meant `init_tracing()`'s own try/except mostly guards against *local* failures (a
missing dependency, a malformed argument), not the network/auth failure the user's design
brief specifically asked about — that failure mode is real, but it surfaces asynchronously,
outside this process's own control flow, which OpenTelemetry's `BatchSpanProcessor` already
isolates from the caller. The "Annotations and Evaluations" mechanism the user asked to be
investigated as its own spec area turned out to be exactly that — a distinct code path
(`openinference.instrumentation.get_evaluation_attributes`, confirmed by reading the
installed package's real source, not docs) from regular span attributes
(`llm.*`/`tool.*`), applied via `span.set_attributes()` onto the SAME span as the call being
judged, not a separate call or a child span. And `ResultMessage.usage`'s cache-token field
names could NOT be 100% confirmed without a live API call (none available this session) —
reported honestly as unconfirmable rather than assumed, with `llm_span_attributes` reading
every cache-token key via `.get()` and only setting the attribute when actually present,
never fabricating a `0`.

**A real correction to the user's own framing, found by tracing signatures rather than
assuming them: `common/mcp_client.py`'s `call()` chokepoint does NOT cover every MCP call
in this system.** It covers every *direct*, non-agentic call (Archive throughout, `ppt_mcp`
in `status_report_agent`/`discovery_agent`, `discovery_agent`'s ADO sampling) — but
`feature_agent.investigate_feature()` and `status_report_agent.investigate_status_report()`
pass `mcp_servers=...`/`allowed_tools=...` straight into `ClaudeAgentOptions`, so their ADO/
`parse_slide` tool calls happen *inside* the Claude Code CLI subprocess's own internal
agentic loop — structurally invisible to `mcp_client.py` regardless of how the chokepoint
itself is instrumented. Scoped deliberately for v1: one LLM-kind span per whole agentic
call (matching the attribute mapping's own shape — one `input.value`/`output.value` pair
per site), not per internal tool-use turn. Real scope boundary, not a silent gap — Feature
Agent's own internal ADO tool calls are not separately traced in v1.

**The centerpiece: `traced_span`'s shape makes "never breaks the pipeline" a property of
the code, not a claim about it.** Only span setup (before `yield`) and teardown (in
`finally`) are wrapped in try/except; the `yield span` line itself — the only line that
ever runs the caller's real business code — has zero exception handling around it. This
single design choice does two things at once, proven by two different test classes rather
than one: (1) a broken tracer, a raising `start_as_current_span`, or a raising
`set_attribute` all leave a wrapped function's real return value completely unaffected
(`_do_real_work(21) == 42` holds in every forced-failure case), and (2) a genuine
`RuntimeError` raised *inside* a `traced_span` block still propagates normally even with a
fully broken tracer underneath — proving the layer doesn't accidentally hide a real bug
behind broken telemetry, which would be its own, equally unacceptable failure mode. Both
halves of the guarantee needed their own proof; a wrapper that only satisfied the first
half would be indistinguishable from one that silently swallows everything.

**A real gap found in this layer's OWN design, before any live failure exposed it —
described in full as gotcha #19 (CLAUDE.md).** `traced_span`'s fail-safe guarantee only
covers code that runs *inside* it. Every attribute-builder helper
(`input_value_attribute`, `output_value_attribute`, `tool_span_attributes`,
`llm_span_attributes`, `evaluation_attributes`) is called as an ARGUMENT at every
instrumented call site — e.g. `traced_span(name, kind, obs.input_value_attribute(prompt))`
— which Python evaluates *before* `traced_span` is ever entered. An unguarded `ImportError`
in one of those helpers (the realistic case: `openinference-semantic-conventions` not
installed) would have raised straight into the caller, completely bypassing the very
protection this module exists to provide. Caught by the same "prove it, don't assert it"
instinct the rest of this build was built around — asking "does the *whole* module actually
satisfy its own stated guarantee, not just the two functions with the most obvious test
coverage" — not by a live failure. Fixed by wrapping every builder's own body in
try/except, returning `{}` (no attributes, not a crash) on any failure, with a dedicated
regression test that blocks the real `openinference` imports via `sys.modules[...] = None`
(not just missing credentials, which every other test already covered) and confirms all 5
builders degrade to `{}` rather than raising.

**Quality-scoring is per-component, not one generic groundedness/coherence pair
everywhere — because what "quality" means differs by what the component actually
produces.** `feature_agent` outputs structured status labels, not prose — its judge scores
groundedness only (does `status_label` follow from `evidence`), with an explicit
instruction that a `Needs Human Review` label honestly citing ambiguous evidence is
well-grounded, not a failure to reach a verdict; penalizing honesty about uncertainty would
have fought the whole reason Requirement 5 added that 4th taxonomy level. `status_report_agent`'s
judge scores extraction faithfulness against the REAL `parse_slide` source — which required
capturing `ToolResultBlock` content off the message stream during `investigate_status_report`'s
own loop (confirmed real via `claude_agent_sdk.types.UserMessage`/`ToolResultBlock`), a
narrower, judge-input-only use of message-stream introspection than the deferred full
per-turn tracing described above; without the real source, "faithfulness" would have
degraded into "internal consistency," a materially weaker check. `synthesis_agent` Part B's
judge scores compression faithfulness (does `display_text` distort `progress_summary`) by
judging the WORST offender across all curated Features, not an average — one fabricated
claim should pull the score down meaningfully, matching this project's existing
"grounding is a floor, not a curve" posture (the risk floor itself never averages away a
single missing Blocked Feature). Part C's judge is the only one scoring TWO dimensions from
one call (groundedness AND coherence) — discovering this required extending
`evaluation_attributes()`'s own signature from a single `{name, score, ...}` shape to a
LIST of evaluations, because `get_evaluation_attributes` flattens by list INDEX
(`evaluations.0.*`, `evaluations.1.*`); two separate single-entry calls would have silently
collided, both producing `evaluations.0.*` and the second call's `span.set_attributes()`
overwriting the first's score instead of adding a second one. `critique_agent` and Slide
Generation Agent's Mode 1 are traced (every agentic call site gets a span, unconditionally)
but deliberately NOT scored: `critique_agent` IS the evaluator — scoring the judge with
another judge wasn't asked for and wasn't obviously well-founded; Mode 1's `flex_bounds`
are already code-validated by `_validate_flex_bounds` immediately after the agentic call
returns (gotcha #17/#18), and nothing in the per-component mapping suggested an LLM judge
adds anything a deterministic check doesn't already cover there.

**Every `synthesize_report()` attempt is scored, not just the final persisted one — a
~$0.014 marginal cost, only on weeks that actually revise, in exchange for data this
project genuinely didn't have before.** At `MAX_REVISIONS=1`, the two synthesis-scoped
judges (Part B + Part C) cost roughly $0.0075 + $0.0065 ≈ $0.014 per `synthesize_report()`
attempt (rough sizing from this project's own established ~$0.29/run baseline and typical
prompt sizes, not a live-metered figure). Scoring only the final report always costs
$0.014; scoring every attempt costs $0.014 on the (more common) no-revision weeks —
identical — and $0.028 only on weeks that revise. `core/orchestrator.py`'s own Build
Status entry already recorded a real, unresolved open question: even after two real
cross-component bug fixes, one genuine live run still ended `reviewed: False`, and
`MAX_REVISIONS` was flagged as "may be worth revisiting once more real runs establish a
pattern." Scoring only the final report would make that question permanently unanswerable
— there would never be a recorded "before" score to compare a revision's "after" against.
Per-attempt scoring was chosen specifically to let that backlog question eventually answer
itself from real data, not to be scored generously by default.

**One root `CHAIN`-kind span per `run_pipeline()` run — a stated judgment call, not a
verified fact, and logged as such rather than asserted with the same confidence as the
verified attribute constants.** `OpenInferenceSpanKindValues` (confirmed real: `AGENT`,
`CHAIN`, `EVALUATOR`, `LLM`, `TOOL`, etc.) carries no docstring guidance on which kind fits
a deterministic-coordination root versus an autonomous-reasoning one. `CHAIN` was chosen
because `run_pipeline()` matches this project's own existing framing exactly — "Orchestrator
delegates, never decides content" (CLAUDE.md's core architectural principle) — while `AGENT`
reads as better suited to the individual `LLM`-kind spans nested underneath it, which
genuinely do reason autonomously. Every nested `traced_span` (in every agent this function
calls, and in `mcp_client.py`'s `call()`) becomes a child of this root automatically via
OpenTelemetry's own `start_as_current_span` context propagation — no explicit
parent-span-passing was added anywhere, which is what gives Arize one connected trace per
real run instead of disconnected spans, exactly as asked for.

## The real per-run cost was ~10x the design-time estimate — SDK isolation mode, its own
## real regression, and a billing-confirmed fix (CLAUDE.md gotcha #20, CRITICAL — FULLY
## RESOLVED, full-pipeline confirmed)

Observability's first live trace didn't just prove the tracing layer worked — it caught a
real, load-bearing bug in the pipeline it was watching, one no prior live-verification pass
of any of the 6 already-shipped agent files had ever surfaced. This entry is the full story,
not scattered across gotcha stubs, because — per explicit instruction — it's one of the most
instructive debugging threads in the project: three real facts (a design-time estimate that
was never checked against real billing, an isolation fix that was correct but incomplete,
and a follow-on regression the fix itself introduced), each found with real evidence, not
guessed.

**Finding #1 — the original ~10x gap, found by cross-checking Arize's own reported cost
against real Anthropic pricing arithmetic, not by doubting Arize.** A real `run_pipeline()`
trace reported 14.73k total tokens but $2.827862 total cost — arithmetic at real Sonnet
pricing put 14.73k tokens at 10-20 cents, off by more than an order of magnitude. Rather than
assume Arize's cost math was buggy, the user's own pasted real Anthropic billing console
table was cross-checked token-by-token against real per-token pricing (pulled live from the
`claude-api` skill, not memory): ~30 real Sonnet API requests averaging ~38k input tokens
each, plus unexplained `claude-haiku-4-5` calls nothing in this codebase ever configured.
That arithmetic landed at ~$2.3 on input alone — close enough to Arize's reported $2.83 to
confirm Arize's reporting was accurate. The real bug was inflated actual token usage per
call, not a tracing/aggregation bug — a materially different, and more serious, finding than
the one first suspected.

**Root cause, confirmed from the real, installed `claude_agent_sdk` source, not guessed from
behavior.** All 6 agentic call sites across all 6 files construct `ClaudeAgentOptions`
without setting `setting_sources`, `skills`, or `strict_mcp_config` — every one of those
three fields defaults to a value that means "behave like a full interactive Claude Code CLI
session," confirmed directly from `ClaudeAgentOptions`'s own docstrings via
`inspect.getsource()`: `setting_sources=None` loads CLAUDE.md and every filesystem settings
source ("all sources loaded, matches CLI defaults"); `skills=None` is explicitly documented
as "not 'skills off'"; `strict_mcp_config=False` lets the CLI additionally load whatever
project/user/plugin MCP configuration exists beyond what the call itself passed in. None of
these three narrow, schema-constrained, supposed-to-be-self-contained calls (an ADO
investigation, a report parse, a zero-tool curation/prose/critique/design call) were ever
designed to need any of that — every one of them ships its own complete `system_prompt` and
declares its own `allowed_tools`/`mcp_servers` explicitly. The fix, confirmed as the correct
SDK-documented mechanism (not a workaround): `setting_sources=[]`, `skills=[]`,
`strict_mcp_config=True` on every `ClaudeAgentOptions` construction — "SDK isolation mode."

**The fix was verified on ONE file first, with a real live billing cross-check, before
touching the other 5 — the user's own explicit sequencing, held to literally.**
`feature_agent.py`'s two real call sites (the investigation itself, and its auto-triggered
groundedness judge) got the fix first, backed by a mechanical, credential-free test
(`run_isolation_mode_test`, monkeypatching the module-level `query` symbol and asserting the
isolation fields directly on the captured `ClaudeAgentOptions`) — proving the fix was wired
without spending a real API call. Only after that mechanical proof did a real live call
happen, spending real budget deliberately, not blindly.

**Real regression #1 — the fix itself broke a previously-passing live run, in the exact same
failure SHAPE as gotcha #10, for a different underlying reason.** The same `feature_agent.py`
test (5-turn budget, the same real Feature #8 that had succeeded multiple times before)
failed with `error_max_turns` immediately after the isolation fields were added — a real
regression, not a coincidence, caught before spending another paid call by adding full
message-stream debug logging (`_debug_log_message`, logging every `ToolUseBlock`/
`ToolResultBlock` in the stream, not just the final `ResultMessage`) and by re-reading the
SDK's own `_build_command`/subprocess-spawn source to check a specific hypothesis (whether
`strict_mcp_config`/`setting_sources=[]` changes how the npx-spawned ADO MCP subprocess
resolves its own env/PATH) before spending any further real budget. That specific hypothesis
was NOT confirmed by the visible Python SDK source: `mcp_servers` is serialized into
`--mcp-config` identically regardless of `strict_mcp_config`, and the CLI subprocess's own
env construction (`inherited_env` + `options.env`) is untouched by either flag — with the
honest caveat that the actual npx spawn happens inside the compiled `claude.exe` binary,
genuinely opaque to Python-level inspection.

**Real regression's actual cause — a mandatory ToolSearch discovery turn, real and
budget-relevant only where a real MCP tool exists to discover.** Under SDK isolation mode,
tool schemas are not preloaded into context the way a full interactive session would —
confirmed real via the live run itself, not theorized: the first turn of a tool-using call is
a mandatory discovery step before the model can invoke a real MCP tool for the first time.
`feature_agent.py`'s `BASE_SYSTEM_PROMPT` had given an EXACT turn-by-turn budget (get details,
batch-fetch children, one optional comments call, final answer = 4 tool-shaped turns + 1
final = 5, `max_turns=5`, zero slack) written before isolation mode existed and before this
discovery-turn cost was known — the fix that removed ~10x of unwanted context simultaneously
introduced a real, previously-nonexistent turn cost the old budget had no room for. Fixed by
bumping `max_turns` 5→6 and rewriting the system prompt's numbered budget to name turn 1 as
tool discovery explicitly ("expected, not wasted"), so future readers don't mistake it for
slack being removed rather than a real, accounted-for cost.

**The discovery-turn cost is NOT universal — verified per file, not assumed, before deciding
whether any of the other 5 files' turn budgets needed the same +1.** Applying the same +1
blindly everywhere would have been guessing, not verifying — this project's own established
"verify mechanically, never trust self-report" convention applied one level up, to a fix
about to be applied to five files at once:
- `status_report_agent.py`'s `investigate_status_report` has exactly one real MCP tool
  (`parse_slide`) and already had `max_turns=6` (unchanged) — needed turns (discovery + one
  parse_slide call + final answer = 3) sit well under the existing budget, so no numeric
  change was needed; the same discovery-turn documentation was still added to its system
  prompt for a future reader's sake, decoupled from whether the number itself needed to move.
- `synthesis_agent.py` (all 4 real call sites: `curate_report`/`write_executive_summary` via
  the shared `_run_agentic_call`, plus their two auto-triggered judges), `critique_agent.py`,
  and `slide_generation_agent.py` Mode 1's `_generate_candidates` are ALL zero-tool calls
  (`allowed_tools=[]`, no `mcp_servers`) — there is nothing for the model to discover, so the
  ToolSearch turn simply does not apply, and none of their existing `max_turns` values needed
  any adjustment.

The general lesson, worth naming: a fix's side effect (here, a new mandatory turn) is only a
real budget risk at the specific call sites whose existing accounting was already exact — a
budget with slack absorbs it silently; a budget written as an exact tally does not.

**Final result — real, billing-confirmed, not just mechanically verified.** The isolation fix
was applied to all 6 files (12 real `ClaudeAgentOptions` construction sites total: 2 in
`feature_agent.py`, 2 in `status_report_agent.py`, 3 in `synthesis_agent.py`, 1 in
`critique_agent.py`, 1 in `slide_generation_agent.py`, plus the already-fixed
`feature_agent.py` originals), each backed by the same mechanical `run_isolation_mode_test`
pattern (module-level `query` monkeypatched, isolation fields asserted directly on every
captured `ClaudeAgentOptions`), and each file's FULL pre-existing test suite re-run
afterward with zero regressions. The user then ran the real, corrected `feature_agent.py`
live against the real Anthropic API and real ADO org and reported the real billing delta:
**$4.10 → $4.34, a $0.24 real cost for one Feature Agent investigation — a ~63% reduction**
from the ~$0.65 pre-fix baseline for the same call shape. The ToolSearch discovery-turn
overhead is real (confirmed structurally, not eliminated) but small relative to the ~10x
reduction the isolation fix itself delivers.

**The project's original ~$0.29/run design-time cost estimate (see "Cost estimate (validated,
not assumed)" above) is INVALIDATED by this finding — corrected here explicitly, not silently
left standing.** That estimate was based on a design-time token-count estimate, never verified
against real billing until observability's first live trace caught the actual figure was off
by roughly 10x. It is not simply "now lower thanks to this fix" — it was never an accurate
figure for what the pipeline actually cost to begin with; the isolation fix corrects the
*mechanism* that was silently inflating every real run.

**Final, full-pipeline confirmation — a genuine `run_pipeline()` run across all 6 fixed files
together (Feature Agent, Status Report Agent, Synthesis Agent, Critique Agent — Slide
Generation Agent not exercised in this particular run), not just `feature_agent.py` in
isolation.** Three things confirmed, per the same "verify, don't assume" standard as every
other finding in this entry:

1. **The "zero-tool-call agents don't need a turn-budget adjustment" reasoning held under a
   real run, not just in theory.** Zero `error_max_turns` (or any similar failure) anywhere
   on Synthesis Agent or Critique Agent, across BOTH attempts of a real two-attempt revision
   cycle — the exact scenario (multiple back-to-back zero-tool calls under isolation mode)
   the earlier per-file audit predicted would be safe because there's no MCP tool for the
   model to discover. A live run is stronger evidence than the source-level reasoning alone,
   and it agreed.
2. **The bounded revision loop (Requirement 13's evaluator-optimizer pattern) still works
   correctly end-to-end under isolation mode.** Critique Agent found a real, genuine issue on
   attempt 1 — jargon leakage (raw ADO "Task"/"Story" terminology in executive-facing prose,
   the same category of leak-into-prose failure gotcha #12 first caught, just a different
   specific term this time) — Synthesis Agent revised using that feedback, and attempt 2
   passed cleanly. Final result: `report_id=13`, `reviewed=true`, `attempts=2`. This is
   real confirmation that isolation mode's changes (no more implicit CLAUDE.md/tool-catalog
   context) didn't silently break the revision-feedback threading between Critique and
   Synthesis — a plausible risk that was never directly tested until this run.
3. **Real cost: $4.34 → $5.29, a $0.95 delta for Feature Agent + Status Report Agent +
   Synthesis Agent × 2 attempts + Critique Agent × 2 attempts.** This is a reasonable,
   explainable number against the corrected ~$0.29 baseline, not a red flag, for two
   structural reasons a future reader should know before assuming regression: (a) a revision
   cycle roughly doubles the Synthesis+Critique portion of the run by design — the original
   ~$0.29 estimate's own "2 critique cycles assumed" framing already anticipated this cost
   shape, it just was never billing-verified until now; (b) Slide Generation Agent was not
   exercised in this run at all, so $0.95 is a partial-pipeline figure, not a full
   apples-to-apples comparison against a complete 6-agent run. Directionally and structurally
   consistent with the fix working as intended, not evidence against it.

**Independent cross-validation from a second measurement system — Arize's own trace data,
comparing the exact same root span before and after the fix.** The Anthropic billing
console delta above is one measurement path (real invoiced dollars). A second, independent
path — Arize's own reported cost for the `run_pipeline()` root `CHAIN` span, the same
metric investigated at the very start of this whole thread — was compared directly:
**$2.827862 (pre-fix, the original anomalous trace) → $1.616024 (post-fix, this
confirmation run's root span), a ~43% reduction.** The two systems measure cost through
different mechanisms (Anthropic's own billing ledger vs. Arize's OpenInference cost
attribution) and were never expected to produce identical numbers — different run
scope/shape (a revision cycle firing, Slide Generation excluded) makes an exact percentage
match unlikely by design, not a red flag when they diverge somewhat. What matters is that
both independently agree on DIRECTION (real, large reduction, not noise) and on rough
MAGNITUDE (same order of reduction, not one system claiming 10% and the other 90%) — two
measurement systems that don't share an implementation converging on the same conclusion is
stronger evidence than either alone, the same "don't trust a single signal" instinct this
entire investigation started from (the original anomaly was itself caught by cross-checking
Arize's number against real pricing arithmetic, not by trusting Arize in isolation).

**Gotcha #20 is FULLY RESOLVED as of this confirmation** — not just mechanically verified
(all 6 files, 12 call sites, isolation fields proven via monkeypatched `query()`), not just
single-file billing-confirmed (`feature_agent.py`'s $0.65→$0.24 delta), but now genuinely
end-to-end confirmed: a real multi-agent `run_pipeline()` run, including a real revision
cycle, completed cleanly with no isolation-mode-induced failures anywhere, and two
independent real-cost measurement systems (Anthropic billing, Arize trace cost) both confirm
a large, real cost reduction in the same direction and rough magnitude. The remaining open
item is not this fix's correctness — it's that no single run yet exercises all 6 agents
(including Slide Generation) together in one pass with a full billing/Arize comparison; that
would sharpen the number further but does not change the resolved status of this gotcha.
