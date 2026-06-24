"""linked-login identities table (user_identities)

Revision ID: 0005_user_identities
Revises: 0004_user_company
Create Date: 2026-06-06

Adds `user_identities` — one row per external login method (Google/GitHub/Microsoft/
Local) linked to a user. Backs link-by-verified-email account tracking and a future
Connected-accounts UI. Idempotent: on a fresh DB the 0001 baseline's create_all already
built it from the model, so we only create it when missing.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_user_identities"
down_revision: Union[str, None] = "0004_user_company"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "user_identities" in insp.get_table_names():
        return
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_user_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
    op.create_index("ix_user_identities_provider", "user_identities", ["provider"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "user_identities" in insp.get_table_names():
        op.drop_table("user_identities")
