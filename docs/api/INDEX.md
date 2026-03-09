# Priya Global Platform - Complete API Documentation Index

## Overview

This directory contains the complete unified API documentation for the Priya Global Platform - a multi-tenant AI-powered sales platform with 36 microservices integrated behind a single API gateway on port 9000.

**Documentation Generated**: March 6, 2024
**API Version**: 1.0.0
**OpenAPI Version**: 3.1.0

## Directory Structure

```
docs/api/
├── INDEX.md                    # This file
├── README.md                   # Main documentation overview
├── INTEGRATION_GUIDE.md         # Step-by-step integration guide
├── QUICK_REFERENCE.md          # Quick command reference
├── openapi.yaml                # OpenAPI 3.1 specification
├── swagger-ui.html             # Interactive Swagger UI
└── openapi.json                # Generated from openapi.yaml

services/gateway/
└── docs_router.py              # FastAPI documentation router
```

## Quick Navigation

### For Getting Started
1. Start here: **[README.md](README.md)** - Overview and quick start
2. Then read: **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - Detailed integration steps
3. Keep handy: **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - API command reference

### For Interactive Documentation
- **[Swagger UI](swagger-ui.html)** - Try-it-out, test endpoints
- **[OpenAPI Spec](openapi.yaml)** - Machine-readable specification

### For Implementation
- **[docs_router.py](../../services/gateway/docs_router.py)** - Backend integration code

## File Descriptions

### 1. README.md (13 KB, 425 lines)
**Purpose**: Main documentation entry point

**Contents**:
- Complete platform overview
- Service list (36 microservices)
- Architecture diagram
- Authentication explanation
- Rate limiting details
- Multi-tenancy support
- Webhook configuration
- Regional support (USD, INR, GBP, AUD)
- Python and JavaScript examples
- Support resources

**Best For**: Understanding the platform, planning integration

---

### 2. INTEGRATION_GUIDE.md (17 KB, 758 lines)
**Purpose**: Step-by-step developer integration guide

**Contents**:
- Prerequisites and setup
- User registration flow
- JWT token management
- 2FA implementation
- Multi-tenant operations
- Channel integration (all 10 types)
- AI Engine integration
- Webhook configuration with signature verification
- Rate limiting handling
- Error handling patterns
- SDK examples (Python, Node.js)
- Best practices and security guidelines
- Performance optimization
- Testing and monitoring setup

**Best For**: Developers implementing the API, channel setup, AI integration

---

### 3. QUICK_REFERENCE.md (9 KB, 300+ lines)
**Purpose**: Quick lookup for endpoints and common operations

**Contents**:
- Copy-paste ready API examples
- All endpoints at a glance
- Status codes reference table
- Rate limits by plan
- Webhook event types
- Error response format
- Environment variables template
- SDK installation commands
- Regional currency codes
- Supported channels list
- Resources and links

**Best For**: Quick lookups while coding, command reference

---

### 4. openapi.yaml (56 KB, 2,231 lines)
**Purpose**: Machine-readable OpenAPI 3.1 specification

**Contents**:
- 36 microservices fully documented
- 200+ endpoint definitions
- Complete request/response schemas
- 50+ webhook event types
- Authentication schemes (JWT Bearer)
- Error response schemas
- Rate limiting definitions
- Server configurations (Production, Staging, Local)
- Regional pricing examples
- Indian phone number examples
- Complete webhook callback definitions

**Best For**: API client generation, IDE integration, spec validation

**Services Documented**:
- Authentication (Auth Service)
- Workspace (Tenant Service)
- Messaging (WhatsApp, Email, SMS, Voice, Social, WebChat, Telegram, RCS, Video)
- AI (AI Engine, Intelligence, Voice AI)
- Business (Billing, Analytics, Marketing, E-commerce, Leads, Appointments)
- Management (Notifications, Plugins, Handoff, Workflows, Compliance, CDN, Deployment, etc.)

---

### 5. swagger-ui.html (18 KB, 541 lines)
**Purpose**: Interactive API documentation UI

**Features**:
- Try-it-out functionality for all endpoints
- Dark mode toggle (Ctrl+T)
- Real-time rate limit display
- Bearer token authentication
- Request/response visualization
- Professional Priya Global branding
- Mobile-responsive design
- Keyboard shortcuts
- Service health aggregation
- Getting started guides

**Access**: http://localhost:9000/docs (development)

**Best For**: Interactive testing, learning by example, live endpoint exploration

---

### 6. docs_router.py (732 lines, Python/FastAPI)
**Purpose**: Backend router for serving documentation endpoints

**Endpoints Provided**:
```
GET  /docs                     → Swagger UI interface
GET  /redoc                    → ReDoc documentation
GET  /docs/openapi.json        → OpenAPI spec (JSON)
GET  /docs/download-spec       → Download spec (YAML or JSON)
GET  /docs/health-summary      → All services health status
GET  /docs/services            → List all 36 services
GET  /docs/guides              → Integration guides catalog
GET  /docs/examples            → Code examples
GET  /docs/api-key-management  → Token management info
GET  /docs/changelog           → Version history
```

**Features**:
- Service health aggregation with concurrent checks
- Health caching (10s TTL) for performance
- Error handling for unavailable services
- Async processing with asyncio
- Auto-generation of OpenAPI spec
- Comprehensive error responses

**Integration**:
```python
from services.gateway.docs_router import docs_router

app = FastAPI()
app.include_router(docs_router)
```

**Best For**: Understanding backend documentation serving, integration implementation

---

## API Architecture Overview

```
┌────────────────────────────────────────────────────┐
│      Client Application (Browser/API Client)       │
└────────────────────────┬───────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │  Gateway (Port 9000) │
              │  - JWT validation    │
              │  - Rate limiting     │
              │  - Request routing   │
              │  - Health checks     │
              └────────┬─────────────┘
                       │
        ┌──────────────┼──────────────┬─────────────┬─────────┐
        │              │              │             │         │
        ▼              ▼              ▼             ▼         ▼
    Auth Svc      Tenant Svc    Channel Router  AI Engine  Billing
    (9001)        (9002)         (9003)         (9020)    (9027)
        │              │              │             │         │
        └──────────────┴──────────────┴─────────────┴─────────┘
                       │
              ┌────────▼────────┐
              │ Shared Services  │
              ├──────────────────┤
              │ - PostgreSQL DB  │
              │ - Redis Cache    │
              │ - Message Queue  │
              │ - S3 Storage     │
              └──────────────────┘
```

## Authentication Methods

### JWT Bearer Token
- **Lifetime**: 15 minutes (access), 7 days (refresh)
- **Algorithm**: RS256 (RSA)
- **Header**: `Authorization: Bearer {token}`

### Token Endpoints
```
POST /api/v1/auth/register     → Create account
POST /api/v1/auth/login        → Get tokens
POST /api/v1/auth/refresh      → Refresh access token
POST /api/v1/auth/verify-2fa   → Verify 2FA code
```

## Rate Limiting

| Plan | Per Minute | Per Hour | Per Day |
|------|-----------|----------|---------|
| **Starter** | 100 | 6,000 | 144,000 |
| **Growth** | 500 | 30,000 | 720,000 |
| **Enterprise** | 2,000 | 120,000 | 2,880,000 |

**Response Headers**:
```
X-RateLimit-Limit: 500
X-RateLimit-Remaining: 423
X-RateLimit-Reset: 1709785200
Retry-After: 60
```

## Supported Channels (10 Total)

1. **WhatsApp Business** - SMS-like messaging
2. **Email** - SMTP/SES integration
3. **SMS** - Text messaging (Twilio/AWS SNS)
4. **Voice** - Phone calls (Twilio/AWS Connect)
5. **Instagram** - Social media messaging
6. **Facebook** - Messenger integration
7. **Twitter/X** - Direct messages
8. **Telegram** - Bot messaging
9. **Web Chat** - Embedded widget
10. **RCS** - Rich Communication Services

Plus:
- **Video** - Jitsi, Zoom integration
- **Channel Router** - Intelligent message routing

## Key Features Documented

### Multi-tenancy
- Complete tenant isolation
- Workspace management
- Role-based access control
- Onboarding workflows

### AI Integration
- Conversational AI
- Knowledge base search
- Sentiment analysis
- Intent classification
- Human handoff

### Real-time Communication
- Webhook callbacks
- Event streaming
- Message status tracking
- Delivery receipts

### Business Operations
- Subscription management
- Usage metering
- Invoice generation
- Payment processing
- Analytics & reporting

### Security
- JWT authentication
- HMAC-SHA256 webhook signatures
- Rate limiting
- Audit logging
- Data encryption

## Getting Started Paths

### Path 1: Quick Start (30 minutes)
1. Read README.md (overview)
2. Check QUICK_REFERENCE.md (commands)
3. Try Swagger UI (live testing)

### Path 2: Full Integration (2-3 hours)
1. Read README.md (full overview)
2. Follow INTEGRATION_GUIDE.md (step-by-step)
3. Review QUICK_REFERENCE.md (lookup commands)
4. Check openapi.yaml (detailed specs)
5. Try Swagger UI (test endpoints)

### Path 3: Implementation (depends on scope)
1. Register account
2. Connect channels
3. Configure AI
4. Set up webhooks
5. Implement error handling
6. Monitor with health checks

## Regional Support

### Currencies
- **USD** - United States & International
- **INR** - India (with ₹ symbol)
- **GBP** - United Kingdom
- **AUD** - Australia

### Phone Format
All phone numbers use E.164 format: `+{country_code}{number}`

Example: `+919876543210` (India)

### Timezones
Full timezone support with IANA timezone identifiers
Example: `Asia/Kolkata` (India Standard Time)

## Code Examples

All documentation includes examples in:
- **cURL** - Command-line HTTP
- **Python** - Using requests library
- **JavaScript/Node.js** - Fetch API or axios
- **SDKs** - Official language-specific clients

## SDK Availability

### Official SDKs
- **Python**: `pip install priya-global`
- **JavaScript**: `npm install @priya-global/sdk`
- **Go**: `go get github.com/priya-ai/sdk`

## Support & Resources

### Links
- **API Documentation**: https://api.priyaai.com/docs
- **Website**: https://priyaai.com
- **Status Page**: https://status.priyaai.com
- **GitHub**: https://github.com/priyaai
- **Community**: https://community.priyaai.com
- **Email Support**: support@priyaai.com

### Response Times
- **Auth endpoints**: < 500ms
- **Messaging**: < 2s
- **Analytics**: < 5s
- **File upload**: < 30s

## Documentation Statistics

| Metric | Count |
|--------|-------|
| Total Files | 6 |
| Markdown Files | 4 |
| Code Files | 1 |
| OpenAPI Spec | 1 |
| Total Lines | 5,222+ |
| Services Documented | 36 |
| Endpoints | 200+ |
| Webhook Events | 50+ |
| Authentication Methods | 2 |
| Supported Channels | 10+ |
| Examples | 30+ |
| Languages (Examples) | 3 |

## Version History

### v1.0.0 (March 6, 2024)
- Initial release
- 36 microservices integrated
- Complete multi-tenant support
- Full webhook documentation
- Regional support (4 currencies)
- Comprehensive examples
- Interactive Swagger UI

## How to Use This Documentation

### For Exploring the API
1. Open `swagger-ui.html` in a browser
2. Search for endpoints
3. Click "Try it out"
4. Test with example data

### For Understanding Flow
1. Read `README.md` for overview
2. Check architecture diagram
3. Review webhook examples
4. Follow integration steps

### For Implementation
1. Check INTEGRATION_GUIDE.md for your use case
2. Copy examples from QUICK_REFERENCE.md
3. Reference openapi.yaml for full specs
4. Use provided code snippets

### For Maintenance
1. Monitor health via `/health/services`
2. Check rate limits in response headers
3. Review error codes for troubleshooting
4. Update based on changelog

## Important Notes

- All timestamps in **ISO 8601** format (UTC)
- All monetary amounts in **local currency** (USD, INR, GBP, AUD)
- Request IDs (X-Request-ID) for tracing
- Tenant-scoped responses (no cross-tenant data)
- Async/await patterns for performance
- Webhook signatures (HMAC-SHA256)
- Health checks cached for performance
- Rate limits per tenant, not per user

## Next Steps

1. **Choose Your Path**:
   - Quick Start: README.md → QUICK_REFERENCE.md
   - Full Integration: README.md → INTEGRATION_GUIDE.md
   - Implementation: Start coding with examples

2. **Set Up Your Environment**:
   - Create account at https://priyaai.com
   - Obtain API credentials
   - Set up webhooks endpoint
   - Configure preferred channels

3. **Test Integration**:
   - Use Swagger UI for manual testing
   - Write integration tests
   - Monitor with health checks
   - Implement error handling

4. **Deploy to Production**:
   - Update base URL to production
   - Enable 2FA
   - Set up monitoring
   - Document your implementation

---

**Last Updated**: March 6, 2024
**API Version**: 1.0.0
**Status**: Production Ready

For questions or issues, contact: support@priyaai.com
