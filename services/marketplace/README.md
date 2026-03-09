# Marketplace & App Store Service

**Location**: `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/marketplace/main.py`
**Port**: 9037
**Lines**: 1001 (optimized architecture)

## Overview
Multi-tenant SaaS FastAPI application providing a complete marketplace ecosystem for third-party app integrations, developer portal, webhook management, and customizable themes.

## Architecture Highlights

### 1. Security & Authentication
- **JWT Authentication**: HTTPBearer + PyJWT with HS256 algorithm
- **AuthContext**: Custom claims structure (sub, tenant_id, email, exp)
- **No Hardcoded Secrets**: All credentials from `os.getenv()` with required validation
  - `JWT_SECRET` (required, no defaults)
  - `DB_PASSWORD` (required, no defaults)
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`
  - `CORS_ORIGINS`, `PORT`
- **Token Validation**: ExpiredSignatureError and InvalidTokenError handling

### 2. Database Layer
- **AsyncPG Connection Pool**: 5-20 connections with 60s timeout
- **Multi-tenant RLS**: Tenant isolation via tenant_id on all queries
- **Automatic Schema Setup**: Creates tables and indices on startup
- **Tables**:
  - `apps`: Marketplace applications with versioning and status tracking
  - `app_installations`: Per-tenant app installations with permission scoping
  - `app_reviews`: User ratings and comments with aggregated scoring
  - `developers`: Developer profiles and registration status
  - `webhooks`: Custom webhook configurations
  - `webhook_templates`: Pre-built webhook templates (Zapier, Make, n8n)
  - `themes`: Custom chat widget themes with styling

### 3. Core Features

#### Feature 1: App Marketplace (Browse & Search)
- **Endpoint**: `GET /marketplace/apps`
- **Parameters**: query, category (CRM, Analytics, Payments, Communication, Productivity, Security, Integration), limit, offset
- **Filtering**: Full-text search on app name/description, category filtering
- **Status**: Only displays "approved" apps to users
- **Aggregates**: Rating, review_count, installation_count

#### Feature 2: App Installation & Management
- **Install**: `POST /marketplace/apps/{id}/install`
  - One-click installation per tenant
  - Permission scoping (read, write, admin)
  - OAuth redirect URI support
  - Prevents duplicate installations
- **Uninstall**: `DELETE /marketplace/apps/{id}/uninstall`
- **Reviews**: `POST /marketplace/apps/{id}/review`
  - Rating (1-5 stars)
  - Comment submission
  - Automatic aggregation of ratings

#### Feature 3: Developer Portal
- **Register**: `POST /marketplace/developer/register`
  - Company information submission
  - Developer profile creation
  - Status tracking (pending approval)
- **Submit App**: `POST /marketplace/developer/apps`
  - App metadata and versioning
  - OAuth client configuration
  - Permission requirements declaration
  - Status workflow (draft → pending_review → approved/rejected)
- **List Apps**: `GET /marketplace/developer/apps`
  - Developer's app inventory with metrics

#### Feature 4: Webhook Marketplace
- **Templates**: `GET /marketplace/webhooks/templates`
  - Pre-built patterns: Zapier, Make, n8n integration templates
  - Example payloads for reference
- **Custom Webhooks**: `POST /marketplace/webhooks`
  - Create custom webhook configurations
  - Template-based or custom setup
- **Testing**: `POST /marketplace/webhooks/test`
  - Webhook delivery testing sandbox
  - Response time metrics
  - Success/failure validation

#### Feature 5: Theme & Widget Store
- **Browse Themes**: `GET /marketplace/themes`
  - Pre-built chat widget themes
  - Download tracking
  - Category organization
- **Customize**: `POST /marketplace/themes/customize`
  - Custom theme variant creation
  - Primary/secondary color customization
  - Font family selection
  - Border radius control
  - Custom CSS injection

#### Health Check
- **Endpoint**: `GET /marketplace/health`
- **Response**: Status, timestamp, database connection status, version

## Models & Enums

### Enums
- **AppCategory**: crm, analytics, payments, communication, productivity, security, integration
- **PermissionScope**: read, write, admin
- **AppStatus**: draft, pending_review, approved, rejected, deprecated
- **WebhookType**: zapier, make, n8n, custom

### Key Request/Response Models
- **AuthContext**: JWT claims validation structure
- **AppMarketplaceItem**: Marketplace listing view
- **AppDetailResponse**: Full app details with changelog
- **AppInstallationResponse**: Installation confirmation with token
- **DeveloperResponse**: Developer registration response
- **WebhookTemplateResponse**: Template listing
- **ThemeResponse**: Theme with styling metadata

## CORS Configuration
- **Source**: Environment variable `CORS_ORIGINS`
- **Default**: http://localhost:3000
- **Format**: Comma-separated list of origins
- **Example**: "https://app.example.com,https://admin.example.com"
- **All Methods & Headers**: Permitted for cross-origin requests

## Environment Variables (Required)

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=marketplace_db
DB_USER=marketplace_user
DB_PASSWORD=<secret-password>  # NO DEFAULT

# Authentication
JWT_SECRET=<secret-key>  # NO DEFAULT

# Server
PORT=9037  # Optional, defaults to 9037

# CORS
CORS_ORIGINS=http://localhost:3000  # Optional, defaults to localhost:3000
```

## Async Operations
- All database operations use asyncpg for non-blocking I/O
- Connection pooling with acquire/release
- Concurrent request handling
- Proper exception propagation

## Tenant Isolation (RLS)
Every database query enforces tenant_id validation:
- App visibility filtered by status and tenant ownership
- Installation records scoped to tenant
- Review queries filtered by tenant
- Developer profiles isolated by tenant
- Webhook configurations isolated by tenant
- Cross-tenant data access prevented

## Running the Service

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=marketplace_db
export DB_USER=marketplace_user
export DB_PASSWORD=your_secret_password
export JWT_SECRET=your_jwt_secret
export CORS_ORIGINS="http://localhost:3000,https://app.example.com"
export PORT=9037

python /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/marketplace/main.py
```

## Dependencies
```
fastapi>=0.100.0
uvicorn>=0.23.0
asyncpg>=0.28.0
pydantic>=2.0.0
pyjwt>=2.8.0
python-multipart>=0.0.6
```

## API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /marketplace/health | Health check |
| GET | /marketplace/apps | Browse/search marketplace |
| GET | /marketplace/apps/{id} | Get app details |
| POST | /marketplace/apps/{id}/install | Install app |
| DELETE | /marketplace/apps/{id}/uninstall | Uninstall app |
| POST | /marketplace/apps/{id}/review | Submit review |
| POST | /marketplace/developer/register | Register as developer |
| POST | /marketplace/developer/apps | Submit app for review |
| GET | /marketplace/developer/apps | List developer's apps |
| GET | /marketplace/webhooks/templates | Get webhook templates |
| POST | /marketplace/webhooks | Create webhook |
| POST | /marketplace/webhooks/test | Test webhook delivery |
| GET | /marketplace/themes | List themes |
| POST | /marketplace/themes/customize | Customize theme |

## Security Notes
- All secrets from environment variables with no defaults
- JWT token validation on protected endpoints
- RLS enforcement on every database operation
- Connection pool isolation
- No credential logging
- Proper error handling without leaking sensitive information
