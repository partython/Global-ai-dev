# API Key Authentication - Quick Start Guide

## For Service Developers

### 1. Protect an Endpoint with API Key

```python
from fastapi import Depends
from shared.middleware.auth import get_api_key_auth
from shared.models.api_key import APIKeyContext, APIKeyScope

@app.get("/api/v1/data")
async def get_data(api_key: APIKeyContext = Depends(get_api_key_auth)):
    """Endpoint that requires a valid API key."""
    # Tenant is automatically extracted from the key
    tenant_id = api_key.tenant_id

    # Check permissions
    if not api_key.can_read:
        raise HTTPException(status_code=403, detail="Read access denied")

    # Your business logic
    return {"tenant": tenant_id, "data": []}

@app.post("/api/v1/data")
async def create_data(data: dict, api_key: APIKeyContext = Depends(get_api_key_auth)):
    """Endpoint that requires write permission."""
    # Require specific scope
    api_key.requires_scope(APIKeyScope.WRITE)  # Raises 403 if not allowed

    # Your business logic
    return {"created": True}
```

### 2. Check Specific Permissions

```python
from shared.models.api_key import APIKeyScope

@app.delete("/api/v1/data/{id}")
async def delete_data(id: str, api_key: APIKeyContext = Depends(get_api_key_auth)):
    """Only admin keys can delete."""
    if not api_key.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Delete logic
    return {"deleted": True}

# Or use requires_scope to automatically raise
api_key.requires_scope(APIKeyScope.ADMIN)
```

### 3. Access Rate Limit Info

```python
@app.get("/api/v1/status")
async def status(api_key: APIKeyContext = Depends(get_api_key_auth)):
    """Return rate limit information."""
    return {
        "remaining_requests": 59,  # From X-RateLimit-Remaining header
        "limit": api_key.rate_limit.requests_per_minute,
        "reset_at": api_key.rate_limit.requests_per_minute * 60,
    }
```

---

## For API Consumers (Clients)

### Generate an API Key

**Admin Dashboard:**
1. Go to Settings → API Keys
2. Click "Generate New Key"
3. Select scopes: READ, WRITE, ADMIN
4. Set expiration (or leave blank for no expiration)
5. Copy the key (you won't see it again!)

**API Endpoint (for admins):**
```bash
curl -X POST https://api.priyaai.com/api/v1/keys \
  -H "Authorization: Bearer <admin_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mobile App Key",
    "scopes": ["read", "write"],
    "expires_in_days": 365
  }'

# Response:
{
  "key_id": "key_abc123xyz",
  "api_key": "priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "scopes": ["read", "write"],
  "created_at": "2026-03-06T10:30:00Z",
  "expires_at": "2027-03-06T10:30:00Z"
}
```

### Use the API Key

**Add to Request Header:**
```bash
curl https://api.priyaai.com/api/v1/data \
  -H "X-API-Key: priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
```

**Python Client:**
```python
import requests

api_key = "priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}

response = requests.get(
    "https://api.priyaai.com/api/v1/data",
    headers=headers
)

# Check rate limits
print("Remaining requests:", response.headers.get("X-RateLimit-Remaining"))
print("Reset time:", response.headers.get("X-RateLimit-Reset"))
```

**JavaScript Client:**
```javascript
const apiKey = "priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6";

fetch("https://api.priyaai.com/api/v1/data", {
  headers: {
    "X-API-Key": apiKey,
    "Content-Type": "application/json"
  }
})
.then(response => {
  // Check rate limits
  console.log("Remaining:", response.headers.get("x-ratelimit-remaining"));
  return response.json();
})
.then(data => console.log(data));
```

### Handle Rate Limiting

```bash
# Will return 429 when rate limit exceeded
curl https://api.priyaai.com/api/v1/data \
  -H "X-API-Key: priya_prod_acme_..."

# Response headers show when you can retry
# X-RateLimit-Limit: 60
# X-RateLimit-Remaining: 0
# X-RateLimit-Reset: 1741276800
# Retry-After: 60

# Wait 60 seconds (or until X-RateLimit-Reset) before retrying
```

---

## API Key Format

### Structure
```
priya_{environment}_{tenant_id_prefix}_{random_32_chars}

Example: priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

### Components
- **`priya_`** - Platform identifier
- **`prod|staging|dev`** - Environment (determines which API to call)
- **`acme`** - Tenant identifier (visible, used for validation)
- **`a1b2c3d4...`** - Random secret (32 characters, base64-like)

### Security Notes
- Never expose in logs
- Never commit to version control
- Never share via email
- Store in secure environment variables
- Rotate regularly (annually recommended)

---

## Scopes Explained

| Scope | Permissions | Use Case |
|-------|------------|----------|
| `READ` | GET, HEAD, OPTIONS | Read-only dashboards, analytics |
| `WRITE` | POST, PUT, PATCH | Integration apps, data imports |
| `ADMIN` | All operations + management | Admin tools, migrations |
| `WEBHOOK` | Webhook signing only | Webhook subscribers |

### Example Permission Checks

```python
# Allow only read operations
if api_key.has_scope(APIKeyScope.READ):
    # User can fetch data
    pass

# Require write for mutations
api_key.requires_scope(APIKeyScope.WRITE)  # Raises 403 if not allowed

# Admin-only functions
if not api_key.is_admin:
    raise PermissionError("Admin access required")
```

---

## Common Scenarios

### Scenario 1: Monitoring Dashboard (Read-Only)

```python
# Create key with READ scope only
curl -X POST https://api.priyaai.com/api/v1/keys \
  -H "Authorization: Bearer <admin>" \
  -d '{
    "name": "Dashboard API Key",
    "scopes": ["read"],
    "expires_in_days": 90
  }'

# Use in dashboard
fetch("https://api.priyaai.com/api/v1/metrics", {
  headers: { "X-API-Key": "priya_prod_..." }
})
```

### Scenario 2: Integration App (Read + Write)

```python
# Create key with READ and WRITE scopes
curl -X POST https://api.priyaai.com/api/v1/keys \
  -H "Authorization: Bearer <admin>" \
  -d '{
    "name": "CRM Integration",
    "scopes": ["read", "write"],
    "expires_in_days": 365
  }'

# Use for syncing data
requests.post("https://api.priyaai.com/api/v1/contacts/batch",
  headers={"X-API-Key": "priya_prod_..."},
  json={"contacts": [...]})
```

### Scenario 3: Key Rotation (No Downtime)

```python
# 1. Create new key (old key still works)
new_key = create_api_key("New Production Key", scopes=["read", "write"])

# 2. Update your application to use new key
# 3. Monitor for errors
# 4. After 24 hours, revoke old key

curl -X POST https://api.priyaai.com/api/v1/keys/{old_key_id}/revoke \
  -H "Authorization: Bearer <admin>"

# Old key now returns 403 "API key has been revoked"
```

---

## Error Responses

### 401 Unauthorized - Missing Key

```bash
curl https://api.priyaai.com/api/v1/data
# HTTP 401
{
  "detail": "API key required (X-API-Key header or x_api_key parameter)"
}
```

### 401 Unauthorized - Invalid Key

```bash
curl https://api.priyaai.com/api/v1/data \
  -H "X-API-Key: invalid_key_format"
# HTTP 401
{
  "detail": "Invalid API key format"
}
```

### 403 Forbidden - Insufficient Permissions

```bash
curl https://api.priyaai.com/api/v1/data \
  -X POST \
  -H "X-API-Key: priya_prod_... (READ only)"
# HTTP 403
{
  "detail": "API key scope 'write' required"
}
```

### 403 Forbidden - Key Expired

```bash
curl https://api.priyaai.com/api/v1/data \
  -H "X-API-Key: priya_prod_... (expired)"
# HTTP 403
{
  "detail": "API key has expired"
}
```

### 429 Too Many Requests - Rate Limited

```bash
curl https://api.priyaai.com/api/v1/data -w "\n%{http_code}\n" \
  -H "X-API-Key: priya_prod_..."
# HTTP 429
{
  "detail": "Rate limit exceeded"
}

Headers:
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1741276800
Retry-After: 60
```

---

## Best Practices

### ✅ DO

1. **Use environment variables**
   ```bash
   export PRIYA_API_KEY="priya_prod_..."
   ```

2. **Check rate limit headers**
   ```python
   if response.headers.get("X-RateLimit-Remaining") == "0":
       time.sleep(60)  # Back off before next request
   ```

3. **Rotate keys regularly**
   - Annually for production
   - Quarterly for integrations
   - Immediately if compromised

4. **Use minimal scopes**
   - Dashboard? Use READ only
   - Integration? Use READ + WRITE
   - Don't grant ADMIN unless necessary

5. **Set expiration dates**
   - Short-lived keys (30-90 days) for testing
   - Annual expiration for production

### ❌ DON'T

1. **Commit keys to version control**
   ```bash
   # Bad
   git add config.py  # Contains API_KEY=priya_prod_...

   # Good
   echo "api_key = os.environ['PRIYA_API_KEY']" in config.py
   export PRIYA_API_KEY="..." in CI/CD
   ```

2. **Log API keys**
   ```python
   # Bad
   print(f"Authenticating with key: {api_key}")

   # Good
   print("API key loaded from environment")
   ```

3. **Share keys via email/chat**
   - Unsafe transmission
   - Permanent record
   - Can be intercepted

4. **Use same key for multiple services**
   - Create separate key per service
   - Easier to rotate
   - Better audit trail

5. **Ignore rate limit warnings**
   - Design for 429 responses
   - Implement exponential backoff
   - Request higher limits if needed

---

## Support

**Issue with your API key?**
- Check expiration: Dashboard → Settings → API Keys
- Verify scopes match your operation
- Check rate limits: Look at `X-RateLimit-*` headers
- Check IP allowlist if configured

**Need a new key or higher limits?**
- Admin Dashboard: Settings → API Keys → Request Limit Increase
- Or contact: api-support@priyaai.com

**Security incident?**
- Revoke key immediately: Settings → API Keys → Revoke
- Create new key
- Rotate in all applications
- Contact: security@priyaai.com
