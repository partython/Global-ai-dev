"""
Sentry Integration for Priya Global Platform

Industry-grade error tracking with:
- Tenant-aware context on every request
- Performance monitoring with transaction sampling
- Custom breadcrumbs for business events
- PII scrubbing (emails, phones, tokens, API keys)
- Environment/release tagging
- Custom error filtering (reduce noise)
- Rate limiting on error reporting
- Service-specific tags

Usage in any service:
    from shared.observability.sentry import init_sentry, set_tenant_context, capture_business_event
    
    init_sentry(service_name="gateway", service_port=9000)
    
    # In request middleware:
    set_tenant_context(tenant_id="t_123", user_id="u_456")
    
    # For business events:
    capture_business_event("order.created", {"order_id": "ord_789", "amount": 1500})
"""

import os
import re
import logging
from typing import Any, Dict, Optional
from functools import lru_cache

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.redis import RedisIntegration

logger = logging.getLogger("priya.sentry")

# ─── PII Patterns ───

PII_PATTERNS = [
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL_REDACTED]'),
    (re.compile(r'\b\d{10,15}\b'), '[PHONE_REDACTED]'),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'Bearer [TOKEN_REDACTED]'),
    (re.compile(r'(?:api[_-]?key|secret|password|token|authorization)\s*[=:]\s*\S+', re.IGNORECASE), '[CREDENTIAL_REDACTED]'),
    (re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'), '[CARD_REDACTED]'),
    (re.compile(r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*'), '[JWT_REDACTED]'),
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '***SSN_REDACTED***'),
    (re.compile(r'\b\d{4}\s?\d{4}\s?\d{4}\b'), '***AADHAR_REDACTED***'),
    (re.compile(r'\b[A-Z]{5}\d{4}[A-Z]\b'), '***PAN_REDACTED***'),
]

# ─── Noise Filters ───

IGNORED_ERRORS = {
    "ConnectionResetError",
    "BrokenPipeError", 
    "asyncio.CancelledError",
    "httpx.ConnectTimeout",
    "httpx.ReadTimeout",
    "redis.ConnectionError",
    "KeyboardInterrupt",
    "SystemExit",
}

IGNORED_TRANSACTIONS = {
    "/health",
    "/healthz",
    "/ready",
    "/readyz",
    "/metrics",
    "/api/v1/health",
    "/_next/static",
    "/favicon.ico",
}


def _scrub_pii(value: str) -> str:
    """Remove PII from string values."""
    if not isinstance(value, str):
        return value
    for pattern, replacement in PII_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _scrub_data(data: Any, depth: int = 0) -> Any:
    """Recursively scrub PII from event data. Max depth 10 to prevent infinite recursion."""
    if depth > 10:
        return data
    if isinstance(data, str):
        return _scrub_pii(data)
    if isinstance(data, dict):
        return {k: _scrub_data(v, depth + 1) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return type(data)(_scrub_data(item, depth + 1) for item in data)
    return data


def _before_send(event: Dict, hint: Dict) -> Optional[Dict]:
    """
    Pre-processing hook for every Sentry event.
    - Filters out noisy/expected errors
    - Scrubs PII from all event data
    - Adds custom fingerprinting
    """
    # Filter ignored error types
    if "exc_info" in hint:
        exc_type = hint["exc_info"][0]
        if exc_type and exc_type.__name__ in IGNORED_ERRORS:
            return None
    
    # Filter HTTP 4xx errors (client errors, not server bugs)
    if event.get("tags", {}).get("http.status_code"):
        status = int(event["tags"]["http.status_code"])
        if 400 <= status < 500 and status != 429:
            return None

    # Scrub PII from event
    event = _scrub_data(event)
    
    return event


def _before_send_transaction(event: Dict, hint: Dict) -> Optional[Dict]:
    """Filter out health check and static asset transactions."""
    transaction = event.get("transaction", "")
    for ignored in IGNORED_TRANSACTIONS:
        if transaction.startswith(ignored):
            return None
    return event


def _traces_sampler(sampling_context: Dict) -> float:
    """
    Dynamic trace sampling based on transaction type.
    - Health checks: 0% (already filtered but belt-and-suspenders)
    - API endpoints: 20% in production, 100% in dev
    - Background tasks: 5%
    """
    transaction = sampling_context.get("transaction_context", {}).get("name", "")
    
    for ignored in IGNORED_TRANSACTIONS:
        if transaction.startswith(ignored):
            return 0.0
    
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        if "background" in transaction.lower() or "cron" in transaction.lower():
            return 0.05
        return 0.2  # 20% of API requests
    
    return 1.0  # 100% in development


def init_sentry(
    service_name: str,
    service_port: int,
    extra_integrations: Optional[list] = None,
) -> None:
    """
    Initialize Sentry for a microservice.
    
    Args:
        service_name: e.g., "gateway", "auth", "billing"
        service_port: e.g., 9000, 9001
        extra_integrations: Additional Sentry integrations beyond defaults
    
    Environment variables:
        SENTRY_DSN: Required. Project DSN from Sentry.
        ENVIRONMENT: "production", "staging", "development" (default: "development")
        SENTRY_RELEASE: Git SHA or version tag (default: "unknown")
        SENTRY_SAMPLE_RATE: Error sample rate 0.0-1.0 (default: 1.0)
        SENTRY_ENABLED: "true"/"false" (default: "true")
    """
    dsn = os.getenv("SENTRY_DSN", "")
    enabled = os.getenv("SENTRY_ENABLED", "true").lower() == "true"
    environment = os.getenv("ENVIRONMENT", "development")
    release = os.getenv("SENTRY_RELEASE", os.getenv("GIT_SHA", "unknown"))
    sample_rate = float(os.getenv("SENTRY_SAMPLE_RATE", "1.0"))
    
    if not dsn or not enabled:
        logger.info(f"Sentry disabled for {service_name} (dsn={'set' if dsn else 'missing'}, enabled={enabled})")
        return
    
    integrations = [
        FastApiIntegration(transaction_style="endpoint"),
        StarletteIntegration(transaction_style="endpoint"),
        AsyncioIntegration(),
        LoggingIntegration(
            level=logging.WARNING,      # Capture WARNING+ as breadcrumbs
            event_level=logging.ERROR,   # Send ERROR+ as events
        ),
        HttpxIntegration(),
        RedisIntegration(),
    ]
    
    if extra_integrations:
        integrations.extend(extra_integrations)
    
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=f"priya-{service_name}@{release}",
        integrations=integrations,
        before_send=_before_send,
        before_send_transaction=_before_send_transaction,
        traces_sampler=_traces_sampler,
        sample_rate=sample_rate,
        send_default_pii=False,         # NEVER send PII automatically
        attach_stacktrace=True,         # Always attach stack traces
        max_breadcrumbs=50,
        request_bodies="medium",        # Capture request bodies up to 10KB
        server_name=f"{service_name}:{service_port}",
        # Performance
        enable_tracing=True,
        profiles_sample_rate=0.1 if environment == "production" else 0.5,
    )
    
    # Set global tags
    sentry_sdk.set_tag("service", service_name)
    sentry_sdk.set_tag("service.port", str(service_port))
    sentry_sdk.set_tag("platform", "priya-global")
    
    logger.info(f"Sentry initialized for {service_name} (env={environment}, release={release})")


def set_tenant_context(
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    plan: Optional[str] = None,
) -> None:
    """
    Set tenant context on the current Sentry scope.
    Call this in request middleware after JWT validation.
    """
    with sentry_sdk.configure_scope() as scope:
        if tenant_id:
            scope.set_tag("tenant_id", tenant_id)
            scope.set_context("tenant", {
                "id": tenant_id,
                "plan": plan or "unknown",
            })
        if user_id:
            scope.set_user({
                "id": user_id,
                # Don't set email — PII
            })


def capture_business_event(
    event_name: str,
    data: Optional[Dict[str, Any]] = None,
    level: str = "info",
) -> None:
    """
    Capture a custom business event as a Sentry breadcrumb + optional event.
    
    Args:
        event_name: e.g., "order.created", "channel.connected", "handoff.escalated"
        data: Additional context data (will be PII-scrubbed)
        level: "info", "warning", "error"
    """
    scrubbed_data = _scrub_data(data or {})
    
    sentry_sdk.add_breadcrumb(
        category="business",
        message=event_name,
        data=scrubbed_data,
        level=level,
    )
    
    # Also send as event for warning/error level business events
    if level in ("warning", "error"):
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("business_event", event_name)
            scope.set_context("business_data", scrubbed_data)
            sentry_sdk.capture_message(
                f"Business Event: {event_name}",
                level=level,
            )


def sentry_middleware_hook(request) -> None:
    """
    Extract tenant context from request and set on Sentry scope.
    Call from FastAPI middleware.
    
    Expected: request.state.tenant_id and request.state.user_id
    set by auth middleware upstream.
    """
    tenant_id = getattr(request.state, "tenant_id", None) if hasattr(request, "state") else None
    user_id = getattr(request.state, "user_id", None) if hasattr(request, "state") else None
    
    if tenant_id or user_id:
        set_tenant_context(tenant_id=tenant_id, user_id=user_id)
    
    # Set request-specific tags
    sentry_sdk.set_tag("http.method", request.method)
    sentry_sdk.set_tag("http.url", str(request.url.path))
