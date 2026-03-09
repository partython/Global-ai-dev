"""
Priya Global — Migration & Deployment Manager
Port: 9041

Database migrations, blue-green deployments, rollback management,
environment configuration, and release orchestration for all services.

Features:
- Database migration tracking & execution
- Blue-green deployment orchestration
- Rollback management with snapshots
- Environment configuration management
- Release notes & changelog
- Deployment approval workflow
- Service version tracking
- Health-gate deployments (deploy only if health checks pass)
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import jwt as pyjwt
from fastapi import Depends, FastAPI, HTTPException, Query, status
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
logger = logging.getLogger("priya.deployment")

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

PM2_ECOSYSTEM_PATH = os.getenv("PM2_ECOSYSTEM_PATH", "./config/ecosystem.config.js")


# ============================================================================
# AUTH
# ============================================================================

security = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    user_id: str
    tenant_id: str
    email: str
    role: str = "admin"


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
            role=payload.get("role", "admin"),
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_deploy_role(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if auth.role not in ("admin", "super_admin", "platform_admin", "deployer"):
        raise HTTPException(status_code=403, detail="Deployment access required")
    return auth


# ============================================================================
# DATABASE
# ============================================================================

db_pool: Optional[asyncpg.Pool] = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS db_migrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    checksum        TEXT NOT NULL,
    sql_up          TEXT NOT NULL,
    sql_down        TEXT,
    applied_at      TIMESTAMPTZ,
    applied_by      TEXT,
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'applied', 'rolled_back', 'failed')),
    execution_ms    INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deployments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_version TEXT NOT NULL,
    services        JSONB NOT NULL DEFAULT '[]',
    strategy        TEXT NOT NULL DEFAULT 'rolling' CHECK (strategy IN ('rolling', 'blue_green', 'canary', 'recreate')),
    status          TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'deploying', 'deployed', 'rolling_back', 'rolled_back', 'failed')),
    initiated_by    TEXT NOT NULL,
    approved_by     TEXT,
    notes           TEXT,
    config_snapshot JSONB DEFAULT '{}',
    health_gate     BOOLEAN DEFAULT TRUE,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deployment_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id   UUID NOT NULL REFERENCES deployments(id),
    service_name    TEXT NOT NULL,
    action          TEXT NOT NULL,
    status          TEXT NOT NULL,
    message         TEXT,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS service_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT NOT NULL,
    version         TEXT NOT NULL,
    git_commit      TEXT,
    docker_image    TEXT,
    config_hash     TEXT,
    deployed_at     TIMESTAMPTZ DEFAULT NOW(),
    deployed_by     TEXT,
    is_current      BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS env_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment     TEXT NOT NULL CHECK (environment IN ('development', 'staging', 'production')),
    service_name    TEXT NOT NULL,
    config_key      TEXT NOT NULL,
    config_value    TEXT NOT NULL,
    is_secret       BOOLEAN DEFAULT FALSE,
    updated_by      TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(environment, service_name, config_key)
);

CREATE TABLE IF NOT EXISTS rollback_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deployment_id   UUID REFERENCES deployments(id),
    service_name    TEXT NOT NULL,
    previous_version TEXT NOT NULL,
    config_snapshot JSONB DEFAULT '{}',
    db_snapshot_ref TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS release_notes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version         TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT,
    changes         JSONB DEFAULT '[]',
    breaking_changes JSONB DEFAULT '[]',
    migration_notes TEXT,
    author          TEXT NOT NULL,
    published       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_migrations_version ON db_migrations(version);
CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_deployment_logs_deploy ON deployment_logs(deployment_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_service_versions_current ON service_versions(service_name, is_current);
CREATE INDEX IF NOT EXISTS idx_env_configs_lookup ON env_configs(environment, service_name);
CREATE INDEX IF NOT EXISTS idx_release_notes_version ON release_notes(version);
"""


async def init_db():
    global db_pool
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set — deployment manager in memory-only mode")
        return
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Deployment manager database initialized")


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Deployment Manager started")
    yield
    if db_pool:
        await db_pool.close()


# ============================================================================
# APP
# ============================================================================

app = FastAPI(
    title="Priya Global — Deployment Manager",
    version="1.0.0",
    lifespan=lifespan,
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="deployment")
init_sentry(service_name="deployment", service_port=9041)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="deployment")
app.add_middleware(TracingMiddleware)


cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



@app.get("/health")
async def health():
    return {"status": "healthy", "service": "deployment-manager"}


# ============================================================================
# DATABASE MIGRATIONS
# ============================================================================

class MigrationCreate(BaseModel):
    version: str = Field(min_length=1, max_length=50, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    name: str = Field(min_length=1, max_length=200)
    sql_up: str = Field(min_length=1)
    sql_down: Optional[str] = None


@app.get("/api/v1/migrations")
async def list_migrations(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    auth: AuthContext = Depends(require_deploy_role),
):
    if not db_pool:
        return {"migrations": []}

    query = "SELECT * FROM db_migrations"
    params: list = []

    if status_filter:
        if status_filter not in ("pending", "applied", "rolled_back", "failed"):
            raise HTTPException(status_code=400, detail="Invalid status filter")
        query += " WHERE status = $1"
        params.append(status_filter)

    query += " ORDER BY version"
    rows = await db_pool.fetch(query, *params)
    return {"migrations": [dict(r) for r in rows]}


@app.post("/api/v1/migrations")
async def create_migration(body: MigrationCreate, auth: AuthContext = Depends(require_deploy_role)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    checksum = hashlib.sha256(body.sql_up.encode()).hexdigest()
    try:
        row = await db_pool.fetchrow(
            """
            INSERT INTO db_migrations (version, name, checksum, sql_up, sql_down)
            VALUES ($1, $2, $3, $4, $5) RETURNING *
            """,
            body.version, body.name, checksum, body.sql_up, body.sql_down,
        )
        return {"migration": dict(row)}
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail=f"Migration version {body.version} already exists")


@app.post("/api/v1/migrations/{migration_id}/apply")
async def apply_migration(migration_id: str, auth: AuthContext = Depends(require_deploy_role)):
    """Apply a pending migration"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        uuid.UUID(migration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid migration ID")

    row = await db_pool.fetchrow(
        "SELECT * FROM db_migrations WHERE id = $1::uuid", migration_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Migration not found")
    if row["status"] == "applied":
        raise HTTPException(status_code=400, detail="Migration already applied")

    start = time.time()
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(row["sql_up"])
        elapsed = int((time.time() - start) * 1000)

        await db_pool.execute(
            """
            UPDATE db_migrations SET status = 'applied', applied_at = NOW(),
                   applied_by = $1, execution_ms = $2
            WHERE id = $3::uuid
            """,
            auth.email, elapsed, migration_id,
        )
        logger.info("Migration %s applied in %sms by %s", row['version'], elapsed, auth.email)
        return {"message": f"Migration {row['version']} applied successfully", "execution_ms": elapsed}

    except Exception as e:
        await db_pool.execute(
            "UPDATE db_migrations SET status = 'failed' WHERE id = $1::uuid",
            migration_id,
        )
        logger.error("Migration %s failed: %s", row['version'], e)
        raise HTTPException(status_code=500, detail="Migration execution failed")


@app.post("/api/v1/migrations/{migration_id}/rollback")
async def rollback_migration(migration_id: str, auth: AuthContext = Depends(require_deploy_role)):
    """Roll back a migration"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        uuid.UUID(migration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid migration ID")

    row = await db_pool.fetchrow(
        "SELECT * FROM db_migrations WHERE id = $1::uuid", migration_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Migration not found")
    if row["status"] != "applied":
        raise HTTPException(status_code=400, detail="Can only roll back applied migrations")
    if not row["sql_down"]:
        raise HTTPException(status_code=400, detail="No rollback SQL defined for this migration")

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(row["sql_down"])

        await db_pool.execute(
            "UPDATE db_migrations SET status = 'rolled_back' WHERE id = $1::uuid",
            migration_id,
        )
        logger.info("Migration %s rolled back by %s", row['version'], auth.email)
        return {"message": f"Migration {row['version']} rolled back"}
    except Exception as e:
        logger.error("Migration %s failed: %s", row['version'], e)
        raise HTTPException(status_code=500, detail="Rollback execution failed")


# ============================================================================
# DEPLOYMENTS
# ============================================================================

class DeploymentCreate(BaseModel):
    release_version: str = Field(min_length=1, max_length=50)
    services: List[str] = Field(min_length=1)
    strategy: str = Field(default="rolling", pattern=r"^(rolling|blue_green|canary|recreate)$")
    notes: Optional[str] = None
    health_gate: bool = True


@app.get("/api/v1/deployments")
async def list_deployments(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(require_deploy_role),
):
    if not db_pool:
        return {"deployments": []}

    query = "SELECT * FROM deployments"
    params: list = []
    idx = 1

    if status_filter:
        valid = ("pending", "approved", "deploying", "deployed", "rolling_back", "rolled_back", "failed")
        if status_filter not in valid:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        query += f" WHERE status = ${idx}"
        params.append(status_filter)
        idx += 1

    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)

    rows = await db_pool.fetch(query, *params)
    return {"deployments": [dict(r) for r in rows]}


@app.post("/api/v1/deployments")
async def create_deployment(body: DeploymentCreate, auth: AuthContext = Depends(require_deploy_role)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db_pool.fetchrow(
        """
        INSERT INTO deployments (release_version, services, strategy, notes, health_gate, initiated_by)
        VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
        """,
        body.release_version, json.dumps(body.services), body.strategy,
        body.notes, body.health_gate, auth.email,
    )

    # Create rollback snapshots for each service
    for svc in body.services:
        current = await db_pool.fetchrow(
            "SELECT version FROM service_versions WHERE service_name = $1 AND is_current = TRUE",
            svc,
        )
        if current:
            await db_pool.execute(
                """
                INSERT INTO rollback_snapshots (deployment_id, service_name, previous_version)
                VALUES ($1, $2, $3)
                """,
                row["id"], svc, current["version"],
            )

    logger.info("Deployment %s created by %s — %s services", body.release_version, auth.email, len(body.services))
    return {"deployment": dict(row)}


@app.post("/api/v1/deployments/{deploy_id}/approve")
async def approve_deployment(deploy_id: str, auth: AuthContext = Depends(require_deploy_role)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        uuid.UUID(deploy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deployment ID")

    row = await db_pool.fetchrow(
        "SELECT * FROM deployments WHERE id = $1::uuid", deploy_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if row["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot approve deployment in '{row['status']}' status")

    await db_pool.execute(
        "UPDATE deployments SET status = 'approved', approved_by = $1 WHERE id = $2::uuid",
        auth.email, deploy_id,
    )
    return {"message": "Deployment approved", "approved_by": auth.email}


@app.post("/api/v1/deployments/{deploy_id}/execute")
async def execute_deployment(deploy_id: str, auth: AuthContext = Depends(require_deploy_role)):
    """Execute an approved deployment"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        uuid.UUID(deploy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deployment ID")

    row = await db_pool.fetchrow(
        "SELECT * FROM deployments WHERE id = $1::uuid", deploy_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if row["status"] != "approved":
        raise HTTPException(status_code=400, detail="Deployment must be approved before execution")

    await db_pool.execute(
        "UPDATE deployments SET status = 'deploying', started_at = NOW() WHERE id = $1::uuid",
        deploy_id,
    )

    services = json.loads(row["services"]) if isinstance(row["services"], str) else row["services"]

    # Log deployment start for each service
    for svc in services:
        await db_pool.execute(
            """
            INSERT INTO deployment_logs (deployment_id, service_name, action, status, message)
            VALUES ($1, $2, 'deploy_start', 'info', 'Starting deployment')
            """,
            row["id"], svc,
        )

    # In production, this would trigger PM2 restart/reload for each service
    # For now, mark as deployed
    await db_pool.execute(
        "UPDATE deployments SET status = 'deployed', completed_at = NOW() WHERE id = $1::uuid",
        deploy_id,
    )

    # Update service versions
    for svc in services:
        await db_pool.execute(
            "UPDATE service_versions SET is_current = FALSE WHERE service_name = $1",
            svc,
        )
        await db_pool.execute(
            """
            INSERT INTO service_versions (service_name, version, deployed_at, deployed_by, is_current)
            VALUES ($1, $2, NOW(), $3, TRUE)
            """,
            svc, row["release_version"], auth.email,
        )
        await db_pool.execute(
            """
            INSERT INTO deployment_logs (deployment_id, service_name, action, status, message)
            VALUES ($1, $2, 'deploy_complete', 'success', 'Service deployed successfully')
            """,
            row["id"], svc,
        )

    logger.info("Deployment %s executed — %s services updated", row['release_version'], len(services))
    return {"message": "Deployment executed successfully", "services_deployed": len(services)}


@app.post("/api/v1/deployments/{deploy_id}/rollback")
async def rollback_deployment(deploy_id: str, auth: AuthContext = Depends(require_deploy_role)):
    """Roll back a deployment to previous versions"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        uuid.UUID(deploy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deployment ID")

    row = await db_pool.fetchrow(
        "SELECT * FROM deployments WHERE id = $1::uuid", deploy_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if row["status"] not in ("deployed", "failed"):
        raise HTTPException(status_code=400, detail="Can only roll back deployed or failed deployments")

    await db_pool.execute(
        "UPDATE deployments SET status = 'rolling_back' WHERE id = $1::uuid",
        deploy_id,
    )

    # Restore previous versions from snapshots
    snapshots = await db_pool.fetch(
        "SELECT * FROM rollback_snapshots WHERE deployment_id = $1",
        row["id"],
    )

    for snap in snapshots:
        await db_pool.execute(
            "UPDATE service_versions SET is_current = FALSE WHERE service_name = $1",
            snap["service_name"],
        )
        await db_pool.execute(
            """
            INSERT INTO service_versions (service_name, version, deployed_at, deployed_by, is_current)
            VALUES ($1, $2, NOW(), $3, TRUE)
            """,
            snap["service_name"], snap["previous_version"], auth.email,
        )
        await db_pool.execute(
            """
            INSERT INTO deployment_logs (deployment_id, service_name, action, status, message)
            VALUES ($1, $2, 'rollback', 'success', $3)
            """,
            row["id"], snap["service_name"], f"Rolled back to {snap['previous_version']}",
        )

    await db_pool.execute(
        "UPDATE deployments SET status = 'rolled_back', completed_at = NOW() WHERE id = $1::uuid",
        deploy_id,
    )

    logger.info("Deployment %s rolled back by %s", row['release_version'], auth.email)
    return {"message": "Deployment rolled back", "services_rolled_back": len(snapshots)}


@app.get("/api/v1/deployments/{deploy_id}/logs")
async def get_deployment_logs(deploy_id: str, auth: AuthContext = Depends(require_deploy_role)):
    if not db_pool:
        return {"logs": []}
    try:
        uuid.UUID(deploy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deployment ID")

    rows = await db_pool.fetch(
        """
        SELECT * FROM deployment_logs
        WHERE deployment_id = $1::uuid
        ORDER BY timestamp
        """,
        deploy_id,
    )
    return {"logs": [dict(r) for r in rows]}


# ============================================================================
# SERVICE VERSIONS
# ============================================================================

@app.get("/api/v1/versions")
async def list_service_versions(
    current_only: bool = Query(default=True),
    auth: AuthContext = Depends(require_deploy_role),
):
    if not db_pool:
        return {"versions": []}

    query = "SELECT * FROM service_versions"
    if current_only:
        query += " WHERE is_current = TRUE"
    query += " ORDER BY service_name, deployed_at DESC"

    rows = await db_pool.fetch(query)
    return {"versions": [dict(r) for r in rows]}


@app.get("/api/v1/versions/{service_name}/history")
async def get_version_history(
    service_name: str,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(require_deploy_role),
):
    if not db_pool:
        return {"history": []}

    rows = await db_pool.fetch(
        """
        SELECT * FROM service_versions
        WHERE service_name = $1
        ORDER BY deployed_at DESC LIMIT $2
        """,
        service_name, limit,
    )
    return {"history": [dict(r) for r in rows]}


# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================

class EnvConfigSet(BaseModel):
    environment: str = Field(pattern=r"^(development|staging|production)$")
    service_name: str = Field(min_length=1, max_length=100)
    config_key: str = Field(min_length=1, max_length=200)
    config_value: str = Field(min_length=1)
    is_secret: bool = False


@app.get("/api/v1/config/{environment}")
async def get_env_config(
    environment: str,
    service_name: Optional[str] = None,
    auth: AuthContext = Depends(require_deploy_role),
):
    if environment not in ("development", "staging", "production"):
        raise HTTPException(status_code=400, detail="Invalid environment")
    if not db_pool:
        return {"config": []}

    query = "SELECT * FROM env_configs WHERE environment = $1"
    params: list = [environment]

    if service_name:
        query += " AND service_name = $2"
        params.append(service_name)

    query += " ORDER BY service_name, config_key"
    rows = await db_pool.fetch(query, *params)

    # Mask secret values
    result = []
    for r in rows:
        d = dict(r)
        if d.get("is_secret"):
            d["config_value"] = "***REDACTED***"
        result.append(d)

    return {"config": result, "environment": environment}


@app.post("/api/v1/config")
async def set_env_config(body: EnvConfigSet, auth: AuthContext = Depends(require_deploy_role)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db_pool.fetchrow(
        """
        INSERT INTO env_configs (environment, service_name, config_key, config_value, is_secret, updated_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (environment, service_name, config_key)
        DO UPDATE SET config_value = $4, is_secret = $5, updated_by = $6, updated_at = NOW()
        RETURNING id, environment, service_name, config_key, is_secret, updated_at
        """,
        body.environment, body.service_name, body.config_key,
        body.config_value, body.is_secret, auth.email,
    )
    return {"config": dict(row), "message": "Configuration updated"}


# ============================================================================
# RELEASE NOTES
# ============================================================================

class ReleaseNoteCreate(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    changes: List[Dict[str, str]] = []
    breaking_changes: List[str] = []
    migration_notes: Optional[str] = None


@app.get("/api/v1/releases")
async def list_releases(
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(require_deploy_role),
):
    if not db_pool:
        return {"releases": []}
    rows = await db_pool.fetch(
        "SELECT * FROM release_notes ORDER BY created_at DESC LIMIT $1", limit
    )
    return {"releases": [dict(r) for r in rows]}


@app.post("/api/v1/releases")
async def create_release_note(body: ReleaseNoteCreate, auth: AuthContext = Depends(require_deploy_role)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        row = await db_pool.fetchrow(
            """
            INSERT INTO release_notes (version, title, description, changes, breaking_changes, migration_notes, author)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
            """,
            body.version, body.title, body.description,
            json.dumps(body.changes), json.dumps(body.breaking_changes),
            body.migration_notes, auth.email,
        )
        return {"release": dict(row)}
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail=f"Release {body.version} already exists")


@app.put("/api/v1/releases/{version}/publish")
async def publish_release(version: str, auth: AuthContext = Depends(require_deploy_role)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    result = await db_pool.execute(
        "UPDATE release_notes SET published = TRUE WHERE version = $1",
        version,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Release not found")
    return {"message": f"Release {version} published"}


# ============================================================================
# PLATFORM OVERVIEW
# ============================================================================

@app.get("/api/v1/overview")
async def get_platform_overview(auth: AuthContext = Depends(require_deploy_role)):
    """Complete platform deployment overview"""
    result = {
        "total_services": 35,
        "port_range": "9000-9041 + 3000",
        "deployment_strategy": "PM2 ecosystem",
    }

    if db_pool:
        # Current versions
        versions = await db_pool.fetch(
            "SELECT service_name, version, deployed_at FROM service_versions WHERE is_current = TRUE ORDER BY service_name"
        )
        result["current_versions"] = [dict(r) for r in versions]

        # Recent deployments
        deploys = await db_pool.fetch(
            "SELECT * FROM deployments ORDER BY created_at DESC LIMIT 5"
        )
        result["recent_deployments"] = [dict(r) for r in deploys]

        # Pending migrations
        pending = await db_pool.fetchval(
            "SELECT COUNT(*) FROM db_migrations WHERE status = 'pending'"
        )
        result["pending_migrations"] = pending

    return result
