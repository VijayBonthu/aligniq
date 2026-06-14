"""client questionnaire share token on presales_analysis

Revision ID: 0013_client_share_token
Revises: 0012_report_version_signoff
Create Date: 2026-06-13

Adds a nullable, unique `client_share_token` to presales_analysis so a firm can
share a public, no-login questionnaire link with the client. The opaque token in
the URL is the only secret; nulling it revokes the link. Closes the email
ping-pong loop (WS-3): the client answers the firm's questions directly.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_client_share_token"
down_revision: Union[str, None] = "0012_report_version_signoff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: 0001 baseline create_all already adds this column on a fresh DB
    # (it's declared on the model), so only add when missing.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    if "client_share_token" not in cols:
        op.add_column(
            "presales_analysis",
            sa.Column("client_share_token", sa.String(length=64), nullable=True),
        )
        op.create_unique_constraint(
            "uq_presales_analysis_client_share_token", "presales_analysis", ["client_share_token"]
        )
        op.create_index(
            "ix_presales_analysis_client_share_token", "presales_analysis", ["client_share_token"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("presales_analysis")}
    indexes = {i["name"] for i in insp.get_indexes("presales_analysis")}
    constraints = {c["name"] for c in insp.get_unique_constraints("presales_analysis")}
    if "ix_presales_analysis_client_share_token" in indexes:
        op.drop_index("ix_presales_analysis_client_share_token", table_name="presales_analysis")
    if "uq_presales_analysis_client_share_token" in constraints:
        op.drop_constraint("uq_presales_analysis_client_share_token", "presales_analysis", type_="unique")
    if "client_share_token" in cols:
        op.drop_column("presales_analysis", "client_share_token")
