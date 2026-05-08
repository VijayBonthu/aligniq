-- Migration 014: Add presales_id to llm_call_log
-- Lets a single project (presales scan + presales brief + full pipeline +
-- chat-with-doc) be summed end-to-end. presales_id is created at /upload
-- before any chat_history_id exists; one presales_id can link to multiple
-- chat_history_ids via analysis_link (presales brief + full report).

ALTER TABLE llm_call_log
    ADD COLUMN IF NOT EXISTS presales_id VARCHAR(255)
        REFERENCES presales_analysis(presales_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_llm_call_log_presales ON llm_call_log(presales_id);

COMMENT ON COLUMN llm_call_log.presales_id IS
    'Project identifier — created at /upload before chat_history_id. Use this to roll up cost across all flows for one project.';
