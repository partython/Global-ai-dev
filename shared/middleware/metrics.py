"""
Prometheus metrics middleware for FastAPI services.

Provides automatic instrumentation for:
- HTTP request rate and timing
- Request/response status codes
- In-flight request counting
- Custom application metrics

Usage:
    from fastapi import FastAPI
    from shared.middleware.metrics import PrometheusMiddleware, setup_metrics_routes

    app = FastAPI()
    app.add_middleware(PrometheusMiddleware, app_name="my-service")
    setup_metrics_routes(app)
"""

import time
from typing import Callable, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import Response as FastAPIResponse
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Enum,
    generate_latest,
    CollectorRegistry,
    REGISTRY,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match


# ============================================================
# Prometheus Metrics Definitions
# ============================================================

# HTTP Request Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code', 'service_name'],
    registry=REGISTRY
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint', 'status_code', 'service_name'],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
    registry=REGISTRY
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests in progress',
    ['method', 'endpoint', 'service_name'],
    registry=REGISTRY
)

http_request_size_bytes = Histogram(
    'http_request_size_bytes',
    'HTTP request body size in bytes',
    ['method', 'endpoint', 'service_name'],
    buckets=(100, 1024, 10240, 102400, 1024000),
    registry=REGISTRY
)

http_response_size_bytes = Histogram(
    'http_response_size_bytes',
    'HTTP response body size in bytes',
    ['method', 'endpoint', 'status_code', 'service_name'],
    buckets=(100, 1024, 10240, 102400, 1024000),
    registry=REGISTRY
)

# Application-level metrics
app_info = Enum(
    'app_info',
    'Application information',
    ['service_name', 'version'],
    states=['running', 'stopped'],
    registry=REGISTRY
)

service_start_time = Gauge(
    'service_start_time_seconds',
    'Service start time as Unix timestamp',
    ['service_name'],
    registry=REGISTRY
)

# Database metrics
db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections',
    ['service_name', 'database'],
    registry=REGISTRY
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query latency in seconds',
    ['service_name', 'operation', 'table'],
    buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
    registry=REGISTRY
)

# Cache metrics
cache_hits_total = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['service_name', 'cache_type'],
    registry=REGISTRY
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['service_name', 'cache_type'],
    registry=REGISTRY
)

# Business logic metrics
active_conversations = Gauge(
    'active_conversations',
    'Number of active conversations',
    ['service_name', 'channel'],
    registry=REGISTRY
)

messages_processed_total = Counter(
    'messages_processed_total',
    'Total messages processed',
    ['service_name', 'channel', 'status'],
    registry=REGISTRY
)

conversations_completed_total = Counter(
    'conversations_completed_total',
    'Total conversations completed',
    ['service_name', 'channel'],
    registry=REGISTRY
)

# AI Engine metrics
ai_inference_total = Counter(
    'ai_inference_total',
    'Total AI inferences',
    ['service_name', 'model', 'status'],
    registry=REGISTRY
)

ai_inference_duration_seconds = Histogram(
    'ai_inference_duration_seconds',
    'AI inference latency in seconds',
    ['service_name', 'model'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY
)

# Rate limiting metrics
rate_limit_requests_remaining = Gauge(
    'rate_limit_requests_remaining',
    'Remaining API requests within rate limit',
    ['service_name', 'client_id'],
    registry=REGISTRY
)

rate_limit_requests_limit = Gauge(
    'rate_limit_requests_limit',
    'API rate limit threshold',
    ['service_name', 'client_id'],
    registry=REGISTRY
)

# SSL Certificate metrics
ssl_certificate_not_after = Gauge(
    'ssl_certificate_not_after',
    'SSL certificate expiration time as Unix timestamp',
    ['domain'],
    registry=REGISTRY
)

# Kafka metrics
kafka_consumer_lag_sum = Gauge(
    'kafka_consumer_lag_sum',
    'Total Kafka consumer lag in messages',
    ['consumer_group', 'topics'],
    registry=REGISTRY
)


# ============================================================
# Prometheus Middleware
# ============================================================

class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware for FastAPI that instruments HTTP requests with Prometheus metrics.

    Records:
    - Request rate per endpoint/method/status
    - Request latency (duration)
    - In-flight request count
    - Request/response body sizes

    Attributes:
        app_name: Name of the service for labeling metrics
        group_paths: If True, groups requests by path pattern
        skip_paths: Set of path prefixes to skip instrumentation
    """

    def __init__(
        self,
        app: FastAPI,
        app_name: str = "fastapi_app",
        group_paths: bool = True,
        skip_paths: Optional[set] = None,
    ):
        super().__init__(app)
        self.app = app
        self.app_name = app_name
        self.group_paths = group_paths
        self.skip_paths = skip_paths or {"/metrics", "/health", "/readiness"}
        self.start_time = datetime.utcnow()

        # Initialize service metrics
        service_start_time.labels(service_name=self.app_name).set(time.time())
        app_info.labels(service_name=self.app_name, version="1.0").state("running")

    def _get_endpoint_name(self, request: Request) -> str:
        """
        Extract the endpoint name from the request.

        Returns either the exact path or a pattern-matched route.
        """
        if not self.group_paths:
            return request.url.path

        for route in self.app.routes:
            match, child_scope = route.matches(request.scope)
            if match == Match.FULL:
                return route.path

        return request.url.path

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the HTTP request and record metrics.
        """
        # Skip metrics collection for excluded paths
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        endpoint = self._get_endpoint_name(request)
        method = request.method

        # Record request size
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                http_request_size_bytes.labels(
                    method=method,
                    endpoint=endpoint,
                    service_name=self.app_name,
                ).observe(int(content_length))
            except (ValueError, TypeError):
                pass

        # Track in-progress requests
        http_requests_in_progress.labels(
            method=method,
            endpoint=endpoint,
            service_name=self.app_name,
        ).inc()

        # Time the request processing
        start_time = time.time()
        status_code = 500  # Default to error

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            raise
        finally:
            # Record request duration and status
            duration = time.time() - start_time

            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                service_name=self.app_name,
            ).observe(duration)

            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                service_name=self.app_name,
            ).inc()

            # Record response size
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    http_response_size_bytes.labels(
                        method=method,
                        endpoint=endpoint,
                        status_code=status_code,
                        service_name=self.app_name,
                    ).observe(int(content_length))
                except (ValueError, TypeError):
                    pass

            # Decrement in-progress requests
            http_requests_in_progress.labels(
                method=method,
                endpoint=endpoint,
                service_name=self.app_name,
            ).dec()

        return response


# ============================================================
# Metrics Endpoints Setup
# ============================================================

def setup_metrics_routes(app: FastAPI) -> None:
    """
    Add metrics endpoint to FastAPI application.

    Creates:
    - GET /metrics: Prometheus metrics endpoint
    - GET /health: Basic health check
    - GET /readiness: Readiness probe

    Args:
        app: FastAPI application instance
    """

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        """Prometheus metrics endpoint."""
        return FastAPIResponse(
            content=generate_latest(),
            media_type="text/plain; charset=utf-8"
        )

    @app.get("/health", include_in_schema=False)
    async def health():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": (datetime.utcnow() - app.state.start_time).total_seconds()
            if hasattr(app.state, 'start_time') else None,
        }

    @app.get("/readiness", include_in_schema=False)
    async def readiness():
        """Readiness probe endpoint."""
        return {
            "ready": True,
            "timestamp": datetime.utcnow().isoformat(),
        }


# ============================================================
# Helper Functions for Recording Custom Metrics
# ============================================================

def record_db_query(
    service_name: str,
    operation: str,
    table: str,
    duration: float
) -> None:
    """
    Record a database query execution.

    Args:
        service_name: Name of the service
        operation: SQL operation (SELECT, INSERT, UPDATE, DELETE)
        table: Table name
        duration: Query duration in seconds
    """
    db_query_duration_seconds.labels(
        service_name=service_name,
        operation=operation,
        table=table,
    ).observe(duration)


def record_cache_hit(service_name: str, cache_type: str) -> None:
    """Record a cache hit."""
    cache_hits_total.labels(
        service_name=service_name,
        cache_type=cache_type,
    ).inc()


def record_cache_miss(service_name: str, cache_type: str) -> None:
    """Record a cache miss."""
    cache_misses_total.labels(
        service_name=service_name,
        cache_type=cache_type,
    ).inc()


def set_active_conversations(
    service_name: str,
    channel: str,
    count: int
) -> None:
    """Update active conversation count."""
    active_conversations.labels(
        service_name=service_name,
        channel=channel,
    ).set(count)


def record_message_processed(
    service_name: str,
    channel: str,
    status: str
) -> None:
    """Record a processed message."""
    messages_processed_total.labels(
        service_name=service_name,
        channel=channel,
        status=status,
    ).inc()


def record_conversation_completed(
    service_name: str,
    channel: str
) -> None:
    """Record a completed conversation."""
    conversations_completed_total.labels(
        service_name=service_name,
        channel=channel,
    ).inc()


def record_ai_inference(
    service_name: str,
    model: str,
    status: str,
    duration: Optional[float] = None
) -> None:
    """
    Record an AI inference.

    Args:
        service_name: Name of the service
        model: Model name/version
        status: Inference status (success, error, timeout)
        duration: Inference duration in seconds
    """
    ai_inference_total.labels(
        service_name=service_name,
        model=model,
        status=status,
    ).inc()

    if duration is not None:
        ai_inference_duration_seconds.labels(
            service_name=service_name,
            model=model,
        ).observe(duration)


def record_db_connection_count(
    service_name: str,
    database: str,
    count: int
) -> None:
    """Update active database connection count."""
    db_connections_active.labels(
        service_name=service_name,
        database=database,
    ).set(count)


def set_rate_limit_remaining(
    service_name: str,
    client_id: str,
    remaining: int,
    limit: int
) -> None:
    """Update rate limit metrics."""
    rate_limit_requests_remaining.labels(
        service_name=service_name,
        client_id=client_id,
    ).set(remaining)

    rate_limit_requests_limit.labels(
        service_name=service_name,
        client_id=client_id,
    ).set(limit)


def record_ssl_cert_expiry(domain: str, expiry_timestamp: float) -> None:
    """Record SSL certificate expiration time."""
    ssl_certificate_not_after.labels(domain=domain).set(expiry_timestamp)


def record_kafka_consumer_lag(consumer_group: str, topics: str, lag: int) -> None:
    """Record Kafka consumer lag."""
    kafka_consumer_lag_sum.labels(
        consumer_group=consumer_group,
        topics=topics,
    ).set(lag)


# ============================================================
# Context Managers for Timing Operations
# ============================================================

@asynccontextmanager
async def time_db_operation(
    service_name: str,
    operation: str,
    table: str
):
    """
    Context manager for timing database operations.

    Usage:
        async with time_db_operation("my-service", "SELECT", "users"):
            # perform query
            pass
    """
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        record_db_query(service_name, operation, table, duration)


@asynccontextmanager
async def time_ai_inference(
    service_name: str,
    model: str,
    status: str = "success"
):
    """
    Context manager for timing AI inference operations.

    Usage:
        async with time_ai_inference("ai-engine", "gpt-3.5-turbo"):
            # perform inference
            pass
    """
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        record_ai_inference(service_name, model, status, duration)
