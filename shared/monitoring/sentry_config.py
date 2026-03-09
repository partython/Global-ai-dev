"""
Priya Global Platform — Sentry Integration

Centralized error tracking configuration for all 36 microservices.
Features:
- Environment-aware initialization (dev/staging/production)
- Tenant context injection on every event
- PII scrubbing (emails, passwords, tokens, API keys)
- Custom error fingerprinting for better grouping
- Performance monitoring with configurable sample rates
- Request/response sanitization
- Release tracking with Git SHA
- Graceful degradation (Sentry failure never crashes the service)
"""

import os
import re
import logging
from typing import Any, Dict, Optional, Callable
from functools import wraps

logger = logging.getLogger("priya.sentry")

# PII patterns to scrub
PII_PATTERNS = [
    (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+'), r'\1=***REDACTED***'),
    (re.compile(r'(?i)(token|api[_-]?key|secret|authorization)\s*[=:]\s*\S+'), r'\1=***REDACTED***'),
    (re.compile(r'(?i)(bearer\s+)\S+'), r'\1***REDACTED***'),
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '***EMAIL_REDACTED***'),
    (re.compile(r'(?i)(credit[_-]?card|cc[_-]?num)\s*[=:]\s*\d+'), r'\1=***REDACTED***'),
    (re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'), '***CARD_REDACTED***'),
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '***SSN_REDACTED***'),
    (re.compile(r'\b\d{4}\s?\d{4}\s?\d{4}\b'), '***AADHAR_REDACTED***'),
    (re.compile(r'\b[A-Z]{5}\d{4}[A-Z]\b'), '***PAN_REDACTED***'),
]

# Errors to ignore (noisy, non-actionable)
IGNORED_ERRORS = [
    "ConnectionResetError",
    "BrokenPipeError",
    "asyncio.CancelledError",
    "KeyboardInterrupt",
    "SystemExit",
    "httpx.ReadTimeout",
    "redis.ConnectionError",
]

def _scrub_pii(data: Any) -> Any:
    """Recursively scrub PII from event data."""
    if isinstance(data, str):
        for pattern, replacement in PII_PATTERNS:
            data = pattern.sub(replacement, data)
        return data
    elif isinstance(data, dict):
        return {k: _scrub_pii(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_scrub_pii(item) for item in data]
    return data

def _before_send(event: Dict, hint: Dict) -> Optional[Dict]:
    """Process event before sending to Sentry. Returns None to drop."""
    try:
        # Drop ignored errors
        if "exc_info" in hint:
            exc_type = hint["exc_info"][0]
            if exc_type and exc_type.__name__ in IGNORED_ERRORS:
                return None

        # Check exception value
        exception = event.get("exception", {})
        values = exception.get("values", [])
        for exc in values:
            if exc.get("type") in IGNORED_ERRORS:
                return None

        # Scrub PII from event
        event = _scrub_pii(event)

        # Scrub request data
        request = event.get("request", {})
        if request:
            # Scrub headers
            headers = request.get("headers", {})
            for sensitive in ["authorization", "cookie", "x-api-key", "x-tenant-secret"]:
                if sensitive in headers:
                    headers[sensitive] = "***REDACTED***"

            # Scrub query string
            if "query_string" in request:
                request["query_string"] = _scrub_pii(request["query_string"])

            # Scrub body
            if "data" in request:
                request["data"] = _scrub_pii(request["data"])

        # Add custom fingerprint for better error grouping
        if values:
            exc = values[-1]
            exc_type = exc.get("type", "Unknown")
            exc_value = exc.get("value", "")
            # Group by type + first meaningful line of message
            short_value = exc_value[:100] if exc_value else ""
            event["fingerprint"] = [exc_type, short_value]

        return event
    except Exception:
        # Never let Sentry processing crash the service
        return event

def _before_send_transaction(event: Dict, hint: Dict) -> Optional[Dict]:
    """Filter transactions before sending."""
    try:
        # Drop health check transactions (too noisy)
        transaction_name = event.get("transaction", "")
        if any(path in transaction_name for path in ["/health", "/ready", "/metrics", "/favicon"]):
            return None
        return event
    except Exception:
        return event

def init_sentry(
    service_name: str,
    service_port: Optional[int] = None,
    dsn: Optional[str] = None,
    environment: Optional[str] = None,
    release: Optional[str] = None,
    traces_sample_rate: Optional[float] = None,
    profiles_sample_rate: Optional[float] = None,
    extra_integrations: Optional[list] = None,
    extra_ignore_errors: Optional[list] = None,
) -> bool:
    """
    Initialize Sentry for a microservice.

    Returns True if initialization succeeded, False otherwise.
    Sentry failure NEVER crashes the service.
    """
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration

        # Resolve configuration
        _dsn = dsn or os.getenv("SENTRY_DSN", "")
        _env = environment or os.getenv("ENVIRONMENT", "development")
        _release = release or os.getenv("SENTRY_RELEASE") or os.getenv("GIT_SHA", "unknown")
        _enabled = os.getenv("SENTRY_ENABLED", "true").lower() in ("true", "1", "yes")

        if not _dsn or not _enabled:
            logger.info(f"Sentry disabled for {service_name} (dsn={'set' if _dsn else 'empty'}, enabled={_enabled})")
            return False

        # Environment-specific sample rates
        default_traces_rate = {
            "production": 0.1,
            "staging": 0.5,
            "development": 1.0,
        }.get(_env, 0.1)

        default_profiles_rate = {
            "production": 0.05,
            "staging": 0.25,
            "development": 1.0,
        }.get(_env, 0.05)

        _traces_rate = traces_sample_rate if traces_sample_rate is not None else float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", str(default_traces_rate)))
        _profiles_rate = profiles_sample_rate if profiles_sample_rate is not None else float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", str(default_profiles_rate)))

        # Build integrations
        integrations = [
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
            AsyncioIntegration(),
        ]
        if extra_integrations:
            integrations.extend(extra_integrations)

        # Build ignore list
        ignore_errors = IGNORED_ERRORS.copy()
        if extra_ignore_errors:
            ignore_errors.extend(extra_ignore_errors)

        sentry_sdk.init(
            dsn=_dsn,
            environment=_env,
            release=f"{service_name}@{_release}",
            server_name=f"{service_name}:{service_port or 'unknown'}",
            traces_sample_rate=_traces_rate,
            profiles_sample_rate=_profiles_rate,
            before_send=_before_send,
            before_send_transaction=_before_send_transaction,
            integrations=integrations,
            ignore_errors=ignore_errors,
            send_default_pii=False,
            attach_stacktrace=True,
            include_local_variables=_env != "production",
            max_breadcrumbs=50,
            debug=_env == "development",
            enable_tracing=True,
        )

        # Set global tags
        sentry_sdk.set_tag("service", service_name)
        sentry_sdk.set_tag("service.port", str(service_port or "unknown"))
        sentry_sdk.set_tag("platform", "priya-global")

        logger.info(f"Sentry initialized for {service_name} (env={_env}, traces={_traces_rate}, profiles={_profiles_rate})")
        return True

    except Exception as e:
        logger.warning(f"Sentry initialization failed for {service_name}: {e}. Service will continue without error tracking.")
        return False

def set_tenant_context(tenant_id: str, tenant_name: Optional[str] = None, plan: Optional[str] = None):
    """Set tenant context on the current Sentry scope."""
    try:
        import sentry_sdk
        sentry_sdk.set_tag("tenant.id", tenant_id)
        if tenant_name:
            sentry_sdk.set_tag("tenant.name", tenant_name)
        if plan:
            sentry_sdk.set_tag("tenant.plan", plan)
        sentry_sdk.set_user({"id": tenant_id, "username": tenant_name or tenant_id})
    except Exception:
        pass

def capture_exception(error: Exception, extra: Optional[Dict] = None, tags: Optional[Dict] = None):
    """Safely capture an exception to Sentry with optional context."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if extra:
                for key, value in extra.items():
                    scope.set_extra(key, value)
            if tags:
                for key, value in tags.items():
                    scope.set_tag(key, value)
            sentry_sdk.capture_exception(error)
    except Exception:
        logger.debug(f"Failed to capture exception to Sentry: {error}")

def capture_message(message: str, level: str = "info", extra: Optional[Dict] = None):
    """Safely capture a message to Sentry."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if extra:
                for key, value in extra.items():
                    scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass

def sentry_trace(op: str, description: Optional[str] = None):
    """Decorator to create a Sentry transaction span for a function."""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                import sentry_sdk
                with sentry_sdk.start_span(op=op, description=description or func.__name__):
                    return await func(*args, **kwargs)
            except ImportError:
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                import sentry_sdk
                with sentry_sdk.start_span(op=op, description=description or func.__name__):
                    return func(*args, **kwargs)
            except ImportError:
                return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


class SentryMiddleware:
    """
    FastAPI middleware that injects tenant context into Sentry scope.

    Usage:
        app.add_middleware(SentryMiddleware)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        try:
            import sentry_sdk

            # Extract tenant_id from headers or path
            headers = dict(scope.get("headers", []))
            tenant_id = None

            # Check X-Tenant-ID header (set by gateway)
            for key, value in headers.items():
                if key == b"x-tenant-id":
                    tenant_id = value.decode("utf-8")
                    break

            if tenant_id:
                sentry_sdk.set_tag("tenant.id", tenant_id)
                sentry_sdk.set_user({"id": tenant_id})

            # Set request context
            path = scope.get("path", "unknown")
            method = scope.get("method", "unknown")
            sentry_sdk.set_tag("http.route", path)
            sentry_sdk.set_tag("http.method", method)

        except Exception:
            pass

        await self.app(scope, receive, send)
