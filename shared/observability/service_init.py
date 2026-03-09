"""
Service Initialization Helper

Centralizes startup for all Priya Global microservices:
- Sentry error tracking
- Structured logging
- Common middleware registration

Usage in any service main.py:
    from shared.observability.service_init import init_service
    
    app = FastAPI(title="My Service")
    init_service(app, service_name="my-service", service_port=9001)
"""

import logging
import os
from typing import Optional

from fastapi import FastAPI

from shared.observability.sentry import init_sentry


def init_service(
    app: FastAPI,
    service_name: str,
    service_port: int,
    extra_sentry_integrations: Optional[list] = None,
) -> None:
    """
    Initialize a Priya Global microservice with all observability.
    
    Call this right after creating the FastAPI app instance.
    """
    # 1. Initialize Sentry
    init_sentry(
        service_name=service_name,
        service_port=service_port,
        extra_integrations=extra_sentry_integrations,
    )
    
    # 2. Add Sentry middleware (tenant context enrichment)
    try:
        from shared.middleware.sentry import SentryTenantMiddleware
        app.add_middleware(SentryTenantMiddleware)
    except Exception as e:
        logging.getLogger("priya.init").warning(f"Could not add Sentry middleware: {e}")
    
    # 3. Log startup
    env = os.getenv("ENVIRONMENT", "development")
    logging.getLogger("priya.init").info(
        f"Service {service_name} initialized (port={service_port}, env={env}, sentry={'enabled' if os.getenv('SENTRY_DSN') else 'disabled'})"
    )
