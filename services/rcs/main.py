"""
RCS (Rich Communication Services) Messaging Service
Multi-tenant SaaS FastAPI application with JWT auth, tenant RLS, and Google RBM integration
"""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
import asyncpg
from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
    Header,
    Request,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# ==================== Configuration & Setup ====================

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/rcs_db")
SECRET_KEY = os.getenv("SECRET_KEY")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
GOOGLE_RBM_API_KEY = os.getenv("GOOGLE_RBM_API_KEY")
GOOGLE_RBM_PROJECT_ID = os.getenv("GOOGLE_RBM_PROJECT_ID")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
SMS_FALLBACK_ENABLED = os.getenv("SMS_FALLBACK_ENABLED", "true").lower() == "true"

if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")

import sys
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

security = HTTPBearer()
app = FastAPI(title="RCS Messaging Service", version="1.0.0")

# Initialize Sentry error tracking
event_bus = EventBus(service_name="rcs")
init_sentry(service_name="rcs", service_port=9033)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="rcs")
app.add_middleware(TracingMiddleware)

# CORS Configuration
if "*" in ALLOWED_ORIGINS:
    print("ERROR: CORS_ORIGINS contains wildcard (*). This is a security risk.", file=sys.stderr)
    ALLOWED_ORIGINS = ["http://localhost:3000"]

cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# ==================== Global State ====================

db_pool: Optional[asyncpg.Pool] = None


# ==================== Lifespan & Database ====================

async def init_db():
    """Initialize database pool and create tables"""
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)

    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rcs_agents (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id),
                agent_name VARCHAR(255) NOT NULL,
                brand_name VARCHAR(255) NOT NULL,
                agent_id VARCHAR(255) UNIQUE NOT NULL,
                verification_status VARCHAR(50) DEFAULT 'pending',
                verified_at TIMESTAMP,
                rbm_api_enabled BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rcs_messages (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id),
                agent_id UUID NOT NULL REFERENCES rcs_agents(id),
                recipient_phone VARCHAR(20) NOT NULL,
                message_type VARCHAR(50) NOT NULL,
                content JSONB NOT NULL,
                delivery_status VARCHAR(50) DEFAULT 'queued',
                read_receipt BOOLEAN DEFAULT false,
                message_id VARCHAR(255),
                fallback_to_sms BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivered_at TIMESTAMP,
                read_at TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rcs_templates (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id),
                template_name VARCHAR(255) NOT NULL,
                template_body TEXT NOT NULL,
                variables JSONB DEFAULT '[]',
                status VARCHAR(50) DEFAULT 'draft',
                approved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rcs_analytics (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id),
                metric_type VARCHAR(100) NOT NULL,
                metric_value INTEGER NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rcs_messages_tenant ON rcs_messages(tenant_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rcs_agents_tenant ON rcs_agents(tenant_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rcs_templates_tenant ON rcs_templates(tenant_id);
        """)


async def close_db():
    """Close database pool"""
    global db_pool
    if db_pool:
        await db_pool.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    await init_db()
    yield
    await close_db()


app.router.lifespan_context = lifespan

# ==================== Models ====================


class AuthContext(BaseModel):
    """JWT authentication context"""
    tenant_id: str
    user_id: str
    exp: int


class SendRCSRequest(BaseModel):
    agent_id: str
    recipient_phone: str
    text: str


class SendRichCardRequest(BaseModel):
    agent_id: str
    recipient_phone: str
    title: str
    description: str
    media_url: Optional[str] = None
    suggested_replies: list[str] = Field(default_factory=list)


class SendCarouselRequest(BaseModel):
    agent_id: str
    recipient_phone: str
    cards: list[dict[str, Any]]


class RegisterAgentRequest(BaseModel):
    agent_name: str
    brand_name: str


class TemplateRequest(BaseModel):
    template_name: str
    template_body: str
    variables: list[str] = Field(default_factory=list)


class CapabilityRequest(BaseModel):
    phone_number: str


class WebhookRequest(BaseModel):
    messageId: str
    conversationId: str
    recipientId: str
    eventType: str
    timestamp: str
    deliveryStatus: Optional[str] = None
    readStatus: Optional[str] = None


# ==================== JWT Authentication ====================


def verify_token(credentials: HTTPAuthorizationCredentials) -> AuthContext:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        exp = payload.get("exp")

        if not tenant_id or not user_id or not exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
            )

        return AuthContext(tenant_id=tenant_id, user_id=user_id, exp=exp)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext:
    """Dependency to get authenticated context"""
    return verify_token(credentials)


# ==================== Database Helpers ====================


async def get_db_connection():
    """Get database connection from pool"""
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return await db_pool.acquire()


async def verify_tenant_agent(
    conn: asyncpg.Connection,
    tenant_id: str,
    agent_id: str,
) -> bool:
    """Verify agent belongs to tenant (RLS)"""
    result = await conn.fetchval(
        "SELECT id FROM rcs_agents WHERE id = $1 AND tenant_id = $2",
        uuid.UUID(agent_id),
        uuid.UUID(tenant_id),
    )
    return result is not None


async def verify_tenant_template(
    conn: asyncpg.Connection,
    tenant_id: str,
    template_id: str,
) -> bool:
    """Verify template belongs to tenant (RLS)"""
    result = await conn.fetchval(
        "SELECT id FROM rcs_templates WHERE id = $1 AND tenant_id = $2",
        uuid.UUID(template_id),
        uuid.UUID(tenant_id),
    )
    return result is not None


async def record_metric(
    conn: asyncpg.Connection,
    tenant_id: str,
    metric_type: str,
    value: int = 1,
):
    """Record analytics metric"""
    await conn.execute(
        """
        INSERT INTO rcs_analytics (id, tenant_id, metric_type, metric_value)
        VALUES ($1, $2, $3, $4)
        """,
        uuid.uuid4(),
        uuid.UUID(tenant_id),
        metric_type,
        value,
    )


# ==================== RCS Integration Helpers ====================


async def check_rcs_capability(phone_number: str) -> bool:
    """Check if phone number supports RCS (mock implementation)"""
    # In production, this would call Google RBM API
    # For now, return based on phone number pattern
    return len(phone_number) >= 10 and phone_number.isdigit()


async def send_to_google_rbm(
    agent_id: str,
    recipient_phone: str,
    content: dict[str, Any],
) -> Optional[str]:
    """Send message to Google RBM API"""
    # Mock implementation - in production, use google-rcs library
    if not GOOGLE_RBM_API_KEY or not GOOGLE_RBM_PROJECT_ID:
        return None

    # Simulate API call
    message_id = f"rbm_{hashlib.md5(f'{agent_id}{recipient_phone}{datetime.now().isoformat()}'.encode()).hexdigest()[:16]}"
    return message_id


async def send_sms_fallback(
    recipient_phone: str,
    text: str,
) -> Optional[str]:
    """Send SMS fallback (mock implementation)"""
    if not SMS_FALLBACK_ENABLED:
        return None

    # Mock SMS sending
    message_id = f"sms_{hashlib.md5(f'{recipient_phone}{text}{datetime.now().isoformat()}'.encode()).hexdigest()[:16]}"
    return message_id


async def substitute_template_variables(
    template: str,
    variables: dict[str, str],
) -> str:
    """Substitute variables in template"""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


# ==================== Endpoints ====================


@app.post("/rcs/send")
async def send_rcs_message(
    request: SendRCSRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Send RCS text message with fallback to SMS"""
    conn = await get_db_connection()
    try:
        # Verify agent belongs to tenant
        if not await verify_tenant_agent(conn, auth.tenant_id, request.agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")

        # Check RCS capability
        supports_rcs = await check_rcs_capability(request.recipient_phone)

        message_id = str(uuid.uuid4())
        content = {"type": "text", "body": request.text}
        fallback_used = False
        delivery_status = "queued"
        rbm_message_id = None

        if supports_rcs:
            rbm_message_id = await send_to_google_rbm(
                request.agent_id,
                request.recipient_phone,
                content,
            )
            if rbm_message_id:
                delivery_status = "sent"
        else:
            # Fallback to SMS
            if SMS_FALLBACK_ENABLED:
                sms_id = await send_sms_fallback(request.recipient_phone, request.text)
                if sms_id:
                    fallback_used = True
                    delivery_status = "sent"
                    rbm_message_id = sms_id

        # Store message in database
        await conn.execute(
            """
            INSERT INTO rcs_messages
            (id, tenant_id, agent_id, recipient_phone, message_type, content,
             delivery_status, message_id, fallback_to_sms, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            uuid.UUID(message_id),
            uuid.UUID(auth.tenant_id),
            uuid.UUID(request.agent_id),
            request.recipient_phone,
            "text",
            json.dumps(content),
            delivery_status,
            rbm_message_id,
            fallback_used,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )

        await record_metric(conn, auth.tenant_id, "messages_sent")
        if fallback_used:
            await record_metric(conn, auth.tenant_id, "sms_fallbacks_used")

        return {
            "message_id": message_id,
            "status": delivery_status,
            "fallback_used": fallback_used,
            "supports_rcs": supports_rcs,
        }
    finally:
        await db_pool.release(conn)


@app.post("/rcs/send-rich-card")
async def send_rich_card(
    request: SendRichCardRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Send RCS rich card with media, title, and suggested replies"""
    conn = await get_db_connection()
    try:
        if not await verify_tenant_agent(conn, auth.tenant_id, request.agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")

        message_id = str(uuid.uuid4())
        content = {
            "type": "rich_card",
            "title": request.title,
            "description": request.description,
            "media_url": request.media_url,
            "suggested_replies": request.suggested_replies,
        }

        rbm_message_id = await send_to_google_rbm(
            request.agent_id,
            request.recipient_phone,
            content,
        )

        await conn.execute(
            """
            INSERT INTO rcs_messages
            (id, tenant_id, agent_id, recipient_phone, message_type, content,
             delivery_status, message_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            uuid.UUID(message_id),
            uuid.UUID(auth.tenant_id),
            uuid.UUID(request.agent_id),
            request.recipient_phone,
            "rich_card",
            json.dumps(content),
            "sent" if rbm_message_id else "queued",
            rbm_message_id,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )

        await record_metric(conn, auth.tenant_id, "rich_cards_sent")

        return {
            "message_id": message_id,
            "status": "sent" if rbm_message_id else "queued",
        }
    finally:
        await db_pool.release(conn)


@app.post("/rcs/send-carousel")
async def send_carousel(
    request: SendCarouselRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Send RCS carousel with multiple cards"""
    conn = await get_db_connection()
    try:
        if not await verify_tenant_agent(conn, auth.tenant_id, request.agent_id):
            raise HTTPException(status_code=404, detail="Agent not found")

        message_id = str(uuid.uuid4())
        content = {
            "type": "carousel",
            "cards": request.cards,
        }

        rbm_message_id = await send_to_google_rbm(
            request.agent_id,
            request.recipient_phone,
            content,
        )

        await conn.execute(
            """
            INSERT INTO rcs_messages
            (id, tenant_id, agent_id, recipient_phone, message_type, content,
             delivery_status, message_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            uuid.UUID(message_id),
            uuid.UUID(auth.tenant_id),
            uuid.UUID(request.agent_id),
            request.recipient_phone,
            "carousel",
            json.dumps(content),
            "sent" if rbm_message_id else "queued",
            rbm_message_id,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )

        await record_metric(conn, auth.tenant_id, "carousels_sent")

        return {
            "message_id": message_id,
            "status": "sent" if rbm_message_id else "queued",
        }
    finally:
        await db_pool.release(conn)


@app.get("/rcs/messages")
async def get_messages(
    auth: AuthContext = Depends(get_auth_context),
    skip: int = 0,
    limit: int = 50,
):
    """Get RCS messages for tenant"""
    conn = await get_db_connection()
    try:
        messages = await conn.fetch(
            """
            SELECT id, agent_id, recipient_phone, message_type, content,
                   delivery_status, read_receipt, created_at, updated_at,
                   fallback_to_sms
            FROM rcs_messages
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            uuid.UUID(auth.tenant_id),
            limit,
            skip,
        )

        return {
            "messages": [dict(msg) for msg in messages],
            "count": len(messages),
        }
    finally:
        await db_pool.release(conn)


@app.post("/rcs/webhooks/google")
async def handle_google_webhook(request: WebhookRequest, x_webhook_signature: Optional[str] = Header(None)):
    """Handle Google RBM webhook for delivery/read receipts"""
    # Webhook from Google RBM API - validate signature
    if not x_webhook_signature or x_webhook_signature != GOOGLE_RBM_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    conn = await get_db_connection()
    try:
        # Find message by RBM message ID
        message = await conn.fetchrow(
            "SELECT id, tenant_id FROM rcs_messages WHERE message_id = $1",
            request.messageId,
        )

        if not message:
            return {"status": "message_not_found"}

        update_data = {"updated_at": datetime.now(timezone.utc)}

        if request.eventType == "DELIVERY_ACK":
            update_data["delivery_status"] = "delivered"
            update_data["delivered_at"] = datetime.fromisoformat(request.timestamp)
            await record_metric(conn, str(message["tenant_id"]), "messages_delivered")

        elif request.eventType == "READ":
            update_data["read_receipt"] = True
            update_data["read_at"] = datetime.fromisoformat(request.timestamp)
            await record_metric(conn, str(message["tenant_id"]), "messages_read")

        # Update message status
        await conn.execute(
            """
            UPDATE rcs_messages
            SET delivery_status = $1, read_receipt = $2,
                delivered_at = $3, read_at = $4, updated_at = $5
            WHERE id = $6
            """,
            update_data.get("delivery_status"),
            update_data.get("read_receipt"),
            update_data.get("delivered_at"),
            update_data.get("read_at"),
            update_data["updated_at"],
            message["id"],
        )

        return {"status": "processed"}
    finally:
        await db_pool.release(conn)


@app.post("/rcs/templates")
async def create_template(
    request: TemplateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Create RCS message template"""
    conn = await get_db_connection()
    try:
        template_id = str(uuid.uuid4())

        await conn.execute(
            """
            INSERT INTO rcs_templates
            (id, tenant_id, template_name, template_body, variables,
             status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            uuid.UUID(template_id),
            uuid.UUID(auth.tenant_id),
            request.template_name,
            request.template_body,
            json.dumps(request.variables),
            "draft",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )

        await record_metric(conn, auth.tenant_id, "templates_created")

        return {
            "template_id": template_id,
            "status": "draft",
        }
    finally:
        await db_pool.release(conn)


@app.get("/rcs/templates")
async def get_templates(
    auth: AuthContext = Depends(get_auth_context),
    skip: int = 0,
    limit: int = 50,
):
    """Get RCS templates for tenant"""
    conn = await get_db_connection()
    try:
        templates = await conn.fetch(
            """
            SELECT id, template_name, template_body, variables, status,
                   created_at, updated_at, approved_at
            FROM rcs_templates
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            uuid.UUID(auth.tenant_id),
            limit,
            skip,
        )

        return {
            "templates": [dict(t) for t in templates],
            "count": len(templates),
        }
    finally:
        await db_pool.release(conn)


@app.post("/rcs/agents/register")
async def register_agent(
    request: RegisterAgentRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    """Register RCS agent for tenant"""
    conn = await get_db_connection()
    try:
        agent_id = str(uuid.uuid4())
        unique_agent_id = f"agent_{hashlib.md5(f'{auth.tenant_id}{agent_id}'.encode()).hexdigest()[:12]}"

        await conn.execute(
            """
            INSERT INTO rcs_agents
            (id, tenant_id, agent_name, brand_name, agent_id,
             verification_status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            uuid.UUID(agent_id),
            uuid.UUID(auth.tenant_id),
            request.agent_name,
            request.brand_name,
            unique_agent_id,
            "pending",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )

        await record_metric(conn, auth.tenant_id, "agents_registered")

        return {
            "agent_id": agent_id,
            "unique_agent_id": unique_agent_id,
            "status": "pending",
        }
    finally:
        await db_pool.release(conn)


@app.get("/rcs/capability/{phone}")
async def check_capability(
    phone: str,
    auth: AuthContext = Depends(get_auth_context),
):
    """Check if phone number supports RCS"""
    supports_rcs = await check_rcs_capability(phone)

    return {
        "phone_number": phone,
        "supports_rcs": supports_rcs,
        "fallback_available": SMS_FALLBACK_ENABLED,
    }


@app.get("/rcs/analytics")
async def get_analytics(
    auth: AuthContext = Depends(get_auth_context),
    metric_type: Optional[str] = None,
    hours: int = 24,
):
    """Get analytics for tenant"""
    conn = await get_db_connection()
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = """
            SELECT metric_type, SUM(metric_value) as total
            FROM rcs_analytics
            WHERE tenant_id = $1 AND recorded_at >= $2
        """
        params = [uuid.UUID(auth.tenant_id), since]

        if metric_type:
            query += " AND metric_type = $3"
            params.append(metric_type)

        query += " GROUP BY metric_type ORDER BY total DESC"

        analytics = await conn.fetch(query, *params)

        return {
            "analytics": [dict(a) for a in analytics],
            "time_period_hours": hours,
        }
    finally:
        await db_pool.release(conn)


@app.get("/rcs/health")
async def health_check():
    """Health check endpoint"""
    if not db_pool:
        return {
            "status": "unhealthy",
            "database": "not_initialized",
        }

    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }


# ==================== Root Endpoint ====================


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "RCS Messaging Service",
        "version": "1.0.0",
        "endpoints": {
            "send_message": "POST /rcs/send",
            "send_rich_card": "POST /rcs/send-rich-card",
            "send_carousel": "POST /rcs/send-carousel",
            "get_messages": "GET /rcs/messages",
            "google_webhook": "POST /rcs/webhooks/google",
            "create_template": "POST /rcs/templates",
            "get_templates": "GET /rcs/templates",
            "register_agent": "POST /rcs/agents/register",
            "check_capability": "GET /rcs/capability/{phone}",
            "get_analytics": "GET /rcs/analytics",
            "health": "GET /rcs/health",
        },
    }


if __name__ == "__main__":
    import uvicorn



    port = int(os.getenv("PORT", "9033"))
    uvicorn.run(app, host="0.0.0.0", port=port)
