"""client respondent identity on presales_analysis

Revision ID: 0017_client_respondent
Revises: 0016_firm_email_templates
Create Date: 2026-06-14

Adds `presales_analysis.client_respondent` (JSON) — who actually completed the
client questionnaire (name / designation / email), captured at submit for the
firm's record + proof of submission.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_client_respondent"
down_revision: Union[str, None] = "0016_firm_email_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_respondent" not in cols:
        op.add_column("presales_analysis", sa.Column("client_respondent", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_respondent" in cols:
        op.drop_column("presales_analysis", "client_respondent")
