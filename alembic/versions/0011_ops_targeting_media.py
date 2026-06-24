"""ops control plane — per-email announcement targeting + changelog media

Revision ID: 0011_ops_targeting_media
Revises: 0010_ops_control_plane
Create Date: 2026-06-10

Adds two nullable columns to existing ops tables (no new tables):

  - `announcements.target_emails` (JSONB) — when audience='users', the explicit
    recipient emails. Served only via the authenticated /my-site-config endpoint.
  - `changelog_entries.media_url`  (varchar) — optional GIF/image URL shown in
    "What's new".

(Maintenance-page GIF + multiline title need no migration: media_url lives in the
`site_settings.maintenance` JSONB value, and multiline is UI/render only.)

Idempotent: the 0001 baseline's create_all builds these from the (now-updated) models
on a fresh DB, so this adds columns only when missing.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_ops_targeting_media"
down_revision: Union[str, None] = "0010_ops_control_plane"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(insp, table: str, col: str) -> bool:
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "announcements" in tables and not _has_column(insp, "announcements", "target_emails"):
        op.add_column("announcements", sa.Column("target_emails", postgresql.JSONB(), nullable=True))

    if "changelog_entries" in tables and not _has_column(insp, "changelog_entries", "media_url"):
        op.add_column("changelog_entries", sa.Column("media_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "changelog_entries" in tables and _has_column(insp, "changelog_entries", "media_url"):
        op.drop_column("changelog_entries", "media_url")
    if "announcements" in tables and _has_column(insp, "announcements", "target_emails"):
        op.drop_column("announcements", "target_emails")
