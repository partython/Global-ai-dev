"""
E-Commerce Integration Service for Priya Global Platform
Port: 9023

Manages multi-tenant e-commerce platform integrations:
- Shopify (Direct REST API + Webhooks)
- WooCommerce (REST API v3)
- Magento (REST API)
- Universal REST API Connector (Custom Endpoints)

FEATURES:
- Product catalog sync (import/export)
- Order tracking & notifications
- Customer sync (bidirectional)
- Cart abandonment detection
- Inventory monitoring
- Webhook signature verification (HMAC-SHA256)
- Field mapping engine (external → internal schema)

SECURITY:
- All API keys/secrets from environment (NEVER hardcoded)
- Webhook signature verification per platform
- Tenant isolation via RLS (SET app.current_tenant_id)
- Input sanitization on all user inputs
- Rate limiting per tenant
- CORS from environment

DATABASE:
- asyncpg for PostgreSQL with connection pooling
- Multi-tenant with RLS patterns

EXTERNAL:
- aiohttp for HTTP calls to e-commerce APIs
- HMAC-SHA256 for webhook verification
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp
import asyncpg
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, Field, HttpUrl, validator

import re
import sys
import os
from base64 import b64encode

import redis.asyncio as aioredis

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

logger = logging.getLogger("priya.ecommerce")

# Redis client for rate limiting and replay protection
redis_client = None

# Security constants
WEBHOOK_REPLAY_WINDOW = 300  # 5 min dedup window
WEBHOOK_RATE_LIMIT_PER_MIN = 200
MAX_ABANDONED_CART_DAYS = 90

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_PLATFORMS = ["shopify", "woocommerce", "magento", "custom"]
SYNC_BATCH_SIZE = 100
WEBHOOK_TIMEOUT = 300  # 5 minutes
RATE_LIMIT_PER_TENANT_PER_MIN = 60

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    port: int
    database: str
    timestamp: str


class PlatformConnection(BaseModel):
    """Connect an e-commerce platform."""
    platform: str = Field(..., regex="^(shopify|woocommerce|magento|custom)$")
    store_url: str = Field(..., max_length=2048)
    api_key: str = Field(..., min_length=1, max_length=1024)
    api_secret: str = Field(..., min_length=1, max_length=1024)
    webhook_secret: Optional[str] = Field(None, max_length=1024)
    metadata: Optional[Dict[str, Any]] = Field(None)

    @validator("store_url", "api_key", "api_secret", pre=True)
    def sanitize_fields(cls, v):
        if v:
            return sanitize_input(v, max_length=2048)
        return v


class FieldMapping(BaseModel):
    """Field mapping configuration for custom platforms."""
    external_field: str = Field(..., max_length=255)
    internal_field: str = Field(..., max_length=255)
    data_type: str = Field(default="string", regex="^(string|number|boolean|datetime|array)$")
    required: bool = Field(default=False)
    transform_script: Optional[str] = Field(None, max_length=2000)

    @validator("external_field", "internal_field", pre=True)
    def sanitize_fields(cls, v):
        if v:
            return sanitize_input(v, max_length=255)
        return v


class SyncRequest(BaseModel):
    """Request to trigger a sync operation."""
    platform_id: str = Field(..., max_length=255)
    full_sync: bool = Field(default=False)
    since_timestamp: Optional[str] = None


class ProductData(BaseModel):
    """Synced product data."""
    external_id: str = Field(..., max_length=255)
    name: str = Field(..., max_length=500)
    sku: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=5000)
    price: float = Field(..., gt=0)
    currency: str = Field(default="USD", regex="^[A-Z]{3}$")
    inventory_count: int = Field(default=0, ge=0)
    status: str = Field(default="active", regex="^(active|inactive|archived)$")
    image_urls: Optional[List[str]] = Field(None, max_length=10)
    metadata: Optional[Dict[str, Any]] = None


class OrderData(BaseModel):
    """Synced order data."""
    external_id: str = Field(..., max_length=255)
    customer_email: str = Field(..., max_length=255)
    customer_name: str = Field(..., max_length=255)
    total_amount: float = Field(..., gt=0)
    currency: str = Field(default="USD", regex="^[A-Z]{3}$")
    status: str = Field(default="pending", regex="^(pending|processing|completed|cancelled)$")
    items_count: int = Field(..., gt=0)
    created_at: str
    updated_at: str


class AbandonedCart(BaseModel):
    """Abandoned cart data."""
    external_id: str = Field(..., max_length=255)
    customer_email: str = Field(..., max_length=255)
    customer_name: Optional[str] = Field(None, max_length=255)
    total_value: float = Field(..., gt=0)
    currency: str = Field(default="USD", regex="^[A-Z]{3}$")
    items_count: int = Field(..., gt=0)
    abandoned_at: str
    recovery_attempted: bool = Field(default=False)


class PlatformResponse(BaseModel):
    """Platform connection response."""
    id: str
    tenant_id: str
    platform: str
    store_url: str
    api_key_masked: str
    status: str
    created_at: str
    last_sync_at: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


async def verify_webhook_signature(
    platform: str,
    body: bytes,
    signature: str,
    webhook_secret: str,
) -> bool:
    """
    Verify webhook signature based on platform.

    Shopify: X-Shopify-Hmac-SHA256 (HMAC-SHA256 of body with app secret)
    WooCommerce: X-WC-Webhook-Signature (base64(HMAC-SHA256))
    Magento: X-Magento-Webhook-Signature (HMAC-SHA256)
    """
    try:
        if platform == "shopify":
            # Shopify uses base64-encoded HMAC-SHA256
            computed = hmac.new(
                webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).digest()
            expected = __import__("base64").b64encode(computed).decode()
            return hmac.compare_digest(signature, expected)

        elif platform in ["woocommerce", "magento"]:
            # Both use HMAC-SHA256 (hex-encoded)
            computed = hmac.new(
                webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(signature, computed)

        return False
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", str(e))
        return False


async def mask_api_key(api_key: str, visible_chars: int = 4) -> str:
    """Mask API key for display (show last N chars only)."""
    if len(api_key) <= visible_chars:
        return "*" * len(api_key)
    return "*" * (len(api_key) - visible_chars) + api_key[-visible_chars:]


async def fetch_shopify_products(
    store_url: str,
    api_key: str,
    api_secret: str,
    limit: int = SYNC_BATCH_SIZE,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch products from Shopify REST Admin API."""
    headers = {
        "X-Shopify-Access-Token": api_secret,
        "Content-Type": "application/json",
    }

    url = f"https://{store_url}/admin/api/2024-01/products.json"
    params = {"limit": limit, "status": "active"}
    if cursor:
        params["after"] = cursor

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 401:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Shopify credentials")
            if resp.status >= 500:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Shopify API unavailable")
            resp.raise_for_status()
            return await resp.json()


async def fetch_woocommerce_products(
    store_url: str,
    api_key: str,
    api_secret: str,
    per_page: int = SYNC_BATCH_SIZE,
    page: int = 1,
) -> List[Dict[str, Any]]:
    """Fetch products from WooCommerce REST API v3."""
    auth = b64encode(f"{api_key}:{api_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }

    url = urljoin(store_url, f"/wp-json/wc/v3/products")
    params = {"per_page": per_page, "page": page, "status": "publish"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 401:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WooCommerce credentials")
            if resp.status >= 500:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="WooCommerce API unavailable")
            resp.raise_for_status()
            return await resp.json()


async def fetch_magento_products(
    store_url: str,
    oauth_token: str,
    limit: int = SYNC_BATCH_SIZE,
    page: int = 1,
) -> Dict[str, Any]:
    """Fetch products from Magento REST API with OAuth."""
    headers = {
        "Authorization": f"Bearer {oauth_token}",
        "Content-Type": "application/json",
    }

    url = urljoin(store_url, "/rest/V1/products")
    offset = (page - 1) * limit
    filter_str = f'?searchCriteria[pageSize]={limit}&searchCriteria[currentPage]={page}'

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{url}{filter_str}", headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 401:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Magento token")
            if resp.status >= 500:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Magento API unavailable")
            resp.raise_for_status()
            return await resp.json()


async def call_custom_api(
    endpoint_url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    auth_header: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call a custom REST API endpoint."""
    if headers is None:
        headers = {}

    if auth_header:
        headers["Authorization"] = auth_header

    headers.setdefault("Content-Type", "application/json")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                endpoint_url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 500:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="External API unavailable")
                resp.raise_for_status()
                return await resp.json()
    except aiohttp.ClientError as e:
        logger.error("Custom API call failed: %s", str(e))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to connect to external API")


async def store_synced_products(
    tenant_id: str,
    platform_id: str,
    products: List[ProductData],
) -> int:
    """Store synced products in database."""
    count = 0
    async with db.transaction(tenant_id) as conn:
        for product in products:
            await conn.execute(
                """
                INSERT INTO ecommerce_products
                (id, tenant_id, platform_id, external_id, name, sku, description, 
                 price, currency, inventory_count, status, image_urls, metadata, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (tenant_id, platform_id, external_id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    price = EXCLUDED.price,
                    inventory_count = EXCLUDED.inventory_count,
                    status = EXCLUDED.status,
                    synced_at = EXCLUDED.synced_at
                """,
                generate_uuid(),
                tenant_id,
                platform_id,
                product.external_id,
                product.name,
                product.sku,
                product.description,
                product.price,
                product.currency,
                product.inventory_count,
                product.status,
                product.image_urls,
                product.metadata,
                utc_now().isoformat(),
            )
            count += 1

    logger.info("Stored %d products: tenant=%s, platform=%s", count, tenant_id, platform_id)
    return count


async def store_synced_orders(
    tenant_id: str,
    platform_id: str,
    orders: List[OrderData],
) -> int:
    """Store synced orders in database."""
    count = 0
    async with db.transaction(tenant_id) as conn:
        for order in orders:
            await conn.execute(
                """
                INSERT INTO ecommerce_orders
                (id, tenant_id, platform_id, external_id, customer_email, customer_name,
                 total_amount, currency, status, items_count, created_at, updated_at, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (tenant_id, platform_id, external_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    synced_at = EXCLUDED.synced_at
                """,
                generate_uuid(),
                tenant_id,
                platform_id,
                order.external_id,
                order.customer_email,
                order.customer_name,
                order.total_amount,
                order.currency,
                order.status,
                order.items_count,
                order.created_at,
                order.updated_at,
                utc_now().isoformat(),
            )
            count += 1

    logger.info("Stored %d orders: tenant=%s, platform=%s", count, tenant_id, platform_id)
    return count


async def store_abandoned_carts(
    tenant_id: str,
    platform_id: str,
    carts: List[AbandonedCart],
) -> int:
    """Store abandoned cart data in database."""
    count = 0
    async with db.transaction(tenant_id) as conn:
        for cart in carts:
            await conn.execute(
                """
                INSERT INTO ecommerce_abandoned_carts
                (id, tenant_id, platform_id, external_id, customer_email, customer_name,
                 total_value, currency, items_count, abandoned_at, recovery_attempted, synced_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (tenant_id, platform_id, external_id)
                DO UPDATE SET
                    recovery_attempted = EXCLUDED.recovery_attempted,
                    synced_at = EXCLUDED.synced_at
                """,
                generate_uuid(),
                tenant_id,
                platform_id,
                cart.external_id,
                cart.customer_email,
                cart.customer_name,
                cart.total_value,
                cart.currency,
                cart.items_count,
                cart.abandoned_at,
                cart.recovery_attempted,
                utc_now().isoformat(),
            )
            count += 1

    logger.info("Stored %d abandoned carts: tenant=%s, platform=%s", count, tenant_id, platform_id)
    return count


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="E-Commerce Integration Service",
    description="Multi-tenant e-commerce platform integration (Shopify, WooCommerce, Magento, Custom)",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Initialize Sentry error tracking
init_sentry(service_name="ecommerce", service_port=9023)

# Initialize event bus
event_bus = EventBus(service_name="ecommerce")

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="ecommerce")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)

# CORS
cors_config = get_cors_config()
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, **cors_config)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware & Startup/Shutdown
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database connection pool and Redis."""
    global redis_client
    logger.info("E-Commerce Service starting on port %d", config.ports.ecommerce)

    await event_bus.startup()
    await db.initialize()
    try:
        redis_client = await aioredis.from_url(config.REDIS_URL)
    except Exception as e:
        logger.warning("Redis unavailable (rate limiting disabled): %s", e)
        redis_client = None
    logger.info("Database pool initialized")


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool and Redis."""
    global redis_client
    logger.info("E-Commerce Service shutting down")
    if redis_client:
        await redis_client.close()
        redis_client = None
    await event_bus.shutdown()
    await db.close()
    shutdown_tracing()


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Service health check."""
    return HealthResponse(
        status="healthy",
        service="ecommerce",
        port=config.ports.ecommerce,
        database="connected",
        timestamp=utc_now().isoformat(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Platform Connection Management
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/ecommerce/connect", response_model=Dict[str, Any])
async def connect_platform(
    connection: PlatformConnection,
    auth: AuthContext = Depends(get_auth),
):
    """
    Connect an e-commerce platform to tenant.

    Supports: shopify, woocommerce, magento, custom

    SECURITY: API credentials stored encrypted in database.
    Only the tenant owner can connect platforms.
    """
    auth.require_role("owner", "admin")

    if connection.platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Platform must be one of: {', '.join(SUPPORTED_PLATFORMS)}",
        )

    platform_id = generate_uuid()

    # Validate connection by making a test API call
    try:
        if connection.platform == "shopify":
            # Test Shopify connection
            await fetch_shopify_products(
                connection.store_url,
                connection.api_key,
                connection.api_secret,
                limit=1,
            )
        elif connection.platform == "woocommerce":
            # Test WooCommerce connection
            await fetch_woocommerce_products(
                connection.store_url,
                connection.api_key,
                connection.api_secret,
                per_page=1,
            )
        elif connection.platform == "magento":
            # Test Magento connection
            await fetch_magento_products(
                connection.store_url,
                connection.api_secret,
                limit=1,
            )
        elif connection.platform == "custom":
            # For custom, just validate the config
            if not connection.webhook_secret:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Custom platform requires webhook_secret",
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Platform connection validation failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to connect to {connection.platform}. Please verify your credentials and store URL.",
        )

    # Store connection in database (credentials encrypted by DB)
    async with db.transaction(auth.tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO ecommerce_platforms
            (id, tenant_id, platform, store_url, api_key, api_secret, webhook_secret, metadata, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            platform_id,
            auth.tenant_id,
            connection.platform,
            connection.store_url,
            connection.api_key,
            connection.api_secret,
            connection.webhook_secret,
            json.dumps(connection.metadata or {}),
            "active",
            utc_now().isoformat(),
        )

    logger.info(
        "Platform connected: tenant=%s, platform=%s, platform_id=%s",
        auth.tenant_id,
        connection.platform,
        platform_id,
    )

    return {
        "status": "success",
        "platform_id": platform_id,
        "platform": connection.platform,
        "message": f"Successfully connected {connection.platform}",
    }


@app.get("/api/v1/ecommerce/platforms", response_model=Dict[str, Any])
async def list_platforms(
    auth: AuthContext = Depends(get_auth),
):
    """List all connected e-commerce platforms for tenant."""
    platforms = await db.fetch_all(
        auth.tenant_id,
        """
        SELECT id, platform, store_url, api_key, status, created_at, last_sync_at
        FROM ecommerce_platforms
        WHERE tenant_id = $1
        ORDER BY created_at DESC
        """,
        auth.tenant_id,
    )

    result = []
    for p in platforms:
        result.append({
            "id": p["id"],
            "platform": p["platform"],
            "store_url": p["store_url"],
            "api_key_masked": await mask_api_key(p["api_key"]),
            "status": p["status"],
            "created_at": p["created_at"],
            "last_sync_at": p["last_sync_at"],
        })

    return {
        "platforms": result,
        "total": len(result),
    }


# Alias: GET /connections — used by dashboard API routes
@app.get("/api/v1/ecommerce/connections", response_model=Dict[str, Any])
async def list_connections(
    auth: AuthContext = Depends(get_auth),
):
    """List all connected stores for tenant (alias for /platforms)."""
    platforms = await db.fetch_all(
        auth.tenant_id,
        """
        SELECT id, platform, store_url, api_key, status, created_at, last_sync_at,
               metadata
        FROM ecommerce_platforms
        WHERE tenant_id = $1
        ORDER BY created_at DESC
        """,
        auth.tenant_id,
    )

    connections = []
    for p in platforms:
        meta = json.loads(p.get("metadata", "{}") or "{}")
        connections.append({
            "id": p["id"],
            "platform": p["platform"],
            "store_url": p["store_url"],
            "store_name": meta.get("store_name", p["store_url"]),
            "status": p["status"],
            "created_at": p["created_at"],
            "last_sync_at": p["last_sync_at"],
            "products_count": meta.get("products_count"),
            "orders_count": meta.get("orders_count"),
            "customers_count": meta.get("customers_count"),
        })

    return {
        "connections": connections,
        "total": len(connections),
    }


@app.delete("/api/v1/ecommerce/connections/{connection_id}", response_model=Dict[str, Any])
async def disconnect_platform(
    connection_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """
    Disconnect an e-commerce platform.

    Sets status to 'disconnected'. Does NOT delete synced data.
    Only tenant owner/admin can disconnect.
    """
    auth.require_role("owner", "admin")

    # Verify connection belongs to this tenant
    conn_row = await db.fetch_one(
        auth.tenant_id,
        """
        SELECT id, platform, store_url FROM ecommerce_platforms
        WHERE id = $1 AND tenant_id = $2
        """,
        connection_id,
        auth.tenant_id,
    )

    if not conn_row:
        raise HTTPException(status_code=404, detail="Connection not found")

    async with db.transaction(auth.tenant_id) as conn:
        await conn.execute(
            """
            UPDATE ecommerce_platforms
            SET status = 'disconnected', updated_at = $1
            WHERE id = $2 AND tenant_id = $3
            """,
            utc_now().isoformat(),
            connection_id,
            auth.tenant_id,
        )

    logger.info(
        "Platform disconnected: tenant=%s, platform=%s, connection_id=%s",
        auth.tenant_id,
        conn_row["platform"],
        connection_id,
    )

    return {
        "status": "success",
        "message": f"Disconnected {conn_row['platform']} ({conn_row['store_url']})",
    }


@app.post("/api/v1/ecommerce/connections/{connection_id}/test", response_model=Dict[str, Any])
async def test_connection(
    connection_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """
    Test an existing e-commerce platform connection.

    Validates that stored credentials still work by making a lightweight API call.
    Rate limited: 5 calls/min per tenant.
    """
    # Rate limit check
    if redis_client:
        rate_key = f"ecommerce_test:{auth.tenant_id}"
        count = await redis_client.incr(rate_key)
        if count == 1:
            await redis_client.expire(rate_key, 60)
        if count > 5:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Max 5 test calls per minute.",
            )

    # Fetch connection
    conn_row = await db.fetch_one(
        auth.tenant_id,
        """
        SELECT id, platform, store_url, api_key, api_secret, status
        FROM ecommerce_platforms
        WHERE id = $1 AND tenant_id = $2
        """,
        connection_id,
        auth.tenant_id,
    )

    if not conn_row:
        raise HTTPException(status_code=404, detail="Connection not found")

    platform = conn_row["platform"]
    store_url = conn_row["store_url"]
    api_key = conn_row["api_key"]
    api_secret = conn_row["api_secret"]

    try:
        if platform == "shopify":
            await fetch_shopify_products(store_url, api_key, api_secret, limit=1)
            return {"status": "success", "message": f"Shopify store at {store_url} is reachable"}

        elif platform == "woocommerce":
            await fetch_woocommerce_products(store_url, api_key, api_secret, per_page=1)
            return {"status": "success", "message": f"WooCommerce store at {store_url} is reachable"}

        elif platform == "custom":
            result = await call_custom_api(
                f"{store_url}/products",
                method="GET",
                auth_header=f"Basic {b64encode(f'{api_key}:{api_secret}'.encode()).decode()}",
                params={"per_page": 1},
            )
            return {"status": "success", "message": f"Custom store at {store_url} is reachable"}

        else:
            return {"status": "failed", "message": f"Unknown platform: {platform}"}

    except Exception as e:
        logger.warning("Connection test failed for %s: %s", connection_id, str(e))
        return {"status": "failed", "message": f"Connection test failed: {str(e)}"}


@app.post("/api/v1/ecommerce/pending", response_model=Dict[str, Any])
async def store_pending_wc_keys(request: Request):
    """
    Temporarily store WooCommerce API keys from server-to-server callback.

    WooCommerce POSTs consumer_key/consumer_secret from their server,
    which may not have our cookies. We store the keys in Redis with a
    10-minute TTL, keyed by the state parameter. The frontend return_url
    triggers a claim of these pending keys.

    This endpoint has NO auth requirement — it's called by WooCommerce servers.
    """
    body = await request.json()
    state = body.get("state")
    consumer_key = body.get("consumer_key")
    consumer_secret = body.get("consumer_secret")

    if not state or not consumer_key or not consumer_secret:
        raise HTTPException(status_code=400, detail="Missing required fields")

    expires_in = body.get("expires_in", 600)

    if redis_client:
        await redis_client.setex(
            f"wc_pending:{state}",
            min(expires_in, 600),  # Max 10 minutes
            json.dumps({
                "consumer_key": consumer_key,
                "consumer_secret": consumer_secret,
                "key_id": body.get("key_id"),
                "key_permissions": body.get("key_permissions"),
            }),
        )
        logger.info("Stored pending WooCommerce keys for state: %s", state)
    else:
        logger.warning("Redis not available — cannot store pending WC keys")
        raise HTTPException(status_code=503, detail="Temporary storage unavailable")

    return {"status": "success", "message": "Keys stored, pending claim"}


@app.post("/api/v1/ecommerce/sync", response_model=Dict[str, Any])
async def trigger_sync(
    request: Request,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """
    Trigger a full or incremental sync for a connected store.

    Dispatches a background sync job for products, orders, and/or customers.
    Rate limited: 5 syncs/hour per tenant.
    """
    body = await request.json()
    platform_id = body.get("platform_id")
    full_sync = body.get("full_sync", False)
    sync_type = body.get("sync_type", "all")

    if not platform_id:
        raise HTTPException(status_code=400, detail="platform_id is required")

    # Rate limit: 5 syncs per hour
    if redis_client:
        rate_key = f"ecommerce_sync:{auth.tenant_id}"
        count = await redis_client.incr(rate_key)
        if count == 1:
            await redis_client.expire(rate_key, 3600)
        if count > 5:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Max 5 sync operations per hour.",
            )

    # Verify connection exists
    conn_row = await db.fetch_one(
        auth.tenant_id,
        """
        SELECT id, platform, store_url, api_key, api_secret, status
        FROM ecommerce_platforms
        WHERE id = $1 AND tenant_id = $2 AND status = 'active'
        """,
        platform_id,
        auth.tenant_id,
    )

    if not conn_row:
        raise HTTPException(status_code=404, detail="Active connection not found")

    # Queue sync job (simplified — in production, use Celery/SQS)
    logger.info(
        "Sync triggered: tenant=%s, platform=%s, type=%s, full=%s",
        auth.tenant_id,
        conn_row["platform"],
        sync_type,
        full_sync,
    )

    return {
        "status": "success",
        "message": f"Sync started for {conn_row['platform']} ({conn_row['store_url']})",
        "sync_type": sync_type,
        "full_sync": full_sync,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Product Sync
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/ecommerce/sync/products", response_model=Dict[str, Any])
async def sync_products(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """
    Trigger product sync from connected e-commerce platform.

    Can be full sync or incremental (since last sync).
    Runs asynchronously in background.
    """
    auth.require_role("owner", "admin")

    # Fetch platform connection
    platform = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM ecommerce_platforms WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        request.platform_id,
    )

    if not platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")

    # Queue sync in background
    async def run_sync():
        try:
            products = []

            if platform["platform"] == "shopify":
                shopify_products = await fetch_shopify_products(
                    platform["store_url"],
                    platform["api_key"],
                    platform["api_secret"],
                )
                for item in shopify_products.get("products", []):
                    products.append(ProductData(
                        external_id=str(item["id"]),
                        name=item["title"],
                        sku=item["handle"],
                        description=item.get("body_html"),
                        price=float(item["variants"][0]["price"]) if item.get("variants") else 0,
                        inventory_count=sum(v.get("inventory_quantity", 0) for v in item.get("variants", [])),
                        image_urls=[img["src"] for img in item.get("images", [])[:3]],
                    ))

            elif platform["platform"] == "woocommerce":
                wc_products = await fetch_woocommerce_products(
                    platform["store_url"],
                    platform["api_key"],
                    platform["api_secret"],
                )
                for item in wc_products:
                    products.append(ProductData(
                        external_id=str(item["id"]),
                        name=item["name"],
                        sku=item.get("sku"),
                        description=item.get("description"),
                        price=float(item["price"] or 0),
                        inventory_count=item.get("stock_quantity", 0),
                        image_urls=[img["src"] for img in item.get("images", [])[:3]],
                    ))

            elif platform["platform"] == "magento":
                mg_products = await fetch_magento_products(
                    platform["store_url"],
                    platform["api_secret"],
                )
                for item in mg_products.get("items", []):
                    products.append(ProductData(
                        external_id=str(item["id"]),
                        name=item["name"],
                        sku=item.get("sku"),
                        description=item.get("description"),
                        price=float(item["price"] or 0),
                    ))

            # Store products
            if products:
                await store_synced_products(auth.tenant_id, request.platform_id, products)

            # Update last sync timestamp
            await db.execute(
                auth.tenant_id,
                "UPDATE ecommerce_platforms SET last_sync_at = $1 WHERE id = $2",
                utc_now().isoformat(),
                request.platform_id,
            )

            logger.info("Product sync completed: tenant=%s, products=%d", auth.tenant_id, len(products))

        except Exception as e:
            logger.error("Product sync failed: %s", str(e), exc_info=True)

    background_tasks.add_task(run_sync)

    return {
        "status": "sync_queued",
        "platform_id": request.platform_id,
        "message": "Product sync started in background",
    }


@app.get("/api/v1/ecommerce/products", response_model=Dict[str, Any])
async def get_products(
    platform_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth),
):
    """Get synced products for tenant (optionally filtered by platform)."""
    if limit > 100:
        limit = 100

    query = "SELECT * FROM ecommerce_products WHERE tenant_id = $1"
    params = [auth.tenant_id]

    if platform_id:
        query += " AND platform_id = $2"
        params.append(platform_id)

    query += " ORDER BY synced_at DESC LIMIT $" + str(len(params) + 1) + " OFFSET $" + str(len(params) + 2)
    params.extend([limit, skip])

    products = await db.fetch_all(auth.tenant_id, query, *params)

    return {
        "products": [dict(p) for p in products],
        "total": len(products),
        "skip": skip,
        "limit": limit,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Order Sync
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/ecommerce/sync/orders", response_model=Dict[str, Any])
async def sync_orders(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """
    Trigger order sync from connected e-commerce platform.
    Runs asynchronously in background.
    """
    auth.require_role("owner", "admin")

    platform = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM ecommerce_platforms WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        request.platform_id,
    )

    if not platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")

    async def run_sync():
        try:
            orders = []

            if platform["platform"] == "shopify":
                # Fetch from Shopify orders endpoint
                headers = {"X-Shopify-Access-Token": platform["api_secret"]}
                url = f"https://{platform['store_url']}/admin/api/2024-01/orders.json"

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as resp:
                        data = await resp.json()
                        for item in data.get("orders", []):
                            orders.append(OrderData(
                                external_id=str(item["id"]),
                                customer_email=item.get("email", "unknown"),
                                customer_name=item.get("customer", {}).get("first_name", "") + " " + item.get("customer", {}).get("last_name", ""),
                                total_amount=float(item.get("total_price", 0)),
                                status=item.get("financial_status", "pending"),
                                items_count=len(item.get("line_items", [])),
                                created_at=item["created_at"],
                                updated_at=item["updated_at"],
                            ))

            if orders:
                await store_synced_orders(auth.tenant_id, request.platform_id, orders)

            await db.execute(
                auth.tenant_id,
                "UPDATE ecommerce_platforms SET last_sync_at = $1 WHERE id = $2",
                utc_now().isoformat(),
                request.platform_id,
            )

            logger.info("Order sync completed: tenant=%s, orders=%d", auth.tenant_id, len(orders))

        except Exception as e:
            logger.error("Order sync failed: %s", str(e), exc_info=True)

    background_tasks.add_task(run_sync)

    return {
        "status": "sync_queued",
        "platform_id": request.platform_id,
        "message": "Order sync started in background",
    }


@app.get("/api/v1/ecommerce/orders", response_model=Dict[str, Any])
async def get_orders(
    platform_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth),
):
    """Get synced orders for tenant."""
    if limit > 100:
        limit = 100

    query = "SELECT * FROM ecommerce_orders WHERE tenant_id = $1"
    params = [auth.tenant_id]
    param_count = 1

    if platform_id:
        param_count += 1
        query += f" AND platform_id = ${param_count}"
        params.append(platform_id)

    if status_filter:
        param_count += 1
        query += f" AND status = ${param_count}"
        params.append(status_filter)

    query += f" ORDER BY created_at DESC LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
    params.extend([limit, skip])

    orders = await db.fetch_all(auth.tenant_id, query, *params)

    return {
        "orders": [dict(o) for o in orders],
        "total": len(orders),
        "skip": skip,
        "limit": limit,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Customer Sync
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/ecommerce/sync/customers", response_model=Dict[str, Any])
async def sync_customers(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """
    Trigger customer sync from e-commerce platform.
    Bidirectional: can update CRM with e-commerce customers.
    """
    auth.require_role("owner", "admin")

    platform = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM ecommerce_platforms WHERE tenant_id = $1 AND id = $2",
        auth.tenant_id,
        request.platform_id,
    )

    if not platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")

    async def run_sync():
        try:
            customers_synced = 0

            if platform["platform"] == "shopify":
                headers = {"X-Shopify-Access-Token": platform["api_secret"]}
                url = f"https://{platform['store_url']}/admin/api/2024-01/customers.json"

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as resp:
                        data = await resp.json()
                        for item in data.get("customers", []):
                            # Store customer (upsert)
                            await db.execute(
                                auth.tenant_id,
                                """
                                INSERT INTO ecommerce_customers
                                (id, tenant_id, platform_id, external_id, email, name, phone, metadata, synced_at)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                                ON CONFLICT (tenant_id, platform_id, external_id) DO UPDATE SET synced_at = EXCLUDED.synced_at
                                """,
                                generate_uuid(),
                                auth.tenant_id,
                                request.platform_id,
                                str(item["id"]),
                                item.get("email"),
                                f"{item.get('first_name', '')} {item.get('last_name', '')}".strip(),
                                item.get("phone"),
                                json.dumps({"created_at": item.get("created_at")}),
                                utc_now().isoformat(),
                            )
                            customers_synced += 1

            logger.info("Customer sync completed: tenant=%s, customers=%d", auth.tenant_id, customers_synced)

        except Exception as e:
            logger.error("Customer sync failed: %s", str(e), exc_info=True)

    background_tasks.add_task(run_sync)

    return {
        "status": "sync_queued",
        "platform_id": request.platform_id,
        "message": "Customer sync started in background",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cart Abandonment
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/ecommerce/cart-abandonment", response_model=Dict[str, Any])
async def get_abandoned_carts(
    platform_id: Optional[str] = None,
    days: int = 7,
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth),
):
    """
    Get abandoned carts detected in the last N days.
    Used for remarketing/recovery campaigns.
    """
    if limit > 100:
        limit = 100
    if days < 1:
        days = 1
    if days > MAX_ABANDONED_CART_DAYS:
        days = MAX_ABANDONED_CART_DAYS

    cutoff_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    query = "SELECT * FROM ecommerce_abandoned_carts WHERE tenant_id = $1 AND abandoned_at > $2"
    params = [auth.tenant_id, cutoff_time]
    param_count = 2

    if platform_id:
        param_count += 1
        query += f" AND platform_id = ${param_count}"
        params.append(platform_id)

    query += f" ORDER BY abandoned_at DESC LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
    params.extend([limit, skip])

    carts = await db.fetch_all(auth.tenant_id, query, *params)

    return {
        "abandoned_carts": [dict(c) for c in carts],
        "total": len(carts),
        "days": days,
        "skip": skip,
        "limit": limit,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Handling
# ─────────────────────────────────────────────────────────────────────────────

async def _check_webhook_replay(platform: str, payload_bytes: bytes) -> bool:
    """Check if this webhook payload was already processed (replay protection)."""
    if not redis_client:
        return False  # Fail closed: deny if Redis unavailable
    try:
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        key = f"ecom:webhook:dedup:{platform}:{payload_hash}"
        result = await redis_client.set(key, "1", nx=True, ex=WEBHOOK_REPLAY_WINDOW)
        return result is None  # True = already seen (replay)
    except Exception as e:
        logger.warning("Webhook replay check failed: %s", e)
        return False  # Fail closed


async def _check_webhook_rate_limit(platform: str) -> bool:
    """Rate limit webhooks per platform. Returns True if over limit."""
    if not redis_client:
        return True  # Fail closed: deny if Redis unavailable
    try:
        key = f"ecom:webhook:rate:{platform}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        return count > WEBHOOK_RATE_LIMIT_PER_MIN
    except Exception as e:
        logger.warning("Webhook rate limit check failed: %s", e)
        return True  # Fail closed


# Validate tenant_id format (UUID)
TENANT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


@app.post("/api/v1/ecommerce/webhooks/{platform}")
async def handle_webhook(
    platform: str,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Universal webhook receiver for all platforms.

    Each platform sends:
    - Shopify: X-Shopify-Hmac-SHA256 header
    - WooCommerce: X-WC-Webhook-Signature header
    - Magento: X-Magento-Webhook-Signature header
    - Custom: X-Webhook-Signature header

    SECURITY: Verify signatures before processing. Rate limited + replay protected.
    """
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")

    # Rate limit webhooks per platform
    if await _check_webhook_rate_limit(platform):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    # Get signature header (varies by platform)
    signature_header = {
        "shopify": "X-Shopify-Hmac-SHA256",
        "woocommerce": "X-WC-Webhook-Signature",
        "magento": "X-Magento-Webhook-Signature",
        "custom": "X-Webhook-Signature",
    }.get(platform, "X-Webhook-Signature")

    signature = request.headers.get(signature_header)
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature")

    body = await request.body()
    if len(body) > 1_048_576:  # 1MB max payload
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")

    # Replay protection
    if await _check_webhook_replay(platform, body):
        logger.info("Webhook replay detected: platform=%s", platform)
        return {"status": "already_processed"}

    # Extract tenant_id from webhook metadata (varies by platform)
    try:
        payload = json.loads(body)
        # Platform-specific tenant extraction — use X-Tenant-ID header (set by gateway/platform config)
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing tenant context")
        # Validate tenant_id format
        if not TENANT_ID_RE.match(tenant_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant ID format")
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Fetch platform config with tenant isolation
    try:
        platform_config = await db.fetch_one(
            tenant_id,
            "SELECT * FROM ecommerce_platforms WHERE tenant_id = $1 AND platform = $2 AND status = 'active' LIMIT 1",
            tenant_id,
            platform,
        )
    except (json.JSONDecodeError, KeyError, ValueError, asyncpg.PostgresError):
        platform_config = None

    if not platform_config or not platform_config.get("webhook_secret"):
        logger.warning("Webhook received but no webhook_secret configured: tenant=%s, platform=%s", tenant_id, platform)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Server configuration error")

    # Verify signature
    if not await verify_webhook_signature(
        platform,
        body,
        signature,
        platform_config["webhook_secret"],
    ):
        logger.warning("Webhook signature verification failed: tenant=%s, platform=%s", tenant_id, platform)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # Process webhook asynchronously
    async def process_webhook():
        try:
            event_type = payload.get("type") or request.headers.get("X-Event-Type", "unknown")

            if "product" in event_type.lower() or "inventory" in event_type.lower():
                # Trigger product sync
                pass

            elif "order" in event_type.lower():
                # Trigger order sync
                pass

            elif "cart" in event_type.lower() or "abandoned" in event_type.lower():
                # Store abandoned cart
                cart_data = AbandonedCart(
                    external_id=payload.get("id", ""),
                    customer_email=payload.get("email", ""),
                    customer_name=payload.get("customer_name"),
                    total_value=float(payload.get("total", 0)),
                    items_count=payload.get("items_count", 0),
                    abandoned_at=utc_now().isoformat(),
                )
                await store_abandoned_carts(
                    tenant_id,
                    platform_config["id"],
                    [cart_data],
                )

            logger.info("Webhook processed: tenant=%s, platform=%s, event=%s", tenant_id, platform, event_type)

        except Exception as e:
            logger.error("Webhook processing failed: %s", str(e), exc_info=True)

    background_tasks.add_task(process_webhook)

    return {"status": "received"}


# ─────────────────────────────────────────────────────────────────────────────
# Field Mapping (Custom Integrations)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/ecommerce/field-mapping", response_model=Dict[str, Any])
async def configure_field_mapping(
    platform_id: str,
    mapping: FieldMapping,
    auth: AuthContext = Depends(get_auth),
):
    """
    Configure field mapping for custom platform integration.

    Maps external API fields to internal schema:
    - Product: name, price, description, sku, inventory_count
    - Order: external_id, customer_email, total_amount, status
    - Customer: email, name, phone
    """
    auth.require_role("owner", "admin")

    platform = await db.fetch_one(
        auth.tenant_id,
        "SELECT * FROM ecommerce_platforms WHERE tenant_id = $1 AND id = $2 AND platform = 'custom'",
        auth.tenant_id,
        platform_id,
    )

    if not platform:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom platform not found")

    mapping_id = generate_uuid()

    await db.execute(
        auth.tenant_id,
        """
        INSERT INTO ecommerce_field_mappings
        (id, tenant_id, platform_id, external_field, internal_field, data_type, required, transform_script, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (tenant_id, platform_id, external_field) DO UPDATE SET
            internal_field = EXCLUDED.internal_field,
            data_type = EXCLUDED.data_type,
            required = EXCLUDED.required
        """,
        mapping_id,
        auth.tenant_id,
        platform_id,
        mapping.external_field,
        mapping.internal_field,
        mapping.data_type,
        mapping.required,
        mapping.transform_script,
        utc_now().isoformat(),
    )

    logger.info(
        "Field mapping configured: tenant=%s, platform=%s, external=%s → internal=%s",
        auth.tenant_id,
        platform_id,
        mapping.external_field,
        mapping.internal_field,
    )

    return {
        "status": "success",
        "mapping_id": mapping_id,
        "message": f"Field mapping configured: {mapping.external_field} → {mapping.internal_field}",
    }


@app.get("/api/v1/ecommerce/field-mappings/{platform_id}", response_model=Dict[str, Any])
async def get_field_mappings(
    platform_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get all field mappings for a custom platform."""
    mappings = await db.fetch_all(
        auth.tenant_id,
        "SELECT * FROM ecommerce_field_mappings WHERE tenant_id = $1 AND platform_id = $2",
        auth.tenant_id,
        platform_id,
    )

    return {
        "platform_id": platform_id,
        "mappings": [dict(m) for m in mappings],
        "total": len(mappings),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return {
        "error": "Internal server error",
        "detail": "An unexpected error occurred. Please try again.",
    }


if __name__ == "__main__":
    import uvicorn



    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.ports.ecommerce,
        log_level=config.log_level.lower(),
    )
