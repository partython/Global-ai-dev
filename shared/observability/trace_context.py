"""
Trace Context Management for Multi-Tenant Distributed Systems

Provides thread-safe context management for:
- Trace ID (automatically set by OpenTelemetry)
- Span ID (automatically set by OpenTelemetry)
- Tenant ID (extracted from request headers)
- User ID (extracted from request headers)
- Request ID (X-Request-ID header or generated)
- Custom attributes (tenant-specific metadata)

Handles propagation across:
- Synchronous function calls
- Async function calls
- HTTP requests to other services (via header injection)
- Kafka messages (via message headers)
- Background jobs

Architecture:
- Uses contextvars for thread-safe context storage
- Integrates with OpenTelemetry's context propagation
- Provides context managers for scope management
- Automatic cleanup on function exit
"""

import contextvars
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from opentelemetry import trace, context as otel_context

logger = logging.getLogger("priya.trace_context")

# Context variables (thread-safe, async-safe)
_trace_context_var: contextvars.ContextVar["TraceContext"] = contextvars.ContextVar(
    "trace_context",
    default=None,
)
_tenant_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "tenant_id",
    default=None,
)
_user_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "user_id",
    default=None,
)
_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id",
    default=None,
)


# ─────────────────────────────────────────────────────────────────────────────
# Trace Context Data Class
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TraceContext:
    """
    Complete trace context for a request/operation in a multi-tenant system.

    Attributes:
        trace_id: OpenTelemetry trace ID (128-bit hex string)
        span_id: OpenTelemetry span ID (64-bit hex string)
        tenant_id: Tenant identifier (required for multi-tenant operations)
        user_id: User identifier (optional)
        request_id: Unique request identifier (for tracing single requests)
        custom_attributes: Additional context-specific attributes
    """
    trace_id: str
    span_id: str
    tenant_id: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    custom_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary (for serialization)."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "custom_attributes": self.custom_attributes,
        }

    def to_headers(self) -> Dict[str, str]:
        """Convert context to HTTP headers for propagation."""
        headers = {
            "x-tenant-id": self.tenant_id,
            "x-trace-id": self.trace_id,
            "x-span-id": self.span_id,
        }

        if self.user_id:
            headers["x-user-id"] = self.user_id
        if self.request_id:
            headers["x-request-id"] = self.request_id

        # SECURITY: Don't serialize complex objects to headers
        # Headers have size limits and JSON can contain sensitive data
        # Only propagate simple IDs, not complex custom_attributes
        # if self.custom_attributes:
        #     headers["x-trace-attributes"] = json.dumps(self.custom_attributes)

        return headers

    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> Optional["TraceContext"]:
        """Create TraceContext from HTTP headers."""
        tenant_id = headers.get("x-tenant-id") or headers.get("x_tenant_id")
        if not tenant_id:
            return None

        # Get trace/span IDs from OpenTelemetry if not in headers
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()
        trace_id = headers.get("x-trace-id") or str(span_context.trace_id)
        span_id = headers.get("x-span-id") or str(span_context.span_id)

        # SECURITY: Validate trace_id is valid 128-bit hex (not 0 or 00000...)
        try:
            trace_id_int = int(trace_id, 16) if isinstance(trace_id, str) else int(trace_id)
            if trace_id_int == 0:
                # Invalid trace ID; generate new one
                import uuid
                trace_id = uuid.uuid4().hex
        except (ValueError, TypeError):
            # Invalid format; use new UUID
            import uuid
            trace_id = uuid.uuid4().hex

        user_id = headers.get("x-user-id") or headers.get("x_user_id")
        request_id = headers.get("x-request-id") or headers.get("x_request_id")

        # Parse custom attributes if present
        custom_attributes = {}
        attrs_json = headers.get("x-trace-attributes")
        if attrs_json:
            try:
                custom_attributes = json.loads(attrs_json)
            except json.JSONDecodeError:
                logger.warning("Failed to parse trace attributes from headers")

        return cls(
            trace_id=str(trace_id),
            span_id=str(span_id),
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=request_id,
            custom_attributes=custom_attributes,
        )

    @classmethod
    def from_kafka_message(cls, message: Dict[str, Any]) -> Optional["TraceContext"]:
        """Create TraceContext from Kafka message headers/metadata."""
        headers = message.get("headers", {})
        if isinstance(headers, list):
            # Kafka Python client format: list of (key, value) tuples
            headers = {k.decode() if isinstance(k, bytes) else k:
                      v.decode() if isinstance(v, bytes) else v
                      for k, v in headers}

        return cls.from_headers(headers)


# ─────────────────────────────────────────────────────────────────────────────
# Context Management
# ─────────────────────────────────────────────────────────────────────────────

def get_current_context() -> Optional[TraceContext]:
    """
    Get the current trace context.

    Returns:
        TraceContext if available, None otherwise
    """
    return _trace_context_var.get()


def set_trace_context(ctx: TraceContext) -> None:
    """
    Set the current trace context.

    Args:
        ctx: TraceContext to set
    """
    _trace_context_var.set(ctx)
    _tenant_id_var.set(ctx.tenant_id)
    _user_id_var.set(ctx.user_id)
    _request_id_var.set(ctx.request_id)

    # Also set in OpenTelemetry span attributes
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("tenant_id", ctx.tenant_id)
        if ctx.user_id:
            span.set_attribute("user_id", ctx.user_id)
        if ctx.request_id:
            span.set_attribute("request_id", ctx.request_id)


def set_tenant_context(
    tenant_id: str,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    custom_attributes: Optional[Dict[str, Any]] = None,
) -> TraceContext:
    """
    Set tenant context for the current request/operation.

    This is typically called in middleware to extract tenant info from
    request headers and store it for use throughout the request.

    Args:
        tenant_id: Tenant identifier (required)
        user_id: User identifier (optional)
        request_id: Request identifier (optional, generated if not provided)
        custom_attributes: Additional context attributes (optional)

    Returns:
        The TraceContext that was set

    Usage:
        # In middleware:
        ctx = set_tenant_context(
            tenant_id=request.headers.get("x-tenant-id"),
            user_id=request.headers.get("x-user-id"),
        )
    """
    # Get current OpenTelemetry trace/span IDs
    current_span = trace.get_current_span()
    span_context = current_span.get_span_context()

    # Convert to hex format (OpenTelemetry uses 16-byte integers)
    trace_id = format(span_context.trace_id, "032x")
    span_id = format(span_context.span_id, "016x")

    # Generate request ID if not provided
    if not request_id:
        request_id = str(uuid.uuid4())

    # Create and set context
    ctx = TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        tenant_id=tenant_id,
        user_id=user_id,
        request_id=request_id,
        custom_attributes=custom_attributes or {},
    )

    set_trace_context(ctx)
    return ctx


def clear_context() -> None:
    """Clear the current trace context."""
    _trace_context_var.set(None)
    _tenant_id_var.set(None)
    _user_id_var.set(None)
    _request_id_var.set(None)


def get_tenant_id() -> Optional[str]:
    """Get the current tenant ID."""
    return _tenant_id_var.get()


def get_user_id() -> Optional[str]:
    """Get the current user ID."""
    return _user_id_var.get()


def get_request_id() -> Optional[str]:
    """Get the current request ID."""
    return _request_id_var.get()


# ─────────────────────────────────────────────────────────────────────────────
# Kafka Message Propagation
# ─────────────────────────────────────────────────────────────────────────────

def propagate_to_kafka(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add trace context headers to a Kafka event message.

    This ensures trace context is preserved when publishing events
    to Kafka, allowing the consuming service to continue the trace.

    Args:
        event: Event dict to enhance with trace headers

    Returns:
        Event dict with trace headers added

    Usage:
        event = {"type": "user.created", "user_id": "123"}
        event = propagate_to_kafka(event)
        await event_bus.publish(event)
    """
    ctx = get_current_context()
    if ctx is None:
        return event

    # Add trace headers to event metadata
    if "headers" not in event:
        event["headers"] = {}

    headers = event["headers"]
    trace_headers = ctx.to_headers()
    headers.update(trace_headers)

    return event


def extract_from_kafka(event: Dict[str, Any]) -> Optional[TraceContext]:
    """
    Extract trace context from a Kafka event message.

    This is called when consuming Kafka messages to restore the trace
    context from the publishing service, continuing the distributed trace.

    Args:
        event: Kafka event dict with potential trace headers

    Returns:
        TraceContext if available, None otherwise

    Usage:
        async def handle_user_created(event: dict):
            ctx = extract_from_kafka(event)
            if ctx:
                set_trace_context(ctx)
            # Now the trace is continued
    """
    headers = event.get("headers", {})

    # Handle both dict and list formats
    if isinstance(headers, list):
        headers = {
            k.decode() if isinstance(k, bytes) else k:
            v.decode() if isinstance(v, bytes) else v
            for k, v in headers
        }

    return TraceContext.from_headers(headers)


# ─────────────────────────────────────────────────────────────────────────────
# Async Context Propagation
# ─────────────────────────────────────────────────────────────────────────────

def copy_context():
    """
    Get a copy of the current context for passing to async tasks.

    Use this when spawning background tasks to ensure they have access
    to the same trace context.

    Usage:
        ctx = copy_context()
        asyncio.create_task(background_task(ctx))

        async def background_task(ctx):
            token = _trace_context_var.set(ctx.trace_context)
            try:
                # Do work with context
                pass
            finally:
                _trace_context_var.reset(token)
    """
    return contextvars.copy_context()


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Header Utilities
# ─────────────────────────────────────────────────────────────────────────────

def inject_context_headers(headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Inject current trace context into HTTP headers.

    Used when making HTTP calls to other services to propagate context.

    Args:
        headers: Optional existing headers dict to extend

    Returns:
        Headers with trace context injected

    Usage:
        headers = inject_context_headers()
        response = await http_client.get("/api/endpoint", headers=headers)
    """
    if headers is None:
        headers = {}
    else:
        headers = headers.copy()

    ctx = get_current_context()
    if ctx:
        headers.update(ctx.to_headers())

    return headers


def extract_context_headers(headers: Dict[str, str]) -> None:
    """
    Extract and set trace context from HTTP response headers.

    Args:
        headers: Response headers dict
    """
    # Normalize headers to lowercase for comparison
    normalized = {k.lower(): v for k, v in headers.items()}

    ctx = TraceContext.from_headers(normalized)
    if ctx:
        set_trace_context(ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Custom Attribute Management
# ─────────────────────────────────────────────────────────────────────────────

def set_custom_attribute(key: str, value: Any) -> None:
    """
    Set a custom attribute on the current trace context.

    Args:
        key: Attribute name
        value: Attribute value (must be JSON-serializable)
    """
    ctx = get_current_context()
    if ctx:
        ctx.custom_attributes[key] = value

        # Also set on current span
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute(f"custom.{key}", value)


def get_custom_attribute(key: str) -> Optional[Any]:
    """
    Get a custom attribute from the current trace context.

    Args:
        key: Attribute name

    Returns:
        Attribute value or None if not set
    """
    ctx = get_current_context()
    if ctx:
        return ctx.custom_attributes.get(key)
    return None
