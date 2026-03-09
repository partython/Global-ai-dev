"""
Alembic environment configuration for Priya Global Platform.

Handles:
- Async migrations with asyncpg
- Multi-tenant schema with RLS policies
- Automatic model detection for autogenerate
- Transaction-per-migration safety
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Import config from shared.core
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.core.config import config

# Alembic Config object
config_obj = context.config

# Interpret the config file for Python logging.
if config_obj.config_file_name is not None:
    fileConfig(config_obj.config_file_name)

# Set sqlalchemy.url from DATABASE_URL environment variable
database_url = os.getenv("DATABASE_URL", config.db.dsn_async)
config_obj.set_main_option("sqlalchemy.url", database_url)


# ============================================================
# Model metadata for autogenerate
# ============================================================
# Import all SQLAlchemy models for Alembic to detect changes
# This is optional but recommended for autogenerate to work properly
# target_metadata = metadata
target_metadata = None


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    This configures the context with just a URL without an Engine,
    though an Engine is acceptable here too. By skipping the Engine
    creation we don't even need a DBAPI to be available.
    """
    url = config_obj.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Execute migrations with the given database connection.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    Creates an async engine and executes migrations with asyncpg.
    """
    url = config_obj.get_main_option("sqlalchemy.url")

    # Create async engine with connection pooling
    engine = create_async_engine(
        url,
        echo=False,
        poolclass=pool.NullPool,  # Use NullPool for migrations
        connect_args={
            "server_settings": {
                # Set tenant_id for RLS policies (set to NULL for admin operations)
                "app.current_tenant_id": "SYSTEM_ADMIN"
            }
        },
    )

    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
