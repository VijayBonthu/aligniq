-- Migration 012: Index for period-based chat-limit enforcement
-- check_chat_limit (subscription.py) issues:
--   SELECT count(*) FROM chat_history
--    WHERE user_id = ? AND created_at >= <period_start>
-- on every billable request that creates a chat (POST /upload, POST /chat).
-- Without this index the query falls back to a scan over the user's lifetime
-- chats. The composite (user_id, created_at) index makes it an index-only
-- scan over a small per-user slice — sub-millisecond at any scale.

CREATE INDEX IF NOT EXISTS idx_chat_history_user_created
    ON chat_history (user_id, created_at);
