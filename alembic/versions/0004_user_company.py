"""company/organization field on users

Revision ID: 0004_user_company
Revises: 0003_comp_grants
Create Date: 2026-06-06

Adds a nullable `company` column to users. The signup form already collected a
company name but dropped it on the floor; this persists it. Meaningful for a
consulting-firm product and cheap to store.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_user_company"
down_revision: Union[str, None] = "0003_comp_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: on a fresh DB the 0001 baseline's create_all already added this
    # column (it's declared on the User model), so only add it when missing.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "company" not in cols:
        op.add_column("users", sa.Column("company", sa.String(length=120), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users")}
    if "company" in cols:
        op.drop_column("users", "company")
