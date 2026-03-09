# RLS Quick Start Guide

## Files Created

### 1. Migration File
**Location**: `shared/migrations/alembic/versions/011_row_level_security.py`

This migration:
- Enables RLS on 50+ tenant-scoped tables
- Creates 4 policies per table (SELECT, INSERT, UPDATE, DELETE)
- Creates `priya_service_role` with BYPASSRLS
- Can be rolled back if needed

### 2. RLS Helper Module
**Location**: `shared/core/rls.py`

Provides:
- `validate_tenant_id()` - UUID validation
- `tenant_context()` - Context manager for setting tenant scope
- `tenant_query_context()` - Convenience method combining both
- `extract_tenant_id_from_request()` - FastAPI integration
- `TenantIsolationMiddleware` - Automatic tenant extraction
- `require_tenant_context()` - Assert tenant in request
- Utility functions for tenant info and access verification

### 3. Test Suite
**Location**: `shared/tests/test_rls.py`

Tests:
- Tenant ID validation
- Tenant context management
- RLS SELECT policy isolation
- RLS INSERT policy enforcement
- RLS UPDATE policy restrictions
- RLS DELETE policy restrictions
- Service role BYPASSRLS
- Request context extraction

### 4. Documentation
**Location**: `docs/RLS_IMPLEMENTATION.md` (comprehensive)
**Location**: `docs/RLS_QUICK_START.md` (this file)

## Installation Steps

### Step 1: Run Migration

```bash
# In project root
alembic upgrade head

# Or specific revision
alembic upgrade 011_row_level_security
```

This will:
1. Enable RLS on all tables
2. Create isolation policies
3. Create priya_service_role
4. Grant permissions

### Step 2: Update FastAPI Setup

Add middleware in your main app file (e.g., `services/api/main.py`):

```python
from fastapi import FastAPI
from shared.core.rls import TenantIsolationMiddleware

app = FastAPI()

# Add early in middleware stack
app.add_middleware(TenantIsolationMiddleware)

# ... rest of your setup
```

### Step 3: Update Database Connection

No changes needed! The existing `TenantDatabase` class already:
- Sets `app.current_tenant_id` in `tenant_connection()`
- Resets it after use
- Has proper transaction handling

### Step 4: Update Route Handlers

**Before**:
```python
@router.get("/customers")
async def list_customers():
    # Manually manages tenant isolation
    tenant_id = get_tenant_from_context()
    async with db.tenant_connection(tenant_id) as conn:
        customers = await conn.fetch("SELECT * FROM customers")
    return customers
```

**After**:
```python
from shared.core.rls import require_tenant_context

@router.get("/customers")
async def list_customers(request: Request):
    # Middleware already extracted tenant_id
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        customers = await conn.fetch("SELECT * FROM customers")
    return customers
```

### Step 5: Run Tests

```bash
# Test RLS functionality
pytest shared/tests/test_rls.py -v

# Test your routes still work
pytest tests/ -v
```

## Common Patterns

### Getting Data for Current Tenant

```python
from shared.core.rls import require_tenant_context

@router.get("/api/customers")
async def list_customers(request: Request):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        return await conn.fetch("SELECT * FROM customers")
    # RLS automatically filters to this tenant
```

### Creating Data for Current Tenant

```python
@router.post("/api/customers")
async def create_customer(request: Request, data: CustomerCreate):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        customer = await conn.fetchrow(
            """
            INSERT INTO customers (id, tenant_id, name, email)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            uuid.uuid4(),
            tenant_id,  # Always set from context
            data.name,
            data.email
        )
    return customer
```

### Admin Operations (Cross-Tenant)

```python
from shared.core.database import db

@router.get("/admin/all-customers")
async def admin_list_all_customers(request: Request):
    # Check admin permission first!
    verify_admin(request)

    # Use admin connection to bypass RLS
    async with db.admin_connection() as conn:
        return await conn.fetch("SELECT * FROM customers")
```

### Manual Tenant Context (Advanced)

```python
from shared.core.rls import tenant_context

async with db.tenant_connection(tenant_id) as conn:
    async with tenant_context(conn, tenant_id):
        # Explicit validation and context management
        customers = await conn.fetch("SELECT * FROM customers")
```

## Security Checklist

- [ ] Migration 011 has been run in database
- [ ] All route handlers using `require_tenant_context()`
- [ ] TenantIsolationMiddleware added to FastAPI app
- [ ] No uses of `db.admin_connection()` in user-facing endpoints
- [ ] Tests in `shared/tests/test_rls.py` pass
- [ ] No tenant_id bypasses in application code
- [ ] All INSERT operations include `tenant_id` column
- [ ] All UPDATE operations check tenant_id
- [ ] All DELETE operations check tenant_id

## Verifying RLS is Working

### In PostgreSQL

```sql
-- Check RLS is enabled
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

-- Check policies exist
SELECT tablename, policyname, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename;

-- Verify service role
SELECT rolname, bypassrls
FROM pg_roles
WHERE rolname = 'priya_service_role';
```

### In Python Tests

```bash
pytest shared/tests/test_rls.py::TestRLSPolicies -v

# All tests should pass:
# - test_select_policy_isolates_data
# - test_insert_policy_enforces_tenant_id
# - test_update_policy_restricts_modifications
# - test_delete_policy_restricts_deletion
# - test_service_role_bypasses_rls
```

## Troubleshooting

### "Error: relation X does not exist"

The table might not have the tenant_id column yet. Check:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'x' AND column_name = 'tenant_id';
```

### "permission denied for relation X"

RLS denied the operation. Verify:
1. tenant_id is set correctly
2. Row belongs to this tenant
3. Using correct tenant_id in connection

```python
async with db.tenant_connection(tenant_id) as conn:
    current = await conn.fetchval("SELECT current_setting('app.current_tenant_id')")
    print(f"Set to: {current}, Expected: {tenant_id}")
```

### "Tenant context not found"

Middleware isn't extracting tenant_id. Check:
1. Header sent: `X-Tenant-ID: <uuid>`
2. Middleware is registered in FastAPI
3. Request has tenant context

```python
# Add to route to debug
@router.get("/debug")
async def debug(request: Request):
    return {
        "tenant_id": getattr(request.state, "tenant_id", None),
        "headers": dict(request.headers),
    }
```

## Performance Notes

- RLS adds < 1% overhead for most queries
- Indexes on (tenant_id, other_columns) recommended
- No special optimization needed in application code

## Next Steps

1. **Read**: `docs/RLS_IMPLEMENTATION.md` for comprehensive guide
2. **Test**: Run `pytest shared/tests/test_rls.py`
3. **Implement**: Update all routes to use RLS
4. **Monitor**: Check logs for RLS-related errors
5. **Document**: Update your API docs with tenant_id requirements

## Support

For questions about RLS:
- Check `docs/RLS_IMPLEMENTATION.md` for detailed info
- Review example code in route handlers
- Run tests to verify your implementation
- Check PostgreSQL RLS documentation: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
