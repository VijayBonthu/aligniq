-- Migration 011: Pipeline Runs
-- Tracks asynchronous executions of the 9-agent full pipeline so the UI can
-- show per-stage progress and so a refresh / multi-user run does not lose state.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id            VARCHAR(255) PRIMARY KEY,
    chat_history_id   VARCHAR(255) NOT NULL UNIQUE
                       REFERENCES chat_history(chat_history_id) ON DELETE CASCADE,
    user_id           VARCHAR(255) NOT NULL,

    -- Lifecycle: queued | running | completed | failed | cancelled
    status            VARCHAR(20)  NOT NULL,

    -- Currently executing node (e.g. 'ambiguity_resolver'); NULL when not running
    current_stage     VARCHAR(64),

    -- Append-only history: [{stage, started_at, completed_at, duration_ms}, ...]
    stages_completed  JSONB        NOT NULL DEFAULT '[]'::jsonb,

    -- Critic feedback loop counter (max 3 in workflow_graph.py)
    loop_count        INTEGER      NOT NULL DEFAULT 0,

    -- Populated when status = 'failed'
    error             TEXT,

    started_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_user   ON pipeline_runs(user_id);

COMMENT ON TABLE  pipeline_runs IS 'Async runs of the 9-agent full pipeline. One in-flight run per chat_history.';
COMMENT ON COLUMN pipeline_runs.status           IS 'queued | running | completed | failed | cancelled';
COMMENT ON COLUMN pipeline_runs.current_stage    IS 'Name of the currently executing agent node';
COMMENT ON COLUMN pipeline_runs.stages_completed IS 'Append-only list of completed stages with timings';
