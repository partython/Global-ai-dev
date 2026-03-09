# Plugin SDK Service - Priya Global AI Sales Platform

## Overview

The Plugin SDK Service is a FastAPI-based microservice that enables third-party developers to extend the Priya Global platform with custom plugins. It provides a complete plugin lifecycle management system with marketplace, webhooks, event system, and sandboxing.

**File:** `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/plugins/main.py`  
**Port:** 9025  
**Lines of Code:** 1032  
**Database:** PostgreSQL with asyncpg  
**Framework:** FastAPI with async/await

## Architecture

### Multi-Tenant Design
- Every table includes `tenant_id` for Row-Level Security (RLS)
- Tenant ID passed via `X-Tenant-ID` header on all requests
- Complete data isolation between tenants

### Async Implementation
- All database operations use asyncpg for non-blocking I/O
- Webhook delivery uses aiohttp for concurrent requests
- Automatic connection pooling (min: 5, max: 20)

## Database Schema

### Tables (8 total)

1. **plugins** - Main plugin registry with marketplace listing
2. **plugin_configs** - Per-tenant plugin configurations
3. **plugin_api_keys** - Scoped API keys for plugins
4. **plugin_subscriptions** - Event subscriptions
5. **plugin_event_logs** - Event delivery logs with retry tracking
6. **plugin_resource_usage** - Usage metrics and tracking
7. **plugin_analytics** - Time-series analytics data
8. **developers** - Plugin developer accounts

## Key Features

### 1. Plugin Registry & Marketplace
- Register/publish plugins with semantic versioning (semver validation)
- 5 plugin categories: channel, analytics, ai-enhancement, integration, workflow
- Plugin status: draft, published, deprecated
- Marketplace listing with filtering and pagination

### 2. Plugin Lifecycle Management
- Install plugin for tenant with initial configuration
- Activate/deactivate per tenant
- Uninstall with complete cleanup (configs, subscriptions, keys, usage data)
- Auto-update support (version comparison)

### 3. Event System & Webhooks
- Event types: message.received, message.sent, lead.scored, order.created, etc.
- Plugin subscription to events
- Webhook-based plugin execution with HMAC-SHA256 signature verification
- Automatic retry logic (up to 3 retries with exponential backoff)
- Event logging with status tracking

### 4. Plugin Configuration
- Per-tenant key-value configuration storage
- JSON schema validation support
- OAuth credentials support
- Update and retrieve configurations

### 5. API Key Management
- Generate scoped API keys: read-only, read-write, admin
- Rate limiting per plugin per tenant
- Secure key hashing with SHA256
- Key expiration support

### 6. Resource Tracking & Analytics
- API calls counter
- Webhook calls counter
- Error tracking
- Last-used timestamp
- Time-series analytics by event type
- Success/failure rates and latency metrics

### 7. Developer Portal
- Developer registration with company affiliation
- Secure API key generation for developers
- Publish plugins to marketplace
- View install analytics

## API Endpoints (21 total)

### Health & Info
- `GET /api/v1/plugins/health` - Health check with DB status

### Marketplace (Public)
- `GET /api/v1/plugins/marketplace` - Browse plugins with filtering
- `GET /api/v1/plugins/{plugin_id}` - Get plugin details

### Plugin Management
- `POST /api/v1/plugins/install` - Install plugin for tenant
- `DELETE /api/v1/plugins/{plugin_id}/uninstall` - Uninstall plugin
- `PUT /api/v1/plugins/{plugin_id}/activate` - Activate plugin
- `PUT /api/v1/plugins/{plugin_id}/deactivate` - Deactivate plugin
- `GET /api/v1/plugins/installed` - List installed plugins

### Configuration
- `PUT /api/v1/plugins/{plugin_id}/config` - Update config
- `GET /api/v1/plugins/{plugin_id}/config` - Get config

### Event System
- `POST /api/v1/plugins/events/emit` - Emit event to subscribers
- `POST /api/v1/plugins/{plugin_id}/subscribe/{event_type}` - Subscribe to event
- `DELETE /api/v1/plugins/{plugin_id}/subscribe/{event_type}` - Unsubscribe

### Webhooks
- `POST /api/v1/plugins/webhooks/{plugin_id}` - Webhook receiver with signature verification

### Developer Portal
- `POST /api/v1/plugins/developer/register` - Register as developer
- `POST /api/v1/plugins/developer/publish` - Publish plugin to marketplace

### API Keys & Analytics
- `POST /api/v1/plugins/{plugin_id}/api-keys` - Create scoped API key
- `GET /api/v1/plugins/{plugin_id}/analytics` - Get usage analytics

## Security Features

### Authentication & Authorization
- Tenant isolation via X-Tenant-ID header
- API key validation for developers (hashed with SHA256)
- Webhook signature verification (HMAC-SHA256)
- Scoped permissions (read-only, read-write, admin)

### Webhook Security
- HMAC-SHA256 signature in X-Webhook-Signature header
- Constant-time signature comparison (prevent timing attacks)
- Payload validation before processing

### Data Protection
- Secure API key generation (UUID-based)
- Hashed storage of API keys
- SQL parameterized queries (prevent SQL injection)
- JSON schema validation for configs

## Environment Variables

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost/priya_plugins
WEBHOOK_SECRET=dev-secret-key
API_HOST=0.0.0.0
API_PORT=9025
MAX_RETRIES=3
WEBHOOK_TIMEOUT=30
```

## Retry Logic

Webhook delivery implements exponential backoff:
- Attempt 1: immediate
- Attempt 2: 2 second delay
- Attempt 3: 4 second delay
- Attempt 4: 8 second delay
- Max attempts: 3 retries (4 total)

## Logging

Comprehensive logging with INFO level:
- Service startup/shutdown
- Plugin activation/deactivation
- Webhook delivery attempts
- Developer registration
- Plugin publishing
- Event emission
- Database errors

## Request/Response Models

### Pydantic Models (11 total)
- PluginMetadata, PluginInstallRequest, PluginConfigUpdate
- DeveloperRegistration, PluginPublish
- EventPayload, WebhookEvent
- ResourceUsageMetrics, Permission enums
- Semantic version validation

## Database Indexes

Optimized query performance:
- `idx_plugins_tenant` - Tenant-based queries
- `idx_plugins_marketplace` - Marketplace listing
- `idx_subscriptions_tenant` - Event subscriptions
- `idx_event_logs_status` - Event log filtering
- `idx_resource_usage_tenant` - Usage tracking
- `idx_analytics_plugin` - Analytics queries

## Error Handling

- UUID validation with proper error responses
- Database constraint violations (duplicate installs)
- Missing plugin validation
- Tenant authorization checks
- Webhook signature verification failures
- Developer API key validation

## Deployment

```bash
# Install dependencies
pip install fastapi uvicorn asyncpg aiohttp pydantic sqlalchemy

# Run with uvicorn
python main.py

# Or custom host/port
API_HOST=0.0.0.0 API_PORT=9025 python main.py
```

## Testing

Key endpoints to test:
1. Health check: `curl http://localhost:9025/api/v1/plugins/health`
2. Register developer, publish plugin, install for tenant
3. Emit events and verify webhook delivery
4. Test rate limiting and API key scopes
5. Verify tenant isolation
