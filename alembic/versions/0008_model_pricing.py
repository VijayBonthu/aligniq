"""model_pricing — DB-backed LLM price book

Revision ID: 0008_model_pricing
Revises: 0007_cost_ledger_fixes
Create Date: 2026-06-06

Mirrors utils.llm_pricing.SEED_PRICES into a table so rates update without a deploy
and can be refreshed by the daily LiteLLM-diff job. Rows are seeded by the app at
startup (load_pricing_from_db), not here. Idempotent: the 0001 baseline create_all
already builds this from the model on a fresh DB.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_model_pricing"
down_revision: Union[str, None] = "0007_cost_ledger_fixes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "model_pricing" in insp.get_table_names():
        return
    op.create_table(
        "model_pricing",
        sa.Column("model", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("input_per_1m", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("cached_input_per_1m", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_per_1m", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("effective_date", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "model_pricing" in insp.get_table_names():
        op.drop_table("model_pricing")
