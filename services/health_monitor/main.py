"""
Priya Global — Health Monitor & Service Mesh
Port: 9039

Centralized health monitoring, circuit breakers, service discovery,
and uptime tracking for all 33+ platform services.

Features:
- Real-time health checks for all services
- Circuit breaker pattern (closed → open → half-open)
- Service registry & discovery
- Uptime tracking & SLA monitoring
- Incident management & auto-recovery
- Alert system (webhook, email, SMS)
- Dependency graph visualization
- Performance metrics aggregation
"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import asyncpg
import httpx
import jwt as pyjwt
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
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
logger = logging.getLogger("priya.health_monitor")

DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")

# Validate secrets at module load time
if not JWT_SECRET:
    logger.warning("Server configuration incomplete — authentication unavailable")
if not DATABASE_URL:
    logger.warning("Server configuration incomplete — running in memory-only mode")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://app.currentglobal.com,https://admin.currentglobal.com"
).split(",")

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "30"))
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
CIRCUIT_BREAKER_RECOVERY_SEC = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_SEC", "60"))
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

# ============================================================================
# SERVICE REGISTRY — All Priya Global services
# ============================================================================

SERVICE_REGISTRY = {
    "gateway":              {"port": 9000, "critical": True,  "layer": 0},
    "auth":                 {"port": 9001, "critical": True,  "layer": 1},
    "tenant":               {"port": 9002, "critical": True,  "layer": 1},
    "channel-router":       {"port": 9003, "critical": True,  "layer": 2},
    "ai-engine":            {"port": 9004, "critical": True,  "layer": 3},
    "whatsapp":             {"port": 9010, "critical": False, "layer": 4},
    "email":                {"port": 9011, "critical": False, "layer": 4},
    "voice":                {"port": 9012, "critical": False, "layer": 4},
    "social":               {"port": 9013, "critical": False, "layer": 4},
    "webchat":              {"port": 9014, "critical": False, "layer": 4},
    "sms":                  {"port": 9015, "critical": False, "layer": 4},
    "telegram":             {"port": 9016, "critical": False, "layer": 4},
    "billing":              {"port": 9020, "critical": True,  "layer": 5},
    "analytics":            {"port": 9021, "critical": False, "layer": 5},
    "marketing":            {"port": 9022, "critical": False, "layer": 5},
    "ecommerce":            {"port": 9023, "critical": False, "layer": 6},
    "notification":         {"port": 9024, "critical": False, "layer": 6},
    "plugins":              {"port": 9025, "critical": False, "layer": 6},
    "handoff":              {"port": 9026, "critical": False, "layer": 6},
    "leads":                {"port": 9027, "critical": False, "layer": 7},
    "conversation-intel":   {"port": 9028, "critical": False, "layer": 7},
    "appointments":         {"port": 9029, "critical": False, "layer": 7},
    "knowledge":            {"port": 9030, "critical": False, "layer": 7},
    "voice-ai":             {"port": 9031, "critical": False, "layer": 8},
    "video":                {"port": 9032, "critical": False, "layer": 8},
    "rcs":                  {"port": 9033, "critical": False, "layer": 8},
    "workflows":            {"port": 9034, "critical": False, "layer": 8},
    "advanced-analytics":   {"port": 9035, "critical": False, "layer": 9},
    "ai-training":          {"port": 9036, "critical": False, "layer": 9},
    "marketplace":          {"port": 9037, "critical": False, "layer": 9},
    "compliance":           {"port": 9038, "critical": False, "layer": 9},
}

# Service dependency graph
SERVICE_DEPENDENCIES = {
    "channel-router": ["auth", "tenant", "ai-engine"],
    "whatsapp":       ["channel-router", "ai-engine"],
    "email":          ["channel-router", "ai-engine"],
    "voice":          ["channel-router", "ai-engine"],
    "social":         ["channel-router", "ai-engine"],
    "webchat":        ["channel-router", "ai-engine"],
    "sms":            ["channel-router", "ai-engine"],
    "telegram":       ["channel-router", "ai-engine"],
    "billing":        ["auth", "tenant"],
    "ecommerce":      ["auth", "tenant"],
    "notification":   ["auth", "tenant"],
    "handoff":        ["auth", "tenant", "channel-router"],
    "leads":          ["auth", "tenant", "analytics"],
    "knowledge":      ["auth", "tenant", "ai-engine"],
    "workflows":      ["auth", "tenant", "notification"],
    "marketplace":    ["auth", "tenant", "billing"],
    "compliance":     ["auth", "tenant"],
}


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================

class CircuitState(str, Enum):
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"    # Testing recovery


@dataclass
class CircuitBreaker:
    service_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    threshold: int = CIRCUIT_BREAKER_THRESHOLD
    recovery_timeout: int = CIRCUIT_BREAKER_RECOVERY_SEC

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_success_time = time.time()

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.state = CircuitState.OPEN
            logger.warning("Circuit OPEN for %s after %s failures", self.service_name, self.failure_count)

    def should_allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit HALF-OPEN for %s, testing recovery", self.service_name)
                return True
            return False
        # HALF_OPEN — allow one test request
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure": datetime.fromtimestamp(self.last_failure_time, tz=timezone.utc).isoformat() if self.last_failure_time else None,
            "last_success": datetime.fromtimestamp(self.last_success_time, tz=timezone.utc).isoformat() if self.last_success_time else None,
        }


# ============================================================================
# GLOBAL STATE
# ============================================================================

db_pool: Optional[asyncpg.Pool] = None
circuit_breakers: Dict[str, CircuitBreaker] = {}
health_check_task: Optional[asyncio.Task] = None
ws_subscribers: Set[WebSocket] = set()

# In-memory status cache
service_status_cache: Dict[str, Dict[str, Any]] = {}


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


def require_admin(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if auth.role not in ("admin", "super_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return auth


# ============================================================================
# DATABASE
# ============================================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS service_health_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('healthy', 'degraded', 'down')),
    response_ms     DOUBLE PRECISION,
    error_message   TEXT,
    checked_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'closed')),
    opened_at       TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT,
    tenant_id       TEXT NOT NULL DEFAULT 'platform'
);

CREATE TABLE IF NOT EXISTS uptime_daily (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    TEXT NOT NULL,
    date            DATE NOT NULL,
    total_checks    INT DEFAULT 0,
    healthy_checks  INT DEFAULT 0,
    uptime_pct      DOUBLE PRECISION DEFAULT 100.0,
    avg_response_ms DOUBLE PRECISION DEFAULT 0,
    UNIQUE(service_name, date)
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL DEFAULT 'platform',
    service_name    TEXT,
    condition_type  TEXT NOT NULL CHECK (condition_type IN ('down', 'degraded', 'response_time', 'circuit_open')),
    threshold       DOUBLE PRECISION,
    notify_channel  TEXT NOT NULL CHECK (notify_channel IN ('webhook', 'email', 'sms')),
    notify_target   TEXT NOT NULL,
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_log_service ON service_health_log(service_name, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_uptime_daily_service ON uptime_daily(service_name, date DESC);
"""


async def init_db():
    global db_pool
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set — health monitor running in memory-only mode")
        return
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Health monitor database initialized")


# ============================================================================
# HEALTH CHECK ENGINE
# ============================================================================

async def check_service_health(service_name: str, port: int) -> Dict[str, Any]:
    """Check a single service's /health endpoint"""
    url = f"http://localhost:{port}/health"
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            elapsed_ms = (time.time() - start) * 1000

            if resp.status_code == 200:
                status_val = "healthy" if elapsed_ms < 5000 else "degraded"
            else:
                status_val = "degraded"

            return {
                "service": service_name,
                "status": status_val,
                "response_ms": round(elapsed_ms, 2),
                "http_status": resp.status_code,
                "error": None,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
    except httpx.ConnectError:
        elapsed_ms = (time.time() - start) * 1000
        return {
            "service": service_name,
            "status": "down",
            "response_ms": round(elapsed_ms, 2),
            "http_status": None,
            "error": "Connection refused",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except httpx.TimeoutException:
        return {
            "service": service_name,
            "status": "down",
            "response_ms": 10000,
            "http_status": None,
            "error": "Timeout (10s)",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        elapsed_ms = (time.time() - start) * 1000
        return {
            "service": service_name,
            "status": "down",
            "response_ms": round(elapsed_ms, 2),
            "http_status": None,
            "error": "Health check failed",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


async def run_health_checks():
    """Check all services concurrently"""
    tasks = []
    for name, info in SERVICE_REGISTRY.items():
        cb = circuit_breakers.get(name)
        if cb and not cb.should_allow_request():
            service_status_cache[name] = {
                "service": name,
                "status": "down",
                "response_ms": 0,
                "http_status": None,
                "error": "Circuit breaker OPEN",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "circuit_state": "open",
            }
            continue
        tasks.append(check_service_health(name, info["port"]))

    if not tasks:
        return

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            continue
        if not isinstance(result, dict):
            continue

        svc_name = result["service"]
        cb = circuit_breakers.setdefault(svc_name, CircuitBreaker(service_name=svc_name))

        if result["status"] == "healthy":
            cb.record_success()
        else:
            cb.record_failure()

        result["circuit_state"] = cb.state.value
        service_status_cache[svc_name] = result

        # Persist to DB
        if db_pool:
            try:
                await db_pool.execute(
                    """
                    INSERT INTO service_health_log (service_name, status, response_ms, error_message)
                    VALUES ($1, $2, $3, $4)
                    """,
                    svc_name, result["status"], result["response_ms"], result.get("error"),
                )
            except Exception as e:
                logger.error("Failed to log health for %s: %s", svc_name, e)

        # Auto-create incident for critical services going down
        if result["status"] == "down" and SERVICE_REGISTRY.get(svc_name, {}).get("critical"):
            await create_auto_incident(svc_name, result.get("error", "Service unreachable"))

    # Update uptime daily
    if db_pool:
        await update_uptime_stats()

    # Broadcast to WebSocket subscribers
    await broadcast_status_update()


async def create_auto_incident(service_name: str, error_msg: str):
    """Auto-create an incident when a critical service goes down"""
    if not db_pool:
        return
    # Check if there's already an open incident for this service
    existing = await db_pool.fetchval(
        "SELECT id FROM incidents WHERE service_name = $1 AND status IN ('open', 'investigating') LIMIT 1",
        service_name,
    )
    if existing:
        return

    await db_pool.execute(
        """
        INSERT INTO incidents (service_name, severity, title, description, status)
        VALUES ($1, 'critical', $2, $3, 'open')
        """,
        service_name,
        "Service %s is DOWN" % service_name,
        "Automated incident: %s" % error_msg,
    )
    logger.warning("Auto-incident created for %s: %s", service_name, error_msg)

    # Send alert webhook
    if ALERT_WEBHOOK_URL:
        await send_alert_webhook(service_name, "critical", error_msg)


async def send_alert_webhook(service_name: str, severity: str, message: str):
    """Send alert to configured webhook"""
    if not ALERT_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(ALERT_WEBHOOK_URL, json={
                "service": service_name,
                "severity": severity,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": "priya-global",
            })
    except Exception as e:
        logger.error("Failed to send alert webhook: %s", e)


async def update_uptime_stats():
    """Update daily uptime statistics"""
    if not db_pool:
        return
    today = datetime.now(timezone.utc).date()
    for svc_name in SERVICE_REGISTRY:
        try:
            await db_pool.execute(
                """
                INSERT INTO uptime_daily (service_name, date, total_checks, healthy_checks, uptime_pct, avg_response_ms)
                SELECT $1, $2,
                       COUNT(*),
                       COUNT(*) FILTER (WHERE status = 'healthy'),
                       ROUND(COUNT(*) FILTER (WHERE status = 'healthy') * 100.0 / NULLIF(COUNT(*), 0), 2),
                       ROUND(AVG(response_ms)::numeric, 2)
                FROM service_health_log
                WHERE service_name = $1 AND checked_at::date = $2
                ON CONFLICT (service_name, date) DO UPDATE SET
                    total_checks = EXCLUDED.total_checks,
                    healthy_checks = EXCLUDED.healthy_checks,
                    uptime_pct = EXCLUDED.uptime_pct,
                    avg_response_ms = EXCLUDED.avg_response_ms
                """,
                svc_name, today,
            )
        except Exception as e:
            logger.error("Failed to update uptime for %s: %s", svc_name, e)


async def broadcast_status_update():
    """Send status updates to all WebSocket subscribers"""
    if not ws_subscribers:
        return
    payload = json.dumps({
        "type": "health_update",
        "data": service_status_cache,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    disconnected = set()
    for ws in ws_subscribers:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.add(ws)
    ws_subscribers -= disconnected


async def health_check_loop():
    """Background task running periodic health checks"""
    while True:
        try:
            await run_health_checks()
        except Exception as e:
            logger.error("Health check loop error: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global health_check_task
    await init_db()
    # Initialize circuit breakers
    for name in SERVICE_REGISTRY:
        circuit_breakers[name] = CircuitBreaker(service_name=name)
    # Start background health checks
    health_check_task = asyncio.create_task(health_check_loop())
    logger.info("Health monitor started — monitoring %s services every %ss", len(SERVICE_REGISTRY), CHECK_INTERVAL_SECONDS)
    yield
    if health_check_task:
        health_check_task.cancel()
    if db_pool:
        await db_pool.close()


# ============================================================================
# APP
# ============================================================================

app = FastAPI(
    title="Priya Global — Health Monitor & Service Mesh",
    version="1.0.0",
    lifespan=lifespan,
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="health_monitor")
init_sentry(service_name="health-monitor", service_port=9039)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="health-monitor")
app.add_middleware(TracingMiddleware)


cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@app.get("/health")
async def self_health():
    """Health check for the health monitor itself"""
    services_up = sum(1 for s in service_status_cache.values() if s.get("status") == "healthy")
    total = len(SERVICE_REGISTRY)
    return {
        "status": "healthy",
        "service": "health-monitor",
        "monitored_services": total,
        "healthy_services": services_up,
        "check_interval_seconds": CHECK_INTERVAL_SECONDS,
    }


@app.get("/status")
async def public_status():
    """Public-facing status page data (no auth required, limited info)"""
    summary = {}
    for name, info in SERVICE_REGISTRY.items():
        cached = service_status_cache.get(name, {})
        summary[name] = {
            "status": cached.get("status", "unknown"),
            "layer": info["layer"],
            "critical": info["critical"],
        }

    healthy = sum(1 for s in summary.values() if s["status"] == "healthy")
    degraded = sum(1 for s in summary.values() if s["status"] == "degraded")
    down = sum(1 for s in summary.values() if s["status"] == "down")

    overall = "operational"
    if down > 0:
        overall = "major_outage" if any(
            s["status"] == "down" and s["critical"] for s in summary.values()
        ) else "partial_outage"
    elif degraded > 0:
        overall = "degraded"

    return {
        "overall_status": overall,
        "services": summary,
        "counts": {"healthy": healthy, "degraded": degraded, "down": down},
        "last_check": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# AUTHENTICATED ENDPOINTS
# ============================================================================

@app.get("/api/v1/services")
async def list_services(auth: AuthContext = Depends(require_admin)):
    """Detailed service status for admin dashboard"""
    result = []
    for name, info in SERVICE_REGISTRY.items():
        cached = service_status_cache.get(name, {})
        cb = circuit_breakers.get(name)
        result.append({
            "name": name,
            "port": info["port"],
            "layer": info["layer"],
            "critical": info["critical"],
            "status": cached.get("status", "unknown"),
            "response_ms": cached.get("response_ms"),
            "http_status": cached.get("http_status"),
            "error": cached.get("error"),
            "circuit_breaker": cb.to_dict() if cb else None,
            "dependencies": SERVICE_DEPENDENCIES.get(name, []),
            "last_check": cached.get("checked_at"),
        })
    return {"services": result, "total": len(result)}


@app.get("/api/v1/services/{service_name}")
async def get_service_detail(service_name: str, auth: AuthContext = Depends(require_admin)):
    """Detailed info for a specific service"""
    if service_name not in SERVICE_REGISTRY:
        raise HTTPException(status_code=404, detail="Service not found")

    info = SERVICE_REGISTRY[service_name]
    cached = service_status_cache.get(service_name, {})
    cb = circuit_breakers.get(service_name)

    # Get recent health history from DB
    history = []
    if db_pool:
        rows = await db_pool.fetch(
            """
            SELECT status, response_ms, error_message, checked_at
            FROM service_health_log
            WHERE service_name = $1
            ORDER BY checked_at DESC LIMIT 50
            """,
            service_name,
        )
        history = [dict(r) for r in rows]

    return {
        "name": service_name,
        "port": info["port"],
        "layer": info["layer"],
        "critical": info["critical"],
        "current_status": cached.get("status", "unknown"),
        "response_ms": cached.get("response_ms"),
        "circuit_breaker": cb.to_dict() if cb else None,
        "dependencies": SERVICE_DEPENDENCIES.get(service_name, []),
        "dependents": [
            s for s, deps in SERVICE_DEPENDENCIES.items() if service_name in deps
        ],
        "recent_history": history,
    }


@app.post("/api/v1/services/{service_name}/reset-circuit")
async def reset_circuit_breaker(service_name: str, auth: AuthContext = Depends(require_admin)):
    """Manually reset a circuit breaker"""
    if service_name not in SERVICE_REGISTRY:
        raise HTTPException(status_code=404, detail="Service not found")
    cb = circuit_breakers.get(service_name)
    if cb:
        cb.state = CircuitState.CLOSED
        cb.failure_count = 0
        logger.info("Circuit breaker reset for %s by %s", service_name, auth.email)
    return {"service": service_name, "circuit_state": "closed", "message": "Circuit breaker reset"}


@app.post("/api/v1/check-now")
async def trigger_health_check(auth: AuthContext = Depends(require_admin)):
    """Manually trigger an immediate health check cycle"""
    await run_health_checks()
    return {"message": "Health check completed", "results": service_status_cache}


# ============================================================================
# UPTIME & SLA
# ============================================================================

@app.get("/api/v1/uptime")
async def get_uptime(
    days: int = Query(default=30, ge=1, le=365),
    service_name: Optional[str] = None,
    auth: AuthContext = Depends(require_admin),
):
    """Get uptime statistics"""
    if not db_pool:
        return {"uptime": [], "message": "Server configuration error"}

    if service_name and service_name not in SERVICE_REGISTRY:
        raise HTTPException(status_code=404, detail="Service not found")

    query = """
        SELECT service_name, date, total_checks, healthy_checks, uptime_pct, avg_response_ms
        FROM uptime_daily
        WHERE date >= CURRENT_DATE - $1::interval
    """
    params: list = [f"{days} days"]

    if service_name:
        query += " AND service_name = $2"
        params.append(service_name)

    query += " ORDER BY date DESC, service_name"
    rows = await db_pool.fetch(query, *params)
    return {"uptime": [dict(r) for r in rows], "days": days}


@app.get("/api/v1/uptime/summary")
async def get_uptime_summary(
    days: int = Query(default=30, ge=1, le=365),
    auth: AuthContext = Depends(require_admin),
):
    """Aggregate uptime summary across all services"""
    if not db_pool:
        return {"summary": {}}

    rows = await db_pool.fetch(
        """
        SELECT service_name,
               ROUND(AVG(uptime_pct)::numeric, 2) as avg_uptime,
               ROUND(AVG(avg_response_ms)::numeric, 2) as avg_response_ms,
               SUM(total_checks) as total_checks
        FROM uptime_daily
        WHERE date >= CURRENT_DATE - $1::interval
        GROUP BY service_name
        ORDER BY avg_uptime ASC
        """,
        f"{days} days",
    )
    return {
        "summary": {r["service_name"]: dict(r) for r in rows},
        "days": days,
        "sla_target": 99.9,
    }


# ============================================================================
# INCIDENTS
# ============================================================================

class IncidentCreate(BaseModel):
    service_name: str
    severity: str = Field(pattern=r"^(critical|high|medium|low)$")
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None


class IncidentUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern=r"^(open|investigating|resolved|closed)$")
    description: Optional[str] = None


@app.get("/api/v1/incidents")
async def list_incidents(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(require_admin),
):
    """List incidents"""
    if not db_pool:
        return {"incidents": []}

    query = "SELECT * FROM incidents WHERE 1=1"
    params: list = []
    idx = 1

    if status_filter:
        if status_filter not in ("open", "investigating", "resolved", "closed"):
            raise HTTPException(status_code=400, detail="Invalid status filter")
        query += f" AND status = ${idx}"
        params.append(status_filter)
        idx += 1

    query += f" ORDER BY opened_at DESC LIMIT ${idx}"
    params.append(limit)

    rows = await db_pool.fetch(query, *params)
    return {"incidents": [dict(r) for r in rows]}


@app.post("/api/v1/incidents")
async def create_incident(body: IncidentCreate, auth: AuthContext = Depends(require_admin)):
    """Manually create an incident"""
    if body.service_name not in SERVICE_REGISTRY:
        raise HTTPException(status_code=400, detail="Unknown service")
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db_pool.fetchrow(
        """
        INSERT INTO incidents (service_name, severity, title, description, tenant_id)
        VALUES ($1, $2, $3, $4, 'platform')
        RETURNING *
        """,
        body.service_name, body.severity, body.title, body.description,
    )
    return {"incident": dict(row)}


@app.put("/api/v1/incidents/{incident_id}")
async def update_incident(incident_id: str, body: IncidentUpdate, auth: AuthContext = Depends(require_admin)):
    """Update incident status"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # Validate UUID format
    try:
        uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    updates = []
    params = []
    idx = 1

    if body.status:
        updates.append(f"status = ${idx}")
        params.append(body.status)
        idx += 1
        if body.status == "resolved":
            updates.append(f"resolved_at = NOW()")
            updates.append(f"resolved_by = ${idx}")
            params.append(auth.email)
            idx += 1

    if body.description:
        updates.append(f"description = ${idx}")
        params.append(body.description)
        idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")

    params.append(incident_id)
    query = f"UPDATE incidents SET {', '.join(updates)} WHERE id = ${idx}::uuid RETURNING *"
    row = await db_pool.fetchrow(query, *params)
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident": dict(row)}


# ============================================================================
# ALERT RULES
# ============================================================================

class AlertRuleCreate(BaseModel):
    service_name: Optional[str] = None
    condition_type: str = Field(pattern=r"^(down|degraded|response_time|circuit_open)$")
    threshold: Optional[float] = None
    notify_channel: str = Field(pattern=r"^(webhook|email|sms)$")
    notify_target: str = Field(min_length=1, max_length=500)


@app.get("/api/v1/alerts/rules")
async def list_alert_rules(auth: AuthContext = Depends(require_admin)):
    if not db_pool:
        return {"rules": []}
    rows = await db_pool.fetch(
        "SELECT * FROM alert_rules WHERE tenant_id = 'platform' ORDER BY created_at DESC"
    )
    return {"rules": [dict(r) for r in rows]}


@app.post("/api/v1/alerts/rules")
async def create_alert_rule(body: AlertRuleCreate, auth: AuthContext = Depends(require_admin)):
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    if body.service_name and body.service_name not in SERVICE_REGISTRY:
        raise HTTPException(status_code=400, detail="Unknown service")

    row = await db_pool.fetchrow(
        """
        INSERT INTO alert_rules (tenant_id, service_name, condition_type, threshold, notify_channel, notify_target)
        VALUES ('platform', $1, $2, $3, $4, $5) RETURNING *
        """,
        body.service_name, body.condition_type, body.threshold, body.notify_channel, body.notify_target,
    )
    return {"rule": dict(row)}


# ============================================================================
# DEPENDENCY GRAPH
# ============================================================================

@app.get("/api/v1/dependency-graph")
async def get_dependency_graph(auth: AuthContext = Depends(require_admin)):
    """Get service dependency graph for visualization"""
    nodes = []
    edges = []
    for name, info in SERVICE_REGISTRY.items():
        cached = service_status_cache.get(name, {})
        nodes.append({
            "id": name,
            "port": info["port"],
            "layer": info["layer"],
            "critical": info["critical"],
            "status": cached.get("status", "unknown"),
        })
    for svc, deps in SERVICE_DEPENDENCIES.items():
        for dep in deps:
            edges.append({"from": dep, "to": svc})

    return {"nodes": nodes, "edges": edges}


# ============================================================================
# WEBSOCKET — Real-time status stream
# ============================================================================

@app.websocket("/ws/status")
async def websocket_status(ws: WebSocket):
    """Real-time health status stream"""
    # Validate JWT_SECRET is configured
    if not JWT_SECRET:
        await ws.close(code=4001, reason="Server configuration error")
        return
    # Validate token from query param
    token = ws.query_params.get("token", "")
    if not token:
        await ws.close(code=4001, reason="Missing authorization token")
        return
    try:
        pyjwt.decode(token, JWT_SECRET, algorithms=["HS256", "RS256"])
    except pyjwt.InvalidTokenError:
        await ws.close(code=4001)
        return

    await ws.accept()
    ws_subscribers.add(ws)

    # Send initial state
    await ws.send_text(json.dumps({
        "type": "initial_state",
        "data": service_status_cache,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    try:
        while True:
            # Keep connection alive, listen for pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        ws_subscribers.discard(ws)


# ============================================================================
# METRICS EXPORT
# ============================================================================

@app.get("/api/v1/metrics")
async def get_metrics(auth: AuthContext = Depends(require_admin)):
    """Prometheus-compatible metrics summary"""
    metrics = {}
    for name, cached in service_status_cache.items():
        metrics[name] = {
            "up": 1 if cached.get("status") == "healthy" else 0,
            "response_ms": cached.get("response_ms", 0),
            "circuit_state": cached.get("circuit_state", "unknown"),
        }

    total = len(SERVICE_REGISTRY)
    healthy = sum(1 for m in metrics.values() if m["up"] == 1)

    return {
        "platform_health_score": round(healthy / total * 100, 1) if total else 0,
        "services_total": total,
        "services_healthy": healthy,
        "services_degraded": sum(1 for s in service_status_cache.values() if s.get("status") == "degraded"),
        "services_down": sum(1 for s in service_status_cache.values() if s.get("status") == "down"),
        "avg_response_ms": round(
            sum(m["response_ms"] for m in metrics.values()) / len(metrics), 2
        ) if metrics else 0,
        "services": metrics,
    }
