"""client-signoff baseline flag on report_version

Revision ID: 0012_report_version_signoff
Revises: 0011_ops_targeting_media
Create Date: 2026-06-13

Adds `is_client_signoff` + `signoff_at` to report_version so a firm can pin the
version the client signed off on. That pinned version is the baseline the
"since signoff" diff + change-order draft are computed against — the
scope-creep-defense artifact the product thesis promises. One baseline per
project (enforced in the endpoint, not the schema).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_report_version_signoff"
down_revision: Union[str, None] = "0011_ops_targeting_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: on a fresh DB the 0001 baseline's create_all already added these
    # columns (declared on the ReportVersions model), so only add when missing.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("report_version")}
    if "is_client_signoff" not in cols:
        op.add_column(
            "report_version",
            sa.Column("is_client_signoff", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
        op.create_index(
            "ix_report_version_is_client_signoff", "report_version", ["is_client_signoff"]
        )
    if "signoff_at" not in cols:
        op.add_column(
            "report_version",
            sa.Column("signoff_at", sa.TIMESTAMP(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("report_version")}
    indexes = {i["name"] for i in insp.get_indexes("report_version")}
    if "ix_report_version_is_client_signoff" in indexes:
        op.drop_index("ix_report_version_is_client_signoff", table_name="report_version")
    if "is_client_signoff" in cols:
        op.drop_column("report_version", "is_client_signoff")
    if "signoff_at" in cols:
        op.drop_column("report_version", "signoff_at")
