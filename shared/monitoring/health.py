"""
Health check utilities with Sentry heartbeat integration.
"""

import os
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("priya.health")

_start_time = time.time()

async def get_health_status(
    service_name: str,
    service_port: int,
    version: str = "1.0.0",
    checks: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Standard health check response with Sentry cron monitoring."""
    uptime = time.time() - _start_time

    all_healthy = all(checks.values()) if checks else True

    status = {
        "status": "healthy" if all_healthy else "degraded",
        "service": service_name,
        "port": service_port,
        "version": version,
        "uptime_seconds": round(uptime, 2),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "checks": checks or {},
    }

    # Report to Sentry as cron heartbeat
    if not all_healthy:
        try:
            from shared.monitoring.sentry_config import capture_message
            capture_message(
                f"{service_name} health degraded",
                level="warning",
                extra={"checks": checks},
            )
        except Exception:
            pass

    return status
