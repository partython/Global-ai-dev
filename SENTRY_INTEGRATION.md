# Sentry Integration for Priya Global Platform

An industry-grade error tracking and performance monitoring system deployed across all 36 FastAPI microservices and the Next.js dashboard.

## Overview

This integration provides:
- **Centralized error tracking** across all services
- **Tenant-aware context** on every error and transaction
- **Performance monitoring** with intelligent sampling
- **PII scrubbing** to ensure data privacy compliance
- **Custom business event tracking** for domain-specific insights
- **Automatic noise filtering** to reduce alert fatigue
- **Session replay** (frontend only) for debugging

## Architecture

### Backend (Python/FastAPI)

**Core Modules:**

1. **`shared/observability/sentry.py`** (302 lines)
   - Main Sentry initialization and configuration
   - PII scrubbing utilities
   - Error and transaction filtering
   - Dynamic sampling strategy
   - Business event capture

2. **`shared/observability/service_init.py`** (54 lines)
   - Centralized service initialization helper
   - One-line setup for all microservices

3. **`shared/middleware/sentry.py`** (84 lines)
   - FastAPI middleware for tenant context enrichment
   - Request/response tracking
   - Performance monitoring
   - Automatic exception capture

### Frontend (TypeScript/Next.js)

**Configuration Files:**

1. **`dashboard/src/lib/sentry.ts`** (127 lines)
   - Client-side Sentry setup
   - Browser error handling
   - Session replay configuration
   - PII scrubbing for frontend

2. **`dashboard/sentry.client.config.ts`**
   - Client-side initialization hook

3. **`dashboard/sentry.server.config.ts`**
   - Server-side API route error handling

4. **`dashboard/sentry.edge.config.ts`**
   - Edge middleware error tracking

## Usage

### For Backend Services

Every microservice already has Sentry integrated. It initializes automatically on startup.

#### Basic Usage

```python
# In request handlers
from shared.observability.sentry import set_tenant_context, capture_business_event

# Set tenant context (usually in middleware)
set_tenant_context(
    tenant_id="t_12345",
    user_id="u_67890",
    plan="enterprise"
)

# Capture business events
capture_business_event(
    "order.created",
    {
        "order_id": "ord_123",
        "amount": 1500,
        "currency": "USD"
    }
)
```

#### Error Tracking

Errors are automatically captured by Sentry middleware. You can also manually capture:

```python
import sentry_sdk

try:
    risky_operation()
except Exception as e:
    sentry_sdk.capture_exception(e)
```

#### Custom Context

```python
import sentry_sdk

with sentry_sdk.configure_scope() as scope:
    scope.set_tag("payment_method", "stripe")
    scope.set_context("order_details", {
        "order_id": "ord_123",
        "status": "processing"
    })
```

### For Frontend (Next.js)

#### Initialization

Initialize in your root layout or `_app.tsx`:

```typescript
import { initSentry, setTenantContext, captureBusinessEvent } from "@/lib/sentry";

// On app load
initSentry();

// After auth (in auth context provider)
setTenantContext(
  tenantId,
  userId,
  userPlan
);
```

#### Capturing Business Events

```typescript
import { captureBusinessEvent } from "@/lib/sentry";

captureBusinessEvent("dashboard.loaded", {
  page: "conversations",
  tenant_id: tenantId
});
```

#### Error Boundaries

Wrap sensitive components:

```typescript
import * as Sentry from "@sentry/nextjs";

const ErrorBoundary = Sentry.errorBoundaryWithProfiler(MyComponent);
```

## Environment Configuration

Set these environment variables:

### For All Services

```bash
# Required
SENTRY_DSN=https://key@sentry.io/project-id

# Optional
ENVIRONMENT=production|staging|development
SENTRY_RELEASE=v1.2.3
SENTRY_ENABLED=true|false
SENTRY_SAMPLE_RATE=1.0
```

### For Frontend (Next.js)

```bash
# Public (browser-accessible)
NEXT_PUBLIC_SENTRY_DSN=https://key@sentry.io/project-id
NEXT_PUBLIC_ENVIRONMENT=production
NEXT_PUBLIC_SENTRY_RELEASE=v1.2.3

# Private (server-only)
SENTRY_DSN=https://key@sentry.io/project-id
ENVIRONMENT=production
SENTRY_RELEASE=v1.2.3
```

## Sampling Strategy

### Errors
- **100% of errors** are captured in all environments
- **HTTP 4xx errors** are filtered (client errors, not bugs)
- **Known noise errors** are ignored (connection resets, timeouts)

### Transactions (Performance)
- **Production**: 20% of API requests, 5% of background tasks
- **Staging**: 100% of all requests
- **Development**: 100% of all requests

### Profiles (Profiling)
- **Production**: 10% of transactions
- **Development**: 50% of transactions

### Session Replay (Frontend Only)
- **Production**: 10% of sessions, 100% of error sessions
- **Development**: 100% of sessions

## PII Scrubbing

Automatically scrubs:
- Email addresses: `john@example.com` → `[EMAIL_REDACTED]`
- Phone numbers: `+14155552671` → `[PHONE_REDACTED]`
- Bearer tokens: `Bearer eyJ0eXAi...` → `Bearer [TOKEN_REDACTED]`
- API keys and secrets: `api_key=sk_live_xxx` → `[CREDENTIAL_REDACTED]`
- Credit cards: `4111-1111-1111-1111` → `[CARD_REDACTED]`
- JWTs: `eyJ0eXAi.eyJzdWI...` → `[JWT_REDACTED]`

## Tenant Context

All errors are automatically tagged with tenant information:

```
Tags:
  - tenant_id: t_12345
  - service: gateway
  - service.port: 9000
  - http.method: POST
  - http.status_code: 500

Context:
  - tenant.id: t_12345
  - tenant.plan: enterprise
```

## Filtering

### Ignored Errors (Won't be reported)
- `ConnectionResetError`
- `BrokenPipeError`
- `asyncio.CancelledError`
- `httpx.ConnectTimeout`
- `redis.ConnectionError`
- HTTP 4xx errors (except 429)

### Ignored Transactions (Won't appear in performance data)
- `/health`, `/healthz`, `/ready`, `/readyz`
- `/metrics`
- `/_next/static`, `/favicon.ico`

## Integrations

### Backend Services
- FastAPI Request integration
- Starlette Middleware integration
- Asyncio integration
- Logging integration (WARNING+ breadcrumbs, ERROR+ events)
- HTTPX integration
- Redis integration

### Frontend
- Next.js integration
- React integration
- Session replay integration
- Performance monitoring

## Services with Sentry Integration

All 35 microservices + 1 dashboard have been configured:

✅ Advanced Analytics (9035)
✅ AI Engine (9004)
✅ AI Training (9036)
✅ Analytics (9021)
✅ Appointments (9029)
✅ Auth (9001)
✅ Billing (9020)
✅ CDN Manager (9040)
✅ Channel Router (9003)
✅ Compliance (9038)
✅ Conversation Intel (9028)
✅ Deployment (9041)
✅ Ecommerce (9023)
✅ Email (9011)
✅ Gateway (9000)
✅ Handoff (9026)
✅ Health Monitor (9039)
✅ Knowledge (9030)
✅ Leads (9027)
✅ Marketing (9022)
✅ Marketplace (9037)
✅ Notification (9024)
✅ Plugins (9025)
✅ RCS (9033)
✅ SMS (9015)
✅ Social (9013)
✅ Telegram (9016)
✅ Tenant (9002)
✅ Tenant Config (9042)
✅ Video (9032)
✅ Voice (9012)
✅ Voice AI (9031)
✅ Webchat (9014)
✅ WhatsApp (9010)
✅ Workflows (9034)
✅ Dashboard (3000)

## Monitoring & Alerting

### Set Up Alerts in Sentry

1. **Per-Tenant Error Spikes**
   ```
   error.type:* AND tags.tenant_id:[tenant_id]
   ```

2. **Service Down (High Error Rate)**
   ```
   tags.service:[service_name] AND level:error
   threshold: > 50 errors/5min
   ```

3. **Performance Degradation**
   ```
   duration > 5000ms
   service: [service_name]
   ```

4. **Business-Critical Events**
   ```
   event.category:business
   business_event:order.failed OR business_event:payment.declined
   ```

## File Locations

### Backend
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/observability/sentry.py`
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/observability/service_init.py`
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/observability/__init__.py`
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/middleware/sentry.py`
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/shared/middleware/__init__.py`

### Frontend
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/dashboard/src/lib/sentry.ts`
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/dashboard/sentry.client.config.ts`
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/dashboard/sentry.server.config.ts`
- `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/dashboard/sentry.edge.config.ts`

### Service Integration Points
All 35 services have been updated with:
- `from shared.observability.sentry import init_sentry` import
- `init_sentry(service_name="...", service_port=...)` call right after FastAPI() instantiation

## Best Practices

1. **Always set tenant context** in auth middleware
2. **Use business events** for domain logic tracking
3. **Never log PII** directly (will be auto-scrubbed but better to avoid)
4. **Add breadcrumbs** for important checkpoints in long operations
5. **Customize context** with business-relevant data (order_id, user_segment, etc)
6. **Monitor sampling rates** - adjust for your error volume
7. **Review ignored errors** - update filters if catching too much noise

## Troubleshooting

### Sentry Not Capturing Events

Check:
1. `SENTRY_DSN` environment variable is set
2. `SENTRY_ENABLED` is not set to false
3. Error is not in `IGNORED_ERRORS` set
4. HTTP status code is not 4xx (except 429)

### High Error Volume

1. Review `IGNORED_ERRORS` configuration
2. Adjust `SENTRY_SAMPLE_RATE` (default 1.0 = 100%)
3. Check `_before_send` filter logic
4. Consider adding transaction filter patterns

### Missing Tenant Context

Ensure:
1. `set_tenant_context()` is called after JWT validation
2. Middleware runs in correct order (after auth)
3. `request.state.tenant_id` is populated by auth middleware

## Future Enhancements

- [ ] Custom dashboards for tenant SLOs
- [ ] Automated incident response (Slack notifications)
- [ ] Custom metrics for business KPIs
- [ ] Distributed tracing across services
- [ ] Replay-assisted debugging
- [ ] Performance budgets per service
