-- Migration: Add Pre-Sales Workflow Tables
-- Created: 2024
-- Description: Adds tables for pre-sales analysis, technology risks capture, and analysis linking

-- ============================================================================
-- TABLE: presales_analysis
-- Stores the fast pre-sales scan results (60-120 seconds)
-- ============================================================================
CREATE TABLE IF NOT EXISTS presales_analysis (
    presales_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    document_id VARCHAR NOT NULL REFERENCES user_documents(document_id) ON DELETE CASCADE,
    user_id VARCHAR NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    -- Analysis outputs (JSON)
    extracted_requirements JSONB,      -- From scanner agent
    blind_spots JSONB,                 -- From blind spot detector
    technology_risks JSONB,            -- Tech risks identified by LLM
    kickstart_questions JSONB,         -- Critical questions for client

    -- Final brief (markdown)
    presales_brief TEXT,

    -- Metadata
    status VARCHAR(50) NOT NULL DEFAULT 'processing',  -- processing, completed, failed
    model_used VARCHAR(100),                           -- e.g., "gpt-4o-mini"
    processing_time_seconds INTEGER,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for presales_analysis
CREATE INDEX IF NOT EXISTS idx_presales_document_id ON presales_analysis(document_id);
CREATE INDEX IF NOT EXISTS idx_presales_user_id ON presales_analysis(user_id);
CREATE INDEX IF NOT EXISTS idx_presales_status ON presales_analysis(status);
CREATE INDEX IF NOT EXISTS idx_presales_created_at ON presales_analysis(created_at);

-- ============================================================================
-- TABLE: raised_technology_risks
-- Passively captures technology risks raised by LLM for future analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS raised_technology_risks (
    risk_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    presales_id VARCHAR NOT NULL REFERENCES presales_analysis(presales_id) ON DELETE CASCADE,
    document_id VARCHAR NOT NULL REFERENCES user_documents(document_id) ON DELETE CASCADE,
    user_id VARCHAR NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    -- Risk details
    technologies JSONB,                -- ["Power BI", "iframe", "API"]
    risk_title VARCHAR(500) NOT NULL,  -- Short title
    risk_description TEXT,             -- Full description
    severity VARCHAR(50),              -- critical, high, medium, low
    category VARCHAR(100),             -- integration, performance, security, etc.

    -- Optional feedback (SA can mark if risk was actually relevant)
    was_relevant BOOLEAN,              -- True = real issue, False = not applicable
    user_feedback TEXT,                -- Notes from SA/user

    -- Metadata
    model_used VARCHAR(100),           -- Model that raised this risk
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for raised_technology_risks
CREATE INDEX IF NOT EXISTS idx_risks_presales_id ON raised_technology_risks(presales_id);
CREATE INDEX IF NOT EXISTS idx_risks_document_id ON raised_technology_risks(document_id);
CREATE INDEX IF NOT EXISTS idx_risks_user_id ON raised_technology_risks(user_id);
CREATE INDEX IF NOT EXISTS idx_risks_severity ON raised_technology_risks(severity);
CREATE INDEX IF NOT EXISTS idx_risks_category ON raised_technology_risks(category);
CREATE INDEX IF NOT EXISTS idx_risks_was_relevant ON raised_technology_risks(was_relevant);

-- ============================================================================
-- TABLE: analysis_links
-- Links pre-sales analysis to full report generation
-- ============================================================================
CREATE TABLE IF NOT EXISTS analysis_links (
    link_id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid()::text,
    document_id VARCHAR NOT NULL REFERENCES user_documents(document_id) ON DELETE CASCADE,
    user_id VARCHAR NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

    -- Links to both analysis types
    presales_id VARCHAR REFERENCES presales_analysis(presales_id) ON DELETE SET NULL,
    chat_history_id VARCHAR REFERENCES chat_history(chat_history_id) ON DELETE SET NULL,

    -- User answers to kickstart questions (if provided before full report)
    user_answers JSONB,

    -- Tracking flags
    full_report_requested BOOLEAN DEFAULT FALSE,
    full_report_generated BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for analysis_links
CREATE INDEX IF NOT EXISTS idx_links_document_id ON analysis_links(document_id);
CREATE INDEX IF NOT EXISTS idx_links_user_id ON analysis_links(user_id);
CREATE INDEX IF NOT EXISTS idx_links_presales_id ON analysis_links(presales_id);
CREATE INDEX IF NOT EXISTS idx_links_chat_history_id ON analysis_links(chat_history_id);

-- ============================================================================
-- COMMENTS for documentation
-- ============================================================================
COMMENT ON TABLE presales_analysis IS 'Stores fast pre-sales scan results (60-120 sec) with requirements, risks, and brief';
COMMENT ON TABLE raised_technology_risks IS 'Passively captures LLM-raised technology risks for future analysis and model improvement';
COMMENT ON TABLE analysis_links IS 'Links pre-sales analysis to full report, tracking the analysis journey';

COMMENT ON COLUMN presales_analysis.extracted_requirements IS 'JSON output from scanner agent - project summary, technologies, integrations, scope';
COMMENT ON COLUMN presales_analysis.blind_spots IS 'JSON output from blindspot detector - underestimations, critical unknowns, red flags';
COMMENT ON COLUMN presales_analysis.technology_risks IS 'Array of technology risks identified by LLM based on its training data';
COMMENT ON COLUMN presales_analysis.kickstart_questions IS 'Critical questions that must be answered before scoping';
COMMENT ON COLUMN presales_analysis.presales_brief IS 'Final markdown brief document for pre-sales use';

COMMENT ON COLUMN raised_technology_risks.was_relevant IS 'Feedback: TRUE if risk was real, FALSE if not applicable (for model improvement)';
COMMENT ON COLUMN raised_technology_risks.user_feedback IS 'Optional notes from SA explaining why risk was/wasn''t relevant';

COMMENT ON COLUMN analysis_links.user_answers IS 'JSON of user-provided answers to kickstart questions before full report';
COMMENT ON COLUMN analysis_links.full_report_requested IS 'TRUE when user clicks "Generate Full Report"';
COMMENT ON COLUMN analysis_links.full_report_generated IS 'TRUE when full report pipeline completes successfully';
