"""support conversation thread (inbound + outbound) + ticket reply fields

Revision ID: 0020_support_messages
Revises: 0019_support_tickets
Create Date: 2026-06-24

Adds:
- `support_messages` — one row per message in a ticket (inbound user replies ingested
  from the Resend inbound webhook; outbound staff replies sent from the admin panel).
- `support_tickets.requester_email` / `.updated_at`.
- Relaxes `support_tickets.user_id` to nullable so an inbound email from a non-user
  can still open a ticket.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020_support_messages"
down_revision: Union[str, None] = "0019_support_tickets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    tk_cols = {c["name"] for c in insp.get_columns("support_tickets")}
    if "requester_email" not in tk_cols:
        op.add_column("support_tickets", sa.Column("requester_email", sa.String(), nullable=True))
        op.create_index("ix_support_tickets_requester_email", "support_tickets", ["requester_email"])
    if "updated_at" not in tk_cols:
        op.add_column(
            "support_tickets",
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    # Relax user_id to nullable (inbound emails from non-users still open a ticket).
    user_id_col = next((c for c in insp.get_columns("support_tickets") if c["name"] == "user_id"), None)
    if user_id_col is not None and not user_id_col.get("nullable", True):
        op.alter_column("support_tickets", "user_id", existing_type=sa.String(), nullable=True)

    if "support_messages" not in insp.get_table_names():
        op.create_table(
            "support_messages",
            sa.Column("message_id", sa.String(), primary_key=True),
            sa.Column("ticket_id", sa.String(), sa.ForeignKey("support_tickets.ticket_id"), nullable=False),
            sa.Column("direction", sa.String(length=10), nullable=False),
            sa.Column("author_email", sa.String(), nullable=True),
            sa.Column("author_name", sa.String(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("body_html", sa.Text(), nullable=True),
            sa.Column("attachments", sa.JSON(), nullable=True),
            sa.Column("provider_message_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_support_messages_message_id", "support_messages", ["message_id"])
        op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])
        op.create_index("ix_support_messages_provider_message_id", "support_messages", ["provider_message_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "support_messages" in insp.get_table_names():
        op.drop_index("ix_support_messages_provider_message_id", table_name="support_messages")
        op.drop_index("ix_support_messages_ticket_id", table_name="support_messages")
        op.drop_index("ix_support_messages_message_id", table_name="support_messages")
        op.drop_table("support_messages")

    tk_cols = {c["name"] for c in insp.get_columns("support_tickets")}
    if "updated_at" in tk_cols:
        op.drop_column("support_tickets", "updated_at")
    if "requester_email" in tk_cols:
        op.drop_index("ix_support_tickets_requester_email", table_name="support_tickets")
        op.drop_column("support_tickets", "requester_email")
