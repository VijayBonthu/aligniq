"""signup anti-abuse audit trail (signup_events)

Revision ID: 0006_signup_events
Revises: 0005_user_identities
Create Date: 2026-06-06

Adds `signup_events` — one row per account creation capturing IP, device fingerprint,
UA, provider, and a `flagged` bit set by device/IP velocity rules. Idempotent: the 0001
baseline's create_all already builds it from the model on a fresh DB.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_signup_events"
down_revision: Union[str, None] = "0005_user_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "signup_events" in insp.get_table_names():
        return
    op.create_table(
        "signup_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    for col in ("user_id", "email", "ip", "device_id"):
        op.create_index(f"ix_signup_events_{col}", "signup_events", [col])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "signup_events" in insp.get_table_names():
        op.drop_table("signup_events")
