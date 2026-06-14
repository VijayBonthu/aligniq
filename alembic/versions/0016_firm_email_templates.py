"""per-firm email template overrides

Revision ID: 0016_firm_email_templates
Revises: 0015_client_check_count
Create Date: 2026-06-14

Adds `firms.email_templates` (JSON) — admin-editable text overrides for the client
questionnaire invite/reminder emails, per organization. Only the copy fields are
overridable; the GroundedIQ-branded shell is always applied at render time.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_firm_email_templates"
down_revision: Union[str, None] = "0015_client_check_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("firms")}
    if "email_templates" not in cols:
        op.add_column("firms", sa.Column("email_templates", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("firms")}
    if "email_templates" in cols:
        op.drop_column("firms", "email_templates")
