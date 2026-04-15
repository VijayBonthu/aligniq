-- Migration 007: Add Changelog Tracking to Report Versions
-- Purpose: Store what changes were applied and a summary of implications for each version
-- This enables users to understand how requirements and architecture evolved over time

-- Add changes_applied column (stores the pending changes that created this version)
ALTER TABLE report_version ADD COLUMN IF NOT EXISTS changes_applied JSONB DEFAULT NULL;

-- Add changelog_summary column (LLM-generated explanation of changes and their implications)
ALTER TABLE report_version ADD COLUMN IF NOT EXISTS changelog_summary TEXT DEFAULT NULL;

-- Add parent_version_id for version lineage tracking
ALTER TABLE report_version ADD COLUMN IF NOT EXISTS parent_version_id VARCHAR(255) DEFAULT NULL;

-- Index for efficient changelog queries by parent version
CREATE INDEX IF NOT EXISTS idx_report_version_parent ON report_version(parent_version_id);

-- Note: Existing versions will have NULL for these fields
-- This is intentional - we cannot retroactively determine what changes created them
-- Version 1 is always "initial generation" and will be handled in application code
