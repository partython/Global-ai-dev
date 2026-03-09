# Row Level Security (RLS) Implementation Guide

## Overview

Priya Global implements PostgreSQL Row Level Security (RLS) for complete multi-tenant data isolation. RLS enforces tenant boundaries at the **database layer**, ensuring that even if application code has bugs, data cannot leak between tenants.

This document explains:
- How RLS works in Priya Global
- How to use RLS in your code
- Security guarantees and limitations
- Troubleshooting

## Architecture

### Security Model

Every database table has:
1. **tenant_id column** - identifies which tenant owns the row
2. **RLS policies** - PostgreSQL enforces filtering based on current tenant
3. **app.current_tenant_id setting** - set per request, used by RLS policies

When a request arrives:
```
Request → Extract tenant_id from header/JWT
         → Set app.current_tenant_id in database
         → Execute all queries
         → All queries automatically filtered by RLS policies
         → Reset app.current_tenant_id
```

### RLS Policy Structure

For each tenant-scoped table, four policies are created:

```sql
-- SELECT: Users can only see their tenant's rows
CREATE POLICY table_tenant_isolation_select ON table_name
    FOR SELECT
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- INSERT: Users can only insert with their tenant_id
CREATE POLICY table_tenant_isolation_insert ON table_name
    FOR INSERT
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- UPDATE: Users can only modify their tenant's rows
CREATE POLICY table_tenant_isolation_update ON table_name
    FOR UPDATE
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- DELETE: Users can only delete their tenant's rows
CREATE POLICY table_tenant_isolation_delete ON table_name
    FOR DELETE
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

## Tables with RLS

The following 48 tables have RLS enabled:

### Core Tables
- `tenants`, `users`, `customers`
- `conversations`, `messages`
- `orders`, `products`
- `knowledge_base`

### Security & Compliance
- `audit_log`, `detailed_audit_logs`
- `security_events`, `compliance_reports`
- `consent_records`, `data_deletion_requests`

### Features
- `api_keys`, `refresh_tokens`
- `handoffs`
- `csat_ratings`
- `funnel_events`
- `nurturing_sequences`
- `ab_experiments`
- `ecommerce_connections`
- `channel_connections`

### Internationalization
- `localization_strings`, `country_settings`
- `currency_rates`, `tax_configurations`

### Onboarding & Analytics
- `onboarding_progress`, `onboarding_analytics`

### Advanced Features
- `conversation_memories`, `customer_memories`
- `memory_episodes`, `conversation_turns`
- `plugins`, `plugin_configs`
- `plugin_analytics`, `plugin_api_keys`
- `plugin_event_logs`, `plugin_resource_usage`
- `plugin_subscriptions`
- `sms_messages`, `sms_opt_outs`, `sms_templates`
- `rest_connectors`, `rest_endpoints`
- `rest_field_mappings`, `rest_sync_logs`
- `translation_glossary`, `translation_audit_log`

### Additional Tables
- `ai_configurations`
- `channel_configurations`

## Usage in Python Code

### Basic Query

```python
from shared.core.database import db

# Automatic tenant isolation - RLS does the filtering
async with db.tenant_connection(tenant_id) as conn:
    customers = await conn.fetch(
        "SELECT * FROM customers WHERE active = TRUE"
    )
    # Only returns THIS tenant's active customers due to RLS
```

### With Tenant Context Manager

```python
from shared.core.rls import tenant_context

async with db.tenant_connection(tenant_id) as conn:
    # Validate tenant_id and set context
    async with tenant_context(conn, tenant_id):
        customer = await conn.fetchrow(
            "SELECT * FROM customers WHERE id = $1",
            customer_id
        )
        # RLS ensures we only got a row if it belongs to tenant_id
```

### Convenience Method

```python
from shared.core.rls import tenant_query_context

# Combines both: tenant_connection + tenant_context
async with tenant_query_context(tenant_id) as conn:
    messages = await conn.fetch(
        "SELECT * FROM messages WHERE conversation_id = $1",
        conversation_id
    )
    # RLS automatically applies
```

## Usage in FastAPI Routes

### Automatic Tenant Extraction

```python
from fastapi import APIRouter, Request
from shared.core.rls import require_tenant_context

router = APIRouter()

@router.get("/customers")
async def list_customers(request: Request):
    # Middleware automatically extracts and validates tenant_id
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        customers = await conn.fetch("SELECT * FROM customers")
        return customers
```

### Manual Tenant Extraction

```python
from fastapi import APIRouter, Request, HTTPException
from shared.core.rls import extract_tenant_id_from_request

router = APIRouter()

@router.get("/customers")
async def list_customers(request: Request):
    tenant_id = extract_tenant_id_from_request(request)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant ID")

    async with db.tenant_connection(tenant_id) as conn:
        customers = await conn.fetch("SELECT * FROM customers")
        return customers
```

### With Header

```bash
# Send requests with X-Tenant-ID header
curl -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
     http://localhost/api/customers
```

## Admin Operations

### Reading Cross-Tenant Data

For system admin operations that need to see all tenants' data:

```python
from shared.core.database import db

async with db.admin_connection() as conn:
    # This connection bypasses RLS
    all_customers = await conn.fetch("SELECT * FROM customers")
    # Returns customers from ALL tenants
```

**SECURITY WARNING**: Only use `admin_connection()` for:
- System maintenance
- Cross-tenant analytics (aggregated, never raw data)
- Tenant creation/deletion
- **Never expose admin_connection to tenant-facing endpoints**

### Service Role Operations

For backend services that need limited cross-tenant access:

```sql
-- priya_service_role is created with BYPASSRLS permission
-- Grant it minimal permissions needed for your operation

GRANT SELECT, INSERT ON conversations TO priya_service_role;

-- Backend service can now bypass RLS while still being restricted
-- to specific tables and operations
```

## Request Flow Example

### Request Arrives

```
POST /api/customers
X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000
Body: {"name": "Acme Corp"}
```

### Middleware Processes

1. Extract tenant_id from header: `550e8400-e29b-41d4-a716-446655440000`
2. Validate it's a valid UUID ✓
3. Store in request.state.tenant_id
4. Route handler receives request

### Route Handler Executes

```python
@router.post("/customers")
async def create_customer(request: Request, data: CustomerCreate):
    tenant_id = require_tenant_context(request)  # Gets from state

    async with db.tenant_connection(tenant_id) as conn:
        # Sets app.current_tenant_id = '550e8400-...'

        await conn.execute(
            """
            INSERT INTO customers (id, tenant_id, name, email)
            VALUES ($1, $2, $3, $4)
            """,
            uuid.uuid4(),
            tenant_id,
            data.name,
            data.email
        )
        # RLS policy checks: tenant_id = current_setting('app.current_tenant_id')
        # ✓ Matches! Insert succeeds
```

### Result

✓ Row inserted with correct tenant_id
✓ Other tenants cannot see it (SELECT policy)
✓ Other tenants cannot modify it (UPDATE policy)
✓ Other tenants cannot delete it (DELETE policy)

## Security Guarantees

### What RLS Protects Against

1. **SQL Injection** - Even if SQL injection occurs, RLS filters results
2. **Logic Bugs** - If app code forgets tenant_id check, RLS still enforces it
3. **Privilege Escalation** - Table owners cannot bypass RLS (FORCE applied)
4. **Accidental Data Leaks** - Cross-tenant joins impossible with RLS active

### Example: SQL Injection

```python
# Vulnerable code - SQL injection + missing tenant check
@router.get("/customer/{id}")
async def get_customer(request: Request, id: str):
    tenant_id = require_tenant_context(request)

    # VULNERABLE: No parameterization
    query = f"SELECT * FROM customers WHERE id = '{id}'"
    async with db.tenant_connection(tenant_id) as conn:
        customer = await conn.fetch(query)
    return customer
```

Without RLS: Attacker can inject SQL to get other customers
```sql
id = 'xxx' OR 1=1; --
-- Returns ALL customers from this tenant
```

With RLS: Attacker still can't get other tenants' data
```sql
-- PostgreSQL internally becomes:
SELECT * FROM customers
WHERE (id = 'xxx' OR 1=1)
AND (tenant_id = current_setting('app.current_tenant_id')::uuid)
-- Only this tenant's customers returned, even with injection
```

## Troubleshooting

### "permission denied for relation X"

RLS policy denied the operation. Check:
1. Is tenant_id set correctly?
2. Does the row belong to current tenant?
3. Are you using correct tenant_id in the query?

```python
# Debug: Check what tenant_id is currently set
async with db.tenant_connection(tenant_id) as conn:
    current_tenant = await conn.fetchval(
        "SELECT current_setting('app.current_tenant_id')"
    )
    print(f"Current tenant: {current_tenant}")
    print(f"Requested tenant: {tenant_id}")
```

### Query Returns Empty When It Should Return Data

Common causes:
1. tenant_id in database doesn't match current_setting
2. No tenant_id set (SET LOCAL not called)
3. Wrong tenant_id passed to connection

```python
# Debug: Verify row exists and belongs to this tenant
async with db.admin_connection() as admin_conn:
    row = await admin_conn.fetchrow(
        "SELECT id, tenant_id FROM customers WHERE id = $1",
        customer_id
    )
    if row:
        print(f"Row exists with tenant_id: {row['tenant_id']}")
        print(f"Current tenant_id: {tenant_id}")
```

### RLS Policies Not Applied

Check:
1. Is RLS enabled? `ALTER TABLE table ENABLE ROW LEVEL SECURITY`
2. Are policies created? `SELECT * FROM pg_policies WHERE tablename = 'table'`
3. Is FORCE applied? `ALTER TABLE table FORCE ROW LEVEL SECURITY`

```sql
-- Check RLS status
SELECT tablename, rowsecurity FROM pg_tables
WHERE schemaname = 'public' AND tablename = 'customers';

-- Check policies
SELECT * FROM pg_policies WHERE tablename = 'customers';
```

## Performance Considerations

### RLS Overhead

- **Minimal** for most operations (< 1% overhead)
- RLS just adds WHERE clause conditions
- Modern PostgreSQL optimizes these effectively

### Indexing

RLS works best with proper indexes. All tenant-scoped tables should have:

```sql
-- Composite index for common patterns
CREATE INDEX idx_table_tenant_id ON table_name(tenant_id, other_column);

-- Speeds up RLS filtering
```

### Cross-Tenant Joins

RLS prevents accidentally joining across tenants:

```sql
SELECT c.*, o.*
FROM customers c
JOIN orders o ON c.id = o.customer_id
-- Both tables have RLS - both filtered by tenant_id automatically
```

## Maintenance

### Adding RLS to New Tables

1. Add tenant_id column to table
2. Add foreign key to tenants table
3. Re-run migration 011 (or create new migration)
4. Verify policies are created

```python
# In migration
op.execute("""
    ALTER TABLE new_table ENABLE ROW LEVEL SECURITY;
    ALTER TABLE new_table FORCE ROW LEVEL SECURITY;

    CREATE POLICY new_table_tenant_isolation_select ON new_table
        FOR SELECT
        USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
    -- ... other policies ...
""")
```

### Modifying RLS Policies

Never modify policies directly in production. Instead:

1. Create new migration
2. Drop old policy
3. Create new policy with different logic
4. Test thoroughly

```python
def upgrade():
    op.execute("""
        DROP POLICY IF EXISTS table_old_policy ON table_name;

        CREATE POLICY table_new_policy ON table_name
            FOR SELECT
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
    """)

def downgrade():
    op.execute("""
        DROP POLICY IF EXISTS table_new_policy ON table_name;

        CREATE POLICY table_old_policy ON table_name
            FOR SELECT
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
    """)
```

### Testing RLS Changes

```python
# Always test in development first
pytest shared/tests/test_rls.py -v

# Verify no data leaks
# Verify performance doesn't degrade
# Verify admin connections still work
```

## Limitations & Edge Cases

### Superusers

PostgreSQL superusers bypass RLS by default. In Priya Global:
- Database superuser should **never** be used by application
- Use service role for backend operations
- Use tenant connection for user operations

### Triggers and Functions

RLS applies to:
- Direct SELECT, INSERT, UPDATE, DELETE
- Indirect operations via triggers

RLS does **not** apply to:
- Functions with SECURITY DEFINER (run as function owner)
- Operations inside PL/pgSQL functions marked SECURITY DEFINER

**Best Practice**: Use SECURITY INVOKER (default) for all user functions

### Cascading Operations

Foreign key cascades respect RLS:

```python
# Delete customer
async with db.tenant_connection(tenant_id) as conn:
    await conn.execute("DELETE FROM customers WHERE id = $1", customer_id)
    # Foreign key cascade (orders → customers) respects RLS
    # Only deletes orders that match both tenant_id AND customer_id
```

## Security Best Practices

1. **Always validate tenant_id is a valid UUID**
   ```python
   validate_tenant_id(tenant_id)
   ```

2. **Always set tenant context before queries**
   ```python
   async with db.tenant_connection(tenant_id) as conn:
       # tenant_id is SET LOCAL here
   ```

3. **Never use admin_connection in user-facing endpoints**
   ```python
   # WRONG - allows any user to see all data
   async with db.admin_connection() as conn:
       customers = await conn.fetch("SELECT * FROM customers")

   # CORRECT - only this tenant's data
   async with db.tenant_connection(tenant_id) as conn:
       customers = await conn.fetch("SELECT * FROM customers")
   ```

4. **Log tenant context changes for audit**
   ```python
   logger.info(f"Tenant context set: {tenant_id}")
   ```

5. **Test with multiple tenants in security tests**
   ```python
   @pytest.mark.asyncio
   async def test_isolation(self):
       tenant1 = create_tenant()
       tenant2 = create_tenant()
       # Verify tenant1 cannot see tenant2's data
   ```

## References

- Migration file: `shared/migrations/alembic/versions/011_row_level_security.py`
- RLS helper module: `shared/core/rls.py`
- Database module: `shared/core/database.py`
- Tests: `shared/tests/test_rls.py`
- PostgreSQL RLS docs: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
