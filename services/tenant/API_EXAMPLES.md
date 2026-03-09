# Tenant Service API Examples

All examples use `curl`. Replace `TOKEN` with actual JWT token and `TENANT_ID` with actual tenant ID.

## Variables

```bash
# Base URL (local development)
BASE_URL="http://localhost:9002"

# Auth token from Auth Service
TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

# Tenant ID (UUID)
TENANT_ID="550e8400-e29b-41d4-a716-446655440000"
```

---

## Health Check

```bash
curl -X GET \
  "${BASE_URL}/health"
```

**Response:**
```json
{
  "status": "healthy",
  "service": "tenant",
  "port": 9002,
  "database": "connected",
  "timestamp": "2025-03-06T10:00:00Z"
}
```

---

## Tenant Management

### Get Tenant Details

```bash
curl -X GET \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "business_name": "Acme Corp",
  "slug": "acme-corp",
  "plan": "growth",
  "status": "active",
  "owner_id": "user-uuid",
  "owner_email": "owner@acme.com",
  "created_at": "2025-03-06T10:00:00Z",
  "settings": {
    "business_name": "Acme Corp",
    "industry": "E-commerce",
    "country": "US",
    "timezone": "America/New_York",
    "language": "en"
  },
  "branding": {
    "logo_url": "https://cdn.example.com/logo.png",
    "primary_color": "#007bff"
  },
  "ai_config": {
    "tone": "friendly",
    "greeting": "Hi! How can I help?",
    "language": "en"
  },
  "team_count": 5
}
```

### Update Tenant Settings

```bash
curl -X PUT \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "Acme Corporation",
    "industry": "E-commerce & SaaS",
    "country": "US",
    "timezone": "America/Los_Angeles",
    "language": "en"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "business_name": "Acme Corporation",
  "slug": "acme-corp",
  "plan": "growth",
  "status": "active",
  ...
}
```

### Update Branding

```bash
curl -X PUT \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/branding" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "logo_url": "https://cdn.acme.com/logo-new.png",
    "favicon_url": "https://cdn.acme.com/favicon.ico",
    "primary_color": "#FF6B6B",
    "secondary_color": "#4ECDC4",
    "accent_color": "#FFE66D"
  }'
```

**Response:**
```json
{
  "status": "success",
  "branding": {
    "logo_url": "https://cdn.acme.com/logo-new.png",
    "favicon_url": "https://cdn.acme.com/favicon.ico",
    "primary_color": "#FF6B6B",
    "secondary_color": "#4ECDC4",
    "accent_color": "#FFE66D"
  }
}
```

### Configure AI Personality

```bash
curl -X PUT \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/ai-config" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tone": "professional",
    "greeting": "Welcome to Acme support! How may I assist you?",
    "system_prompt": "You are a professional customer support representative for Acme Corp. Be helpful, courteous, and efficient.",
    "language": "en"
  }'
```

**Valid tones:** `friendly`, `professional`, `casual`

**Response:**
```json
{
  "status": "success",
  "ai_config": {
    "tone": "professional",
    "greeting": "Welcome to Acme support! How may I assist you?",
    "system_prompt": "You are a professional customer support...",
    "language": "en"
  }
}
```

### Get Usage Statistics

```bash
curl -X GET \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/usage" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Response:**
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversations_used": 2450,
  "conversations_limit": 5000,
  "storage_used_mb": 512.5,
  "storage_limit_mb": 10000,
  "team_members_used": 5,
  "team_members_limit": 10,
  "channels_enabled": ["whatsapp", "email", "web_chat"],
  "plan": "growth"
}
```

### Delete Tenant (Soft Delete)

```bash
curl -X DELETE \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Note:** Owner only. This is a soft delete (status = 'deleted').

---

## Team Management

### List Team Members

```bash
curl -X GET \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/members" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Response:**
```json
[
  {
    "id": "member-uuid-1",
    "email": "john@acme.com",
    "role": "admin",
    "joined_at": "2025-02-15T14:30:00Z",
    "invited_by": "owner-uuid",
    "status": "active"
  },
  {
    "id": "member-uuid-2",
    "email": "jane@acme.com",
    "role": "member",
    "joined_at": "2025-03-01T09:15:00Z",
    "invited_by": "owner-uuid",
    "status": "active"
  },
  {
    "id": "member-uuid-3",
    "email": "bob@acme.com",
    "role": "member",
    "joined_at": null,
    "invited_by": "owner-uuid",
    "status": "invited"
  }
]
```

### Invite Team Member

```bash
curl -X POST \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/members/invite" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newmember@acme.com",
    "role": "member"
  }'
```

**Valid roles:** `admin`, `member`

**Response:**
```json
{
  "status": "success",
  "message": "Invitation sent to newmember@acme.com",
  "invitation_id": "inv-uuid"
}
```

### Update Member Role

```bash
curl -X PUT \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/members/member-uuid/role" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "admin"
  }'
```

**Response:**
```json
{
  "status": "success",
  "new_role": "admin"
}
```

### Remove Team Member

```bash
curl -X DELETE \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/members/member-uuid" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Response:**
```json
{
  "status": "success",
  "message": "Member removed from team"
}
```

### Transfer Ownership

```bash
curl -X POST \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/members/transfer-ownership" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "new_owner_email": "jane@acme.com"
  }'
```

**Note:** Current owner only. New owner must be active team member.

**Response:**
```json
{
  "status": "success",
  "message": "Ownership transferred to jane@acme.com"
}
```

---

## AI Onboarding

### Start Onboarding

```bash
curl -X POST \
  "${BASE_URL}/api/v1/onboarding/start" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "Acme Corp",
    "email": "owner@acme.com"
  }'
```

**Response:**
```json
{
  "tenant_id": "new-tenant-uuid",
  "step": 1,
  "step_name": "Welcome",
  "ai_message": "Welcome to Priya! I'm excited to help you set up your AI assistant. To get started, what's the name of your business?",
  "expected_fields": ["business_name"]
}
```

### Process Onboarding Step

```bash
curl -X POST \
  "${BASE_URL}/api/v1/onboarding/step" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "new-tenant-uuid",
    "step": 1,
    "response": "Acme Corporation - we provide e-commerce solutions"
  }'
```

**Response (Step 1→2):**
```json
{
  "tenant_id": "new-tenant-uuid",
  "step": 2,
  "step_name": "Industry",
  "ai_message": "Great! What industry does your business operate in? (e.g., e-commerce, healthcare, finance, retail)",
  "expected_fields": ["industry"],
  "previous_response": "Acme Corporation - we provide e-commerce solutions"
}
```

**Full Onboarding Flow:**

```bash
# Step 1: Welcome
curl -X POST "${BASE_URL}/api/v1/onboarding/step" \
  -d '{"tenant_id":"'$TENANT_ID'","step":1,"response":"Acme Corp"}'

# Step 2: Industry
curl -X POST "${BASE_URL}/api/v1/onboarding/step" \
  -d '{"tenant_id":"'$TENANT_ID'","step":2,"response":"E-commerce"}'

# Step 3: Channels
curl -X POST "${BASE_URL}/api/v1/onboarding/step" \
  -d '{"tenant_id":"'$TENANT_ID'","step":3,"response":"WhatsApp, Email, Web Chat"}'

# Step 4: E-commerce
curl -X POST "${BASE_URL}/api/v1/onboarding/step" \
  -d '{"tenant_id":"'$TENANT_ID'","step":4,"response":"Shopify"}'

# Step 5: AI Personality
curl -X POST "${BASE_URL}/api/v1/onboarding/step" \
  -d '{"tenant_id":"'$TENANT_ID'","step":5,"response":"Friendly tone, greeting is: Hi there! How can we help?"}'

# Step 6: Test
curl -X POST "${BASE_URL}/api/v1/onboarding/step" \
  -d '{"tenant_id":"'$TENANT_ID'","step":6,"response":"What are your business hours?"}'
```

### Get Onboarding Status

```bash
curl -X GET \
  "${BASE_URL}/api/v1/onboarding/status/${TENANT_ID}"
```

**Response:**
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "current_step": 3,
  "completed": false,
  "started_at": "2025-03-06T10:00:00Z",
  "completed_at": null,
  "data": {
    "business_name": "Acme Corp",
    "email": "owner@acme.com",
    "industry": "E-commerce",
    "channels": ["whatsapp", "email"]
  }
}
```

### Complete Onboarding

```bash
curl -X POST \
  "${BASE_URL}/api/v1/onboarding/complete" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "'${TENANT_ID}'"
  }'
```

**Response:**
```json
{
  "status": "success",
  "message": "Workspace is now active!",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Feature Flags

### Get Feature Flags

```bash
curl -X GET \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/features" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Response:**
```json
{
  "plan": "growth",
  "features": {
    "whatsapp": true,
    "email": true,
    "web_chat": true,
    "voice": true,
    "social": true,
    "sms": true,
    "ai_personality": true,
    "custom_branding": true,
    "api_access": false
  }
}
```

### Update Feature Flags

```bash
curl -X PUT \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/features" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "features": {
      "whatsapp": true,
      "email": true,
      "web_chat": false,
      "voice": true,
      "social": true,
      "sms": false
    }
  }'
```

---

## Plan Management

### Get Plan Details

```bash
curl -X GET \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/plan" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Response:**
```json
{
  "plan": "growth",
  "limits": {
    "max_team_members": 10,
    "max_channels": 999,
    "max_conversations_per_month": 5000,
    "storage_limit_mb": 10000,
    "features": {
      "whatsapp": true,
      "email": true,
      ...
    }
  }
}
```

### Upgrade Plan

```bash
curl -X PUT \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/plan" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "plan": "enterprise"
  }'
```

**Valid plans:** `starter`, `growth`, `enterprise`

**Response:**
```json
{
  "status": "success",
  "plan": "enterprise",
  "limits": {
    "max_team_members": 999999,
    "max_channels": 999999,
    "max_conversations_per_month": 999999,
    "storage_limit_mb": 999999,
    "features": {...}
  },
  "message": "Plan upgraded to enterprise"
}
```

---

## Error Examples

### Missing Token

```bash
curl -X GET "${BASE_URL}/api/v1/tenants/${TENANT_ID}"
```

**Response (401):**
```json
{
  "detail": "Authentication required"
}
```

### Insufficient Permissions

```bash
# As member trying to delete tenant (owner only)
curl -X DELETE \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}" \
  -H "Authorization: Bearer ${MEMBER_TOKEN}"
```

**Response (403):**
```json
{
  "detail": "Permission denied: role owner required"
}
```

### Team Member Limit Exceeded

```bash
curl -X POST \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/members/invite" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"email":"user@example.com","role":"member"}'
```

**Response (400) - Starter plan limit (2 members):**
```json
{
  "detail": "Team member limit (2) reached for starter plan"
}
```

### Invalid Email

```bash
curl -X POST \
  "${BASE_URL}/api/v1/tenants/${TENANT_ID}/members/invite" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"email":"not-an-email","role":"member"}'
```

**Response (422):**
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "invalid email format",
      "type": "value_error.email"
    }
  ]
}
```

---

## Bash Script Template

```bash
#!/bin/bash

# Tenant Service API Test Script

BASE_URL="http://localhost:9002"
TOKEN="your-jwt-token-here"
TENANT_ID="your-tenant-id-here"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test function
test_endpoint() {
  local method=$1
  local endpoint=$2
  local data=$3

  echo -e "${GREEN}Testing: ${method} ${endpoint}${NC}"

  if [ -z "$data" ]; then
    curl -X "${method}" \
      "${BASE_URL}${endpoint}" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json"
  else
    curl -X "${method}" \
      "${BASE_URL}${endpoint}" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Content-Type: application/json" \
      -d "${data}"
  fi

  echo -e "\n---\n"
}

# Run tests
test_endpoint GET "/health"
test_endpoint GET "/api/v1/tenants/${TENANT_ID}"
test_endpoint GET "/api/v1/tenants/${TENANT_ID}/members"
test_endpoint GET "/api/v1/tenants/${TENANT_ID}/usage"
```

---

## Postman Collection

Import this into Postman:

```json
{
  "info": {
    "name": "Tenant Service API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/health"
      }
    },
    {
      "name": "Get Tenant",
      "request": {
        "method": "GET",
        "header": [
          {
            "key": "Authorization",
            "value": "Bearer {{token}}"
          }
        ],
        "url": "{{base_url}}/api/v1/tenants/{{tenant_id}}"
      }
    }
  ],
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:9002"
    },
    {
      "key": "token",
      "value": "your_jwt_token_here"
    },
    {
      "key": "tenant_id",
      "value": "your_tenant_id_here"
    }
  ]
}
```
