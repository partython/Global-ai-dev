# Tenant Service

**Port:** 9002
**Framework:** FastAPI + AsyncPG
**Database:** PostgreSQL with Row Level Security (RLS)

## Overview

The Tenant Service manages all aspects of workspace and team management for the Priya Global platform:

1. **Workspace/Tenant Management** - Create, configure, and delete workspaces
2. **Team Member Management** - Invite, role assignment, and access control
3. **AI Onboarding Flow** - Conversational AI-driven setup experience
4. **Feature Flags** - Plan-based feature access control
5. **Usage Tracking** - Monitor conversations, storage, and team members
6. **Plan Management** - Upgrade/downgrade subscription plans

## Critical Security Architecture

### Tenant Isolation (RLS)

Every endpoint uses `db.tenant_connection(tenant_id)` which enforces Row Level Security:

```python
async with db.tenant_connection(tenant_id) as conn:
    rows = await conn.fetch("SELECT * FROM customers")
    # ^ Returns ONLY this tenant's customers. RLS enforces at DB level.
```

**SECURITY GUARANTEE:** Even if application code has a bug, data cannot leak between tenants. PSI AI (Tenant #1) knowledge is completely isolated from all other workspaces.

### Role-Based Access Control (RBAC)

Three roles with enforced permissions:

- **owner** - Full control, can transfer ownership, delete workspace
- **admin** - Manage team, update settings, configure AI
- **member** - View-only, limited to their own data

```python
auth.require_role("owner", "admin")  # Only owner/admin can call this
```

## API Endpoints

### Health Check

```http
GET /health
```

Returns service status.

---

### Tenant/Workspace Management

#### Get Tenant Details
```http
GET /api/v1/tenants/:id
Authorization: Bearer <token>
```

**Response:**
```json
{
  "id": "uuid",
  "business_name": "Acme Corp",
  "slug": "acme-corp",
  "plan": "growth",
  "status": "active",
  "owner_id": "user-uuid",
  "owner_email": "owner@acme.com",
  "created_at": "2025-03-06T10:00:00Z",
  "settings": {...},
  "branding": {...},
  "ai_config": {...},
  "team_count": 5
}
```

#### Update Tenant Settings
```http
PUT /api/v1/tenants/:id
Authorization: Bearer <token>
Content-Type: application/json

{
  "business_name": "Acme Corp Updated",
  "industry": "E-commerce",
  "country": "US",
  "timezone": "America/New_York",
  "language": "en"
}
```

#### Update Branding
```http
PUT /api/v1/tenants/:id/branding
Authorization: Bearer <token>
Content-Type: application/json

{
  "logo_url": "https://cdn.example.com/logo.png",
  "favicon_url": "https://cdn.example.com/favicon.ico",
  "primary_color": "#007bff",
  "secondary_color": "#6c757d",
  "accent_color": "#28a745"
}
```

#### Configure AI Personality
```http
PUT /api/v1/tenants/:id/ai-config
Authorization: Bearer <token>
Content-Type: application/json

{
  "tone": "friendly",
  "greeting": "Hi! How can I help you today?",
  "system_prompt": "You are a helpful customer service representative...",
  "language": "en"
}
```

**Valid tones:** `friendly`, `professional`, `casual`

#### Get Usage Statistics
```http
GET /api/v1/tenants/:id/usage
Authorization: Bearer <token>
```

**Response:**
```json
{
  "tenant_id": "uuid",
  "conversations_used": 450,
  "conversations_limit": 5000,
  "storage_used_mb": 256.5,
  "storage_limit_mb": 10000,
  "team_members_used": 5,
  "team_members_limit": 10,
  "channels_enabled": ["whatsapp", "email", "web_chat"],
  "plan": "growth"
}
```

#### Delete Tenant
```http
DELETE /api/v1/tenants/:id
Authorization: Bearer <token>
```

**SECURITY:** Owner only. Soft-deletes the workspace (not permanent).

---

### Team Management

#### List Team Members
```http
GET /api/v1/tenants/:id/members
Authorization: Bearer <token>
```

**Response:**
```json
[
  {
    "id": "member-uuid",
    "email": "john@acme.com",
    "role": "admin",
    "joined_at": "2025-02-15T14:30:00Z",
    "invited_by": "owner-uuid",
    "status": "active"
  },
  ...
]
```

#### Invite Team Member
```http
POST /api/v1/tenants/:id/members/invite
Authorization: Bearer <token>
Content-Type: application/json

{
  "email": "jane@acme.com",
  "role": "member"
}
```

**SECURITY:** Enforces `max_team_members` limit per plan.

**Valid roles:** `admin`, `member` (owner cannot be assigned)

#### Update Member Role
```http
PUT /api/v1/tenants/:id/members/:user_id/role
Authorization: Bearer <token>
Content-Type: application/json

{
  "role": "admin"
}
```

#### Remove Team Member
```http
DELETE /api/v1/tenants/:id/members/:user_id
Authorization: Bearer <token>
```

**SECURITY:** Cannot remove owner. Cannot be a member.

#### Transfer Ownership
```http
POST /api/v1/tenants/:id/members/transfer-ownership
Authorization: Bearer <token>
Content-Type: application/json

{
  "new_owner_email": "jane@acme.com"
}
```

**SECURITY:** Current owner only. New owner must be an active team member.

---

### AI Onboarding Flow

The onboarding is **fully conversational**. Each step is AI-driven with natural language interaction.

#### 1. Start Onboarding
```http
POST /api/v1/onboarding/start
Content-Type: application/json

{
  "business_name": "Acme Corp",
  "email": "owner@acme.com"
}
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

#### 2. Process Onboarding Step
```http
POST /api/v1/onboarding/step
Content-Type: application/json

{
  "tenant_id": "tenant-uuid",
  "step": 1,
  "response": "Acme Corp - we're in e-commerce"
}
```

**Response (Step 1→2):**
```json
{
  "tenant_id": "tenant-uuid",
  "step": 2,
  "step_name": "Industry",
  "ai_message": "Great! What industry does your business operate in? (e.g., e-commerce, healthcare, finance, retail)",
  "expected_fields": ["industry"],
  "previous_response": "Acme Corp - we're in e-commerce"
}
```

**Onboarding Steps:**

| Step | Name | AI Question | Captures |
|------|------|-------------|----------|
| 1 | Welcome | "What's the name of your business?" | business_name |
| 2 | Industry | "What industry are you in?" | industry |
| 3 | Channels | "Which channels do you want?" | channels |
| 4 | E-commerce | "Do you have a Shopify/WooCommerce store?" | ecommerce_platform |
| 5 | AI Personality | "What tone should your AI use?" | ai_tone, greeting |
| 6 | Test Conversation | "Let's test it! Send a message." | test_response |

After step 6, the user is prompted to go live.

#### 3. Get Onboarding Status
```http
GET /api/v1/onboarding/status/:tenant_id
```

**Response:**
```json
{
  "tenant_id": "tenant-uuid",
  "current_step": 3,
  "completed": false,
  "started_at": "2025-03-06T10:00:00Z",
  "completed_at": null,
  "data": {
    "business_name": "Acme Corp",
    "email": "owner@acme.com",
    "industry": "E-commerce"
  }
}
```

#### 4. Complete Onboarding
```http
POST /api/v1/onboarding/complete
Authorization: Bearer <token>
Content-Type: application/json

{
  "tenant_id": "tenant-uuid"
}
```

Transitions tenant from `onboarding` → `active` status.

---

### Feature Flags

#### Get Feature Flags
```http
GET /api/v1/tenants/:id/features
Authorization: Bearer <token>
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

#### Update Feature Flags
```http
PUT /api/v1/tenants/:id/features
Authorization: Bearer <token>
Content-Type: application/json

{
  "features": {
    "whatsapp": true,
    "email": true,
    "web_chat": false
  }
}
```

**SECURITY:** Cannot enable features beyond plan limits.

---

### Plan Management

#### Get Plan Details
```http
GET /api/v1/tenants/:id/plan
Authorization: Bearer <token>
```

**Response:**
```json
{
  "plan": "starter",
  "limits": {
    "max_team_members": 2,
    "max_channels": 3,
    "max_conversations_per_month": 1000,
    "storage_limit_mb": 1000,
    "features": {...}
  }
}
```

#### Upgrade/Downgrade Plan
```http
PUT /api/v1/tenants/:id/plan
Authorization: Bearer <token>
Content-Type: application/json

{
  "plan": "growth"
}
```

**Valid plans:** `starter`, `growth`, `enterprise`

**Plan Limits:**

| | Starter | Growth | Enterprise |
|---|---------|--------|-----------|
| Max Team Members | 2 | 10 | Unlimited |
| Max Channels | 3 | All | All |
| Conversations/mo | 1K | 5K | Unlimited |
| Storage | 1GB | 10GB | Unlimited |
| Custom Branding | ✗ | ✓ | ✓ |
| API Access | ✗ | ✗ | ✓ |

---

## Error Responses

All endpoints follow standard HTTP status codes:

```json
{
  "detail": "Permission denied: role owner required"
}
```

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad request (validation error) |
| 401 | Unauthorized (invalid/missing token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not found |
| 409 | Conflict (e.g., user already invited) |
| 500 | Internal server error |

---

## Environment Variables

```bash
# Database
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=priya_global
PG_USER=priya_admin
PG_PASSWORD=...

# JWT Authentication
JWT_SECRET_KEY=...
JWT_PUBLIC_KEY=...
JWT_ISSUER=priya-global

# Service Configuration
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
```

---

## Running the Service

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py

# Run with Uvicorn
uvicorn main:app --host 0.0.0.0 --port 9002 --log-level info

# Run in Docker
docker build -t priya-tenant-service .
docker run -p 9002:9002 --env-file .env priya-tenant-service
```

---

## Database Schema Requirements

The service expects these tables with RLS policies:

```sql
-- Core tenant table
CREATE TABLE tenants (
  id UUID PRIMARY KEY,
  business_name VARCHAR(255) NOT NULL,
  slug VARCHAR(64) UNIQUE NOT NULL,
  plan VARCHAR(50) DEFAULT 'starter',
  status VARCHAR(50) DEFAULT 'onboarding', -- onboarding, active, suspended, deleted
  owner_id UUID NOT NULL,
  owner_email VARCHAR(255) NOT NULL,
  settings JSONB DEFAULT '{}',
  branding JSONB DEFAULT '{}',
  ai_config JSONB DEFAULT '{}',
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP,
  deleted_at TIMESTAMP,
  tenant_id UUID DEFAULT gen_random_uuid()
);

-- Team members table
CREATE TABLE team_members (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  email VARCHAR(255) NOT NULL,
  role VARCHAR(50) NOT NULL, -- owner, admin, member
  status VARCHAR(50) DEFAULT 'active', -- active, invited, removed
  invited_by UUID,
  invited_at TIMESTAMP,
  joined_at TIMESTAMP,
  removed_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP
);

-- Row Level Security policies enforce tenant isolation
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenants_tenant_isolation ON tenants
  USING (id::text = current_setting('app.current_tenant_id'));

CREATE POLICY team_members_tenant_isolation ON team_members
  USING (tenant_id::text = current_setting('app.current_tenant_id'));
```

---

## Logging & Monitoring

All operations are logged with audit trails:

```
INFO: Tenant acme-corp settings updated by user john-doe
WARNING: Ownership transferred: tenant=acme-corp, from=john-doe, to=jane-smith
ERROR: Plan change failed for tenant acme-corp: Billing service unavailable
```

Sensitive data (emails, user IDs) is masked in logs.

---

## Integration with Other Services

- **Auth Service (9001)** - Validates JWT tokens, provisions users
- **Billing Service (9027)** - Processes plan upgrades, enforces usage limits
- **Notification Service (9024)** - Sends team invitation emails
- **AI Engine (9020)** - Provides conversational responses during onboarding
- **Gateway (9000)** - Routes requests, handles rate limiting

---

## Security Checklist

- [x] Tenant isolation via RLS at database level
- [x] RBAC enforcement on all endpoints
- [x] PII masking in logs
- [x] Input sanitization (SQL injection, XSS prevention)
- [x] Plan limits enforced (team members, channels, storage)
- [x] Ownership transfer requires current owner
- [x] Team member removal prevents removing owner
- [x] Feature flags locked to plan tier
- [x] Onboarding state persisted securely in JSONB
- [x] Admin connection used only for system operations

---

## License

Proprietary - Priya Global Platform
