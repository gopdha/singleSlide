---
project_id: singleslide
layout_archetype: two_column_metrics_sidebar
palette:
  background: '#FFFFFF'
  text_primary: '#1F2937'
  text_secondary: '#5B6472'
  brand_primary: '#0B5FA5'
  green: '#2E8B57'
  amber: '#E0A030'
  red: '#D64545'
  needs_review: '#8A94A6'
fonts:
  heading_font: Calibri Light
  body_font: Segoe UI
  heading_size_pt: 20
  body_size_pt: 13
flex_bounds:
  font_size_pt_min: 8
  row_height_in_min: 0.05
  display_text_max_chars_default: 140
  display_text_max_chars_min: 80
---

## Design rationale

Renders into two_column_metrics_sidebar, where a left rail carries status chips/RAG rollup and a right column carries the content — this is the most 'operational dashboard' of the three, so it gets a crisp white background, a clean corporate blue brand color, and saturated-but-professional status colors that need to pop clearly against a narrow sidebar at a glance. Distinct from the editorial candidate's muted palette and from the banner candidate's high-contrast one. Row height floor (0.05in) sits between the other two, reflecting that sidebar rows are short status lines, not full sentences, but the right column still carries some narrative.

