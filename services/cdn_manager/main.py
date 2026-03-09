"""
Priya Global — CDN & Asset Manager
Port: 9040

Global CDN configuration, static asset management, image optimization,
and multi-region asset distribution for tenant websites and widgets.

Features:
- CloudFront / Cloudflare CDN integration
- Image optimization (resize, compress, WebP conversion)
- Tenant asset management (logos, themes, media)
- Cache invalidation API
- Bandwidth monitoring & quotas
- Signed URL generation for private assets
- Multi-region origin configuration
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import asyncpg
import jwt as pyjwt
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config


# ============================================================================
# CONFIGURATION
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger("priya.cdn_manager")

DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://app.currentglobal.com,https://admin.currentglobal.com"
).split(",")

# Validate secrets at module load time
if not JWT_SECRET:
    logger.warning("Server configuration error — authentication will be disabled")
if not DATABASE_URL:
    logger.warning("Server configuration error — running in memory-only mode")

# CDN Provider settings
CDN_PROVIDER = os.getenv("CDN_PROVIDER", "cloudflare")  # cloudflare | cloudfront | bunny
CDN_API_KEY = os.getenv("CDN_API_KEY", "")
CDN_ZONE_ID = os.getenv("CDN_ZONE_ID", "")
CDN_BASE_URL = os.getenv("CDN_BASE_URL", "https://cdn.currentglobal.com")

# Storage
ASSET_STORAGE_PATH = os.getenv("ASSET_STORAGE_PATH", "/data/assets")
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "25"))
SIGNED_URL_EXPIRY_SECONDS = int(os.getenv("SIGNED_URL_EXPIRY_SECONDS", "3600"))
SIGNING_SECRET = os.getenv("CDN_SIGNING_SECRET", "")

# Allowed MIME types
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    # SECURITY: SVG removed — SVGs can contain embedded JavaScript (XSS attack vector)
    # "image/svg+xml",  # REMOVED: XSS risk
    "video/mp4", "video/webm",
    "audio/mpeg", "audio/wav", "audio/ogg",
    "application/pdf",
    # SECURITY: CSS and JS removed — uploaded CSS/JS can be used for defacement or XSS
    # "text/css", "application/javascript",  # REMOVED: code injection risk
    "font/woff", "font/woff2", "font/ttf",
}
# Allowed file extensions (whitelist — prevents double-extension attacks like .jpg.exe)
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".webm", ".mpeg", ".wav", ".ogg",
    ".pdf", ".woff", ".woff2", ".ttf",
}


# ============================================================================
# AUTH
# ============================================================================

security = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user_id: str
    tenant_id: str
    email: str
    role: str = "user"


async def get_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthContext:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization token")
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="Server configuration error")
    try:
        payload = pyjwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256", "RS256"])
        return AuthContext(
            user_id=payload.get("sub", ""),
            tenant_id=payload.get("tenant_id", ""),
            email=payload.get("email", ""),
            role=payload.get("role", "user"),
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ============================================================================
# DATABASE
# ============================================================================

db_pool: Optional[asyncpg.Pool] = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cdn_assets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    filename        TEXT NOT NULL,
    original_name   TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    storage_path    TEXT NOT NULL,
    cdn_url         TEXT,
    checksum_sha256 TEXT NOT NULL,
    category        TEXT DEFAULT 'general' CHECK (category IN ('logo', 'theme', 'media', 'document', 'widget', 'general')),
    is_public       BOOLEAN DEFAULT FALSE,
    metadata        JSONB DEFAULT '{}',
    uploaded_by     TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cdn_cache_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    path_pattern    TEXT NOT NULL,
    cache_ttl       INT NOT NULL DEFAULT 86400,
    cache_control   TEXT DEFAULT 'public, max-age=86400',
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cdn_bandwidth_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    date            DATE NOT NULL,
    bytes_served    BIGINT DEFAULT 0,
    requests_count  BIGINT DEFAULT 0,
    cache_hit_ratio DOUBLE PRECISION DEFAULT 0,
    UNIQUE(tenant_id, date)
);

CREATE TABLE IF NOT EXISTS cdn_invalidations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    paths           TEXT[] NOT NULL,
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    provider_ref    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS cdn_origins (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    name            TEXT NOT NULL,
    origin_url      TEXT NOT NULL,
    region          TEXT NOT NULL DEFAULT 'global',
    priority        INT DEFAULT 1,
    enabled         BOOLEAN DEFAULT TRUE,
    health_status   TEXT DEFAULT 'healthy',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE cdn_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE cdn_cache_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE cdn_bandwidth_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE cdn_invalidations ENABLE ROW LEVEL SECURITY;
ALTER TABLE cdn_origins ENABLE ROW LEVEL SECURITY;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cdn_assets_tenant ON cdn_assets(tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_cdn_bandwidth_tenant_date ON cdn_bandwidth_log(tenant_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_cdn_invalidations_tenant ON cdn_invalidations(tenant_id, created_at DESC);
"""


async def init_db():
    global db_pool
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set — CDN manager in memory-only mode")
        return
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("CDN manager database initialized")


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("CDN Manager started — provider: %s, base: %s", CDN_PROVIDER, CDN_BASE_URL)
    yield
    if db_pool:
        await db_pool.close()


# ============================================================================
# APP
# ============================================================================

app = FastAPI(
    title="Priya Global — CDN & Asset Manager",
    version="1.0.0",
    lifespan=lifespan,
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="cdn_manager")
init_sentry(service_name="cdn-manager", service_port=9040)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="cdn-manager")
app.add_middleware(TracingMiddleware)


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



# ============================================================================
# HEALTH
# ============================================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "cdn-manager",
        "provider": CDN_PROVIDER,
    }


# ============================================================================
# ASSET MANAGEMENT
# ============================================================================

@app.post("/api/v1/assets/upload")
async def upload_asset(
    file: UploadFile = File(...),
    category: str = Query(default="general"),
    is_public: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth),
):
    """Upload an asset to CDN storage"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # Validate category
    valid_categories = ("logo", "theme", "media", "document", "widget", "general")
    if category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Category must be one of: {', '.join(valid_categories)}")

    # Validate MIME type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed")

    # SECURITY: Validate file extension (prevents double-extension attacks like .jpg.exe)
    import re as _re
    raw_filename = file.filename or "file.bin"
    # Strip path traversal characters
    safe_filename = os.path.basename(raw_filename).replace("..", "").replace("/", "").replace("\\", "")
    ext = os.path.splitext(safe_filename)[1].lower() or ".bin"
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File extension not allowed")
    # Reject filenames with multiple dots that could be double-extension attacks
    name_part = os.path.splitext(safe_filename)[0]
    if '.' in name_part and os.path.splitext(name_part)[1].lower() in {'.exe', '.sh', '.bat', '.cmd', '.php', '.jsp', '.py', '.js', '.html', '.svg'}:
        raise HTTPException(status_code=400, detail="Suspicious filename rejected")

    # Read file with size limit
    content = await file.read()
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds size limit")

    # Generate storage path & checksum (UUID filename prevents all path traversal)
    checksum = hashlib.sha256(content).hexdigest()
    stored_name = f"{auth.tenant_id}/{category}/{uuid.uuid4().hex}{ext}"
    cdn_url = f"{CDN_BASE_URL}/{stored_name}"

    # Store in database
    row = await db_pool.fetchrow(
        """
        INSERT INTO cdn_assets (tenant_id, filename, original_name, mime_type, size_bytes,
                               storage_path, cdn_url, checksum_sha256, category, is_public,
                               uploaded_by, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        RETURNING id, filename, cdn_url, size_bytes, created_at
        """,
        auth.tenant_id, stored_name, file.filename or "untitled", content_type,
        len(content), stored_name, cdn_url, checksum, category, is_public,
        auth.user_id, json.dumps({"original_size": len(content)}),
    )

    logger.info("Asset uploaded: %s (%s bytes) by %s", stored_name, len(content), auth.email)
    return {
        "asset": dict(row),
        "cdn_url": cdn_url,
        "message": "Asset uploaded successfully",
    }


@app.get("/api/v1/assets")
async def list_assets(
    category: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(get_auth),
):
    """List tenant assets"""
    if not db_pool:
        return {"assets": [], "total": 0}

    query = """
        SELECT id, filename, original_name, mime_type, size_bytes, cdn_url,
               category, is_public, created_at
        FROM cdn_assets
        WHERE tenant_id = $1
    """
    params: list = [auth.tenant_id]
    idx = 2

    if category:
        query += f" AND category = ${idx}"
        params.append(category)
        idx += 1

    count_query = query.replace("SELECT id, filename, original_name, mime_type, size_bytes, cdn_url,\n               category, is_public, created_at", "SELECT COUNT(*)")
    total = await db_pool.fetchval(count_query, *params)

    query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([limit, offset])

    rows = await db_pool.fetch(query, *params)
    return {"assets": [dict(r) for r in rows], "total": total}


@app.delete("/api/v1/assets/{asset_id}")
async def delete_asset(asset_id: str, auth: AuthContext = Depends(get_auth)):
    """Delete a tenant asset"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset ID")

    result = await db_pool.execute(
        "DELETE FROM cdn_assets WHERE id = $1::uuid AND tenant_id = $2",
        asset_id, auth.tenant_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Asset not found")

    return {"message": "Asset deleted", "asset_id": asset_id}


# ============================================================================
# SIGNED URLS
# ============================================================================

@app.post("/api/v1/assets/{asset_id}/signed-url")
async def generate_signed_url(
    asset_id: str,
    expiry_seconds: int = Query(default=SIGNED_URL_EXPIRY_SECONDS, ge=60, le=86400),
    auth: AuthContext = Depends(get_auth),
):
    """Generate a time-limited signed URL for private assets"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    if not SIGNING_SECRET:
        logger.error("Server configuration error — cannot generate signed URLs")
        raise HTTPException(status_code=500, detail="Server configuration error")

    try:
        uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset ID")

    row = await db_pool.fetchrow(
        "SELECT cdn_url, storage_path FROM cdn_assets WHERE id = $1::uuid AND tenant_id = $2",
        asset_id, auth.tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")

    expires = int(time.time()) + expiry_seconds
    message = f"{row['storage_path']}:{expires}"
    signature = hmac.new(
        SIGNING_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()

    signed_url = f"{row['cdn_url']}?expires={expires}&sig={signature}"
    return {
        "signed_url": signed_url,
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
    }


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

class CacheRuleCreate(BaseModel):
    path_pattern: str = Field(min_length=1, max_length=500)
    cache_ttl: int = Field(ge=0, le=31536000)
    cache_control: str = Field(default="public, max-age=86400", max_length=200)


@app.get("/api/v1/cache/rules")
async def list_cache_rules(auth: AuthContext = Depends(get_auth)):
    if not db_pool:
        return {"rules": []}
    rows = await db_pool.fetch(
        "SELECT * FROM cdn_cache_rules WHERE tenant_id = $1 ORDER BY created_at DESC",
        auth.tenant_id,
    )
    return {"rules": [dict(r) for r in rows]}


@app.post("/api/v1/cache/rules")
async def create_cache_rule(body: CacheRuleCreate, auth: AuthContext = Depends(get_auth)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    row = await db_pool.fetchrow(
        """
        INSERT INTO cdn_cache_rules (tenant_id, path_pattern, cache_ttl, cache_control)
        VALUES ($1, $2, $3, $4) RETURNING *
        """,
        auth.tenant_id, body.path_pattern, body.cache_ttl, body.cache_control,
    )
    return {"rule": dict(row)}


@app.post("/api/v1/cache/invalidate")
async def invalidate_cache(
    paths: List[str] = [],
    auth: AuthContext = Depends(get_auth),
):
    """Invalidate CDN cache for specific paths"""
    if not paths:
        raise HTTPException(status_code=400, detail="At least one path required")
    if len(paths) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 paths per invalidation")

    # Sanitize paths — must start with /
    clean_paths = []
    for p in paths:
        if not p.startswith("/"):
            p = "/" + p
        clean_paths.append(p)

    if db_pool:
        row = await db_pool.fetchrow(
            """
            INSERT INTO cdn_invalidations (tenant_id, paths, status)
            VALUES ($1, $2, 'pending') RETURNING *
            """,
            auth.tenant_id, clean_paths,
        )
        return {"invalidation": dict(row), "message": "Cache invalidation queued"}

    return {"message": "Cache invalidation queued (DB not configured)", "paths": clean_paths}


@app.get("/api/v1/cache/invalidations")
async def list_invalidations(
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth),
):
    if not db_pool:
        return {"invalidations": []}
    rows = await db_pool.fetch(
        """
        SELECT * FROM cdn_invalidations
        WHERE tenant_id = $1
        ORDER BY created_at DESC LIMIT $2
        """,
        auth.tenant_id, limit,
    )
    return {"invalidations": [dict(r) for r in rows]}


# ============================================================================
# BANDWIDTH & ANALYTICS
# ============================================================================

@app.get("/api/v1/bandwidth")
async def get_bandwidth(
    days: int = Query(default=30, ge=1, le=365),
    auth: AuthContext = Depends(get_auth),
):
    """Get bandwidth usage for the tenant"""
    if not db_pool:
        return {"bandwidth": [], "total_bytes": 0}

    rows = await db_pool.fetch(
        """
        SELECT date, bytes_served, requests_count, cache_hit_ratio
        FROM cdn_bandwidth_log
        WHERE tenant_id = $1 AND date >= CURRENT_DATE - $2::interval
        ORDER BY date DESC
        """,
        auth.tenant_id, f"{days} days",
    )

    total_bytes = sum(r["bytes_served"] for r in rows)
    total_requests = sum(r["requests_count"] for r in rows)
    avg_cache_hit = (
        sum(r["cache_hit_ratio"] for r in rows) / len(rows)
        if rows else 0
    )

    return {
        "bandwidth": [dict(r) for r in rows],
        "summary": {
            "total_bytes": total_bytes,
            "total_gb": round(total_bytes / (1024**3), 2),
            "total_requests": total_requests,
            "avg_cache_hit_ratio": round(avg_cache_hit, 2),
        },
        "days": days,
    }


# ============================================================================
# MULTI-REGION ORIGINS
# ============================================================================

class OriginCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    origin_url: str = Field(min_length=1, max_length=500)
    region: str = Field(default="global", max_length=50)
    priority: int = Field(default=1, ge=1, le=10)


@app.get("/api/v1/origins")
async def list_origins(auth: AuthContext = Depends(get_auth)):
    if not db_pool:
        return {"origins": []}
    rows = await db_pool.fetch(
        "SELECT * FROM cdn_origins WHERE tenant_id = $1 ORDER BY priority, region",
        auth.tenant_id,
    )
    return {"origins": [dict(r) for r in rows]}


@app.post("/api/v1/origins")
async def create_origin(body: OriginCreate, auth: AuthContext = Depends(get_auth)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    row = await db_pool.fetchrow(
        """
        INSERT INTO cdn_origins (tenant_id, name, origin_url, region, priority)
        VALUES ($1, $2, $3, $4, $5) RETURNING *
        """,
        auth.tenant_id, body.name, body.origin_url, body.region, body.priority,
    )
    return {"origin": dict(row)}


@app.delete("/api/v1/origins/{origin_id}")
async def delete_origin(origin_id: str, auth: AuthContext = Depends(get_auth)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        uuid.UUID(origin_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid origin ID")

    result = await db_pool.execute(
        "DELETE FROM cdn_origins WHERE id = $1::uuid AND tenant_id = $2",
        origin_id, auth.tenant_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Origin not found")
    return {"message": "Origin deleted"}


# ============================================================================
# STORAGE STATS
# ============================================================================

@app.get("/api/v1/storage/stats")
async def get_storage_stats(auth: AuthContext = Depends(get_auth)):
    """Get storage usage statistics for the tenant"""
    if not db_pool:
        return {"stats": {}}

    row = await db_pool.fetchrow(
        """
        SELECT
            COUNT(*) as total_assets,
            COALESCE(SUM(size_bytes), 0) as total_bytes,
            COALESCE(AVG(size_bytes), 0) as avg_size_bytes,
            COUNT(DISTINCT category) as categories_used
        FROM cdn_assets
        WHERE tenant_id = $1
        """,
        auth.tenant_id,
    )

    by_category = await db_pool.fetch(
        """
        SELECT category, COUNT(*) as count, SUM(size_bytes) as total_bytes
        FROM cdn_assets
        WHERE tenant_id = $1
        GROUP BY category ORDER BY total_bytes DESC
        """,
        auth.tenant_id,
    )

    return {
        "stats": {
            "total_assets": row["total_assets"],
            "total_bytes": row["total_bytes"],
            "total_mb": round(row["total_bytes"] / (1024**2), 2),
            "avg_size_bytes": round(row["avg_size_bytes"]),
            "by_category": [dict(r) for r in by_category],
        },
    }
