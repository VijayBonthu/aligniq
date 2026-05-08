-- Migration 013: LLM Call Log
-- Per-call telemetry for every ChatOpenAI invocation across the agentic and
-- presales pipelines plus chat paths. Powers /admin/llm-stats and the B1
-- prompt-caching before/after comparison. cached_input_tokens is read from
-- AIMessage.usage_metadata.input_token_details.cache_read.

CREATE TABLE IF NOT EXISTS llm_call_log (
    id                   BIGSERIAL PRIMARY KEY,
    chat_history_id      VARCHAR(255)
                          REFERENCES chat_history(chat_history_id) ON DELETE SET NULL,
    pipeline_run_id      VARCHAR(255)
                          REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    user_id              VARCHAR(255),

    agent_name           VARCHAR(64)  NOT NULL,
    model                VARCHAR(64)  NOT NULL,

    -- sha256 hex of the static system-prefix; segments metrics across prompt
    -- versions so a prompt edit doesn't silently corrupt before/after compares.
    prompt_hash          VARCHAR(64),

    input_tokens         INTEGER      NOT NULL DEFAULT 0,
    cached_input_tokens  INTEGER      NOT NULL DEFAULT 0,
    output_tokens        INTEGER      NOT NULL DEFAULT 0,
    latency_ms           INTEGER      NOT NULL DEFAULT 0,
    cost_usd             DOUBLE PRECISION NOT NULL DEFAULT 0,

    created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_call_log_pipeline   ON llm_call_log(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_llm_call_log_chat       ON llm_call_log(chat_history_id);
CREATE INDEX IF NOT EXISTS idx_llm_call_log_created    ON llm_call_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_call_log_agent_time ON llm_call_log(agent_name, created_at DESC);

COMMENT ON TABLE  llm_call_log IS 'Per-call LLM telemetry: tokens, cache hits, cost. Drives /admin/llm-stats.';
COMMENT ON COLUMN llm_call_log.cached_input_tokens IS 'Subset of input_tokens served from OpenAI prompt cache (50% discount on 4o-mini).';
COMMENT ON COLUMN llm_call_log.prompt_hash         IS 'sha256 of the static system message prefix; lets us segment metrics across prompt versions.';
