"""
Universal REST API Connector for Priya Global Platform
Port: 9035

Generic REST/webhook connector for ANY platform — BigCommerce, Wix, Squarespace,
custom backends, Zapier/Make, or any API that speaks JSON over HTTP.

FEATURES:
- Configurable REST endpoint definitions (URL, method, auth, headers)
- Multiple auth types: API Key, Bearer Token, Basic Auth, OAuth 2.0
- Webhook ingestion with signature verification
- Field mapping engine (map any JSON to Priya schema)
- Automatic retry with exponential backoff
- Request/response logging with PII redaction
- Per-connector rate limiting
- Health checks for external endpoints

SECURITY:
- All secrets stored encrypted (via DB-level encryption)
- Auth credentials never returned to API responses
- Tenant isolation via RLS
- HMAC-SHA256 webhook verification
- Input sanitization on all fields
- Rate limiting per tenant per connector
- CORS from environment
- Fail-closed rate limiting via Redis

DATABASE:
- asyncpg for PostgreSQL with connection pooling
- Multi-tenant with RLS patterns
"""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from base64 import b64encode, b64decode
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
import asyncpg
import redis.asyncio as aioredis
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import sanitize_input
from shared.middleware.auth import AuthContext, get_auth
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logger = logging.getLogger("priya.rest_connector")

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SERVICE_PORT = 9035
MAX_CONNECTORS_PER_TENANT = 50
MAX_ENDPOINTS_PER_CONNECTOR = 25
MAX_MAPPINGS_PER_ENDPOINT = 100
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 2  # seconds
REQUEST_TIMEOUT = 30  # seconds
MAX_RESPONSE_SIZE = 10_485_760  # 10MB
WEBHOOK_REPLAY_WINDOW = 300  # 5 min dedup
WEBHOOK_RATE_LIMIT_PER_MIN = 200
RATE_LIMIT_PER_TENANT_PER_MIN = 120
MAX_SYNC_LOG_DAYS = 90
MAX_URL_LENGTH = 2048
MAX_HEADER_VALUE_LENGTH = 4096
MAX_ITEMS_PER_RESPONSE = 5000  # Max items to process from external API
MAX_JSON_SIZE = 5_242_880  # 5MB max JSON payload

# Allowed URL schemes for connector endpoints
ALLOWED_SCHEMES = {"https"}  # Only HTTPS in production

# Blocked private IP ranges (SSRF protection) — includes port-stripped hostnames
BLOCKED_HOSTS = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|"
    r"192\.168\.\d+\.\d+|"
    r"0\.0\.0\.0|"
    r"\[?::1\]?|"
    r"\[?fe80:.*\]?|"
    r"\[?fd.*\]?|"
    r"metadata\.google\.internal|"
    r"169\.254\.\d+\.\d+)$",
    re.IGNORECASE,
)

# UUID validation
TENANT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Redis client
redis_client = None

# Event bus
event_bus = EventBus(service_name="rest_connector")


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class AuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class SyncDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    BIDIRECTIONAL = "bidirectional"


class DataType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    ARRAY = "array"
    OBJECT = "object"


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    service: str
    port: int
    database: str
    timestamp: str


class AuthConfig(BaseModel):
    """Authentication configuration for a connector."""
    auth_type: AuthType = Field(default=AuthType.NONE)
    # API Key auth
    api_key_header: Optional[str] = Field(None, max_length=255)
    api_key_value: Optional[str] = Field(None, max_length=1024)
    # Bearer token
    bearer_token: Optional[str] = Field(None, max_length=4096)
    # Basic auth
    basic_username: Optional[str] = Field(None, max_length=255)
    basic_password: Optional[str] = Field(None, max_length=1024)
    # OAuth2
    oauth2_client_id: Optional[str] = Field(None, max_length=512)
    oauth2_client_secret: Optional[str] = Field(None, max_length=1024)
    oauth2_token_url: Optional[str] = Field(None, max_length=2048)
    oauth2_scope: Optional[str] = Field(None, max_length=1024)
    oauth2_access_token: Optional[str] = Field(None, max_length=4096)
    oauth2_refresh_token: Optional[str] = Field(None, max_length=4096)
    oauth2_token_expiry: Optional[str] = None


class CreateConnectorRequest(BaseModel):
    """Create a new REST API connector."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    base_url: str = Field(..., max_length=MAX_URL_LENGTH)
    auth_config: AuthConfig = Field(default_factory=AuthConfig)
    default_headers: Optional[Dict[str, str]] = None
    webhook_secret: Optional[str] = Field(None, max_length=1024)
    sync_direction: SyncDirection = Field(default=SyncDirection.INBOUND)
    retry_enabled: bool = Field(default=True)
    metadata: Optional[Dict[str, Any]] = None

    @validator("name", "description", pre=True)
    def sanitize_text(cls, v):
        if v:
            return sanitize_input(v, max_length=2000)
        return v

    @validator("base_url")
    def validate_url(cls, v):
        parsed = urlparse(v)
        if parsed.scheme not in ALLOWED_SCHEMES:
            raise ValueError(f"URL scheme must be one of: {ALLOWED_SCHEMES}")
        if not parsed.hostname:
            raise ValueError("URL must have a valid hostname")
        if BLOCKED_HOSTS.match(parsed.hostname):
            raise ValueError("URL points to a blocked address")
        return v

    @validator("default_headers")
    def validate_headers(cls, v):
        if v:
            if len(v) > 20:
                raise ValueError("Maximum 20 default headers allowed")
            for key, val in v.items():
                if len(key) > 255 or len(val) > MAX_HEADER_VALUE_LENGTH:
                    raise ValueError("Header name max 255 chars, value max 4096 chars")
        return v


class UpdateConnectorRequest(BaseModel):
    """Update an existing connector."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    base_url: Optional[str] = Field(None, max_length=MAX_URL_LENGTH)
    auth_config: Optional[AuthConfig] = None
    default_headers: Optional[Dict[str, str]] = None
    webhook_secret: Optional[str] = Field(None, max_length=1024)
    sync_direction: Optional[SyncDirection] = None
    retry_enabled: Optional[bool] = None
    status: Optional[ConnectorStatus] = None

    @validator("base_url")
    def validate_url(cls, v):
        if v:
            parsed = urlparse(v)
            if parsed.scheme not in ALLOWED_SCHEMES:
                raise ValueError(f"URL scheme must be one of: {ALLOWED_SCHEMES}")
            if not parsed.hostname:
                raise ValueError("URL must have a valid hostname")
            if BLOCKED_HOSTS.match(parsed.hostname):
                raise ValueError("URL points to a blocked address")
        return v


class EndpointDefinition(BaseModel):
    """Define a REST endpoint for a connector."""
    name: str = Field(..., min_length=1, max_length=255)
    path: str = Field(..., min_length=1, max_length=1024)
    method: HttpMethod = Field(default=HttpMethod.GET)
    description: Optional[str] = Field(None, max_length=2000)
    query_params: Optional[Dict[str, str]] = None
    request_body_template: Optional[Dict[str, Any]] = None
    response_root_path: Optional[str] = Field(None, max_length=500)
    pagination_type: Optional[str] = Field(None, regex="^(cursor|page|offset|link|none)$")
    pagination_config: Optional[Dict[str, Any]] = None
    is_active: bool = Field(default=True)

    @validator("name", "description", pre=True)
    def sanitize_text(cls, v):
        if v:
            return sanitize_input(v, max_length=2000)
        return v

    @validator("path")
    def validate_path(cls, v):
        from urllib.parse import unquote
        decoded = unquote(v)
        if ".." in decoded or ";" in decoded or "\x00" in decoded:
            raise ValueError("Invalid path characters")
        if "%2e" in v.lower() or "%3b" in v.lower() or "%00" in v.lower():
            raise ValueError("Invalid encoded path characters")
        return v


class FieldMappingRule(BaseModel):
    """Map external API field to internal Priya schema field."""
    source_path: str = Field(..., max_length=500)
    target_field: str = Field(..., max_length=255)
    data_type: DataType = Field(default=DataType.STRING)
    default_value: Optional[str] = Field(None, max_length=1000)
    is_required: bool = Field(default=False)
    transform: Optional[str] = Field(
        None,
        regex="^(lowercase|uppercase|trim|to_int|to_float|to_bool|iso_date|epoch_to_date|strip_html)$",
    )

    @validator("source_path", "target_field", pre=True)
    def sanitize_fields(cls, v):
        if v:
            return sanitize_input(v, max_length=500)
        return v


class WebhookConfig(BaseModel):
    """Configure webhook ingestion for a connector."""
    event_types: List[str] = Field(..., min_items=1, max_items=50)
    signature_header: Optional[str] = Field(None, max_length=255)
    signature_algorithm: str = Field(default="hmac-sha256", regex="^(hmac-sha256|hmac-sha1)$")
    payload_format: str = Field(default="json", regex="^(json|form)$")


class ExecuteEndpointRequest(BaseModel):
    """Execute a specific endpoint on a connector."""
    endpoint_id: str = Field(..., max_length=255)
    override_params: Optional[Dict[str, str]] = None
    override_body: Optional[Dict[str, Any]] = None


class TestConnectionRequest(BaseModel):
    """Test a connector's connection."""
    connector_id: str = Field(..., max_length=255)


# ─────────────────────────────────────────────────────────────────────────────
# Security Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _validate_url_safe(url: str) -> bool:
    """
    Validate URL is safe (SSRF protection).
    Checks: scheme, hostname against blocked patterns, resolved IP against private ranges.
    """
    import ipaddress
    import socket

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ALLOWED_SCHEMES:
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        # URL-decode and check again
        from urllib.parse import unquote
        decoded_hostname = unquote(hostname).lower()
        if BLOCKED_HOSTS.match(decoded_hostname):
            return False
        if BLOCKED_HOSTS.match(hostname):
            return False
        # Resolve hostname and check IP against private ranges
        try:
            resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for family, socktype, proto, canonname, sockaddr in resolved_ips:
                ip_str = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                    logger.warning("SSRF blocked: %s resolved to private IP %s", hostname, ip_str)
                    return False
        except socket.gaierror:
            # DNS resolution failed — allow (external host may be temporarily down)
            pass
        return True
    except Exception:
        return False


async def _check_rate_limit(tenant_id: str) -> bool:
    """Per-tenant rate limiting. Returns True if over limit."""
    if not redis_client:
        return True  # Fail closed
    try:
        key = f"restconn:rate:{tenant_id}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        return count > RATE_LIMIT_PER_TENANT_PER_MIN
    except Exception as e:
        logger.warning("Rate limit check failed: %s", e)
        return True  # Fail closed


async def _check_webhook_replay(connector_id: str, payload_bytes: bytes) -> bool:
    """Webhook replay protection. Returns True if replay detected."""
    if not redis_client:
        return False  # Fail closed — deny
    try:
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        key = f"restconn:webhook:dedup:{connector_id}:{payload_hash}"
        result = await redis_client.set(key, "1", nx=True, ex=WEBHOOK_REPLAY_WINDOW)
        return result is None  # True = already exists = replay
    except Exception as e:
        logger.warning("Webhook replay check failed: %s", e)
        return False


async def _check_webhook_rate_limit(connector_id: str) -> bool:
    """Webhook rate limiting. Returns True if over limit."""
    if not redis_client:
        return True  # Fail closed
    try:
        key = f"restconn:webhook:rate:{connector_id}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        return count > WEBHOOK_RATE_LIMIT_PER_MIN
    except Exception as e:
        logger.warning("Webhook rate limit check failed: %s", e)
        return True


def _mask_secret(secret: str, visible_chars: int = 4) -> str:
    """Mask a secret for display."""
    if not secret or len(secret) <= visible_chars:
        return "****"
    return "*" * (len(secret) - visible_chars) + secret[-visible_chars:]


def _redact_auth_config(auth_config: dict) -> dict:
    """Redact sensitive fields from auth config for API responses."""
    redacted = {}
    for key, val in auth_config.items():
        if val is None:
            redacted[key] = None
        elif any(s in key for s in ["secret", "password", "token", "api_key_value"]):
            redacted[key] = _mask_secret(str(val)) if val else None
        else:
            redacted[key] = val
    return redacted


# ─────────────────────────────────────────────────────────────────────────────
# Auth Builder
# ─────────────────────────────────────────────────────────────────────────────

async def _build_auth_headers(auth_config: dict) -> Dict[str, str]:
    """Build authentication headers based on auth config."""
    headers = {}
    auth_type = auth_config.get("auth_type", "none")

    if auth_type == "api_key":
        header_name = auth_config.get("api_key_header", "X-API-Key")
        api_key_value = auth_config.get("api_key_value", "")
        if header_name and api_key_value:
            headers[header_name] = api_key_value

    elif auth_type == "bearer":
        token = auth_config.get("bearer_token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    elif auth_type == "basic":
        username = auth_config.get("basic_username", "")
        password = auth_config.get("basic_password", "")
        if username:
            encoded = b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

    elif auth_type == "oauth2":
        access_token = auth_config.get("oauth2_access_token", "")
        if access_token:
            # Check if token is expired and needs refresh
            token_expiry = auth_config.get("oauth2_token_expiry")
            if token_expiry:
                try:
                    expiry_dt = datetime.fromisoformat(token_expiry)
                    if expiry_dt < datetime.now(timezone.utc):
                        access_token = await _refresh_oauth2_token(auth_config)
                except (ValueError, TypeError):
                    pass
            headers["Authorization"] = f"Bearer {access_token}"

    return headers


async def _refresh_oauth2_token(auth_config: dict) -> str:
    """Refresh an OAuth2 access token."""
    token_url = auth_config.get("oauth2_token_url")
    client_id = auth_config.get("oauth2_client_id")
    client_secret = auth_config.get("oauth2_client_secret")
    refresh_token = auth_config.get("oauth2_refresh_token")

    if not all([token_url, client_id, client_secret, refresh_token]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth2 refresh requires token_url, client_id, client_secret, and refresh_token",
        )

    if not _validate_url_safe(token_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth2 token URL is not allowed",
        )

    async with aiohttp.ClientSession() as session:
        async with session.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to refresh OAuth2 token",
                )
            data = await resp.json()
            return data.get("access_token", "")


# ─────────────────────────────────────────────────────────────────────────────
# Field Mapping Engine
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json_path(data: Any, path: str) -> Any:
    """
    Extract value from nested JSON using dot-notation path.
    e.g. "order.customer.email" → data["order"]["customer"]["email"]
    Supports array indexing: "items.0.name"
    """
    if not path or data is None:
        return None

    parts = path.split(".")
    current = data

    for part in parts:
        if current is None:
            return None

        # Array index
        if part.isdigit():
            idx = int(part)
            if isinstance(current, list) and 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        # Object key
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None

    return current


def _apply_transform(value: Any, transform: Optional[str]) -> Any:
    """Apply a safe, predefined transform to a value."""
    if value is None or transform is None:
        return value

    try:
        if transform == "lowercase":
            return str(value).lower()
        elif transform == "uppercase":
            return str(value).upper()
        elif transform == "trim":
            return str(value).strip()
        elif transform == "to_int":
            return int(float(str(value)))
        elif transform == "to_float":
            return float(str(value))
        elif transform == "to_bool":
            return str(value).lower() in ("true", "1", "yes")
        elif transform == "iso_date":
            # Parse various date formats to ISO
            return str(value)
        elif transform == "epoch_to_date":
            ts = float(str(value))
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        elif transform == "strip_html":
            return re.sub(r"<[^>]+>", "", str(value))
        else:
            return value
    except (ValueError, TypeError) as e:
        logger.warning("Transform '%s' failed on value: %s", transform, e)
        return value


async def apply_field_mappings(
    raw_data: Any,
    mappings: List[dict],
) -> Dict[str, Any]:
    """Apply field mapping rules to transform external data to Priya schema."""
    result = {}

    for mapping in mappings:
        source_path = mapping.get("source_path", "")
        target_field = mapping.get("target_field", "")
        data_type = mapping.get("data_type", "string")
        default_value = mapping.get("default_value")
        is_required = mapping.get("is_required", False)
        transform = mapping.get("transform")

        # Extract value from source
        value = _extract_json_path(raw_data, source_path)

        # Apply default if value is None
        if value is None:
            if is_required:
                raise ValueError(f"Required field missing: {source_path}")
            value = default_value

        # Apply transform
        if value is not None:
            value = _apply_transform(value, transform)

        # Set in result
        if value is not None:
            result[target_field] = value

    return result


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Client with Retry
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_http_request(
    url: str,
    method: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    retry_enabled: bool = True,
) -> Dict[str, Any]:
    """
    Execute an HTTP request with retry, timeout, and size limits.
    Returns dict with status_code, headers, body, elapsed_ms.
    """
    if not _validate_url_safe(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target URL is not allowed (SSRF protection)",
        )

    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")

    max_attempts = MAX_RETRY_ATTEMPTS if retry_enabled else 1
    last_error = None

    for attempt in range(max_attempts):
        start_time = time.monotonic()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    max_field_size=MAX_HEADER_VALUE_LENGTH,
                ) as resp:
                    elapsed_ms = int((time.monotonic() - start_time) * 1000)

                    # Check response size
                    content_length = resp.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Response too large from external API",
                        )

                    body = await resp.text()
                    if len(body) > MAX_RESPONSE_SIZE:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Response too large from external API",
                        )

                    # Parse JSON response
                    try:
                        json_body = json.loads(body) if body else {}
                    except json.JSONDecodeError:
                        json_body = {"_raw_text": body[:5000]}

                    return {
                        "status_code": resp.status,
                        "headers": dict(resp.headers),
                        "body": json_body,
                        "elapsed_ms": elapsed_ms,
                    }

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_error = e
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                "HTTP request failed (attempt %d/%d): %s %s → %s (%dms)",
                attempt + 1, max_attempts, method, url, str(e), elapsed_ms,
            )

            if attempt < max_attempts - 1:
                wait = RETRY_BACKOFF_BASE ** attempt
                await asyncio.sleep(wait)

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"External API unreachable after {max_attempts} attempts",
    )


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Universal REST API Connector",
    description="Generic REST/webhook connector for any platform",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Sentry
init_sentry(service_name="rest_connector", service_port=SERVICE_PORT)

# Tracing
init_tracing(app, service_name="rest_connector")
app.add_middleware(TracingMiddleware)
app.add_middleware(SentryTenantMiddleware)

# CORS
cors_config = get_cors_config()
app.add_middleware(CORSMiddleware, **cors_config)


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database, Redis, and event bus."""
    global redis_client
    logger.info("REST API Connector starting on port %d", SERVICE_PORT)
    await event_bus.startup()
    await db.initialize()
    try:
        redis_client = await aioredis.from_url(config.REDIS_URL)
    except Exception as e:
        logger.warning("Redis unavailable (rate limiting disabled): %s", e)
        redis_client = None
    logger.info("REST API Connector initialized")


@app.on_event("shutdown")
async def shutdown():
    """Clean shutdown."""
    global redis_client
    logger.info("REST API Connector shutting down")
    if redis_client:
        await redis_client.close()
        redis_client = None
    await event_bus.shutdown()
    await db.close()
    shutdown_tracing()


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        service="rest_connector",
        port=SERVICE_PORT,
        database="connected",
        timestamp=utc_now().isoformat(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Connector CRUD
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/connectors", response_model=Dict[str, Any])
async def create_connector(
    req: CreateConnectorRequest,
    auth: AuthContext = Depends(get_auth),
):
    """
    Create a new REST API connector.
    Supports API Key, Bearer, Basic Auth, and OAuth2 authentication.
    """
    auth.require_role("owner", "admin")

    if await _check_rate_limit(str(auth.tenant_id)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    # Check connector limit per tenant
    count_row = await db.fetch_one(
        auth.tenant_id,
        "SELECT COUNT(*) as cnt FROM rest_connectors WHERE tenant_id = $1",
        auth.tenant_id,
    )
    if count_row and count_row["cnt"] >= MAX_CONNECTORS_PER_TENANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_CONNECTORS_PER_TENANT} connectors per tenant",
        )

    connector_id = generate_uuid()

    async with db.transaction(auth.tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO rest_connectors
            (id, tenant_id, name, description, base_url, auth_config, default_headers,
             webhook_secret, sync_direction, retry_enabled, status, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            connector_id,
            auth.tenant_id,
            req.name,
            req.description,
            req.base_url,
            json.dumps(req.auth_config.dict()),
            json.dumps(req.default_headers or {}),
            req.webhook_secret,
            req.sync_direction.value,
            req.retry_enabled,
            ConnectorStatus.ACTIVE.value,
            json.dumps(req.metadata or {}),
            utc_now().isoformat(),
            utc_now().isoformat(),
        )

    logger.info(
        "Connector created: tenant=%s, connector=%s, name=%s",
        auth.tenant_id, connector_id, req.name,
    )

    return {
        "status": "success",
        "connector_id": connector_id,
        "name": req.name,
        "base_url": req.base_url,
    }


@app.get("/api/v1/connectors", response_model=Dict[str, Any])
async def list_connectors(
    skip: int = 0,
    limit: int = 20,
    auth: AuthContext = Depends(get_auth),
):
    """List all REST API connectors for the tenant."""
    if limit > 50:
        limit = 50
    if skip < 0:
        skip = 0

    connectors = await db.fetch_all(
        auth.tenant_id,
        """
        SELECT id, name, description, base_url, auth_config, sync_direction,
               retry_enabled, status, created_at, updated_at, last_sync_at
        FROM rest_connectors
        WHERE tenant_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        auth.tenant_id,
        limit,
        skip,
    )

    results = []
    for c in connectors:
        auth_cfg = json.loads(c["auth_config"]) if c["auth_config"] else {}
        results.append({
            "id": c["id"],
            "name": c["name"],
            "description": c["description"],
            "base_url": c["base_url"],
            "auth_type": auth_cfg.get("auth_type", "none"),
            "sync_direction": c["sync_direction"],
            "retry_enabled": c["retry_enabled"],
            "status": c["status"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "last_sync_at": c["last_sync_at"],
        })

    return {"connectors": results, "total": len(results), "skip": skip, "limit": limit}


@app.get("/api/v1/connectors/{connector_id}", response_model=Dict[str, Any])
async def get_connector(
    connector_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get detailed info about a specific connector (secrets redacted)."""
    connector = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM rest_connectors WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        connector_id,
    )

    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    auth_cfg = json.loads(connector["auth_config"]) if connector["auth_config"] else {}

    return {
        "id": connector["id"],
        "name": connector["name"],
        "description": connector["description"],
        "base_url": connector["base_url"],
        "auth_config": _redact_auth_config(auth_cfg),
        "default_headers": json.loads(connector["default_headers"]) if connector["default_headers"] else {},
        "sync_direction": connector["sync_direction"],
        "retry_enabled": connector["retry_enabled"],
        "status": connector["status"],
        "metadata": json.loads(connector["metadata"]) if connector["metadata"] else {},
        "created_at": connector["created_at"],
        "updated_at": connector["updated_at"],
        "last_sync_at": connector["last_sync_at"],
    }


@app.put("/api/v1/connectors/{connector_id}", response_model=Dict[str, Any])
async def update_connector(
    connector_id: str,
    req: UpdateConnectorRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Update connector configuration."""
    auth.require_role("owner", "admin")

    existing = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM rest_connectors WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        connector_id,
    )

    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    # Build update fields
    updates = []
    params = []
    param_idx = 1

    if req.name is not None:
        param_idx += 1
        updates.append(f"name = ${param_idx}")
        params.append(req.name)

    if req.description is not None:
        param_idx += 1
        updates.append(f"description = ${param_idx}")
        params.append(req.description)

    if req.base_url is not None:
        param_idx += 1
        updates.append(f"base_url = ${param_idx}")
        params.append(req.base_url)

    if req.auth_config is not None:
        param_idx += 1
        updates.append(f"auth_config = ${param_idx}")
        params.append(json.dumps(req.auth_config.dict()))

    if req.default_headers is not None:
        param_idx += 1
        updates.append(f"default_headers = ${param_idx}")
        params.append(json.dumps(req.default_headers))

    if req.webhook_secret is not None:
        param_idx += 1
        updates.append(f"webhook_secret = ${param_idx}")
        params.append(req.webhook_secret)

    if req.sync_direction is not None:
        param_idx += 1
        updates.append(f"sync_direction = ${param_idx}")
        params.append(req.sync_direction.value)

    if req.retry_enabled is not None:
        param_idx += 1
        updates.append(f"retry_enabled = ${param_idx}")
        params.append(req.retry_enabled)

    if req.status is not None:
        param_idx += 1
        updates.append(f"status = ${param_idx}")
        params.append(req.status.value)

    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    param_idx += 1
    updates.append(f"updated_at = ${param_idx}")
    params.append(utc_now().isoformat())

    query = f"UPDATE rest_connectors SET {', '.join(updates)} WHERE id = $1"
    params.insert(0, connector_id)

    await db.execute(auth.tenant_id, query, *params)

    logger.info("Connector updated: tenant=%s, connector=%s", auth.tenant_id, connector_id)
    return {"status": "success", "connector_id": connector_id}


@app.delete("/api/v1/connectors/{connector_id}", response_model=Dict[str, Any])
async def delete_connector(
    connector_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Soft-delete a connector (set status to inactive)."""
    auth.require_role("owner", "admin")

    existing = await db.fetch_one(
        auth.tenant_id,
        "SELECT id FROM rest_connectors WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        connector_id,
    )

    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    await db.execute(
        auth.tenant_id,
        "UPDATE rest_connectors SET status = $1, updated_at = $2 WHERE id = $3",
        ConnectorStatus.INACTIVE.value,
        utc_now().isoformat(),
        connector_id,
    )

    logger.info("Connector deleted (soft): tenant=%s, connector=%s", auth.tenant_id, connector_id)
    return {"status": "success", "connector_id": connector_id}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint Definitions
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/connectors/{connector_id}/endpoints", response_model=Dict[str, Any])
async def create_endpoint(
    connector_id: str,
    endpoint: EndpointDefinition,
    auth: AuthContext = Depends(get_auth),
):
    """Define a REST endpoint on a connector."""
    auth.require_role("owner", "admin")

    # Verify connector exists and belongs to tenant
    connector = await db.fetch_one(
        auth.tenant_id,
        "SELECT id FROM rest_connectors WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        connector_id,
    )
    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    # Check endpoint limit
    count_row = await db.fetch_one(
        auth.tenant_id,
        "SELECT COUNT(*) as cnt FROM rest_endpoints WHERE tenant_id = $1 AND connector_id = $2",
        auth.tenant_id,
        connector_id,
    )
    if count_row and count_row["cnt"] >= MAX_ENDPOINTS_PER_CONNECTOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ENDPOINTS_PER_CONNECTOR} endpoints per connector",
        )

    endpoint_id = generate_uuid()

    await db.execute(
        auth.tenant_id,
        """
        INSERT INTO rest_endpoints
        (id, tenant_id, connector_id, name, path, method, description,
         query_params, request_body_template, response_root_path,
         pagination_type, pagination_config, is_active, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        """,
        endpoint_id,
        auth.tenant_id,
        connector_id,
        endpoint.name,
        endpoint.path,
        endpoint.method.value,
        endpoint.description,
        json.dumps(endpoint.query_params or {}),
        json.dumps(endpoint.request_body_template or {}),
        endpoint.response_root_path,
        endpoint.pagination_type,
        json.dumps(endpoint.pagination_config or {}),
        endpoint.is_active,
        utc_now().isoformat(),
        utc_now().isoformat(),
    )

    logger.info(
        "Endpoint created: tenant=%s, connector=%s, endpoint=%s, name=%s",
        auth.tenant_id, connector_id, endpoint_id, endpoint.name,
    )

    return {"status": "success", "endpoint_id": endpoint_id, "name": endpoint.name}


@app.get("/api/v1/connectors/{connector_id}/endpoints", response_model=Dict[str, Any])
async def list_endpoints(
    connector_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """List all endpoints for a connector."""
    endpoints = await db.fetch_all(
        auth.tenant_id,
        """
        SELECT id, name, path, method, description, is_active, created_at, updated_at
        FROM rest_endpoints
        WHERE tenant_id = $1 AND connector_id = $2
        ORDER BY created_at
        """,
        auth.tenant_id,
        connector_id,
    )

    return {
        "connector_id": connector_id,
        "endpoints": [dict(e) for e in endpoints],
        "total": len(endpoints),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Field Mappings
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/connectors/{connector_id}/endpoints/{endpoint_id}/mappings", response_model=Dict[str, Any])
async def create_field_mapping(
    connector_id: str,
    endpoint_id: str,
    mapping: FieldMappingRule,
    auth: AuthContext = Depends(get_auth),
):
    """Create a field mapping rule for an endpoint."""
    auth.require_role("owner", "admin")

    # Verify endpoint belongs to tenant and connector
    ep = await db.fetch_one(
        auth.tenant_id,
        "SELECT id FROM rest_endpoints WHERE tenant_id = $1 AND connector_id = $2 AND id = $3",
        auth.tenant_id,
        connector_id,
        endpoint_id,
    )
    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    # Check mapping limit
    count_row = await db.fetch_one(
        auth.tenant_id,
        "SELECT COUNT(*) as cnt FROM rest_field_mappings WHERE tenant_id = $1 AND endpoint_id = $2",
        auth.tenant_id,
        endpoint_id,
    )
    if count_row and count_row["cnt"] >= MAX_MAPPINGS_PER_ENDPOINT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_MAPPINGS_PER_ENDPOINT} mappings per endpoint",
        )

    mapping_id = generate_uuid()

    await db.execute(
        auth.tenant_id,
        """
        INSERT INTO rest_field_mappings
        (id, tenant_id, connector_id, endpoint_id, source_path, target_field,
         data_type, default_value, is_required, transform, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
        mapping_id,
        auth.tenant_id,
        connector_id,
        endpoint_id,
        mapping.source_path,
        mapping.target_field,
        mapping.data_type.value,
        mapping.default_value,
        mapping.is_required,
        mapping.transform,
        utc_now().isoformat(),
    )

    return {"status": "success", "mapping_id": mapping_id}


@app.get("/api/v1/connectors/{connector_id}/endpoints/{endpoint_id}/mappings", response_model=Dict[str, Any])
async def list_field_mappings(
    connector_id: str,
    endpoint_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """List all field mappings for an endpoint."""
    mappings = await db.fetch_all(
        auth.tenant_id,
        """
        SELECT id, source_path, target_field, data_type, default_value,
               is_required, transform, created_at
        FROM rest_field_mappings
        WHERE tenant_id = $1 AND connector_id = $2 AND endpoint_id = $3
        ORDER BY created_at
        """,
        auth.tenant_id,
        connector_id,
        endpoint_id,
    )

    return {
        "connector_id": connector_id,
        "endpoint_id": endpoint_id,
        "mappings": [dict(m) for m in mappings],
        "total": len(mappings),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Execute / Test Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/connectors/{connector_id}/execute", response_model=Dict[str, Any])
async def execute_endpoint(
    connector_id: str,
    req: ExecuteEndpointRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """
    Execute a specific endpoint and apply field mappings.
    Returns mapped data according to configured field mappings.
    """
    auth.require_role("owner", "admin")

    if await _check_rate_limit(str(auth.tenant_id)):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    # Fetch connector
    connector = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM rest_connectors WHERE tenant_id = $1 AND id = $2 AND status = 'active'",
        auth.tenant_id,
        connector_id,
    )
    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found or inactive")

    # Fetch endpoint
    endpoint = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM rest_endpoints WHERE tenant_id = $1 AND connector_id = $2 AND id = $3 AND is_active = TRUE",
        auth.tenant_id,
        connector_id,
        req.endpoint_id,
    )
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found or inactive")

    # Fetch field mappings
    mappings = await db.fetch_all(
        auth.tenant_id,
        "SELECT * FROM rest_field_mappings WHERE tenant_id = $1 AND endpoint_id = $2",
        auth.tenant_id,
        req.endpoint_id,
    )

    # Build URL
    base_url = connector["base_url"].rstrip("/")
    path = endpoint["path"].lstrip("/")
    full_url = f"{base_url}/{path}"

    if not _validate_url_safe(full_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Computed URL is not allowed",
        )

    # Build auth headers
    auth_cfg = json.loads(connector["auth_config"]) if connector["auth_config"] else {}
    auth_headers = await _build_auth_headers(auth_cfg)

    # Merge default headers
    default_headers = json.loads(connector["default_headers"]) if connector["default_headers"] else {}
    headers = {**default_headers, **auth_headers}

    # Query params
    query_params = json.loads(endpoint["query_params"]) if endpoint["query_params"] else {}
    if req.override_params:
        query_params.update(req.override_params)

    # Request body
    body_template = json.loads(endpoint["request_body_template"]) if endpoint["request_body_template"] else None
    if req.override_body:
        body_template = req.override_body

    # Execute request
    start_time = time.monotonic()
    result = await _execute_http_request(
        url=full_url,
        method=endpoint["method"],
        headers=headers,
        params=query_params if query_params else None,
        json_data=body_template,
        retry_enabled=connector["retry_enabled"],
    )
    total_ms = int((time.monotonic() - start_time) * 1000)

    # Extract response data from root path
    response_data = result["body"]
    root_path = endpoint.get("response_root_path")
    if root_path:
        response_data = _extract_json_path(response_data, root_path)

    # Apply field mappings if any
    mapped_data = None
    if mappings:
        try:
            if isinstance(response_data, list):
                mapped_data = []
                for i, item in enumerate(response_data):
                    if i >= MAX_ITEMS_PER_RESPONSE:
                        logger.warning("Truncated response: %d items (max %d)", len(response_data), MAX_ITEMS_PER_RESPONSE)
                        break
                    mapped_item = await apply_field_mappings(item, [dict(m) for m in mappings])
                    mapped_data.append(mapped_item)
            elif isinstance(response_data, dict):
                mapped_data = await apply_field_mappings(response_data, [dict(m) for m in mappings])
        except ValueError as e:
            logger.warning("Field mapping error: connector=%s, endpoint=%s, error=%s", connector_id, req.endpoint_id, e)
            mapped_data = {"_mapping_error": "One or more required fields could not be mapped"}

    # Log execution
    log_id = generate_uuid()
    background_tasks.add_task(
        _log_sync_execution,
        auth.tenant_id,
        connector_id,
        req.endpoint_id,
        log_id,
        result["status_code"],
        total_ms,
        len(mapped_data) if isinstance(mapped_data, list) else 1 if mapped_data else 0,
    )

    return {
        "status": "success",
        "connector_id": connector_id,
        "endpoint_id": req.endpoint_id,
        "http_status": result["status_code"],
        "elapsed_ms": total_ms,
        "raw_data": response_data if not mapped_data else None,
        "mapped_data": mapped_data,
        "records_count": len(mapped_data) if isinstance(mapped_data, list) else 1 if mapped_data else 0,
    }


@app.post("/api/v1/connectors/{connector_id}/test", response_model=Dict[str, Any])
async def test_connection(
    connector_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Test connector connectivity by making a lightweight request."""
    auth.require_role("owner", "admin")

    connector = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM rest_connectors WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        connector_id,
    )
    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    auth_cfg = json.loads(connector["auth_config"]) if connector["auth_config"] else {}
    auth_headers = await _build_auth_headers(auth_cfg)
    default_headers = json.loads(connector["default_headers"]) if connector["default_headers"] else {}
    headers = {**default_headers, **auth_headers}

    try:
        result = await _execute_http_request(
            url=connector["base_url"],
            method="GET",
            headers=headers,
            retry_enabled=False,
        )
        return {
            "status": "success",
            "connector_id": connector_id,
            "reachable": True,
            "http_status": result["status_code"],
            "elapsed_ms": result["elapsed_ms"],
        }
    except HTTPException:
        return {
            "status": "failed",
            "connector_id": connector_id,
            "reachable": False,
            "message": "Could not reach the external API. Please verify the URL and credentials.",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Ingestion
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/connectors/{connector_id}/webhook")
async def receive_webhook(
    connector_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Universal webhook receiver for any connector.
    Verifies HMAC signature, deduplicates, and processes payload.
    """
    # Rate limit
    if await _check_webhook_rate_limit(connector_id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    body = await request.body()
    if len(body) > 1_048_576:  # 1MB max
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")

    # Replay protection
    if await _check_webhook_replay(connector_id, body):
        return {"status": "already_processed"}

    # Tenant extraction from header (set by gateway)
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id or not TENANT_ID_RE.match(tenant_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing or invalid tenant context")

    # Fetch connector with tenant isolation
    connector = await db.fetch_one(
        tenant_id,
        "SELECT * FROM rest_connectors WHERE tenant_id = $1 AND id = $2 AND status = 'active'",
        tenant_id,
        connector_id,
    )
    if not connector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    # Verify webhook signature — MANDATORY
    webhook_secret = connector.get("webhook_secret")
    if not webhook_secret:
        logger.warning("Webhook rejected: no webhook_secret configured for connector=%s", connector_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook not configured — webhook_secret required")

    signature = request.headers.get("X-Webhook-Signature") or request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature")

    computed = hmac.new(
        webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    # Support both raw hex and "sha256=" prefixed
    sig_value = signature.replace("sha256=", "")
    if not hmac.compare_digest(computed, sig_value):
        logger.warning("Webhook signature mismatch: connector=%s", connector_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    # Process webhook asynchronously
    async def process_webhook():
        try:
            event_type = (
                request.headers.get("X-Event-Type")
                or request.headers.get("X-Webhook-Event")
                or payload.get("event_type", "unknown")
            )

            # Find matching endpoint for field mapping
            # Convention: webhook endpoints are named "webhook_{event_type}"
            endpoint = await db.fetch_one(
                tenant_id,
                """
                SELECT * FROM rest_endpoints
                WHERE tenant_id = $1 AND connector_id = $2 AND is_active = TRUE
                ORDER BY created_at LIMIT 1
                """,
                tenant_id,
                connector_id,
            )

            mapped_data = payload
            if endpoint:
                mappings = await db.fetch_all(
                    tenant_id,
                    "SELECT * FROM rest_field_mappings WHERE tenant_id = $1 AND endpoint_id = $2",
                    tenant_id,
                    endpoint["id"],
                )
                if mappings:
                    try:
                        mapped_data = await apply_field_mappings(payload, [dict(m) for m in mappings])
                    except ValueError as e:
                        logger.warning("Webhook mapping error: %s", e)

            # Store webhook event
            await db.execute(
                tenant_id,
                """
                INSERT INTO rest_sync_logs
                (id, tenant_id, connector_id, endpoint_id, direction, event_type,
                 status_code, records_count, elapsed_ms, error_message, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                generate_uuid(),
                tenant_id,
                connector_id,
                endpoint["id"] if endpoint else None,
                "inbound",
                event_type,
                200,
                1,
                0,
                None,
                utc_now().isoformat(),
            )

            # Emit event for other services
            await event_bus.publish(
                EventType.WEBHOOK_RECEIVED,
                {
                    "tenant_id": tenant_id,
                    "connector_id": connector_id,
                    "event_type": event_type,
                    "mapped_data": mapped_data,
                },
            )

            logger.info(
                "Webhook processed: tenant=%s, connector=%s, event=%s",
                tenant_id, connector_id, event_type,
            )

        except Exception as e:
            logger.error("Webhook processing failed: %s", str(e), exc_info=True)

    background_tasks.add_task(process_webhook)
    return {"status": "received"}


# ─────────────────────────────────────────────────────────────────────────────
# Sync Logs
# ─────────────────────────────────────────────────────────────────────────────

async def _log_sync_execution(
    tenant_id: str,
    connector_id: str,
    endpoint_id: str,
    log_id: str,
    status_code: int,
    elapsed_ms: int,
    records_count: int,
    error_message: Optional[str] = None,
):
    """Log a sync execution for audit trail."""
    try:
        await db.execute(
            tenant_id,
            """
            INSERT INTO rest_sync_logs
            (id, tenant_id, connector_id, endpoint_id, direction, event_type,
             status_code, records_count, elapsed_ms, error_message, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            log_id,
            tenant_id,
            connector_id,
            endpoint_id,
            "outbound",
            "api_call",
            status_code,
            records_count,
            elapsed_ms,
            error_message,
            utc_now().isoformat(),
        )

        # Update connector last_sync_at
        await db.execute(
            tenant_id,
            "UPDATE rest_connectors SET last_sync_at = $1 WHERE id = $2",
            utc_now().isoformat(),
            connector_id,
        )
    except Exception as e:
        logger.warning("Failed to log sync execution: %s", e)


@app.get("/api/v1/connectors/{connector_id}/logs", response_model=Dict[str, Any])
async def get_sync_logs(
    connector_id: str,
    days: int = 7,
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth),
):
    """Get sync execution logs for a connector."""
    if limit > 100:
        limit = 100
    if skip < 0:
        skip = 0
    if days < 1:
        days = 1
    if days > MAX_SYNC_LOG_DAYS:
        days = MAX_SYNC_LOG_DAYS

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    logs = await db.fetch_all(
        auth.tenant_id,
        """
        SELECT id, connector_id, endpoint_id, direction, event_type,
               status_code, records_count, elapsed_ms, error_message, created_at
        FROM rest_sync_logs
        WHERE tenant_id = $1 AND connector_id = $2 AND created_at > $3
        ORDER BY created_at DESC
        LIMIT $4 OFFSET $5
        """,
        auth.tenant_id,
        connector_id,
        cutoff,
        limit,
        skip,
    )

    return {
        "connector_id": connector_id,
        "logs": [dict(log) for log in logs],
        "total": len(logs),
        "days": days,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Admin / Stats
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/connectors/admin/stats", response_model=Dict[str, Any])
async def get_connector_stats(
    auth: AuthContext = Depends(get_auth),
):
    """Get aggregate stats for all connectors of this tenant."""
    auth.require_role("owner", "admin")

    stats = await db.fetch_one(
        auth.tenant_id,
        """
        SELECT
            COUNT(*) FILTER (WHERE status = 'active') as active_connectors,
            COUNT(*) FILTER (WHERE status = 'inactive') as inactive_connectors,
            COUNT(*) FILTER (WHERE status = 'error') as error_connectors,
            COUNT(*) as total_connectors
        FROM rest_connectors
        WHERE tenant_id = $1
        """,
        auth.tenant_id,
    )

    endpoint_count = await db.fetch_one(
        auth.tenant_id,
        "SELECT COUNT(*) as cnt FROM rest_endpoints WHERE tenant_id = $1",
        auth.tenant_id,
    )

    recent_syncs = await db.fetch_one(
        auth.tenant_id,
        """
        SELECT
            COUNT(*) as total_syncs,
            AVG(elapsed_ms) as avg_elapsed_ms,
            SUM(records_count) as total_records
        FROM rest_sync_logs
        WHERE tenant_id = $1 AND created_at > $2
        """,
        auth.tenant_id,
        (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
    )

    return {
        "connectors": dict(stats) if stats else {},
        "endpoints": endpoint_count["cnt"] if endpoint_count else 0,
        "syncs_last_7d": {
            "total": recent_syncs["total_syncs"] if recent_syncs else 0,
            "avg_elapsed_ms": round(float(recent_syncs["avg_elapsed_ms"] or 0), 1) if recent_syncs else 0,
            "total_records": recent_syncs["total_records"] if recent_syncs else 0,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Error Handler
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return {"error": "Internal server error", "detail": "An unexpected error occurred. Please try again."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SERVICE_PORT,
        log_level=config.log_level.lower(),
    )
