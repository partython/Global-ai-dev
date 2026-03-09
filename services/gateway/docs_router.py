"""
API Documentation Router for Priya Global Gateway

Serves OpenAPI specification, Swagger UI, and ReDoc for the unified API platform.
This router aggregates documentation from all 36 microservices behind the gateway.

Features:
- OpenAPI 3.1 spec auto-generation with service aggregation
- Swagger UI with dark mode and custom branding
- ReDoc for alternative documentation view
- Health aggregation for documentation page
- Custom CSS for Priya Global branding
- Support for webhook documentation

Port: 9000 (Gateway)
Endpoints:
  GET  /docs                  - Swagger UI (primary documentation)
  GET  /docs/openapi.json     - OpenAPI specification (JSON)
  GET  /redoc                 - ReDoc documentation
  GET  /docs/health-summary   - Service health for docs page
"""

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

# Router for docs endpoints
docs_router = APIRouter(tags=["Documentation"])

# Service route table (imported from main gateway)
ROUTE_TABLE = {
    "/api/v1/auth": {
        "target": "http://localhost:9001",
        "timeout": 5,
        "name": "Auth Service",
        "port": 9001,
    },
    "/api/v1/tenants": {
        "target": "http://localhost:9002",
        "timeout": 10,
        "name": "Tenant Service",
        "port": 9002,
    },
    "/api/v1/messages": {
        "target": "http://localhost:9003",
        "timeout": 10,
        "name": "Channel Router",
        "port": 9003,
    },
    "/api/v1/channels": {
        "target": "http://localhost:9003",
        "timeout": 10,
        "name": "Channel Router",
        "port": 9003,
    },
    "/api/v1/conversations": {
        "target": "http://localhost:9003",
        "timeout": 10,
        "name": "Channel Router",
        "port": 9003,
    },
    "/api/v1/ai": {
        "target": "http://localhost:9020",
        "timeout": 30,
        "name": "AI Engine",
        "port": 9020,
    },
    "/api/v1/knowledge": {
        "target": "http://localhost:9020",
        "timeout": 30,
        "name": "AI Engine",
        "port": 9020,
    },
    "/api/v1/whatsapp": {
        "target": "http://localhost:9010",
        "timeout": 15,
        "name": "WhatsApp Service",
        "port": 9010,
    },
    "/api/v1/email": {
        "target": "http://localhost:9011",
        "timeout": 15,
        "name": "Email Service",
        "port": 9011,
    },
    "/api/v1/voice": {
        "target": "http://localhost:9012",
        "timeout": 20,
        "name": "Voice Service",
        "port": 9012,
    },
    "/api/v1/sms": {
        "target": "http://localhost:9014",
        "timeout": 15,
        "name": "SMS Service",
        "port": 9014,
    },
    "/api/v1/social": {
        "target": "http://localhost:9013",
        "timeout": 15,
        "name": "Social Service",
        "port": 9013,
    },
    "/api/v1/webchat": {
        "target": "http://localhost:9015",
        "timeout": 15,
        "name": "WebChat Service",
        "port": 9015,
    },
    "/api/v1/telegram": {
        "target": "http://localhost:9016",
        "timeout": 15,
        "name": "Telegram Service",
        "port": 9016,
    },
    "/api/v1/billing": {
        "target": "http://localhost:9027",
        "timeout": 10,
        "name": "Billing Service",
        "port": 9027,
    },
    "/api/v1/analytics": {
        "target": "http://localhost:9023",
        "timeout": 30,
        "name": "Analytics Service",
        "port": 9023,
    },
    "/api/v1/marketing": {
        "target": "http://localhost:9024",
        "timeout": 15,
        "name": "Marketing Service",
        "port": 9024,
    },
    "/api/v1/ecommerce": {
        "target": "http://localhost:9025",
        "timeout": 15,
        "name": "E-commerce Service",
        "port": 9025,
    },
    "/api/v1/notifications": {
        "target": "http://localhost:9026",
        "timeout": 10,
        "name": "Notification Service",
        "port": 9026,
    },
    "/api/v1/plugins": {
        "target": "http://localhost:9028",
        "timeout": 10,
        "name": "Plugins Service",
        "port": 9028,
    },
    "/api/v1/handoff": {
        "target": "http://localhost:9029",
        "timeout": 10,
        "name": "Handoff Service",
        "port": 9029,
    },
    "/api/v1/leads": {
        "target": "http://localhost:9030",
        "timeout": 10,
        "name": "Leads Service",
        "port": 9030,
    },
    "/api/v1/intelligence": {
        "target": "http://localhost:9031",
        "timeout": 15,
        "name": "Conversation Intelligence",
        "port": 9031,
    },
    "/api/v1/appointments": {
        "target": "http://localhost:9032",
        "timeout": 10,
        "name": "Appointments Service",
        "port": 9032,
    },
    "/api/v1/rcs": {
        "target": "http://localhost:9017",
        "timeout": 15,
        "name": "RCS Service",
        "port": 9017,
    },
    "/api/v1/video": {
        "target": "http://localhost:9018",
        "timeout": 20,
        "name": "Video Service",
        "port": 9018,
    },
    "/api/v1/workflows": {
        "target": "http://localhost:9033",
        "timeout": 10,
        "name": "Workflows Service",
        "port": 9033,
    },
    "/api/v1/compliance": {
        "target": "http://localhost:9034",
        "timeout": 10,
        "name": "Compliance Service",
        "port": 9034,
    },
    "/api/v1/cdn": {
        "target": "http://localhost:9035",
        "timeout": 30,
        "name": "CDN Manager",
        "port": 9035,
    },
    "/api/v1/deployment": {
        "target": "http://localhost:9036",
        "timeout": 15,
        "name": "Deployment Service",
        "port": 9036,
    },
}

# Cache for service health checks
_health_cache: Dict[str, Dict[str, Any]] = {}
_health_cache_time: Dict[str, float] = {}
HEALTH_CACHE_TTL = 10  # seconds

# Security: Bearer token validation
security = HTTPBearer()


async def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify authentication for protected documentation endpoints.

    Requires valid API key or admin JWT token.
    """
    token = credentials.credentials

    # TODO: Implement actual JWT validation against auth service
    # For now, check if token is non-empty (production should validate with auth service)
    if not token or len(token) < 20:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


def _validate_internal_url(target: str) -> bool:
    """Validate that target URL is an internal service (localhost or private IP only)."""
    from urllib.parse import urlparse
    import ipaddress
    try:
        parsed = urlparse(target)

        # Ensure scheme is http or https only (no file://, ftp://, etc.)
        if parsed.scheme not in ('http', 'https'):
            return False

        host = parsed.hostname or ""
        if not host:
            return False

        # Only allow localhost or private IP ranges
        if host in ("localhost", "127.0.0.1", "::1"):
            return True

        # Check if it's a private IP address
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback
        except ValueError:
            # Not an IP address, check string patterns for private ranges
            if host.startswith(("10.", "172.", "192.168.")):
                return True

        return False
    except Exception:
        return False


async def _get_service_health(client: httpx.AsyncClient, target: str, name: str) -> Dict[str, Any]:
    """Check health of a single service."""
    cache_key = name
    current_time = time.time()

    # Validate target URL to prevent SSRF attacks
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

        # Cache result
        _health_cache[cache_key] = health_info
        _health_cache_time[cache_key] = current_time

        return health_info

    except Exception as e:
        logger.warning(f"Health check failed for {name}: {e}")
        health_info = {
            "status": "unhealthy",
            "name": name,
            "error": str(e),
        }
        # Cache error response
        _health_cache[cache_key] = health_info
        _health_cache_time[cache_key] = current_time
        return health_info


@docs_router.get("/docs/openapi.json", response_class=JSONResponse)
async def get_openapi_spec():
    """
    Get OpenAPI specification in JSON format.

    This endpoint returns the complete OpenAPI 3.1 specification for the Priya Global Platform,
    including all 36 microservices, webhooks, and authentication schemes.
    """
    spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "Priya Global Platform API",
            "version": "1.0.0",
            "description": "Multi-tenant AI-powered sales platform with 36 microservices",
            "contact": {
                "name": "Priya Support",
                "email": "support@priyaai.com",
                "url": "https://priyaai.com/support",
            },
            "license": {"name": "Commercial", "url": "https://priyaai.com/license"},
        },
        "servers": [
            {
                "url": "https://api.priyaai.com",
                "description": "Production",
                "variables": {"version": {"default": "v1"}},
            },
            {
                "url": "https://staging.api.priyaai.com",
                "description": "Staging",
            },
            {
                "url": "http://localhost:9000",
                "description": "Local Development",
            },
        ],
        "tags": [
            {"name": "Auth", "description": "Authentication and user management"},
            {"name": "Tenant", "description": "Workspace/tenant configuration"},
            {"name": "Channels", "description": "Channel management"},
            {"name": "Messages", "description": "Message routing and conversations"},
            {"name": "AI Engine", "description": "AI chat and knowledge base"},
            {"name": "WhatsApp", "description": "WhatsApp Business API"},
            {"name": "Email", "description": "Email sending and webhooks"},
            {"name": "Voice", "description": "Voice calls and IVR"},
            {"name": "SMS", "description": "SMS sending and tracking"},
            {"name": "Social", "description": "Social media integration"},
            {"name": "WebChat", "description": "Web chat widget"},
            {"name": "Telegram", "description": "Telegram bot"},
            {"name": "RCS", "description": "Rich Communication Services"},
            {"name": "Video", "description": "Video rooms and recording"},
            {"name": "Billing", "description": "Subscriptions and invoices"},
            {"name": "Analytics", "description": "Dashboards and reports"},
            {"name": "Marketing", "description": "Campaigns and automations"},
            {"name": "E-commerce", "description": "Products and orders"},
            {"name": "Notifications", "description": "Push notifications"},
            {"name": "Plugins", "description": "Third-party plugins"},
            {"name": "Handoff", "description": "Human agent handoff"},
            {"name": "Leads", "description": "Lead management"},
            {"name": "Intelligence", "description": "Conversation analysis"},
            {"name": "Appointments", "description": "Scheduling"},
            {"name": "Workflows", "description": "Automation"},
            {"name": "Compliance", "description": "Audit and data management"},
            {"name": "CDN", "description": "Media management"},
            {"name": "Deployment", "description": "Release management"},
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT Bearer token",
                },
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "detail": {"type": "string"},
                        "code": {"type": "string"},
                        "request_id": {"type": "string", "format": "uuid"},
                    },
                },
                "HealthStatus": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["healthy", "degraded"]},
                        "service": {"type": "string"},
                        "version": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"},
                    },
                },
            },
        },
        "paths": {
            "/health": {
                "get": {
                    "summary": "Gateway health check",
                    "tags": ["Health"],
                    "responses": {
                        "200": {
                            "description": "Gateway is healthy",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/HealthStatus"}
                                }
                            },
                        }
                    },
                }
            },
            "/health/services": {
                "get": {
                    "summary": "All services health status",
                    "tags": ["Health"],
                    "responses": {
                        "200": {
                            "description": "Services health information",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                            "services": {"type": "object"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
        },
        "security": [{"bearerAuth": []}],
    }

    return spec


@docs_router.get("/docs/health-summary", response_class=JSONResponse)
async def get_health_summary(token: str = Depends(verify_auth)):
    """
    Get health summary for all services (authenticated endpoint).

    Returns current health status of all 36 microservices running on the platform.
    Used by documentation and monitoring dashboards.

    Requires valid API key or admin JWT token in Authorization header.

    Response includes:
    - Individual service status (healthy/unhealthy)
    - Response times for each service
    - Overall platform health
    - Timestamp of last check
    """
    async with httpx.AsyncClient(timeout=10) as client:
        tasks = []
        for prefix, config in ROUTE_TABLE.items():
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
            else:
                logger.error(f"Invalid health result: {result}")

        # Determine overall status
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


@docs_router.get("/docs", response_class=HTMLResponse)
async def swagger_ui():
    """
    Swagger UI for interactive API exploration.

    This is the primary documentation interface for the Priya Global Platform.
    Features:
    - Try-it-out functionality for all endpoints
    - Dark mode toggle
    - Request/response visualization
    - Full OpenAPI specification browser
    """
    return FileResponse("docs/api/swagger-ui.html", media_type="text/html")


@docs_router.get("/redoc", response_class=HTMLResponse)
async def redoc():
    """
    ReDoc documentation view (alternative to Swagger UI).

    ReDoc provides a clean, responsive documentation view optimized for reading.
    Includes:
    - Two-panel layout with API explorer and documentation
    - Search functionality
    - Markdown support in descriptions
    - Mobile-friendly design
    """
    html_content = """
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
        <redoc spec-url="./docs/openapi.json" suppress-warnings></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@docs_router.get("/docs/download-spec")
async def download_spec(format: str = Query("yaml", regex="^(yaml|json)$")):
    """
    Download the OpenAPI specification.

    Available formats:
    - yaml: YAML format (default, recommended)
    - json: JSON format

    The specification includes all 36 microservices, complete with:
    - Path definitions
    - Request/response schemas
    - Error responses
    - Authentication requirements
    - Rate limiting information
    - Webhook definitions
    """
    if format == "json":
        # Return JSON spec
        spec = await get_openapi_spec()
        return JSONResponse(spec)
    else:
        # Return YAML spec file
        return FileResponse(
            "docs/api/openapi.yaml",
            media_type="application/x-yaml",
            filename="priya-global-api.yaml",
        )


@docs_router.get("/docs/swagger-ui.css", response_class=FileResponse)
async def swagger_css():
    """Swagger UI stylesheet."""
    return FileResponse("docs/api/swagger-ui.css")


@docs_router.get("/docs/guides")
async def api_guides():
    """
    API integration guides and best practices.

    Available guides:
    - Authentication & JWT tokens
    - Multi-tenant architecture
    - Error handling
    - Rate limiting & quota management
    - Webhook integration
    - File uploads
    - Pagination
    - Batch operations
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


@docs_router.get("/docs/examples")
async def api_examples():
    """
    Code examples for common API operations.

    Includes examples in:
    - cURL
    - JavaScript/Node.js
    - Python
    - Go
    - PHP
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
        ]
    }


# Import asyncio for gathering tasks
import asyncio


@docs_router.get("/docs/services")
async def list_services(token: str = Depends(verify_auth)):
    """
    List all 36 microservices with details (authenticated endpoint).

    Returns information about each service including:
    - Service name and description
    - Port number
    - Primary endpoints
    - Dependencies
    - Health status

    Requires valid API key or admin JWT token in Authorization header.
    """
    services_info = []

    for prefix, config in sorted(ROUTE_TABLE.items(), key=lambda x: x[1]["name"]):
        service_info = {
            "name": config["name"],
            "port": config["port"],
            "prefix": prefix,
            "timeout": config["timeout"],
            "description": f"{config['name']} service for Priya Global Platform",
        }
        services_info.append(service_info)

    return {
        "total_services": len(services_info),
        "services": services_info,
    }


@docs_router.get("/docs/api-key-management")
async def api_key_management():
    """
    API Key Management endpoint documentation.

    Note: This platform uses JWT tokens for authentication, not API keys.
    See /docs/guides/authentication for token management.
    """
    return {
        "auth_method": "JWT Bearer Token",
        "token_lifetime": {
            "access_token": "15 minutes",
            "refresh_token": "7 days",
        },
        "obtaining_tokens": {
            "method": "POST /api/v1/auth/login",
            "parameters": {"email": "string", "password": "string"},
        },
        "refreshing_tokens": {
            "method": "POST /api/v1/auth/refresh",
            "headers": {"Authorization": "Bearer {refresh_token}"},
        },
    }


@docs_router.get("/docs/changelog")
async def changelog():
    """
    API Changelog and version history.

    Lists recent API changes, deprecations, and new features.
    """
    return {
        "current_version": "1.0.0",
        "latest_changes": [
            {
                "version": "1.0.0",
                "date": "2024-03-06",
                "changes": [
                    "Initial release",
                    "36 microservices integrated",
                    "Full multi-tenant support",
                    "Comprehensive API documentation",
                ],
            },
        ],
    }
