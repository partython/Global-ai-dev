# Priya Global Platform - Developer Integration Guide

Complete guide for integrating the Priya Global Platform API into your applications.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Authentication](#authentication)
3. [Multi-tenancy](#multi-tenancy)
4. [Channels](#channels)
5. [AI Integration](#ai-integration)
6. [Webhooks](#webhooks)
7. [Rate Limiting](#rate-limiting)
8. [Error Handling](#error-handling)
9. [SDK Examples](#sdk-examples)
10. [Best Practices](#best-practices)

## Getting Started

### Prerequisites

- API credentials (email + password or OAuth)
- JWT token (obtained via login)
- Tenant ID (assigned on registration)
- HTTPS-enabled application

### Base URL

```
Production:  https://api.priyaai.com
Staging:     https://staging.api.priyaai.com
Development: http://localhost:9000
```

### API Version

Current stable version: `v1.0.0`

All endpoints follow the pattern: `/api/v1/{service}/{endpoint}`

## Authentication

### 1. User Registration

Register a new tenant and user account:

```bash
curl -X POST https://api.priyaai.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@mycompany.com",
    "password": "SecurePass123!",
    "first_name": "John",
    "last_name": "Doe",
    "business_name": "My Company Ltd",
    "country": "IN"
  }'
```

**Response** (201 Created):
```json
{
  "id": "usr_1234567890",
  "email": "admin@mycompany.com",
  "tenant_id": "tnt_0987654321",
  "status": "onboarding",
  "created_at": "2024-03-06T10:30:00Z"
}
```

### 2. User Login

Obtain access and refresh tokens:

```bash
curl -X POST https://api.priyaai.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@mycompany.com",
    "password": "SecurePass123!"
  }'
```

**Response** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### 3. Token Management

**Include token in requests**:
```bash
curl -X GET https://api.priyaai.com/api/v1/tenants \
  -H "Authorization: Bearer {access_token}"
```

**Refresh token when expired** (token expires in 15 minutes):
```bash
curl -X POST https://api.priyaai.com/api/v1/auth/refresh \
  -H "Authorization: Bearer {refresh_token}"
```

**Token Claims** (JWT payload):
```json
{
  "sub": "usr_1234567890",
  "tenant_id": "tnt_0987654321",
  "email": "admin@mycompany.com",
  "role": "owner",
  "exp": 1709785200,
  "iat": 1709783400
}
```

### 4. Two-Factor Authentication

Enable 2FA for extra security:

```bash
# Enable 2FA - receive TOTP secret
curl -X POST https://api.priyaai.com/api/v1/auth/2fa/enable \
  -H "Authorization: Bearer {access_token}"

# Verify 2FA code
curl -X POST https://api.priyaai.com/api/v1/auth/verify-2fa \
  -H "Content-Type: application/json" \
  -d '{
    "code": "123456"
  }'
```

## Multi-tenancy

The platform uses strict tenant isolation:

### Tenant Context

Every authenticated request automatically includes tenant context:

```bash
curl -X GET https://api.priyaai.com/api/v1/conversations \
  -H "Authorization: Bearer {access_token}" \
  -H "X-Tenant-ID: {tenant_id}" \
  -H "X-Request-ID: {request_id}"
```

### Tenant Operations

**Get tenant details**:
```bash
curl -X GET https://api.priyaai.com/api/v1/tenants \
  -H "Authorization: Bearer {access_token}"
```

Response:
```json
{
  "id": "tnt_0987654321",
  "name": "My Company Ltd",
  "industry": "Technology",
  "country": "IN",
  "plan": "growth",
  "status": "active",
  "users_count": 5,
  "conversations_count": 1234,
  "created_at": "2024-03-06T10:00:00Z"
}
```

**Update tenant settings**:
```bash
curl -X PATCH https://api.priyaai.com/api/v1/tenants \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "My Company Ltd (Updated)",
    "timezone": "Asia/Kolkata",
    "primary_color": "#0066CC"
  }'
```

**Get onboarding status**:
```bash
curl -X GET https://api.priyaai.com/api/v1/tenants/onboarding/status \
  -H "Authorization: Bearer {access_token}"
```

Response:
```json
{
  "current_step": 2,
  "total_steps": 5,
  "completed_steps": ["account_created", "channels_connected"]
}
```

## Channels

Connect communication channels to reach customers:

### Supported Channels

- WhatsApp Business
- Email (SMTP/SES)
- SMS (Twilio, AWS SNS)
- Voice (Twilio, AWS Connect)
- Social (Instagram, Facebook, Twitter)
- Web Chat (Embedded widget)
- Telegram
- RCS (Rich Communication Services)
- Video (Jitsi, Zoom)

### Connect WhatsApp Channel

```bash
curl -X POST https://api.priyaai.com/api/v1/channels \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "whatsapp",
    "name": "Support Channel",
    "config": {
      "phone_number_id": "123456789",
      "api_key": "your-meta-api-key",
      "webhook_verify_token": "your-verify-token"
    }
  }'
```

Response (201 Created):
```json
{
  "id": "ch_1234567890",
  "type": "whatsapp",
  "name": "Support Channel",
  "status": "connected",
  "config": {
    "phone_number": "+919876543210"
  },
  "created_at": "2024-03-06T10:30:00Z",
  "last_tested_at": "2024-03-06T10:35:00Z"
}
```

### Connect Email Channel

```bash
curl -X POST https://api.priyaai.com/api/v1/channels \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "email",
    "name": "Support Email",
    "config": {
      "smtp_host": "email-smtp.ap-south-1.amazonaws.com",
      "smtp_port": 587,
      "smtp_username": "YOUR_SMTP_USERNAME_HERE",
      "smtp_password": "YOUR_SMTP_PASSWORD_HERE",
      "from_email": "support@mycompany.com",
      "from_name": "My Company Support"
    }
  }'
```

### Test Channel

```bash
curl -X POST https://api.priyaai.com/api/v1/channels/{channel_id}/test \
  -H "Authorization: Bearer {access_token}"
```

### List Channels

```bash
curl -X GET https://api.priyaai.com/api/v1/channels \
  -H "Authorization: Bearer {access_token}" \
  -H "X-Tenant-ID: {tenant_id}"
```

Response:
```json
{
  "data": [
    {
      "id": "ch_1234567890",
      "type": "whatsapp",
      "name": "Support Channel",
      "status": "connected"
    },
    {
      "id": "ch_0987654321",
      "type": "email",
      "name": "Support Email",
      "status": "connected"
    }
  ],
  "pagination": {
    "total": 2,
    "limit": 20,
    "offset": 0,
    "has_more": false
  }
}
```

## AI Integration

Use the AI Engine for intelligent responses:

### Basic Chat

```bash
curl -X POST https://api.priyaai.com/api/v1/ai/chat \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are your business hours?",
    "channel": "whatsapp"
  }'
```

Response:
```json
{
  "id": "msg_1234567890",
  "message": "We are open Monday to Friday, 9 AM to 6 PM IST. On weekends, we're available on WhatsApp for urgent queries.",
  "confidence": 0.95,
  "sources": ["kb_article_001", "kb_article_002"],
  "sentiment": "positive",
  "requires_handoff": false
}
```

### Configure AI Personality

```bash
curl -X PATCH https://api.priyaai.com/api/v1/ai/configure \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "tone": "professional",
    "greeting": "Hello! Welcome to My Company. How can I assist you today?",
    "system_prompt": "You are a helpful customer support representative for My Company Ltd. Focus on solving customer issues quickly and professionally.",
    "language": "en"
  }'
```

### Get Conversation History

```bash
curl -X GET "https://api.priyaai.com/api/v1/ai/history?conversation_id={conv_id}" \
  -H "Authorization: Bearer {access_token}"
```

### Search Knowledge Base

```bash
curl -X GET "https://api.priyaai.com/api/v1/knowledge/search?query=billing" \
  -H "Authorization: Bearer {access_token}"
```

Response:
```json
{
  "data": [
    {
      "id": "kb_article_001",
      "title": "How to manage billing",
      "content": "...",
      "category": "Billing",
      "relevance_score": 0.98
    }
  ],
  "pagination": {
    "total": 3,
    "limit": 20,
    "offset": 0,
    "has_more": false
  }
}
```

## Webhooks

Receive real-time events from Priya:

### Register Webhook

```bash
curl -X POST https://api.priyaai.com/api/v1/webhooks \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://myapp.example.com/webhook/priya",
    "events": [
      "message.received",
      "conversation.started",
      "subscription.updated"
    ],
    "active": true
  }'
```

Response:
```json
{
  "id": "wh_1234567890",
  "url": "https://myapp.example.com/webhook/priya",
  "events": ["message.received", "conversation.started"],
  "secret": "YOUR_WEBHOOK_SECRET_HERE",
  "active": true
}
```

**Important**: Store the webhook secret securely in your environment variables or secure configuration system. Never commit it to version control.

### Webhook Payload

All webhooks follow this format:

```json
{
  "id": "evt_1234567890",
  "type": "message.received",
  "timestamp": "2024-03-06T10:30:00Z",
  "data": {
    "id": "msg_1234567890",
    "conversation_id": "conv_1234567890",
    "channel": "whatsapp",
    "content": "Hello! I need help with my order",
    "sender": {
      "id": "cust_0987654321",
      "name": "Ramesh Kumar",
      "phone": "+919876543210"
    },
    "status": "delivered"
  }
}
```

### Verify Webhook Signature

**Header**: `X-Webhook-Signature`

Verify using HMAC-SHA256:

```python
import hmac
import hashlib
import json

def verify_webhook(request_body: str, signature: str, secret: str) -> bool:
    """Verify webhook signature"""
    expected_signature = hmac.new(
        secret.encode(),
        request_body.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)

# In your webhook handler
@app.post("/webhook/priya")
async def handle_webhook(request):
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    secret = os.getenv("PRIYA_WEBHOOK_SECRET")  # Load from environment variable

    if not verify_webhook(body.decode(), signature, secret):
        return {"error": "Invalid signature"}, 401

    payload = json.loads(body)
    event_type = payload["type"]

    if event_type == "message.received":
        # Handle incoming message
        message = payload["data"]
        print(f"Message from {message['sender']['phone']}: {message['content']}")

    return {"status": "ok"}, 200
```

### Webhook Event Types

- `message.received` - New incoming message
- `message.sent` - Message successfully sent
- `message.failed` - Message delivery failed
- `conversation.started` - New conversation created
- `conversation.ended` - Conversation closed
- `conversation.assigned` - Assigned to agent
- `subscription.updated` - Plan changed
- `subscription.cancelled` - Subscription cancelled
- `invoice.created` - New invoice generated
- `invoice.paid` - Invoice payment received

## Rate Limiting

Plan-based rate limiting ensures fair usage:

### Check Rate Limit Status

Response headers included in every API response:

```
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 423
X-RateLimit-Reset: 1709785200
```

- **X-RateLimit-Limit**: Maximum requests per hour
- **X-RateLimit-Remaining**: Requests remaining in window
- **X-RateLimit-Reset**: Unix timestamp when limit resets
- **Retry-After**: Seconds to wait (when limited)

### Plan Limits

| Plan | Req/Min | Req/Hour | Req/Day |
|------|---------|----------|---------|
| Starter | 100 | 6,000 | 144,000 |
| Growth | 500 | 30,000 | 720,000 |
| Enterprise | 2,000 | 120,000 | 2,880,000 |

### Handle Rate Limiting

```python
import time

def api_call_with_retry(url, headers, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)

        if response.status_code == 429:
            # Rate limited
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            continue

        return response

    raise Exception("Max retries exceeded")
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

### Common Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource created successfully |
| 204 | No Content | Successful, no response body |
| 400 | Bad Request | Invalid parameters, check body |
| 401 | Unauthorized | Invalid/missing authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 422 | Unprocessable | Validation error in request |
| 429 | Rate Limited | Too many requests, retry later |
| 500 | Server Error | Platform error, retry later |
| 502 | Bad Gateway | Service unavailable |
| 503 | Unavailable | Maintenance, try again later |
| 504 | Timeout | Request took too long |

### Error Handling Example

```python
import requests
from requests.exceptions import RequestException

def safe_api_call(method, url, **kwargs):
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as e:
        error = e.response.json()

        if e.response.status_code == 401:
            # Re-authenticate
            print("Auth failed, need to refresh token")
        elif e.response.status_code == 429:
            # Rate limited
            retry_after = int(e.response.headers.get("Retry-After", 60))
            print(f"Rate limited, retry after {retry_after}s")
        elif e.response.status_code >= 500:
            # Server error, exponential backoff
            print("Server error, retrying with backoff...")

        raise Exception(f"{error['code']}: {error['detail']}")

    except RequestException as e:
        print(f"Network error: {e}")
        raise
```

## SDK Examples

### Python

```python
from priya_global import PriyaClient

# Initialize client
client = PriyaClient(
    email="admin@mycompany.com",
    password="SecurePass123!",
    environment="production"  # or "staging"
)

# Get tenant info
tenant = client.tenants.get()
print(f"Tenant: {tenant['name']}")

# List channels
channels = client.channels.list()
for channel in channels:
    print(f"Channel: {channel['type']} - {channel['name']}")

# Send message
message = client.messages.send(
    recipient="+919876543210",
    content="Hello from Priya!",
    channel="whatsapp"
)

# Chat with AI
response = client.ai.chat(
    message="What are your products?",
    channel="whatsapp"
)
print(f"AI: {response['message']}")
```

### JavaScript/Node.js

```javascript
import { PriyaClient } from '@priya-global/sdk';

// Initialize client
const client = new PriyaClient({
  email: 'admin@mycompany.com',
  password: 'SecurePass123!',
  environment: 'production'
});

// Get tenant info
const tenant = await client.tenants.get();
console.log(`Tenant: ${tenant.name}`);

// List channels
const channels = await client.channels.list();
channels.forEach(ch => {
  console.log(`Channel: ${ch.type} - ${ch.name}`);
});

// Send message
const message = await client.messages.send({
  recipient: '+919876543210',
  content: 'Hello from Priya!',
  channel: 'whatsapp'
});

// Chat with AI
const response = await client.ai.chat({
  message: 'What are your products?',
  channel: 'whatsapp'
});
console.log(`AI: ${response.message}`);
```

## Best Practices

### 1. Security

- **Store tokens securely** (never in client-side code)
- **Use environment variables** for credentials
- **Rotate refresh tokens** regularly
- **Enable 2FA** on admin accounts
- **Use HTTPS** for all requests

```python
import os
from dotenv import load_dotenv

load_dotenv()

email = os.getenv("PRIYA_EMAIL")
password = os.getenv("PRIYA_PASSWORD")
# Never hardcode credentials!
```

### 2. Error Handling

- **Always handle 429 (rate limit)** responses
- **Implement exponential backoff** for retries
- **Log request IDs** for debugging
- **Monitor error rates** in production

### 3. Performance

- **Cache tokens** (valid for 15 minutes)
- **Batch requests** when possible
- **Use pagination** for large datasets
- **Monitor response times** in X-RateLimit headers

```python
# Pagination example
page = 1
limit = 50
all_conversations = []

while True:
    conversations = client.conversations.list(
        limit=limit,
        offset=(page - 1) * limit
    )

    all_conversations.extend(conversations['data'])

    if not conversations['pagination']['has_more']:
        break

    page += 1
```

### 4. Testing

- **Use staging environment** for testing
- **Test webhook handlers** locally
- **Verify error scenarios**
- **Load test rate limiting**

### 5. Monitoring

- **Track API response times**
- **Monitor error rates**
- **Alert on webhook failures**
- **Log all important events**

---

**For more information**: https://priyaai.com/docs
**Support**: support@priyaai.com
