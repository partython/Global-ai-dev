"""
Sentry Middleware for FastAPI Services

Automatically:
- Sets tenant context from request state (populated by auth middleware)
- Tracks request performance
- Captures unhandled exceptions with full context
- Adds request breadcrumbs

Usage:
    from shared.middleware.sentry import SentryTenantMiddleware
    app.add_middleware(SentryTenantMiddleware)
"""

import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import sentry_sdk

logger = logging.getLogger("priya.middleware.sentry")


class SentryTenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enriches Sentry events with tenant context.
    Must be added AFTER auth middleware so request.state has tenant_id.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        
        # Extract tenant context from auth middleware
        tenant_id = getattr(request.state, "tenant_id", None) if hasattr(request, "state") else None
        user_id = getattr(request.state, "user_id", None) if hasattr(request, "state") else None
        
        with sentry_sdk.configure_scope() as scope:
            # Set tenant tags
            if tenant_id:
                scope.set_tag("tenant_id", tenant_id)
                scope.set_context("tenant", {"id": tenant_id})
            if user_id:
                scope.set_user({"id": user_id})
            
            # Set request tags
            scope.set_tag("http.method", request.method)
            scope.set_tag("http.path", request.url.path)
            
            # Add request breadcrumb
            sentry_sdk.add_breadcrumb(
                category="http",
                message=f"{request.method} {request.url.path}",
                level="info",
                data={
                    "method": request.method,
                    "path": request.url.path,
                    "tenant_id": tenant_id or "unknown",
                },
            )
            
            try:
                response = await call_next(request)
                
                # Tag response status
                scope.set_tag("http.status_code", str(response.status_code))
                
                # Track slow requests
                duration = time.monotonic() - start
                if duration > 5.0:
                    sentry_sdk.add_breadcrumb(
                        category="performance",
                        message=f"Slow request: {request.method} {request.url.path} took {duration:.2f}s",
                        level="warning",
                    )
                
                return response
                
            except Exception as exc:
                # Capture with full context
                scope.set_tag("http.status_code", "500")
                sentry_sdk.capture_exception(exc)
                raise
