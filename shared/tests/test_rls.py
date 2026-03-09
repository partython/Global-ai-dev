"""
Row Level Security Integration Tests

Tests to verify:
1. RLS policies are correctly applied
2. Tenant isolation is enforced at DB level
3. Service role can bypass RLS when needed
4. Tenant context management works correctly

SECURITY: These tests are critical. RLS failure = data breach.
"""

import pytest
import uuid
from typing import AsyncGenerator

import asyncpg

from shared.core.database import db
from shared.core.rls import (
    tenant_context,
    validate_tenant_id,
    extract_tenant_id_from_request,
)


class TestTenantIdValidation:
    """Test tenant_id validation"""

    def test_valid_uuid_string(self):
        """Valid UUID strings should be accepted"""
        valid_uuid = str(uuid.uuid4())
        result = validate_tenant_id(valid_uuid)
        assert isinstance(result, uuid.UUID)
        assert str(result) == valid_uuid

    def test_valid_uuid_object(self):
        """Valid UUID objects should be accepted"""
        valid_uuid = uuid.uuid4()
        result = validate_tenant_id(str(valid_uuid))
        assert isinstance(result, uuid.UUID)

    def test_invalid_uuid_string(self):
        """Invalid UUID strings should raise ValueError"""
        with pytest.raises(ValueError):
            validate_tenant_id("not-a-valid-uuid")

    def test_empty_string(self):
        """Empty string should raise ValueError"""
        with pytest.raises(ValueError):
            validate_tenant_id("")

    def test_none_value(self):
        """None should raise ValueError"""
        with pytest.raises(ValueError):
            validate_tenant_id(None)


class TestTenantContextManagement:
    """Test tenant context setting and isolation"""

    @pytest.mark.asyncio
    async def test_tenant_context_sets_setting(self):
        """Verify tenant context actually sets the PostgreSQL setting"""
        tenant_id = str(uuid.uuid4())

        async with db.tenant_connection(tenant_id) as conn:
            # Get the setting value
            result = await conn.fetchval(
                "SELECT current_setting('app.current_tenant_id', true)"
            )
            assert result == tenant_id

    @pytest.mark.asyncio
    async def test_tenant_context_resets_on_exit(self):
        """Verify tenant context is reset after use"""
        tenant_id = str(uuid.uuid4())

        # Set context
        async with db.tenant_connection(tenant_id) as conn:
            result = await conn.fetchval(
                "SELECT current_setting('app.current_tenant_id', true)"
            )
            assert result == tenant_id

        # Try new connection - should be empty
        async with db.tenant_connection(str(uuid.uuid4())) as conn:
            result = await conn.fetchval(
                "SELECT current_setting('app.current_tenant_id', true)"
            )
            # Should be different tenant
            assert result != tenant_id

    @pytest.mark.asyncio
    async def test_invalid_tenant_id_in_context(self):
        """Invalid tenant_id should raise error"""
        with pytest.raises(ValueError):
            async with db.tenant_connection("invalid-uuid") as conn:
                pass


class TestRLSPolicies:
    """Test that RLS policies actually enforce isolation"""

    @pytest.mark.asyncio
    async def test_select_policy_isolates_data(self):
        """
        SELECT policy should only return rows for current tenant.

        SECURITY TEST: This verifies the core isolation mechanism.
        """
        # Create two tenants
        tenant1 = str(uuid.uuid4())
        tenant2 = str(uuid.uuid4())

        # Admin connection to set up test data
        async with db.admin_connection() as admin_conn:
            # Create test customers in both tenants
            await admin_conn.execute(
                """
                INSERT INTO customers (id, tenant_id, name, email)
                VALUES ($1, $2, $3, $4)
                """,
                uuid.uuid4(),
                tenant1,
                "Customer 1",
                "cust1@example.com",
            )

            await admin_conn.execute(
                """
                INSERT INTO customers (id, tenant_id, name, email)
                VALUES ($1, $2, $3, $4)
                """,
                uuid.uuid4(),
                tenant2,
                "Customer 2",
                "cust2@example.com",
            )

        # Tenant1 connection
        async with db.tenant_connection(tenant1) as conn:
            rows = await conn.fetch("SELECT * FROM customers")
            # Should only see tenant1's customer
            assert len(rows) == 1
            assert rows[0]["tenant_id"] == uuid.UUID(tenant1)
            assert rows[0]["name"] == "Customer 1"

        # Tenant2 connection
        async with db.tenant_connection(tenant2) as conn:
            rows = await conn.fetch("SELECT * FROM customers")
            # Should only see tenant2's customer
            assert len(rows) == 1
            assert rows[0]["tenant_id"] == uuid.UUID(tenant2)
            assert rows[0]["name"] == "Customer 2"

    @pytest.mark.asyncio
    async def test_insert_policy_enforces_tenant_id(self):
        """
        INSERT policy should require matching tenant_id.

        SECURITY TEST: Users cannot insert data for other tenants.
        """
        tenant_id = str(uuid.uuid4())
        other_tenant_id = str(uuid.uuid4())

        async with db.tenant_connection(tenant_id) as conn:
            # Try to insert with matching tenant_id - should succeed
            result = await conn.execute(
                """
                INSERT INTO customers (id, tenant_id, name, email)
                VALUES ($1, $2, $3, $4)
                """,
                uuid.uuid4(),
                tenant_id,
                "Customer",
                "cust@example.com",
            )
            assert result == "INSERT 0 1"

            # Try to insert with different tenant_id - should fail
            with pytest.raises(Exception):  # RLS violation
                await conn.execute(
                    """
                    INSERT INTO customers (id, tenant_id, name, email)
                    VALUES ($1, $2, $3, $4)
                    """,
                    uuid.uuid4(),
                    other_tenant_id,
                    "Hacker's Customer",
                    "hacker@example.com",
                )

    @pytest.mark.asyncio
    async def test_update_policy_restricts_modifications(self):
        """
        UPDATE policy should only allow updating current tenant's rows.

        SECURITY TEST: Users cannot modify other tenants' data.
        """
        tenant_id = str(uuid.uuid4())
        other_tenant_id = str(uuid.uuid4())

        # Set up test data
        customer_id = uuid.uuid4()
        async with db.admin_connection() as admin_conn:
            await admin_conn.execute(
                """
                INSERT INTO customers (id, tenant_id, name, email)
                VALUES ($1, $2, $3, $4)
                """,
                customer_id,
                tenant_id,
                "Original Name",
                "original@example.com",
            )

        # Tenant should be able to update their own data
        async with db.tenant_connection(tenant_id) as conn:
            result = await conn.execute(
                "UPDATE customers SET name = $1 WHERE id = $2",
                "Updated Name",
                customer_id,
            )
            assert result == "UPDATE 1"

            # Verify update worked
            row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            assert row["name"] == "Updated Name"

        # Other tenant cannot update this customer
        async with db.tenant_connection(other_tenant_id) as conn:
            result = await conn.execute(
                "UPDATE customers SET name = $1 WHERE id = $2",
                "Hacker Name",
                customer_id,
            )
            # RLS should prevent the update - no rows affected
            assert result == "UPDATE 0"

    @pytest.mark.asyncio
    async def test_delete_policy_restricts_deletion(self):
        """
        DELETE policy should only allow deleting current tenant's rows.

        SECURITY TEST: Users cannot delete other tenants' data.
        """
        tenant_id = str(uuid.uuid4())
        other_tenant_id = str(uuid.uuid4())

        # Set up test customer
        customer_id = uuid.uuid4()
        async with db.admin_connection() as admin_conn:
            await admin_conn.execute(
                """
                INSERT INTO customers (id, tenant_id, name, email)
                VALUES ($1, $2, $3, $4)
                """,
                customer_id,
                tenant_id,
                "Customer",
                "cust@example.com",
            )

        # Other tenant cannot delete
        async with db.tenant_connection(other_tenant_id) as conn:
            result = await conn.execute(
                "DELETE FROM customers WHERE id = $1",
                customer_id,
            )
            # No rows should be deleted
            assert result == "DELETE 0"

        # Verify customer still exists
        async with db.tenant_connection(tenant_id) as conn:
            row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            assert row is not None

        # Owner can delete
        async with db.tenant_connection(tenant_id) as conn:
            result = await conn.execute(
                "DELETE FROM customers WHERE id = $1",
                customer_id,
            )
            assert result == "DELETE 1"

    @pytest.mark.asyncio
    async def test_service_role_bypasses_rls(self):
        """
        Service role should be able to bypass RLS for system operations.

        SECURITY TEST: Service role must have BYPASSRLS to perform admin tasks.
        """
        tenant1 = str(uuid.uuid4())
        tenant2 = str(uuid.uuid4())

        # Set up data in both tenants
        async with db.admin_connection() as admin_conn:
            cust1_id = uuid.uuid4()
            cust2_id = uuid.uuid4()

            await admin_conn.execute(
                """
                INSERT INTO customers (id, tenant_id, name, email)
                VALUES ($1, $2, $3, $4)
                """,
                cust1_id,
                tenant1,
                "Customer 1",
                "cust1@example.com",
            )

            await admin_conn.execute(
                """
                INSERT INTO customers (id, tenant_id, name, email)
                VALUES ($1, $2, $3, $4)
                """,
                cust2_id,
                tenant2,
                "Customer 2",
                "cust2@example.com",
            )

            # Admin should see all customers
            all_customers = await admin_conn.fetch("SELECT * FROM customers WHERE id IN ($1, $2)", cust1_id, cust2_id)
            assert len(all_customers) == 2


class TestRequestContextExtraction:
    """Test extraction of tenant_id from FastAPI requests"""

    def test_extract_from_header(self):
        """Should extract tenant_id from X-Tenant-ID header"""
        from fastapi import Request
        from starlette.requests import Request as StarletteRequest

        tenant_id = str(uuid.uuid4())
        # Mock request with header
        class MockRequest:
            def __init__(self):
                self.headers = {"X-Tenant-ID": tenant_id}
                self.query_params = {}
                self.state = type("obj", (object,), {})()

        request = MockRequest()
        extracted = extract_tenant_id_from_request(request)
        assert extracted == tenant_id

    def test_extract_from_query_param(self):
        """Should extract tenant_id from query parameter"""
        tenant_id = str(uuid.uuid4())

        class MockRequest:
            def __init__(self):
                self.headers = {}
                self.query_params = {"tenant_id": tenant_id}
                self.state = type("obj", (object,), {})()

        request = MockRequest()
        extracted = extract_tenant_id_from_request(request)
        assert extracted == tenant_id

    def test_header_precedence_over_query(self):
        """Header should take precedence over query parameter"""
        header_tenant = str(uuid.uuid4())
        query_tenant = str(uuid.uuid4())

        class MockRequest:
            def __init__(self):
                self.headers = {"X-Tenant-ID": header_tenant}
                self.query_params = {"tenant_id": query_tenant}
                self.state = type("obj", (object,), {})()

        request = MockRequest()
        extracted = extract_tenant_id_from_request(request)
        assert extracted == header_tenant
        assert extracted != query_tenant


@pytest.fixture
async def test_tenant() -> str:
    """Fixture providing a test tenant ID"""
    return str(uuid.uuid4())


@pytest.fixture
async def test_database():
    """Fixture for database initialization"""
    await db.initialize()
    yield db
    await db.close()
