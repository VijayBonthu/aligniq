-- Migration: Add is_default column to report_version table
-- Description: Allows users to mark a specific version as the default/recommended version
-- Date: 2026-02-17

-- Add is_default column to report_version table
ALTER TABLE report_version ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_report_version_is_default ON report_version(is_default);

-- Set the latest version for each chat_history_id as default for existing records
-- This ensures existing data has a sensible default
WITH latest_versions AS (
    SELECT DISTINCT ON (chat_history_id) report_version_id
    FROM report_version
    ORDER BY chat_history_id, version_number DESC
)
UPDATE report_version
SET is_default = TRUE
WHERE report_version_id IN (SELECT report_version_id FROM latest_versions);

-- Verify the migration
-- SELECT chat_history_id, version_number, is_default
-- FROM report_version
-- ORDER BY chat_history_id, version_number;
