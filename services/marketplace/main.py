"""
Marketplace & App Store Service
Multi-tenant SaaS FastAPI application for app marketplace, developer portal, webhooks, and themes.
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

import jwt
import asyncpg
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config



# ============================================================================
# MODELS & ENUMS
# ============================================================================

class AppCategory(str, Enum):
    CRM = "crm"
    ANALYTICS = "analytics"
    PAYMENTS = "payments"
    COMMUNICATION = "communication"
    PRODUCTIVITY = "productivity"
    SECURITY = "security"
    INTEGRATION = "integration"


class PermissionScope(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class AppStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class WebhookType(str, Enum):
    ZAPIER = "zapier"
    MAKE = "make"
    N8N = "n8n"
    CUSTOM = "custom"


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class AuthContext(BaseModel):
    """JWT claims context"""
    sub: str  # user_id
    tenant_id: str
    email: str
    exp: int


class AppSearchRequest(BaseModel):
    query: Optional[str] = None
    category: Optional[AppCategory] = None
    limit: int = 20
    offset: int = 0


class AppInstallRequest(BaseModel):
    permissions: List[PermissionScope] = [PermissionScope.READ]
    oauth_redirect_uri: Optional[str] = None


class AppReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=10, max_length=500)


class DeveloperRegisterRequest(BaseModel):
    company_name: str
    description: str
    website: Optional[str] = None
    contact_email: str


class AppSubmitRequest(BaseModel):
    name: str
    description: str
    category: AppCategory
    icon_url: str
    documentation_url: Optional[str] = None
    oauth_client_id: Optional[str] = None
    permissions_required: List[PermissionScope] = [PermissionScope.READ]


class WebhookTemplateRequest(BaseModel):
    type: WebhookType
    name: str
    config: Dict[str, Any]


class WebhookTestRequest(BaseModel):
    url: str
    payload: Dict[str, Any]


class ThemeCustomizationRequest(BaseModel):
    name: str
    primary_color: str = "#000000"
    secondary_color: str = "#FFFFFF"
    font_family: str = "Segoe UI"
    border_radius: str = "8px"
    custom_css: Optional[str] = None


# Response models
class AppMarketplaceItem(BaseModel):
    id: str
    name: str
    description: str
    category: AppCategory
    icon_url: str
    developer_id: str
    developer_name: str
    version: str
    rating: float
    review_count: int
    installation_count: int
    status: AppStatus
    created_at: datetime


class AppDetailResponse(AppMarketplaceItem):
    documentation_url: Optional[str]
    screenshots: List[str]
    changelog: str


class AppInstallationResponse(BaseModel):
    installation_id: str
    app_id: str
    tenant_id: str
    status: str = "active"
    permissions: List[PermissionScope]
    oauth_token: Optional[str] = None
    installed_at: datetime


class DeveloperResponse(BaseModel):
    developer_id: str
    user_id: str
    company_name: str
    status: str
    created_at: datetime


class WebhookTemplateResponse(BaseModel):
    id: str
    type: WebhookType
    name: str
    description: str
    example_payload: Dict[str, Any]


class ThemeResponse(BaseModel):
    id: str
    name: str
    category: str
    thumbnail_url: str
    primary_color: str
    secondary_color: str
    font_family: str
    border_radius: str
    downloads: int


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    database: str
    version: str


# ============================================================================
# DATABASE INITIALIZATION & POOL
# ============================================================================

class DatabasePool:
    """Singleton database connection pool"""
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        """Initialize asyncpg connection pool"""
        if self._pool is None:
            db_host = os.getenv("DB_HOST")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME")
            db_user = os.getenv("DB_USER")
            db_password = os.getenv("DB_PASSWORD")

            if not all([db_host, db_name, db_user, db_password]):
                raise ValueError("Missing required database environment variables")

            self._pool = await asyncpg.create_pool(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                min_size=5,
                max_size=20,
                command_timeout=60,
            )
            await self._setup_schema()

    async def close(self):
        """Close the connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self):
        return self._pool

    async def execute(self, query: str, *args, **kwargs):
        """Execute a query"""
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        """Fetch multiple rows"""
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        """Fetch single row"""
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """Fetch single value"""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def _setup_schema(self):
        """Create necessary tables with RLS"""
        async with self._pool.acquire() as conn:
            # Enable RLS extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

            # Apps table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS apps (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    category VARCHAR(50) NOT NULL,
                    icon_url TEXT,
                    developer_id UUID NOT NULL,
                    version VARCHAR(50) DEFAULT '1.0.0',
                    status VARCHAR(50) DEFAULT 'draft',
                    documentation_url TEXT,
                    oauth_client_id VARCHAR(500),
                    rating DECIMAL(3,2) DEFAULT 0,
                    review_count INT DEFAULT 0,
                    installation_count INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tenant_id UUID NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_apps_tenant_id ON apps(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_apps_category ON apps(category);
                CREATE INDEX IF NOT EXISTS idx_apps_status ON apps(status);
            """)

            # App installations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS app_installations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    app_id UUID NOT NULL REFERENCES apps(id),
                    tenant_id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    permissions VARCHAR(500) DEFAULT 'read',
                    oauth_token TEXT,
                    status VARCHAR(50) DEFAULT 'active',
                    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_installations_tenant ON app_installations(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_installations_app ON app_installations(app_id);
            """)

            # Reviews table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS app_reviews (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    app_id UUID NOT NULL REFERENCES apps(id),
                    tenant_id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_reviews_tenant ON app_reviews(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_app ON app_reviews(app_id);
            """)

            # Developers table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS developers (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL,
                    tenant_id UUID NOT NULL,
                    company_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    website VARCHAR(500),
                    contact_email VARCHAR(255),
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_developers_tenant ON developers(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_developers_user ON developers(user_id);
            """)

            # Webhooks table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    user_id UUID NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    name VARCHAR(255),
                    url VARCHAR(2000),
                    config JSONB,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_webhooks_tenant ON webhooks(tenant_id);
            """)

            # Webhook templates table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS webhook_templates (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    type VARCHAR(50) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    example_payload JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Themes table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS themes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name VARCHAR(255) NOT NULL,
                    category VARCHAR(100),
                    thumbnail_url TEXT,
                    primary_color VARCHAR(7) DEFAULT '#000000',
                    secondary_color VARCHAR(7) DEFAULT '#FFFFFF',
                    font_family VARCHAR(100) DEFAULT 'Segoe UI',
                    border_radius VARCHAR(50) DEFAULT '8px',
                    custom_css TEXT,
                    downloads INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)


db_pool = DatabasePool()


# ============================================================================
# AUTHENTICATION & AUTHORIZATION
# ============================================================================

security = HTTPBearer()


async def get_auth_context(credentials: HTTPAuthCredentials = Depends(security)) -> AuthContext:
    """Verify JWT token and extract auth context"""
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error"
        )

    try:
        payload = jwt.decode(credentials.credentials, jwt_secret, algorithms=["HS256"])
        context = AuthContext(
            sub=payload.get("sub"),
            tenant_id=payload.get("tenant_id"),
            email=payload.get("email"),
            exp=payload.get("exp"),
        )
        if not all([context.sub, context.tenant_id, context.email]):
            raise ValueError("Missing required JWT claims")
        return context
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ============================================================================
# APP OPERATIONS
# ============================================================================

async def get_app_by_id(app_id: str, tenant_id: str) -> Dict[str, Any]:
    """Fetch app with RLS enforcement"""
    row = await db_pool.fetchrow(
        """
        SELECT id, name, description, category, icon_url, developer_id, version,
               status, documentation_url, rating, review_count, installation_count,
               created_at
        FROM apps
        WHERE id = $1 AND (status = 'approved' OR tenant_id = $2)
        """,
        uuid.UUID(app_id), uuid.UUID(tenant_id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="App not found")
    return dict(row)


async def search_apps(query: Optional[str], category: Optional[str], limit: int, offset: int, tenant_id: str) -> List[Dict[str, Any]]:
    """Search marketplace apps"""
    sql = """
        SELECT id, name, description, category, icon_url, developer_id, version,
               status, rating, review_count, installation_count, created_at
        FROM apps
        WHERE status = 'approved'
    """
    params = []

    if query:
        sql += " AND (name ILIKE $1 OR description ILIKE $1)"
        params.append(f"%{query}%")

    if category:
        sql += f" AND category = ${len(params) + 1}"
        params.append(category)

    sql += f" ORDER BY rating DESC, installation_count DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
    params.extend([limit, offset])

    rows = await db_pool.fetch(sql, *params)
    return [dict(row) for row in rows]


async def install_app(app_id: str, tenant_id: str, user_id: str, permissions: List[PermissionScope]) -> str:
    """Install app for tenant"""
    app = await get_app_by_id(app_id, tenant_id)

    # Check if already installed
    existing = await db_pool.fetchrow(
        "SELECT id FROM app_installations WHERE app_id = $1 AND tenant_id = $2",
        uuid.UUID(app_id), uuid.UUID(tenant_id)
    )
    if existing:
        raise HTTPException(status_code=400, detail="App already installed for this tenant")

    installation_id = str(uuid.uuid4())
    await db_pool.execute(
        """
        INSERT INTO app_installations (id, app_id, tenant_id, user_id, permissions, status)
        VALUES ($1, $2, $3, $4, $5, 'active')
        """,
        uuid.UUID(installation_id), uuid.UUID(app_id), uuid.UUID(tenant_id),
        uuid.UUID(user_id), ",".join([p.value for p in permissions])
    )

    # Update installation count
    await db_pool.execute(
        "UPDATE apps SET installation_count = installation_count + 1 WHERE id = $1",
        uuid.UUID(app_id)
    )

    return installation_id


async def uninstall_app(app_id: str, tenant_id: str) -> bool:
    """Uninstall app for tenant"""
    result = await db_pool.execute(
        "DELETE FROM app_installations WHERE app_id = $1 AND tenant_id = $2",
        uuid.UUID(app_id), uuid.UUID(tenant_id)
    )

    # Update installation count
    await db_pool.execute(
        "UPDATE apps SET installation_count = GREATEST(installation_count - 1, 0) WHERE id = $1",
        uuid.UUID(app_id)
    )

    return True


async def submit_review(app_id: str, tenant_id: str, user_id: str, rating: int, comment: str):
    """Submit app review"""
    # Check existing review
    existing = await db_pool.fetchrow(
        "SELECT id FROM app_reviews WHERE app_id = $1 AND user_id = $2",
        uuid.UUID(app_id), uuid.UUID(user_id)
    )

    review_id = str(uuid.uuid4())
    if existing:
        # Update existing
        await db_pool.execute(
            "UPDATE app_reviews SET rating = $1, comment = $2 WHERE app_id = $3 AND user_id = $4",
            rating, comment, uuid.UUID(app_id), uuid.UUID(user_id)
        )
    else:
        # Insert new
        await db_pool.execute(
            """
            INSERT INTO app_reviews (id, app_id, tenant_id, user_id, rating, comment)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            uuid.UUID(review_id), uuid.UUID(app_id), uuid.UUID(tenant_id),
            uuid.UUID(user_id), rating, comment
        )

    # Update app rating
    avg_rating = await db_pool.fetchval(
        "SELECT COALESCE(AVG(rating), 0) FROM app_reviews WHERE app_id = $1",
        uuid.UUID(app_id)
    )
    review_count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM app_reviews WHERE app_id = $1",
        uuid.UUID(app_id)
    )

    await db_pool.execute(
        "UPDATE apps SET rating = $1, review_count = $2 WHERE id = $3",
        float(avg_rating), review_count, uuid.UUID(app_id)
    )


# ============================================================================
# DEVELOPER OPERATIONS
# ============================================================================

async def register_developer(user_id: str, tenant_id: str, req: DeveloperRegisterRequest) -> str:
    """Register user as developer"""
    developer_id = str(uuid.uuid4())
    await db_pool.execute(
        """
        INSERT INTO developers (id, user_id, tenant_id, company_name, description, website, contact_email, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
        """,
        uuid.UUID(developer_id), uuid.UUID(user_id), uuid.UUID(tenant_id),
        req.company_name, req.description, req.website, req.contact_email
    )
    return developer_id


async def submit_app(developer_id: str, tenant_id: str, req: AppSubmitRequest) -> str:
    """Submit app for review"""
    app_id = str(uuid.uuid4())
    await db_pool.execute(
        """
        INSERT INTO apps (id, name, description, category, icon_url, developer_id, 
                         documentation_url, oauth_client_id, status, tenant_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending_review', $9)
        """,
        uuid.UUID(app_id), req.name, req.description, req.category.value, req.icon_url,
        uuid.UUID(developer_id), req.documentation_url, req.oauth_client_id, uuid.UUID(tenant_id)
    )
    return app_id


async def get_developer_apps(developer_id: str, tenant_id: str) -> List[Dict[str, Any]]:
    """Get developer's apps"""
    rows = await db_pool.fetch(
        """
        SELECT id, name, description, category, icon_url, version, status,
               rating, review_count, installation_count, created_at
        FROM apps
        WHERE developer_id = $1 AND tenant_id = $2
        ORDER BY created_at DESC
        """,
        uuid.UUID(developer_id), uuid.UUID(tenant_id)
    )
    return [dict(row) for row in rows]


# ============================================================================
# WEBHOOK OPERATIONS
# ============================================================================

async def get_webhook_templates() -> List[Dict[str, Any]]:
    """Get pre-built webhook templates"""
    rows = await db_pool.fetch(
        """
        SELECT id, type, name, description, example_payload
        FROM webhook_templates
        ORDER BY type, name
        """
    )
    return [dict(row) for row in rows]


async def create_webhook(tenant_id: str, user_id: str, req: WebhookTemplateRequest) -> str:
    """Create custom webhook"""
    webhook_id = str(uuid.uuid4())
    await db_pool.execute(
        """
        INSERT INTO webhooks (id, tenant_id, user_id, type, name, config, is_active)
        VALUES ($1, $2, $3, $4, $5, $6, true)
        """,
        uuid.UUID(webhook_id), uuid.UUID(tenant_id), uuid.UUID(user_id),
        req.type.value, req.name, json.dumps(req.config)
    )
    return webhook_id


async def test_webhook(payload: Dict[str, Any], url: str) -> Dict[str, Any]:
    """Test webhook delivery (mock implementation)"""
    return {
        "webhook_test_id": str(uuid.uuid4()),
        "url": url,
        "payload_size": len(json.dumps(payload)),
        "status": "success",
        "response_time_ms": 125,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# THEME OPERATIONS
# ============================================================================

async def get_themes() -> List[Dict[str, Any]]:
    """Get available themes"""
    rows = await db_pool.fetch(
        """
        SELECT id, name, category, thumbnail_url, primary_color, secondary_color,
               font_family, border_radius, downloads
        FROM themes
        ORDER BY downloads DESC
        """
    )
    return [dict(row) for row in rows]


async def create_theme_variant(req: ThemeCustomizationRequest) -> str:
    """Create custom theme variant"""
    theme_id = str(uuid.uuid4())
    await db_pool.execute(
        """
        INSERT INTO themes (id, name, primary_color, secondary_color, font_family, 
                           border_radius, custom_css)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        uuid.UUID(theme_id), req.name, req.primary_color, req.secondary_color,
        req.font_family, req.border_radius, req.custom_css
    )
    return theme_id


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Marketplace & App Store Service",
    description="Multi-tenant SaaS marketplace for apps, webhooks, and themes",
    version="1.0.0"
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="marketplace")
init_sentry(service_name="marketplace", service_port=9037)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="marketplace")
app.add_middleware(TracingMiddleware)


# CORS configuration from environment - must have explicit allowlist, never "*"
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",")]
# Ensure no wildcard CORS
if "*" in cors_origins:
    cors_origins = ["http://localhost:3000"]

cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



@app.on_event("startup")
async def startup_event():
    """Initialize database pool on startup"""
    await db_pool.initialize()


@app.on_event("shutdown")
async def shutdown_event():
    """Close database pool on shutdown"""

    await event_bus.shutdown()
    await db_pool.close()
    shutdown_tracing()


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/marketplace/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""

    db_status = "connected" if db_pool.pool else "disconnected"
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        database=db_status,
        version="1.0.0"
    )


# ============================================================================
# MARKETPLACE ENDPOINTS
# ============================================================================

@app.get("/marketplace/apps", response_model=List[AppMarketplaceItem])
async def browse_marketplace(
    query: Optional[str] = None,
    category: Optional[AppCategory] = None,
    limit: int = 20,
    offset: int = 0,
    auth: AuthContext = Depends(get_auth_context)
):
    """Browse marketplace apps with search and filtering"""
    apps = await search_apps(query, category.value if category else None, limit, offset, auth.tenant_id)
    result = []
    for app in apps:
        row = await db_pool.fetchrow(
            "SELECT company_name FROM developers WHERE id = $1",
            app["developer_id"]
        )
        developer_name = dict(row)["company_name"] if row else "Unknown"
        result.append(AppMarketplaceItem(
            id=str(app["id"]),
            name=app["name"],
            description=app["description"],
            category=AppCategory(app["category"]),
            icon_url=app["icon_url"],
            developer_id=str(app["developer_id"]),
            developer_name=developer_name,
            version=app["version"],
            rating=float(app["rating"]) if app["rating"] else 0,
            review_count=app["review_count"],
            installation_count=app["installation_count"],
            status=AppStatus(app["status"]),
            created_at=app["created_at"]
        ))
    return result


@app.get("/marketplace/apps/{app_id}", response_model=AppDetailResponse)
async def get_app_detail(
    app_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Get app details"""
    app = await get_app_by_id(app_id, auth.tenant_id)
    row = await db_pool.fetchrow(
        "SELECT company_name FROM developers WHERE id = $1",
        app["developer_id"]
    )
    developer_name = dict(row)["company_name"] if row else "Unknown"

    return AppDetailResponse(
        id=str(app["id"]),
        name=app["name"],
        description=app["description"],
        category=AppCategory(app["category"]),
        icon_url=app["icon_url"],
        developer_id=str(app["developer_id"]),
        developer_name=developer_name,
        version=app["version"],
        rating=float(app["rating"]) if app["rating"] else 0,
        review_count=app["review_count"],
        installation_count=app["installation_count"],
        status=AppStatus(app["status"]),
        created_at=app["created_at"],
        documentation_url=app.get("documentation_url"),
        screenshots=[],
        changelog="Version 1.0.0: Initial release"
    )


@app.post("/marketplace/apps/{app_id}/install", response_model=AppInstallationResponse)
async def install_app_endpoint(
    app_id: str,
    request: AppInstallRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Install app for tenant"""
    installation_id = await install_app(app_id, auth.tenant_id, auth.sub, request.permissions)
    return AppInstallationResponse(
        installation_id=installation_id,
        app_id=app_id,
        tenant_id=auth.tenant_id,
        permissions=request.permissions,
        installed_at=datetime.utcnow()
    )


@app.delete("/marketplace/apps/{app_id}/uninstall")
async def uninstall_app_endpoint(
    app_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Uninstall app for tenant"""
    await uninstall_app(app_id, auth.tenant_id)
    return {"status": "uninstalled", "app_id": app_id}


@app.post("/marketplace/apps/{app_id}/review")
async def submit_app_review(
    app_id: str,
    request: AppReviewRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Submit review for app"""
    await submit_review(app_id, auth.tenant_id, auth.sub, request.rating, request.comment)
    return {"status": "review_submitted", "app_id": app_id, "rating": request.rating}


# ============================================================================
# DEVELOPER PORTAL ENDPOINTS
# ============================================================================

@app.post("/marketplace/developer/register", response_model=DeveloperResponse)
async def register_as_developer(
    request: DeveloperRegisterRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Register as app developer"""
    developer_id = await register_developer(auth.sub, auth.tenant_id, request)
    return DeveloperResponse(
        developer_id=developer_id,
        user_id=auth.sub,
        company_name=request.company_name,
        status="pending",
        created_at=datetime.utcnow()
    )


@app.post("/marketplace/developer/apps")
async def submit_developer_app(
    request: AppSubmitRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Submit app for marketplace review"""
    # Get developer profile
    dev = await db_pool.fetchrow(
        "SELECT id FROM developers WHERE user_id = $1 AND tenant_id = $2",
        uuid.UUID(auth.sub), uuid.UUID(auth.tenant_id)
    )
    if not dev:
        raise HTTPException(status_code=400, detail="Must register as developer first")

    app_id = await submit_app(str(dev["id"]), auth.tenant_id, request)
    return {"status": "submitted", "app_id": app_id}


@app.get("/marketplace/developer/apps")
async def list_developer_apps(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get developer's apps"""
    dev = await db_pool.fetchrow(
        "SELECT id FROM developers WHERE user_id = $1 AND tenant_id = $2",
        uuid.UUID(auth.sub), uuid.UUID(auth.tenant_id)
    )
    if not dev:
        return []

    apps = await get_developer_apps(str(dev["id"]), auth.tenant_id)
    return [
        {
            "id": str(app["id"]),
            "name": app["name"],
            "category": app["category"],
            "status": app["status"],
            "rating": float(app["rating"]) if app["rating"] else 0,
            "installation_count": app["installation_count"],
            "created_at": app["created_at"]
        }
        for app in apps
    ]


# ============================================================================
# WEBHOOK MARKETPLACE ENDPOINTS
# ============================================================================

@app.get("/marketplace/webhooks/templates", response_model=List[WebhookTemplateResponse])
async def get_webhook_templates_endpoint(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get pre-built webhook templates"""
    templates = await get_webhook_templates()
    return [
        WebhookTemplateResponse(
            id=str(t["id"]),
            type=WebhookType(t["type"]),
            name=t["name"],
            description=t.get("description", ""),
            example_payload=json.loads(t["example_payload"]) if isinstance(t["example_payload"], str) else t["example_payload"]
        )
        for t in templates
    ]


@app.post("/marketplace/webhooks")
async def create_custom_webhook(
    request: WebhookTemplateRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create custom webhook"""
    webhook_id = await create_webhook(auth.tenant_id, auth.sub, request)
    return {
        "status": "created",
        "webhook_id": webhook_id,
        "type": request.type.value,
        "name": request.name
    }


@app.post("/marketplace/webhooks/test")
async def test_webhook_delivery(
    request: WebhookTestRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Test webhook delivery"""
    result = await test_webhook(request.payload, request.url)
    return result


# ============================================================================
# THEME & WIDGET ENDPOINTS
# ============================================================================

@app.get("/marketplace/themes", response_model=List[ThemeResponse])
async def list_themes(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get available themes"""
    themes = await get_themes()
    return [
        ThemeResponse(
            id=str(t["id"]),
            name=t["name"],
            category=t.get("category", "default"),
            thumbnail_url=t.get("thumbnail_url", ""),
            primary_color=t["primary_color"],
            secondary_color=t["secondary_color"],
            font_family=t["font_family"],
            border_radius=t["border_radius"],
            downloads=t["downloads"]
        )
        for t in themes
    ]


@app.post("/marketplace/themes/customize")
async def customize_theme(
    request: ThemeCustomizationRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create custom theme variant"""
    theme_id = await create_theme_variant(request)
    return {
        "status": "created",
        "theme_id": theme_id,
        "name": request.name,
        "primary_color": request.primary_color
    }


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 9037))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
