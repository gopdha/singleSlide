---
project_id: singleslide
entry_criteria:
  work_item_type: feature
  filter_field: Tags
  filter_operator: CONTAINS
  filter_value: Committed
hierarchy:
  root_type: feature
  child_types:
  - story
  child_relation: child
fields:
  story_points_field: Microsoft.VSTS.Scheduling.StoryPoints
---

## Project-specific investigation notes

Entry criteria for this project: **Feature** work items whose **Tags** field
contains "Committed" (substring match, not exact-equals — a Feature tagged
"Committed, Q3" still qualifies). Don't filter on PI or State here; Tags is
the only gate. `Build Agentic Dashboard` is a real example of a Feature that
matched this criteria during sampling — use it as a sanity check if you need
a reference for what a well-formed item in this project looks like.

Hierarchy is Feature -> Story only, via the standard "Child" relation type.
No Bug children were found under this project's Features during sampling —
don't go looking for a Bug child type here, and don't assume story points
live anywhere but Story items. If a future Feature does turn up with a
non-Story child, treat that as a genuine anomaly worth flagging (Needs
Human Review), not something to silently fold into the Story rollup.

Story Points live on the `Microsoft.VSTS.Scheduling.StoryPoints` field on
Story work items. When you hydrate child items via `get_batch`, pull this
field explicitly — it won't come back from the WIQL query itself (see the
shared gotcha about WIQL only returning IDs). Sum across all Story children
of a Feature for the Feature's total; there's no separate Bug-points source
to reconcile against in this project.

