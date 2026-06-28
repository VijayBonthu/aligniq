"""in-app help & support tickets

Revision ID: 0019_support_tickets
Revises: 0018_project_naming_link_status
Create Date: 2026-06-24

Adds the `support_tickets` table backing the in-app Help & Support form (bug /
feedback / question submissions). The response loop is email — the durable record
lives here.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_support_tickets"
down_revision: Union[str, None] = "0018_project_naming_link_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "support_tickets" not in insp.get_table_names():
        op.create_table(
            "support_tickets",
            sa.Column("ticket_id", sa.String(), primary_key=True),
            sa.Column("ref_code", sa.String(length=16), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("category", sa.String(length=24), nullable=False),
            sa.Column("subject", sa.String(length=200), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("screenshot_path", sa.String(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'open'")),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_support_tickets_ticket_id", "support_tickets", ["ticket_id"])
        op.create_index("ix_support_tickets_ref_code", "support_tickets", ["ref_code"])
        op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "support_tickets" in insp.get_table_names():
        op.drop_index("ix_support_tickets_user_id", table_name="support_tickets")
        op.drop_index("ix_support_tickets_ref_code", table_name="support_tickets")
        op.drop_index("ix_support_tickets_ticket_id", table_name="support_tickets")
        op.drop_table("support_tickets")
