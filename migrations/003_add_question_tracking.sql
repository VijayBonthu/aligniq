-- Migration: Add Question Tracking System
-- Created: 2026-01-28
-- Description: Adds tables for tracking presales questions, answers, and analysis history

-- ============================================================================
-- Update presales_analysis table with new columns
-- ============================================================================
ALTER TABLE presales_analysis
ADD COLUMN IF NOT EXISTS iteration_count INTEGER DEFAULT 1;

ALTER TABLE presales_analysis
ADD COLUMN IF NOT EXISTS readiness_score FLOAT DEFAULT 0.0;

ALTER TABLE presales_analysis
ADD COLUMN IF NOT EXISTS readiness_status VARCHAR(50) DEFAULT 'not_analyzed';
-- Values: 'not_analyzed', 'needs_more_info', 'ready_with_assumptions', 'ready'

ALTER TABLE presales_analysis
ADD COLUMN IF NOT EXISTS assumptions_list JSONB DEFAULT '[]'::jsonb;

ALTER TABLE presales_analysis
ADD COLUMN IF NOT EXISTS contradictions_list JSONB DEFAULT '[]'::jsonb;

ALTER TABLE presales_analysis
ADD COLUMN IF NOT EXISTS vague_answers_list JSONB DEFAULT '[]'::jsonb;

-- Comments for new columns
COMMENT ON COLUMN presales_analysis.iteration_count IS 'Number of times analysis has been run (increments on re-analysis)';
COMMENT ON COLUMN presales_analysis.readiness_score IS 'Score from 0.0 to 1.0 indicating readiness for full report';
COMMENT ON COLUMN presales_analysis.readiness_status IS 'Status: not_analyzed, needs_more_info, ready_with_assumptions, ready';
COMMENT ON COLUMN presales_analysis.assumptions_list IS 'JSON array of assumptions that will be made in full report';
COMMENT ON COLUMN presales_analysis.contradictions_list IS 'JSON array of contradictions found in answers';
COMMENT ON COLUMN presales_analysis.vague_answers_list IS 'JSON array of vague answers needing clarification';

-- ============================================================================
-- TABLE: presales_questions
-- Tracks individual questions with state management
-- ============================================================================
CREATE TABLE IF NOT EXISTS presales_questions (
    question_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    presales_id VARCHAR NOT NULL REFERENCES presales_analysis(presales_id) ON DELETE CASCADE,
    user_id VARCHAR NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    -- Question identification
    question_type VARCHAR(20) NOT NULL,  -- 'p1_blocker' or 'kickstart'
    question_number VARCHAR(10) NOT NULL,  -- 'P1-1', 'P1-2', 'Q1', 'Q2', etc.
    display_order INTEGER NOT NULL DEFAULT 0,

    -- Question content (from blind spots analysis)
    area_or_category VARCHAR(100),  -- 'Integration', 'Security', 'data', etc.
    title VARCHAR(500),  -- Blocker title or main question text
    description TEXT,  -- why_it_matters (P1) or why_critical (kickstart)
    impact_description TEXT,  -- impact_if_unknown for kickstart questions
    question_text TEXT NOT NULL,  -- The actual question to ask the client

    -- Answer tracking
    answer TEXT,
    answer_quality VARCHAR(20),  -- 'good', 'vague', 'contradicting', null
    answer_feedback TEXT,  -- Feedback about the answer quality
    answered_at TIMESTAMP WITH TIME ZONE,
    answered_by VARCHAR,  -- user_id who answered

    -- State management
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: 'pending', 'answered', 'invalid', 'needs_review'

    -- Invalidation tracking
    invalidated_reason TEXT,
    invalidated_at TIMESTAMP WITH TIME ZONE,
    invalidated_by_question_id VARCHAR,  -- Which question's answer invalidated this

    -- Iteration tracking
    created_in_iteration INTEGER DEFAULT 1,
    invalidated_in_iteration INTEGER,
    restored_in_iteration INTEGER,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for presales_questions
CREATE INDEX IF NOT EXISTS idx_pq_presales_id ON presales_questions(presales_id);
CREATE INDEX IF NOT EXISTS idx_pq_user_id ON presales_questions(user_id);
CREATE INDEX IF NOT EXISTS idx_pq_status ON presales_questions(status);
CREATE INDEX IF NOT EXISTS idx_pq_question_type ON presales_questions(question_type);
CREATE INDEX IF NOT EXISTS idx_pq_display_order ON presales_questions(presales_id, display_order);

-- ============================================================================
-- TABLE: presales_answer_history
-- Audit trail for answer changes
-- ============================================================================
CREATE TABLE IF NOT EXISTS presales_answer_history (
    history_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    question_id VARCHAR NOT NULL REFERENCES presales_questions(question_id) ON DELETE CASCADE,
    presales_id VARCHAR NOT NULL REFERENCES presales_analysis(presales_id) ON DELETE CASCADE,

    -- Change tracking
    previous_answer TEXT,
    new_answer TEXT,
    change_type VARCHAR(20) NOT NULL,  -- 'created', 'updated', 'cleared'

    -- Metadata
    changed_by VARCHAR NOT NULL,  -- user_id
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    iteration_number INTEGER
);

-- Indexes for answer history
CREATE INDEX IF NOT EXISTS idx_ah_question_id ON presales_answer_history(question_id);
CREATE INDEX IF NOT EXISTS idx_ah_presales_id ON presales_answer_history(presales_id);
CREATE INDEX IF NOT EXISTS idx_ah_changed_at ON presales_answer_history(changed_at);

-- ============================================================================
-- TABLE: presales_analysis_history
-- Tracks each analysis run for audit/debugging
-- ============================================================================
CREATE TABLE IF NOT EXISTS presales_analysis_history (
    analysis_history_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    presales_id VARCHAR NOT NULL REFERENCES presales_analysis(presales_id) ON DELETE CASCADE,

    -- Analysis snapshot
    iteration_number INTEGER NOT NULL,
    readiness_score FLOAT,
    readiness_status VARCHAR(50),

    -- Analysis results
    assumptions_made JSONB,
    contradictions_found JSONB,
    vague_answers_found JSONB,
    questions_invalidated JSONB,  -- Array of question_ids that were invalidated
    questions_added JSONB,  -- Array of new questions added (if follow-up feature enabled)

    -- Input snapshot
    answers_snapshot JSONB,  -- Snapshot of all answers at time of analysis

    -- Metadata
    analyzed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    analyzed_by VARCHAR,  -- user_id who triggered analysis
    processing_time_ms INTEGER
);

-- Indexes for analysis history
CREATE INDEX IF NOT EXISTS idx_anlh_presales_id ON presales_analysis_history(presales_id);
CREATE INDEX IF NOT EXISTS idx_anlh_iteration ON presales_analysis_history(presales_id, iteration_number);

-- ============================================================================
-- COMMENTS for documentation
-- ============================================================================
COMMENT ON TABLE presales_questions IS 'Tracks individual P1 blockers and kickstart questions with answers and state';
COMMENT ON TABLE presales_answer_history IS 'Audit trail for all answer changes';
COMMENT ON TABLE presales_analysis_history IS 'History of each analysis run with snapshots';

COMMENT ON COLUMN presales_questions.status IS 'Question state: pending (no answer), answered (has answer), invalid (no longer relevant), needs_review (restored/flagged)';
COMMENT ON COLUMN presales_questions.answer_quality IS 'Quality assessment: good (clear answer), vague (needs clarification), contradicting (conflicts with other answers)';
COMMENT ON COLUMN presales_questions.invalidated_by_question_id IS 'If this question was invalidated because another question was answered, reference to that question';
