"""client portal fields on presales_analysis

Revision ID: 0014_client_portal_fields
Revises: 0013_client_share_token
Create Date: 2026-06-13

Adds `client_email` + `client_submitted_at` to presales_analysis for the Client
Readiness Portal (WS-3 v2): the recipient email (set on first send, reused for
reminders) and the "client submitted — firm review now" signal.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_client_portal_fields"
down_revision: Union[str, None] = "0013_client_share_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_email" not in cols:
        op.add_column("presales_analysis", sa.Column("client_email", sa.String(length=320), nullable=True))
    if "client_submitted_at" not in cols:
        op.add_column("presales_analysis", sa.Column("client_submitted_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_submitted_at" in cols:
        op.drop_column("presales_analysis", "client_submitted_at")
    if "client_email" in cols:
        op.drop_column("presales_analysis", "client_email")
