---
project_id: ai-reports-demo
report_file_glob: "*.pptx"
---

## Project-specific report-parsing notes

Team leads on this project use the default section header phrasing that
`ppt_mcp`'s parser already recognizes out of the box (Accomplishments,
Planned Next Steps, Risks, Help Needed) — no unusual synonyms in use here.
If that ever changes, extend `SECTION_KEYWORDS` in
`mcp_servers/ppt_mcp/server.py` first; this skill governs how the *agent*
interprets the parsed sections, not what counts as a section header in the
first place.

### Other Initiatives
Team leads on this project often describe informal initiatives by a short
nickname ("the vendor migration", "the Q3 cleanup") rather than a formal
title — don't expect an exact string match against anything. Judge by
topic, not by exact wording.

### Matching against existing Features
The existing-Features list provided in your instructions is titles only, no
description — semantic/topic matching against report prose is inherently
fuzzy here (a known, accepted limitation of the system, not something this
skill can fully solve). When a report mentions something that plausibly
relates to an existing Feature only by general topic overlap (not a clear,
explicit reference), mark `match_confidence: "low"` rather than guessing
"high" — a PM reviewing potential enrichments needs to know which matches
are solid and which are speculative.

### Color cues
This project's leads occasionally use a colored status shape near an
initiative or risk mention as an informal RAG indicator. Treat it as
supplementary color context only — never as the basis for a status label
(Other Initiatives don't get one) and never as grounds to assume something
is or isn't already covered in ADO.
