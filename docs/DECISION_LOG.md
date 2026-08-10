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
