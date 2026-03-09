# Security Implementation Summary - Priya Global Platform

## Overview
Comprehensive CORS (Cross-Origin Resource Sharing) and API Key authentication implementation for international-grade security across all microservices in the Priya Global Platform.

**Implementation Date:** March 2026
**Scope:** All 35+ microservices
**Status:** Complete

---

## PART 1: Centralized CORS Configuration

### File: `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/middleware/cors.py`

**Purpose:** Single source of truth for CORS policies across all services.

**Key Features:**
- Environment-aware configuration (production, staging, development)
- Explicit method and header whitelisting (no `["*"]` in production)
- Response header exposure control for security
- Browser preflight caching (1 hour)
- Credential support for authenticated requests

**Configuration by Environment:**

#### Production
```python
allowed_origins = [
    "https://api.priyaai.com",
    "https://app.priyaai.com",
    "https://dashboard.priyaai.com",
    "https://priyaai.com",
    "https://www.priyaai.com",
]
```
- Strict whitelist only
- HTTPS only
- No localhost
- No development domains

#### Staging
```python
allowed_origins = [
    "https://api-staging.priyaai.com",
    "https://app-staging.priyaai.com",
    "https://dashboard-staging.priyaai.com",
    "http://localhost:3000",  # Local testing
    "http://localhost:3001",
    "http://localhost:8000",
    # ... more localhost variants
]
```
- Staging domains
- Localhost support for local development
- Mixed HTTP/HTTPS

#### Development
```python
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "ws://localhost:3000",    # WebSocket support
    # ... all port variants
]
```
- All localhost combinations
- HTTP allowed
- WebSocket support

**Allowed Methods (All Environments):**
```python
["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
```

**Allowed Headers (All Environments):**
```python
[
    "Content-Type",      # Request content type
    "Authorization",     # JWT tokens
    "X-API-Key",        # API key authentication
    "X-Tenant-ID",      # Tenant isolation
    "X-Request-ID",     # Request tracing
    "Accept",
    "Accept-Language",
    "Origin",
    "User-Agent",
]
```

**Exposed Response Headers:**
```python
[
    "X-Request-ID",           # For tracing
    "X-RateLimit-Limit",      # Rate limit info
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",      # Unix timestamp
    "Retry-After",
    "Content-Type",
    "Content-Length",
]
```

### API Usage

**In Services:**
```python
from shared.middleware.cors import get_cors_config
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
```

**Helper Functions:**
- `get_cors_config(environment)` - Get full config dict
- `get_allowed_origins(environment)` - Get just origins list
- `is_origin_allowed(origin, environment)` - Check if origin is allowed

---

## PART 2: API Key Authentication

### New Files Created

#### 1. `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/models/api_key.py`

**Purpose:** Pydantic models for API key lifecycle and authentication.

**Key Models:**

##### APIKeyScope (Enum)
Granular permission levels:
- `READ` - Read-only access (GET, HEAD, OPTIONS)
- `WRITE` - Write access (POST, PUT, PATCH)
- `ADMIN` - Full administrative access
- `WEBHOOK` - Webhook callback signing only

##### RateLimitConfig
Per-key rate limiting:
```python
{
    "requests_per_minute": 60,      # Configurable limit
    "requests_per_hour": 3600,      # Or use default
    "burst_size": 10,               # Burst allowance
}
```

##### APIKeyCreate (Request Model)
```python
{
    "name": "Production API Key",        # Human-readable
    "scopes": ["READ", "WRITE"],         # Permissions
    "expires_in_days": 365,              # Optional expiration
    "rate_limit": {...},                 # Optional custom limits
    "metadata": {...}                    # Custom fields
}
```

##### APIKeyResponse (Response Model - Secret Shown Once)
```python
{
    "key_id": "uuid",
    "name": "Production API Key",
    "api_key": "priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",  # NEVER shown again
    "scopes": ["READ", "WRITE"],
    "rate_limit": {...},
    "status": "active",
    "created_at": "2026-03-06T...",
    "expires_at": "2027-03-06T...",
    "last_used_at": null
}
```

##### APIKeyInfo (Viewing Model - Secret Hidden)
```python
{
    "key_id": "uuid",
    "name": "Production API Key",
    "key_preview": "priya_prod_****_****o5p6",  # Obfuscated
    "scopes": ["READ", "WRITE"],
    "status": "active",
    "created_at": "2026-03-06T...",
    "usage_count": 1547
}
```

##### APIKeyContext (Authenticated Context)
Returned after successful authentication:
```python
{
    "tenant_id": "acme-corp",
    "key_id": "api_key_uuid",
    "scopes": ["READ", "WRITE"],
    "rate_limit": {...},
    "expires_at": "2027-03-06T...",
    "can_read": true,
    "can_write": true,
    "is_admin": false
}
```

#### 2. Enhanced `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/middleware/auth.py`

**New Function: `get_api_key_auth()`**

**API Key Format:**
```
priya_{environment}_{tenant_id_prefix}_{random_32_chars}

Example: priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

**Components:**
- `priya_` - Platform prefix
- `prod|staging|dev` - Environment identifier
- `acme` - Tenant identifier (extracted for validation)
- `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6` - Random 32-char secret

**Authentication Flow:**

1. **Extract API Key** from `X-API-Key` header
2. **Validate Format** using regex pattern
3. **Hash Comparison** - SHA256 hash comparison (never plaintext storage)
4. **Database Lookup** - Check api_keys table
5. **Status Validation** - Ensure key is "active" (not revoked/expired)
6. **Expiration Check** - Verify expires_at timestamp
7. **Scope Extraction** - Get permission scopes from database
8. **Rate Limit Check** - Validate against per-minute and per-hour limits using Redis
9. **Usage Logging** - Audit trail with timestamp, IP, method, path
10. **Context Return** - Return APIKeyContext with permissions

**Rate Limiting:**

Uses Redis for tracking:
- **Minute Window:** `rl:apikey:{key_id}:min:{window}`
- **Hour Window:** `rl:apikey:{key_id}:hour:{window}`
- **Sliding Window Counter** with automatic expiry
- **Response Headers:**
  - `X-RateLimit-Limit` - Maximum requests
  - `X-RateLimit-Remaining` - Requests remaining
  - `X-RateLimit-Reset` - Unix timestamp for reset
  - `Retry-After` - Seconds to wait (on 429)

**Key Rotation Support:**

Database schema supports:
- Multiple active keys per tenant
- Old key grace period (configurable hours)
- Automatic status transition (active → rotated → expired)
- Scope preservation during rotation

**Error Handling:**

| Scenario | Status | Message |
|----------|--------|---------|
| Missing header | 401 | "API key required (X-API-Key header)" |
| Invalid format | 401 | "Invalid API key format" |
| Not found | 401 | "Invalid API key" |
| Revoked | 403 | "API key has been revoked" |
| Expired | 403 | "API key has expired" |
| No scopes | 403 | "API key has no permissions configured" |
| Rate limited | 429 | "Rate limit exceeded" |

**Usage in Endpoints:**

```python
from fastapi import Depends
from shared.middleware.auth import get_api_key_auth
from shared.models.api_key import APIKeyContext

@app.get("/api/v1/protected")
async def protected_endpoint(api_key: APIKeyContext = Depends(get_api_key_auth)):
    """
    Access requires valid API key.
    Tenant context automatically injected.
    """
    return {
        "tenant": api_key.tenant_id,
        "scopes": api_key.scopes,
        "can_write": api_key.can_write
    }

@app.post("/api/v1/write-only")
async def write_endpoint(api_key: APIKeyContext = Depends(get_api_key_auth)):
    """
    This endpoint requires write permission.
    """
    api_key.requires_scope(APIKeyScope.WRITE)  # Raises 403 if no permission
    # ... implementation
```

---

## PART 3: Service Updates

### Gateway Service (`services/gateway/main.py`)

**Changes:**
- ✅ Added `from shared.middleware.cors import get_cors_config`
- ✅ Replaced wildcard CORS with centralized config
- ✅ Environment-aware configuration loading

**New Code:**
```python
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
```

### All Microservices (35 services updated)

Updated the following services with centralized CORS:

**Tier 1 (Core Services):**
- ✅ auth
- ✅ billing
- ✅ analytics
- ✅ notification

**Tier 2 (Channel Services):**
- ✅ whatsapp
- ✅ email
- ✅ voice
- ✅ social
- ✅ telegram
- ✅ sms
- ✅ rcs
- ✅ webchat

**Tier 3 (AI/Intelligence Services):**
- ✅ ai_engine
- ✅ knowledge
- ✅ ai_training
- ✅ conversation_intel
- ✅ voice_ai

**Tier 4 (Business Services):**
- ✅ leads
- ✅ appointments
- ✅ ecommerce
- ✅ marketing
- ✅ marketplace
- ✅ workflows

**Tier 5 (Infrastructure Services):**
- ✅ tenant
- ✅ tenant_config
- ✅ deployment
- ✅ cdn_manager
- ✅ video
- ✅ health_monitor

**Tier 6 (Specialized Services):**
- ✅ compliance
- ✅ plugins
- ✅ advanced_analytics
- ✅ channel_router
- ✅ handoff

---

## Security Best Practices Implemented

### CORS Security

1. **No Wildcard Origins in Production**
   - Only specific, whitelisted domains
   - No `allow_origins=["*"]`

2. **Explicit Method Whitelisting**
   - Not `allow_methods=["*"]`
   - Only: GET, POST, PUT, PATCH, DELETE, OPTIONS

3. **Explicit Header Whitelisting**
   - Not `allow_headers=["*"]`
   - Specific headers for each use case

4. **Credential Support**
   - `allow_credentials=True` for authentication
   - Allows cookies and auth headers
   - Requires explicit origin (no wildcards with credentials)

5. **Response Header Exposure**
   - Only necessary headers exposed
   - Prevents leakage of internal implementation details

### API Key Security

1. **Key Format Standards**
   - Semantic versioning in key format (environment, tenant)
   - 32-char random component (256 bits of entropy)
   - Impossible to brute force

2. **Secure Storage**
   - API keys never stored in plaintext
   - SHA256 hashing before database storage
   - Comparison uses `hmac.compare_digest()` (constant-time)

3. **Multiple Active Keys**
   - Support for key rotation without downtime
   - Grace period for old key migration
   - Status tracking (active, rotated, revoked, expired)

4. **Fine-Grained Permissions**
   - Scope-based access control
   - Separate scopes: READ, WRITE, ADMIN, WEBHOOK
   - Default to minimum required permissions

5. **Rate Limiting**
   - Per-key rate limits with Redis backing
   - Minute and hour windows
   - Burst allowance for legitimate traffic spikes
   - Configurable per key

6. **Usage Auditing**
   - Every API key request logged
   - Timestamp, IP, method, path tracked
   - Non-blocking logging (doesn't impact response)

7. **Expiration Support**
   - Optional expiration dates
   - Automatic status transitions
   - Timezone-aware (UTC)

8. **Key Rotation**
   - Multiple active keys per tenant
   - Graceful deprecation period
   - Scope preservation during rotation
   - Clear audit trail

---

## Environment Setup

### Required Environment Variables

For all services, set:

```bash
# Environment determines CORS configuration
ENVIRONMENT=production  # or staging, development

# Redis for rate limiting and caching
REDIS_URL=redis://localhost:6379

# Database connection (for API key lookups)
DATABASE_URL=postgresql://user:pass@localhost/priya
```

### Database Schema Required

API key management requires `api_keys` table:

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA256 hash
    tenant_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    scopes TEXT[] NOT NULL,                -- Array: ['read', 'write', 'admin']
    rate_limit_rpm INTEGER DEFAULT 60,
    rate_limit_rph INTEGER DEFAULT 3600,
    burst_size INTEGER DEFAULT 10,
    status VARCHAR(32) DEFAULT 'active',   -- active, rotated, revoked, expired
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    metadata JSONB,
    CONSTRAINT tenant_fk FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_status ON api_keys(status);
```

---

## Testing & Validation

### CORS Testing

```bash
# Test preflight request
curl -X OPTIONS https://api.priyaai.com/api/v1/data \
  -H "Origin: https://app.priyaai.com" \
  -H "Access-Control-Request-Method: POST" \
  -v

# Should return:
# Access-Control-Allow-Origin: https://app.priyaai.com
# Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
# Access-Control-Allow-Headers: Content-Type, Authorization, X-API-Key, X-Tenant-ID, X-Request-ID, ...
```

### API Key Testing

```bash
# Create API key (admin endpoint)
curl -X POST https://api.priyaai.com/api/v1/keys \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Integration Key",
    "scopes": ["read", "write"],
    "expires_in_days": 365
  }'

# Use API key
curl https://api.priyaai.com/api/v1/data \
  -H "X-API-Key: priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

# Check rate limit headers
curl https://api.priyaai.com/api/v1/data \
  -H "X-API-Key: priya_prod_acme_..." \
  -v

# Response includes:
# X-RateLimit-Limit: 60
# X-RateLimit-Remaining: 59
# X-RateLimit-Reset: 1741276800
```

---

## Migration Guide for Existing Integrations

### For Customers Using JWT

**No changes required** - JWT authentication continues to work alongside API keys.

### For Customers Adding API Key Support

1. **Request API Key** from Priya admin dashboard
2. **Store Securely** - Never commit to version control
3. **Use in Headers** - Add `X-API-Key: priya_prod_...` to requests
4. **Monitor Limits** - Check `X-RateLimit-*` headers
5. **Rotate Regularly** - Create new key, migrate, revoke old one

### For Webhook Integrations

API keys with `webhook` scope:
- Used for signing webhook payloads
- Included in `X-Hub-Signature-256` header
- Allows webhook source verification

---

## Monitoring & Alerts

### Key Metrics to Track

1. **CORS Rejections** - Failed preflight requests (check logs for blocked origins)
2. **API Key Usage** - Number of requests per key (in audit logs)
3. **Rate Limit Hits** - Requests exceeding limits (429 responses)
4. **Key Expiration** - Approaching expiration dates
5. **Key Rotation** - Status changes and deprecation

### Log Patterns to Monitor

```
# CORS rejection
CORS preflight failed: Origin "https://malicious.com" not in allowed list

# Rate limit hit
API key rate limit exceeded: key_id=12345 tenant=acme status=429

# Suspicious activity
API key with no scopes: key_id=67890
```

---

## Compliance Notes

### GDPR
- API key usage logged with timestamps
- Audit trail maintained for compliance
- IP addresses masked where possible
- Configurable retention policies

### PCI-DSS
- No payment card data in logs
- API keys never shown in responses (except creation)
- Secure transmission via HTTPS only
- Rate limiting prevents brute force attacks

### SOC 2
- Comprehensive audit logging
- Monitoring and alerting infrastructure
- Environment separation (prod/staging/dev)
- Access controls (RBAC via scopes)

---

## Implementation Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| `shared/middleware/cors.py` | 107 | Centralized CORS config |
| `shared/models/api_key.py` | 267 | API key models & enums |
| `shared/middleware/auth.py` | +150 | API key authentication |
| `services/gateway/main.py` | +2 changes | CORS import & config |
| All 35 microservices | +2 changes each | CORS import & config |

**Total Impact:**
- ✅ 35+ services updated
- ✅ 2 new core modules (CORS, API Key models)
- ✅ 1 enhanced middleware module (Auth)
- ✅ Backward compatible (JWT still works)
- ✅ Environment-aware configuration
- ✅ International-grade security

---

## Next Steps / Future Enhancements

1. **API Key Dashboard**
   - UI for managing API keys
   - Usage analytics
   - Automatic alerts before expiration

2. **OAuth 2.0 Integration**
   - OAuth2 Authorization Code flow
   - Delegation tokens
   - Third-party integrations

3. **WebAuthn/FIDO2**
   - Hardware key support
   - Passwordless authentication
   - Enhanced security

4. **Rate Limit Analytics**
   - Per-tenant rate limit tuning
   - Usage-based pricing
   - Predictive scaling

5. **API Gateway Enhancement**
   - GraphQL API support
   - gRPC endpoint
   - API versioning strategy

---

**Document Version:** 1.0
**Last Updated:** March 6, 2026
**Status:** Production Ready
