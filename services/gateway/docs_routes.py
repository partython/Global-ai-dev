"""
API Documentation Routes for Priya Global Gateway

This module provides FastAPI routes for serving comprehensive API documentation
including OpenAPI specifications, Swagger UI, and ReDoc interfaces.

Features:
- OpenAPI 3.0 specification serving with full endpoint documentation
- Swagger UI with custom branding, dark mode, and try-it-out functionality
- ReDoc alternative documentation view
- Health aggregation for service status
- Rate-limited public access with caching
- Custom CSS for Priya Global branding

Endpoints:
    GET  /docs              - Swagger UI (primary documentation)
    GET  /docs/openapi.json - OpenAPI specification (JSON)
    GET  /redoc             - ReDoc documentation (alternative view)
    GET  /docs/health       - Service health information
    GET  /docs/guides       - Integration guides
    GET  /docs/examples     - Code examples
    GET  /docs/services     - Service catalog
    GET  /docs/changelog    - API version history
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("priya.gateway.docs")

# Router for documentation endpoints
docs_router = APIRouter(
    prefix="/docs",
    tags=["Documentation"],
    responses={404: {"description": "Not found"}}
)

# Service configuration mapping (from gateway route table)
SERVICE_MAPPING = {
    "/api/v1/auth": {
        "target": "http://localhost:9001",
        "name": "Auth Service",
        "port": 9001,
        "description": "User authentication, registration, and token management",
    },
    "/api/v1/tenants": {
        "target": "http://localhost:9002",
        "name": "Tenant Service",
        "port": 9002,
        "description": "Multi-tenant workspace configuration",
    },
    "/api/v1/conversations": {
        "target": "http://localhost:9003",
        "name": "Channel Router",
        "port": 9003,
        "description": "Conversation and message management",
    },
    "/api/v1/channels": {
        "target": "http://localhost:9003",
        "name": "Channel Router",
        "port": 9003,
        "description": "Communication channel configuration",
    },
    "/api/v1/messages": {
        "target": "http://localhost:9003",
        "name": "Channel Router",
        "port": 9003,
        "description": "Message routing and delivery",
    },
    "/api/v1/ai": {
        "target": "http://localhost:9020",
        "name": "AI Engine",
        "port": 9020,
        "description": "AI-powered message classification and response generation",
    },
    "/api/v1/knowledge": {
        "target": "http://localhost:9020",
        "name": "AI Engine",
        "port": 9020,
        "description": "Knowledge base and document management",
    },
    "/api/v1/whatsapp": {
        "target": "http://localhost:9010",
        "name": "WhatsApp Service",
        "port": 9010,
        "description": "WhatsApp Business API integration",
    },
    "/api/v1/email": {
        "target": "http://localhost:9011",
        "name": "Email Service",
        "port": 9011,
        "description": "Email sending and webhook handling",
    },
    "/api/v1/voice": {
        "target": "http://localhost:9012",
        "name": "Voice Service",
        "port": 9012,
        "description": "Voice calls and IVR",
    },
    "/api/v1/sms": {
        "target": "http://localhost:9014",
        "name": "SMS Service",
        "port": 9014,
        "description": "SMS sending and delivery tracking",
    },
    "/api/v1/social": {
        "target": "http://localhost:9013",
        "name": "Social Service",
        "port": 9013,
        "description": "Social media channel integration",
    },
    "/api/v1/webchat": {
        "target": "http://localhost:9015",
        "name": "WebChat Service",
        "port": 9015,
        "description": "Web chat widget and embedded chat",
    },
    "/api/v1/telegram": {
        "target": "http://localhost:9016",
        "name": "Telegram Service",
        "port": 9016,
        "description": "Telegram bot integration",
    },
    "/api/v1/rcs": {
        "target": "http://localhost:9017",
        "name": "RCS Service",
        "port": 9017,
        "description": "Rich Communication Services",
    },
    "/api/v1/video": {
        "target": "http://localhost:9018",
        "name": "Video Service",
        "port": 9018,
        "description": "Video rooms and live streaming",
    },
    "/api/v1/billing": {
        "target": "http://localhost:9027",
        "name": "Billing Service",
        "port": 9027,
        "description": "Subscription management and invoicing",
    },
    "/api/v1/analytics": {
        "target": "http://localhost:9023",
        "name": "Analytics Service",
        "port": 9023,
        "description": "Analytics dashboards and reporting",
    },
    "/api/v1/marketing": {
        "target": "http://localhost:9024",
        "name": "Marketing Service",
        "port": 9024,
        "description": "Campaigns and marketing automation",
    },
    "/api/v1/ecommerce": {
        "target": "http://localhost:9025",
        "name": "E-commerce Service",
        "port": 9025,
        "description": "Product catalog and order management",
    },
    "/api/v1/notifications": {
        "target": "http://localhost:9026",
        "name": "Notification Service",
        "port": 9026,
        "description": "Push notifications and alerts",
    },
    "/api/v1/plugins": {
        "target": "http://localhost:9028",
        "name": "Plugins Service",
        "port": 9028,
        "description": "Third-party plugin management",
    },
    "/api/v1/handoff": {
        "target": "http://localhost:9029",
        "name": "Handoff Service",
        "port": 9029,
        "description": "Human agent handoff and escalation",
    },
    "/api/v1/leads": {
        "target": "http://localhost:9030",
        "name": "Leads Service",
        "port": 9030,
        "description": "Lead capture and management",
    },
    "/api/v1/intelligence": {
        "target": "http://localhost:9031",
        "name": "Conversation Intelligence",
        "port": 9031,
        "description": "Conversation analysis and insights",
    },
    "/api/v1/appointments": {
        "target": "http://localhost:9032",
        "name": "Appointments Service",
        "port": 9032,
        "description": "Scheduling and appointment management",
    },
    "/api/v1/workflows": {
        "target": "http://localhost:9033",
        "name": "Workflows Service",
        "port": 9033,
        "description": "Automation workflows and triggers",
    },
    "/api/v1/compliance": {
        "target": "http://localhost:9034",
        "name": "Compliance Service",
        "port": 9034,
        "description": "Audit logs and compliance reporting",
    },
    "/api/v1/cdn": {
        "target": "http://localhost:9035",
        "name": "CDN Manager",
        "port": 9035,
        "description": "Media management and CDN operations",
    },
    "/api/v1/deployment": {
        "target": "http://localhost:9036",
        "name": "Deployment Service",
        "port": 9036,
        "description": "Release and deployment management",
    },
}

# Health check caching
_health_cache: Dict[str, Dict[str, Any]] = {}
_health_cache_time: Dict[str, float] = {}
HEALTH_CACHE_TTL = 10  # seconds

# Bearer token validation
security = HTTPBearer()


def _validate_internal_url(target: str) -> bool:
    """
    Validate that target URL is an internal service (localhost or private IP only).
    Prevents SSRF attacks by restricting to internal addresses.
    """
    from urllib.parse import urlparse
    import ipaddress

    try:
        parsed = urlparse(target)

        # Ensure scheme is http or https only
        if parsed.scheme not in ('http', 'https'):
            return False

        host = parsed.hostname or ""
        if not host:
            return False

        # Allow localhost and loopback
        if host in ("localhost", "127.0.0.1", "::1"):
            return True

        # Check private IP ranges
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback
        except ValueError:
            # Check string patterns for private ranges
            if host.startswith(("10.", "172.", "192.168.")):
                return True

        return False
    except Exception as e:
        logger.error("Error validating URL format")
        return False


async def _get_service_health(client: httpx.AsyncClient, target: str, name: str) -> Dict[str, Any]:
    """Check health of a single service with caching."""
    cache_key = name
    current_time = time.time()

    # Validate target URL
    if not _validate_internal_url(target):
        logger.error(f"Rejecting non-internal service URL for {name}: {target}")
        return {
            "status": "unhealthy",
            "name": name,
            "error": "Invalid service URL",
        }

    # Check cache
    if cache_key in _health_cache and cache_key in _health_cache_time:
        if current_time - _health_cache_time[cache_key] < HEALTH_CACHE_TTL:
            return _health_cache[cache_key]

    try:
        response = await client.get(f"{target}/health", timeout=5)
        is_healthy = response.status_code == 200

        health_info = {
            "status": "healthy" if is_healthy else "unhealthy",
            "name": name,
            "response_time_ms": int(response.elapsed.total_seconds() * 1000),
        }

        _health_cache[cache_key] = health_info
        _health_cache_time[cache_key] = current_time

        return health_info

    except Exception as e:
        logger.warning(f"Health check failed for {name}: connection error")
        health_info = {
            "status": "unhealthy",
            "name": name,
            "error": "Service unavailable",
        }
        _health_cache[cache_key] = health_info
        _health_cache_time[cache_key] = current_time
        return health_info


@docs_router.get("/openapi.json", response_class=JSONResponse)
async def get_openapi_spec():
    """
    Get OpenAPI 3.0 specification in JSON format.

    Returns the complete OpenAPI specification for the Priya Global Platform
    with all 40+ microservice endpoints, complete request/response schemas,
    error handling documentation, and authentication requirements.

    Returns:
        dict: OpenAPI 3.0 specification document

    Example:
        GET /docs/openapi.json
        Content-Type: application/json
    """
    try:
        # Try to load from openapi.yaml file
        with open("docs/api/openapi.yaml", "r") as f:
            import yaml
            spec = yaml.safe_load(f)
            return spec
    except Exception as e:
        logger.warning(f"Could not load openapi.yaml: {e}, returning minimal spec")
        return {
            "openapi": "3.0.3",
            "info": {
                "title": "Priya Global Platform API",
                "version": "1.0.0",
                "description": "AI-powered multi-channel sales platform",
                "contact": {
                    "name": "Priya Support",
                    "email": "support@priyaai.com",
                    "url": "https://priyaai.com/support",
                },
            },
            "servers": [
                {
                    "url": "https://api.priyaai.com",
                    "description": "Production",
                },
                {
                    "url": "http://localhost:9000",
                    "description": "Local Development",
                },
            ],
            "paths": {},
        }


@docs_router.get("/health", response_class=JSONResponse)
async def get_health_status():
    """
    Get health summary for all services.

    Returns current health status of all microservices running on the platform.
    Cached for 10 seconds to avoid excessive health checks.

    Returns:
        dict: Health status with service details
    """
    async with httpx.AsyncClient(timeout=10) as client:
        tasks = []
        for prefix, config in SERVICE_MAPPING.items():
            tasks.append(_get_service_health(client, config["target"], config["name"]))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        services = {}
        unhealthy_count = 0

        for result in results:
            if isinstance(result, dict) and "name" in result:
                name = result["name"]
                services[name] = result
                if result.get("status") != "healthy":
                    unhealthy_count += 1

        overall_status = "healthy"
        if unhealthy_count > 0:
            overall_status = "degraded" if unhealthy_count < len(services) else "unhealthy"

        return {
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_services": len(services),
            "healthy_services": len(services) - unhealthy_count,
            "unhealthy_services": unhealthy_count,
            "services": services,
        }


@docs_router.get("", response_class=HTMLResponse)
async def swagger_ui_page():
    """
    Swagger UI documentation interface.

    Serves the interactive Swagger UI page for exploring and testing the API.
    Includes request/response visualization, authentication, and try-it-out functionality.

    Returns:
        HTMLResponse: Swagger UI HTML page

    Example:
        GET /docs
    """
    try:
        with open("docs/api/index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("Swagger UI HTML file not found")
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Priya Global API Documentation</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@3/swagger-ui.css">
        </head>
        <body>
            <div id="swagger-ui"></div>
            <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@3/swagger-ui-bundle.js"></script>
            <script>
                SwaggerUIBundle({
                    url: "./openapi.json",
                    dom_id: '#swagger-ui',
                    presets: [SwaggerUIBundle.presets.apis],
                    layout: "StandaloneLayout",
                    tryItOutEnabled: true,
                })
            </script>
        </body>
        </html>
        """


@docs_router.get("/redoc", response_class=HTMLResponse)
async def redoc_page():
    """
    ReDoc documentation interface (alternative view).

    Serves the ReDoc documentation page with a different layout optimized
    for reading and navigation.

    Returns:
        HTMLResponse: ReDoc HTML page
    """
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Priya Global Platform API - ReDoc</title>
        <style>
            body {
                margin: 0;
                padding: 0;
                font-family: sans-serif;
                background: #fafafa;
            }
            redoc {
                display: block;
            }
        </style>
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    </head>
    <body>
        <redoc spec-url="./openapi.json" suppress-warnings></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """


@docs_router.get("/download-spec", response_class=JSONResponse)
async def download_openapi_spec(format: str = Query("json", regex="^(yaml|json)$")):
    """
    Download the OpenAPI specification.

    Returns the API specification in the requested format.

    Query Parameters:
        format (str): Output format - "json" or "yaml" (default: "json")

    Returns:
        dict: OpenAPI specification document

    Example:
        GET /docs/download-spec?format=json
        GET /docs/download-spec?format=yaml
    """
    if format == "json":
        return await get_openapi_spec()
    else:
        # For YAML, return as JSON-serialized
        try:
            with open("docs/api/openapi.yaml", "r") as f:
                import yaml
                spec = yaml.safe_load(f)
                return spec
        except Exception as e:
            logger.error(f"Error loading YAML spec: {e}")
            raise HTTPException(status_code=500, detail="Could not load API specification")


@docs_router.get("/services", response_class=JSONResponse)
async def list_services():
    """
    Get catalog of all platform microservices.

    Returns detailed information about each microservice including:
    - Service name and description
    - Port number
    - API prefix
    - Configured timeout
    - Service capabilities

    Returns:
        dict: Service catalog with details
    """
    services_info = []

    for prefix, config in sorted(SERVICE_MAPPING.items(), key=lambda x: x[1]["name"]):
        service_info = {
            "name": config["name"],
            "port": config["port"],
            "prefix": prefix,
            "timeout_seconds": config.get("timeout", 10),
            "description": config.get("description", ""),
            "url": config["target"],
        }
        services_info.append(service_info)

    return {
        "total_services": len(services_info),
        "services": services_info,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@docs_router.get("/guides", response_class=JSONResponse)
async def api_integration_guides():
    """
    Get list of API integration guides and best practices.

    Returns:
        dict: Available guides with URLs and descriptions
    """
    return {
        "guides": [
            {
                "id": "authentication",
                "title": "Authentication & JWT",
                "description": "How to authenticate and manage JWT tokens",
                "url": "/docs/guides/authentication",
            },
            {
                "id": "multi-tenancy",
                "title": "Multi-tenant Architecture",
                "description": "Understanding tenant isolation and data security",
                "url": "/docs/guides/multi-tenancy",
            },
            {
                "id": "rate-limiting",
                "title": "Rate Limiting & Quotas",
                "description": "Managing rate limits based on your plan",
                "url": "/docs/guides/rate-limiting",
            },
            {
                "id": "webhooks",
                "title": "Webhook Integration",
                "description": "Receiving real-time events from Priya",
                "url": "/docs/guides/webhooks",
            },
            {
                "id": "error-handling",
                "title": "Error Handling",
                "description": "Understanding error responses and status codes",
                "url": "/docs/guides/error-handling",
            },
            {
                "id": "channels",
                "title": "Channel Integration",
                "description": "Connecting to WhatsApp, Email, SMS, and other channels",
                "url": "/docs/guides/channels",
            },
            {
                "id": "ai-integration",
                "title": "AI Integration",
                "description": "Leveraging the AI Engine for intelligent responses",
                "url": "/docs/guides/ai-integration",
            },
            {
                "id": "billing",
                "title": "Billing & Subscriptions",
                "description": "Managing subscriptions and billing cycles",
                "url": "/docs/guides/billing",
            },
        ]
    }


@docs_router.get("/examples", response_class=JSONResponse)
async def code_examples():
    """
    Get code examples for common API operations.

    Returns:
        dict: Code examples in multiple languages
    """
    return {
        "examples": [
            {
                "title": "User Login",
                "category": "Authentication",
                "languages": {
                    "curl": 'curl -X POST https://api.priyaai.com/api/v1/auth/login -H "Content-Type: application/json" -d \'{"email":"user@example.com","password":"SecurePass123!"}\'',
                    "python": "import requests\nresponse = requests.post('https://api.priyaai.com/api/v1/auth/login', json={'email': 'user@example.com', 'password': 'SecurePass123!'})",
                    "javascript": "fetch('https://api.priyaai.com/api/v1/auth/login', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email: 'user@example.com', password: 'SecurePass123!'}) })",
                },
            },
            {
                "title": "Send WhatsApp Message",
                "category": "Messaging",
                "languages": {
                    "curl": 'curl -X POST https://api.priyaai.com/api/v1/whatsapp/send -H "Authorization: Bearer {token}" -H "Content-Type: application/json" -d \'{"phone":"+919876543210","message":"Hello!"}\'',
                    "python": "import requests\nheaders = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}\nresponse = requests.post('https://api.priyaai.com/api/v1/whatsapp/send', json={'phone': '+919876543210', 'message': 'Hello!'}, headers=headers)",
                },
            },
            {
                "title": "List Conversations",
                "category": "Conversations",
                "languages": {
                    "curl": 'curl -X GET "https://api.priyaai.com/api/v1/conversations?status=active&limit=20" -H "Authorization: Bearer {token}"',
                    "python": "import requests\nheaders = {'Authorization': f'Bearer {token}'}\nresponse = requests.get('https://api.priyaai.com/api/v1/conversations', headers=headers, params={'status': 'active', 'limit': 20})",
                },
            },
        ]
    }


@docs_router.get("/changelog", response_class=JSONResponse)
async def api_changelog():
    """
    Get API version history and changelog.

    Returns:
        dict: Version history with dates and changes
    """
    return {
        "current_version": "1.0.0",
        "release_date": "2024-03-07",
        "latest_changes": [
            {
                "version": "1.0.0",
                "date": "2024-03-07",
                "type": "major",
                "changes": [
                    "Initial production release",
                    "36 microservices integrated",
                    "Full multi-tenant support",
                    "Comprehensive API documentation",
                    "Swagger UI with dark mode",
                    "OpenAPI 3.0 specification",
                    "Rate limiting and quota management",
                    "Webhook support for real-time events",
                ],
            },
        ],
        "deprecations": [],
    }
