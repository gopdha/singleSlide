---
project_id: ai-reports-demo
entry_criteria:
  work_item_type: Feature
  filter_field: Tags
  filter_operator: CONTAINS
  filter_value: Committed
hierarchy:
  root_type: Feature
  child_types:
    - Story
    - Bug
  child_relation: Child
fields:
  story_points_field: Microsoft.VSTS.Scheduling.StoryPoints
---

## Project-specific investigation notes

This project uses the standard Agile process template. Story Points are
tracked on both Stories and Bugs (not just Stories) — include Bug children
in your story-point calculations, not just Stories.

No unusual field names or hierarchy quirks in this project — standard
Feature -> Story/Bug parent-child structure via the "Child" relation type.

Comments in this project's ADO instance are generally terse; don't expect
long discussions. A one-line comment like "blocked, waiting on vendor" is
the norm, not a red flag about comment quality — treat short comments as
equally valid evidence as long ones.
