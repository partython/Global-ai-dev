# RLS Integration Examples

Real-world examples of using RLS in Priya Global services.

## Example 1: Conversation Service

### Without RLS (Old Way)

```python
# services/conversation/api.py
from fastapi import APIRouter, Request, HTTPException
from shared.core.database import db

router = APIRouter()

@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str):
    # Manually extract tenant_id
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant ID")

    # Manually check tenant_id in query
    async with db.tenant_connection(tenant_id) as conn:
        conversation = await conn.fetchrow(
            """
            SELECT * FROM conversations
            WHERE id = $1 AND tenant_id = $2
            """,
            conversation_id,
            tenant_id
        )

    if not conversation:
        raise HTTPException(status_code=404, detail="Not found")

    return conversation
```

**Problems**:
- Manual tenant_id extraction in every route
- Manual tenant_id check in every query
- Risk of forgetting the check

### With RLS (New Way)

```python
# services/conversation/api.py
from fastapi import APIRouter, Request, HTTPException
from shared.core.rls import require_tenant_context
from shared.core.database import db

router = APIRouter()

@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str):
    # Tenant_id extracted and validated by middleware
    tenant_id = require_tenant_context(request)

    # RLS handles the filtering automatically
    async with db.tenant_connection(tenant_id) as conn:
        conversation = await conn.fetchrow(
            "SELECT * FROM conversations WHERE id = $1",
            conversation_id
        )

    if not conversation:
        raise HTTPException(status_code=404, detail="Not found")

    return conversation
```

**Benefits**:
- Simpler, cleaner code
- RLS enforces isolation at DB level
- Even if you forget the WHERE clause, RLS filters it
- Automatic across all tables

## Example 2: Customer Service

### Create Customer

```python
# services/customer/api.py
from fastapi import APIRouter, Request
from pydantic import BaseModel
import uuid

from shared.core.rls import require_tenant_context
from shared.core.database import db

router = APIRouter()

class CustomerCreate(BaseModel):
    name: str
    email: str
    phone: str = None

@router.post("/customers")
async def create_customer(request: Request, data: CustomerCreate):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        customer = await conn.fetchrow(
            """
            INSERT INTO customers (id, tenant_id, name, email, phone)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            uuid.uuid4(),
            tenant_id,  # Always from request context
            data.name,
            data.email,
            data.phone
        )

    return customer
```

### List Customers with Pagination

```python
from typing import Optional

@router.get("/customers")
async def list_customers(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None
):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        # Build query
        where_clause = "WHERE 1=1"
        params = []

        if search:
            where_clause += " AND (name ILIKE $1 OR email ILIKE $1)"
            params.append(f"%{search}%")

        # RLS automatically adds: AND tenant_id = current_setting(...)
        query = f"""
            SELECT * FROM customers
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {limit} OFFSET {skip}
        """

        customers = await conn.fetch(query, *params)

    return customers
```

### Update Customer

```python
@router.put("/customers/{customer_id}")
async def update_customer(request: Request, customer_id: str, data: CustomerCreate):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        # RLS ensures we can only update this tenant's customers
        customer = await conn.fetchrow(
            """
            UPDATE customers
            SET name = $1, email = $2, phone = $3, updated_at = NOW()
            WHERE id = $4
            RETURNING *
            """,
            data.name,
            data.email,
            data.phone,
            customer_id
        )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return customer
```

### Delete Customer

```python
@router.delete("/customers/{customer_id}")
async def delete_customer(request: Request, customer_id: str):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        # RLS prevents deleting other tenants' customers
        result = await conn.execute(
            "DELETE FROM customers WHERE id = $1",
            customer_id
        )

    # Check if anything was deleted
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Customer not found")

    return {"status": "deleted"}
```

## Example 3: Message/Conversation Thread

### Create Message in Conversation

```python
from datetime import datetime
from enum import Enum

class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"

@router.post("/conversations/{conversation_id}/messages")
async def create_message(
    request: Request,
    conversation_id: str,
    content: str,
    role: MessageRole = MessageRole.USER
):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        # Verify conversation belongs to this tenant
        conversation = await conn.fetchrow(
            "SELECT id FROM conversations WHERE id = $1",
            conversation_id
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Create message
        # RLS ensures message has correct tenant_id
        message = await conn.fetchrow(
            """
            INSERT INTO messages
            (id, tenant_id, conversation_id, content, role, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            uuid.uuid4(),
            tenant_id,  # From request context
            conversation_id,
            content,
            role,
            datetime.utcnow()
        )

    return message
```

### Get Conversation Thread

```python
@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_thread(
    request: Request,
    conversation_id: str,
    limit: int = 50
):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        messages = await conn.fetch(
            """
            SELECT * FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            conversation_id,
            limit
        )

    return messages
    # RLS ensures we only get messages from this tenant
```

## Example 4: Multi-Tenant Analytics

### Tenant-Scoped Analytics

```python
# services/analytics/api.py
from fastapi import APIRouter, Request
from datetime import datetime, timedelta

from shared.core.rls import require_tenant_context
from shared.core.database import db

router = APIRouter()

@router.get("/analytics/conversation-metrics")
async def get_conversation_metrics(
    request: Request,
    start_date: str,
    end_date: str
):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        metrics = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total_conversations,
                AVG(duration_seconds) as avg_duration,
                SUM(CASE WHEN outcome = 'resolved' THEN 1 ELSE 0 END) as resolved_count
            FROM conversations
            WHERE created_at BETWEEN $1::timestamp AND $2::timestamp
            """,
            start_date,
            end_date
        )

    return metrics
    # RLS automatically filters to this tenant only!
```

### Cross-Tenant Analytics (Admin Only)

```python
from shared.core.database import db

@router.get("/admin/analytics/all-tenants")
async def admin_get_cross_tenant_analytics(request: Request):
    # Verify admin permission
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="Admin only")

    # Use admin connection to bypass RLS
    async with db.admin_connection() as conn:
        metrics = await conn.fetchrow(
            """
            SELECT
                COUNT(DISTINCT tenant_id) as total_tenants,
                COUNT(*) as total_conversations,
                AVG(duration_seconds) as avg_duration
            FROM conversations
            """
        )

    return metrics
```

## Example 5: Bulk Operations with RLS

### Bulk Create

```python
@router.post("/bulk-import/customers")
async def bulk_import_customers(request: Request, customers: list[CustomerCreate]):
    tenant_id = require_tenant_context(request)

    async with db.transaction(tenant_id) as conn:
        results = []

        for customer_data in customers:
            customer = await conn.fetchrow(
                """
                INSERT INTO customers (id, tenant_id, name, email, phone)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                uuid.uuid4(),
                tenant_id,
                customer_data.name,
                customer_data.email,
                customer_data.phone
            )
            results.append(customer)

        # All inserts in single transaction
        # RLS checked for each row

    return results
```

### Bulk Update

```python
@router.put("/bulk/customers/status")
async def bulk_update_customer_status(
    request: Request,
    customer_ids: list[str],
    status: str
):
    tenant_id = require_tenant_context(request)

    async with db.transaction(tenant_id) as conn:
        # RLS ensures we can only update this tenant's customers
        result = await conn.execute(
            """
            UPDATE customers
            SET status = $1, updated_at = NOW()
            WHERE id = ANY($2)
            """,
            status,
            customer_ids
        )

        return {"updated": result.split()[-1]}  # Extract count
```

## Example 6: Error Handling with RLS

### Proper Error Handling

```python
from fastapi import HTTPException

@router.get("/customers/{customer_id}")
async def get_customer(request: Request, customer_id: str):
    tenant_id = require_tenant_context(request)

    try:
        async with db.tenant_connection(tenant_id) as conn:
            customer = await conn.fetchrow(
                "SELECT * FROM customers WHERE id = $1",
                customer_id
            )

        if not customer:
            # Return 404 whether customer doesn't exist or belongs to other tenant
            # (Don't leak which it is)
            raise HTTPException(status_code=404, detail="Customer not found")

        return customer

    except ValueError as e:
        # Tenant validation error
        raise HTTPException(status_code=400, detail="Invalid tenant context")
    except Exception as e:
        logger.error(f"Failed to get customer: {e}")
        raise HTTPException(status_code=500, detail="Internal error")
```

## Example 7: Middleware Usage

### In Main App

```python
# main.py
from fastapi import FastAPI
from shared.core.rls import TenantIsolationMiddleware

app = FastAPI()

# Add middleware early in the stack
app.add_middleware(TenantIsolationMiddleware)

# Your routes now automatically have tenant context!
```

### Accessing in Routes

```python
from fastapi import Request
from shared.core.rls import require_tenant_context

@app.get("/current-tenant")
async def get_current_tenant_info(request: Request):
    tenant_id = require_tenant_context(request)

    # Middleware already extracted and validated it!
    return {"tenant_id": tenant_id}
```

## Example 8: Complex Queries with JOINs

### Multi-Table Query

```python
@router.get("/conversations/{conversation_id}/full")
async def get_conversation_with_details(
    request: Request,
    conversation_id: str
):
    tenant_id = require_tenant_context(request)

    async with db.tenant_connection(tenant_id) as conn:
        # Complex JOIN query
        # RLS applies to BOTH tables automatically
        conversation = await conn.fetchrow(
            """
            SELECT
                c.id,
                c.title,
                c.created_at,
                cust.name as customer_name,
                cust.email,
                COUNT(m.id) as message_count
            FROM conversations c
            JOIN customers cust ON c.customer_id = cust.id
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.id = $1
            GROUP BY c.id, cust.id
            """,
            conversation_id
        )
        # RLS filters:
        # - conversations: WHERE tenant_id = current_tenant
        # - customers: WHERE tenant_id = current_tenant
        # - messages: WHERE tenant_id = current_tenant
        # Impossible to leak cross-tenant data

    return conversation
```

## Example 9: Testing with RLS

### Unit Test Example

```python
# tests/test_customer_api.py
import pytest
import uuid

from shared.core.database import db
from services.customer.api import router

@pytest.mark.asyncio
async def test_customer_isolation():
    """Verify RLS prevents cross-tenant data access"""
    tenant1 = str(uuid.uuid4())
    tenant2 = str(uuid.uuid4())

    # Create customers in both tenants
    async with db.admin_connection() as admin:
        cust1_id = uuid.uuid4()
        cust2_id = uuid.uuid4()

        await admin.execute(
            "INSERT INTO customers (id, tenant_id, name, email) VALUES ($1, $2, $3, $4)",
            cust1_id, tenant1, "Customer 1", "cust1@example.com"
        )

        await admin.execute(
            "INSERT INTO customers (id, tenant_id, name, email) VALUES ($1, $2, $3, $4)",
            cust2_id, tenant2, "Customer 2", "cust2@example.com"
        )

    # Tenant1 queries
    async with db.tenant_connection(tenant1) as conn:
        rows = await conn.fetch("SELECT * FROM customers")
        assert len(rows) == 1
        assert str(rows[0]["id"]) == str(cust1_id)

    # Tenant2 queries
    async with db.tenant_connection(tenant2) as conn:
        rows = await conn.fetch("SELECT * FROM customers")
        assert len(rows) == 1
        assert str(rows[0]["id"]) == str(cust2_id)

    # Verify: Tenant1 cannot see Tenant2's customer
    async with db.tenant_connection(tenant1) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM customers WHERE id = $1",
            cust2_id
        )
        assert row is None  # RLS filtered it out!
```

## Best Practices Summary

1. **Always use `require_tenant_context(request)`**
   ```python
   tenant_id = require_tenant_context(request)
   ```

2. **Always pass tenant_id to `db.tenant_connection()`**
   ```python
   async with db.tenant_connection(tenant_id) as conn:
   ```

3. **Always include tenant_id in INSERT/UPDATE**
   ```python
   INSERT INTO table (id, tenant_id, ...)
   VALUES ($1, $2, ...)
   ```

4. **Use admin_connection only for admin operations**
   ```python
   async with db.admin_connection() as conn:
   ```

5. **Test with multiple tenants**
   ```python
   tenant1 = create_tenant()
   tenant2 = create_tenant()
   # Verify tenant1 can't see tenant2's data
   ```

6. **Log tenant operations for audit**
   ```python
   logger.info(f"Tenant {tenant_id} accessed customer {customer_id}")
   ```

7. **Return 404 for both "not found" and "not owned"**
   ```python
   if not row:
       raise HTTPException(status_code=404)  # Don't leak which!
   ```
