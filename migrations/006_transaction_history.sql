-- Migration 006: Transaction History for Undo/Redo Operations
-- This table tracks all reversible actions in chat-with-doc conversations

CREATE TABLE IF NOT EXISTS transaction_history (
    id VARCHAR(255) PRIMARY KEY,
    chat_history_id VARCHAR(255) NOT NULL REFERENCES chat_history(chat_history_id),

    -- Action details
    action_type VARCHAR(50) NOT NULL,
    action_description TEXT,
    action_data JSONB NOT NULL,

    -- Stack position (for ordering)
    sequence_number INTEGER NOT NULL,

    -- State tracking
    is_undone BOOLEAN NOT NULL DEFAULT FALSE,
    undone_at TIMESTAMP WITH TIME ZONE,
    redone_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_transaction_history_chat ON transaction_history(chat_history_id);
CREATE INDEX IF NOT EXISTS idx_transaction_history_sequence ON transaction_history(chat_history_id, sequence_number DESC);
CREATE INDEX IF NOT EXISTS idx_transaction_history_undone ON transaction_history(chat_history_id, is_undone);
