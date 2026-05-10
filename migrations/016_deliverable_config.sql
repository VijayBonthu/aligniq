-- Migration 016: Deliverable Builder (A5) — per-project curation state
--
-- Adds three columns to report_version:
--   deliverable_config           — user's section include/exclude + custom additions + manual edits
--   deliverable_polished_sections — per-section LLM polish overrides (kept separate so revert
--                                   doesn't lose manual edits)
--   deliverable_updated_at        — last write timestamp for the curation state
--
-- Lifecycle: a row's deliverable state is bound to that report_version. On regeneration,
-- create_new_report_version() carries the config forward when section IDs match across versions
-- (config survives content edits) and NULLs polished_sections (their content is stale by definition).
--
-- All three columns are nullable; absence means "use defaults" (internal sections unchecked,
-- standard sections checked). No backfill required.

ALTER TABLE report_version
    ADD COLUMN IF NOT EXISTS deliverable_config JSON NULL,
    ADD COLUMN IF NOT EXISTS deliverable_polished_sections JSON NULL,
    ADD COLUMN IF NOT EXISTS deliverable_updated_at TIMESTAMP NULL;

COMMENT ON COLUMN report_version.deliverable_config IS
    'Deliverable Builder (A5) curation state. Shape: '
    '{ included_section_ids: string[], excluded_section_ids: string[], '
    '  custom_sections: [{ id, position: { after_section_id }, markdown }], '
    '  section_edits: { [section_id]: markdown } }. '
    'NULL = use defaults (internal sections excluded, standard included).';

COMMENT ON COLUMN report_version.deliverable_polished_sections IS
    'Per-section LLM polish overrides. Shape: '
    '{ [section_id]: { markdown, polished_at } }. '
    'NULL or missing key = no polish for that section. Reset on every new report version.';

COMMENT ON COLUMN report_version.deliverable_updated_at IS
    'Last write timestamp for deliverable_config or deliverable_polished_sections.';
