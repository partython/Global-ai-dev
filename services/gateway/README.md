# Priya Global API Gateway

**Port:** 9000
**Status:** Production-Ready
**Type:** Reverse Proxy + API Gateway

## Overview

Single entry point for ALL external API traffic in the Priya Global multi-tenant AI sales platform. This lightweight gateway handles:

- **Request Routing** - Routes to 13+ internal services
- **Rate Limiting** - Per-tenant sliding window (plan-based), per-IP for unauthenticated
- **Authentication** - JWT extraction & quick validation (full validation delegated to services)
- **Security Headers** - All responses include security headers
- **Request Tracing** - X-Request-ID generation for distributed tracing
- **Response Compression** - gzip compression for JSON/text > 1KB
- **Service Health** - Aggregated health checks with circuit breaker
- **CORS Handling** - Configurable per tenant

## Service Routing

### API Routes (Authenticated)

| Path | Target | Timeout | Service |
|------|--------|---------|---------|
| `/api/v1/auth/*` | :9001 | 5s | Auth |
| `/api/v1/tenants/*` | :9002 | 10s | Tenant |
| `/api/v1/messages/*` | :9003 | 10s | Channel Router |
| `/api/v1/channels/*` | :9003 | 10s | Channel Router |
| `/api/v1/conversations/*` | :9003 | 10s | Channel Router |
| `/api/v1/ai/*` | :9020 | 30s | AI Engine |
| `/api/v1/knowledge/*` | :9020 | 30s | AI Engine |
| `/api/v1/whatsapp/*` | :9010 | 15s | WhatsApp |
| `/api/v1/email/*` | :9011 | 15s | Email |
| `/api/v1/voice/*` | :9012 | 20s | Voice |
| `/api/v1/social/*` | :9013 | 15s | Social |
| `/api/v1/billing/*` | :9027 | 10s | Billing (future) |
| `/api/v1/analytics/*` | :9023 | 30s | Analytics (future) |

### Webhook Routes (No Auth)

| Path | Target | Service |
|------|--------|---------|
| `/webhook/whatsapp` | :9010 | WhatsApp |
| `/webhook/ses` | :9011 | Email (SES) |
| `/webhook/voice` | :9012 | Voice |
| `/webhook/social` | :9013 | Social |
| `/webhook/stripe` | :9027 | Billing |

## Rate Limiting

**Plan-based (per tenant):**
- Starter: 100 req/min (6000 req/hour)
- Growth: 500 req/min (30,000 req/hour)
- Enterprise: 2000 req/min (120,000 req/hour)

**Unauthenticated (per IP):**
- 100 req/hour

**Response Headers:**
```
X-RateLimit-Limit: 6000
X-RateLimit-Remaining: 5999
X-RateLimit-Reset: 1678000000
Retry-After: 3600
```

## Security Features

**Headers on all responses:**
- `X-Content-Type-Options: nosniff` - Prevent MIME sniffing
- `X-Frame-Options: DENY` - Prevent clickjacking
- `X-XSS-Protection: 1; mode=block` - XSS protection
- `Strict-Transport-Security: max-age=31536000` - Force HTTPS
- `Content-Security-Policy: default-src 'self'` - CSP

**Other:**
- Request size limit: 10MB
- Slow-loris protection: 30s request timeout (configurable per service)
- CORS validation
- JWT signature checking (basic)
- PII masking in logs

## Health Endpoints

```bash
# Gateway health
curl http://localhost:9000/health

# All services health
curl http://localhost:9000/health/services
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2025-03-06T10:30:00Z",
  "services": {
    "Auth Service": {"status": "healthy"},
    "Tenant Service": {"status": "healthy"},
    ...
  }
}
```

## API Documentation

```bash
# Swagger UI
http://localhost:9000/docs

# OpenAPI JSON
curl http://localhost:9000/openapi.json
```

## Request/Response Flow

### Authenticated Request

```
Client
  ↓ Authorization: Bearer <JWT>
  ↓ X-Request-ID: [generated]
API Gateway
  ├─ Extract tenant_id from JWT
  ├─ Check rate limit (Redis)
  ├─ Validate token expiry
  └─ Inject X-Tenant-ID header
     ↓
   Downstream Service
     ├─ Full JWT validation
     ├─ RBAC checks
     └─ Response
  ↓
Gateway
  ├─ Compress (if > 1KB)
  ├─ Add security headers
  └─ Add rate limit headers
     ↓
   Client
```

### Webhook Request

```
External System (WhatsApp, Stripe, etc.)
  ↓ POST /webhook/whatsapp
API Gateway
  ├─ No auth required
  ├─ Rate limit (if IP-based)
  └─ Proxy to target service
     ↓
   Webhook Handler Service
```

## Configuration

Via environment variables:

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_SSL=false

# JWT
JWT_PUBLIC_KEY=<RS256 public key>
JWT_ISSUER=priya-global

# CORS
CORS_ORIGINS=https://app.priyaai.com,http://localhost:3000

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=production
DEBUG=false
```

## Running

```bash
# Development
python /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/gateway/main.py

# Production (with Gunicorn)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:9000 \
  services.gateway.main:app
```

## Key Design Decisions

1. **Lightweight Token Validation** - Only checks expiry at gateway; full validation delegated to downstream services
2. **Redis for Rate Limiting** - Sliding window counter for accuracy and distributed support
3. **Streaming Responses** - Large payloads streamed to prevent memory issues
4. **Service Timeouts** - Different per service type (auth: 5s, AI: 30s, etc.)
5. **Health Check Aggregation** - Parallel service checks with caching
6. **No Auth Dependency** - Gateway doesn't import auth module to avoid circular dependencies

## Monitoring

Log format: `[REQUEST-ID] METHOD PATH tenant=TENANT_ID status=CODE elapsed=XMs service=NAME`

Example:
```
[a1b2c3d4-e5f6-7890] POST /api/v1/messages/send tenant=org-123 status=200 elapsed=45ms service=Channel Router
```

## Future Enhancements

- [ ] Circuit breaker pattern for failing services
- [ ] Request deduplication for idempotent operations
- [ ] GraphQL federation
- [ ] Request/response mutation (e.g., PII masking)
- [ ] API versioning (v2, v3, etc.)
- [ ] Canary deployments via header-based routing
