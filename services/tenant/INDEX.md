# Tenant Service - File Index & Navigation

## Quick Access

| File | Purpose | Size | Status |
|------|---------|------|--------|
| **main.py** | Complete FastAPI service | 1.5 KB | ✅ Ready |
| **README.md** | Full documentation | 580 lines | ✅ Ready |
| **QUICKSTART.md** | 5-minute setup guide | 394 lines | ✅ Ready |
| **API_EXAMPLES.md** | All API examples & curl commands | 729 lines | ✅ Ready |
| **IMPLEMENTATION_SUMMARY.md** | Implementation overview | 467 lines | ✅ Ready |
| **CHECKLIST.md** | Requirements verification | - | ✅ Ready |
| **test_tenant_service.py** | Unit tests | 475 lines | ✅ Ready |
| **requirements.txt** | Python dependencies | - | ✅ Ready |
| **Dockerfile** | Production Docker image | - | ✅ Ready |
| **docker-compose.dev.yml** | Development environment | - | ✅ Ready |
| **.env.example** | Environment template | - | ✅ Ready |
| **__init__.py** | Package initialization | - | ✅ Ready |

---

## Getting Started

### 1. First Time Setup (Choose One)

**Option A: Docker Compose (Recommended)**
```bash
cd /mnt/Ai/priya-global/services/tenant
docker-compose -f docker-compose.dev.yml up -d
# Service at http://localhost:9002
```
→ See: **QUICKSTART.md** → "Option 1: Docker Compose"

**Option B: Local Python**
```bash
cd /mnt/Ai/priya-global/services/tenant
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --port 9002 --reload
```
→ See: **QUICKSTART.md** → "Option 2: Local Python"

### 2. Verify It's Working

```bash
curl http://localhost:9002/health
# Should return: {"status": "healthy", ...}
```

### 3. View API Documentation

Open browser: **http://localhost:9002/docs**
(Interactive Swagger UI with all endpoints)

---

## Documentation by Use Case

### "I want to understand what this service does"
→ **README.md** - Complete overview of all features

### "I want to deploy to production"
→ **IMPLEMENTATION_SUMMARY.md** → "Production Checklist"
→ **QUICKSTART.md** → "Production Deployment"

### "I want to call the API"
→ **API_EXAMPLES.md** - All endpoints with curl examples
→ **README.md** → "Error Responses" section

### "I want to run tests"
→ **test_tenant_service.py** - 40+ test cases
```bash
pip install pytest pytest-asyncio
pytest test_tenant_service.py -v
```

### "I want to test the onboarding flow"
→ **QUICKSTART.md** → "Test Onboarding Flow"
→ **API_EXAMPLES.md** → "AI Onboarding" section

### "I want to understand the architecture"
→ **IMPLEMENTATION_SUMMARY.md** → "Architecture Highlights"
→ **README.md** → "Critical Security Architecture"

### "I want to troubleshoot an issue"
→ **QUICKSTART.md** → "Common Issues"
→ **QUICKSTART.md** → "Troubleshooting Onboarding"

### "I want to verify all requirements are met"
→ **CHECKLIST.md** - Complete requirement verification

---

## File Structure

```
/mnt/Ai/priya-global/services/tenant/
├── main.py                      # FastAPI application
├── __init__.py                  # Package init
├── requirements.txt             # Dependencies
├── Dockerfile                   # Production image
├── docker-compose.dev.yml       # Dev environment
├── .env.example                 # Config template
├── test_tenant_service.py       # Tests
├── README.md                    # Full documentation
├── QUICKSTART.md                # Quick start guide
├── API_EXAMPLES.md              # API examples
├── IMPLEMENTATION_SUMMARY.md    # Overview
├── CHECKLIST.md                 # Requirements
└── INDEX.md                     # This file
```

---

## 20 API Endpoints

### Health & Status (1)
- `GET /health` - Service status

### Tenant Management (6)
- `GET /api/v1/tenants/:id`
- `PUT /api/v1/tenants/:id`
- `PUT /api/v1/tenants/:id/branding`
- `PUT /api/v1/tenants/:id/ai-config`
- `GET /api/v1/tenants/:id/usage`
- `DELETE /api/v1/tenants/:id`

### Team Management (5)
- `GET /api/v1/tenants/:id/members`
- `POST /api/v1/tenants/:id/members/invite`
- `PUT /api/v1/tenants/:id/members/:user_id/role`
- `DELETE /api/v1/tenants/:id/members/:user_id`
- `POST /api/v1/tenants/:id/members/transfer-ownership`

### Onboarding (4)
- `POST /api/v1/onboarding/start`
- `POST /api/v1/onboarding/step`
- `GET /api/v1/onboarding/status/:tenant_id`
- `POST /api/v1/onboarding/complete`

### Features & Plans (4)
- `GET /api/v1/tenants/:id/features`
- `PUT /api/v1/tenants/:id/features`
- `GET /api/v1/tenants/:id/plan`
- `PUT /api/v1/tenants/:id/plan`

---

## Key Features

✅ **Tenant Isolation** - Row Level Security prevents data leakage
✅ **RBAC** - Owner/Admin/Member roles with permission enforcement
✅ **Onboarding** - Fully conversational, AI-driven setup flow
✅ **Team Management** - Invite, role assignment, ownership transfer
✅ **Plan Limits** - Enforce team size, channels, conversations, storage
✅ **Feature Flags** - Control feature access by plan tier
✅ **Production Ready** - Comprehensive error handling, logging, tests

---

## Technology Stack

- **Framework:** FastAPI + Uvicorn
- **Database:** PostgreSQL with Row Level Security
- **Async:** asyncio + asyncpg
- **Auth:** JWT (RS256)
- **Validation:** Pydantic
- **Testing:** pytest + pytest-asyncio
- **Deployment:** Docker + Docker Compose

---

## Important Notes

### Security
- All protected endpoints require JWT token in Authorization header
- Tenant isolation enforced at PostgreSQL RLS level
- PII is masked in all logs
- Input sanitization on all user-provided text

### Database
- Requires PostgreSQL 14+
- Row Level Security policies must be enabled
- Connection pooling configured for performance
- Tables: tenants, team_members

### Ports
- Tenant Service: **9002** (this service)
- Gateway: 9000 (routes to this service)
- Auth Service: 9001 (provides JWT tokens)
- Billing Service: 9027 (handles plan upgrades)
- AI Engine: 9020 (provides conversational responses)

### Environment
- Configuration via .env file
- See .env.example for all variables
- Production requires real JWT keys, not dev keys

---

## Common Commands

```bash
# Start development server
uvicorn main:app --port 9002 --reload

# Run tests
pytest test_tenant_service.py -v

# Docker development
docker-compose -f docker-compose.dev.yml up -d

# Database
psql -U priya_admin -d priya_global

# API docs
http://localhost:9002/docs

# Health check
curl http://localhost:9002/health

# Start onboarding
curl -X POST http://localhost:9002/api/v1/onboarding/start \
  -d '{"business_name":"Test","email":"test@example.com"}'
```

---

## Support & Integration

### Dependencies On
- **Shared Library** - Config, database, security, auth middleware
- **PostgreSQL** - For tenant data storage
- **Redis** - For caching/sessions (future)

### Used By
- **Gateway** (9000) - Routes API requests
- **Frontend** (port 3000) - Web UI for workspace management
- **Mobile Apps** - Native mobile clients

### Integrates With
- **Auth Service** (9001) - JWT token validation
- **Billing Service** (9027) - Plan management, usage limits
- **Notification Service** (9024) - Team invitations
- **AI Engine** (9020) - Conversational responses

---

## Version History

| Version | Date | Status |
|---------|------|--------|
| 1.0.0 | 2025-03-06 | Production Ready |

---

## License

Proprietary - Priya Global Platform

---

**Last Updated:** 2025-03-06
**Maintained By:** Priya Team
**Status:** Active Development
