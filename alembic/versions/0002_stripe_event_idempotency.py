"""stripe webhook idempotency table

Revision ID: 0002_stripe_events
Revises: 0001_baseline
Create Date: 2026-06-01

Adds processed_stripe_events so redelivered/duplicate Stripe webhook events are
ignored (see src/routers/billing.py:stripe_webhook).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_stripe_events"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: on a fresh DB the 0001 baseline's create_all already built this
    # table (it's a declared model), so only create what's actually missing. This
    # lets `alembic upgrade head` work on BOTH a fresh DB and an existing DB that
    # was stamped at 0001_baseline.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "processed_stripe_events" not in insp.get_table_names():
        op.create_table(
            "processed_stripe_events",
            sa.Column("event_id", sa.String(), primary_key=True),
            sa.Column("event_type", sa.String(length=100), nullable=True),
            sa.Column(
                "received_at",
                sa.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_processed_stripe_events_event_id",
            "processed_stripe_events",
            ["event_id"],
        )
    else:
        existing = {ix["name"] for ix in insp.get_indexes("processed_stripe_events")}
        if "ix_processed_stripe_events_event_id" not in existing:
            op.create_index(
                "ix_processed_stripe_events_event_id",
                "processed_stripe_events",
                ["event_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "processed_stripe_events" in insp.get_table_names():
        existing = {ix["name"] for ix in insp.get_indexes("processed_stripe_events")}
        if "ix_processed_stripe_events_event_id" in existing:
            op.drop_index(
                "ix_processed_stripe_events_event_id",
                table_name="processed_stripe_events",
            )
        op.drop_table("processed_stripe_events")
