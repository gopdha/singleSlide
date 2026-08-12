---
project_id: singleslide
---

## Rubric — skill-defined criteria only

You are NOT re-checking the risk floor or whether critical Features are named in the
summary — that's already verified in code and given to you as context. Judge only:

### 1. Tone matches RAG severity
Red: real urgency without alarmism, name the specific blocker. Amber: name the
specific risk(s), not vague "some concerns." Green: confident and brief is fine, but
don't overstate certainty, and don't let Needs Human Review items get glossed over
just because the week is otherwise Green.

### 2. Conciseness — no filler
Flag phrases like "I'm pleased to report", "I'm happy to announce", "Please note
that", "It is important to mention", "Moving forward", "As you may be aware."

### 3. trend_line is meaningful, not generic
Name the specific Feature/Initiative that changed and how — not "status improved."
An empty trend_line is CORRECT, not a failure, when prior_week is null.

### 4. No jargon or ticket-number bleed
No internal field names, work item IDs, or ADO terminology in the prose — the reader
is an executive.

### 5. Leads with the headline
First sentence or two should convey overall status and the biggest risk, not build
up to it through preamble.

## When in doubt
A genuinely borderline check should fail with specific, actionable feedback — a
revision loop needs direction, not a guess dressed up as leniency.

No PM notes have been given beyond this baseline rubric yet — hand-authored to
unblock the first real `run_pipeline()` run for this project (see
docs/BACKLOG.md's new entry on `discovery_agent`'s incomplete scope), not
generated through a real onboarding conversation. Revisit once real usage
surfaces anything singleslide-specific worth capturing here.
