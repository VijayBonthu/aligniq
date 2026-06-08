"""credits + report-generation metering

Revision ID: 0009_credits_metering
Revises: 0008_model_pricing
Create Date: 2026-06-08

Monetization redesign (see ~/.claude/plans/after-understand-the-project-*.md):

1. New `credit_wallet` (prepaid balance, one row/user) + append-only `credit_ledger`
   (FK-free, like llm_call_log — a credit history must outlive the rows it paid for).
   Credits are the universal top-up once a tier's monthly allowance is spent.

2. `usage_tracking` gains `report_generations_used` (ONE pool for the initial full
   report AND every regeneration — closes the hole where the first, most expensive,
   generation was uncounted) and `presales_used` (the cheap brief, metered separately).

Idempotent: the 0001 baseline's create_all builds these from the (now-updated) models
on a fresh DB, so this adds tables/columns only when missing.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_credits_metering"
down_revision: Union[str, None] = "0008_model_pricing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(insp, table: str, col: str) -> bool:
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "credit_wallet" not in tables:
        op.create_table(
            "credit_wallet",
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("balance_credits", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("user_id"),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        )

    if "credit_ledger" not in tables:
        op.create_table(
            "credit_ledger",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("balance_after", sa.Integer(), nullable=True),
            sa.Column("reason", sa.String(length=64), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=True),
            sa.Column("ref_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])
        op.create_index("ix_credit_ledger_ref_id", "credit_ledger", ["ref_id"])

    if "usage_tracking" in tables:
        if not _has_column(insp, "usage_tracking", "report_generations_used"):
            op.add_column(
                "usage_tracking",
                sa.Column("report_generations_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
        if not _has_column(insp, "usage_tracking", "presales_used"):
            op.add_column(
                "usage_tracking",
                sa.Column("presales_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "usage_tracking" in tables:
        for col in ("report_generations_used", "presales_used"):
            if _has_column(insp, "usage_tracking", col):
                op.drop_column("usage_tracking", col)

    if "credit_ledger" in tables:
        op.drop_table("credit_ledger")
    if "credit_wallet" in tables:
        op.drop_table("credit_wallet")
