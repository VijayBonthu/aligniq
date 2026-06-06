"""backend comp/gift grants on users

Revision ID: 0003_comp_grants
Revises: 0002_stripe_events
Create Date: 2026-06-01

Adds comp_tier + comp_expires_at to users so an admin can grant any tier for a
fixed window (free months, complaint make-goods) without touching Stripe. The
usage layer (utils/subscription.py:get_effective_tier) honors an unexpired comp
and lazily reverts to the real subscription_tier when it lapses.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_comp_grants"
down_revision: Union[str, None] = "0002_stripe_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: on a fresh DB the 0001 baseline's create_all already added these
    # columns (they're declared on the User model), so only add what's missing.
    # Existing DBs stamped at 0001_baseline get the columns added here.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "comp_tier" not in cols:
        op.add_column("users", sa.Column("comp_tier", sa.String(length=50), nullable=True))
    if "comp_expires_at" not in cols:
        op.add_column(
            "users",
            sa.Column("comp_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "comp_expires_at" in cols:
        op.drop_column("users", "comp_expires_at")
    if "comp_tier" in cols:
        op.drop_column("users", "comp_tier")
