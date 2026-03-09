# Marketplace Service - Architecture Deep Dive

## Code Structure (1001 Lines)

### Section 1: Imports & Core Dependencies (Lines 1-18)
- FastAPI, Uvicorn for async HTTP server
- asyncpg for PostgreSQL connection pooling
- JWT for authentication
- Pydantic for request/response validation

### Section 2: Models & Enums (Lines 21-120)
**Enums (7)**
- `AppCategory`: 7 categories (CRM, Analytics, Payments, Communication, Productivity, Security, Integration)
- `PermissionScope`: 3 scopes (READ, WRITE, ADMIN)
- `AppStatus`: 5 statuses (DRAFT, PENDING_REVIEW, APPROVED, REJECTED, DEPRECATED)
- `WebhookType`: 4 types (ZAPIER, MAKE, N8N, CUSTOM)

**Request Models (8)**
- `AuthContext`: JWT claims container
- `AppSearchRequest`: Marketplace search parameters
- `AppInstallRequest`: Installation preferences
- `AppReviewRequest`: Rating and comment submission
- `DeveloperRegisterRequest`: Developer onboarding
- `AppSubmitRequest`: App submission for review
- `WebhookTemplateRequest`: Webhook creation
- `WebhookTestRequest`: Webhook testing
- `ThemeCustomizationRequest`: Theme customization

**Response Models (7)**
- `AppMarketplaceItem`: Listing view
- `AppDetailResponse`: Full app details
- `AppInstallationResponse`: Installation confirmation
- `DeveloperResponse`: Developer profile
- `WebhookTemplateResponse`: Template listing
- `ThemeResponse`: Theme with styling
- `HealthResponse`: Service health

### Section 3: Database Layer (Lines 123-230)

**DatabasePool Class**
- Singleton pattern for connection management
- AsyncPG connection pool (5-20 connections)
- Schema initialization on startup
- Query execution methods:
  - `execute()`: INSERT, UPDATE, DELETE
  - `fetch()`: SELECT multiple rows
  - `fetchrow()`: SELECT single row
  - `fetchval()`: SELECT scalar value

**Database Tables (7)**
1. **apps**: Core marketplace apps
   - UUID id, name, category, icon_url
   - status workflow tracking
   - ratings aggregation
   - Multi-tenant via tenant_id
   - Indices: tenant_id, category, status

2. **app_installations**: Per-tenant installations
   - UUID id, app_id (FK), tenant_id
   - permissions (read/write/admin)
   - oauth_token storage
   - Indices: tenant_id, app_id

3. **app_reviews**: User ratings and comments
   - UUID id, app_id (FK), user_id, tenant_id
   - rating (1-5 constraint)
   - comment text
   - Indices: tenant_id, app_id

4. **developers**: Developer profiles
   - UUID id, user_id, tenant_id
   - company_name, contact_email
   - status (pending/approved/rejected)
   - Indices: tenant_id, user_id

5. **webhooks**: Custom webhook configurations
   - UUID id, tenant_id, user_id
   - type (zapier/make/n8n/custom)
   - JSONB config storage
   - is_active boolean flag
   - Index: tenant_id

6. **webhook_templates**: Pre-built templates
   - UUID id, type, name
   - JSONB example_payload
   - No tenant isolation (shared templates)

7. **themes**: Customizable chat widget themes
   - UUID id, name, category
   - Color scheme (primary, secondary)
   - Font and border radius
   - custom_css injection
   - downloads counter

### Section 4: Authentication (Lines 233-261)

**Security Layer**
- HTTPBearer token extraction
- JWT decoding with HS256 algorithm
- Claims validation (sub, tenant_id, email, exp)
- Error handling:
  - ExpiredSignatureError (401)
  - InvalidTokenError (401)
  - Missing JWT_SECRET (500)

**AuthContext Dependency**
- Injected via FastAPI Depends()
- Available on all protected endpoints
- Automatic tenant isolation via tenant_id claim

### Section 5: App Operations (Lines 264-360)

**Functions (7)**
1. `get_app_by_id()`: Fetch app with RLS enforcement
   - Status filtering (approved or owned by tenant)
   - Returns app dictionary
   - Raises 404 if not found

2. `search_apps()`: Full-text search with filters
   - Query parameter (ILIKE on name/description)
   - Category filtering
   - Limit/offset pagination
   - Ordered by rating and installation_count

3. `install_app()`: One-click installation
   - Duplicate detection
   - Installation record creation
   - installation_count increment
   - Returns installation_id

4. `uninstall_app()`: Remove tenant installation
   - Cascade deletion
   - installation_count decrement
   - RLS enforcement via tenant_id

5. `submit_review()`: Rating and comment submission
   - Update-or-insert logic
   - Automatic rating aggregation (AVG)
   - review_count calculation
   - App rating update

6. `get_app_by_id()`: Used by detail endpoint
   - Filters: status=approved or owned by tenant
   - Includes developer name lookup

7. `search_apps()`: Dynamic query building
   - Parameterized queries (SQL injection safe)
   - Optional query/category filters
   - Offset-based pagination

### Section 6: Developer Operations (Lines 363-414)

**Functions (3)**
1. `register_developer()`: Developer onboarding
   - Creates developer profile
   - Pending status by default
   - Tenant isolation

2. `submit_app()`: App submission for review
   - Creates app record with pending_review status
   - Captures OAuth client ID
   - Permission requirements storage

3. `get_developer_apps()`: List developer's submissions
   - Fetches all apps for developer
   - Includes metrics (rating, installation_count)
   - Ordered by creation date (DESC)

### Section 7: Webhook Operations (Lines 417-455)

**Functions (3)**
1. `get_webhook_templates()`: Fetch pre-built templates
   - Zapier, Make, n8n patterns
   - Example payloads for reference
   - No tenant filtering (shared templates)

2. `create_webhook()`: Custom webhook setup
   - Stores webhook configuration
   - Supports custom JSONB config
   - is_active flag

3. `test_webhook()`: Webhook testing sandbox
   - Mock delivery simulation
   - Payload size calculation
   - Response time measurement
   - Success status return

### Section 8: Theme Operations (Lines 458-489)

**Functions (2)**
1. `get_themes()`: List available themes
   - All pre-built themes
   - Ordered by downloads (DESC)
   - Includes color and font metadata

2. `create_theme_variant()`: Custom theme creation
   - Custom CSS injection
   - Color customization
   - Font family selection
   - Border radius control

### Section 9: FastAPI Application (Lines 492-520)

**Configuration**
- CORS middleware with environment-based origins
- Async event handlers (startup/shutdown)
- Connection pool initialization

**Lifecycle**
- `@app.on_event("startup")`: Initialize DatabasePool
- `@app.on_event("shutdown")`: Close pool gracefully

### Section 10: Endpoints (Lines 523-955)

**Health Check (1 endpoint)**
- GET /marketplace/health
  - Returns service status
  - Database connection status
  - Version information

**Marketplace Browse (2 endpoints)**
- GET /marketplace/apps
  - Search and filter apps
  - Returns AppMarketplaceItem list
  - Query, category, limit, offset parameters

- GET /marketplace/apps/{app_id}
  - Detailed app view
  - Changelog and documentation
  - Screenshots placeholder

**App Management (3 endpoints)**
- POST /marketplace/apps/{app_id}/install
  - Permission scoping
  - OAuth redirect URI support
  - Returns AppInstallationResponse

- DELETE /marketplace/apps/{app_id}/uninstall
  - Cascade deletion
  - Installation count update

- POST /marketplace/apps/{app_id}/review
  - Rating submission (1-5)
  - Comment requirement (10-500 chars)
  - Automatic rating aggregation

**Developer Portal (3 endpoints)**
- POST /marketplace/developer/register
  - Company information collection
  - Status tracking
  - Returns DeveloperResponse

- POST /marketplace/developer/apps
  - App submission
  - OAuth configuration
  - Permission declaration

- GET /marketplace/developer/apps
  - App inventory
  - Metrics display (rating, installations)

**Webhook Marketplace (3 endpoints)**
- GET /marketplace/webhooks/templates
  - Pre-built patterns
  - Example payloads
  - Template listing

- POST /marketplace/webhooks
  - Custom webhook creation
  - Configuration storage

- POST /marketplace/webhooks/test
  - Delivery testing
  - Response validation

**Theme Store (2 endpoints)**
- GET /marketplace/themes
  - Theme listing
  - Download metrics

- POST /marketplace/themes/customize
  - Custom variant creation
  - Styling customization

### Section 11: Entry Point (Lines 958-1001)

**Main Block**
- Port configuration from environment (default 9037)
- Uvicorn server startup
- No reload in production

## Multi-Tenancy Implementation

### RLS (Row-Level Security)
Every query enforces tenant_id:
```python
# Example: Apps filtered by status and tenant
SELECT ... FROM apps
WHERE id = $1 AND (status = 'approved' OR tenant_id = $2)
```

### Isolation Points
1. **Apps Table**: Visibility by status or tenant ownership
2. **Installations**: Scoped to tenant
3. **Reviews**: Filtered by tenant in aggregation
4. **Developers**: Isolated by tenant
5. **Webhooks**: Scoped to tenant
6. **Themes**: Shared (no tenant filtering)

### JWT Claims
- `sub`: User ID
- `tenant_id`: Tenant isolation key
- `email`: User email
- `exp`: Expiration time

## Async Patterns

### Database Operations
```python
async with self._pool.acquire() as conn:
    result = await conn.fetch(query, *params)
```

### Request Handlers
```python
@app.get("/path")
async def endpoint(auth: AuthContext = Depends(get_auth_context)):
    data = await db_pool.fetch(...)
    return data
```

### Connection Pool Lifecycle
- Initialization: `await db_pool.initialize()`
- Shutdown: `await db_pool.close()`
- Concurrent connections: 5-20 managed by asyncpg

## Error Handling

### JWT Validation
- `HTTPException(401, "Token expired")`
- `HTTPException(401, "Invalid token: ...")`
- `HTTPException(500, "JWT_SECRET not configured")`

### Database Operations
- `HTTPException(404, "App not found")`
- `HTTPException(400, "App already installed")`
- `HTTPException(400, "Must register as developer first")`

### Query Execution
- Parameterized queries (prevents SQL injection)
- Automatic type conversion
- Timeout: 60 seconds per query

## Performance Optimizations

### Indices
- `idx_apps_tenant_id`: Fast tenant filtering
- `idx_apps_category`: Category filtering
- `idx_apps_status`: Status filtering
- `idx_installations_tenant`: Installation lookups
- `idx_installations_app`: App-specific queries
- `idx_reviews_tenant`: Review filtering
- `idx_reviews_app`: App review aggregation
- `idx_developers_tenant`: Developer lookups
- `idx_developers_user`: User to developer mapping
- `idx_webhooks_tenant`: Webhook isolation

### Connection Pooling
- Min: 5 connections
- Max: 20 connections
- Query timeout: 60 seconds
- Allows concurrent request handling

### Pagination
- Limit/offset pattern
- Default limit: 20
- Prevents full-table scans

## Security Layers

1. **Authentication**: JWT with HS256
2. **Authorization**: AuthContext with tenant_id
3. **Database**: RLS enforcement on queries
4. **CORS**: Environment-based origin validation
5. **SQL Injection**: Parameterized queries
6. **Secret Management**: Environment variables only
7. **Rate Limiting**: (Can be added via middleware)
8. **Logging**: (No sensitive data exposure)

## Extensibility Points

### Add New Endpoints
1. Create request/response models
2. Define handler function
3. Add @app.get/post/put/delete decorator
4. Inject AuthContext for authorization

### Add New Tables
1. Define schema in DatabasePool._setup_schema()
2. Add indices for tenant_id if multi-tenant
3. Create helper functions for CRUD operations
4. Add request/response models

### Add New Features
1. Webhook event system (pre-built templates)
2. App rating distribution
3. Developer revenue tracking
4. App usage analytics
5. Webhook delivery logs
6. Theme preview system
7. OAuth token refresh logic

## Testing Strategy

### Unit Tests
- Model validation
- Enum values
- Request/response schemas

### Integration Tests
- JWT token generation/validation
- Database operations
- RLS enforcement
- Endpoint behavior

### Load Tests
- Connection pool limits
- Concurrent request handling
- Query performance

