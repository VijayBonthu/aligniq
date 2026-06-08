"""cost ledger fixes: drop llm_call_log FKs + add per-run cost totals

Revision ID: 0007_cost_ledger_fixes
Revises: 0006_signup_events
Create Date: 2026-06-06

Two changes that make the LLM cost ledger correct and queryable:

1. Drop the hard FKs on `llm_call_log` (presales_id, chat_history_id, pipeline_run_id).
   They are now LOGICAL references. The FK on presales_id silently dropped every
   initial-presales-scan call, because the scan's calls are recorded before the
   parent presales_analysis row is saved (FK violation -> rolled back). A telemetry
   ledger must tolerate out-of-order writes and outlive the rows it references.

2. Add materialized COGS roll-up columns `total_cost_usd` / `total_calls` to
   `pipeline_runs` and `presales_analysis`, written on completion from the ledger.

Idempotent: the 0001 baseline's create_all builds these from the (now-updated) models
on a fresh DB, so this migration drops FKs only if present and adds columns only if missing.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_cost_ledger_fixes"
down_revision: Union[str, None] = "0006_signup_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEDGER_FK_COLUMNS = {"presales_id", "chat_history_id", "pipeline_run_id"}
_TOTAL_COLUMNS = ("total_cost_usd", "total_calls")


def _has_column(insp, table: str, col: str) -> bool:
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # 1. Drop the three hard FKs on llm_call_log (by discovered name, idempotent).
    if "llm_call_log" in tables:
        for fk in insp.get_foreign_keys("llm_call_log"):
            cols = set(fk.get("constrained_columns") or [])
            if fk.get("name") and (cols & _LEDGER_FK_COLUMNS):
                op.drop_constraint(fk["name"], "llm_call_log", type_="foreignkey")

    # 2. Add the materialized cost-total columns where missing.
    for table in ("pipeline_runs", "presales_analysis"):
        if table not in tables:
            continue
        if not _has_column(insp, table, "total_cost_usd"):
            op.add_column(
                table,
                sa.Column("total_cost_usd", sa.Float(), nullable=False,
                          server_default=sa.text("0")),
            )
        if not _has_column(insp, table, "total_calls"):
            op.add_column(
                table,
                sa.Column("total_calls", sa.Integer(), nullable=False,
                          server_default=sa.text("0")),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    for table in ("pipeline_runs", "presales_analysis"):
        if table not in tables:
            continue
        for col in _TOTAL_COLUMNS:
            if _has_column(insp, table, col):
                op.drop_column(table, col)

    # Re-add the FKs. NOTE: this fails if orphan ledger rows exist (the very reason
    # they were dropped) — that is the intended signal to an operator downgrading.
    if "llm_call_log" in tables:
        op.create_foreign_key(None, "llm_call_log", "chat_history",
                              ["chat_history_id"], ["chat_history_id"])
        op.create_foreign_key(None, "llm_call_log", "pipeline_runs",
                              ["pipeline_run_id"], ["run_id"])
        op.create_foreign_key(None, "llm_call_log", "presales_analysis",
                              ["presales_id"], ["presales_id"])
