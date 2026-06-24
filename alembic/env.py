"""Alembic environment.

Imports the live SQLAlchemy metadata and DB URL from the application
(`src/config.py` + `src/models.py`) so migrations and autogenerate stay in sync
with the running app. `prepend_sys_path = src` in alembic.ini puts the app source
on the path; we also insert it defensively here in case alembic is invoked from a
different cwd.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- make the app's source importable (config/models import each other top-level) ---
_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from config import settings  # noqa: E402
from models import Base  # noqa: E402

config = context.config

# Inject the DB URL from app settings (never hard-coded in alembic.ini).
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a live DB connection (`alembic upgrade --sql`).

    Note: the 0001 baseline uses metadata.create_all and therefore requires an
    online bind; offline mode is intended for plain DDL revisions only.
    """
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
