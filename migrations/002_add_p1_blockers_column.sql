-- Migration: Add P1 Blockers column to presales_analysis
-- Created: 2026-01-27
-- Description: Adds p1_blockers JSON column to store P1 blockers with questions

-- ============================================================================
-- Add p1_blockers column to presales_analysis table
-- ============================================================================
ALTER TABLE presales_analysis
ADD COLUMN IF NOT EXISTS p1_blockers JSONB;

-- Add comment for documentation
COMMENT ON COLUMN presales_analysis.p1_blockers IS 'Array of P1 blockers with area, blocker description, why_it_matters, and question to ask';
