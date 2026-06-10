"""operational control plane — site settings, announcements, changelog, is_staff

Revision ID: 0010_ops_control_plane
Revises: 0009_credits_metering
Create Date: 2026-06-09

Production ops control plane (see ~/.claude/plans/the-app-is-almost-fizzy-glacier.md):

  - `site_settings`     — durable key/value for maintenance / read-only / feature flags
                          (dynamic, no-restart; Redis here is non-persistent so it can't
                          be the source of truth).
  - `announcements`     — user-facing banners (outage / maintenance / info ...).
  - `changelog_entries` — product "what's new" feed.
  - `users.is_staff`    — platform-admin flag gating the /admin console.

Idempotent: the 0001 baseline's create_all builds these from the (now-updated) models
on a fresh DB, so this adds tables/columns only when missing.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_ops_control_plane"
down_revision: Union[str, None] = "0009_credits_metering"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(insp, table: str, col: str) -> bool:
    return any(c["name"] == col for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "site_settings" not in tables:
        op.create_table(
            "site_settings",
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column("value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_by", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("key"),
        )

    if "announcements" not in tables:
        op.create_table(
            "announcements",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False, server_default=sa.text("'info'")),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("dismissible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("audience", sa.String(length=20), nullable=False, server_default=sa.text("'all'")),
            sa.Column("link_url", sa.String(length=500), nullable=True),
            sa.Column("link_label", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "changelog_entries" not in tables:
        op.create_table(
            "changelog_entries",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("version", sa.String(length=40), nullable=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=20), nullable=True),
            sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "users" in tables and not _has_column(insp, "users", "is_staff"):
        op.add_column(
            "users",
            sa.Column("is_staff", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "users" in tables and _has_column(insp, "users", "is_staff"):
        op.drop_column("users", "is_staff")
    for tbl in ("changelog_entries", "announcements", "site_settings"):
        if tbl in tables:
            op.drop_table(tbl)
