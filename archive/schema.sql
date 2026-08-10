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
    rag_status         TEXT NOT NULL CHECK (rag_status IN ('Red', 'Amber', 'Green')),
    executive_summary  TEXT NOT NULL,
    curated_features    JSONB NOT NULL,    -- final Feature Status slide content (ordered,
                                            -- possibly flex-bound-condensed display text)
    curated_initiatives JSONB NOT NULL,    -- same idea for Initiative Status slide
    pm_approved_at     TIMESTAMPTZ,        -- NULL = pending Review Gate; reset to NULL
                                            -- whenever this (project_id, week_of) is re-saved
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, week_of)
);

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
