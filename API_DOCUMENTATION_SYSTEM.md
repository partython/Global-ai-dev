# Priya Global API Documentation System

## Overview

A comprehensive API documentation system has been created for Priya Global, covering the entire platform with OpenAPI 3.0 specifications, interactive Swagger UI, and FastAPI routes for serving documentation.

**Total API Coverage:**
- 36 Endpoint paths
- 53 API operations (GET, POST, PATCH, DELETE)
- 40+ major endpoints across 12 service categories
- Complete request/response schemas
- Error handling documentation
- Authentication and rate limiting specifications

---

## Files Created

### 1. `/docs/api/openapi.yaml` (47 KB, 1850+ lines)

**Complete OpenAPI 3.0 specification** covering all major endpoints:

#### Service Categories & Endpoints:

**Authentication (4 operations)**
- POST /api/v1/auth/register - User registration
- POST /api/v1/auth/login - User login
- POST /api/v1/auth/refresh - Refresh access token
- POST /api/v1/auth/logout - User logout

**Conversations (7 operations)**
- GET /api/v1/conversations - List conversations
- POST /api/v1/conversations - Create conversation
- GET /api/v1/conversations/{id} - Get conversation details
- PATCH /api/v1/conversations/{id} - Update conversation
- POST /api/v1/conversations/{id}/messages - Send message
- PATCH /api/v1/conversations/{id}/close - Close conversation

**Contacts (5 operations)**
- GET /api/v1/contacts - List contacts
- POST /api/v1/contacts - Create contact
- GET /api/v1/contacts/{id} - Get contact details
- PATCH /api/v1/contacts/{id} - Update contact
- DELETE /api/v1/contacts/{id} - Delete contact

**Channels (5 operations)**
- GET /api/v1/channels - List channels
- POST /api/v1/channels - Configure channel
- GET /api/v1/channels/{id} - Get channel details
- PATCH /api/v1/channels/{id} - Update channel
- DELETE /api/v1/channels/{id} - Delete channel

**Knowledge Base (5 operations)**
- GET /api/v1/knowledge/documents - List documents
- POST /api/v1/knowledge/documents - Upload document
- GET /api/v1/knowledge/documents/{id} - Get document details
- DELETE /api/v1/knowledge/documents/{id} - Delete document
- POST /api/v1/knowledge/query - Search documents

**AI Services (2 operations)**
- POST /api/v1/ai/classify - Classify message
- POST /api/v1/ai/generate-response - Generate AI response

**Analytics (3 operations)**
- GET /api/v1/analytics/overview - Dashboard overview
- GET /api/v1/analytics/conversations - Conversation analytics
- GET /api/v1/analytics/agents - Agent performance

**Billing (4 operations)**
- GET /api/v1/billing/subscription - Get subscription
- POST /api/v1/billing/subscribe - Create/upgrade subscription
- GET /api/v1/billing/invoices - List invoices
- GET /api/v1/billing/usage - Get current usage

**Campaigns (4 operations)**
- GET /api/v1/campaigns - List campaigns
- POST /api/v1/campaigns - Create campaign
- GET /api/v1/campaigns/{id} - Get campaign details
- PATCH /api/v1/campaigns/{id} - Update campaign
- POST /api/v1/campaigns/{id}/send - Send campaign

**Workflows (4 operations)**
- GET /api/v1/workflows - List workflows
- POST /api/v1/workflows - Create workflow
- GET /api/v1/workflows/{id} - Get workflow details
- PATCH /api/v1/workflows/{id} - Update workflow
- POST /api/v1/workflows/{id}/execute - Execute workflow

**Team Management (3 operations)**
- GET /api/v1/team/members - List team members
- POST /api/v1/team/invite - Invite team member
- DELETE /api/v1/team/{id} - Remove team member

**Webhooks (3 operations)**
- GET /api/v1/webhooks - List webhooks
- POST /api/v1/webhooks - Create webhook
- DELETE /api/v1/webhooks/{id} - Delete webhook

**Leads (2 operations)**
- GET /api/v1/leads - List leads
- POST /api/v1/leads - Capture lead

**Health & Status (1 operation)**
- GET /health - Platform health check

#### OpenAPI Specification Includes:

- **Info Section**: Title, version, description, contact, license, logo
- **Servers**: Production, Staging, and Local Development
- **Security**: Bearer JWT authentication
- **Tags**: 14 organized service categories
- **Components**:
  - `securitySchemes`: JWT bearer token
  - `schemas`: 15+ reusable request/response models
    - Error, HealthStatus, Conversation, Message, Contact
    - Channel, Document, Campaign, Workflow, TeamMember
    - Webhook, Lead, and more

#### Response Specifications:
- **Status Codes**: 200, 201, 204, 400, 401, 403, 404, 413, 429, 500
- **Request Bodies**: Complete with required fields, examples, and constraints
- **Response Bodies**: Fully documented with field descriptions and types
- **Error Responses**: Standardized error schema with detail, code, request_id, timestamp
- **Pagination**: limit, offset, total_count, cursor support
- **Rate Limiting**: Plan-based throttling information

---

### 2. `/docs/api/index.html` (12 KB)

**Interactive Swagger UI documentation page** with:

#### Features:
- Modern, responsive design with Priya Global branding
- Custom color scheme (Primary: #1565C0, Accent: #FF6F00)
- Dark mode support with CSS media queries
- Try-it-out functionality for all endpoints
- Request/response visualization
- Built-in authentication testing
- Server selection dropdown
- Search and filter capabilities

#### Custom Styling:
- Custom topbar with gradient background
- Color-coded operation types:
  - GET (purple)
  - POST (green)
  - PATCH (orange)
  - DELETE (red)
- Responsive table layouts
- Dark mode with automatic theme detection
- Accessible form inputs and buttons
- Smooth transitions and hover states

#### Swagger UI Components:
- Swagger UI Bundle (v3) from CDN
- Request interceptor for logging
- Response interceptor for monitoring
- Deep linking support
- Model expansion controls
- Filter support for operations

---

### 3. `/services/gateway/docs_routes.py` (23 KB)

**FastAPI routes for serving API documentation** with:

#### Route Endpoints:
```
GET  /docs                  - Swagger UI HTML page
GET  /docs/openapi.json     - OpenAPI specification JSON
GET  /redoc                 - ReDoc alternative documentation
GET  /docs/health           - Service health status
GET  /docs/services         - Microservice catalog
GET  /docs/guides           - Integration guides
GET  /docs/examples         - Code examples
GET  /docs/changelog        - API version history
GET  /docs/download-spec    - Download specification
```

#### Key Features:

**Service Health Monitoring:**
- Asynchronous health check aggregation for all 36 microservices
- 10-second cache to prevent excessive checks
- SSRF prevention with URL validation
- Individual service timeout handling
- Overall platform health status calculation

**Security:**
- Bearer token authentication with HTTPBearer
- SSRF attack prevention via URL validation
- Private IP range checking
- Localhost and loopback allowlisting

**Service Mapping (36 Services):**
- Auth, Tenant, Channel Router, AI Engine
- WhatsApp, Email, Voice, SMS, Social
- WebChat, Telegram, RCS, Video
- Billing, Analytics, Marketing, E-commerce
- Notifications, Plugins, Handoff, Leads
- Conversation Intelligence, Appointments
- Workflows, Compliance, CDN, Deployment

**Documentation Features:**
- Service catalog with descriptions and ports
- Integration guides with URLs
- Code examples in multiple languages (cURL, Python, JavaScript)
- API changelog and version history
- Error handling documentation

#### Implementation Details:

```python
# Health Check Caching
HEALTH_CACHE_TTL = 10  # seconds
_health_cache: Dict[str, Dict[str, Any]] = {}

# Service Validation
_validate_internal_url(target: str) -> bool
# Prevents SSRF by validating internal addresses only

# Async Health Aggregation
async def _get_service_health(client, target, name) -> Dict
# Checks individual service health with timeout handling

# FastAPI Routes
@docs_router.get("/openapi.json")
@docs_router.get("/")  # Swagger UI
@docs_router.get("/redoc")
@docs_router.get("/health")
@docs_router.get("/services")
@docs_router.get("/guides")
@docs_router.get("/examples")
@docs_router.get("/changelog")
```

---

## Integration with Gateway

The documentation system integrates seamlessly with the Priya Global Gateway (port 9000):

### Setup Instructions:

1. **Import the router in main.py:**
```python
from services.gateway.docs_routes import docs_router

# Include in FastAPI app
app.include_router(docs_router, prefix="/docs")
```

2. **Ensure files are in place:**
```
docs/api/openapi.yaml   # OpenAPI specification
docs/api/index.html     # Swagger UI page
services/gateway/docs_routes.py  # FastAPI routes
```

3. **Access Documentation:**
```
http://localhost:9000/docs              # Swagger UI
http://localhost:9000/docs/openapi.json # OpenAPI spec
http://localhost:9000/redoc             # ReDoc view
http://localhost:9000/docs/health       # Service health
```

---

## API Documentation Features

### 1. Request Documentation
- **Path Parameters**: UUID and enum validation
- **Query Parameters**: Filtering, sorting, pagination
- **Request Bodies**: JSON with required fields and examples
- **File Uploads**: Multipart form-data support
- **Authentication**: Bearer JWT token requirement

### 2. Response Documentation
- **Success Responses**: 200, 201, 204 with schemas
- **Error Responses**: 400, 401, 403, 404, 429, 500
- **Error Schema**: Standard format with detail, code, request_id
- **Pagination**: limit, offset, total_count, cursor
- **Examples**: Real-world request/response examples

### 3. Data Schemas
- **UUID Types**: For IDs and identifiers
- **Date-Time Formats**: ISO 8601 with timezone
- **Enums**: Restricted value sets for statuses, channels
- **Objects**: Nested data structures with type definitions
- **Arrays**: Paginated and bulk operation support

### 4. Security Documentation
- **Authentication**: Bearer JWT tokens
- **Token Lifetime**: 15 minutes (access), 7 days (refresh)
- **Rate Limiting**: Plan-based throttling (100-2000 req/min)
- **Multi-tenancy**: X-Tenant-ID header injection
- **CORS**: Cross-origin request handling

---

## Endpoint Groups

### Multi-Channel Communication
- **Conversations**: Message threading and context
- **Channels**: WhatsApp, Email, SMS, Voice, Social, RCS, Video, Telegram, WebChat
- **Messages**: Routing, delivery, and tracking

### Customer Management
- **Contacts**: Database and CRM integration
- **Leads**: Capture and qualification
- **Analytics**: Customer insights and metrics

### AI & Intelligence
- **Classification**: Message categorization
- **Response Generation**: AI-powered replies
- **Knowledge Base**: Document search and retrieval

### Business Operations
- **Campaigns**: Marketing and bulk messaging
- **Workflows**: Automation and triggers
- **Appointments**: Scheduling and reminders
- **Billing**: Subscriptions and invoicing

### Administration
- **Team**: User and role management
- **Webhooks**: Event subscriptions
- **Compliance**: Audit and data management

---

## Example Usage

### Login and Get Token
```bash
curl -X POST https://api.priyaai.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePass123!"
  }'
```

### Create Conversation
```bash
curl -X POST https://api.priyaai.com/api/v1/conversations \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "contact_id": "123e4567-e89b-12d3-a456-426614174000",
    "channel": "whatsapp",
    "subject": "Product Inquiry"
  }'
```

### Send Message with AI
```bash
curl -X POST https://api.priyaai.com/api/v1/conversations/{id}/messages \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Customer question here",
    "use_ai": true
  }'
```

### Check Service Health
```bash
curl https://localhost:9000/docs/health
```

---

## File Statistics

| File | Size | Lines | Type |
|------|------|-------|------|
| openapi.yaml | 47 KB | 1850+ | YAML |
| index.html | 12 KB | 250+ | HTML |
| docs_routes.py | 23 KB | 530+ | Python |
| **Total** | **82 KB** | **2630+** | Combined |

---

## Architecture

```
Gateway (Port 9000)
│
├── /docs                 → Swagger UI (index.html)
├── /docs/openapi.json    → OpenAPI Spec JSON
├── /redoc                → ReDoc Documentation
├── /docs/health          → Service Health Aggregator
├── /docs/services        → Service Catalog
├── /docs/guides          → Integration Guides
├── /docs/examples        → Code Examples
└── /docs/changelog       → Version History

API Routes → Service Mapping (36 Microservices)
│
├── Auth (9001)
├── Tenant (9002)
├── Channel Router (9003)
├── AI Engine (9020)
├── Billing (9027)
├── Analytics (9023)
├── Marketing (9024)
├── E-commerce (9025)
├── Notifications (9026)
├── Plugins (9028)
├── Handoff (9029)
├── Leads (9030)
├── Intelligence (9031)
├── Appointments (9032)
├── Workflows (9033)
├── Compliance (9034)
├── CDN (9035)
├── Deployment (9036)
└── ... (additional services)
```

---

## Next Steps

1. **Integration**: Add docs_router import to gateway main.py
2. **Testing**: Access documentation at http://localhost:9000/docs
3. **Customization**: Update openapi.yaml with any service-specific details
4. **Deployment**: Include docs files in Docker images
5. **CDN**: Consider hosting openapi.yaml on CDN for faster delivery

---

## Documentation Standards

All endpoints follow REST conventions:
- **GET**: Retrieve resources
- **POST**: Create new resources
- **PATCH**: Partial updates
- **DELETE**: Remove resources
- **PUT**: Full replacement (if applicable)

All responses use:
- Standard HTTP status codes
- JSON formatting
- Consistent error structures
- Pagination for list endpoints
- UTC timestamps

---

## Support

For documentation updates or API changes:
1. Update `docs/api/openapi.yaml` with new endpoints
2. Reload `/docs/openapi.json` endpoint
3. Documentation updates automatically reflect in Swagger UI
4. Keep `docs_routes.py` in sync with service mappings

---

## License

Commercial - Priya Global
Contact: support@priyaai.com
