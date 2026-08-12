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
