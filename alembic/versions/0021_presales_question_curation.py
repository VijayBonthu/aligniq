"""enterprise question curation: priority/theme/role/impact/default + durable context

Revision ID: 0021_presales_question_curation
Revises: 0020_support_messages
Create Date: 2026-07-05

Adds the fields that turn the clarifying-question step from a flat checklist into
prioritized, routed, defaulted intelligence:

- presales_questions.priority / theme / respondent_role / estimate_impact /
  default_assumption / default_assumption_risk
- presales_analysis.additional_context — durable free-text client/team context
  (was previously a transient form param, dropped from the CRD).
- presales_analysis.readiness_breakdown — per-theme readiness + top-gaps JSON.

All columns are nullable/additive — nothing is dropped, existing rows keep working.
Idempotent (guarded on inspector) so re-running `upgrade head` is a no-op.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_presales_question_curation"
down_revision: Union[str, None] = "0020_support_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_QUESTION_COLUMNS = [
    ("priority", sa.String(length=20)),
    ("theme", sa.String(length=40)),
    ("respondent_role", sa.String(length=20)),
    ("estimate_impact", sa.Text()),
    ("default_assumption", sa.Text()),
    ("default_assumption_risk", sa.String(length=20)),
]

_ANALYSIS_COLUMNS = [
    ("additional_context", sa.Text()),
    ("readiness_breakdown", sa.JSON()),
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    q_cols = {c["name"] for c in insp.get_columns("presales_questions")}
    for name, coltype in _QUESTION_COLUMNS:
        if name not in q_cols:
            op.add_column("presales_questions", sa.Column(name, coltype, nullable=True))

    a_cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    for name, coltype in _ANALYSIS_COLUMNS:
        if name not in a_cols:
            op.add_column("presales_analysis", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    a_cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    for name, _ in _ANALYSIS_COLUMNS:
        if name in a_cols:
            op.drop_column("presales_analysis", name)

    q_cols = {c["name"] for c in insp.get_columns("presales_questions")}
    for name, _ in _QUESTION_COLUMNS:
        if name in q_cols:
            op.drop_column("presales_questions", name)
