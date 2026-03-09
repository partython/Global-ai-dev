"""
Convenient Decorators for OpenTelemetry Tracing

Provides easy-to-use decorators for automatic span creation around:
- Async functions (automatic exception handling and timing)
- Database operations (with query logging)
- Cache operations (with key tracking)
- External API calls (Stripe, Twilio, Slack, etc.)
- AI model inference (with token counting)
- Background jobs (with job context)

All decorators automatically:
- Create spans with function name as span name
- Record execution time
- Handle and record exceptions
- Extract tenant context from request/function args

Usage:
    @trace_function
    async def process_order(order_id: str):
        # Automatically traced
        pass

    @trace_db_operation
    async def get_user(user_id: str):
        # Automatically traced as db.query span
        pass

    @trace_external_call("stripe", "create_charge")
    async def charge_customer(amount: float):
        # Automatically traced
        pass
"""

import asyncio
import functools
import inspect
import logging
import time
from typing import Any, Callable, Optional, TypeVar, Union

from opentelemetry import trace, context
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger("priya.trace_decorators")

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _get_tenant_id_from_args(func_args: tuple, func_kwargs: dict) -> Optional[str]:
    """Try to extract tenant_id from function arguments.

    SECURITY: Only extract tenant_id from explicit keyword arguments.
    Do NOT infer from positional args or heuristics (prone to spoofing).
    The actual tenant_id should come from request context (headers, JWT).
    """
    # ONLY accept explicit tenant_id keyword argument
    if "tenant_id" in func_kwargs:
        tenant_id = func_kwargs["tenant_id"]
        # Validate format (basic sanity check)
        if isinstance(tenant_id, str) and len(tenant_id) > 0:
            return tenant_id

    # SECURITY: Do NOT extract from positional args via heuristics
    # This was vulnerable to spoofing; removed startswith("t_") checks

    return None


def _get_current_tracer() -> trace.Tracer:
    """Get the current OpenTelemetry tracer."""
    return trace.get_tracer(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Generic Function Tracing
# ─────────────────────────────────────────────────────────────────────────────

def trace_function(
    func: Optional[Callable[..., T]] = None,
    *,
    span_name: Optional[str] = None,
    attributes: Optional[dict] = None,
) -> Union[Callable[[Callable[..., T]], Callable[..., T]], Callable[..., T]]:
    """
    Decorator to automatically trace any async function.

    Creates a span around function execution with:
    - Automatic exception recording
    - Execution time measurement
    - Function name as span name (or custom span_name)
    - Optional custom attributes

    Usage:
        @trace_function
        async def process_data(data: dict):
            # Automatically traced
            pass

        @trace_function(span_name="custom_name", attributes={"version": "1.0"})
        async def complex_operation():
            pass

    Args:
        func: Function to trace
        span_name: Optional custom span name (defaults to function name)
        attributes: Optional dict of static attributes to add to span
    """

    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        nonlocal span_name
        if span_name is None:
            span_name = f.__name__

        is_async = asyncio.iscoroutinefunction(f)

        if is_async:

            @functools.wraps(f)
            async def async_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = attributes.copy() if attributes else {}

                # Try to extract tenant context
                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    # Set attributes
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = await f(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(f)
            def sync_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = attributes.copy() if attributes else {}

                # Try to extract tenant context
                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    # Set attributes
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = f(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return sync_wrapper  # type: ignore

    if func is None:
        # Called with arguments: @trace_function(span_name="...")
        return decorator
    else:
        # Called without arguments: @trace_function
        return decorator(func)


# ─────────────────────────────────────────────────────────────────────────────
# Database Operation Tracing
# ─────────────────────────────────────────────────────────────────────────────

def trace_db_operation(
    func: Optional[Callable[..., T]] = None,
    *,
    span_name: Optional[str] = None,
    db_system: str = "postgres",
) -> Union[Callable[[Callable[..., T]], Callable[..., T]], Callable[..., T]]:
    """
    Decorator to trace database operations.

    Creates a span with database-specific attributes:
    - db.system: database type (postgres, mysql, etc.)
    - db.operation: operation type (SELECT, INSERT, UPDATE, DELETE, etc.)
    - Optional: query snippet (first 200 chars for security)

    Usage:
        @trace_db_operation
        async def get_user_by_id(user_id: str):
            # SELECT * FROM users WHERE id = ?
            pass

        @trace_db_operation(db_system="mysql")
        async def create_account(account_data: dict):
            pass

    Args:
        func: Function to trace
        span_name: Optional custom span name (defaults to function name)
        db_system: Database system (postgres, mysql, mongodb, etc.)
    """

    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        nonlocal span_name
        if span_name is None:
            span_name = f"{f.__name__}.db"

        is_async = asyncio.iscoroutinefunction(f)

        if is_async:

            @functools.wraps(f)
            async def async_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "db.system": db_system,
                    "db.operation": "query",  # Will be updated based on function name
                }

                # Infer operation from function name
                func_name_lower = f.__name__.lower()
                if "create" in func_name_lower or "insert" in func_name_lower:
                    span_attrs["db.operation"] = "INSERT"
                elif "update" in func_name_lower:
                    span_attrs["db.operation"] = "UPDATE"
                elif "delete" in func_name_lower:
                    span_attrs["db.operation"] = "DELETE"
                elif "get" in func_name_lower or "find" in func_name_lower or "select" in func_name_lower:
                    span_attrs["db.operation"] = "SELECT"

                # Try to extract tenant context
                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = await f(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(f)
            def sync_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "db.system": db_system,
                    "db.operation": "query",
                }

                # Infer operation from function name
                func_name_lower = f.__name__.lower()
                if "create" in func_name_lower or "insert" in func_name_lower:
                    span_attrs["db.operation"] = "INSERT"
                elif "update" in func_name_lower:
                    span_attrs["db.operation"] = "UPDATE"
                elif "delete" in func_name_lower:
                    span_attrs["db.operation"] = "DELETE"
                elif "get" in func_name_lower or "find" in func_name_lower:
                    span_attrs["db.operation"] = "SELECT"

                # Try to extract tenant context
                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = f(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return sync_wrapper  # type: ignore

    if func is None:
        return decorator
    else:
        return decorator(func)


# ─────────────────────────────────────────────────────────────────────────────
# Cache Operation Tracing
# ─────────────────────────────────────────────────────────────────────────────

def trace_cache_operation(
    func: Optional[Callable[..., T]] = None,
    *,
    span_name: Optional[str] = None,
    cache_system: str = "redis",
) -> Union[Callable[[Callable[..., T]], Callable[..., T]], Callable[..., T]]:
    """
    Decorator to trace cache (Redis) operations.

    Creates a span with cache-specific attributes:
    - cache.system: cache system (redis, memcached, etc.)
    - cache.operation: operation type (GET, SET, DELETE, etc.)

    Usage:
        @trace_cache_operation
        async def get_user_session(session_id: str):
            # Redis GET
            pass

        @trace_cache_operation(cache_system="memcached")
        async def set_cache_value(key: str, value: str):
            pass

    Args:
        func: Function to trace
        span_name: Optional custom span name (defaults to function name)
        cache_system: Cache system name (redis, memcached, etc.)
    """

    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        nonlocal span_name
        if span_name is None:
            span_name = f"{f.__name__}.cache"

        is_async = asyncio.iscoroutinefunction(f)

        if is_async:

            @functools.wraps(f)
            async def async_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "cache.system": cache_system,
                    "cache.operation": "operation",
                }

                # Infer operation from function name
                func_name_lower = f.__name__.lower()
                if "set" in func_name_lower:
                    span_attrs["cache.operation"] = "SET"
                elif "get" in func_name_lower:
                    span_attrs["cache.operation"] = "GET"
                elif "delete" in func_name_lower or "remove" in func_name_lower:
                    span_attrs["cache.operation"] = "DELETE"
                elif "incr" in func_name_lower:
                    span_attrs["cache.operation"] = "INCR"
                elif "expire" in func_name_lower:
                    span_attrs["cache.operation"] = "EXPIRE"

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = await f(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(f)
            def sync_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "cache.system": cache_system,
                    "cache.operation": "operation",
                }

                func_name_lower = f.__name__.lower()
                if "set" in func_name_lower:
                    span_attrs["cache.operation"] = "SET"
                elif "get" in func_name_lower:
                    span_attrs["cache.operation"] = "GET"
                elif "delete" in func_name_lower or "remove" in func_name_lower:
                    span_attrs["cache.operation"] = "DELETE"
                elif "incr" in func_name_lower:
                    span_attrs["cache.operation"] = "INCR"

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = f(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return sync_wrapper  # type: ignore

    if func is None:
        return decorator
    else:
        return decorator(func)


# ─────────────────────────────────────────────────────────────────────────────
# External API Call Tracing
# ─────────────────────────────────────────────────────────────────────────────

def trace_external_call(
    service: str,
    operation: Optional[str] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to trace calls to external APIs (Stripe, Twilio, Slack, etc.).

    Creates a span with external service attributes:
    - external.service: service name (stripe, twilio, slack, etc.)
    - external.operation: operation performed

    Usage:
        @trace_external_call("stripe", "create_charge")
        async def charge_customer(amount: float):
            pass

        @trace_external_call("twilio", "send_sms")
        async def send_sms(phone: str, message: str):
            pass

    Args:
        service: External service name (stripe, twilio, slack, etc.)
        operation: Operation name (optional, inferred from function name if not provided)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        nonlocal operation
        if operation is None:
            operation = func.__name__

        span_name = f"external.{service}.{operation}"
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "external.service": service,
                    "external.operation": operation,
                }

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "external.service": service,
                    "external.operation": operation,
                }

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return sync_wrapper  # type: ignore

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# AI Inference Tracing
# ─────────────────────────────────────────────────────────────────────────────

def trace_ai_inference(
    model: str,
    operation: str = "inference",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to trace AI model inference calls.

    Creates a span with AI-specific attributes:
    - ai.model: model name (gpt-4, claude, etc.)
    - ai.operation: operation type (inference, training, etc.)
    - ai.tokens: token count (if available)

    Usage:
        @trace_ai_inference("gpt-4", "completion")
        async def generate_response(prompt: str, tokens: int = 150):
            pass

        @trace_ai_inference("claude-3")
        async def classify_message(text: str):
            pass

    Args:
        model: AI model name
        operation: Operation type (inference, training, embedding, etc.)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        span_name = f"ai.{model}.{operation}"
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "ai.model": model,
                    "ai.operation": operation,
                }

                # Try to extract token count from kwargs
                if "tokens" in kwargs:
                    span_attrs["ai.tokens"] = kwargs["tokens"]
                elif "max_tokens" in kwargs:
                    span_attrs["ai.tokens"] = kwargs["max_tokens"]

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "ai.model": model,
                    "ai.operation": operation,
                }

                if "tokens" in kwargs:
                    span_attrs["ai.tokens"] = kwargs["tokens"]
                elif "max_tokens" in kwargs:
                    span_attrs["ai.tokens"] = kwargs["max_tokens"]

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return sync_wrapper  # type: ignore

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Background Job Tracing
# ─────────────────────────────────────────────────────────────────────────────

def trace_background_job(
    job_name: Optional[str] = None,
    queue: Optional[str] = None,
) -> Union[Callable[[Callable[..., T]], Callable[..., T]], Callable[..., T]]:
    """
    Decorator to trace background worker jobs.

    Creates a span with job-specific attributes:
    - job.name: job name
    - job.queue: queue name (celery, rq, etc.)
    - job.id: job ID (if available)

    Usage:
        @trace_background_job(queue="celery")
        async def process_email(email_id: str):
            pass

        @trace_background_job("send_digest")
        async def send_daily_digest(user_id: str):
            pass

    Args:
        job_name: Optional job name (defaults to function name)
        queue: Optional queue system name (celery, rq, etc.)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        name = job_name or func.__name__
        span_name = f"job.{name}"
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "job.name": name,
                }

                if queue:
                    span_attrs["job.queue"] = queue

                # Try to extract job ID from kwargs
                if "job_id" in kwargs:
                    span_attrs["job.id"] = kwargs["job_id"]

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return async_wrapper  # type: ignore
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                tracer = _get_current_tracer()
                span_attrs = {
                    "job.name": name,
                }

                if queue:
                    span_attrs["job.queue"] = queue

                if "job_id" in kwargs:
                    span_attrs["job.id"] = kwargs["job_id"]

                tenant_id = _get_tenant_id_from_args(args, kwargs)
                if tenant_id:
                    span_attrs["tenant_id"] = tenant_id

                with tracer.start_as_current_span(span_name) as span:
                    for key, value in span_attrs.items():
                        span.set_attribute(key, value)

                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return sync_wrapper  # type: ignore

    if func is None:
        return decorator
    else:
        return decorator(func)
