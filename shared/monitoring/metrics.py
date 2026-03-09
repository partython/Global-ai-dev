"""
Prometheus Metrics Module for Priya Global Platform

Shared metrics collection that ALL 36 microservices import.
Lightweight and efficient for use across the platform.

Exported Metrics:
- http_requests_total: Counter for HTTP requests
- http_request_duration_seconds: Histogram for request latency
- http_requests_in_progress: Gauge for concurrent requests
- db_query_duration_seconds: Histogram for database queries
- redis_operations_total: Counter for Redis operations
- kafka_messages_produced_total: Counter for Kafka produces
- kafka_messages_consumed_total: Counter for Kafka consumes
- active_conversations: Gauge for active conversations
- ai_tokens_used_total: Counter for AI tokens consumed
- tenant_api_calls_total: Counter for tenant API calls
- service_info: Gauge for service metadata (version, environment)
"""

import os
import time
from typing import Callable, Optional
from functools import wraps

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from prometheus_client.core import REGISTRY
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.requests import Request


# ─────────────────────────────────────────────────────────────────────────────
# Histogram buckets optimized for observing p50, p90, p95, p99
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Metrics
# ─────────────────────────────────────────────────────────────────────────────

http_requests_total = Counter(
    name="http_requests_total",
    documentation="Total HTTP requests received",
    labelnames=("method", "endpoint", "status", "tenant_id", "service"),
)
# SECURITY: tenant_id label is kept for per-tenant analytics and billing.
# The /metrics endpoint MUST be protected with authentication in production
# to prevent unauthorized access to per-tenant metrics data.

http_request_duration_seconds = Histogram(
    name="http_request_duration_seconds",
    documentation="HTTP request latency in seconds",
    labelnames=("method", "endpoint", "service"),
    buckets=DEFAULT_BUCKETS,
)

http_requests_in_progress = Gauge(
    name="http_requests_in_progress",
    documentation="HTTP requests currently being processed",
    labelnames=("service",),
)


# ─────────────────────────────────────────────────────────────────────────────
# Database Metrics
# ─────────────────────────────────────────────────────────────────────────────

db_query_duration_seconds = Histogram(
    name="db_query_duration_seconds",
    documentation="Database query execution time in seconds",
    labelnames=("query_type", "service"),
    buckets=DEFAULT_BUCKETS,
)

db_connections_active = Gauge(
    name="db_connections_active",
    documentation="Active database connections",
    labelnames=("service", "pool"),
)

db_connections_available = Gauge(
    name="db_connections_available",
    documentation="Available database connections in pool",
    labelnames=("service", "pool"),
)


# ─────────────────────────────────────────────────────────────────────────────
# Cache/Redis Metrics
# ─────────────────────────────────────────────────────────────────────────────

redis_operations_total = Counter(
    name="redis_operations_total",
    documentation="Total Redis operations",
    labelnames=("operation", "service"),
)

redis_operation_duration_seconds = Histogram(
    name="redis_operation_duration_seconds",
    documentation="Redis operation latency in seconds",
    labelnames=("operation", "service"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

redis_memory_usage_bytes = Gauge(
    name="redis_memory_usage_bytes",
    documentation="Redis memory usage in bytes",
)

redis_connected_clients = Gauge(
    name="redis_connected_clients",
    documentation="Number of connected Redis clients",
)


# ─────────────────────────────────────────────────────────────────────────────
# Message Queue Metrics
# ─────────────────────────────────────────────────────────────────────────────

kafka_messages_produced_total = Counter(
    name="kafka_messages_produced_total",
    documentation="Total Kafka messages published",
    labelnames=("topic", "service"),
)

kafka_messages_consumed_total = Counter(
    name="kafka_messages_consumed_total",
    documentation="Total Kafka messages consumed",
    labelnames=("topic", "service"),
)

kafka_consumer_lag = Gauge(
    name="kafka_consumer_lag",
    documentation="Kafka consumer lag (messages behind)",
    labelnames=("topic", "consumer_group", "service"),
)

kafka_produce_duration_seconds = Histogram(
    name="kafka_produce_duration_seconds",
    documentation="Kafka produce latency in seconds",
    labelnames=("topic", "service"),
    buckets=DEFAULT_BUCKETS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: Conversations
# ─────────────────────────────────────────────────────────────────────────────

active_conversations = Gauge(
    name="active_conversations",
    documentation="Number of active conversations",
    labelnames=("tenant_id", "channel"),
)

conversations_created_total = Counter(
    name="conversations_created_total",
    documentation="Total conversations created",
    labelnames=("tenant_id", "channel", "service"),
)

conversation_duration_seconds = Histogram(
    name="conversation_duration_seconds",
    documentation="Conversation duration in seconds",
    labelnames=("tenant_id", "channel", "service"),
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400, 28800),
)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: AI & LLM
# ─────────────────────────────────────────────────────────────────────────────

ai_tokens_used_total = Counter(
    name="ai_tokens_used_total",
    documentation="Total AI tokens consumed",
    labelnames=("tenant_id", "model", "service"),
)

ai_api_calls_total = Counter(
    name="ai_api_calls_total",
    documentation="Total AI API calls made",
    labelnames=("model", "service", "status"),
)

ai_api_duration_seconds = Histogram(
    name="ai_api_duration_seconds",
    documentation="AI API call latency in seconds",
    labelnames=("model", "service"),
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

ai_token_budget_used_percent = Gauge(
    name="ai_token_budget_used_percent",
    documentation="Percentage of tenant's AI token budget used",
    labelnames=("tenant_id", "model"),
)


# ─────────────────────────────────────────────────────────────────────────────
# Tenant/Multi-tenancy Metrics
# ─────────────────────────────────────────────────────────────────────────────

tenant_api_calls_total = Counter(
    name="tenant_api_calls_total",
    documentation="Total API calls per tenant",
    labelnames=("tenant_id", "plan", "service"),
)

tenant_rate_limit_exceeded_total = Counter(
    name="tenant_rate_limit_exceeded_total",
    documentation="Total rate limit exceeds per tenant",
    labelnames=("tenant_id", "service"),
)

active_tenants = Gauge(
    name="active_tenants",
    documentation="Number of active tenants",
)

tenant_token_usage_percent = Gauge(
    name="tenant_token_usage_percent",
    documentation="Percentage of tenant's token quota used",
    labelnames=("tenant_id", "quota_type"),
)


# ─────────────────────────────────────────────────────────────────────────────
# System/Service Metrics
# ─────────────────────────────────────────────────────────────────────────────

service_info = Info(
    name="service_info",
    documentation="Service metadata",
    labelnames=("service", "version", "environment"),
)

ssl_cert_expiry_seconds = Gauge(
    name="ssl_cert_expiry_seconds",
    documentation="SSL certificate expiry time (Unix timestamp)",
    labelnames=("domain", "service"),
)

disk_free_bytes = Gauge(
    name="disk_free_bytes",
    documentation="Free disk space in bytes",
    labelnames=("service", "mount_point"),
)

disk_total_bytes = Gauge(
    name="disk_total_bytes",
    documentation="Total disk space in bytes",
    labelnames=("service", "mount_point"),
)


# ─────────────────────────────────────────────────────────────────────────────
# Error/Exception Tracking
# ─────────────────────────────────────────────────────────────────────────────

exceptions_total = Counter(
    name="exceptions_total",
    documentation="Total unhandled exceptions",
    labelnames=("exception_type", "service"),
)

validation_errors_total = Counter(
    name="validation_errors_total",
    documentation="Total validation errors",
    labelnames=("field", "error_type", "service"),
)


# ─────────────────────────────────────────────────────────────────────────────
# PrometheusMiddleware for FastAPI
# ─────────────────────────────────────────────────────────────────────────────


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that automatically instruments all HTTP endpoints.

    Tracks:
    - http_requests_total (counter with method, endpoint, status, tenant_id, service)
    - http_request_duration_seconds (histogram with method, endpoint, service)
    - http_requests_in_progress (gauge with service)
    """

    def __init__(self, app, service_name: str):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and record metrics."""
        start_time = time.time()

        # Get tenant_id from headers or path
        tenant_id = request.headers.get("X-Tenant-ID", "unknown")

        # Clean endpoint path (remove variable parts like /users/{id})
        endpoint = request.url.path
        for route in request.app.routes:
            try:
                match = route.path_regex.match(request.url.path)
                if match:
                    endpoint = route.path
                    break
            except AttributeError:
                pass

        # Increment in-progress counter
        http_requests_in_progress.labels(service=self.service_name).inc()

        try:
            # Call the actual endpoint
            response = await call_next(request)

            # Record metrics
            duration = time.time() - start_time
            status = response.status_code

            http_requests_total.labels(
                method=request.method,
                endpoint=endpoint,
                status=status,
                tenant_id=tenant_id,
                service=self.service_name,
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=endpoint,
                service=self.service_name,
            ).observe(duration)

            return response

        finally:
            # Decrement in-progress counter
            http_requests_in_progress.labels(service=self.service_name).dec()


# ─────────────────────────────────────────────────────────────────────────────
# Custom Metric Decorator
# ─────────────────────────────────────────────────────────────────────────────


def track_metric(
    histogram: Optional[Histogram] = None,
    counter: Optional[Counter] = None,
    metric_labels: Optional[dict] = None,
):
    """
    Decorator to track custom metrics on a function.

    Usage:
        @track_metric(
            histogram=db_query_duration_seconds,
            counter=db_operations_total,
            metric_labels={"query_type": "select", "service": "my-service"}
        )
        async def get_user(user_id: int):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time

                if histogram and metric_labels:
                    histogram.labels(**metric_labels).observe(duration)

                if counter and metric_labels:
                    counter.labels(**metric_labels).inc()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time

                if histogram and metric_labels:
                    histogram.labels(**metric_labels).observe(duration)

                if counter and metric_labels:
                    counter.labels(**metric_labels).inc()

        # Return async or sync wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# /metrics Endpoint Handler
# ─────────────────────────────────────────────────────────────────────────────


async def metrics_handler(request: Request) -> Response:
    """
    FastAPI endpoint that serves Prometheus metrics.

    SECURITY: Production deployments MUST protect this endpoint with authentication.
    This endpoint should only be accessible to monitoring systems (Prometheus, Grafana).
    Use one of the following approaches in production:
    - Firewall/network policies (recommended)
    - mTLS via service mesh (e.g., Istio, Linkerd)
    - Bearer token authentication
    - Basic authentication
    - API Gateway authentication

    Add to your FastAPI app:
        from fastapi import FastAPI
        from shared.monitoring.metrics import metrics_handler

        app = FastAPI()
        app.add_api_route("/metrics", metrics_handler, methods=["GET"])
    """
    # Check for X-Metrics-Token header (development convenience)
    # Production must use service mesh mTLS or firewall rules
    metrics_token = request.headers.get("X-Metrics-Token", "").strip()
    expected_token = os.getenv("METRICS_TOKEN", "")

    if expected_token and metrics_token != expected_token:
        return Response(
            content="Unauthorized",
            status_code=401,
            media_type="text/plain",
        )

    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Service Info Setup Helper
# ─────────────────────────────────────────────────────────────────────────────


def init_service_info(
    service_name: str,
    version: str = "1.0.0",
    environment: Optional[str] = None,
):
    """
    Initialize service_info metric with metadata.

    Call this once at service startup:
        from shared.monitoring.metrics import init_service_info

        init_service_info(
            service_name="auth",
            version=os.getenv("SERVICE_VERSION", "1.0.0"),
            environment=os.getenv("ENVIRONMENT", "development")
        )
    """
    if not environment:
        environment = os.getenv("ENVIRONMENT", "development")

    service_info.labels(
        service=service_name,
        version=version,
        environment=environment,
    ).info({})
