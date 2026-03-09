import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import hmac
import logging
import hashlib
import secrets
import httpx
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import uuid4
from urllib.parse import urlparse
import socket
import ipaddress
import re
import os

from fastapi import FastAPI, HTTPException, Header, Depends, Body, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, validator
import redis.asyncio as redis

from shared.core.config import config
from shared.core.security import mask_pii
from shared.core.database import DatabaseManager
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Developer Portal & API Documentation",
    description="Multi-tenant developer portal and API documentation service",
    version="1.0.0"
)

db = DatabaseManager(service_name="developer_portal")
redis_client = None
event_bus = None
http_client = None

cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)

init_sentry(service_name="developer_portal", service_port=9036)
init_tracing(app, service_name="developer_portal")
app.add_middleware(TracingMiddleware)
app.add_middleware(SentryTenantMiddleware)


class DeveloperRegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    company: str = Field(..., min_length=1, max_length=255)

    @validator("name", "company")
    def validate_string_fields(cls, v):
        if len(v.strip()) == 0:
            raise ValueError("Cannot be empty or whitespace")
        return v.strip()


class DeveloperUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    company: Optional[str] = Field(None, min_length=1, max_length=255)

    @validator("name", "company")
    def validate_string_fields(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Cannot be empty or whitespace")
        return v.strip() if v else None


class DeveloperResponse(BaseModel):
    id: str
    email: str
    name: str
    company: str
    is_verified: bool
    created_at: str


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scope: str = Field(..., regex="^(read|write|admin)$")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)

    @validator("name")
    def validate_name(cls, v):
        if len(v.strip()) == 0:
            raise ValueError("Cannot be empty or whitespace")
        return v.strip()


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    scope: str
    key_prefix: str
    last_used_at: Optional[str]
    created_at: str
    expires_at: Optional[str]


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    scope: str
    key_prefix: str
    key: str
    created_at: str
    expires_at: Optional[str]


class PluginSubmitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    version: str = Field(..., min_length=1, max_length=20)
    description: str = Field(..., min_length=10, max_length=2000)
    category: str = Field(..., min_length=1, max_length=50)
    permissions: List[str] = Field(default_factory=list)
    webhook_url: Optional[str] = Field(None, max_length=2048)
    config_schema: Optional[Dict[str, Any]] = None
    icon_url: Optional[str] = Field(None, max_length=2048)
    homepage_url: Optional[str] = Field(None, max_length=2048)
    source_url: Optional[str] = Field(None, max_length=2048)

    @validator("webhook_url")
    def validate_webhook_url(cls, v):
        if v:
            validate_url_ssrf(v)
        return v

    @validator("icon_url", "homepage_url", "source_url")
    def validate_urls(cls, v):
        if v:
            validate_url_format(v)
        return v


class PluginUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    version: Optional[str] = Field(None, min_length=1, max_length=20)
    description: Optional[str] = Field(None, min_length=10, max_length=2000)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    permissions: Optional[List[str]] = None
    webhook_url: Optional[str] = Field(None, max_length=2048)
    config_schema: Optional[Dict[str, Any]] = None
    icon_url: Optional[str] = Field(None, max_length=2048)
    homepage_url: Optional[str] = Field(None, max_length=2048)
    source_url: Optional[str] = Field(None, max_length=2048)

    @validator("webhook_url")
    def validate_webhook_url(cls, v):
        if v:
            validate_url_ssrf(v)
        return v


class PluginReviewRequest(BaseModel):
    status: str = Field(..., regex="^(approved|rejected)$")
    notes: Optional[str] = Field(None, max_length=2000)


class PluginSubmissionResponse(BaseModel):
    id: str
    name: str
    version: str
    description: str
    category: str
    status: str
    submitted_at: str
    reviewed_at: Optional[str]


class SandboxTestRequest(BaseModel):
    method: str = Field(..., regex="^(GET|POST|PUT|DELETE|PATCH)$")
    endpoint: str = Field(..., min_length=1, max_length=2048)
    body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None

    @validator("headers")
    def validate_headers(cls, v):
        if v:
            for key in v.keys():
                if not isinstance(key, str) or len(key) > 255:
                    raise ValueError("Invalid header key")
        return v or {}


class WebhookTestRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @validator("url")
    def validate_webhook_url(cls, v):
        validate_url_ssrf(v)
        return v


class SandboxTestResponse(BaseModel):
    status_code: int
    response_body: Dict[str, Any]
    latency_ms: float


def validate_url_format(url: str) -> None:
    try:
        result = urlparse(url)
        if not result.scheme or not result.netloc:
            raise ValueError("Invalid URL format")
        if result.scheme not in ("http", "https"):
            raise ValueError("Only http and https schemes allowed")
    except Exception as e:
        raise ValueError(f"Invalid URL: {str(e)}")


_BLOCKED_HOST_RE = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|"
    r"192\.168\.\d+\.\d+|0\.0\.0\.0|"
    r"\[?::1\]?|\[?fe80:.*\]?|\[?fd.*\]?|"
    r"169\.254\.\d+\.\d+|metadata\.google\.internal)$",
    re.IGNORECASE,
)


def validate_url_ssrf(url: str) -> None:
    """Validate URL is safe from SSRF with DNS resolution check."""
    validate_url_format(url)

    parsed = urlparse(url)
    hostname = parsed.hostname

    if not hostname:
        raise ValueError("Invalid URL: missing hostname")

    # Block known private hostnames
    if _BLOCKED_HOST_RE.match(hostname):
        raise ValueError("Blocked hostname")

    # Resolve DNS and check all IPs
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, socktype, proto, canonname, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Private/reserved IP addresses not allowed")
    except socket.gaierror:
        raise ValueError("Hostname resolution failed")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("URL validation failed")


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key():
    """Generate API key, returning (raw_key, key_hash, key_prefix)."""
    raw_key = secrets.token_urlsafe(32)
    key_prefix = raw_key[:10]
    key_hash = hash_api_key(raw_key)
    return raw_key, key_hash, key_prefix


async def get_developer_from_key(x_developer_key: str = Header(...)) -> dict:
    if not x_developer_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    key_hash = hash_api_key(x_developer_key)
    result = await db.fetch_one(
        "system",
        """
        SELECT dak.id, dak.developer_id, dak.scope, dak.is_active, dak.expires_at, d.id as dev_id, d.email
        FROM developer_api_keys dak
        JOIN developers d ON dak.developer_id = d.id
        WHERE dak.key_hash = $1
        """,
        key_hash
    )

    if not result:
        raise HTTPException(status_code=401, detail="Invalid API key")

    is_active = result.get("is_active", False)
    if not is_active:
        raise HTTPException(status_code=401, detail="API key is inactive")

    expires_at = result.get("expires_at")
    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if datetime.utcnow() > expires_dt:
            raise HTTPException(status_code=401, detail="API key expired")

    # Rate limiting — fail-closed (deny on Redis failure)
    try:
        rate_limit_key = "rate_limit:%s" % hash_api_key(x_developer_key)[:16]
        current_count = await redis_client.incr(rate_limit_key)
        if current_count == 1:
            await redis_client.expire(rate_limit_key, 60)

        if current_count > 100:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        logger.error("Redis rate limit check failed — denying request (fail-closed)")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    await db.execute(
        "system",
        "UPDATE developer_api_keys SET last_used_at = NOW() WHERE id = $1",
        result["id"]
    )

    return {
        "developer_id": result["developer_id"],
        "key_id": result["id"],
        "scope": result["scope"],
        "email": result["email"],
    }


ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
if not ADMIN_TOKEN:
    ADMIN_TOKEN = secrets.token_hex(32)
    logger.critical(
        "ADMIN_TOKEN env var not set — generated ephemeral token (admin endpoints "
        "will only work until restart; set ADMIN_TOKEN in environment for persistence)"
    )


async def get_admin_key(x_admin_token: str = Header(...)) -> dict:
    """Validate admin token from header."""
    if not x_admin_token or not hmac.compare_digest(x_admin_token, ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return {"authenticated": True}


@app.on_event("startup")
async def startup():
    global redis_client, event_bus, http_client

    await db.initialize()
    logger.info("Database initialized")

    redis_client = await redis.from_url(config.redis_url)
    logger.info("Redis client initialized")

    event_bus = EventBus(service_name="developer_portal")
    await event_bus.startup()
    logger.info("Event bus initialized")

    http_client = httpx.AsyncClient(timeout=10.0)
    logger.info("HTTP client initialized")

    logger.info("Developer Portal service started on port 9036")


@app.on_event("shutdown")
async def shutdown():
    global redis_client, http_client

    await db.close()
    logger.info("Database closed")

    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed")

    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")

    await shutdown_tracing()
    logger.info("Developer Portal service stopped")


@app.get("/health", status_code=200)
async def health_check():
    return {
        "status": "healthy",
        "service": "developer_portal",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/developers/register", status_code=201)
async def register_developer(request: DeveloperRegisterRequest):
    logger.info("Developer registration attempt for email %s", mask_pii(request.email))

    existing = await db.fetch_one(
        "system",
        "SELECT id FROM developers WHERE email = $1",
        request.email
    )

    if existing:
        logger.warning("Registration failed: email already exists %s", mask_pii(request.email))
        raise HTTPException(status_code=409, detail="Email already registered")

    developer_id = str(uuid4())
    verification_token = secrets.token_urlsafe(32)
    token_hash = hash_api_key(verification_token)

    await db.execute(
        "system",
        """
        INSERT INTO developers (id, email, name, company, is_verified)
        VALUES ($1, $2, $3, $4, $5)
        """,
        developer_id,
        request.email,
        request.name,
        request.company,
        False
    )

    cache_key = f"verify_token:{developer_id}"
    await redis_client.setex(cache_key, 86400, token_hash)

    await event_bus.publish(
        EventType.DEVELOPER_REGISTERED,
        {
            "developer_id": developer_id,
            "email": request.email,
            "name": request.name,
            "company": request.company,
            "verification_token": verification_token,
        }
    )

    logger.info("Developer registered successfully: %s", developer_id)

    return {
        "id": developer_id,
        "email": request.email,
        "name": request.name,
        "company": request.company,
        "is_verified": False,
        "created_at": datetime.utcnow().isoformat(),
    }


@app.get("/developers/me", status_code=200)
async def get_developer_profile(developer: dict = Depends(get_developer_from_key)):
    logger.info("Fetching developer profile for %s", developer["developer_id"])

    result = await db.fetch_one(
        "system",
        "SELECT id, email, name, company, is_verified, created_at FROM developers WHERE id = $1",
        developer["developer_id"]
    )

    if not result:
        logger.error("Developer not found %s", developer["developer_id"])
        raise HTTPException(status_code=404, detail="Developer not found")

    return {
        "id": result["id"],
        "email": result["email"],
        "name": result["name"],
        "company": result["company"],
        "is_verified": result["is_verified"],
        "created_at": result["created_at"].isoformat() if result["created_at"] else None,
    }


@app.put("/developers/me", status_code=200)
async def update_developer_profile(
    request: DeveloperUpdateRequest,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Updating developer profile for %s", developer["developer_id"])

    # Build safe parameterized UPDATE — no dynamic column names
    set_parts = []
    params = [developer["developer_id"]]
    param_idx = 2

    if request.name is not None:
        set_parts.append("name = $" + str(param_idx))
        params.append(request.name)
        param_idx += 1

    if request.company is not None:
        set_parts.append("company = $" + str(param_idx))
        params.append(request.company)
        param_idx += 1

    if not set_parts:
        logger.warning("No updates provided for developer %s", developer["developer_id"])
        raise HTTPException(status_code=400, detail="No fields to update")

    query = "UPDATE developers SET " + ", ".join(set_parts) + ", updated_at = NOW() WHERE id = $1"

    await db.execute("system", query, *params)

    result = await db.fetch_one(
        "system",
        "SELECT id, email, name, company, is_verified, created_at FROM developers WHERE id = $1",
        developer["developer_id"]
    )

    logger.info("Developer profile updated successfully: %s", developer["developer_id"])

    return {
        "id": result["id"],
        "email": result["email"],
        "name": result["name"],
        "company": result["company"],
        "is_verified": result["is_verified"],
        "created_at": result["created_at"].isoformat() if result["created_at"] else None,
    }


@app.post("/developers/verify", status_code=200)
async def verify_developer_email(token: str = Body(..., embed=True)):
    logger.info("Email verification attempt")

    cached_tokens = await redis_client.keys("verify_token:*")

    matching_dev_id = None
    token_hash = hash_api_key(token)

    for key in cached_tokens:
        stored_hash = await redis_client.get(key)
        if stored_hash and hmac.compare_digest(stored_hash.decode(), token_hash):
            dev_id = key.decode().replace("verify_token:", "")
            matching_dev_id = dev_id
            break

    if not matching_dev_id:
        logger.warning("Invalid or expired verification token")
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    await db.execute(
        "system",
        "UPDATE developers SET is_verified = TRUE, updated_at = NOW() WHERE id = $1",
        matching_dev_id
    )

    await redis_client.delete(f"verify_token:{matching_dev_id}")

    logger.info("Developer email verified: %s", matching_dev_id)

    return {"message": "Email verified successfully"}


@app.post("/developers/me/keys", status_code=201)
async def create_api_key(
    request: ApiKeyCreateRequest,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Creating new API key for developer %s", developer["developer_id"])

    key_id = str(uuid4())
    raw_key, key_hash, key_prefix = generate_api_key()

    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    await db.execute(
        "system",
        """
        INSERT INTO developer_api_keys (id, developer_id, key_hash, key_prefix, scope, name, is_active, created_at, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8)
        """,
        key_id,
        developer["developer_id"],
        key_hash,
        key_prefix,
        request.scope,
        request.name,
        True,
        expires_at.isoformat() if expires_at else None
    )

    logger.info("API key created successfully: %s", key_id)

    return {
        "id": key_id,
        "name": request.name,
        "scope": request.scope,
        "key_prefix": key_prefix,
        "key": raw_key,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@app.get("/developers/me/keys", status_code=200)
async def list_api_keys(developer: dict = Depends(get_developer_from_key)):
    logger.info("Listing API keys for developer %s", developer["developer_id"])

    results = await db.fetch_all(
        "system",
        """
        SELECT id, name, scope, key_prefix, last_used_at, created_at, expires_at
        FROM developer_api_keys
        WHERE developer_id = $1 AND is_active = TRUE
        ORDER BY created_at DESC
        """,
        developer["developer_id"]
    )

    keys = []
    for row in results:
        keys.append({
            "id": row["id"],
            "name": row["name"],
            "scope": row["scope"],
            "key_prefix": row["key_prefix"],
            "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        })

    logger.info("Retrieved %d API keys for developer %s", len(keys), developer["developer_id"])

    return {"keys": keys}


@app.delete("/developers/me/keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Revoking API key %s for developer %s", key_id, developer["developer_id"])

    result = await db.fetch_one(
        "system",
        "SELECT id FROM developer_api_keys WHERE id = $1 AND developer_id = $2",
        key_id,
        developer["developer_id"]
    )

    if not result:
        logger.warning("API key not found: %s", key_id)
        raise HTTPException(status_code=404, detail="API key not found")

    await db.execute(
        "system",
        "UPDATE developer_api_keys SET is_active = FALSE WHERE id = $1",
        key_id
    )

    logger.info("API key revoked: %s", key_id)

    return None


@app.post("/developers/me/keys/{key_id}/rotate", status_code=201)
async def rotate_api_key(
    key_id: str,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Rotating API key %s for developer %s", key_id, developer["developer_id"])

    old_key = await db.fetch_one(
        "system",
        "SELECT id, name, scope, expires_at FROM developer_api_keys WHERE id = $1 AND developer_id = $2",
        key_id,
        developer["developer_id"]
    )

    if not old_key:
        logger.warning("API key not found for rotation: %s", key_id)
        raise HTTPException(status_code=404, detail="API key not found")

    raw_key, key_hash, key_prefix = generate_api_key()
    new_key_id = str(uuid4())

    await db.execute(
        "system",
        """
        INSERT INTO developer_api_keys (id, developer_id, key_hash, key_prefix, scope, name, is_active, created_at, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8)
        """,
        new_key_id,
        developer["developer_id"],
        key_hash,
        key_prefix,
        old_key["scope"],
        old_key["name"],
        True,
        old_key["expires_at"]
    )

    await db.execute(
        "system",
        "UPDATE developer_api_keys SET is_active = FALSE WHERE id = $1",
        key_id
    )

    logger.info("API key rotated successfully: %s -> %s", key_id, new_key_id)

    return {
        "id": new_key_id,
        "name": old_key["name"],
        "scope": old_key["scope"],
        "key_prefix": key_prefix,
        "key": raw_key,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": old_key["expires_at"].isoformat() if old_key["expires_at"] else None,
    }


@app.get("/docs/services", status_code=200)
async def list_api_services():
    logger.info("Listing available API services")

    cache_key = "api_services_list"
    cached = await redis_client.get(cache_key)

    if cached:
        logger.info("Returning cached API services list")
        return json.loads(cached)

    services = [
        {
            "name": "auth",
            "description": "Authentication and authorization service",
            "version": "1.0.0",
            "status": "production",
        },
        {
            "name": "plugins",
            "description": "Plugin marketplace and management",
            "version": "1.0.0",
            "status": "production",
        },
        {
            "name": "integrations",
            "description": "Third-party integrations",
            "version": "1.0.0",
            "status": "production",
        },
        {
            "name": "analytics",
            "description": "Analytics and reporting",
            "version": "1.0.0",
            "status": "production",
        },
    ]

    await redis_client.setex(cache_key, 300, json.dumps(services))

    return {"services": services}


@app.get("/docs/services/{service_name}/openapi", status_code=200)
async def get_service_openapi(service_name: str):
    logger.info("Fetching OpenAPI spec for service %s", service_name)

    cache_key = f"openapi:{service_name}"
    cached = await redis_client.get(cache_key)

    if cached:
        logger.info("Returning cached OpenAPI spec for %s", service_name)
        return json.loads(cached)

    service_ports = {
        "auth": 9033,
        "plugins": 9034,
        "integrations": 9035,
        "analytics": 9037,
    }

    port = service_ports.get(service_name)
    if not port:
        logger.warning("Service not found: %s", service_name)
        raise HTTPException(status_code=404, detail="Service not found")

    try:
        url = f"http://localhost:{port}/openapi.json"
        response = await http_client.get(url, timeout=5.0)
        response.raise_for_status()
        spec = response.json()

        await redis_client.setex(cache_key, 300, json.dumps(spec))

        logger.info("Retrieved OpenAPI spec for %s", service_name)
        return spec
    except httpx.RequestError as e:
        logger.error("Failed to fetch OpenAPI spec for %s: %s", service_name, str(e))
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/docs/search", status_code=200)
async def search_documentation(q: str = None):
    logger.info("Searching documentation with query %s", q)

    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    results = [
        {
            "title": "Authentication API",
            "description": "Use this endpoint to authenticate users",
            "service": "auth",
            "relevance": 0.95,
        },
        {
            "title": "Plugin Installation",
            "description": "Install plugins from the marketplace",
            "service": "plugins",
            "relevance": 0.87,
        },
    ]

    logger.info("Search returned %d results", len(results))

    return {"results": results, "total": len(results)}


@app.get("/docs/changelog", status_code=200)
async def get_changelog():
    logger.info("Fetching API changelog")

    cache_key = "api_changelog"
    cached = await redis_client.get(cache_key)

    if cached:
        logger.info("Returning cached changelog")
        return json.loads(cached)

    changelog = {
        "releases": [
            {
                "version": "1.0.0",
                "date": "2026-03-01",
                "changes": [
                    "Initial release",
                    "Authentication service available",
                    "Plugin marketplace launched",
                ],
            },
        ],
    }

    await redis_client.setex(cache_key, 300, json.dumps(changelog))

    return changelog


@app.post("/developers/me/plugins", status_code=201)
async def submit_plugin(
    request: PluginSubmitRequest,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Plugin submission for developer %s", developer["developer_id"])

    submission_id = str(uuid4())

    await db.execute(
        "system",
        """
        INSERT INTO plugin_submissions (
            id, developer_id, name, version, description, category,
            permissions, webhook_url, config_schema, icon_url,
            homepage_url, source_url, status, submitted_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
        """,
        submission_id,
        developer["developer_id"],
        request.name,
        request.version,
        request.description,
        request.category,
        json.dumps(request.permissions),
        request.webhook_url,
        json.dumps(request.config_schema) if request.config_schema else None,
        request.icon_url,
        request.homepage_url,
        request.source_url,
        "pending_review"
    )

    await event_bus.publish(
        EventType.PLUGIN_SUBMITTED,
        {
            "submission_id": submission_id,
            "developer_id": developer["developer_id"],
            "plugin_name": request.name,
            "version": request.version,
        }
    )

    logger.info("Plugin submitted successfully: %s", submission_id)

    return {
        "id": submission_id,
        "name": request.name,
        "version": request.version,
        "description": request.description,
        "category": request.category,
        "status": "pending_review",
        "submitted_at": datetime.utcnow().isoformat(),
        "reviewed_at": None,
    }


@app.get("/developers/me/plugins", status_code=200)
async def list_developer_plugins(developer: dict = Depends(get_developer_from_key)):
    logger.info("Listing plugins for developer %s", developer["developer_id"])

    results = await db.fetch_all(
        "system",
        """
        SELECT id, name, version, description, category, status, submitted_at, reviewed_at
        FROM plugin_submissions
        WHERE developer_id = $1
        ORDER BY submitted_at DESC
        """,
        developer["developer_id"]
    )

    plugins = []
    for row in results:
        plugins.append({
            "id": row["id"],
            "name": row["name"],
            "version": row["version"],
            "description": row["description"],
            "category": row["category"],
            "status": row["status"],
            "submitted_at": row["submitted_at"].isoformat() if row["submitted_at"] else None,
            "reviewed_at": row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        })

    logger.info("Retrieved %d plugins for developer %s", len(plugins), developer["developer_id"])

    return {"plugins": plugins}


@app.get("/developers/me/plugins/{plugin_id}", status_code=200)
async def get_plugin_submission(
    plugin_id: str,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Fetching plugin submission %s for developer %s", plugin_id, developer["developer_id"])

    result = await db.fetch_one(
        "system",
        """
        SELECT id, name, version, description, category, permissions, webhook_url,
               config_schema, icon_url, homepage_url, source_url, status, reviewer_notes,
               submitted_at, reviewed_at
        FROM plugin_submissions
        WHERE id = $1 AND developer_id = $2
        """,
        plugin_id,
        developer["developer_id"]
    )

    if not result:
        logger.warning("Plugin submission not found: %s", plugin_id)
        raise HTTPException(status_code=404, detail="Plugin submission not found")

    return {
        "id": result["id"],
        "name": result["name"],
        "version": result["version"],
        "description": result["description"],
        "category": result["category"],
        "permissions": json.loads(result["permissions"]) if result["permissions"] else [],
        "webhook_url": result["webhook_url"],
        "config_schema": json.loads(result["config_schema"]) if result["config_schema"] else None,
        "icon_url": result["icon_url"],
        "homepage_url": result["homepage_url"],
        "source_url": result["source_url"],
        "status": result["status"],
        "reviewer_notes": result["reviewer_notes"],
        "submitted_at": result["submitted_at"].isoformat() if result["submitted_at"] else None,
        "reviewed_at": result["reviewed_at"].isoformat() if result["reviewed_at"] else None,
    }


@app.put("/developers/me/plugins/{plugin_id}", status_code=200)
async def update_plugin_submission(
    plugin_id: str,
    request: PluginUpdateRequest,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Updating plugin submission %s for developer %s", plugin_id, developer["developer_id"])

    existing = await db.fetch_one(
        "system",
        "SELECT id, status FROM plugin_submissions WHERE id = $1 AND developer_id = $2",
        plugin_id,
        developer["developer_id"]
    )

    if not existing:
        logger.warning("Plugin submission not found: %s", plugin_id)
        raise HTTPException(status_code=404, detail="Plugin submission not found")

    if existing["status"] != "pending_review":
        logger.warning("Cannot update plugin submission with status %s", existing["status"])
        raise HTTPException(status_code=400, detail="Cannot update plugin after review started")

    updates = []
    params = [plugin_id, developer["developer_id"]]

    if request.name is not None:
        updates.append(f"name = ${len(params) + 1}")
        params.append(request.name)

    if request.version is not None:
        updates.append(f"version = ${len(params) + 1}")
        params.append(request.version)

    if request.description is not None:
        updates.append(f"description = ${len(params) + 1}")
        params.append(request.description)

    if request.category is not None:
        updates.append(f"category = ${len(params) + 1}")
        params.append(request.category)

    if request.permissions is not None:
        updates.append(f"permissions = ${len(params) + 1}")
        params.append(json.dumps(request.permissions))

    if request.webhook_url is not None:
        updates.append(f"webhook_url = ${len(params) + 1}")
        params.append(request.webhook_url)

    if request.config_schema is not None:
        updates.append(f"config_schema = ${len(params) + 1}")
        params.append(json.dumps(request.config_schema))

    if request.icon_url is not None:
        updates.append(f"icon_url = ${len(params) + 1}")
        params.append(request.icon_url)

    if request.homepage_url is not None:
        updates.append(f"homepage_url = ${len(params) + 1}")
        params.append(request.homepage_url)

    if request.source_url is not None:
        updates.append(f"source_url = ${len(params) + 1}")
        params.append(request.source_url)

    if not updates:
        logger.warning("No updates provided for plugin %s", plugin_id)
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(updates)
    query = f"UPDATE plugin_submissions SET {set_clause} WHERE id = $1 AND developer_id = $2"

    await db.execute("system", query, *params)

    result = await db.fetch_one(
        "system",
        """
        SELECT id, name, version, description, category, status, submitted_at, reviewed_at
        FROM plugin_submissions
        WHERE id = $1 AND developer_id = $2
        """,
        plugin_id,
        developer["developer_id"]
    )

    logger.info("Plugin submission updated: %s", plugin_id)

    return {
        "id": result["id"],
        "name": result["name"],
        "version": result["version"],
        "description": result["description"],
        "category": result["category"],
        "status": result["status"],
        "submitted_at": result["submitted_at"].isoformat() if result["submitted_at"] else None,
        "reviewed_at": result["reviewed_at"].isoformat() if result["reviewed_at"] else None,
    }


@app.post("/admin/plugins/{plugin_id}/review", status_code=200)
async def review_plugin_submission(
    plugin_id: str,
    request: PluginReviewRequest,
    admin: dict = Depends(get_admin_key)
):
    logger.info("Admin reviewing plugin submission %s with status %s", plugin_id, request.status)

    result = await db.fetch_one(
        "system",
        "SELECT id FROM plugin_submissions WHERE id = $1",
        plugin_id
    )

    if not result:
        logger.warning("Plugin submission not found for review: %s", plugin_id)
        raise HTTPException(status_code=404, detail="Plugin submission not found")

    await db.execute(
        "system",
        """
        UPDATE plugin_submissions
        SET status = $1, reviewer_notes = $2, reviewed_at = NOW()
        WHERE id = $3
        """,
        request.status,
        request.notes,
        plugin_id
    )

    await event_bus.publish(
        EventType.PLUGIN_REVIEWED,
        {
            "submission_id": plugin_id,
            "status": request.status,
            "notes": request.notes,
        }
    )

    logger.info("Plugin submission reviewed: %s -> %s", plugin_id, request.status)

    return {"message": f"Plugin submission {request.status}"}


@app.get("/developers/me/analytics", status_code=200)
async def get_developer_analytics(developer: dict = Depends(get_developer_from_key)):
    logger.info("Fetching analytics for developer %s", developer["developer_id"])

    results = await db.fetch_all(
        "system",
        """
        SELECT method, COUNT(*) as total_calls, COUNT(CASE WHEN status_code >= 400 THEN 1 END) as errors,
               AVG(latency_ms) as avg_latency
        FROM developer_usage_logs
        WHERE developer_id = $1 AND created_at > NOW() - INTERVAL '30 days'
        GROUP BY method
        """,
        developer["developer_id"]
    )

    analytics = {
        "period": "30_days",
        "total_calls": 0,
        "total_errors": 0,
        "avg_latency_ms": 0,
        "by_method": [],
    }

    for row in results:
        analytics["total_calls"] += row["total_calls"]
        analytics["total_errors"] += row["errors"]

        analytics["by_method"].append({
            "method": row["method"],
            "calls": row["total_calls"],
            "errors": row["errors"],
            "avg_latency_ms": float(row["avg_latency"]) if row["avg_latency"] else 0,
        })

    if results:
        total_latency_sum = sum(r["avg_latency"] or 0 for r in results)
        analytics["avg_latency_ms"] = total_latency_sum / len(results)

    logger.info("Analytics retrieved for developer %s", developer["developer_id"])

    return analytics


@app.get("/developers/me/analytics/plugins", status_code=200)
async def get_plugin_analytics(developer: dict = Depends(get_developer_from_key)):
    logger.info("Fetching plugin analytics for developer %s", developer["developer_id"])

    plugins = await db.fetch_all(
        "system",
        "SELECT id FROM plugin_submissions WHERE developer_id = $1",
        developer["developer_id"]
    )

    plugin_analytics = []

    for plugin in plugins:
        analytics = await db.fetch_all(
            "system",
            """
            SELECT event_type, success_count, failure_count, avg_latency_ms, date
            FROM plugin_analytics
            WHERE plugin_id = $1 AND date > NOW() - INTERVAL '30 days'
            ORDER BY date DESC
            """,
            plugin["id"]
        )

        total_success = sum(a["success_count"] for a in analytics)
        total_failure = sum(a["failure_count"] for a in analytics)

        plugin_analytics.append({
            "plugin_id": plugin["id"],
            "total_success": total_success,
            "total_failure": total_failure,
            "recent_events": [
                {
                    "event_type": a["event_type"],
                    "success_count": a["success_count"],
                    "failure_count": a["failure_count"],
                    "avg_latency_ms": a["avg_latency_ms"],
                    "date": a["date"].isoformat() if a["date"] else None,
                }
                for a in analytics[:10]
            ],
        })

    logger.info("Plugin analytics retrieved for developer %s", developer["developer_id"])

    return {"plugin_analytics": plugin_analytics}


@app.get("/developers/me/analytics/revenue", status_code=200)
async def get_revenue_analytics(developer: dict = Depends(get_developer_from_key)):
    logger.info("Fetching revenue analytics for developer %s", developer["developer_id"])

    plugins = await db.fetch_all(
        "system",
        "SELECT id, name FROM plugin_submissions WHERE developer_id = $1",
        developer["developer_id"]
    )

    revenue_data = {
        "total_revenue": 0.0,
        "currency": "USD",
        "plugins": [],
    }

    for plugin in plugins:
        revenue_data["plugins"].append({
            "plugin_id": plugin["id"],
            "plugin_name": plugin["name"],
            "revenue": 0.0,
            "installations": 0,
        })

    logger.info("Revenue analytics retrieved for developer %s", developer["developer_id"])

    return revenue_data


SANDBOX_ALLOWED_PREFIXES = [
    "http://localhost:9001/api/",
    "http://localhost:9002/api/",
    "http://localhost:9025/api/",
]


def _validate_sandbox_url(endpoint: str) -> None:
    """Ensure sandbox requests only go to internal platform APIs."""
    if not any(endpoint.startswith(prefix) for prefix in SANDBOX_ALLOWED_PREFIXES):
        raise ValueError("Sandbox only allows requests to internal platform APIs")


@app.post("/sandbox/test", status_code=200)
async def sandbox_test_api_call(
    request: SandboxTestRequest,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Sandbox test for developer %s: %s %s", developer["developer_id"], request.method, request.endpoint)

    # SSRF protection: only allow internal platform API endpoints
    try:
        _validate_sandbox_url(request.endpoint)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Internal server error")

    test_id = str(uuid4())
    start_time = datetime.utcnow()

    try:
        response = await http_client.request(
            method=request.method,
            url=request.endpoint,
            json=request.body if request.method != "GET" else None,
            headers=request.headers,
            timeout=5.0
        )

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000

        response_data = {}
        try:
            response_data = response.json()
        except (json.JSONDecodeError, ValueError):
            response_data = {"body": response.text}

        await db.execute(
            "system",
            """
            INSERT INTO sandbox_logs (id, developer_id, request_type, request_data, response_data, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            test_id,
            developer["developer_id"],
            f"{request.method}",
            json.dumps({"endpoint": request.endpoint, "body": request.body}),
            json.dumps(response_data),
            "success"
        )

        logger.info("Sandbox test completed: %s", test_id)

        return {
            "status_code": response.status_code,
            "response_body": response_data,
            "latency_ms": latency,
        }
    except Exception as e:
        logger.error("Sandbox test failed: %s", str(e))

        await db.execute(
            "system",
            """
            INSERT INTO sandbox_logs (id, developer_id, request_type, request_data, status)
            VALUES ($1, $2, $3, $4, $5)
            """,
            test_id,
            developer["developer_id"],
            f"{request.method}",
            json.dumps({"endpoint": request.endpoint, "body": request.body}),
            "failed"
        )

        raise HTTPException(status_code=502, detail="Sandbox test failed — check logs")


@app.post("/sandbox/webhook-test", status_code=200)
async def sandbox_test_webhook(
    request: WebhookTestRequest,
    developer: dict = Depends(get_developer_from_key)
):
    logger.info("Webhook test for developer %s: %s", developer["developer_id"], request.url)

    test_id = str(uuid4())
    start_time = datetime.utcnow()

    try:
        response = await http_client.post(
            url=request.url,
            json=request.payload,
            timeout=10.0
        )

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000

        response_data = {}
        try:
            response_data = response.json()
        except (json.JSONDecodeError, ValueError):
            response_data = {"body": response.text}

        await db.execute(
            "system",
            """
            INSERT INTO sandbox_logs (id, developer_id, request_type, request_data, response_data, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            test_id,
            developer["developer_id"],
            "webhook",
            json.dumps({"url": request.url, "payload": request.payload}),
            json.dumps(response_data),
            "success"
        )

        logger.info("Webhook test completed: %s", test_id)

        return {
            "status_code": response.status_code,
            "response_body": response_data,
            "latency_ms": latency,
        }
    except Exception as e:
        logger.error("Webhook test failed: %s", str(e))

        await db.execute(
            "system",
            """
            INSERT INTO sandbox_logs (id, developer_id, request_type, request_data, status)
            VALUES ($1, $2, $3, $4, $5)
            """,
            test_id,
            developer["developer_id"],
            "webhook",
            json.dumps({"url": request.url, "payload": request.payload}),
            "failed"
        )

        raise HTTPException(status_code=502, detail="Webhook test failed — check logs")


@app.get("/sandbox/logs", status_code=200)
async def get_sandbox_logs(
    developer: dict = Depends(get_developer_from_key),
    limit: int = 50
):
    logger.info("Fetching sandbox logs for developer %s", developer["developer_id"])

    if limit < 1 or limit > 500:
        limit = 50

    results = await db.fetch_all(
        "system",
        """
        SELECT id, request_type, request_data, response_data, status, created_at
        FROM sandbox_logs
        WHERE developer_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        developer["developer_id"],
        limit
    )

    logs = []
    for row in results:
        logs.append({
            "id": row["id"],
            "request_type": row["request_type"],
            "request_data": json.loads(row["request_data"]) if row["request_data"] else None,
            "response_data": json.loads(row["response_data"]) if row["response_data"] else None,
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    logger.info("Retrieved %d sandbox logs for developer %s", len(logs), developer["developer_id"])

    return {"logs": logs}


@app.get("/admin/developers", status_code=200)
async def list_all_developers(
    admin: dict = Depends(get_admin_key),
    limit: int = 100,
    offset: int = 0
):
    logger.info("Admin fetching all developers")

    if limit < 1 or limit > 500:
        limit = 100

    if offset < 0:
        offset = 0

    results = await db.fetch_all(
        "system",
        """
        SELECT id, email, name, company, is_verified, created_at
        FROM developers
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset
    )

    total = await db.fetch_one(
        "system",
        "SELECT COUNT(*) as count FROM developers"
    )

    developers = []
    for row in results:
        developers.append({
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "company": row["company"],
            "is_verified": row["is_verified"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    logger.info("Admin retrieved %d developers (total: %d)", len(developers), total["count"])

    return {
        "developers": developers,
        "total": total["count"],
        "limit": limit,
        "offset": offset,
    }


@app.get("/admin/stats", status_code=200)
async def get_admin_stats(admin: dict = Depends(get_admin_key)):
    logger.info("Admin fetching portal statistics")

    total_devs = await db.fetch_one(
        "system",
        "SELECT COUNT(*) as count FROM developers"
    )

    verified_devs = await db.fetch_one(
        "system",
        "SELECT COUNT(*) as count FROM developers WHERE is_verified = TRUE"
    )

    total_submissions = await db.fetch_one(
        "system",
        "SELECT COUNT(*) as count FROM plugin_submissions"
    )

    approved_plugins = await db.fetch_one(
        "system",
        "SELECT COUNT(*) as count FROM plugin_submissions WHERE status = 'approved'"
    )

    stats = {
        "total_developers": total_devs["count"],
        "verified_developers": verified_devs["count"],
        "total_plugin_submissions": total_submissions["count"],
        "approved_plugins": approved_plugins["count"],
        "timestamp": datetime.utcnow().isoformat(),
    }

    logger.info("Admin stats retrieved")

    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9036)
