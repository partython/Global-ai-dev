# WhatsApp Service API Reference

Complete API documentation for the Meta WhatsApp Business API integration service.

**Base URL:** `https://api.priyaai.com` (or `http://localhost:9010` for local development)
**Service Port:** 9010
**API Version:** v1

## Authentication

All endpoints (except `/webhook` and `/health`) require JWT Bearer token authentication:

```bash
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

JWT token must include:
- `sub` - User ID
- `tenant_id` - Tenant UUID
- `role` - User role (owner, admin, operator, viewer)
- `exp` - Expiration timestamp

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error description",
  "status_code": 400
}
```

Common status codes:
- `200` - Success
- `201` - Created
- `400` - Bad request (invalid input)
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (permission denied)
- `404` - Not found
- `429` - Rate limited
- `500` - Internal server error

---

## Webhook Endpoints

### GET /webhook

Meta webhook verification endpoint (no auth required).

Called by Meta during webhook setup to verify ownership of the URL.

**Query Parameters:**
- `hub.mode` (string, required): Must be "subscribe"
- `hub.verify_token` (string, required): Verification token from Meta dashboard
- `hub.challenge` (string, required): Challenge string to echo back

**Response:**
```
HTTP/1.1 200 OK
Content-Type: text/plain

12345
```

**Example:**
```bash
curl -X GET "http://localhost:9010/webhook?hub.mode=subscribe&hub.verify_token=priya_whatsapp_webhook_token&hub.challenge=12345"
# Returns: 12345
```

**Error Responses:**
- `400` - Missing or invalid parameters
- `403` - Invalid verification token

---

### POST /webhook

Receive WhatsApp events from Meta (messages, status updates, etc).

**Headers:**
- `X-Hub-Signature-256` (required): HMAC SHA256 signature for verification
  - Format: `sha256=HEXDIGEST`

**Request Body:**
```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "ENTRY_ID",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "1234567890",
              "phone_number_id": "1234567890123456"
            },
            "messages": [
              {
                "from": "1234567890",
                "id": "wamid.xxx=",
                "timestamp": "1234567890",
                "type": "text",
                "text": {
                  "body": "Hello!"
                }
              }
            ],
            "statuses": [],
            "contacts": [],
            "errors": []
          }
        }
      ]
    }
  ]
}
```

**Response:**
```json
HTTP/1.1 200 OK
{
  "success": true
}
```

**Processing:**
- Asynchronous processing of events
- Events processed in background
- Returns 200 OK immediately to Meta
- Forwards to Channel Router service

**Error Responses:**
- `400` - Invalid JSON
- `403` - Invalid signature

---

## Message Sending

### POST /api/v1/send

Send a message to a customer on WhatsApp.

**Authentication:** Required (Bearer token)

**Request Body:**
```json
{
  "to": "1234567890",
  "type": "text",
  "text": "Hello customer!",
  "preview_url": true
}
```

**Message Types:**

#### Text Message
```json
{
  "to": "1234567890",
  "type": "text",
  "text": "Your message here",
  "preview_url": false
}
```

#### Media Message (Image, Audio, Video, Document)
```json
{
  "to": "1234567890",
  "type": "image",
  "media_url": "https://example.com/photo.jpg",
  "caption": "Product photo"
}
```

**Media Types Supported:**
- `image` - Image media (JPEG, PNG, WebP)
- `audio` - Audio message (AAC, MP4, MPEG, OGG)
- `video` - Video message (H264, MP4, QuickTime)
- `document` - Document (PDF, Word, Excel, PowerPoint, Text)

#### Location Message
```json
{
  "to": "1234567890",
  "type": "location",
  "location": {
    "latitude": 37.7749,
    "longitude": -122.4194,
    "name": "San Francisco Store",
    "address": "123 Market St, San Francisco, CA 94102"
  }
}
```

#### Interactive Message - Buttons
```json
{
  "to": "1234567890",
  "type": "interactive",
  "interactive": {
    "type": "button",
    "body": {
      "text": "Choose an option:"
    },
    "action": {
      "buttons": [
        {
          "type": "reply",
          "reply": {
            "id": "btn_1",
            "title": "Option 1"
          }
        },
        {
          "type": "reply",
          "reply": {
            "id": "btn_2",
            "title": "Option 2"
          }
        }
      ]
    }
  }
}
```

#### Interactive Message - List
```json
{
  "to": "1234567890",
  "type": "interactive",
  "interactive": {
    "type": "list",
    "body": {
      "text": "Select from list:"
    },
    "action": {
      "button": "Choose",
      "sections": [
        {
          "title": "Section 1",
          "rows": [
            {
              "id": "item_1",
              "title": "Item 1",
              "description": "Description 1"
            }
          ]
        }
      ]
    }
  }
}
```

#### Template Message
```json
{
  "to": "1234567890",
  "type": "template",
  "template_name": "order_confirmation",
  "template_params": ["John Doe", "ORDER123", "2"]
}
```

#### Reaction Message
```json
{
  "to": "1234567890",
  "type": "reaction",
  "reaction": {
    "message_id": "wamid.xxx=",
    "emoji": "👍"
  }
}
```

#### Contacts Message
```json
{
  "to": "1234567890",
  "type": "contacts",
  "contacts": [
    {
      "addresses": [
        {
          "street": "123 Main St",
          "city": "San Francisco",
          "state": "CA",
          "zip": "94102",
          "country": "USA",
          "country_code": "1",
          "type": "work"
        }
      ],
      "emails": [
        {
          "email": "support@example.com",
          "type": "work"
        }
      ],
      "name": {
        "first_name": "John",
        "last_name": "Doe"
      },
      "phones": [
        {
          "phone": "+14155552671",
          "type": "work"
        }
      ]
    }
  ]
}
```

**Response:**
```json
{
  "message_id": "wamid.HBEUGVlpQkVBAIAiAhAvAhAvA4Z3NAB-",
  "status": "sent",
  "sent_at": "2026-03-06T10:30:00Z"
}
```

**Status Values:**
- `sent` - Accepted by Meta
- `delivered` - Delivered to device
- `read` - Opened by customer
- `failed` - Delivery failed

**Error Responses:**
- `400` - Invalid phone number or message format
- `401` - Unauthorized
- `404` - WhatsApp not configured for tenant
- `429` - 24-hour window expired (use template message)
- `500` - Meta API error

**Rate Limits:**
- Starter plan: 100 messages/min
- Growth plan: 500 messages/min
- Enterprise plan: 2000 messages/min

---

## Template Management

### GET /api/v1/templates

List all message templates for the tenant.

**Authentication:** Required

**Query Parameters:**
- `status` (optional): Filter by status (PENDING, APPROVED, REJECTED)
- `category` (optional): Filter by category (MARKETING, AUTHENTICATION, UTILITY)

**Response:**
```json
{
  "templates": [
    {
      "id": "uuid-1",
      "name": "welcome",
      "category": "MARKETING",
      "language": "en_US",
      "body": "Welcome {{1}}!",
      "status": "APPROVED",
      "created_at": "2026-03-06T10:00:00Z"
    },
    {
      "id": "uuid-2",
      "name": "order_confirmation",
      "category": "UTILITY",
      "language": "en_US",
      "body": "Order {{1}} confirmed",
      "status": "PENDING",
      "created_at": "2026-03-06T11:00:00Z"
    }
  ],
  "count": 2
}
```

---

### POST /api/v1/templates

Create a new message template (submitted to Meta for approval).

**Authentication:** Required

**Request Body:**
```json
{
  "name": "order_confirmation",
  "category": "UTILITY",
  "language": "en_US",
  "header_type": "TEXT",
  "header_text": "Order Confirmation",
  "body": "Hi {{1}}, your order {{2}} has been confirmed and will arrive in {{3}} days.",
  "footer": "Thank you for shopping with us!",
  "buttons": [
    {
      "type": "url",
      "text": "Track Order",
      "url": "https://example.com/track/{{2}}"
    },
    {
      "type": "phone_number",
      "text": "Call Us",
      "phone_number": "+1234567890"
    }
  ]
}
```

**Template Parameters:**
- `name` (string, required): Template name (1-512 chars)
- `category` (string, required): Category
  - `MARKETING` - Marketing messages
  - `AUTHENTICATION` - Auth codes, verification
  - `UTILITY` - Transactional messages
- `language` (string): ISO language code (default: en_US)
- `header_type` (string): Header format
  - `TEXT` - Text header
  - `IMAGE` - Image header
  - `VIDEO` - Video header
  - `DOCUMENT` - Document header
- `header_text` (string): Header content
- `body` (string, required): Message body with {{1}}, {{2}}, etc for parameters
- `footer` (string): Optional footer text
- `buttons` (array): Optional action buttons

**Response:**
```json
{
  "template_id": "123456789012345",
  "name": "order_confirmation",
  "status": "PENDING",
  "message": "Template submitted for Meta approval (2-24 hours)"
}
```

**Important Notes:**
- Template must be approved by Meta (2-24 hours typical)
- Only APPROVED templates can be sent
- All template variables use {{1}}, {{2}}, etc format
- Category affects delivery and pricing

---

### GET /api/v1/templates/{name}

Get details of a specific template.

**Authentication:** Required

**Parameters:**
- `name` (path, required): Template name

**Response:**
```json
{
  "id": "uuid-1",
  "name": "order_confirmation",
  "template_id": "123456789012345",
  "category": "UTILITY",
  "language": "en_US",
  "body": "Hi {{1}}, your order {{2}} has been confirmed",
  "header_text": "Order Confirmation",
  "footer": "Thank you!",
  "status": "APPROVED",
  "rejection_reason": null,
  "created_at": "2026-03-06T10:00:00Z",
  "updated_at": "2026-03-06T12:00:00Z"
}
```

**Status Values:**
- `PENDING` - Awaiting Meta review
- `APPROVED` - Ready to use
- `REJECTED` - Not approved (see rejection_reason)
- `DISABLED` - Disabled by tenant

---

### DELETE /api/v1/templates/{name}

Delete a template.

**Authentication:** Required

**Parameters:**
- `name` (path, required): Template name

**Response:**
```json
{
  "message": "Template deleted successfully"
}
```

**Error Responses:**
- `404` - Template not found

---

## Phone Number Management

### GET /api/v1/phone-numbers

List all registered phone numbers for the tenant.

**Authentication:** Required

**Response:**
```json
{
  "phone_numbers": [
    {
      "phone_number_id": "1234567890123456",
      "display_phone_number": "+1 (234) 567-8900",
      "business_name": "Acme Sales",
      "quality_rating": "GREEN",
      "created_at": "2026-03-01T10:00:00Z"
    }
  ],
  "count": 1
}
```

**Quality Ratings:**
- `GREEN` - Excellent (low risk)
- `YELLOW` - At risk (may be restricted)
- `RED` - Restricted (cannot send messages)

---

### POST /api/v1/phone-numbers/register

Register a new phone number to the tenant.

**Authentication:** Required

**Request Body:**
```json
{
  "phone_number": "+1234567890",
  "display_name": "Sales Support",
  "business_name": "Acme Corporation",
  "business_category": "GENERAL"
}
```

**Parameters:**
- `phone_number` (string, required): Phone in E.164 format (+CCNNNNNNNNNN)
- `display_name` (string, required): Display name (max 30 chars)
- `business_name` (string, required): Business name (max 100 chars)
- `business_category` (string): Category
  - GENERAL, RETAIL, ECOMMERCE, SERVICES, etc

**Response:**
```json
{
  "status": "registered",
  "phone_number": "+1234567890",
  "message": "Phone number registered. Complete verification in Meta dashboard."
}
```

**Next Steps:**
1. Verify phone number in Meta dashboard (SMS or call)
2. Get Phone Number ID
3. Create access token
4. Update channel_connections with credentials

---

### GET /api/v1/phone-numbers/{phone_id}/profile

Get business profile for a phone number.

**Authentication:** Required

**Parameters:**
- `phone_id` (path, required): Meta Phone Number ID

**Response:**
```json
{
  "phone_number_id": "1234567890123456",
  "display_name": "Sales Support",
  "business_name": "Acme Corp",
  "business_category": "RETAIL",
  "quality_rating": "GREEN",
  "about": "We're here to help!",
  "website": "https://example.com",
  "profile_photo_url": "https://example.com/photo.jpg"
}
```

---

### PUT /api/v1/phone-numbers/{phone_id}/profile

Update business profile.

**Authentication:** Required

**Parameters:**
- `phone_id` (path, required): Meta Phone Number ID

**Request Body:**
```json
{
  "about": "Your message or mission statement (max 139 chars)",
  "business_vertical": "RETAIL",
  "profile_photo_url": "https://example.com/logo.jpg",
  "website": "https://example.com"
}
```

**Parameters:**
- `about` (string): Business description (max 139 chars)
- `business_vertical` (string): Business category
- `profile_photo_url` (string): Logo/profile picture URL
- `website` (string): Business website

**Response:**
```json
{
  "message": "Profile updated successfully"
}
```

**Notes:**
- Profile photo must be image (JPEG, PNG, WebP)
- Max size: 5MB
- Changes propagate immediately to customers

---

## Media Management

### POST /api/v1/media/upload

Upload media to Meta for sending.

**Authentication:** Required

**Request Body:**
```json
{
  "media_url": "https://example.com/image.jpg",
  "media_type": "image/jpeg",
  "filename": "product.jpg"
}
```

**Parameters:**
- `media_url` (string, required): Publicly accessible URL
- `media_type` (string, required): MIME type
  - Images: image/jpeg, image/png, image/webp
  - Audio: audio/aac, audio/mp4, audio/mpeg, audio/ogg
  - Video: video/h264, video/mp4, video/quicktime
  - Documents: application/pdf, etc
- `filename` (string): Original filename (optional)

**Response:**
```json
{
  "media_id": "wamid.xxx=",
  "media_type": "image/jpeg",
  "message": "Media uploaded successfully"
}
```

**Limits:**
- Max size: 16MB
- Supported formats: See MIME types above
- URLs must be publicly accessible
- Media cached for 24 hours by Meta

---

### GET /api/v1/media/{media_id}

Get media details and URL.

**Authentication:** Required

**Parameters:**
- `media_id` (path, required): Media ID from upload or webhook

**Response:**
```json
{
  "media_id": "wamid.xxx=",
  "media_type": "image/jpeg",
  "media_url": "https://platform.meta.com/...",
  "size_bytes": 102400,
  "created_at": "2026-03-06T10:00:00Z"
}
```

**Notes:**
- Meta URLs expire after ~24 hours
- Re-upload if URL expires
- Media URL can be used for downloading media

---

## Health Check

### GET /health

Service health check endpoint (no auth required).

**Response:**
```json
{
  "status": "healthy",
  "service": "whatsapp",
  "port": "9010"
}
```

---

## Rate Limiting

Rate limits are applied per tenant:

| Plan | Messages/min | Webhooks/sec |
|------|-------------|-------------|
| Trial/Starter | 100 | 50 |
| Growth | 500 | 100 |
| Enterprise | 2000 | 500 |

**Headers in Response:**
- `X-RateLimit-Limit` - Total limit
- `X-RateLimit-Remaining` - Requests remaining
- `X-RateLimit-Reset` - Unix timestamp of reset

**Status Code:** `429 Too Many Requests` when exceeded

---

## Webhook Payloads

### Inbound Message Webhook

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "ENTRY_ID",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "1234567890",
              "phone_number_id": "1234567890123456"
            },
            "messages": [
              {
                "from": "1234567890",
                "id": "wamid.HBEUGVlpQkVBAIAiAhAvAhAvA4Z3NAB-",
                "timestamp": "1234567890",
                "type": "text",
                "text": {
                  "body": "Hello, how can I help?"
                }
              }
            ]
          }
        }
      ]
    }
  ]
}
```

### Message Status Webhook

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "ENTRY_ID",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "phone_number_id": "1234567890123456"
            },
            "statuses": [
              {
                "id": "wamid.HBEUGVlpQkVBAIAiAhAvAhAvA4Z3NAB-",
                "status": "delivered",
                "timestamp": "1234567890",
                "recipient_id": "1234567890"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

---

## Best Practices

### Message Sending
1. **Check conversation window** - 24 hours from last customer message
2. **Use templates** - Outside 24h window, only templates allowed
3. **Batch sending** - Group messages to same customer
4. **Error handling** - Retry failed messages with exponential backoff

### Templates
1. **Meaningful variables** - Use {{1}}, {{2}} for dynamic content
2. **Pre-test** - Test before sending to customers
3. **Multi-language** - Create templates for each supported language
4. **Approval time** - Plan ahead for 2-24 hour Meta review

### Media
1. **File size** - Keep under 16MB limit
2. **Quality** - High-quality images/videos for better UX
3. **Accessibility** - Include captions for accessibility
4. **Format** - Use recommended formats (JPEG, H.264 video)

### Compliance
1. **Opt-in** - Only message users who opted in
2. **Unsubscribe** - Honor "STOP" keyword
3. **Quality rating** - Monitor and maintain GREEN status
4. **Compliance** - Follow WhatsApp Business Messaging Policy

---

## Support & Debugging

### Common Errors

**"24-hour window expired"**
- Solution: Send a template message to re-initiate conversation

**"Invalid phone number"**
- Check format: Must be E.164 (+CCNNNNNNNNNN)
- Must be registered in Meta dashboard

**"Template not approved"**
- Wait for Meta review (2-24 hours)
- Check rejection reason in template details
- Fix issues and resubmit

**"Invalid signature"**
- Verify WHATSAPP_APP_SECRET matches Meta dashboard
- Check header format: `sha256=HEXDIGEST`

### Debugging

Enable debug logging:
```bash
LOG_LEVEL=DEBUG python services/whatsapp/main.py
```

Check logs for:
- Webhook signature verification
- Message status transitions
- Template approvals
- API errors

### Support Contacts

- API Issues: api-support@priyaai.com
- Urgent: platform@priyaai.com
- Meta Issues: https://developers.facebook.com/support/

---

Last updated: 2026-03-06
API Version: 1.0
