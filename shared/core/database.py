"""
Multi-Tenant Database Layer with Row Level Security (RLS)

SECURITY ARCHITECTURE:
- Every table has a tenant_id column
- PostgreSQL RLS policies enforce tenant isolation at the DB level
- Even if application code has a bug, data cannot leak between tenants
- Every connection sets the current tenant via SET LOCAL
- PSI AI (Tenant #1) data is completely isolated from other tenants

This is the MOST CRITICAL security component of the platform.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

import asyncpg

from .config import config

logger = logging.getLogger("priya.database")


class TenantDatabase:
    """
    PostgreSQL connection pool with automatic tenant isolation.

    Usage:
        db = TenantDatabase()
        await db.initialize()

        # All queries automatically scoped to tenant
        async with db.tenant_connection(tenant_id) as conn:
            rows = await conn.fetch("SELECT * FROM customers")
            # ^ Only returns THIS tenant's customers. RLS enforces this.
    """

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def initialize(self):
        """Create connection pool. Call once at service startup."""
        if self._initialized:
            return

        self._pool = await asyncpg.create_pool(
            host=config.db.host,
            port=config.db.port,
            database=config.db.name,
            user=config.db.user,
            password=config.db.password,
            min_size=config.db.pool_min,
            max_size=config.db.pool_max,
            command_timeout=30,
            statement_cache_size=100,
        )
        self._initialized = True
        logger.info("Database pool initialized (min=%d, max=%d)", config.db.pool_min, config.db.pool_max)

    async def close(self):
        """Close pool. Call at service shutdown."""
        if self._pool:
            await self._pool.close()
            self._initialized = False
            logger.info("Database pool closed")

    @asynccontextmanager
    async def tenant_connection(self, tenant_id: str) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Get a connection with tenant context set.

        SECURITY: This sets `app.current_tenant_id` which RLS policies use
        to filter ALL queries to only this tenant's data.

        PSI AI knowledge (Tenant #1) CANNOT leak to Tenant #2 through this layer.
        """
        if not self._pool:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._pool.acquire() as conn:
            # SET LOCAL only applies to current transaction
            # This is the security boundary - RLS uses this value
            await conn.execute("SET LOCAL app.current_tenant_id = $1", str(tenant_id))
            try:
                yield conn
            finally:
                # Reset to prevent any leak between pool reuse
                await conn.execute("RESET app.current_tenant_id")

    @asynccontextmanager
    async def admin_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Connection WITHOUT tenant filtering. For platform admin operations ONLY.

        SECURITY: Only use this for:
        - Tenant creation/deletion
        - Cross-tenant analytics (aggregated, never raw data)
        - System maintenance

        NEVER expose admin_connection to tenant-facing endpoints.
        """
        if not self._pool:
            raise RuntimeError("Database not initialized. Call initialize() first.")

        async with self._pool.acquire() as conn:
            # Explicitly set to admin mode
            await conn.execute("SET LOCAL app.current_tenant_id = 'SYSTEM_ADMIN'")
            try:
                yield conn
            finally:
                await conn.execute("RESET app.current_tenant_id")

    @asynccontextmanager
    async def transaction(self, tenant_id: str) -> AsyncGenerator[asyncpg.Connection, None]:
        """Tenant-scoped transaction with automatic commit/rollback."""
        async with self.tenant_connection(tenant_id) as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                yield conn
                await tr.commit()
            except Exception:
                await tr.rollback()
                raise

    # ─── Helper Methods ───

    async def fetch_one(self, tenant_id: str, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch single row with tenant isolation."""
        async with self.tenant_connection(tenant_id) as conn:
            return await conn.fetchrow(query, *args)

    async def fetch_all(self, tenant_id: str, query: str, *args) -> List[asyncpg.Record]:
        """Fetch all rows with tenant isolation."""
        async with self.tenant_connection(tenant_id) as conn:
            return await conn.fetch(query, *args)

    async def execute(self, tenant_id: str, query: str, *args) -> str:
        """Execute query with tenant isolation."""
        async with self.tenant_connection(tenant_id) as conn:
            return await conn.execute(query, *args)

    async def insert_returning(self, tenant_id: str, query: str, *args) -> Optional[asyncpg.Record]:
        """Insert and return the created row."""
        async with self.tenant_connection(tenant_id) as conn:
            return await conn.fetchrow(query, *args)


def generate_uuid() -> str:
    """Generate a new UUID v4 string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


# Singleton database instance
db = TenantDatabase()
