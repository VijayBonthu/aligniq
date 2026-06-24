"""project custom name + client-link shared status

Revision ID: 0018_project_naming_link_status
Revises: 0017_client_respondent
Create Date: 2026-06-14

Adds:
- chat_history.custom_title — firm-set project-card name (LLM `title` stays as the
  searchable fallback).
- presales_analysis.client_link_shared_at — when the questionnaire link was shared
  (email or marked manually), for the dashboard "sent" status.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018_project_naming_link_status"
down_revision: Union[str, None] = "0017_client_respondent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    ch_cols = {c["name"] for c in insp.get_columns("chat_history")}
    if "custom_title" not in ch_cols:
        op.add_column("chat_history", sa.Column("custom_title", sa.String(length=200), nullable=True))
    pa_cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_link_shared_at" not in pa_cols:
        op.add_column("presales_analysis", sa.Column("client_link_shared_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    ch_cols = {c["name"] for c in insp.get_columns("chat_history")}
    if "custom_title" in ch_cols:
        op.drop_column("chat_history", "custom_title")
    pa_cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_link_shared_at" in pa_cols:
        op.drop_column("presales_analysis", "client_link_shared_at")
