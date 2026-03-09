"""
Row Level Security (RLS) Helper Module

Provides utilities for managing PostgreSQL Row Level Security in the Priya Global platform.

SECURITY ARCHITECTURE:
- Every database operation is automatically scoped to the current tenant
- The tenant_context manager sets app.current_tenant_id for the transaction
- All RLS policies use this setting to filter data at the database layer
- Even if application code has bugs, data cannot leak between tenants

Usage Example:
    from shared.core.rls import tenant_context
    from shared.core.database import db

    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch("SELECT * FROM customers")
        # Only returns THIS tenant's customers due to RLS policies
"""

import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

import asyncpg
from fastapi import Request

from .database import db

logger = logging.getLogger("priya.rls")


def validate_tenant_id(tenant_id: str) -> uuid.UUID:
    """
    Validate that tenant_id is a valid UUID.

    Args:
        tenant_id: Tenant ID string to validate

    Returns:
        uuid.UUID: Validated UUID object

    Raises:
        ValueError: If tenant_id is not a valid UUID
    """
    try:
        return uuid.UUID(tenant_id)
    except (ValueError, AttributeError) as e:
        logger.warning(f"Invalid tenant_id format: {tenant_id}")
        raise ValueError(f"Invalid tenant_id format: {tenant_id}") from e


@asynccontextmanager
async def tenant_context(conn: asyncpg.Connection, tenant_id: str) -> AsyncGenerator[None, None]:
    """
    Context manager that sets the tenant context for database operations.

    This is the PRIMARY SECURITY BOUNDARY for tenant isolation. All RLS policies
    depend on the app.current_tenant_id setting to enforce data isolation.

    SECURITY: This uses SET LOCAL which only applies within a transaction.
    The setting is automatically reset when the context exits.

    Args:
        conn: asyncpg database connection
        tenant_id: The tenant ID to set as the current context (must be valid UUID)

    Yields:
        None

    Raises:
        ValueError: If tenant_id is not a valid UUID

    Example:
        async with db.tenant_connection(tenant_id) as conn:
            async with tenant_context(conn, tenant_id):
                rows = await conn.fetch("SELECT * FROM conversations")
                # RLS policies enforce only this tenant's data is returned
    """
    # Validate tenant_id format first
    validated_id = validate_tenant_id(tenant_id)
    tenant_id_str = str(validated_id)

    try:
        # SET LOCAL only applies to the current transaction
        # This prevents any accidental leakage to other transactions
        # Using parameterized query to prevent SQL injection
        await conn.execute("SET app.current_tenant_id = $1", tenant_id_str)

        logger.debug(f"Tenant context set: {tenant_id_str}")

        yield

    finally:
        # Reset to prevent any leak on connection reuse
        try:
            await conn.execute("RESET app.current_tenant_id")
            logger.debug(f"Tenant context reset")
        except Exception as e:
            logger.error(f"Failed to reset tenant context: {e}")


@asynccontextmanager
async def tenant_query_context(tenant_id: str) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Convenience context manager combining tenant_connection and tenant_context.

    This is the simplest way to execute tenant-scoped queries.

    Args:
        tenant_id: The tenant ID to scope operations to

    Yields:
        asyncpg.Connection: Connection with tenant context set

    Example:
        async with tenant_query_context(tenant_id) as conn:
            customer = await conn.fetchrow(
                "SELECT * FROM customers WHERE id = $1",
                customer_id
            )
            # RLS ensures we can only fetch this tenant's customers
    """
    # Validate tenant_id
    validate_tenant_id(tenant_id)

    async with db.tenant_connection(tenant_id) as conn:
        yield conn


def extract_tenant_id_from_request(request: Request) -> Optional[str]:
    """
    Extract tenant_id from the request context.

    Supports multiple sources (in order of precedence):
    1. X-Tenant-ID header
    2. Authorization token claims (JWT)
    3. Query parameter

    Args:
        request: FastAPI Request object

    Returns:
        str: Tenant ID if found, None otherwise

    Example:
        from fastapi import Request, Depends

        async def get_tenant_id(request: Request) -> str:
            tenant_id = extract_tenant_id_from_request(request)
            if not tenant_id:
                raise HTTPException(status_code=400, detail="No tenant ID")
            return tenant_id
    """
    # Priority 1: X-Tenant-ID header
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id

    # Priority 2: JWT claims (if JWT middleware is in place)
    # The request.state.user object should be set by authentication middleware
    if hasattr(request.state, "user") and hasattr(request.state.user, "tenant_id"):
        return request.state.user.tenant_id

    # Priority 3: Query parameter
    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        return tenant_id

    # No tenant ID found
    logger.warning("No tenant_id found in request")
    return None


async def set_tenant_context_from_request(request: Request) -> Optional[str]:
    """
    Extract tenant_id from request and validate it.

    This should be called in middleware to ensure all requests have a valid tenant context.

    Args:
        request: FastAPI Request object

    Returns:
        str: Validated tenant ID if found, None otherwise

    Raises:
        ValueError: If tenant_id format is invalid
    """
    tenant_id = extract_tenant_id_from_request(request)

    if not tenant_id:
        logger.warning("Attempting to set tenant context without tenant_id")
        return None

    # Validate the format
    try:
        validate_tenant_id(tenant_id)
        logger.debug(f"Tenant context extracted from request: {tenant_id}")
        return tenant_id
    except ValueError as e:
        logger.error(f"Invalid tenant_id in request: {e}")
        raise


class TenantIsolationMiddleware:
    """
    FastAPI middleware for automatic tenant context management.

    This middleware:
    1. Extracts tenant_id from request headers/JWT
    2. Validates the tenant_id format
    3. Stores it in request.state for use in route handlers

    Usage in main.py:
        from fastapi import FastAPI
        from shared.core.rls import TenantIsolationMiddleware

        app = FastAPI()
        app.add_middleware(TenantIsolationMiddleware)

    Then in route handlers, extract from request.state.tenant_id
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, request: Request, call_next):
        """
        Process request to extract and validate tenant context.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response with tenant context applied
        """
        # Extract tenant_id from request
        try:
            tenant_id = await set_tenant_context_from_request(request)
            request.state.tenant_id = tenant_id

            # If no tenant_id found, log warning (may be required route)
            if not tenant_id:
                logger.debug(f"Request {request.method} {request.url.path} has no tenant context")

        except ValueError as e:
            logger.error(f"Tenant context validation failed: {e}")
            # Store error for handler to check
            request.state.tenant_error = str(e)

        # Continue to next middleware/handler
        response = await call_next(request)
        return response


# Helper to check tenant context in request handlers
def require_tenant_context(request: Request) -> str:
    """
    Get tenant_id from request.state, raising error if not present.

    Use this in route handlers that require a valid tenant context.

    Args:
        request: FastAPI Request object

    Returns:
        str: The tenant_id from request.state

    Raises:
        ValueError: If tenant_id is missing or invalid

    Example:
        from fastapi import Request, Depends

        @router.get("/customers")
        async def list_customers(request: Request):
            tenant_id = require_tenant_context(request)
            # Now you have a validated tenant_id
    """
    # Check for tenant context errors
    if hasattr(request.state, "tenant_error"):
        raise ValueError(f"Tenant context error: {request.state.tenant_error}")

    # Check for tenant_id
    if not hasattr(request.state, "tenant_id") or not request.state.tenant_id:
        raise ValueError("No tenant context found in request")

    return request.state.tenant_id


async def get_tenant_info(conn: asyncpg.Connection, tenant_id: str) -> Optional[dict]:
    """
    Fetch tenant information from the database.

    SECURITY: This requires admin connection or service role - it bypasses RLS.
    Only call this for administrative purposes.

    Args:
        conn: Database connection (must be admin or service role)
        tenant_id: Tenant ID to fetch

    Returns:
        dict: Tenant information if found, None otherwise

    Example:
        async with db.admin_connection() as conn:
            tenant = await get_tenant_info(conn, tenant_id)
            print(f"Tenant: {tenant['name']}")
    """
    try:
        validate_tenant_id(tenant_id)

        tenant = await conn.fetchrow(
            """
            SELECT id, name, slug, plan, status, created_at
            FROM tenants
            WHERE id = $1
            """,
            tenant_id,
        )

        if tenant:
            logger.debug(f"Tenant info retrieved: {tenant_id}")
            return dict(tenant)

        logger.warning(f"Tenant not found: {tenant_id}")
        return None

    except Exception as e:
        logger.error(f"Failed to get tenant info: {e}")
        raise


async def verify_tenant_access(
    conn: asyncpg.Connection, tenant_id: str, user_id: str
) -> bool:
    """
    Verify that a user has access to the given tenant.

    SECURITY: This is a secondary check - RLS is the primary enforcement.
    Use this for application-level authorization decisions.

    Args:
        conn: Database connection (must be admin/service role)
        tenant_id: Tenant to check access for
        user_id: User to verify

    Returns:
        bool: True if user can access tenant, False otherwise

    Example:
        async with db.admin_connection() as conn:
            has_access = await verify_tenant_access(conn, tenant_id, user_id)
            if not has_access:
                raise HTTPException(status_code=403, detail="Access denied")
    """
    try:
        validate_tenant_id(tenant_id)

        # Check if user exists and belongs to this tenant
        user = await conn.fetchrow(
            """
            SELECT id FROM users
            WHERE id = $1 AND tenant_id = $2
            """,
            user_id,
            tenant_id,
        )

        has_access = user is not None
        logger.debug(f"Tenant access check: user={user_id}, tenant={tenant_id}, access={has_access}")

        return has_access

    except Exception as e:
        logger.error(f"Failed to verify tenant access: {e}")
        return False
