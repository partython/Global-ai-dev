# Priya Global Platform - Quick Reference Card

## API Base URLs

```
Production:  https://api.priyaai.com
Staging:     https://staging.api.priyaai.com
Development: http://localhost:9000
```

## Authentication

```bash
# Register
POST /api/v1/auth/register
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "business_name": "Company",
  "country": "IN"
}

# Login
POST /api/v1/auth/login
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}

# Refresh Token
POST /api/v1/auth/refresh
Header: Authorization: Bearer {refresh_token}

# Verify 2FA
POST /api/v1/auth/verify-2fa
{
  "code": "123456"
}
```

**Include in all requests:**
```
Authorization: Bearer {access_token}
X-Tenant-ID: {tenant_id}
X-Request-ID: {request_id}
```

## Tenant Management

```bash
# Get Tenant
GET /api/v1/tenants

# Update Tenant
PATCH /api/v1/tenants
{
  "business_name": "New Name",
  "timezone": "Asia/Kolkata"
}

# Get Onboarding Status
GET /api/v1/tenants/onboarding/status

# Get Plan
GET /api/v1/tenants/plan
```

## Channels

```bash
# List Channels
GET /api/v1/channels?limit=20&offset=0

# Connect Channel
POST /api/v1/channels
{
  "type": "whatsapp|email|sms|voice|social|webchat|telegram|rcs|video",
  "name": "Channel Name",
  "config": { ... }
}

# Get Channel
GET /api/v1/channels/{channel_id}

# Test Channel
POST /api/v1/channels/{channel_id}/test

# Disconnect Channel
DELETE /api/v1/channels/{channel_id}
```

## Messages

```bash
# Send Message
POST /api/v1/messages
{
  "recipient": "+919876543210",
  "content": "Hello!",
  "channel": "whatsapp",
  "template_id": "optional"
}

# Get Message
GET /api/v1/messages/{message_id}

# List Conversations
GET /api/v1/conversations?limit=20&offset=0&status=active

# Get Conversation Messages
GET /api/v1/conversations/{conversation_id}/messages?limit=50
```

## AI Engine

```bash
# Chat
POST /api/v1/ai/chat
{
  "message": "Help text",
  "conversation_id": "optional",
  "channel": "whatsapp"
}

# Test Message
POST /api/v1/ai/test-message
{
  "message": "Help text"
}

# Configure AI
PATCH /api/v1/ai/configure
{
  "tone": "professional|friendly|casual",
  "greeting": "Hi!",
  "system_prompt": "You are...",
  "language": "en"
}

# Get History
GET /api/v1/ai/history?conversation_id={id}

# Search Knowledge Base
GET /api/v1/knowledge/search?query=search_term
```

## WhatsApp

```bash
# Send Message
POST /api/v1/whatsapp/send
{
  "phone": "+919876543210",
  "message": "Hello!"
}

# List Templates
GET /api/v1/whatsapp/templates?limit=20

# Receive Webhook
POST /webhook/whatsapp
Header: X-Webhook-Signature: {signature}
```

## Email

```bash
# Send Email
POST /api/v1/email/send
{
  "to": "user@example.com",
  "subject": "Subject",
  "body": "Plain text body",
  "html_body": "<h1>HTML</h1>",
  "template_id": "optional"
}

# List Templates
GET /api/v1/email/templates?limit=20

# Receive Webhook
POST /webhook/ses
Header: X-Webhook-Signature: {signature}
```

## Voice

```bash
# Initiate Call
POST /api/v1/voice/initiate
{
  "phone": "+919876543210",
  "greeting": "Hello, welcome!"
}

# Configure IVR
PATCH /api/v1/voice/ivr/configure
{
  "greeting": "Say 1 for support...",
  "menus": [ ... ]
}

# List Recordings
GET /api/v1/voice/recordings?limit=20
```

## SMS

```bash
# Send SMS
POST /api/v1/sms/send
{
  "phone": "+919876543210",
  "message": "Hello!"
}

# Receive Webhook
POST /webhook/sms
Header: X-Webhook-Signature: {signature}
```

## Social Media

```bash
# Post to Social
POST /api/v1/social/post
{
  "channel": "instagram|facebook|twitter",
  "content": "Post content",
  "media_urls": [ ... ]
}

# Receive Webhook
POST /webhook/social
Header: X-Webhook-Signature: {signature}
```

## Billing

```bash
# Get Subscription
GET /api/v1/billing/subscriptions

# Create Subscription
POST /api/v1/billing/subscriptions
{
  "plan": "starter|growth|enterprise",
  "currency": "USD|INR|GBP|AUD",
  "billing_cycle": "monthly|annual"
}

# Update Subscription
PATCH /api/v1/billing/subscriptions/{subscription_id}
{
  "plan": "growth",
  "status": "active|cancelled"
}

# List Invoices
GET /api/v1/billing/invoices?limit=20&offset=0

# Get Invoice
GET /api/v1/billing/invoices/{invoice_id}

# Download Invoice
GET /api/v1/billing/invoices/{invoice_id}/download

# Get Usage
GET /api/v1/billing/usage?period=current|last_month

# Stripe Webhook
POST /webhook/stripe
Header: X-Webhook-Signature: {signature}
```

## Analytics

```bash
# Dashboard Stats
GET /api/v1/analytics/dashboard?period=today|last_7_days|last_30_days|last_90_days

# List Reports
GET /api/v1/analytics/reports?limit=20

# Create Custom Report
POST /api/v1/analytics/reports
{
  "name": "Report Name",
  "metrics": [ "metric1", "metric2" ],
  "dimensions": [ "dimension1" ],
  "filters": { ... },
  "schedule": "daily|weekly|monthly"
}

# Export Data
POST /api/v1/analytics/export
{
  "format": "csv|json|xlsx",
  "period": "last_30_days",
  "metrics": [ ... ]
}
```

## Webhooks

```bash
# Register Webhook
POST /api/v1/webhooks
{
  "url": "https://myapp.com/webhook",
  "events": [
    "message.received",
    "conversation.started",
    "subscription.updated"
  ],
  "active": true
}

# List Webhooks
GET /api/v1/webhooks?limit=20

# Delete Webhook
DELETE /api/v1/webhooks/{webhook_id}
```

## Workflows

```bash
# List Workflows
GET /api/v1/workflows?limit=20

# Create Workflow
POST /api/v1/workflows
{
  "name": "Workflow Name",
  "trigger": "message.received",
  "actions": [ ... ],
  "status": "active|paused|draft"
}
```

## Handoff

```bash
# Create Handoff
POST /api/v1/handoff
{
  "conversation_id": "{id}",
  "reason": "Customer request",
  "assigned_to": "{agent_id}"
}
```

## Health & Status

```bash
# Gateway Health
GET /health

# Services Health
GET /health/services

# Health Summary for Docs
GET /docs/health-summary
```

## Documentation

```bash
# Swagger UI
GET /docs

# ReDoc
GET /redoc

# OpenAPI JSON
GET /docs/openapi.json

# Download Spec
GET /docs/download-spec?format=yaml|json

# API Guides
GET /docs/guides

# Code Examples
GET /docs/examples

# Services List
GET /docs/services

# API Key Management
GET /docs/api-key-management

# Changelog
GET /docs/changelog
```

## Error Responses

```json
{
  "detail": "Error message",
  "code": "ERROR_CODE",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-03-06T10:30:00Z"
}
```

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK |
| 201 | Created |
| 204 | No Content |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Unprocessable Entity |
| 429 | Rate Limited |
| 500 | Server Error |
| 502 | Bad Gateway |
| 503 | Unavailable |
| 504 | Timeout |

## Rate Limits

| Plan | Req/Min | Req/Hour |
|------|---------|----------|
| Starter | 100 | 6,000 |
| Growth | 500 | 30,000 |
| Enterprise | 2,000 | 120,000 |

**Headers:**
```
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 423
X-RateLimit-Reset: 1709785200
Retry-After: 60
```

## Webhook Event Types

- `message.received` - Incoming message
- `message.sent` - Message delivered
- `message.failed` - Delivery failed
- `conversation.started` - New conversation
- `conversation.ended` - Conversation closed
- `conversation.assigned` - Assigned to agent
- `subscription.updated` - Plan changed
- `subscription.cancelled` - Subscription cancelled
- `invoice.created` - Invoice generated
- `invoice.paid` - Invoice paid

## Token Info

- **Access Token**: 15 minutes lifetime
- **Refresh Token**: 7 days lifetime
- **Algorithm**: RS256 (RSA)
- **Format**: JWT Bearer

## Regional Currencies

- USD - United States
- INR - India
- GBP - United Kingdom
- AUD - Australia

## Supported Channels

- WhatsApp Business
- Email (SMTP/SES)
- SMS (Twilio, AWS SNS)
- Voice (Twilio, AWS Connect)
- Instagram
- Facebook
- Twitter/X
- Telegram
- Web Chat
- RCS
- Video

## Common Headers

```
Authorization: Bearer {token}
Content-Type: application/json
X-Tenant-ID: {tenant_id}
X-Request-ID: {request_id}
X-Webhook-Signature: {signature}
Accept: application/json
Accept-Encoding: gzip, deflate
```

## Environment Variables

```bash
PRIYA_EMAIL=admin@mycompany.com
PRIYA_PASSWORD=SecurePass123!
PRIYA_API_URL=https://api.priyaai.com
PRIYA_ENVIRONMENT=production
```

## SDK Installation

**Python:**
```bash
pip install priya-global
```

**Node.js:**
```bash
npm install @priya-global/sdk
```

**Go:**
```bash
go get github.com/priya-ai/sdk
```

## Resources

- **API Docs**: https://api.priyaai.com/docs
- **Website**: https://priyaai.com
- **Support**: support@priyaai.com
- **Status Page**: https://status.priyaai.com
- **GitHub**: https://github.com/priyaai
- **Community**: https://community.priyaai.com

---

**API Version**: 1.0.0 | **Last Updated**: 2024-03-06
