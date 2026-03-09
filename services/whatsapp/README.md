# WhatsApp Channel Service

Meta WhatsApp Business API direct integration for the Priya Global multi-tenant AI sales platform.

**Service Port:** 9010
**Database:** PostgreSQL (multi-tenant with Row-Level Security)
**Auth:** JWT Bearer + API Key
**Webhook Signature:** HMAC SHA256

## Architecture

This service handles ALL WhatsApp communication for the platform:

- **Inbound**: Receive all customer messages from Meta webhook
- **Outbound**: Send normalized messages via Meta API
- **Templates**: Create, manage, and track approval status
- **Media**: Download/upload with validation and caching
- **Conversations**: Track 24-hour customer service windows
- **Quality**: Monitor phone number quality ratings
- **Multi-tenant**: Route by phone_number_id → tenant_id

## Key Features

### 1. Webhook Verification & Reception

**GET /webhook** - Meta verification challenge
```bash
GET /webhook?hub.mode=subscribe&hub.verify_token=TOKEN&hub.challenge=CHALLENGE
```

**POST /webhook** - Receive events with signature verification
```bash
POST /webhook
X-Hub-Signature-256: sha256=SIGNATURE
Content-Type: application/json

{
  "object": "whatsapp_business_account",
  "entry": [...]
}
```

### 2. Inbound Message Processing

Handles all WhatsApp message types:
- `text` - Plain text messages
- `image`, `audio`, `video`, `document` - Media with Meta download
- `location` - GPS coordinates + name/address
- `contacts` - Contact card information
- `interactive` - Buttons, lists, products
- `reaction` - Emoji reactions to messages
- `sticker` - Sticker files
- `order` - Product orders
- `template` - Template responses

Media is downloaded from Meta, validated, and stored temporarily.

### 3. Message Status Tracking

Webhook receives status updates:
- `sent` - Message accepted by Meta
- `delivered` - Reached customer's phone
- `read` - Customer opened message
- `failed` - Delivery failure

### 4. 24-Hour Conversation Window

**Critical for pricing and compliance:**
- Customer initiates: 24-hour window opens (reply with ANY message type)
- Window expires: Only pre-approved templates allowed
- Tracks timestamps in `whatsapp_conversations` table

```sql
-- Schema
CREATE TABLE whatsapp_conversations (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  phone_number_id VARCHAR(255) NOT NULL,
  customer_phone VARCHAR(20) NOT NULL,
  conversation_category VARCHAR(20),  -- user_initiated | business_initiated
  last_customer_message_at TIMESTAMP,
  last_business_message_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(tenant_id, phone_number_id, customer_phone)
);

CREATE TABLE whatsapp_messages (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  phone_number_id VARCHAR(255) NOT NULL,
  message_id VARCHAR(255) UNIQUE NOT NULL,
  customer_phone VARCHAR(20) NOT NULL,
  message_type VARCHAR(50),
  status VARCHAR(20),  -- sent | delivered | read | failed
  error_details JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE whatsapp_templates (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  template_id VARCHAR(255),
  name VARCHAR(512) NOT NULL,
  category VARCHAR(50),  -- MARKETING | AUTHENTICATION | UTILITY
  language VARCHAR(10),
  body TEXT,
  header_text TEXT,
  footer TEXT,
  components JSONB,
  status VARCHAR(20),  -- PENDING | APPROVED | REJECTED
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE whatsapp_media (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  media_id VARCHAR(255) UNIQUE NOT NULL,
  media_type VARCHAR(50),
  media_url TEXT,
  size_bytes INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

## API Endpoints

### Outbound Sending

**POST /api/v1/send** - Send message
```bash
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "to": "1234567890",
  "type": "text",
  "text": "Hello customer!",
  "preview_url": true
}
```

Response:
```json
{
  "message_id": "wamid.xxxxx",
  "status": "sent",
  "sent_at": "2026-03-06T10:30:00Z"
}
```

### Template Management

**GET /api/v1/templates** - List all templates
```bash
Authorization: Bearer TOKEN
```

**POST /api/v1/templates** - Create template
```bash
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "name": "order_confirmation",
  "category": "UTILITY",
  "language": "en_US",
  "body": "Your order {{1}} has been confirmed for {{2}}",
  "buttons": [
    {
      "type": "url",
      "text": "Track Order",
      "url": "https://example.com/track/{{1}}"
    }
  ]
}
```

**GET /api/v1/templates/{name}** - Get template details
```bash
Authorization: Bearer TOKEN
```

**DELETE /api/v1/templates/{name}** - Delete template
```bash
Authorization: Bearer TOKEN
```

### Phone Number Management

**GET /api/v1/phone-numbers** - List registered numbers
```bash
Authorization: Bearer TOKEN
```

**POST /api/v1/phone-numbers/register** - Register phone number
```bash
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "phone_number": "+1234567890",
  "display_name": "Sales Support",
  "business_name": "Acme Corp",
  "business_category": "GENERAL"
}
```

**GET /api/v1/phone-numbers/{phone_id}/profile** - Get business profile
```bash
Authorization: Bearer TOKEN
```

**PUT /api/v1/phone-numbers/{phone_id}/profile** - Update profile
```bash
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "about": "We're here to help!",
  "business_vertical": "RETAIL",
  "profile_photo_url": "https://...",
  "website": "https://example.com"
}
```

### Media

**POST /api/v1/media/upload** - Upload media to Meta
```bash
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "media_url": "https://...",
  "media_type": "image/jpeg",
  "filename": "product.jpg"
}
```

**GET /api/v1/media/{media_id}** - Get media URL
```bash
Authorization: Bearer TOKEN
```

## Configuration

Environment variables (in `.env`):

```bash
# Core
ENVIRONMENT=production
LOG_LEVEL=INFO
DEBUG=false

# Database
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=priya_global
PG_USER=priya_admin
PG_PASSWORD=***

# JWT
JWT_SECRET_KEY=***
JWT_PUBLIC_KEY=***

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# WhatsApp (per Meta app)
WHATSAPP_APP_SECRET=*** (for webhook signature verification)
WHATSAPP_VERIFY_TOKEN=priya_whatsapp_webhook_token
```

### Per-Tenant Configuration

Each tenant's WhatsApp credentials stored in `channel_connections` table:

```sql
INSERT INTO channel_connections (
  channel,
  tenant_id,
  channel_metadata
) VALUES (
  'whatsapp',
  'tenant-uuid-here',
  jsonb_build_object(
    'phone_number_id', '1234567890123456',
    'business_account_id', '123456789012345',
    'access_token', 'EABs...',
    'display_phone_number', '+1 (234) 567-8900',
    'business_name', 'Acme Sales',
    'quality_rating', 'GREEN',
    'quality_score', 100.0
  )
);
```

## Multi-Tenant Routing

The service is completely multi-tenant:

1. **Single webhook URL** shared by all tenants
2. **Phone number ID → Tenant ID lookup** on every webhook
3. **Tenant isolation** via `tenant_connection()` for all DB queries
4. **RLS policies** ensure data cannot leak between tenants

```python
# Example from webhook processing
async with db.admin_connection() as conn:
    tenant_id = await conn.fetchval(
        "SELECT tenant_id FROM channel_connections "
        "WHERE channel = $1 AND channel_metadata ->> 'phone_number_id' = $2",
        "whatsapp",
        phone_number_id  # From webhook
    )

# All subsequent queries use tenant_connection()
async with db.tenant_connection(tenant_id) as conn:
    # RLS automatically filters to this tenant only
    await conn.fetch("SELECT * FROM whatsapp_messages")
```

## Security

### Webhook Signature Verification

Every incoming webhook is verified with HMAC SHA256:

```python
signature = request.headers.get("X-Hub-Signature-256")
# Format: sha256=HEXDIGEST

expected = "sha256=" + hmac.new(
    app_secret.encode(),
    payload_body,
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(signature, expected):
    raise HTTPException(403, "Invalid signature")
```

### Bearer Auth

All management endpoints require valid JWT:

```bash
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Token must include:
- `tenant_id` - Enforced for all DB queries
- `role` - For RBAC (owner, admin, operator, etc)
- `sub` - User ID

### Media Security

- **Type validation**: Only allowed MIME types
- **Size limit**: 16MB per Meta's limits
- **Temporary storage**: Media cached in DB with TTL
- **PII masking**: No message content in logs

### PII Protection

All logs use `mask_pii()`:
- Email: `j***@e***.com`
- Phone: `+91 ******* 3210`
- Credit card: `****-****-****-1234`

## Deployment

### Local Development

```bash
cd services/whatsapp

# Install deps (shared across services)
pip install -r ../../requirements.txt

# Run
python main.py
# Listens on http://localhost:9010
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 9010
CMD ["python", "services/whatsapp/main.py"]
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: whatsapp-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: whatsapp-service
  template:
    metadata:
      labels:
        app: whatsapp-service
    spec:
      containers:
      - name: whatsapp
        image: priya/whatsapp-service:1.0.0
        ports:
        - containerPort: 9010
        env:
        - name: PG_HOST
          value: postgres.default
        - name: REDIS_HOST
          value: redis.default
        livenessProbe:
          httpGet:
            path: /health
            port: 9010
          initialDelaySeconds: 10
          periodSeconds: 10
```

### Meta Configuration

1. Go to Meta App Dashboard
2. Select WhatsApp App
3. Configure Webhook:
   - **Webhook URL**: `https://api.priyaai.com/whatsapp/webhook`
   - **Verify Token**: `priya_whatsapp_webhook_token`
   - **Subscribe to Fields**: `messages`, `message_status`, `message_template_status_update`

4. Generate Access Token with permissions:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`

## Testing

### Test Webhook Verification

```bash
curl -X GET "http://localhost:9010/webhook?hub.mode=subscribe&hub.verify_token=priya_whatsapp_webhook_token&hub.challenge=12345"
# Returns: 12345
```

### Test Inbound Message

```bash
curl -X POST "http://localhost:9010/webhook" \
  -H "X-Hub-Signature-256: sha256=SIGNATURE" \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "1234567890",
            "id": "wamid.xxx",
            "timestamp": "1234567890",
            "type": "text",
            "text": {"body": "Hello"}
          }],
          "metadata": {
            "phone_number_id": "1234567890123456"
          }
        }
      }]
    }]
  }'
```

### Test Sending

```bash
curl -X POST "http://localhost:9010/api/v1/send" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "1234567890",
    "type": "text",
    "text": "Test message"
  }'
```

## Monitoring

### Metrics to Track

- Message throughput (inbound/outbound per second)
- Webhook latency (P50, P95, P99)
- Message delivery rate
- Template approval/rejection rates
- 24-hour window violations
- Phone number quality changes

### Logs

All logs include:
- Timestamp (ISO 8601)
- Service name (`priya.whatsapp`)
- Level (DEBUG, INFO, WARNING, ERROR)
- Message (PII masked)

Example:
```
2026-03-06T10:30:00.123Z - priya.whatsapp - INFO - Inbound message processed: wamid.xxx from +91 ******* 3210
```

## Troubleshooting

### Webhook Signature Verification Fails

1. Verify `app_secret` matches Meta dashboard
2. Check `X-Hub-Signature-256` header format: `sha256=HEXDIGEST`
3. Ensure body is raw bytes (not parsed JSON)

### Messages Not Sending

1. Check access token validity and permissions
2. Verify phone number has quality rating (not RED)
3. Confirm conversation window (user_initiated or within 24h)
4. Check Message type is supported by recipient

### Template Approval Delays

- Meta review typically 2-24 hours
- Check `status` field in templates table
- Review rejection reason in Meta dashboard

### Media Upload Failures

1. Validate MIME type matches `SUPPORTED_MEDIA_TYPES`
2. Check file size ≤ 16MB
3. Verify access token has media upload permissions

## Code Structure

```
services/whatsapp/
├── main.py                    # FastAPI app + all endpoints
├── __init__.py                # Package init
├── README.md                  # This file
└── requirements.txt           # (in root)

Key components:
- WebhookMessage schema         # Inbound webhook parsing
- OutboundMessage schema        # Normalized outbound
- process_webhook()             # Async webhook handler
- handle_inbound_message()      # Message processing
- send_message() endpoint       # Outbound API
- [Templates/Phone/Media]       # Management endpoints
```

## Future Enhancements

- [ ] Media caching with S3/CloudFront
- [ ] Batch message sending
- [ ] Interactive message builders
- [ ] A/B testing framework
- [ ] Conversation categorization (AI)
- [ ] Sentiment analysis on inbound
- [ ] Multi-language template translation
- [ ] Phone number health monitoring dashboard
- [ ] Advanced rate limiting per tenant
