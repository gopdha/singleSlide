-- Archive persistence schema for SingleSlide, over Postgres (Neon-compatible).
-- Approved design — see docs/DECISION_LOG.md ("Archive schema design decisions"
-- and "Archive schema — additional confirmed design choices") for the reasoning
-- behind each constraint and the deliberate omissions (no template_id FK, no
-- pm_edits column yet).
--
-- Idempotent: every statement is IF NOT EXISTS, so migrate.py can be re-run
-- safely. No ALTER-based versioning yet — fine for a single-operator project
-- at this stage; revisit with a real migration tool if the schema needs to
-- evolve after real data exists.

CREATE TABLE IF NOT EXISTS projects (
    project_id    TEXT PRIMARY KEY,        -- caller-supplied, e.g. 'ai-reports-demo' —
                                            -- the same slug used under skills/<project_id>/,
                                            -- never derived/inferred here
    name          TEXT NOT NULL,
    input_config  JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS preference_profiles (
    profile_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  TEXT NOT NULL UNIQUE REFERENCES projects(project_id) ON DELETE CASCADE,
    profile     JSONB NOT NULL,            -- Discovery Agent's output; shape not fixed here —
                                            -- Discovery Agent doesn't exist yet
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    report_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id         TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    week_of            DATE NOT NULL,
    -- 'Unknown' added post-launch (see docs/DECISION_LOG.md, gotcha found during
    -- core/orchestrator.py's live verification): archive/ shipped before
    -- core/rag_rollup.py existed and added the 4th value; nothing caught the gap until
    -- a real pipeline run actually produced Unknown. See the standalone ALTER below for
    -- already-existing databases.
    rag_status         TEXT NOT NULL CHECK (rag_status IN ('Red', 'Amber', 'Green', 'Unknown')),
    executive_summary  TEXT NOT NULL,
    trend_line         TEXT NOT NULL DEFAULT '', -- Part C's short continuity callout vs.
                                            -- prior_week; '' when there was no prior_week to
                                            -- compare against (first report for the project)
    curated_features    JSONB NOT NULL,    -- final Feature Status slide content (ordered,
                                            -- possibly flex-bound-condensed display text)
    curated_initiatives JSONB NOT NULL,    -- same idea for Initiative Status slide
    pm_approved_at     TIMESTAMPTZ,        -- NULL = pending Review Gate; reset to NULL
                                            -- whenever this (project_id, week_of) is re-saved
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, week_of)
);

-- weekly_reports existed before trend_line was added (see docs/DECISION_LOG.md, "trend_line
-- storage resolution" under core/orchestrator.py) — CREATE TABLE IF NOT EXISTS above is a
-- no-op against an already-existing table, so the column is added explicitly here too.
-- Idempotent: safe to re-run against a fresh database where the table (and column) were
-- just created above.
ALTER TABLE weekly_reports ADD COLUMN IF NOT EXISTS trend_line TEXT NOT NULL DEFAULT '';

-- Same situation as trend_line above: the original CHECK constraint was written for
-- Requirement 10's literal 3-value rule, before rag_rollup.py's 'Unknown' existed.
-- Postgres has no "ADD CONSTRAINT IF NOT EXISTS" — DROP-then-ADD is the idempotent
-- equivalent (safe to re-run; ends in the same state either way). Constraint name is
-- Postgres's own auto-generated default (<table>_<column>_check) for an inline CHECK.
ALTER TABLE weekly_reports DROP CONSTRAINT IF EXISTS weekly_reports_rag_status_check;
ALTER TABLE weekly_reports ADD CONSTRAINT weekly_reports_rag_status_check
    CHECK (rag_status IN ('Red', 'Amber', 'Green', 'Unknown'));

CREATE TABLE IF NOT EXISTS feature_snapshots (
    snapshot_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_id          BIGINT NOT NULL REFERENCES weekly_reports(report_id) ON DELETE CASCADE,
    ado_feature_id     INTEGER NOT NULL,   -- feature_agent's feature_id (ADO work item ID)
    title              TEXT NOT NULL,
    short_description  TEXT NOT NULL,
    status_label       TEXT NOT NULL CHECK (status_label IN
                            ('On Track', 'At Risk', 'Blocked', 'Needs Human Review')),
    progress_summary   TEXT NOT NULL,
    risk               TEXT,               -- nullable, per FEATURE_SCHEMA
    evidence           TEXT[] NOT NULL,    -- flat string array, matches FEATURE_SCHEMA
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_id, ado_feature_id)
);

CREATE TABLE IF NOT EXISTS initiative_snapshots (
    snapshot_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_id          BIGINT NOT NULL REFERENCES weekly_reports(report_id) ON DELETE CASCADE,
    title              TEXT NOT NULL,          -- matches STATUS_REPORT_SCHEMA's
    narrative_summary  TEXT NOT NULL,          -- other_initiatives[].{title,
    evidence           TEXT[] NOT NULL,        -- narrative_summary, evidence} — still no status
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()  -- label column at all, by design
);
