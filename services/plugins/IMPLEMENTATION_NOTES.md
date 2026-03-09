# Implementation Notes - Plugin SDK Service

## Architecture Highlights

### Multi-Tenant Design with Row-Level Security

```python
# Every table has tenant_id for isolation
async with db_pool.acquire() as conn:
    plugin = await conn.fetchrow("""
        SELECT * FROM plugins
        WHERE id = $1 AND tenant_id = $2  # RLS enforcement
    """, plugin_uuid, tenant_uuid)
```

### Secure API Key Handling

```python
# Keys are generated with UUID prefix and hashed for storage
def generate_api_key() -> str:
    return f"pk_{uuid.uuid4().hex}"

def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
```

### Webhook Signature Verification

```python
# HMAC-SHA256 with constant-time comparison
def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    expected = generate_webhook_signature(payload, secret)
    return hmac.compare_digest(expected, signature)  # Timing-safe comparison
```

### Exponential Backoff Retry

```python
# Automatic retry with exponential backoff
async def deliver_webhook(webhook_url, event, plugin_id, tenant_id, retry_count=0):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, ...) as resp:
                if resp.status >= 400:
                    raise Exception(f"HTTP {resp.status}")
                return True
    except Exception as e:
        if retry_count < MAX_RETRIES:
            await asyncio.sleep(2 ** retry_count)  # 2, 4, 8 seconds
            return await deliver_webhook(..., retry_count + 1)
        return False
```

### Async Database Operations

```python
# Connection pooling with async operations
db_pool = await asyncpg.create_pool(DB_URL, min_size=5, max_size=20)

async with db_pool.acquire() as conn:
    plugins = await conn.fetch("""
        SELECT * FROM plugins WHERE tenant_id = $1
    """, tenant_uuid)
```

## Database Design Decisions

### plugins table
- Marketplace plugins: `marketplace=true, tenant_id=NULL`
- Installed plugins: `marketplace=false, tenant_id=<tenant_uuid>`
- Status: draft, published, deprecated
- Unique constraint: (tenant_id, name, version)

### plugin_configs table
- Per-tenant configuration storage
- JSON support for flexible schema
- Unique constraint: (tenant_id, plugin_id)

### plugin_api_keys table
- Scoped keys: read-only, read-write, admin
- Rate limiting per key
- Expiration support
- Unique constraint: (tenant_id, plugin_id, scope)

### plugin_subscriptions table
- Plugin event subscriptions
- Webhook URL caching for performance
- Unique constraint: (tenant_id, plugin_id, event_type)

### plugin_event_logs table
- Event delivery tracking
- Retry count and error messages
- Status: pending, delivered, failed
- Useful for debugging and analytics

### plugin_resource_usage table
- API call counts
- Webhook call counts
- Error tracking
- Last-used timestamp for cleanup

### plugin_analytics table
- Time-series analytics per event type
- Success/failure counts
- Average latency metrics
- Date partitioning for efficient queries

### developers table
- Plugin developer accounts
- Unique email and API key constraints
- Company affiliation tracking

## Event Flow

### Event Emission
```
1. Client emits event via POST /api/v1/plugins/events/emit
2. Tenant and event type validated
3. Query for all active plugin subscriptions
4. Log event to plugin_event_logs
5. Queue webhooks for asynchronous delivery
6. Return with count of subscribed plugins
```

### Webhook Delivery
```
1. Create payload with event data
2. Generate HMAC-SHA256 signature
3. Send to plugin webhook URL with signature header
4. On failure, retry with exponential backoff
5. Update event log with final status
6. Log success/failure with error message
```

## Security Considerations

### Tenant Isolation
- All endpoints require X-Tenant-ID header
- Database queries filtered by tenant_id
- No cross-tenant data leakage possible

### API Key Security
- Keys prefixed with 'pk_' for easy identification
- Stored as SHA256 hashes (one-way)
- Unique constraints prevent duplicates
- Supports key rotation via expiration

### Webhook Security
- HMAC-SHA256 signature verification
- Constant-time comparison (prevent timing attacks)
- Payload validation before processing
- Timeout protection (30 seconds default)

### SQL Injection Prevention
- Parameterized queries throughout
- No string concatenation in SQL
- Using asyncpg which handles parameter binding

## Performance Optimizations

### Database Indexes
- Covering indexes on frequently queried columns
- Separate indexes for marketplace and tenant queries
- Index on event log status for filtering

### Connection Pooling
- Minimum 5 connections, maximum 20
- Reuse connections across requests
- Automatic cleanup on shutdown

### Async/Await
- Non-blocking I/O for all database operations
- Concurrent webhook delivery
- Background task processing for long-running operations

### Query Optimization
- Select only needed columns
- Pagination with limit/offset
- Efficient joins on indexed columns

## Error Handling Strategy

### UUID Validation
```python
try:
    plugin_uuid = uuid.UUID(plugin_id)
except ValueError:
    raise HTTPException(status_code=400, detail="Invalid UUID format")
```

### Database Constraints
- Catch UniqueViolationError for duplicate installs
- Return appropriate HTTP status codes
- Provide meaningful error messages

### Webhook Delivery
- Retry with exponential backoff
- Log all attempts and errors
- Update event log with final status

## Testing Recommendations

### Unit Tests
- Webhook signature generation and verification
- Semver validation
- API key hashing

### Integration Tests
- Plugin install/uninstall flow
- Event emission and delivery
- Developer registration and plugin publishing

### End-to-End Tests
- Multi-tenant isolation
- Event retry mechanism
- Rate limiting enforcement

### Load Tests
- Concurrent webhook delivery
- Database connection pool under load
- Event emission with many subscribers

## Monitoring & Observability

### Logging Points
- Service startup/shutdown
- Plugin lifecycle events
- Webhook delivery attempts
- Developer registration
- Database errors

### Metrics to Track
- Plugin install/uninstall counts
- Event emission frequency
- Webhook delivery success rate
- API key usage
- Database connection pool utilization

### Health Check
- Database connectivity
- Service status
- Database status (healthy/degraded)

## Future Enhancements

1. Rate limiting middleware with token bucket algorithm
2. Plugin dependency management (plugin A requires plugin B)
3. Plugin versioning with auto-upgrade
4. Plugin permissions matrix (granular per-endpoint)
5. Resource usage quotas and enforcement
6. Plugin marketplace reviews and ratings
7. Audit logging for compliance
8. Plugin sandbox execution environment
9. Plugin data storage/database access
10. GraphQL support for complex queries
