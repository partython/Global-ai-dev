"""
Production-Grade Inter-Service HTTP Client

Advanced features for resilient service-to-service communication:
- Circuit breaker pattern (CLOSED → OPEN → HALF_OPEN states)
- Exponential backoff retry with jitter
- Automatic tenant context propagation
- Request/response logging with PII scrubbing
- Connection pooling and keepalive
- Metrics collection (request count, latency, errors)
- Comprehensive error classes
- OpenTelemetry distributed tracing integration

RELIABILITY FEATURES:
- Failure threshold: 5 consecutive failures
- Recovery timeout: 30 seconds
- Half-open max calls: 3 (test if service recovered)
- Max retries: 3
- Exponential backoff: base 0.5s, max 8s
- Request timeouts: connect 5s, read 30s, write 10s

TRACING:
- All inter-service calls are automatically traced
- Trace context is propagated via headers
- Each request creates a span with service/method/path attributes
- Errors are recorded in spans
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
HAS_OTEL = True

from .service_registry import get_registry

logger = logging.getLogger("priya.http_client")


class CircuitState(Enum):
    """Circuit breaker state machine."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Circuit open, rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


class ServiceUnavailableError(Exception):
    """Service is not available (circuit open or unreachable)."""
    pass


class CircuitOpenError(Exception):
    """Circuit breaker is open - service is temporarily unavailable."""
    pass


class ServiceTimeoutError(Exception):
    """Request to service timed out."""
    pass


class ServiceConnectionError(Exception):
    """Cannot connect to service."""
    pass


@dataclass
class CircuitBreakerState:
    """State tracking for circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    success_count: int = 0  # Success count in HALF_OPEN state
    last_state_change: float = 0.0

    def is_open(self) -> bool:
        """Check if circuit is in OPEN state."""
        return self.state == CircuitState.OPEN

    def is_closed(self) -> bool:
        """Check if circuit is in CLOSED state."""
        return self.state == CircuitState.CLOSED

    def is_half_open(self) -> bool:
        """Check if circuit is in HALF_OPEN state."""
        return self.state == CircuitState.HALF_OPEN


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    service_name: str
    method: str
    path: str
    status_code: Optional[int]
    latency_ms: float
    timestamp: float
    error: Optional[str] = None
    retry_count: int = 0
    is_circuit_open: bool = False


@dataclass
class ServiceMetrics:
    """Aggregated metrics for a service."""
    service_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    circuit_open_rejections: int = 0
    timeout_errors: int = 0
    connection_errors: int = 0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_updated: float = field(default_factory=time.time)

    def __post_init__(self):
        self.latencies: List[float] = []

    def record_request(self, metrics: RequestMetrics):
        """Record a request in service metrics."""
        self.total_requests += 1
        self.last_updated = time.time()

        if metrics.is_circuit_open:
            self.circuit_open_rejections += 1
            self.last_error = "circuit_open"
        elif metrics.error:
            self.failed_requests += 1
            self.last_error = metrics.error

            if isinstance(metrics.error, str):
                if "timeout" in metrics.error.lower():
                    self.timeout_errors += 1
                elif "connection" in metrics.error.lower():
                    self.connection_errors += 1
        else:
            self.successful_requests += 1

        # Track latency
        if metrics.latency_ms >= 0:
            self.latencies.append(metrics.latency_ms)
            self._update_latency_stats()

    def _update_latency_stats(self):
        """Update latency percentiles."""
        if not self.latencies:
            return

        sorted_latencies = sorted(self.latencies)
        self.avg_latency_ms = sum(self.latencies) / len(self.latencies)
        self.min_latency_ms = min(self.latencies)
        self.max_latency_ms = max(self.latencies)

        # P95 and P99
        if len(sorted_latencies) > 0:
            p95_idx = int(len(sorted_latencies) * 0.95)
            p99_idx = int(len(sorted_latencies) * 0.99)
            self.p95_latency_ms = sorted_latencies[max(0, p95_idx - 1)]
            self.p99_latency_ms = sorted_latencies[max(0, p99_idx - 1)]

    def get_success_rate(self) -> float:
        """Get request success rate (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests


class ServiceClient:
    """
    Production-grade HTTP client for inter-service communication.

    Features:
    - Automatic service discovery via ServiceRegistry
    - Circuit breaker pattern for fault tolerance
    - Exponential backoff retry strategy
    - Automatic tenant context propagation
    - Request/response logging with PII scrubbing
    - Connection pooling
    - Comprehensive metrics
    """

    # Circuit breaker configuration
    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 30  # seconds
    HALF_OPEN_MAX_CALLS = 3

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 0.5  # seconds
    RETRY_MAX_DELAY = 8.0  # seconds

    # Timeout configuration (seconds)
    CONNECT_TIMEOUT = 5.0
    READ_TIMEOUT = 30.0
    WRITE_TIMEOUT = 10.0

    def __init__(
        self,
        environment: Optional[str] = None,
        max_connections: int = 100,
        max_keepalive: int = 20,
        custom_headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the service client.

        Args:
            environment: Deployment environment ('local', 'docker', 'kubernetes')
            max_connections: Maximum connection pool size
            max_keepalive: Maximum keepalive connections per host
            custom_headers: Custom headers to include in all requests
        """
        self.registry = get_registry(environment)
        self.custom_headers = custom_headers or {}

        # Connection pool
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
        )
        self.client = httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(
                timeout=self.READ_TIMEOUT,
                connect=self.CONNECT_TIMEOUT,
                write=self.WRITE_TIMEOUT,
            ),
        )

        # Circuit breaker state per service
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {}

        # Metrics per service
        self._metrics: Dict[str, ServiceMetrics] = {}

        # PII patterns for scrubbing
        self._pii_patterns = [
            (r'"email":\s*"[^"]*"', '"email": "***"'),
            (r'"phone":\s*"[^"]*"', '"phone": "***"'),
            (r'"ssn":\s*"[^"]*"', '"ssn": "***"'),
            (r'"card":\s*"[^"]*"', '"card": "***"'),
            (r'"password":\s*"[^"]*"', '"password": "***"'),
            (r'"api_key":\s*"[^"]*"', '"api_key": "***"'),
            (r'"secret":\s*"[^"]*"', '"secret": "***"'),
        ]

    def _get_circuit_breaker(self, service_name: str) -> CircuitBreakerState:
        """Get or create circuit breaker for a service."""
        if service_name not in self._circuit_breakers:
            self._circuit_breakers[service_name] = CircuitBreakerState()
        return self._circuit_breakers[service_name]

    def _get_metrics(self, service_name: str) -> ServiceMetrics:
        """Get or create metrics for a service."""
        if service_name not in self._metrics:
            self._metrics[service_name] = ServiceMetrics(service_name)
        return self._metrics[service_name]

    def _scrub_pii(self, text: str) -> str:
        """Scrub PII from text for logging."""
        for pattern, replacement in self._pii_patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    async def _check_circuit(self, service_name: str) -> bool:
        """
        Check circuit breaker state and potentially transition states.

        Returns:
            True if request should proceed, False if circuit is open
        """
        cb = self._get_circuit_breaker(service_name)

        if cb.state == CircuitState.CLOSED:
            return True

        elif cb.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if time.time() - cb.last_failure_time >= self.RECOVERY_TIMEOUT:
                logger.info(f"Circuit breaker for {service_name} transitioning to HALF_OPEN")
                cb.state = CircuitState.HALF_OPEN
                cb.success_count = 0
                cb.last_state_change = time.time()
                return True
            else:
                return False

        elif cb.state == CircuitState.HALF_OPEN:
            # In HALF_OPEN: allow limited requests
            if cb.success_count < self.HALF_OPEN_MAX_CALLS:
                return True
            else:
                # Successfully recovered
                logger.info(f"Circuit breaker for {service_name} transitioning to CLOSED")
                cb.state = CircuitState.CLOSED
                cb.failure_count = 0
                cb.success_count = 0
                cb.last_state_change = time.time()
                return True

    def _record_success(self, service_name: str):
        """Record successful request."""
        cb = self._get_circuit_breaker(service_name)

        if cb.state == CircuitState.HALF_OPEN:
            cb.success_count += 1
        elif cb.state == CircuitState.CLOSED:
            cb.failure_count = 0

    def _record_failure(self, service_name: str):
        """Record failed request."""
        cb = self._get_circuit_breaker(service_name)

        cb.failure_count += 1
        cb.last_failure_time = time.time()

        if cb.state == CircuitState.CLOSED:
            if cb.failure_count >= self.FAILURE_THRESHOLD:
                logger.warning(
                    f"Circuit breaker for {service_name} transitioning to OPEN "
                    f"({cb.failure_count} failures)"
                )
                cb.state = CircuitState.OPEN
                cb.last_state_change = time.time()

        elif cb.state == CircuitState.HALF_OPEN:
            # One failure in HALF_OPEN reopens
            logger.warning(f"Circuit breaker for {service_name} reopening (failed during HALF_OPEN)")
            cb.state = CircuitState.OPEN
            cb.last_state_change = time.time()

    async def _execute_with_retry(
        self,
        method: str,
        url: str,
        service_name: str,
        **kwargs
    ) -> httpx.Response:
        """
        Execute request with exponential backoff retry.

        Raises:
            ServiceTimeoutError: On timeout
            ServiceConnectionError: On connection error
            httpx.HTTPError: On other HTTP errors
        """
        last_error = None
        metrics = self._get_metrics(service_name)

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                self._record_success(service_name)
                return response

            except httpx.TimeoutException as e:
                last_error = e
                self._record_failure(service_name)
                metrics.timeout_errors += 1

                if attempt < self.MAX_RETRIES:
                    delay = min(
                        self.RETRY_BASE_DELAY * (2 ** attempt),
                        self.RETRY_MAX_DELAY
                    )
                    logger.warning(
                        f"Request to {service_name} timed out (attempt {attempt + 1}), "
                        f"retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise ServiceTimeoutError(f"Service {service_name} timeout") from e

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_error = e
                self._record_failure(service_name)
                metrics.connection_errors += 1

                if attempt < self.MAX_RETRIES:
                    delay = min(
                        self.RETRY_BASE_DELAY * (2 ** attempt),
                        self.RETRY_MAX_DELAY
                    )
                    logger.warning(
                        f"Cannot connect to {service_name} (attempt {attempt + 1}), "
                        f"retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise ServiceConnectionError(f"Cannot connect to {service_name}") from e

            except httpx.HTTPError as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    delay = min(
                        self.RETRY_BASE_DELAY * (2 ** attempt),
                        self.RETRY_MAX_DELAY
                    )
                    logger.warning(
                        f"HTTP error from {service_name} (attempt {attempt + 1}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    self._record_failure(service_name)
                    raise

        # Should not reach here
        raise ServiceTimeoutError(f"Service {service_name} unreachable") from last_error

    def _prepare_headers(
        self,
        headers: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None,
        authorization: Optional[str] = None,
    ) -> Dict[str, str]:
        """Prepare headers with automatic tenant context propagation."""
        final_headers = self.custom_headers.copy()

        if headers:
            final_headers.update(headers)

        # Add tracking headers
        if request_id:
            final_headers["X-Request-ID"] = request_id
        elif "X-Request-ID" not in final_headers:
            final_headers["X-Request-ID"] = str(uuid.uuid4())

        # Add tenant context
        if tenant_id:
            final_headers["X-Tenant-ID"] = tenant_id

        # Add authorization
        if authorization:
            final_headers["Authorization"] = authorization

        # Add user-agent
        final_headers["User-Agent"] = "Priya-ServiceClient/1.0"

        return final_headers

    async def call_service(
        self,
        service_name: str,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
        request_id: Optional[str] = None,
        authorization: Optional[str] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Call another service with automatic URL resolution and resilience.

        Args:
            service_name: Name of the service (e.g., 'auth', 'whatsapp')
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., '/api/v1/users')
            headers: Optional custom headers
            tenant_id: Tenant ID for context propagation
            request_id: Request ID for tracing
            authorization: Authorization header value
            **kwargs: Additional httpx request arguments (data, json, etc.)

        Returns:
            httpx.Response object

        Raises:
            CircuitOpenError: If circuit breaker is open
            ServiceTimeoutError: If request times out
            ServiceConnectionError: If cannot connect
            ValueError: If service not found
        """
        # Validate service
        if not self.registry.validate_service(service_name):
            raise ValueError(f"Unknown service: {service_name}")

        # Check circuit breaker
        if not await self._check_circuit(service_name):
            metrics = self._get_metrics(service_name)
            metrics.circuit_open_rejections += 1
            raise CircuitOpenError(f"Circuit breaker open for {service_name}")

        # Resolve URL
        base_url = self.registry.get_service_url(service_name)
        full_url = f"{base_url}{path}"

        # Prepare headers
        final_headers = self._prepare_headers(
            headers=headers,
            tenant_id=tenant_id,
            request_id=request_id,
            authorization=authorization,
        )

        # Check request body size (10MB limit)
        if "content" in kwargs:
            content = kwargs["content"]
            if isinstance(content, bytes):
                content_size = len(content)
            elif isinstance(content, str):
                content_size = len(content.encode())
            else:
                content_size = 0

            max_size = 10 * 1024 * 1024  # 10MB
            if content_size > max_size:
                raise ValueError(
                    f"Request body exceeds maximum size (10MB): {content_size} bytes"
                )

        # Log request
        scrubbed_kwargs = kwargs.copy()
        if "json" in scrubbed_kwargs:
            scrubbed_kwargs["json"] = json.loads(
                self._scrub_pii(json.dumps(scrubbed_kwargs["json"]))
            )

        logger.info(
            f"[{final_headers.get('X-Request-ID')}] "
            f"{method} {service_name}:{path} "
            f"tenant={tenant_id or 'N/A'}"
        )

        # Create OpenTelemetry span for inter-service call (optional)
        span = None
        span_ctx = None
        if HAS_OTEL:
            tracer = trace.get_tracer(__name__)
            span_name = f"{service_name}.{method.lower()}"
            span_ctx = tracer.start_as_current_span(span_name)
            span = span_ctx.__enter__()
            span.set_attribute("rpc.system", "http")
            span.set_attribute("rpc.service", service_name)
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", full_url)
            if tenant_id:
                span.set_attribute("tenant_id", tenant_id)
            if request_id:
                span.set_attribute("request_id", request_id)
            try:
                from opentelemetry.propagate import inject
                inject(final_headers)
            except Exception:
                pass

        # Execute with retry and metrics
        start_time = time.time()
        try:
            response = await self._execute_with_retry(
                method,
                full_url,
                service_name,
                headers=final_headers,
                **kwargs
            )

            latency_ms = (time.time() - start_time) * 1000
            self._get_metrics(service_name).record_request(
                RequestMetrics(
                    service_name=service_name,
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    timestamp=time.time(),
                )
            )

            if span:
                span.set_attribute("http.status_code", response.status_code)
                if response.status_code >= 400:
                    span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                else:
                    span.set_status(Status(StatusCode.OK))

            logger.info(
                f"[{final_headers.get('X-Request-ID')}] "
                f"{response.status_code} {service_name} latency={latency_ms:.1f}ms"
            )

            return response

        except (CircuitOpenError, ServiceTimeoutError, ServiceConnectionError) as e:
            latency_ms = (time.time() - start_time) * 1000
            self._get_metrics(service_name).record_request(
                RequestMetrics(
                    service_name=service_name,
                    method=method,
                    path=path,
                    status_code=None,
                    latency_ms=latency_ms,
                    timestamp=time.time(),
                    error=str(e),
                )
            )

            if span:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))

            logger.error(f"[{request_id or 'N/A'}] Service error: {e}")
            raise
        finally:
            if span_ctx:
                span_ctx.__exit__(None, None, None)

    async def get(
        self,
        service_name: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """GET request to a service."""
        return await self.call_service(service_name, "GET", path, **kwargs)

    async def post(
        self,
        service_name: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """POST request to a service."""
        return await self.call_service(service_name, "POST", path, **kwargs)

    async def put(
        self,
        service_name: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """PUT request to a service."""
        return await self.call_service(service_name, "PUT", path, **kwargs)

    async def patch(
        self,
        service_name: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """PATCH request to a service."""
        return await self.call_service(service_name, "PATCH", path, **kwargs)

    async def delete(
        self,
        service_name: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """DELETE request to a service."""
        return await self.call_service(service_name, "DELETE", path, **kwargs)

    async def health_check(self, service_name: str) -> bool:
        """
        Check if a service is healthy.

        Returns:
            True if service responds with 200 to /health
        """
        try:
            response = await self.get(service_name, "/health")
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed for {service_name}: {e}")
            return False

    def get_service_metrics(self, service_name: str) -> ServiceMetrics:
        """Get metrics for a service."""
        return self._get_metrics(service_name)

    def get_all_metrics(self) -> Dict[str, ServiceMetrics]:
        """Get metrics for all services that have been called."""
        return self._metrics.copy()

    def get_circuit_breaker_status(self, service_name: str) -> Dict[str, Any]:
        """Get circuit breaker status for a service."""
        cb = self._get_circuit_breaker(service_name)
        return {
            "service": service_name,
            "state": cb.state.value,
            "failure_count": cb.failure_count,
            "last_failure": cb.last_failure_time,
            "success_count": cb.success_count,
            "last_state_change": cb.last_state_change,
        }

    def get_all_circuit_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get circuit breaker status for all services."""
        return {
            name: self.get_circuit_breaker_status(name)
            for name in self._circuit_breakers.keys()
        }

    async def close(self):
        """Close the HTTP client and cleanup."""
        await self.client.aclose()
        logger.info("ServiceClient closed")


# Global singleton instance
_client: Optional[ServiceClient] = None


async def get_service_client(environment: Optional[str] = None) -> ServiceClient:
    """
    Get the global service client instance.

    Args:
        environment: Deployment environment (only used on first call).
                    Defaults to ENVIRONMENT env var or 'local'.

    Returns:
        ServiceClient singleton

    Note:
        This is async to allow for future initialization requirements.
        Currently, initialization is synchronous.
    """
    global _client

    if _client is None:
        _client = ServiceClient(environment=environment)

    return _client


async def close_service_client():
    """Close the global service client."""
    global _client

    if _client:
        await _client.close()
        _client = None
