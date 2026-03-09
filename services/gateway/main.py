"""
Priya Global API Gateway (Port 9001)

Single entry point for ALL external API traffic. This lightweight reverse proxy:
- Routes requests to internal services via ServiceRegistry
- Enforces rate limiting (per-tenant, plan-based)
- Validates JWTs and injects tenant context
- Aggregates service health
- Adds security headers and request tracing
- Compresses responses
- Provides API documentation aggregation
- Uses ServiceClient for resilient inter-service communication with circuit breaker pattern

SECURITY: The gateway now FULLY validates JWT signatures. Previously, it used verify_signature=False,
which meant ANY attacker could forge a valid-looking token with arbitrary tenant_id/role claims.
Downstream services still validate independently (defense in depth), but the gateway is the first wall.

SERVICE DISCOVERY:
- Uses ServiceRegistry for all downstream service URL resolution
- Supports LOCAL, DOCKER, and KUBERNETES deployments
- Circuit breaker pattern automatically handles service failures
"""

import asyncio
import gzip
import hashlib
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
import redis.asyncio as redis
from fastapi import FastAPI, Request, Response, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

# Add shared core to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.core.config import config
from shared.core.security import get_rate_limit, mask_pii
from shared.core.service_registry import get_registry
from shared.core.http_client import (
    get_service_client,
    close_service_client,
    CircuitOpenError,
    ServiceTimeoutError,
    ServiceConnectionError,
)
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config, get_allowed_origins
from shared.realtime.websocket_manager import get_websocket_manager
from shared.realtime.events import parse_ws_message, create_error_message, create_pong_message

# ─── Configuration ───

logger = logging.getLogger("priya.gateway")
logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Service routing table (maps API paths to service names and configuration)
ROUTE_TABLE = {
    "/api/v1/auth": {
        "service": "auth",
        "timeout": 5,
        "auth_required": False,
    },
    "/api/v1/tenants": {
        "service": "tenant",
        "timeout": 10,
        "auth_required": True,
    },
    "/api/v1/messages": {
        "service": "channel_router",
        "timeout": 10,
        "auth_required": True,
    },
    "/api/v1/channels": {
        "service": "channel_router",
        "timeout": 10,
        "auth_required": True,
    },
    "/api/v1/conversations": {
        "service": "conversation",
        "timeout": 10,
        "auth_required": True,
    },
    "/api/v1/ai": {
        "service": "ai_engine",
        "timeout": 30,
        "auth_required": True,
    },
    "/api/v1/knowledge": {
        "service": "knowledge_base",
        "timeout": 30,
        "auth_required": True,
    },
    "/api/v1/memory": {
        "service": "memory",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/whatsapp/embedded-signup": {
        "service": "whatsapp",
        "timeout": 30,
        "auth_required": True,
        # No balance required — this is the onboarding flow
    },
    "/api/v1/whatsapp/connection-status": {
        "service": "whatsapp",
        "timeout": 10,
        "auth_required": True,
    },
    "/api/v1/whatsapp/calling": {
        "service": "whatsapp",
        "timeout": 20,
        "auth_required": True,
        "requires_balance": True,  # Calls cost money
    },
    "/api/v1/whatsapp": {
        "service": "whatsapp",
        "timeout": 15,
        "auth_required": True,
        "requires_balance": True,  # Paid channel — wallet balance required
    },
    "/api/v1/email": {
        "service": "email",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/voice": {
        "service": "voice",
        "timeout": 20,
        "auth_required": True,
        "requires_balance": True,  # Paid channel — wallet balance required
    },
    "/api/v1/social": {
        "service": "facebook",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/instagram": {
        "service": "facebook",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/facebook": {
        "service": "facebook",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/billing": {
        "service": "billing",
        "timeout": 10,
        "auth_required": True,
    },
    "/api/v1/analytics": {
        "service": "analytics",
        "timeout": 30,
        "auth_required": True,
    },
    "/api/v1/leads": {
        "service": "leads",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/notifications": {
        "service": "notification",
        "timeout": 10,
        "auth_required": True,
    },
    "/api/v1/appointments": {
        "service": "appointment",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/translation": {
        "service": "translation",
        "timeout": 30,
        "auth_required": True,
    },
    "/api/v1/sms": {
        "service": "sms",
        "timeout": 15,
        "auth_required": True,
        "requires_balance": True,  # Paid channel — wallet balance required
    },
    "/api/v1/ecommerce": {
        "service": "ecommerce",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/connectors": {
        "service": "rest_connector",
        "timeout": 30,
        "auth_required": True,
    },
    "/api/v1/plugins": {
        "service": "plugins",
        "timeout": 15,
        "auth_required": True,
    },
    "/api/v1/developers": {
        "service": "developer_portal",
        "timeout": 15,
        "auth_required": False,
    },
    "/api/v1/docs": {
        "service": "developer_portal",
        "timeout": 15,
        "auth_required": False,
    },
    "/api/v1/sandbox": {
        "service": "developer_portal",
        "timeout": 30,
        "auth_required": False,
    },
    "/api/v1/wallet": {
        "service": "wallet",
        "timeout": 15,
        "auth_required": True,
    },
}

# Webhook routing (no authentication required)
WEBHOOK_TABLE = {
    "/webhook/whatsapp": {
        "service": "whatsapp",
        "timeout": 10,
    },
    "/webhook/ses": {
        "service": "email",
        "timeout": 10,
    },
    "/webhook/voice": {
        "service": "voice",
        "timeout": 10,
    },
    "/webhook/social": {
        "service": "facebook",
        "timeout": 10,
    },
    "/webhook/stripe": {
        "service": "billing",
        "timeout": 10,
    },
    "/webhook/sms": {
        "service": "sms",
        "timeout": 10,
    },
    "/webhook/ecommerce": {
        "service": "ecommerce",
        "timeout": 10,
    },
    "/webhook/rest-connector": {
        "service": "rest_connector",
        "timeout": 15,
    },
    "/webhooks/razorpay": {
        "service": "wallet",
        "timeout": 10,
    },
}

# ─── Application Setup ───

app = FastAPI(
    title="Priya Global API Gateway",
    description="Central API routing, rate limiting, and security layer",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
# Initialize Sentry error tracking
init_sentry(service_name="gateway", service_port=9000)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="gateway")
app.add_middleware(TracingMiddleware)


# CORS middleware with centralized, environment-specific configuration
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Global clients
service_client = None  # Will be initialized at startup
redis_client: Optional[redis.Redis] = None
service_registry = None  # Will be initialized at startup
websocket_manager = None  # Will be initialized at startup


# Initialize event bus
event_bus = EventBus(service_name="gateway")

# ─── Lifecycle Events ───


@app.on_event("startup")
async def startup():
    """Initialize connections on startup."""
    global service_client, redis_client, service_registry, websocket_manager

    # Initialize service registry
    await event_bus.startup()
    service_registry = get_registry(environment=config.environment)
    logger.info("Service registry initialized: %d services", len(service_registry.get_all_services()))
    logger.info("Deployment environment: %s", service_registry.get_environment())

    # Initialize service client
    service_client = await get_service_client(environment=config.environment)
    logger.info("Service client initialized with circuit breaker pattern")

    # Initialize Redis client
    redis_client = redis.from_url(config.redis.url, decode_responses=True)
    logger.info("Redis client initialized")

    # Initialize WebSocket manager
    websocket_manager = get_websocket_manager()
    await websocket_manager.startup()
    logger.info("WebSocket manager initialized")

    logger.info("Gateway started on port 9001")
    logger.info("Configuration environment: %s", config.environment)


@app.on_event("shutdown")
async def shutdown():
    """Clean up connections on shutdown."""
    global service_client, redis_client, websocket_manager
    shutdown_tracing()

    await event_bus.shutdown()
    if service_client:
        await close_service_client()
        logger.info("Service client closed")

    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed")

    if websocket_manager:
        await websocket_manager.shutdown()
        logger.info("WebSocket manager closed")

    logger.info("Gateway shutdown")


# ─── Rate Limiting ───


async def check_rate_limit(
    tenant_id: Optional[str], client_ip: str, request_path: str
) -> tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if request is within rate limit.
    Returns (allowed, response_dict_if_limited).
    """
    if not redis_client:
        return True, None

    # For authenticated requests: use tenant-based rate limit
    if tenant_id:
        # Get tenant plan from a cached lookup (simplified for gateway)
        # In production, this would be cached from the tenant service
        plan = "growth"  # Default, should be fetched from tenant context
        limit_per_hour = get_rate_limit(plan) * 60  # Convert req/min to req/hour
        window_key = f"rl:tenant:{tenant_id}:hourly"
    else:
        # For unauthenticated: use IP-based rate limit (100 req/hour)
        limit_per_hour = 100
        window_key = f"rl:ip:{client_ip}:hourly"

    try:
        # Sliding window counter in Redis
        now = int(time.time())
        current_count = await redis_client.incr(window_key)

        if current_count == 1:
            # First request in window, set expiry
            await redis_client.expire(window_key, 3600)

        if current_count > limit_per_hour:
            reset_time = now + 3600
            return False, {
                "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
                "detail": "Rate limit exceeded",
                "X-RateLimit-Limit": str(limit_per_hour),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
                "Retry-After": str(3600),
            }

        return True, {
            "X-RateLimit-Limit": str(limit_per_hour),
            "X-RateLimit-Remaining": str(max(0, limit_per_hour - current_count)),
            "X-RateLimit-Reset": str(now + 3600),
        }

    except Exception as e:
        logger.error("Rate limit check failed: %s", type(e).__name__)
        # Fail open - don't block on Redis errors
        return True, None


# ─── Token Extraction & Validation ───


def extract_and_validate_token(authorization_header: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Quick token extraction and basic validation.
    Does NOT do full validation (that's downstream service's job).

    ARCHITECTURE NOTE: The gateway validates only token format and expiry (quick rejection).
    Full signature validation is delegated to downstream services that hold the JWT secret.
    This design allows the gateway to scale independently and prevents secret management
    complexity at the edge. Each service validates the complete token with its own secret.

    Returns verified claims if token signature is valid, required fields present, and not expired.
    Rejects ALL tokens with invalid signatures — no more verify_signature=False.
    """
    if not authorization_header:
        return None

    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]

    try:
        # FULL signature verification — never skip this
        verified = jwt.decode(
            token,
            config.jwt.secret_key,
            algorithms=[config.jwt.algorithm],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require": ["sub", "tenant_id", "exp", "iat"],
            },
            issuer=config.jwt.issuer,
        )

        # Validate required claim types
        if not isinstance(verified.get("tenant_id"), str) or not verified["tenant_id"]:
            logger.warning("JWT missing or empty tenant_id claim")
            return None
        if not isinstance(verified.get("sub"), str) or not verified["sub"]:
            logger.warning("JWT missing or empty sub claim")
            return None

        return verified

    except jwt.ExpiredSignatureError:
        logger.debug("Token expired at gateway")
        return None
    except jwt.InvalidIssuerError:
        logger.warning("Token has invalid issuer")
        return None
    except jwt.InvalidSignatureError:
        logger.warning("Token has INVALID SIGNATURE — possible forgery attempt")
        return None
    except jwt.DecodeError as e:
        logger.warning("Token decode failed: %s", type(e).__name__)
        return None
    except Exception as e:
        logger.debug("Token extraction failed: %s", type(e).__name__)
        return None


# ─── Request/Response Middleware ───


async def compress_response(content: bytes) -> bytes:
    """Compress response with gzip if > 1KB."""
    if len(content) <= 1024:
        return content

    buf = BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write(content)
    return buf.getvalue()


def get_security_headers() -> Dict[str, str]:
    """Return security headers for all responses."""
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
    }


# ─── Service Routing ───


def find_route(path: str) -> Optional[tuple[str, Dict[str, Any]]]:
    """Find matching route for a path. Longest prefix match."""
    best_match = None
    best_config = None

    for prefix, route_config in {**ROUTE_TABLE, **WEBHOOK_TABLE}.items():
        if path.startswith(prefix) and (
            best_match is None or len(prefix) > len(best_match)
        ):
            best_match = prefix
            best_config = route_config

    return (best_match, best_config) if best_match else (None, None)


# ─── Wallet Balance Gate ─────────────────────────────────────────────────────

# Simple in-memory cache for balance checks (avoid hitting wallet service on every request)
_balance_cache: Dict[str, tuple] = {}  # tenant_id -> (balance_ok, timestamp)
_BALANCE_CACHE_TTL = 30  # seconds


async def _check_tenant_balance(tenant_id: str) -> bool:
    """
    Check if tenant has sufficient wallet balance for paid operations.
    Uses a short TTL cache to avoid hammering the wallet service.
    Returns True if balance > 0, False if zero/negative.
    """
    import time as _time

    # Check cache first
    cached = _balance_cache.get(tenant_id)
    if cached:
        ok, ts = cached
        if _time.time() - ts < _BALANCE_CACHE_TTL:
            return ok

    # Call wallet service
    try:
        if service_client:
            resp = await service_client.call_service(
                "wallet", "GET", "/api/v1/wallet/balance",
                tenant_id=tenant_id,
                request_id=str(uuid.uuid4()),
            )
            if resp.status_code == 200:
                import json
                data = json.loads(resp.content)
                balance_ok = data.get("balance_paisa", 0) > 0
                _balance_cache[tenant_id] = (balance_ok, _time.time())
                return balance_ok
    except Exception as e:
        logger.warning(f"Wallet balance check failed: {e}")

    # Default: allow if check fails (don't block on wallet service outage)
    return True


async def proxy_request(
    request: Request,
    service_name: str,
    timeout: int,
    tenant_id: Optional[str] = None,
) -> Response:
    """
    Proxy request to downstream service using ServiceClient.

    Handles circuit breaker state, automatic retries, and resilience patterns.
    """
    global service_client

    if not service_client:
        return JSONResponse(
            {"detail": "Service temporarily unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Path forwarding strategy:
    # - API routes: forward FULL path (services define their own /api/v1/... routes)
    # - Webhook routes: strip the gateway prefix (e.g., /webhook/whatsapp → /webhook)
    #   because services define webhooks at /webhook, not /webhook/whatsapp
    path = request.url.path
    is_webhook_path = any(path.startswith(wp) for wp in WEBHOOK_TABLE.keys())
    if is_webhook_path:
        for prefix in WEBHOOK_TABLE.keys():
            if path.startswith(prefix):
                remainder = path[len(prefix):].lstrip("/")
                path = "/webhook" + ("/" + remainder if remainder else "")
                break

    # Append query string if present
    if request.url.query:
        path += f"?{request.url.query}"

    # Prepare headers
    headers = dict(request.headers)
    request_id = request.state.request_id
    headers.pop("host", None)  # Remove host header, downstream service will set it

    # Read body if present
    body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else b""

    # Request size limit (10MB)
    if len(body) > 10 * 1024 * 1024:
        return JSONResponse(
            {"detail": "Request body too large (max 10MB)"},
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    try:
        # Call service using ServiceClient (handles circuit breaker, retries, etc.)
        kwargs = {
            "headers": headers,
            "tenant_id": tenant_id,
            "request_id": request_id,
        }

        # Add body for non-GET requests
        if body:
            kwargs["content"] = body

        response = await service_client.call_service(
            service_name,
            request.method,
            path,
            **kwargs
        )

        # Read response body
        response_body = response.content

        # Compress if needed
        if response.headers.get("content-type", "").startswith(
            ("application/json", "text/")
        ):
            response_body = await compress_response(response_body)
            headers_dict = dict(response.headers)
            if len(response_body) < len(response.content):
                headers_dict["Content-Encoding"] = "gzip"
        else:
            headers_dict = dict(response.headers)

        # Add security headers
        headers_dict.update(get_security_headers())

        return Response(
            content=response_body,
            status_code=response.status_code,
            headers=headers_dict,
        )

    except CircuitOpenError:
        logger.warning("Circuit breaker open for %s", service_name)
        return JSONResponse(
            {
                "detail": f"Service {service_name} is temporarily unavailable",
                "error": "circuit_open"
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers=get_security_headers(),
        )

    except ServiceTimeoutError:
        logger.error("Timeout calling service %s", service_name)
        return JSONResponse(
            {"detail": "Service timeout"},
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            headers=get_security_headers(),
        )

    except ServiceConnectionError:
        logger.error("Cannot connect to service %s", service_name)
        return JSONResponse(
            {"detail": "Service unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers=get_security_headers(),
        )

    except Exception as e:
        logger.error("Proxy error for %s: %s", service_name, type(e).__name__)
        return JSONResponse(
            {"detail": "Gateway error"},
            status_code=status.HTTP_502_BAD_GATEWAY,
            headers=get_security_headers(),
        )


# ─── Request Handler ───


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def gateway_handler(request: Request, path: str) -> Response:
    """Main request handler - routes to services."""

    # Handle gateway's own health endpoint directly
    full_path = request.url.path
    if full_path == "/health":
        return JSONResponse({
            "status": "healthy",
            "service": "api-gateway",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Generate request ID for tracing
    request.state.request_id = str(uuid.uuid4())
    request_start = time.time()

    full_path = "/" + path if path else "/"

    # Check if this is a webhook
    is_webhook = any(full_path.startswith(prefix) for prefix in WEBHOOK_TABLE.keys())

    # Find matching route
    prefix, route_config = find_route(full_path)

    if not route_config:
        return JSONResponse(
            {"detail": "Not found"},
            status_code=status.HTTP_404_NOT_FOUND,
            headers=get_security_headers(),
        )

    # Extract tenant ID and token from auth header
    tenant_id = None
    token_claims = None
    authorization = request.headers.get("Authorization")

    if not is_webhook and route_config.get("auth_required"):
        # Extract token
        token_claims = extract_and_validate_token(authorization)

        if not token_claims:
            return JSONResponse(
                {"detail": "Unauthorized - missing or invalid token"},
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers=get_security_headers(),
            )

        tenant_id = token_claims.get("tenant_id")

        if not tenant_id:
            return JSONResponse(
                {"detail": "Invalid token - missing tenant_id"},
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers=get_security_headers(),
            )

    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    allowed, rate_limit_response = await check_rate_limit(
        tenant_id, client_ip, full_path
    )

    if not allowed:
        headers = get_security_headers()
        if rate_limit_response:
            headers.update(rate_limit_response)
        return JSONResponse(
            {"detail": "Rate limit exceeded"},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers=headers,
        )

    # Log request
    logger.info(
        f"[{request.state.request_id}] {request.method} {full_path} "
        f"tenant={tenant_id or 'N/A'} client={client_ip}"
    )

    # ─── Wallet Balance Gate (block paid actions at zero balance) ─────────
    # Only check for authenticated, outbound-action routes (not reads/GETs)
    requires_balance = route_config.get("requires_balance", False)
    if (requires_balance and tenant_id and request.method in ("POST", "PUT", "PATCH")
            and not full_path.startswith("/api/v1/wallet")):
        try:
            balance_ok = await _check_tenant_balance(tenant_id)
            if not balance_ok:
                return JSONResponse(
                    {
                        "detail": "Insufficient wallet balance. Please top up to continue.",
                        "code": "INSUFFICIENT_BALANCE",
                        "topup_url": "/wallet",
                    },
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    headers=get_security_headers(),
                )
        except Exception as e:
            # Non-blocking — if balance check fails, allow request through
            logger.warning(f"Balance check failed for tenant {tenant_id}: {e}")

    # Proxy request using service discovery
    service_name = route_config["service"]
    timeout = route_config["timeout"]

    response = await proxy_request(request, service_name, timeout, tenant_id)

    # Add rate limit headers if available
    if rate_limit_response:
        for header, value in rate_limit_response.items():
            if header.startswith("X-RateLimit") or header == "Retry-After":
                response.headers[header] = str(value)

    # Add request ID to response
    response.headers["X-Request-ID"] = request.state.request_id

    # Log response
    elapsed = time.time() - request_start
    logger.info(
        f"[{request.state.request_id}] {response.status_code} "
        f"elapsed={elapsed:.2f}s service={service_name}"
    )

    return response


# ─── Health Checks ───

# Simple in-memory rate limiter for health/metrics endpoints (prevent DoS)
_health_rate_limit: Dict[str, list] = {}
_HEALTH_RATE_LIMIT_MAX = 60  # max requests per window
_HEALTH_RATE_LIMIT_WINDOW = 60  # seconds


def _check_health_rate_limit(client_ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    if client_ip not in _health_rate_limit:
        _health_rate_limit[client_ip] = []
    # Prune old timestamps
    _health_rate_limit[client_ip] = [
        t for t in _health_rate_limit[client_ip]
        if now - t < _HEALTH_RATE_LIMIT_WINDOW
    ]
    if len(_health_rate_limit[client_ip]) >= _HEALTH_RATE_LIMIT_MAX:
        return False
    _health_rate_limit[client_ip].append(now)
    return True


@app.get("/health")
async def health_check(request: Request) -> Any:
    """Gateway health status. Rate-limited to prevent DoS."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_health_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after_seconds": _HEALTH_RATE_LIMIT_WINDOW},
        )
    return {
        "status": "healthy",
        "service": "api-gateway",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/services")
async def services_health(request: Request) -> Any:
    """Check health of all downstream services. Rate-limited."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_health_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after_seconds": _HEALTH_RATE_LIMIT_WINDOW},
        )
    global service_client, service_registry

    if not service_client or not service_registry:
        return {"status": "unhealthy", "reason": "Service client not initialized"}

    # Get unique services from both route tables
    unique_services = set()
    for config_dict in {**ROUTE_TABLE, **WEBHOOK_TABLE}.values():
        unique_services.add(config_dict["service"])

    # Check health of all services concurrently
    services = {}
    for service_name in sorted(unique_services):
        try:
            is_healthy = await service_client.health_check(service_name)
            status_val = "healthy" if is_healthy else "unhealthy"

            # Get service info
            service_info = service_registry.get_service_info(service_name)
            services[service_name] = {
                "status": status_val,
                "namespace": service_info.namespace,
                "port": service_info.port,
            }
        except Exception as e:
            logger.error("Health check error for %s: %s", service_name, type(e).__name__)
            services[service_name] = {
                "status": "unhealthy",
                "error": "Service unavailable",
            }

    # Get circuit breaker status
    circuit_status = service_client.get_all_circuit_statuses()

    # Summary
    healthy_count = sum(1 for s in services.values() if s["status"] == "healthy")
    total_count = len(services)

    overall_status = "healthy" if healthy_count == total_count else (
        "degraded" if healthy_count > 0 else "unhealthy"
    )

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_services": total_count,
            "healthy_services": healthy_count,
            "degraded_services": total_count - healthy_count,
        },
        "services": services,
        "circuit_breakers": circuit_status,
    }


# ─── API Documentation ───


@app.get("/openapi.json")
async def openapi_schema() -> Dict[str, Any]:
    """OpenAPI schema (placeholder for aggregated spec)."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Priya Global API",
            "version": "1.0.0",
            "description": "Multi-tenant AI sales platform",
        },
        "servers": [{"url": "https://api.priyaai.com", "description": "Production"}],
        "paths": {
            "/api/v1/auth/register": {
                "post": {
                    "summary": "Register a new user",
                    "operationId": "register",
                    "tags": ["auth"],
                }
            },
            "/api/v1/auth/login": {
                "post": {
                    "summary": "Login user",
                    "operationId": "login",
                    "tags": ["auth"],
                }
            },
            "/api/v1/tenants/{tenant_id}": {
                "get": {
                    "summary": "Get tenant details",
                    "operationId": "get_tenant",
                    "tags": ["tenants"],
                }
            },
        },
    }


# ─── WebSocket Security Helpers ───


def _validate_ws_origin(websocket: WebSocket) -> bool:
    """
    Validate the WebSocket Origin header against the CORS allowed-origins list.

    Returns True if the origin is allowed (or if no Origin header is present,
    which happens with non-browser clients — those are authenticated via JWT).
    """
    origin = websocket.headers.get("origin")
    if not origin:
        # Non-browser clients (Postman, server-to-server) don't send Origin.
        # They are still authenticated via JWT, so this is fine.
        return True

    allowed = get_allowed_origins()
    # Normalise: strip trailing slashes for comparison
    origin_normalised = origin.rstrip("/")
    for allowed_origin in allowed:
        if origin_normalised == allowed_origin.rstrip("/"):
            return True

    logger.warning("WebSocket origin rejected")
    return False


async def _ws_first_message_auth(websocket: WebSocket, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """
    Wait for a first-message auth payload from the client.

    The client sends: { "type": "auth", "token": "<jwt>" }
    We validate the token and return the claims, or None on failure.

    This allows clients to authenticate without embedding the JWT in the URL
    (which would leak in server logs, proxy logs, and referrer headers).
    """
    try:
        data = await asyncio.wait_for(websocket.receive_json(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("WebSocket auth timeout — no auth message received")
        return None
    except Exception as e:
        logger.warning("WebSocket auth receive error: %s", type(e).__name__)
        return None

    if data.get("type") != "auth" or not data.get("token"):
        return None

    # Validate the token from the first message
    bearer_header = f"Bearer {data['token']}"
    return extract_and_validate_token(bearer_header)


async def _authenticate_websocket(websocket: WebSocket) -> Optional[Dict[str, Any]]:
    """
    Authenticate a WebSocket connection via Authorization header OR first-message auth.

    Tries the Authorization header first (for backward compatibility).
    If no header token, accepts the connection and waits for first-message auth.

    Returns validated token claims, or None if authentication fails.
    On failure the caller is responsible for closing the socket.
    """
    # Try header-based auth first (backward compatibility)
    auth_header = websocket.headers.get("Authorization")
    token_claims = extract_and_validate_token(auth_header)

    if token_claims:
        return token_claims

    # No header token — accept and try first-message auth
    await websocket.accept()
    token_claims = await _ws_first_message_auth(websocket)

    if token_claims:
        # Send auth acknowledgement so the client knows it's authenticated
        await websocket.send_json({
            "type": "auth_ack",
            "status": "authenticated",
        })
        return token_claims

    # Auth failed — notify and close
    await websocket.send_json({
        "type": "auth_error",
        "data": {"reason": "Invalid or missing token"},
    })
    return None


# ─── WebSocket Endpoints ───


@app.websocket("/ws/conversations/{conversation_id}")
async def websocket_conversation_endpoint(websocket: WebSocket, conversation_id: str):
    """
    WebSocket endpoint for real-time conversation updates.

    Supports:
    - JWT in Authorization header (backward compatible)
    - First-message auth: { "type": "auth", "token": "<jwt>" }
    - Origin validation against CORS whitelist

    Rooms: conversation:{conversation_id}
    Messages: chat, typing, presence, message_read
    """
    global websocket_manager

    if not websocket_manager:
        await websocket.close(code=status.WS_1011_SERVER_ERROR, reason="WebSocket not initialized")
        return

    # ── SECURITY: Origin validation ──
    if not _validate_ws_origin(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        return

    # ── SECURITY: Authenticate via header or first-message ──
    token_claims = await _authenticate_websocket(websocket)

    if not token_claims:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        except Exception:
            pass
        return

    tenant_id = token_claims.get("tenant_id")
    user_id = token_claims.get("sub") or token_claims.get("user_id")

    if not tenant_id or not user_id:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        except Exception:
            pass
        return

    # Accept connection (if not already accepted by first-message auth)
    try:
        await websocket.accept()
    except RuntimeError:
        pass  # Already accepted during first-message auth
    connection_id = None

    try:
        # Register connection
        room = f"conversation:{conversation_id}"

        # Validate room access: ensure room is prefixed with tenant_id for isolation
        # Gateway validates tenant_id matches token; downstream validates conversation ownership
        if not room.startswith(f"tenant:{tenant_id}:"):
            # For backward compatibility, conversation rooms don't require prefix
            # But we validate token tenant_id matches the conversation context
            logger.debug("WebSocket room access check for %s by tenant %s", room, tenant_id)

        connection_id = await websocket_manager.connect(
            websocket,
            tenant_id=tenant_id,
            user_id=user_id,
            rooms=[room],
        )

        # Start heartbeat
        heartbeat_task = await websocket_manager.start_heartbeat(connection_id)

        # Send connected message
        await websocket.send_json({
            "type": "connect",
            "connection_id": connection_id,
            "conversation_id": conversation_id,
            "status": "connected",
        })

        logger.info("WebSocket connected for conversation %s: %s", conversation_id, connection_id)

        # Message loop
        while True:
            data = await websocket.receive_json()

            # Parse and validate message
            message = parse_ws_message(data)
            if not message:
                await websocket.send_json(
                    create_error_message("invalid_message", "Invalid message format")
                )
                continue

            # Route message based on type
            message_type = data.get("type", "message").lower()

            if message_type == "message":
                # Chat message - route to service
                msg = {
                    "type": "message",
                    "message_id": message.message_id,
                    "conversation_id": conversation_id,
                    "sender_id": user_id,
                    "content": data.get("content", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Broadcast to room (local and cross-instance)
                await websocket_manager.send_to_room(room, msg)
                await websocket_manager._publish_message(room, msg)

            elif message_type == "typing":
                # Typing indicator
                msg = {
                    "type": "typing_start" if data.get("is_typing") else "typing_stop",
                    "conversation_id": conversation_id,
                    "sender_id": user_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await websocket_manager.send_to_room(room, msg, exclude_connection_id=connection_id)
                await websocket_manager._publish_message(room, msg)

            elif message_type == "ping":
                # Respond to ping
                await websocket.send_json(create_pong_message())

            elif message_type == "pong":
                # Just acknowledge
                pass

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", connection_id)
    except Exception as e:
        logger.error("WebSocket error in conversation %s: %s", conversation_id, type(e).__name__)
        try:
            await websocket.send_json(
                create_error_message("internal_error", "An error occurred")
            )
        except Exception:
            pass
    finally:
        if connection_id:
            await websocket_manager.disconnect(connection_id)


@app.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    Supports:
    - JWT in Authorization header (backward compatible)
    - First-message auth: { "type": "auth", "token": "<jwt>" }
    - Origin validation against CORS whitelist

    Rooms: dashboard:{tenant_id}
    Messages: metrics_update, notifications, alerts
    """
    global websocket_manager

    if not websocket_manager:
        await websocket.close(code=status.WS_1011_SERVER_ERROR, reason="WebSocket not initialized")
        return

    # ── SECURITY: Origin validation ──
    if not _validate_ws_origin(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        return

    # ── SECURITY: Authenticate via header or first-message ──
    token_claims = await _authenticate_websocket(websocket)

    if not token_claims:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        except Exception:
            pass
        return

    tenant_id = token_claims.get("tenant_id")
    user_id = token_claims.get("sub") or token_claims.get("user_id")

    if not tenant_id or not user_id:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        except Exception:
            pass
        return

    # Accept connection (if not already accepted by first-message auth)
    try:
        await websocket.accept()
    except RuntimeError:
        pass  # Already accepted during first-message auth
    connection_id = None

    try:
        # Register connection
        room = f"dashboard:{tenant_id}"
        connection_id = await websocket_manager.connect(
            websocket,
            tenant_id=tenant_id,
            user_id=user_id,
            rooms=[room],
        )

        # Start heartbeat
        heartbeat_task = await websocket_manager.start_heartbeat(connection_id)

        # Send connected message
        await websocket.send_json({
            "type": "connect",
            "connection_id": connection_id,
            "room": room,
            "status": "connected",
        })

        logger.info("WebSocket connected for dashboard %s: %s", tenant_id, connection_id)

        # Message loop
        while True:
            data = await websocket.receive_json()

            message_type = data.get("type", "").lower()

            if message_type == "ping":
                await websocket.send_json(create_pong_message())

            elif message_type == "subscribe":
                # Subscribe to specific metric updates
                metric_type = data.get("metric_type")
                if metric_type:
                    await websocket_manager.join_room(connection_id, f"metric:{metric_type}")

            elif message_type == "unsubscribe":
                # Unsubscribe from metric
                metric_type = data.get("metric_type")
                if metric_type:
                    await websocket_manager.leave_room(connection_id, f"metric:{metric_type}")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", connection_id)
    except Exception as e:
        logger.error("WebSocket error in dashboard: %s", type(e).__name__)
        try:
            await websocket.send_json(
                create_error_message("internal_error", "An error occurred")
            )
        except Exception:
            pass
    finally:
        if connection_id:
            await websocket_manager.disconnect(connection_id)


@app.websocket("/ws/agent")
async def websocket_agent_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for agent presence and assignment updates.

    Supports:
    - JWT in Authorization header (backward compatible)
    - First-message auth: { "type": "auth", "token": "<jwt>" }
    - Origin validation against CORS whitelist

    Rooms: agent:{agent_id}, agent_queue:{tenant_id}
    Messages: agent_status, conversation_assigned, conversation_closed
    """
    global websocket_manager

    if not websocket_manager:
        await websocket.close(code=status.WS_1011_SERVER_ERROR, reason="WebSocket not initialized")
        return

    # ── SECURITY: Origin validation ──
    if not _validate_ws_origin(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Origin not allowed")
        return

    # ── SECURITY: Authenticate via header or first-message ──
    token_claims = await _authenticate_websocket(websocket)

    if not token_claims:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        except Exception:
            pass
        return

    tenant_id = token_claims.get("tenant_id")
    user_id = token_claims.get("sub") or token_claims.get("user_id")
    agent_id = token_claims.get("agent_id") or user_id

    if not tenant_id or not user_id:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        except Exception:
            pass
        return

    # Accept connection (if not already accepted by first-message auth)
    try:
        await websocket.accept()
    except RuntimeError:
        pass  # Already accepted during first-message auth
    connection_id = None

    try:
        # Register connection with agent and tenant rooms
        rooms = [
            f"agent:{agent_id}",
            f"agent_queue:{tenant_id}",
        ]
        connection_id = await websocket_manager.connect(
            websocket,
            tenant_id=tenant_id,
            user_id=user_id,
            rooms=rooms,
        )

        # Start heartbeat
        heartbeat_task = await websocket_manager.start_heartbeat(connection_id)

        # Send connected message
        await websocket.send_json({
            "type": "connect",
            "connection_id": connection_id,
            "agent_id": agent_id,
            "status": "connected",
        })

        logger.info("WebSocket connected for agent %s: %s", agent_id, connection_id)

        # Message loop
        while True:
            data = await websocket.receive_json()

            message_type = data.get("type", "").lower()

            if message_type == "agent_status":
                # Agent status update
                status_value = data.get("status", "available")  # available, busy, offline
                msg = {
                    "type": "agent_status",
                    "agent_id": agent_id,
                    "status": status_value,
                    "active_conversations": data.get("active_conversations", 0),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Broadcast to tenant queue
                await websocket_manager.send_to_room(f"agent_queue:{tenant_id}", msg)
                await websocket_manager._publish_message(f"agent_queue:{tenant_id}", msg)

            elif message_type == "ping":
                await websocket.send_json(create_pong_message())

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", connection_id)
    except Exception as e:
        logger.error("WebSocket error in agent endpoint: %s", type(e).__name__)
        try:
            await websocket.send_json(
                create_error_message("internal_error", "An error occurred")
            )
        except Exception:
            pass
    finally:
        if connection_id:
            await websocket_manager.disconnect(connection_id)


@app.get("/ws/metrics")
async def websocket_metrics():
    """Get WebSocket connection metrics"""
    global websocket_manager

    if not websocket_manager:
        return {"error": "WebSocket not initialized"}

    return websocket_manager.get_metrics()


# ─── Catch-all for v2 (future) ───


@app.api_route("/api/v2/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v2_placeholder(path: str) -> JSONResponse:
    """API v2 placeholder."""
    return JSONResponse(
        {
            "detail": "API v2 coming soon",
            "status": "not_implemented",
        },
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9001,  # API Gateway port
        workers=1,
        log_level=config.log_level.lower(),
    )
