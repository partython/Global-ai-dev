# Priya Global Platform - Unified API Documentation

Complete API documentation for the Priya Global multi-tenant platform serving 36 microservices through a single gateway on port 9000.

## Documentation Files

### 1. OpenAPI Specification
**File**: `openapi.yaml`
**Format**: OpenAPI 3.1
**Lines**: 1200+

Comprehensive OpenAPI specification covering:
- All 36 microservices with complete path definitions
- Authentication schemes (JWT Bearer token)
- Common response schemas (Error, Pagination, HealthStatus)
- Multi-tenant headers (X-Tenant-ID)
- Rate limiting headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
- Webhook callback definitions and event types
- Server definitions (Production, Staging, Local Development)
- Regional pricing examples (USD, INR, GBP, AUD)
- Indian phone number examples (+91 format)

**Services Documented** (36 total):

Authentication:
- Auth Service (login, register, 2FA, password reset)

Workspace Management:
- Tenant Service (configuration, onboarding, plan management)

Messaging & Channels:
- Channel Router (multi-channel routing)
- WhatsApp Service (send, templates, webhooks)
- Email Service (send, templates, SES webhooks)
- Voice Service (calls, IVR, recordings)
- SMS Service (send, webhooks)
- Social Service (Instagram, Facebook, webhooks)
- WebChat Service (widget, sessions)
- Telegram Service (bot, webhooks)
- RCS Service (rich cards, carousels)
- Video Service (rooms, recordings)

AI & Intelligence:
- AI Engine (chat, knowledge base, personality config)
- Conversation Intelligence (sentiment, keywords, analysis)
- Voice AI (STT, TTS, NLU)

Business Operations:
- Billing Service (subscriptions, invoices, usage tracking)
- Analytics Service (dashboards, custom reports, export)
- Marketing Service (campaigns, automations, templates)
- E-commerce Service (products, orders)
- Leads Service (scoring, pipeline, conversion)
- Appointments Service (booking, scheduling)

Management Features:
- Notification Service (push notifications, preferences)
- Plugins Service (marketplace, installation)
- Handoff Service (agent assignment, conversations)
- Workflow Service (automation, triggers)
- Compliance Service (audit logs, data export)
- Knowledge Base Service (articles, search)
- CDN Manager (media upload, optimization)
- Deployment Service (releases, rollback)
- Configuration Service (onboarding, industry setup)
- Health Monitor (service metrics, status)

### 2. Swagger UI
**File**: `swagger-ui.html`
**Type**: Interactive Documentation

Standalone Swagger UI with:
- Dark mode toggle (Ctrl+T)
- Platform branding (Priya Global)
- Try-it-out functionality for all endpoints
- Request/response visualization
- Real-time rate limit display
- Keyboard shortcuts (Ctrl+K search, Ctrl+T theme)
- Responsive design for mobile
- Service health aggregation
- Custom CSS for professional appearance

**Features**:
- Loads OpenAPI spec from `/docs/openapi.json`
- Automatic request tracing with X-Request-ID
- Rate limit headers monitoring
- Bearer token authentication support
- Multi-language support

### 3. Gateway Documentation Router
**File**: `services/gateway/docs_router.py`
**Language**: Python (FastAPI)
**Type**: Backend router for serving docs

Provides the following endpoints:

**Documentation Endpoints**:
- `GET /docs` - Swagger UI (primary)
- `GET /redoc` - ReDoc alternative view
- `GET /docs/openapi.json` - OpenAPI spec (JSON)
- `GET /docs/download-spec` - Download spec (YAML or JSON)

**Utility Endpoints**:
- `GET /docs/health-summary` - All services health status
- `GET /docs/services` - List all 36 services
- `GET /docs/guides` - Integration guides
- `GET /docs/examples` - Code examples (cURL, Python, JavaScript)
- `GET /docs/api-key-management` - JWT token management
- `GET /docs/changelog` - Version history

**Features**:
- Service health caching (10s TTL)
- Aggregated health status from all services
- Concurrent health checks with asyncio
- Performance-optimized responses
- Error handling for unavailable services

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Gateway (Port 9000)                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  docs_router.py                                      │   │
│  │  ├─ /docs              → swagger-ui.html             │   │
│  │  ├─ /redoc             → ReDoc view                  │   │
│  │  ├─ /openapi.json      → openapi.yaml spec          │   │
│  │  └─ /health-summary    → Services health            │   │
│  └──────────────────────────────────────────────────────┘   │
│                            │                                 │
│  ┌──────────────┬──────────┴──────────┬──────────────────┐  │
│  │              │                     │                  │  │
│  ▼              ▼                     ▼                  ▼  │
│ Auth         Tenant               Channels           Billing
│ (9001)       (9002)               (9003)            (9027)
│  │              │                     │                  │
│  └──────────────┴─────────────────────┴──────────────────┘
│
└─────────────────────────────────────────────────────────────┘
```

## Authentication

All endpoints use **JWT Bearer Token** authentication (except public webhooks):

```bash
curl -X GET https://api.priyaai.com/api/v1/tenants \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Token Management
- **Access Token Lifetime**: 15 minutes
- **Refresh Token Lifetime**: 7 days
- **Algorithm**: RS256

### Obtaining Tokens
```bash
curl -X POST https://api.priyaai.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123!"
  }'
```

## Rate Limiting

Rates are plan-based with per-tenant limits:

| Plan | Requests/Minute | Requests/Hour |
|------|-----------------|---------------|
| Starter | 100 | 6,000 |
| Growth | 500 | 30,000 |
| Enterprise | 2,000 | 120,000 |

**Response Headers**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1709785200
Retry-After: 60
```

## Multi-tenancy

All requests are tenant-scoped:

```bash
curl -X GET https://api.priyaai.com/api/v1/conversations \
  -H "Authorization: Bearer {token}" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-Request-ID: {request_id}"
```

Headers automatically injected by gateway:
- **X-Tenant-ID**: Tenant identifier (from JWT)
- **X-Request-ID**: Unique request identifier for tracing
- **X-Forwarded-For**: Client IP address
- **X-Forwarded-Proto**: Protocol (https)

## Quick Start

### 1. Register
```bash
curl -X POST https://api.priyaai.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@priyaai.com",
    "password": "SecurePass123!",
    "first_name": "Priya",
    "last_name": "Singh",
    "business_name": "Tech Solutions",
    "country": "IN"
  }'
```

### 2. Login
```bash
curl -X POST https://api.priyaai.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@priyaai.com",
    "password": "SecurePass123!"
  }'
```

### 3. Connect Channel (WhatsApp)
```bash
curl -X POST https://api.priyaai.com/api/v1/channels \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "whatsapp",
    "name": "Support Channel",
    "config": {
      "phone_number_id": "123456789",
      "api_key": "your-api-key"
    }
  }'
```

### 4. Send Message
```bash
curl -X POST https://api.priyaai.com/api/v1/messages \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient": "+919876543210",
    "content": "Hello! How can we help you today?",
    "channel": "whatsapp"
  }'
```

## Webhook Events

Webhooks are sent to registered endpoints for real-time events:

**Event Types**:
- `message.received` - New incoming message
- `message.sent` - Message successfully sent
- `conversation.started` - New conversation created
- `conversation.ended` - Conversation closed
- `subscription.updated` - Subscription plan changed
- `invoice.created` - New invoice generated

**Webhook Format**:
```json
{
  "id": "evt_1234567890",
  "type": "message.received",
  "timestamp": "2024-03-06T10:30:00Z",
  "data": {
    "id": "msg_1234567890",
    "conversation_id": "conv_1234567890",
    "channel": "whatsapp",
    "content": "Hello!",
    "sender": {
      "id": "user_1234567890",
      "name": "John Doe",
      "phone": "+919876543210"
    }
  }
}
```

**Signature Verification** (HMAC-SHA256):
```python
import hmac
import hashlib

def verify_webhook(payload: str, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)
```

## Error Handling

All errors follow a consistent format:

```json
{
  "detail": "Resource not found",
  "code": "NOT_FOUND",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-03-06T10:30:00Z"
}
```

**Status Codes**:
- `200` - OK
- `201` - Created
- `204` - No Content
- `400` - Bad Request (validation error)
- `401` - Unauthorized (authentication required)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found
- `422` - Unprocessable Entity (validation error)
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error
- `502` - Bad Gateway
- `503` - Service Unavailable
- `504` - Gateway Timeout

## Regional Support

**Currencies**:
- USD - United States
- INR - India
- GBP - United Kingdom
- AUD - Australia

**Localization**:
- Phone numbers use E.164 format (+country_code)
- Dates in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
- Timezone-aware timestamps

## Integration Examples

### Python
```python
import requests
import json

BASE_URL = "https://api.priyaai.com/api/v1"
TOKEN = "your_access_token"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

# Get tenant info
response = requests.get(f"{BASE_URL}/tenants", headers=headers)
tenant = response.json()
print(json.dumps(tenant, indent=2))

# Send message
message_data = {
    "recipient": "+919876543210",
    "content": "Hello from Priya!",
    "channel": "whatsapp"
}
response = requests.post(f"{BASE_URL}/messages", json=message_data, headers=headers)
print(response.status_code)
```

### JavaScript/Node.js
```javascript
const BASE_URL = "https://api.priyaai.com/api/v1";
const TOKEN = "your_access_token";

const headers = {
  "Authorization": `Bearer ${TOKEN}`,
  "Content-Type": "application/json"
};

// Get tenant info
const tenantResponse = await fetch(`${BASE_URL}/tenants`, { headers });
const tenant = await tenantResponse.json();
console.log(tenant);

// Send message
const messageData = {
  recipient: "+919876543210",
  content: "Hello from Priya!",
  channel: "whatsapp"
};

const messageResponse = await fetch(`${BASE_URL}/messages`, {
  method: "POST",
  headers,
  body: JSON.stringify(messageData)
});

console.log(messageResponse.status);
```

## Support

- **Documentation**: https://priyaai.com/docs
- **API Status**: https://status.priyaai.com
- **Support Email**: support@priyaai.com
- **Community Forum**: https://community.priyaai.com
- **GitHub**: https://github.com/priyaai

## Versioning

Current API version: **1.0.0**

This documentation is auto-generated from the OpenAPI specification and covers:
- 36 microservices
- 200+ endpoints
- 50+ webhooks
- Complete request/response schemas
- Real-world examples (India-focused)

---

**Last Updated**: 2024-03-06
**OpenAPI Version**: 3.1.0
**FastAPI Version**: 0.100+
