"""Tests for src/utils/report_sections.py.

Verifies:
- Stable section IDs across small report variations.
- Correct internal vs standard classification per the prompt structure.
- assemble_deliverable() honors exclusions, edits, polish, and custom anchors.
- Orphaned H2 (all children excluded) is dropped.
"""

from src.utils.report_sections import (
    parse_sections,
    assemble_deliverable,
    default_excluded_ids,
)


# A trimmed but representative report mirroring Report_Generator_Prompt structure.
FIXTURE_FULL = """\
# Project: Acme Migration

## 1. Executive Summary

We propose a phased migration to AWS over 18 months, totaling $1.2M.

## 2. Business Requirements

### 2.1 Functional Requirements

- FR-1: Single sign-on across portals.
- FR-2: $50,000 annual budget for compliance audits.

### 2.2 Non-Functional Requirements

- NFR-1: 99.9% uptime SLA.

## 3. Assumptions & Client Questions

### 3.1 Explicit Assumptions

- We assume PostgreSQL is acceptable for the relational store.

### 3.2 Unanswered Questions

- What is the expected peak QPS?

## 4. Solution Architecture

### 4.1 Candidate Architectures

Option A: PostgreSQL on RDS. Option B: DynamoDB. Option C: Aurora Serverless.

### 4.2 Recommended Architecture (Deep Technical Breakdown)

PostgreSQL on RDS, multi-AZ, with read replicas in 2 regions.

## 5. Detailed Design Considerations

Encryption at rest using AWS KMS. IAM roles for service-to-service auth.

## 6. Feasibility & Effort Estimates

### 6.1 MVP Effort Breakdown

12 weeks, 4 engineers at $180/hr blended rate.

### 6.2 Production Effort Breakdown

26 weeks, 6 engineers at $180/hr blended rate.

## 7. Risks & Mitigations

- Risk: vendor lock-in to AWS. Mitigation: keep abstractions thin.

## 8. Recommendations

Proceed with phased migration starting Q1.
"""


def test_parses_h2_and_h3_sections_in_order():
    sections = parse_sections(FIXTURE_FULL)
    ids = [s.id for s in sections]
    # Spot-check key IDs and ordering
    assert "s-1-executive-summary" in ids
    assert "s-2-business-requirements" in ids
    assert "s-2-1-functional-requirements" in ids
    assert "s-3-2-unanswered-questions" in ids
    assert "s-4-1-candidate-architectures" in ids
    assert "s-4-2-recommended-architecture-deep-technical-breakdown" in ids
    assert "s-6-1-mvp-effort-breakdown" in ids
    assert ids.index("s-3-1-explicit-assumptions") < ids.index("s-3-2-unanswered-questions")
    assert ids.index("s-3-2-unanswered-questions") < ids.index("s-4-1-candidate-architectures")


def test_internal_classification_matches_prompt_rules():
    sections = {s.id: s for s in parse_sections(FIXTURE_FULL)}
    assert sections["s-3-2-unanswered-questions"].kind == "internal"
    assert sections["s-4-1-candidate-architectures"].kind == "internal"
    assert sections["s-6-1-mvp-effort-breakdown"].kind == "internal"
    assert sections["s-6-2-production-effort-breakdown"].kind == "internal"
    # Standard
    assert sections["s-1-executive-summary"].kind == "standard"
    assert sections["s-3-1-explicit-assumptions"].kind == "standard"
    assert sections["s-4-2-recommended-architecture-deep-technical-breakdown"].kind == "standard"
    assert sections["s-7-risks-mitigations"].kind == "standard"


def test_h3_parent_id_links_to_enclosing_h2():
    sections = {s.id: s for s in parse_sections(FIXTURE_FULL)}
    assert sections["s-3-1-explicit-assumptions"].parent_id == "s-3-assumptions-client-questions"
    assert sections["s-3-2-unanswered-questions"].parent_id == "s-3-assumptions-client-questions"
    assert sections["s-1-executive-summary"].parent_id is None  # H2, no parent


def test_section_ids_are_stable_across_minor_content_changes():
    """Editing body text inside a section must not change its ID — that's
    the whole point of carrying deliverable_config forward across regens.
    """
    edited = FIXTURE_FULL.replace(
        "Encryption at rest using AWS KMS.",
        "Encryption at rest using AWS KMS and customer-managed keys.",
    )
    ids_before = {s.id for s in parse_sections(FIXTURE_FULL)}
    ids_after = {s.id for s in parse_sections(edited)}
    assert ids_before == ids_after


def test_default_excluded_ids_returns_only_internal():
    sections = parse_sections(FIXTURE_FULL)
    excluded = set(default_excluded_ids(sections))
    assert "s-3-2-unanswered-questions" in excluded
    assert "s-4-1-candidate-architectures" in excluded
    assert "s-6-1-mvp-effort-breakdown" in excluded
    assert "s-6-2-production-effort-breakdown" in excluded
    assert "s-1-executive-summary" not in excluded
    assert "s-7-risks-mitigations" not in excluded


def test_assemble_deliverable_with_defaults_drops_internal_only():
    sections = parse_sections(FIXTURE_FULL)
    excluded = set(default_excluded_ids(sections))
    out = assemble_deliverable(
        sections,
        excluded_ids=excluded,
        section_edits={},
        polished={},
        custom_sections=[],
    )
    assert "Executive Summary" in out
    assert "Recommended Architecture" in out
    assert "Risks & Mitigations" in out
    # Internal stuff gone
    assert "Unanswered Questions" not in out
    assert "Candidate Architectures" not in out
    assert "MVP Effort Breakdown" not in out


def test_assemble_drops_h2_when_all_children_excluded():
    """When every H3 under an H2 is excluded, the H2 heading itself must drop
    so we don't leave an empty "## 6. Feasibility & Effort Estimates" header.
    """
    sections = parse_sections(FIXTURE_FULL)
    out = assemble_deliverable(
        sections,
        excluded_ids={"s-6-1-mvp-effort-breakdown", "s-6-2-production-effort-breakdown"},
        section_edits={},
        polished={},
        custom_sections=[],
    )
    assert "Feasibility & Effort Estimates" not in out


def test_assemble_keeps_h2_when_some_children_remain():
    sections = parse_sections(FIXTURE_FULL)
    out = assemble_deliverable(
        sections,
        excluded_ids={"s-3-2-unanswered-questions"},  # 3.1 still in
        section_edits={},
        polished={},
        custom_sections=[],
    )
    assert "Assumptions & Client Questions" in out
    assert "Explicit Assumptions" in out
    assert "Unanswered Questions" not in out


def test_assemble_prefers_polished_over_edits_over_raw():
    sections = parse_sections(FIXTURE_FULL)
    out_raw = assemble_deliverable(sections, excluded_ids=set(), section_edits={}, polished={}, custom_sections=[])
    assert "Single sign-on across portals" in out_raw

    out_edited = assemble_deliverable(
        sections,
        excluded_ids=set(),
        section_edits={"s-2-1-functional-requirements": "### 2.1 Functional Requirements\n\nEDITED VERSION\n"},
        polished={},
        custom_sections=[],
    )
    assert "EDITED VERSION" in out_edited
    assert "Single sign-on across portals" not in out_edited

    out_polished = assemble_deliverable(
        sections,
        excluded_ids=set(),
        section_edits={"s-2-1-functional-requirements": "### 2.1 Functional Requirements\n\nEDITED VERSION\n"},
        polished={"s-2-1-functional-requirements": {"markdown": "### 2.1 Functional Requirements\n\nPOLISHED VERSION\n"}},
        custom_sections=[],
    )
    assert "POLISHED VERSION" in out_polished
    assert "EDITED VERSION" not in out_polished


def test_assemble_inserts_custom_section_after_anchor():
    sections = parse_sections(FIXTURE_FULL)
    out = assemble_deliverable(
        sections,
        excluded_ids=set(default_excluded_ids(sections)),
        section_edits={},
        polished={},
        custom_sections=[
            {
                "id": "custom-1",
                "position": {"after_section_id": "s-3-1-explicit-assumptions"},
                "markdown": "### Questions for Acme\n\n- What is your expected peak QPS?\n",
            }
        ],
    )
    assert "Questions for Acme" in out
    # Anchor section appears before the inserted block
    assert out.index("Explicit Assumptions") < out.index("Questions for Acme")
    # Inserted block appears before the next H2 (Section 4)
    assert out.index("Questions for Acme") < out.index("Solution Architecture")


def test_empty_input_returns_empty_list():
    assert parse_sections("") == []
    assert parse_sections("   \n   \n") == []
    assert parse_sections("# Just a title with no H2 sections\n\nbody only") == []
