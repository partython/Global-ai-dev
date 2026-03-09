# WhatsApp Service Setup Guide

Complete setup instructions for deploying the Meta WhatsApp Business API integration.

## Prerequisites

- PostgreSQL 12+ with admin access
- Redis 6+ for caching
- Meta WhatsApp Business Account
- Meta App (for API credentials)
- Python 3.11+

## Step 1: Create Meta App & WhatsApp Business Account

### 1.1 Create Meta App

1. Go to [Meta Developers](https://developers.facebook.com/apps)
2. Click "Create App" → Choose "Business" type
3. Fill in app details:
   - App Name: `Priya Global WhatsApp`
   - App Contact Email: your-email@company.com
   - App Purpose: Select "App to run my business"
4. Click "Create App"

### 1.2 Add WhatsApp Product

1. In your app dashboard, click "Add Product"
2. Find "WhatsApp" → Click "Set Up"
3. Select your existing WhatsApp Business Account or create new one
4. Accept terms and proceed

### 1.3 Get API Credentials

In the app dashboard:

1. Go to **Settings** → **Basic**
   - Copy **App ID**
   - Copy **App Secret** (use this for webhook signature verification)
   - This is your `WHATSAPP_APP_SECRET`

2. Go to **WhatsApp** → **Getting Started**
   - Get your **Business Account ID**
   - Get your **Phone Number ID** (for each registered number)

3. Go to **WhatsApp** → **API Setup** → **Temporary Access Token**
   - Generate temporary token (valid 24h)
   - Store this as `access_token` in channel_connections metadata
   - **IMPORTANT**: Before going to production, set up a permanent token via system user

### 1.4 Set Up Permanent Access Token

1. In app dashboard, go to **Users** → **System Users**
2. Click "Add System User"
3. Select role: "Admin"
4. Assign permissions:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
   - `whatsapp_business_account_management`
5. Generate token from "Tokens" section
6. Copy token and store securely

## Step 2: Database Setup

### 2.1 Run Migrations

```bash
# Connect to PostgreSQL as admin
psql -h localhost -U postgres -d priya_global -f /path/to/services/whatsapp/migrations.sql

# Verify tables created
psql -h localhost -U priya_admin -d priya_global -c \
  "SELECT tablename FROM pg_tables WHERE tablename LIKE 'whatsapp_%' ORDER BY tablename;"

# Expected output:
# whatsapp_audit_log
# whatsapp_conversations
# whatsapp_media
# whatsapp_messages
# whatsapp_phone_quality
# whatsapp_templates
# whatsapp_webhook_events
```

### 2.2 Verify Row Level Security

```sql
-- Check RLS is enabled
SELECT tablename, rowsecurity
FROM pg_tables
WHERE tablename LIKE 'whatsapp_%'
ORDER BY tablename;

-- Check policies exist
SELECT schemaname, tablename, policyname
FROM pg_policies
WHERE tablename LIKE 'whatsapp_%'
ORDER BY tablename;
```

### 2.3 Insert Channel Connection

```sql
-- For each tenant, create a channel connection
-- Replace VALUES with actual data from Meta

INSERT INTO channel_connections (
    id,
    channel,
    tenant_id,
    channel_metadata,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'whatsapp',
    'your-tenant-id-here',
    jsonb_build_object(
        'phone_number_id', '1234567890123456',
        'business_account_id', '123456789012345',
        'access_token', 'EABsZA...',
        'display_phone_number', '+1 (234) 567-8900',
        'business_name', 'Acme Sales',
        'business_category', 'GENERAL',
        'quality_rating', 'GREEN',
        'quality_score', 100.0
    ),
    NOW(),
    NOW()
);

-- Verify
SELECT channel, tenant_id, channel_metadata
FROM channel_connections
WHERE channel = 'whatsapp';
```

## Step 3: Configure Environment

### 3.1 Create `.env` File

```bash
# .env or docker-compose.override.yml

# ─── Core Settings ───
ENVIRONMENT=production
LOG_LEVEL=INFO
DEBUG=false

# ─── Database ───
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=priya_global
PG_USER=priya_admin
PG_PASSWORD=your-secure-password-here
PG_SSL_MODE=require

# ─── Redis ───
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_SSL=false

# ─── JWT ───
JWT_SECRET_KEY=your-rs256-private-key-in-pem-format
JWT_PUBLIC_KEY=your-rs256-public-key-in-pem-format
JWT_ISSUER=priya-global

# ─── WhatsApp ───
WHATSAPP_APP_SECRET=your-meta-app-secret-here
WHATSAPP_VERIFY_TOKEN=priya_whatsapp_webhook_token

# ─── AWS (if using S3 for media) ───
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
S3_BUCKET=priya-global-media
```

### 3.2 Load Environment Variables

```bash
# In your shell before running service
export $(cat .env | xargs)

# Or use direnv
echo "export $(cat .env | xargs)" > .envrc
direnv allow
```

## Step 4: Configure Meta Webhook

### 4.1 Set Webhook URL

1. Go to Meta App Dashboard
2. Navigate to **WhatsApp** → **Configuration**
3. Under "Webhook URL":
   - Enter: `https://api.priyaai.com/whatsapp/webhook` (or your domain)
   - Enter Verify Token: `priya_whatsapp_webhook_token`
   - Click "Verify and Save"

4. Meta will send verification request:
   ```
   GET /webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
   ```
   Service automatically responds with the challenge.

### 4.2 Subscribe to Webhook Events

In Meta App Dashboard:

1. Go to **WhatsApp** → **Configuration** → **Webhook fields**
2. Subscribe to:
   - ✓ `messages` - Inbound customer messages
   - ✓ `message_status` - Delivery status updates (sent, delivered, read, failed)
   - ✓ `message_template_status_update` - Template approval changes
   - ✓ `phones` - Phone number profile changes

### 4.3 Test Webhook

```bash
# From Meta App Dashboard, click "Test Webhook"
# Should see success response

# Or manually test with curl:
curl -X GET "http://localhost:9010/webhook?hub.mode=subscribe&hub.verify_token=priya_whatsapp_webhook_token&hub.challenge=test-challenge-12345"

# Should return:
# 12345
```

## Step 5: Register Phone Number

### 5.1 Via Meta Dashboard

1. Go to **WhatsApp** → **Getting Started** → **Phone Numbers**
2. Click "Add Phone Number"
3. Choose existing or add new
4. Complete phone verification (SMS or call)
5. Once verified, note the **Phone Number ID**

### 5.2 Via API

```bash
# Register in your database
curl -X POST "http://localhost:9010/api/v1/phone-numbers/register" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+1234567890",
    "display_name": "Sales Support",
    "business_name": "Acme Corp",
    "business_category": "GENERAL"
  }'

# Response:
# {
#   "status": "registered",
#   "phone_number": "+1234567890",
#   "message": "Phone number registered. Complete verification in Meta dashboard."
# }
```

### 5.3 Verify in Database

```sql
SELECT channel_metadata ->> 'phone_number_id' as phone_id,
       channel_metadata ->> 'display_phone_number' as display_phone,
       channel_metadata ->> 'business_name' as business_name
FROM channel_connections
WHERE channel = 'whatsapp'
  AND tenant_id = 'your-tenant-id';
```

## Step 6: Create Message Templates

### 6.1 Create Template via API

```bash
curl -X POST "http://localhost:9010/api/v1/templates" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "order_confirmation",
    "category": "UTILITY",
    "language": "en_US",
    "body": "Hi {{1}}, your order {{2}} has been confirmed and will arrive within {{3}} days.",
    "header_text": "Order Confirmation",
    "footer": "Thank you for shopping with us!",
    "buttons": [
      {
        "type": "url",
        "text": "Track Order",
        "url": "https://example.com/track/{{2}}"
      }
    ]
  }'

# Response:
# {
#   "template_id": "123456789012345",
#   "name": "order_confirmation",
#   "status": "PENDING",
#   "message": "Template submitted for Meta approval"
# }
```

### 6.2 Monitor Template Approval

```bash
# Check status
curl -X GET "http://localhost:9010/api/v1/templates/order_confirmation" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Meta typically approves within 2-24 hours
# Status will change from PENDING → APPROVED (or REJECTED)
```

## Step 7: Test Integration

### 7.1 Test Webhook Reception

Meta will send test events. Monitor logs:

```bash
tail -f /var/log/priya/whatsapp.log

# Look for:
# "Webhook received: ..."
# "Webhook verified successfully"
```

### 7.2 Test Message Sending

```bash
# Send a test message
curl -X POST "http://localhost:9010/api/v1/send" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "1234567890",
    "type": "text",
    "text": "Hello from Priya!",
    "preview_url": true
  }'

# Success response:
# {
#   "message_id": "wamid.xxxxxx=",
#   "status": "sent",
#   "sent_at": "2026-03-06T10:30:00Z"
# }

# Verify in database
psql -h localhost -U priya_admin -d priya_global -c \
  "SELECT message_id, status, created_at FROM whatsapp_messages ORDER BY created_at DESC LIMIT 5;"
```

### 7.3 Monitor Delivery Status

Wait a few seconds, then check:

```bash
# You should receive webhook with status update
# Message status should change to 'delivered' or 'read' in DB

psql -h localhost -U priya_admin -d priya_global -c \
  "SELECT message_id, status, updated_at FROM whatsapp_messages WHERE status != 'sent' ORDER BY updated_at DESC LIMIT 5;"
```

### 7.4 Test 24-Hour Window

```bash
# Send first message (window opens)
curl -X POST "http://localhost:9010/api/v1/send" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "to": "1234567890",
    "type": "text",
    "text": "Test message"
  }'

# Try sending non-template message > 24h later (should fail)
# Error: "24-hour conversation window expired. Use templates to initiate new conversation."

# Send template message (should work even outside window)
curl -X POST "http://localhost:9010/api/v1/send" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "to": "1234567890",
    "type": "template",
    "template_name": "order_confirmation",
    "template_params": ["John", "ORDER123", "2"]
  }'
```

## Step 8: Production Deployment

### 8.1 Scale Replicas

```yaml
# kubernetes deployment
replicas: 3  # Horizontal scaling for webhook processing
```

### 8.2 Set Up Monitoring

```bash
# Prometheus metrics endpoint
# GET /metrics

# Alert on:
# - Webhook processing latency > 2s
# - Failed message rate > 1%
# - Phone number quality DROP (GREEN → YELLOW)
# - Webhook signature failures
```

### 8.3 Configure Logging

```python
# ELK Stack / CloudWatch / Datadog
# All logs include:
# - tenant_id (for multi-tenant correlation)
# - message_id (for tracing)
# - PII masking (no raw customer data)
```

### 8.4 Backup & Disaster Recovery

```bash
# Daily backup of PostgreSQL
pg_dump -h localhost -U priya_admin priya_global \
  | gzip > /backups/priya_global_$(date +%Y%m%d).sql.gz

# Backup retention: 30 days minimum
```

## Step 9: Security Hardening

### 9.1 Secure API Endpoints

- [ ] All endpoints require valid JWT with tenant_id
- [ ] HTTPS only (TLS 1.3+)
- [ ] Rate limiting enabled (100 req/min per tenant)
- [ ] CORS configured for frontend domain only

### 9.2 Webhook Security

- [ ] Signature verification on EVERY webhook (HMAC SHA256)
- [ ] Webhook payload validated against schema
- [ ] Idempotency checking (no duplicate processing)
- [ ] Timeout limits (30s max processing)

### 9.3 Data Protection

- [ ] RLS policies enforced at DB layer
- [ ] PII masking in all logs
- [ ] Media stored with encryption at rest
- [ ] Access tokens never logged or stored in plaintext

### 9.4 Compliance

- [ ] GDPR: Customer data deletion on request
- [ ] CCPA: Privacy policy mentions WhatsApp
- [ ] Message templates reviewed for compliance
- [ ] Audit log retention: 90 days minimum

## Troubleshooting

### Webhook Verification Fails

```bash
# Check environment variables
echo $WHATSAPP_APP_SECRET
echo $WHATSAPP_VERIFY_TOKEN

# Verify service is running
curl http://localhost:9010/health

# Check logs
tail -f logs/whatsapp.log | grep "signature"
```

### Messages Not Sending

```sql
-- Check phone number is registered
SELECT channel_metadata
FROM channel_connections
WHERE channel = 'whatsapp' AND tenant_id = 'your-tenant-id';

-- Check access token is valid (should be recent)
-- Regenerate if older than 30 days

-- Check conversation window
SELECT * FROM whatsapp_conversations
WHERE customer_phone = '1234567890';

-- If window expired, check last_customer_message_at
-- Must be within 24 hours OR use template message
```

### Template Approval Stuck

```sql
-- Check template status
SELECT name, status, rejection_reason, created_at
FROM whatsapp_templates
WHERE tenant_id = 'your-tenant-id'
ORDER BY created_at DESC;

-- If REJECTED, read rejection_reason
-- Common issues:
-- - Header/body contains variables not properly formatted
-- - Content violates Meta guidelines
-- - Language mismatch

-- Resubmit after fixing:
DELETE FROM whatsapp_templates WHERE name = 'problematic_template';
-- Then use API to create corrected template
```

### High Webhook Latency

```bash
# Check database connection pool
# Should see connection reuse, not creating new connections

# Monitor Channel Router response time
# If slow, check: AI engine, message queue

# Scale replicas if webhook queue building up
```

## Monitoring Dashboard

Key metrics to track:

```
Dashboard: WhatsApp Service Health

Panels:
1. Message Throughput (inbound/outbound messages/sec)
2. Webhook Latency (P50, P95, P99)
3. Delivery Rate (% of messages delivered)
4. Template Approval Rate (% approved vs rejected)
5. Phone Number Quality (GREEN/YELLOW/RED count)
6. Error Rate (webhook failures, API errors)
7. Conversation Windows (% within 24h vs expired)

Alerts:
- Webhook latency > 2s
- Message delivery rate < 95%
- Phone number quality DROP
- Webhook signature failures > 0.1%
```

## Next Steps

1. ✓ Complete all setup steps above
2. ✓ Test thoroughly in staging environment
3. ✓ Monitor production deployment
4. ✓ Set up on-call rotations for incidents
5. ✓ Document tenant-specific configurations
6. ✓ Plan quarterly security audits

## Support

For issues or questions:
- Check service logs: `/var/log/priya/whatsapp.log`
- Review Meta API docs: https://developers.facebook.com/docs/whatsapp/cloud-api/
- Contact platform team: platform@priyaai.com
