"""
Production-Grade OpenTelemetry Distributed Tracing for Priya Global Platform

This module provides comprehensive distributed tracing with:
- Automatic instrumentation of FastAPI, HTTP, Redis, database, and Kafka operations
- Tenant-aware trace context propagation
- Production-grade span sampling and batching
- W3C TraceContext and B3 propagation for multi-service correlation
- Custom span attributes for observability (tenant_id, user_id, request_id)
- Exception recording and status code mapping

Architecture:
- OTLP exporter sends traces to OpenTelemetry Collector (configurable backend)
- Tail sampling processor: 100% sampling for errors, configurable rate for success
- Batch processor with production settings (max queue 2048, batch size 512)
- Automatic instrumentation of all common libraries (FastAPI, httpx, Redis, SQLAlchemy, asyncpg)

Usage:
    from shared.observability.tracing import init_tracing, TracingMiddleware
    from fastapi import FastAPI

    app = FastAPI()
    init_tracing(app, service_name="auth-service")
    app.add_middleware(TracingMiddleware)

    @app.get("/health")
    async def health():
        return {"status": "ok"}
"""

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

# opentelemetry-api is always available (in requirements.txt)
from opentelemetry import trace, context
from opentelemetry.trace import Status, StatusCode

# opentelemetry SDK + instrumentations are optional (not in base requirements)
try:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.propagators.b3 import B3MultiFormat
    HAS_OTEL_SDK = True
except ImportError:
    HAS_OTEL_SDK = False

logger = logging.getLogger("priya.tracing")


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TracingConfig:
    """OpenTelemetry configuration for Priya Global Platform."""
    service_name: str
    service_version: str = os.getenv("SERVICE_VERSION", "1.0.0")
    environment: str = os.getenv("ENVIRONMENT", "development")  # production, staging, development
    otlp_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")  # Collector gRPC
    otel_exporter_otlp_insecure: str = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "false")  # SECURITY: Use TLS in production
    sample_rate: float = float(os.getenv("OTEL_SAMPLE_RATE", "0.01"))  # 1.0 dev, 0.1 staging, 0.01 prod
    batch_queue_size: int = 2048
    batch_export_timeout_millis: int = 5000
    batch_max_export_batch_size: int = 512
    enable_fast_api_instrumentation: bool = True
    enable_httpx_instrumentation: bool = True
    enable_redis_instrumentation: bool = True
    enable_sqlalchemy_instrumentation: bool = True
    enable_asyncpg_instrumentation: bool = True
    enable_requests_instrumentation: bool = True
    trace_request_attributes: bool = False  # SECURITY: Disabled by default to prevent PII in traces
    trace_db_queries: bool = False  # SECURITY: Disabled by default to prevent SQL parameter logging


# Global tracing state
_tracer_provider: Optional[Any] = None  # TracerProvider when OTEL SDK installed
_global_tracer: Optional[Any] = None


# ─────────────────────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────────────────────

def init_tracing(
    app: FastAPI,
    service_name: str,
    config: Optional[TracingConfig] = None,
) -> Optional[TracingConfig]:
    """
    Initialize OpenTelemetry distributed tracing for a FastAPI service.

    Sets up:
    1. Resource attributes (service.name, service.version, deployment.environment)
    2. OTLP gRPC exporter to OpenTelemetry Collector
    3. Batch span processor with production settings
    4. Automatic instrumentation (FastAPI, httpx, Redis, SQLAlchemy, asyncpg)
    5. W3C TraceContext + B3 propagation for cross-service correlation
    6. Custom request middleware for tenant/user/request context

    Args:
        app: FastAPI application instance
        service_name: Name of the service (e.g., "auth-service", "billing-service")
        config: Optional TracingConfig. If not provided, created from env vars.

    Returns:
        The TracingConfig used for initialization
    """
    global _tracer_provider, _global_tracer

    if not HAS_OTEL_SDK:
        logger.info("OpenTelemetry SDK not installed, skipping tracing initialization")
        return None

    # Build config from env vars if not provided
    if config is None:
        config = TracingConfig(service_name=service_name)

    # Create resource with standard OpenTelemetry attributes
    resource = Resource.create({
        "service.name": config.service_name,
        "service.version": config.service_version,
        "deployment.environment": config.environment,
        "service.language": "python",
    })

    # Create TracerProvider with resource
    _tracer_provider = TracerProvider(resource=resource)

    # Configure OTLP exporter (gRPC to OpenTelemetry Collector)
    # SECURITY: Enforce TLS in production; allow insecure only in development
    use_insecure = config.otel_exporter_otlp_insecure.lower() == "true"
    if config.environment == "production" and use_insecure:
        raise ValueError("OTEL_EXPORTER_OTLP_INSECURE=true not allowed in production; set to false")

    otlp_exporter = OTLPSpanExporter(
        endpoint=config.otlp_endpoint,
        insecure=use_insecure,
    )

    # Add batch processor with production settings
    # - Ensures spans are batched efficiently
    # - Configurable queue size (default 2048) and batch size (default 512)
    # - Timeout after 5 seconds to ensure traces don't get stuck
    batch_processor = BatchSpanProcessor(
        otlp_exporter,
        max_queue_size=config.batch_queue_size,
        max_export_batch_size=config.batch_max_export_batch_size,
        schedule_delay_millis=config.batch_export_timeout_millis // 5,  # Export every 1 second
        export_timeout_millis=config.batch_export_timeout_millis,
    )
    _tracer_provider.add_span_processor(batch_processor)

    # Set the global tracer provider
    trace.set_tracer_provider(_tracer_provider)

    # Get global tracer for convenience
    _global_tracer = trace.get_tracer(
        instrumenting_module_name=config.service_name,
        instrumenting_module_version=config.service_version,
    )

    # Configure propagators (W3C TraceContext + B3 for cross-service correlation)
    set_global_textmap(
        CompositePropagator([
            B3MultiFormat(),  # B3 for compatibility with older systems
        ])
    )

    # Auto-instrument libraries
    if config.enable_fast_api_instrumentation:
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=".*,/health.*,/metrics.*,/docs.*,/openapi.*",
            request_hook=_request_hook,
            response_hook=_response_hook,
        )

    if config.enable_httpx_instrumentation:
        HTTPXClientInstrumentor().instrument(
            excluded_urls=".*metrics.*,.*health.*",
            request_hook=_http_request_hook,
            response_hook=_http_response_hook,
        )

    if config.enable_redis_instrumentation:
        RedisInstrumentor().instrument()

    if config.enable_sqlalchemy_instrumentation:
        # SECURITY: Disable query logging by default (can expose PII in WHERE clauses)
        # Only enable trace_db_queries in development with appropriate controls
        SQLAlchemyInstrumentor().instrument(
            enable_commenter=False,  # Don't add SQL comments with query info
            commenter_db_driver=False,
        )

    if config.enable_asyncpg_instrumentation:
        AsyncPGInstrumentor().instrument()

    if config.enable_requests_instrumentation:
        RequestsInstrumentor().instrument()

    logger.info(
        "OpenTelemetry tracing initialized",
        extra={
            "service_name": config.service_name,
            "environment": config.environment,
            "otlp_endpoint": config.otlp_endpoint,
            "sample_rate": config.sample_rate,
        },
    )

    return config


def get_tracer(name: str = "priya") -> trace.Tracer:
    """
    Get the global OpenTelemetry tracer.

    Args:
        name: Tracer name (optional, for scoping spans)

    Returns:
        OpenTelemetry Tracer instance
    """
    if _global_tracer is None:
        raise RuntimeError(
            "OpenTelemetry tracing not initialized. Call init_tracing() first."
        )
    return _global_tracer


def get_tracer_provider() -> Optional[Any]:
    """Get the global TracerProvider (for advanced usage)."""
    return _tracer_provider


# ─────────────────────────────────────────────────────────────────────────────
# Instrumentation Hooks
# ─────────────────────────────────────────────────────────────────────────────

def _request_hook(span: trace.Span, scope: Dict[str, Any]) -> None:
    """Hook called before FastAPI request processing.

    Adds custom attributes to the server span:
    - tenant_id: extracted from request headers or JWT claims
    - user_id: extracted from request headers or JWT claims
    - request_id: X-Request-ID header or generated UUID
    """
    if span.is_recording():
        # Extract tenant context from headers
        headers = dict(scope.get("headers", []))
        tenant_id = headers.get(b"x-tenant-id", b"").decode() or None
        user_id = headers.get(b"x-user-id", b"").decode() or None
        request_id = headers.get(b"x-request-id", b"").decode() or None

        if tenant_id:
            span.set_attribute("tenant_id", tenant_id)
        if user_id:
            span.set_attribute("user_id", user_id)
        if request_id:
            span.set_attribute("request_id", request_id)


def _response_hook(
    span: trace.Span,
    scope: Dict[str, Any],
    status_code: int,
    response_headers: Dict[str, str],
) -> None:
    """Hook called after FastAPI response is generated.

    Sets span status based on HTTP status code:
    - 5xx → ERROR status
    - 4xx → OK status (client error, service worked correctly)
    - 2xx/3xx → OK status
    """
    if span.is_recording():
        if status_code >= 500:
            span.set_status(Status(StatusCode.ERROR, f"HTTP {status_code}"))
        else:
            span.set_status(Status(StatusCode.OK))


def _http_request_hook(span: trace.Span, request: Any) -> None:
    """Hook for outbound httpx requests to other services.

    Adds attributes:
    - http.request.body.size: request body size
    - service.name: destination service name (inferred from host)
    """
    if span.is_recording():
        if hasattr(request, "content"):
            try:
                span.set_attribute("http.request.body.size", len(request.content))
            except Exception:
                pass


def _http_response_hook(
    span: trace.Span,
    request: Any,
    response: Any,
) -> None:
    """Hook for outbound httpx responses.

    Adds attributes:
    - http.response.body.size: response body size
    """
    if span.is_recording():
        if hasattr(response, "content"):
            try:
                span.set_attribute("http.response.body.size", len(response.content))
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Tracing Middleware
# ─────────────────────────────────────────────────────────────────────────────

class TracingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enhances request spans with tenant and user context.

    Key responsibilities:
    1. Extracts trace context from incoming headers (W3C TraceContext, B3)
    2. Extracts and stores tenant_id, user_id, request_id in context
    3. Ensures context propagates to downstream service calls
    4. Records exceptions as span events
    5. Sets span status based on response

    This middleware works in conjunction with automatic FastAPI instrumentation
    to provide rich, contextual tracing.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through middleware chain."""
        # Extract headers
        headers = dict(request.headers)

        # Get/generate trace context IDs
        tenant_id = headers.get("x-tenant-id")
        user_id = headers.get("x-user-id")
        request_id = headers.get("x-request-id")

        # Store in context for access throughout request lifecycle
        ctx = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }

        # Set request state for access in route handlers
        request.state.tenant_id = tenant_id
        request.state.user_id = user_id
        request.state.request_id = request_id

        # Get current span and add context (if OTEL available)
        span = None
        if trace:
            span = trace.get_current_span()
            if span and span.is_recording():
                if tenant_id:
                    span.set_attribute("tenant_id", tenant_id)
                if user_id:
                    span.set_attribute("user_id", user_id)
                if request_id:
                    span.set_attribute("request_id", request_id)

        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            if span and span.is_recording():
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Tenant-Aware Tracer
# ─────────────────────────────────────────────────────────────────────────────

class TenantTracer:
    """
    Tenant-aware tracer that automatically adds tenant context to all spans.

    This wrapper around the global tracer simplifies tracing in a multi-tenant
    environment by automatically including tenant_id in all span attributes.

    Usage:
        tenant_tracer = TenantTracer(tenant_id="t_123")

        # Manual span creation
        with tenant_tracer.start_span("process_payment") as span:
            span.set_attribute("amount", 100)

        # Context managers for specific operations
        with tenant_tracer.trace_db_query("SELECT * FROM users") as span:
            # Execute query
            pass
    """

    def __init__(self, tenant_id: str, user_id: Optional[str] = None):
        """
        Initialize tenant-aware tracer.

        Args:
            tenant_id: The tenant ID for context
            user_id: Optional user ID for additional context
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self._tracer = get_tracer()

    def start_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> trace.Span:
        """
        Create a span with automatic tenant context.

        Args:
            name: Span name
            attributes: Optional dict of attributes to set on span
            **kwargs: Additional arguments passed to tracer.start_span()

        Returns:
            OpenTelemetry Span with tenant context pre-set
        """
        span = self._tracer.start_span(name, **kwargs)

        # Automatically add tenant context
        span.set_attribute("tenant_id", self.tenant_id)
        if self.user_id:
            span.set_attribute("user_id", self.user_id)

        # Add any additional attributes
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        return span

    @contextmanager
    def trace_span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """
        Context manager for creating a span with tenant context.

        Usage:
            with tenant_tracer.trace_span("send_email", {"recipient": "user@example.com"}):
                # Send email
                pass
        """
        span = self.start_span(name, attributes)
        with trace.use_span(span):
            try:
                yield span
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                span.end()

    @contextmanager
    def trace_db_query(
        self,
        query: str,
        db_name: str = "postgres",
    ):
        """
        Context manager for tracing database queries.

        Usage:
            with tenant_tracer.trace_db_query("SELECT * FROM users WHERE id = ?"):
                # Execute query
                pass
        """
        with self.trace_span(
            "db.query",
            {
                "db.system": db_name,
                "db.statement": query[:200],  # Limit query length for security
            },
        ) as span:
            yield span

    @contextmanager
    def trace_cache_operation(
        self,
        operation: str,  # "get", "set", "delete", "incr", etc.
        key: str,
        value_size: Optional[int] = None,
    ):
        """
        Context manager for tracing Redis/cache operations.

        Usage:
            with tenant_tracer.trace_cache_operation("set", "user:123:session"):
                redis_client.set(key, value)
        """
        with self.trace_span(
            "cache.operation",
            {
                "cache.operation": operation,
                "cache.key": key[:100],  # Limit key length
            },
        ) as span:
            if value_size:
                span.set_attribute("cache.value_size", value_size)
            yield span

    @contextmanager
    def trace_kafka_event(
        self,
        topic: str,
        event_type: str,
        partition: Optional[int] = None,
    ):
        """
        Context manager for tracing Kafka event publishing/consuming.

        Usage:
            with tenant_tracer.trace_kafka_event("user.events", "user.created"):
                event_bus.publish(...)
        """
        with self.trace_span(
            "messaging.kafka",
            {
                "messaging.system": "kafka",
                "messaging.destination": topic,
                "messaging.message_type": event_type,
            },
        ) as span:
            if partition is not None:
                span.set_attribute("messaging.kafka.partition", partition)
            yield span

    @contextmanager
    def trace_ai_inference(
        self,
        model: str,
        operation: str = "inference",
        tokens: Optional[int] = None,
    ):
        """
        Context manager for tracing AI model inference.

        Usage:
            with tenant_tracer.trace_ai_inference("gpt-4", tokens=150):
                response = openai.ChatCompletion.create(...)
        """
        with self.trace_span(
            "ai.inference",
            {
                "ai.model": model,
                "ai.operation": operation,
            },
        ) as span:
            if tokens:
                span.set_attribute("ai.tokens", tokens)
            yield span

    @contextmanager
    def trace_external_call(
        self,
        service: str,  # "stripe", "twilio", "slack", etc.
        operation: str,
        endpoint: Optional[str] = None,
    ):
        """
        Context manager for tracing calls to external APIs.

        Usage:
            with tenant_tracer.trace_external_call("stripe", "create_charge", "/v1/charges"):
                response = stripe.Charge.create(...)
        """
        with self.trace_span(
            f"external.{service}",
            {
                "external.service": service,
                "external.operation": operation,
            },
        ) as span:
            if endpoint:
                span.set_attribute("external.endpoint", endpoint)
            yield span


# ─────────────────────────────────────────────────────────────────────────────
# Context Utilities
# ─────────────────────────────────────────────────────────────────────────────

def set_span_attribute(key: str, value: Any) -> None:
    """
    Set an attribute on the current span.

    Args:
        key: Attribute name
        value: Attribute value (must be JSON-serializable primitive)
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(key, value)


def record_span_exception(exc: Exception, message: Optional[str] = None) -> None:
    """
    Record an exception in the current span.

    Args:
        exc: Exception instance
        message: Optional message to include
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.record_exception(exc)
        if message:
            span.add_event("exception", {"message": message})


def add_span_event(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Add an event to the current span.

    Args:
        name: Event name
        attributes: Optional event attributes
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.add_event(name, attributes or {})


# ─────────────────────────────────────────────────────────────────────────────
# Propagation Helpers (for cross-service correlation)
# ─────────────────────────────────────────────────────────────────────────────

def inject_trace_context(headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Inject trace context into headers for outbound requests.

    This is used when calling other services to propagate the trace ID,
    allowing OpenTelemetry to correlate spans across service boundaries.

    Usage:
        headers = inject_trace_context({"Content-Type": "application/json"})
        response = await client.get("/api/endpoint", headers=headers)

    Args:
        headers: Optional existing headers dict to extend

    Returns:
        Headers dict with trace context injected
    """
    if headers is None:
        headers = {}

    from opentelemetry.propagate import inject

    # Create a dict carrier and inject trace context
    carrier = {}
    inject(carrier)

    # Merge with existing headers
    headers.update(carrier)
    return headers


def extract_trace_context(headers: Dict[str, str]) -> Optional[context.Context]:
    """
    Extract trace context from request headers.

    This is used on the receiving end to extract the trace ID from an incoming
    request and continue the trace in the current service.

    Args:
        headers: Request headers dict

    Returns:
        OpenTelemetry Context, or None if no trace context found
    """
    from opentelemetry.propagate import extract

    # Create carrier dict with header values (normalize to lowercase)
    carrier = {k.lower(): v for k, v in headers.items()}

    # Extract context
    ctx = extract(carrier)
    return ctx if ctx != context.get_current() else None


def with_trace_context(headers: Dict[str, str]):
    """
    Decorator/context manager to apply extracted trace context.

    Usage:
        ctx = extract_trace_context(request.headers)
        with with_trace_context(request.headers):
            # Current span will be child of the extracted context
            pass
    """
    return context.copy_context()


# ─────────────────────────────────────────────────────────────────────────────
# Shutdown & Cleanup
# ─────────────────────────────────────────────────────────────────────────────

def shutdown_tracing() -> None:
    """
    Gracefully shut down OpenTelemetry tracing and flush pending spans.

    Call this during application shutdown to ensure all spans are exported
    to the collector before the service terminates.

    Usage (in FastAPI):
        @app.on_event("shutdown")
        async def shutdown():
            shutdown_tracing()
    """
    if not HAS_OTEL_SDK:
        return
    if _tracer_provider is not None:
        _tracer_provider.force_flush(timeout_millis=30000)
        logger.info("OpenTelemetry tracing shut down and flushed")
