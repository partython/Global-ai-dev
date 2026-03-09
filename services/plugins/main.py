import os
import json
import uuid
import hmac
import hashlib
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum
from pydantic import BaseModel, Field, validator
import logging

from fastapi import FastAPI, Depends, HTTPException, Header, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import aiohttp
from sqlalchemy import text
from shared.core.security import mask_pii
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/priya_plugins")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
if not WEBHOOK_SECRET:
    logger.critical("WEBHOOK_SECRET environment variable must be set")
    WEBHOOK_SECRET = hashlib.sha256(os.urandom(32)).hexdigest()  # Generate random fallback
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 9025))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
WEBHOOK_TIMEOUT = int(os.getenv("WEBHOOK_TIMEOUT", 30))

# SSRF protection — blocked hosts for webhook URLs
import re as _re
import ipaddress as _ipaddress
import socket as _socket
from urllib.parse import urlparse as _urlparse

_BLOCKED_HOSTS = _re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|"
    r"192\.168\.\d+\.\d+|0\.0\.0\.0|"
    r"\[?::1\]?|\[?fe80:.*\]?|\[?fd.*\]?|"
    r"169\.254\.\d+\.\d+|metadata\.google\.internal)$",
    _re.IGNORECASE,
)


def _validate_webhook_url(url: str) -> bool:
    """Validate webhook URL is safe (SSRF protection)."""
    try:
        parsed = _urlparse(url)
        if parsed.scheme not in ("https",):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if _BLOCKED_HOSTS.match(hostname):
            return False
        # Resolve and check IP
        try:
            resolved = _socket.getaddrinfo(hostname, None, _socket.AF_UNSPEC, _socket.SOCK_STREAM)
            for family, socktype, proto, canonname, sockaddr in resolved:
                ip = _ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
        except _socket.gaierror:
            pass
        return True
    except Exception:
        return False

# FastAPI app setup
app = FastAPI(title="Plugin SDK Service", version="1.0.0")
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="plugins")
init_sentry(service_name="plugins", service_port=9025)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="plugins")
app.add_middleware(TracingMiddleware)


# CORS middleware
# Should come from environment config, not hardcoded
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Database connection pool
db_pool: Optional[asyncpg.Pool] = None


# Enums
class PluginCategory(str, Enum):
    CHANNEL = "channel"
    ANALYTICS = "analytics"
    AI_ENHANCEMENT = "ai-enhancement"
    INTEGRATION = "integration"
    WORKFLOW = "workflow"


class PluginStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class PermissionScope(str, Enum):
    READ_ONLY = "read-only"
    READ_WRITE = "read-write"
    ADMIN = "admin"


# Request/Response Models
class PluginMetadata(BaseModel):
    name: str
    version: str
    author: str
    description: str
    category: PluginCategory
    permissions: List[str]
    webhook_url: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None

    @validator("version")
    def validate_semver(cls, v):
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("Version must follow semantic versioning (e.g., 1.0.0)")
        return v


class PluginInstallRequest(BaseModel):
    plugin_id: str
    config: Optional[Dict[str, Any]] = None


class PluginConfigUpdate(BaseModel):
    config: Dict[str, Any]


class DeveloperRegistration(BaseModel):
    email: str
    company: str
    name: str


class PluginPublish(BaseModel):
    name: str
    version: str
    description: str
    category: PluginCategory
    permissions: List[str]
    webhook_url: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None


class EventPayload(BaseModel):
    event_type: str
    tenant_id: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WebhookEvent(BaseModel):
    plugin_id: str
    event_type: str
    tenant_id: str
    data: Dict[str, Any]
    timestamp: datetime


class ResourceUsageMetrics(BaseModel):
    plugin_id: str
    tenant_id: str
    api_calls: int = 0
    webhook_calls: int = 0
    error_count: int = 0
    last_used: Optional[datetime] = None


# Database initialization
async def init_db():
    """Initialize database connection pool and create tables."""
    global db_pool
    db_pool = await asyncpg.create_pool(DB_URL, min_size=5, max_size=20)
    
    async with db_pool.acquire() as conn:
        # Plugins table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugins (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                version VARCHAR(20) NOT NULL,
                author VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(50) NOT NULL,
                permissions JSONB DEFAULT '[]',
                webhook_url VARCHAR(2048),
                config_schema JSONB,
                status VARCHAR(50) DEFAULT 'published',
                installed_at TIMESTAMP,
                activated_at TIMESTAMP,
                is_active BOOLEAN DEFAULT false,
                marketplace BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, name, version)
            );
        """)
        
        # Plugin configurations table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_configs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                plugin_id UUID NOT NULL REFERENCES plugins(id),
                config JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, plugin_id)
            );
        """)
        
        # API keys table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_api_keys (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                plugin_id UUID NOT NULL REFERENCES plugins(id),
                key_hash VARCHAR(255) NOT NULL UNIQUE,
                scope VARCHAR(50) NOT NULL,
                rate_limit INT DEFAULT 1000,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                UNIQUE(tenant_id, plugin_id, scope)
            );
        """)
        
        # Event subscriptions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_subscriptions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                plugin_id UUID NOT NULL REFERENCES plugins(id),
                event_type VARCHAR(255) NOT NULL,
                webhook_url VARCHAR(2048) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, plugin_id, event_type)
            );
        """)
        
        # Event logs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_event_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                plugin_id UUID NOT NULL,
                event_type VARCHAR(255) NOT NULL,
                payload JSONB,
                status VARCHAR(50) DEFAULT 'pending',
                retry_count INT DEFAULT 0,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Resource usage tracking table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_resource_usage (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                plugin_id UUID NOT NULL,
                api_calls INT DEFAULT 0,
                webhook_calls INT DEFAULT 0,
                error_count INT DEFAULT 0,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, plugin_id)
            );
        """)
        
        # Developers table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS developers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL UNIQUE,
                company VARCHAR(255),
                name VARCHAR(255) NOT NULL,
                api_key VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Plugin analytics table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_analytics (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                plugin_id UUID NOT NULL,
                event_type VARCHAR(255),
                success_count INT DEFAULT 0,
                failure_count INT DEFAULT 0,
                avg_latency_ms FLOAT DEFAULT 0,
                date DATE DEFAULT CURRENT_DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant_id, plugin_id, event_type, date)
            );
        """)
        
        # Create indexes
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_plugins_tenant ON plugins(tenant_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_plugins_marketplace ON plugins(marketplace) WHERE marketplace = true;")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON plugin_subscriptions(tenant_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_event_logs_status ON plugin_event_logs(status);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_resource_usage_tenant ON plugin_resource_usage(tenant_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_plugin ON plugin_analytics(plugin_id);")
    
    logger.info("Database initialized successfully")


async def close_db():
    """Close database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()


# Utility functions
def generate_api_key() -> str:
    """Generate a secure API key."""
    return f"pk_{uuid.uuid4().hex}"


def hash_api_key(key: str) -> str:
    """Hash API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_webhook_signature(payload: str, secret: str) -> str:
    """Generate HMAC signature for webhook payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify webhook signature."""
    expected = generate_webhook_signature(payload, secret)
    return hmac.compare_digest(expected, signature)


async def get_tenant_id(x_tenant_id: str = Header(None)) -> str:
    """
    Extract and validate tenant ID from headers.

    SECURITY NOTE: This header MUST only be set by the API gateway after JWT verification.
    Direct external calls to the plugins service must be blocked by network policy.
    The gateway validates the JWT and injects X-Tenant-ID from verified claims.
    """
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    # Validate format: must be UUID-like to prevent injection
    import re as _re
    if not _re.match(r'^[a-f0-9\-]{36}$', x_tenant_id):
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    return x_tenant_id


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key from header."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    return x_api_key


# API Endpoints

@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    await init_db()
    await event_bus.startup()
    logger.info("Plugin SDK Service started on port %d", API_PORT)


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await event_bus.shutdown()
    await close_db()
    shutdown_tracing()


@app.get("/api/v1/plugins/health")
async def health_check():
    """Health check endpoint."""
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logger.error("Database health check failed: %s", str(e))
        db_status = "degraded"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "plugin-sdk",
        "port": API_PORT
    }


@app.get("/api/v1/plugins/marketplace")
async def list_marketplace_plugins(
    tenant_id: str = Depends(get_tenant_id),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None
):
    """Browse available plugins in marketplace."""
    async with db_pool.acquire() as conn:
        query = """
            SELECT id, name, version, author, description, category, permissions, 
                   webhook_url, config_schema, created_at
            FROM plugins
            WHERE marketplace = true AND status = $1
        """
        params = ["published"]
        
        if category:
            query += " AND category = $4"
            params.append(category)
        
        query += " ORDER BY created_at DESC LIMIT $2 OFFSET $3"
        plugins = await conn.fetch(query, *params, limit, offset)
    
    return {
        "plugins": [dict(p) for p in plugins],
        "total": len(plugins),
        "limit": limit,
        "offset": offset
    }


@app.get("/api/v1/plugins/{plugin_id}")
async def get_plugin_details(
    plugin_id: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """Get plugin details."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid plugin ID format")
    
    tenant_uuid = uuid.UUID(tenant_id)
    
    async with db_pool.acquire() as conn:
        plugin = await conn.fetchrow("""
            SELECT id, name, version, author, description, category, permissions,
                   webhook_url, config_schema, is_active, created_at, marketplace
            FROM plugins
            WHERE id = $1 AND (marketplace = true OR tenant_id = $2)
        """, plugin_uuid, tenant_uuid)
    
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    return dict(plugin)


@app.post("/api/v1/plugins/install")
async def install_plugin(
    request: PluginInstallRequest,
    tenant_id: str = Depends(get_tenant_id),
    background_tasks: BackgroundTasks = None
):
    """Install plugin for tenant."""
    try:
        tenant_uuid = uuid.UUID(tenant_id)
        plugin_uuid = uuid.UUID(request.plugin_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        # Check if plugin exists in marketplace
        plugin = await conn.fetchrow(
            "SELECT * FROM plugins WHERE id = $1 AND marketplace = true",
            plugin_uuid
        )
        
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found in marketplace")
        
        # Check if already installed
        existing = await conn.fetchrow(
            "SELECT id FROM plugins WHERE id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        if existing:
            raise HTTPException(status_code=409, detail="Plugin already installed")
        
        # Install plugin
        installed = await conn.fetchrow("""
            INSERT INTO plugins (id, tenant_id, name, version, author, description, 
                                category, permissions, webhook_url, config_schema,
                                is_active, installed_at, status, marketplace)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, true, CURRENT_TIMESTAMP, $11, false)
            RETURNING id, name, version
        """, plugin_uuid, tenant_uuid, plugin["name"], plugin["version"],
            plugin["author"], plugin["description"], plugin["category"],
            plugin["permissions"], plugin["webhook_url"], plugin["config_schema"],
            "published")
        
        # Save configuration
        if request.config:
            await conn.execute("""
                INSERT INTO plugin_configs (tenant_id, plugin_id, config)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
            """, tenant_uuid, plugin_uuid, json.dumps(request.config))
        
        # Initialize resource usage tracking
        await conn.execute("""
            INSERT INTO plugin_resource_usage (tenant_id, plugin_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """, tenant_uuid, plugin_uuid)
    
    return {
        "status": "installed",
        "plugin_id": str(installed["id"]),
        "name": installed["name"],
        "version": installed["version"]
    }


@app.delete("/api/v1/plugins/{plugin_id}/uninstall")
async def uninstall_plugin(
    plugin_id: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """Uninstall plugin for tenant."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        # Verify plugin exists
        plugin = await conn.fetchrow(
            "SELECT id FROM plugins WHERE id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        
        # Delete configurations
        await conn.execute(
            "DELETE FROM plugin_configs WHERE plugin_id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        # Delete subscriptions
        await conn.execute(
            "DELETE FROM plugin_subscriptions WHERE plugin_id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        # Delete API keys
        await conn.execute(
            "DELETE FROM plugin_api_keys WHERE plugin_id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        # Delete resource usage
        await conn.execute(
            "DELETE FROM plugin_resource_usage WHERE plugin_id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        # Delete plugin
        await conn.execute(
            "DELETE FROM plugins WHERE id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
    
    return {"status": "uninstalled", "plugin_id": plugin_id}


@app.put("/api/v1/plugins/{plugin_id}/activate")
async def activate_plugin(
    plugin_id: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """Activate plugin for tenant."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        plugin = await conn.fetchrow("""
            UPDATE plugins
            SET is_active = true, activated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND tenant_id = $2
            RETURNING id, name, is_active
        """, plugin_uuid, tenant_uuid)
    
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    logger.info("Plugin %s activated for tenant %s", plugin_id, tenant_id)
    
    return {"status": "activated", "plugin_id": str(plugin["id"]), "is_active": plugin["is_active"]}


@app.put("/api/v1/plugins/{plugin_id}/deactivate")
async def deactivate_plugin(
    plugin_id: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """Deactivate plugin for tenant."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        plugin = await conn.fetchrow("""
            UPDATE plugins
            SET is_active = false, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1 AND tenant_id = $2
            RETURNING id, name, is_active
        """, plugin_uuid, tenant_uuid)
    
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    logger.info("Plugin %s deactivated for tenant %s", plugin_id, tenant_id)
    
    return {"status": "deactivated", "plugin_id": str(plugin["id"]), "is_active": plugin["is_active"]}


@app.get("/api/v1/plugins/installed")
async def list_installed_plugins(
    tenant_id: str = Depends(get_tenant_id),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    is_active: Optional[bool] = None
):
    """List installed plugins for tenant."""
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        query = """
            SELECT id, name, version, author, description, category, is_active,
                   installed_at, activated_at
            FROM plugins
            WHERE tenant_id = $1 AND marketplace = false
        """
        params = [tenant_uuid]
        
        if is_active is not None:
            query += " AND is_active = $4"
            params.append(is_active)
        
        query += " ORDER BY installed_at DESC LIMIT $2 OFFSET $3"
        plugins = await conn.fetch(query, *params, limit, offset)
    
    return {
        "plugins": [dict(p) for p in plugins],
        "total": len(plugins),
        "limit": limit,
        "offset": offset
    }


@app.put("/api/v1/plugins/{plugin_id}/config")
async def update_plugin_config(
    plugin_id: str,
    request: PluginConfigUpdate,
    tenant_id: str = Depends(get_tenant_id)
):
    """Update plugin configuration for tenant."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        # Verify plugin exists
        plugin = await conn.fetchrow(
            "SELECT id FROM plugins WHERE id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        
        config = await conn.fetchrow("""
            INSERT INTO plugin_configs (tenant_id, plugin_id, config)
            VALUES ($1, $2, $3)
            ON CONFLICT (tenant_id, plugin_id)
            DO UPDATE SET config = $3, updated_at = CURRENT_TIMESTAMP
            RETURNING config, updated_at
        """, tenant_uuid, plugin_uuid, json.dumps(request.config))
    
    return {"status": "updated", "plugin_id": plugin_id, "config": config["config"]}


@app.get("/api/v1/plugins/{plugin_id}/config")
async def get_plugin_config(
    plugin_id: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """Get plugin configuration for tenant."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        config = await conn.fetchrow("""
            SELECT config FROM plugin_configs
            WHERE plugin_id = $1 AND tenant_id = $2
        """, plugin_uuid, tenant_uuid)
    
    if not config:
        return {"plugin_id": plugin_id, "config": {}}
    
    return {"plugin_id": plugin_id, "config": config["config"]}


@app.post("/api/v1/plugins/developer/register")
async def register_developer(request: DeveloperRegistration):
    """Register as plugin developer."""
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    
    async with db_pool.acquire() as conn:
        try:
            developer = await conn.fetchrow("""
                INSERT INTO developers (email, company, name, api_key)
                VALUES ($1, $2, $3, $4)
                RETURNING id, email, company, name, created_at
            """, request.email, request.company, request.name, key_hash)
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="Developer already registered")
    
    logger.info("New developer registered: %s", mask_pii(request.email))
    
    return {
        "developer_id": str(developer["id"]),
        "email": developer["email"],
        "api_key": api_key,
        "message": "Store API key securely. You won't be able to see it again."
    }


@app.post("/api/v1/plugins/developer/publish")
async def publish_plugin(
    request: PluginPublish,
    x_api_key: str = Header(None)
):
    """Publish a plugin to marketplace."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # Validate webhook URL if provided (SSRF protection)
    if request.webhook_url and not _validate_webhook_url(request.webhook_url):
        raise HTTPException(status_code=400, detail="Webhook URL must be HTTPS and not point to private/internal addresses")

    api_key_hash = hash_api_key(x_api_key)

    async with db_pool.acquire() as conn:
        # Verify developer
        developer = await conn.fetchrow(
            "SELECT id FROM developers WHERE api_key = $1",
            api_key_hash
        )

        if not developer:
            raise HTTPException(status_code=401, detail="Invalid API key")

        # Publish plugin
        plugin = await conn.fetchrow("""
            INSERT INTO plugins (
                id, tenant_id, name, version, author, description, category,
                permissions, webhook_url, config_schema, status, marketplace
            )
            VALUES (
                gen_random_uuid(), $1, $2, $3, $2, $4, $5, $6, $7, $8, $9, true
            )
            RETURNING id, name, version, created_at
        """, developer["id"], request.name, request.version,
            request.description, request.category.value,
            json.dumps(request.permissions), request.webhook_url or None,
            json.dumps(request.config_schema) if request.config_schema else None,
            "published")
    
    logger.info("Plugin published: %s v%s", request.name, request.version)
    
    return {
        "plugin_id": str(plugin["id"]),
        "name": plugin["name"],
        "version": plugin["version"],
        "status": "published"
    }


@app.post("/api/v1/plugins/webhooks/{plugin_id}")
async def webhook_receiver(
    plugin_id: str,
    payload: Dict[str, Any],
    x_webhook_signature: str = Header(None)
):
    """Webhook receiver for plugin events."""
    if not x_webhook_signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    
    payload_str = json.dumps(payload, sort_keys=True)
    
    if not verify_webhook_signature(payload_str, x_webhook_signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    logger.info("Webhook received for plugin %s", plugin_id)
    
    return {"status": "received", "plugin_id": plugin_id}


async def deliver_webhook(
    webhook_url: str,
    event: WebhookEvent,
    plugin_id: str,
    tenant_id: str,
    retry_count: int = 0
):
    """Deliver webhook to plugin with retry logic and SSRF protection."""
    if not _validate_webhook_url(webhook_url):
        logger.warning("Webhook delivery blocked (SSRF): plugin=%s, url=%s", plugin_id, webhook_url)
        return False
    payload = event.dict(by_alias=False)
    payload_str = json.dumps(payload, sort_keys=True)
    signature = generate_webhook_signature(payload_str, WEBHOOK_SECRET)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={
                    "X-Webhook-Signature": signature,
                    "X-Tenant-ID": tenant_id,
                    "Content-Type": "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=WEBHOOK_TIMEOUT)
            ) as resp:
                if resp.status >= 400:
                    raise Exception(f"HTTP {resp.status}: {await resp.text()}")
                
                logger.info("Webhook delivered to %s", webhook_url)
                return True
    except Exception as e:
        logger.error("Webhook delivery failed (attempt %d): %s", retry_count + 1, str(e))
        
        if retry_count < MAX_RETRIES:
            delay = 2 ** retry_count
            await asyncio.sleep(delay)
            return await deliver_webhook(webhook_url, event, plugin_id, tenant_id, retry_count + 1)
        return False


@app.post("/api/v1/plugins/events/emit")
async def emit_event(
    event: EventPayload,
    tenant_id: str = Depends(get_tenant_id),
    background_tasks: BackgroundTasks = None
):
    """Emit event to subscribed plugins."""
    try:
        tenant_uuid = uuid.UUID(event.tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    
    if str(tenant_uuid) != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    
    async with db_pool.acquire() as conn:
        # Get subscribed active plugins
        subscriptions = await conn.fetch("""
            SELECT ps.plugin_id, ps.webhook_url, p.id
            FROM plugin_subscriptions ps
            JOIN plugins p ON ps.plugin_id = p.id
            WHERE ps.tenant_id = $1 AND ps.event_type = $2 AND p.is_active = true
        """, tenant_uuid, event.event_type)
        
        # Log event
        for sub in subscriptions:
            await conn.execute("""
                INSERT INTO plugin_event_logs (tenant_id, plugin_id, event_type, payload, status)
                VALUES ($1, $2, $3, $4, $5)
            """, tenant_uuid, sub["plugin_id"], event.event_type, json.dumps(event.dict()), "pending")
    
    # Queue webhooks for delivery
    delivered = 0
    for sub in subscriptions:
        webhook_event = WebhookEvent(
            plugin_id=str(sub["plugin_id"]),
            event_type=event.event_type,
            tenant_id=str(tenant_uuid),
            data=event.data,
            timestamp=event.timestamp
        )
        
        if background_tasks:
            background_tasks.add_task(
                deliver_webhook,
                sub["webhook_url"],
                webhook_event,
                str(sub["plugin_id"]),
                tenant_id
            )
            delivered += 1
    
    logger.info("Event %s emitted to %d plugins", event.event_type, delivered)
    
    return {
        "status": "emitted",
        "event_type": event.event_type,
        "subscribed_plugins": len(subscriptions),
        "delivered": delivered
    }


@app.post("/api/v1/plugins/{plugin_id}/subscribe/{event_type}")
async def subscribe_to_event(
    plugin_id: str,
    event_type: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """Subscribe plugin to event."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        # Get plugin webhook URL
        plugin = await conn.fetchrow(
            "SELECT webhook_url FROM plugins WHERE id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        if not plugin or not plugin["webhook_url"]:
            raise HTTPException(status_code=400, detail="Plugin has no webhook URL configured")
        
        # Create subscription
        await conn.execute("""
            INSERT INTO plugin_subscriptions (tenant_id, plugin_id, event_type, webhook_url)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tenant_id, plugin_id, event_type) DO NOTHING
        """, tenant_uuid, plugin_uuid, event_type, plugin["webhook_url"])
    
    logger.info("Plugin %s subscribed to %s", plugin_id, event_type)
    
    return {"status": "subscribed", "plugin_id": plugin_id, "event_type": event_type}


@app.delete("/api/v1/plugins/{plugin_id}/subscribe/{event_type}")
async def unsubscribe_from_event(
    plugin_id: str,
    event_type: str,
    tenant_id: str = Depends(get_tenant_id)
):
    """Unsubscribe plugin from event."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM plugin_subscriptions
            WHERE plugin_id = $1 AND tenant_id = $2 AND event_type = $3
        """, plugin_uuid, tenant_uuid, event_type)
    
    logger.info("Plugin %s unsubscribed from %s", plugin_id, event_type)
    
    return {"status": "unsubscribed", "plugin_id": plugin_id, "event_type": event_type}


@app.post("/api/v1/plugins/{plugin_id}/api-keys")
async def create_api_key(
    plugin_id: str,
    scope: PermissionScope = PermissionScope.READ_ONLY,
    rate_limit: int = 1000,
    tenant_id: str = Depends(get_tenant_id)
):
    """Create scoped API key for plugin."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    if rate_limit < 1:
        raise HTTPException(status_code=400, detail="Rate limit must be >= 1")
    
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)
    
    async with db_pool.acquire() as conn:
        # Verify plugin exists
        plugin = await conn.fetchrow(
            "SELECT id FROM plugins WHERE id = $1 AND tenant_id = $2",
            plugin_uuid, tenant_uuid
        )
        
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        
        key = await conn.fetchrow("""
            INSERT INTO plugin_api_keys (tenant_id, plugin_id, key_hash, scope, rate_limit)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, created_at
        """, tenant_uuid, plugin_uuid, key_hash, scope.value, rate_limit)
    
    logger.info("API key created for plugin %s with scope %s", plugin_id, scope.value)
    
    return {
        "api_key": api_key,
        "scope": scope.value,
        "rate_limit": rate_limit,
        "message": "Store this key securely. You won't be able to see it again."
    }


@app.get("/api/v1/plugins/{plugin_id}/analytics")
async def get_plugin_analytics(
    plugin_id: str,
    tenant_id: str = Depends(get_tenant_id),
    days: int = Query(7, ge=1, le=90)
):
    """Get plugin analytics and usage metrics."""
    try:
        plugin_uuid = uuid.UUID(plugin_id)
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    async with db_pool.acquire() as conn:
        # Get resource usage
        usage = await conn.fetchrow("""
            SELECT api_calls, webhook_calls, error_count, last_used
            FROM plugin_resource_usage
            WHERE plugin_id = $1 AND tenant_id = $2
        """, plugin_uuid, tenant_uuid)
        
        # Get analytics
        analytics = await conn.fetch("""
            SELECT event_type, success_count, failure_count, avg_latency_ms, date
            FROM plugin_analytics
            WHERE plugin_id = $1 AND tenant_id = $2 AND date >= CURRENT_DATE - INTERVAL '1 day' * $3
            ORDER BY date DESC
        """, plugin_uuid, tenant_uuid, days)
    
    if not usage:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    return {
        "plugin_id": plugin_id,
        "resource_usage": dict(usage),
        "analytics": [dict(a) for a in analytics],
        "period_days": days
    }


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host=API_HOST, port=API_PORT)
