-- Migration: Add pending_actions table for conversation state management
-- This replaces fragile string-based pending action extraction with explicit state tracking

CREATE TABLE IF NOT EXISTS pending_actions (
    id VARCHAR(50) PRIMARY KEY,  -- Format: PA-001, PA-002, etc.
    chat_history_id VARCHAR(255) NOT NULL,
    action_type VARCHAR(50) NOT NULL,  -- 'suggestion', 'rollback', 'clear_all', 'confirmation_request'
    content TEXT NOT NULL,  -- What the action does (e.g., "Use PostgreSQL instead of MongoDB")
    context TEXT,  -- Why this was offered (e.g., "User asked about database options")
    category VARCHAR(50),  -- 'modify_architecture', 'modify_requirements', 'correct_assumptions'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    awaiting_response BOOLEAN DEFAULT TRUE,
    resolved_at TIMESTAMP,
    resolution VARCHAR(50),  -- 'confirmed', 'declined', 'expired', 'superseded'
    resolution_message TEXT,  -- Any conditions or notes from resolution

    -- Foreign key to chat_history
    CONSTRAINT fk_pending_actions_chat_history
        FOREIGN KEY (chat_history_id)
        REFERENCES chat_history(chat_history_id)
        ON DELETE CASCADE
);

-- Index for fast lookups by chat_history_id and awaiting_response
CREATE INDEX IF NOT EXISTS idx_pending_actions_chat_awaiting
    ON pending_actions(chat_history_id, awaiting_response);

-- Index for cleanup of old resolved actions
CREATE INDEX IF NOT EXISTS idx_pending_actions_resolved_at
    ON pending_actions(resolved_at);

-- Add comment for documentation
COMMENT ON TABLE pending_actions IS 'Tracks pending actions awaiting user confirmation in chat conversations. Replaces fragile string-based extraction.';
COMMENT ON COLUMN pending_actions.action_type IS 'Type of pending action: suggestion, rollback, clear_all, confirmation_request';
COMMENT ON COLUMN pending_actions.category IS 'Change category: modify_architecture, modify_requirements, correct_assumptions';
COMMENT ON COLUMN pending_actions.resolution IS 'How the action was resolved: confirmed, declined, expired, superseded';
