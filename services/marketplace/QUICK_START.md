# Marketplace Service - Quick Start

## File Location
```
/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/marketplace/main.py
```

## Service Stats
- **Lines of Code**: 1001
- **Endpoints**: 16
- **Functions**: 39
- **Database Tables**: 7
- **Port**: 9037

## 5-Minute Setup

### 1. Create Database
```bash
createdb marketplace_db
createuser marketplace_user --password
psql marketplace_db -c "ALTER USER marketplace_user CREATEDB;"
```

### 2. Set Environment Variables
```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=marketplace_db
export DB_USER=marketplace_user
export DB_PASSWORD=secure_password_here
export JWT_SECRET=your_jwt_secret_key_here
export PORT=9037
export CORS_ORIGINS="http://localhost:3000,https://app.example.com"
```

### 3. Install Dependencies
```bash
pip install fastapi uvicorn asyncpg pydantic pyjwt python-multipart
```

### 4. Start Service
```bash
python /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/marketplace/main.py
```

### 5. Test Health
```bash
curl -X GET http://localhost:9037/marketplace/health
```

## Authentication Flow

### 1. Generate JWT Token
```python
import jwt
import os
from datetime import datetime, timedelta

jwt_secret = os.getenv("JWT_SECRET")
payload = {
    "sub": "user_123",
    "tenant_id": "tenant_456",
    "email": "user@example.com",
    "exp": datetime.utcnow() + timedelta(hours=24)
}
token = jwt.encode(payload, jwt_secret, algorithm="HS256")
```

### 2. Use Token in Requests
```bash
curl -X GET http://localhost:9037/marketplace/apps \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE"
```

## Key Endpoints

### Browse Marketplace
```bash
curl -X GET "http://localhost:9037/marketplace/apps?category=crm&limit=10" \
  -H "Authorization: Bearer TOKEN"
```

### Install App
```bash
curl -X POST http://localhost:9037/marketplace/apps/APP_ID/install \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "permissions": ["read", "write"],
    "oauth_redirect_uri": "https://app.example.com/oauth/callback"
  }'
```

### Submit App Review
```bash
curl -X POST http://localhost:9037/marketplace/apps/APP_ID/review \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "rating": 5,
    "comment": "Amazing app, works perfectly!"
  }'
```

### Register as Developer
```bash
curl -X POST http://localhost:9037/marketplace/developer/register \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Inc",
    "description": "Leading app development company",
    "website": "https://acme.example.com",
    "contact_email": "contact@acme.example.com"
  }'
```

### Submit App for Review
```bash
curl -X POST http://localhost:9037/marketplace/developer/apps \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CRM Assistant",
    "description": "Powerful CRM integration",
    "category": "crm",
    "icon_url": "https://example.com/icon.png",
    "documentation_url": "https://docs.example.com",
    "oauth_client_id": "client_123",
    "permissions_required": ["read", "write"]
  }'
```

### Get Webhook Templates
```bash
curl -X GET http://localhost:9037/marketplace/webhooks/templates \
  -H "Authorization: Bearer TOKEN"
```

### Create Custom Webhook
```bash
curl -X POST http://localhost:9037/marketplace/webhooks \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "custom",
    "name": "Order Sync Webhook",
    "config": {
      "event": "order.created",
      "retry_count": 3
    }
  }'
```

### List Themes
```bash
curl -X GET http://localhost:9037/marketplace/themes \
  -H "Authorization: Bearer TOKEN"
```

### Customize Theme
```bash
curl -X POST http://localhost:9037/marketplace/themes/customize \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dark Mode Theme",
    "primary_color": "#1a1a2e",
    "secondary_color": "#16213e",
    "font_family": "Inter",
    "border_radius": "12px",
    "custom_css": ".widget { box-shadow: 0 4px 12px rgba(0,0,0,0.5); }"
  }'
```

## Database Schema

### Apps Table
- id (UUID): Primary key
- name (VARCHAR): App name
- category (VARCHAR): crm, analytics, payments, etc.
- status (VARCHAR): draft, pending_review, approved, rejected, deprecated
- rating (DECIMAL): Average rating (0-5)
- installation_count (INT): Total installations
- tenant_id (UUID): Multi-tenant isolation key

### App Installations Table
- id (UUID): Primary key
- app_id (UUID): Foreign key to apps
- tenant_id (UUID): Tenant isolation
- permissions (VARCHAR): Comma-separated (read, write, admin)
- status (VARCHAR): active, inactive, suspended
- installed_at (TIMESTAMP): Installation datetime

### Developers Table
- id (UUID): Primary key
- user_id (UUID): Reference to user
- company_name (VARCHAR): Developer company
- status (VARCHAR): pending, approved, rejected
- created_at (TIMESTAMP): Registration datetime

### Webhooks Table
- id (UUID): Primary key
- tenant_id (UUID): Isolation key
- type (VARCHAR): zapier, make, n8n, custom
- is_active (BOOLEAN): Active/inactive flag
- config (JSONB): Webhook configuration

## Environment Variables Checklist

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| DB_HOST | Yes | - | PostgreSQL host |
| DB_PORT | No | 5432 | PostgreSQL port |
| DB_NAME | Yes | - | Database name |
| DB_USER | Yes | - | Database user |
| DB_PASSWORD | Yes | - | Database password (no default!) |
| JWT_SECRET | Yes | - | JWT signing key (no default!) |
| PORT | No | 9037 | Service port |
| CORS_ORIGINS | No | http://localhost:3000 | Comma-separated origins |

## Testing with Python

```python
import requests
import jwt
import os
from datetime import datetime, timedelta

# Generate token
jwt_secret = "test_secret"
token = jwt.encode({
    "sub": "test_user",
    "tenant_id": "test_tenant",
    "email": "test@example.com",
    "exp": datetime.utcnow() + timedelta(hours=1)
}, jwt_secret, algorithm="HS256")

# Make request
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("http://localhost:9037/marketplace/health", headers=headers)
print(response.json())
```

## Troubleshooting

### JWT_SECRET Not Configured
```
HTTPException: 500 - JWT_SECRET not configured
```
**Fix**: `export JWT_SECRET=your_secret`

### Database Connection Failed
```
asyncpg.PostgresError: could not connect to server
```
**Fix**: Check DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

### Token Expired
```
HTTPException: 401 - Token expired
```
**Fix**: Generate new JWT token with future expiration

### CORS Error
```
Access to XMLHttpRequest from origin blocked by CORS policy
```
**Fix**: Add origin to CORS_ORIGINS variable

## Performance Notes
- Connection pool: 5-20 asyncpg connections
- Query timeout: 60 seconds
- Max concurrent requests: Limited by connection pool
- Recommended: Use with reverse proxy (nginx, caddy)

## Security Checklist
- [ ] JWT_SECRET is strong (32+ characters)
- [ ] DB_PASSWORD is complex
- [ ] CORS_ORIGINS restricted to known domains
- [ ] Database user has minimal required permissions
- [ ] Service runs with non-root user
- [ ] HTTPS enforced in production
- [ ] Secrets stored in secure vault (not in code/git)

