"""durable per-token readiness-check counter on presales_analysis

Revision ID: 0015_client_check_count
Revises: 0014_client_portal_fields
Create Date: 2026-06-14

Adds `client_check_count` to presales_analysis — the durable lifetime ceiling on
public "Check readiness" LLM calls per share link. This is the backstop that caps
LLM cost even when the Redis windowed throttle is unavailable (DB never fails open).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_client_check_count"
down_revision: Union[str, None] = "0014_client_portal_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_check_count" not in cols:
        op.add_column(
            "presales_analysis",
            sa.Column("client_check_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_check_count" in cols:
        op.drop_column("presales_analysis", "client_check_count")
