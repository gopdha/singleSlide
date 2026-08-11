---
project_id: singleslide
report_file_glob: '*.pptx'
---

## Project-specific report-parsing notes

The one sample pulled during onboarding (a report from team lead Priya
Nair) used exactly the default section header phrasing `ppt_mcp` already
recognizes — Accomplishments, Planned Next Steps, Risks, Help Needed — with
`parse_confidence: 1.0` and no `missing_sections`. Nothing unusual to
compensate for here yet; if a future lead's deck comes back with
`missing_sections` non-empty or a lower confidence, that's a parser-keyword
gap to fix in `mcp_servers/ppt_mcp/server.py`, not something to paper over
in this agent's judgment.

### Tables vs. narrative sections
This sample's deck also carried a raw `Task/Status` table ("Load testing
setup — Not started", "Vendor sandbox escalation — In progress") separate
from the parsed prose sections. Both rows restate things already said in
narrative form (Planned Next Steps mentions load testing; Risks mentions
the vendor sandbox). Don't treat the table as a second, independent source
of facts — cross-check it against the narrative sections first and only
pull net-new information from it. Silently duplicating the same fact from
both the table and the prose into a Feature update is exactly the kind of
redundant-text problem cross-source enrichment is supposed to avoid.

### Other Initiatives
The single sample didn't surface a clear example of an informally-named
initiative with no ADO counterpart, so there's no team-specific naming
convention to record yet (e.g. no nicknames observed). Default to
topic-based judgment rather than exact-string matching until more reports
establish a pattern.

### Matching against existing Features
As on other projects, the existing-Features list is titles only. In this
sample, prose like "dashboard aggregation service" and "ADO connector
module" reads as plausible Feature-title matches by topic, not verbatim
string equality — keep `match_confidence` honest (`low` for topic-only
overlap) rather than inferring exact identity from a close-sounding phrase.

### Color cues
Priya's report used one colored shape (RGB `FFC000`, amber) positioned near
the vendor-sandbox risk mention. Read this the same way as the general
convention: supplementary context only. It never sets or overrides a
Feature's status label — status taxonomy (On Track/At Risk/Blocked/Needs
Human Review) is produced solely by Feature Agent's own ADO investigation,
and Other Initiatives don't carry a status label at all, regardless of any
color shape sitting next to them in the slide.

### Team lead attribution
`team_lead_id` was captured cleanly on this sample ("Priya Nair") — keep
passing it through untouched on every Other Initiative this agent emits,
since Synthesis Agent relies on that field to dedupe/merge overlapping
initiatives across multiple leads' reports.

No PM notes were given beyond this one sample, so treat the above as a
first pass — worth revisiting once reports from other team leads on this
project have been seen.
