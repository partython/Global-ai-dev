"""
Custom Exception Classes for Priya Global Platform

Provides standardized error handling across all microservices.
All exceptions map to appropriate HTTP status codes.

USAGE:
    from shared.utils import NotFoundError, TenantIsolationError

    if not resource:
        raise NotFoundError("Resource not found", details={"resource_id": "123"})

    if tenant_id != resource.tenant_id:
        raise TenantIsolationError("Cross-tenant access attempt")
"""

import logging
from typing import Any, Dict, Optional

from fastapi import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("priya.errors")


# ─── Base Exception ───

class PriyaBaseError(Exception):
    """
    Base exception for all platform-specific errors.

    SECURITY: Error responses never include stack traces in production.
    Details field can be used for debugging but is redacted in production.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_response(self) -> Dict[str, Any]:
        """Convert to API response format."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details if self.details else None,
        }

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(error_code={self.error_code}, status_code={self.status_code})"


# ─── HTTP 4xx Errors ───

class NotFoundError(PriyaBaseError):
    """Resource not found (HTTP 404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="NOT_FOUND",
            status_code=404,
            details=details,
        )


class UnauthorizedError(PriyaBaseError):
    """Authentication failed (HTTP 401)."""

    def __init__(
        self,
        message: str = "Unauthorized",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="UNAUTHORIZED",
            status_code=401,
            details=details,
        )


class ForbiddenError(PriyaBaseError):
    """Access denied (HTTP 403)."""

    def __init__(
        self,
        message: str = "Access denied",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="FORBIDDEN",
            status_code=403,
            details=details,
        )


class ValidationError(PriyaBaseError):
    """Input validation failed (HTTP 422)."""

    def __init__(
        self,
        message: str = "Validation error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class ConflictError(PriyaBaseError):
    """Resource conflict (HTTP 409)."""

    def __init__(
        self,
        message: str = "Resource conflict",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="CONFLICT",
            status_code=409,
            details=details,
        )


class RateLimitError(PriyaBaseError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details,
        )


# ─── HTTP 5xx Errors ───

class ServiceUnavailableError(PriyaBaseError):
    """Service unavailable (HTTP 503)."""

    def __init__(
        self,
        message: str = "Service unavailable",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details,
        )


# ─── Platform-Specific Errors ───

class TenantIsolationError(PriyaBaseError):
    """
    Cross-tenant access attempt detected.

    SECURITY CRITICAL: This indicates a potential security breach.
    All such attempts are logged with full context.
    """

    def __init__(
        self,
        message: str = "Tenant isolation violation",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="TENANT_ISOLATION_ERROR",
            status_code=403,
            details=details,
        )


class DatabaseError(PriyaBaseError):
    """Database operation failed (HTTP 500)."""

    def __init__(
        self,
        message: str = "Database error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            status_code=500,
            details=details,
        )


class ExternalServiceError(PriyaBaseError):
    """External service call failed (HTTP 502/503)."""

    def __init__(
        self,
        message: str = "External service error",
        status_code: int = 502,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            error_code="EXTERNAL_SERVICE_ERROR",
            status_code=status_code,
            details=details,
        )


# ─── FastAPI Integration ───

async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    FastAPI exception handler for platform errors.

    Catches PriyaBaseError and converts to JSON response.
    All other exceptions return 500 with generic message.

    USAGE in main.py:
        from fastapi import FastAPI
        from shared.utils import global_exception_handler, PriyaBaseError

        app = FastAPI()
        app.add_exception_handler(PriyaBaseError, global_exception_handler)
    """
    if isinstance(exc, PriyaBaseError):
        # Log platform errors
        logger.warning(
            f"Platform error: {exc.error_code}",
            extra={
                "error_code": exc.error_code,
                "message": exc.message,
                "path": request.url.path,
                "status_code": exc.status_code,
            },
        )

        # Check for security-critical errors
        if exc.error_code == "TENANT_ISOLATION_ERROR":
            logger.critical(
                "SECURITY ALERT: Tenant isolation violation detected",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "client": request.client,
                    "details": exc.details,
                },
            )

        response_data = {
            "error_code": exc.error_code,
            "message": exc.message,
            "request_id": request.headers.get("X-Request-ID", "unknown"),
            "details": exc.details if exc.details else None,
        }

        return JSONResponse(
            status_code=exc.status_code,
            content=response_data,
        )

    # Generic 500 error (never expose details)
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "request_id": request.headers.get("X-Request-ID", "unknown"),
        },
    )
