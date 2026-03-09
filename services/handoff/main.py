"""
Priya Global AI Sales Platform - Handoff Service
Manages AI-to-human agent transitions with queue management, SLA tracking, and CSAT collection.

Key Features:
- Multi-tenant architecture with Row-Level Security (RLS)
- Intelligent queue management with priority routing
- Skills-based and language-aware agent assignment
- Real-time WebSocket dashboard for agents
- SLA tracking and breach detection
- CSAT collection and analysis
- Configurable handoff triggers per tenant
- Agent-to-agent transfer and escalation
- Conversation context and AI suggestions
- Internal note collaboration system

Port: 9026
Database: PostgreSQL with asyncpg
API Framework: FastAPI with async/await
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum
from uuid import uuid4

import hashlib
import hmac

import asyncpg
import jwt as pyjwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException, Query, Body, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from contextlib import asynccontextmanager
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# ==================== Configuration ====================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD environment variable must be set")
DB_NAME = os.getenv("DB_NAME", "priya")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("CRITICAL: JWT_SECRET environment variable must be set")
SERVICE_PORT = 9026
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# ==================== Enums ====================
class HandoffStatus(str, Enum):
    """Handoff conversation status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    TRANSFERRED = "transferred"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    RETURNED_TO_AI = "returned_to_ai"

class AgentStatus(str, Enum):
    """Agent availability status."""
    ONLINE = "online"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"

class TriggerType(str, Enum):
    """Handoff trigger type."""
    CUSTOMER_REQUEST = "customer_request"
    LOW_CONFIDENCE = "low_confidence"
    SENTIMENT_DROP = "sentiment_drop"
    VIP_CUSTOMER = "vip_customer"
    COMPLEX_QUERY = "complex_query"
    CUSTOM = "custom"

class PriorityLevel(str, Enum):
    """Queue priority level."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

# ==================== Pydantic Models ====================
class HandoffRequest(BaseModel):
    """Request handoff from AI to human agent."""
    conversation_id: str
    customer_id: str
    trigger_type: TriggerType
    reason: Optional[str] = None
    ai_confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    sentiment_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    preferred_language: Optional[str] = "en"
    is_vip: bool = False
    priority_level: Optional[PriorityLevel] = PriorityLevel.NORMAL
    required_skills: Optional[List[str]] = None
    
    @validator('conversation_id', 'customer_id')
    def not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Cannot be empty')
        return v

class HandoffResponse(BaseModel):
    """Response after handoff request."""
    id: str
    conversation_id: str
    customer_id: str
    assigned_agent_id: Optional[str] = None
    status: HandoffStatus
    trigger_type: TriggerType
    queue_position: int
    estimated_wait_time_seconds: int
    created_at: datetime

class AgentInfo(BaseModel):
    """Agent information."""
    id: str
    name: str
    status: AgentStatus
    current_conversations: int
    max_concurrent: int
    is_supervisor: bool
    language_proficiencies: List[str] = ["en"]
    skills: Dict[str, int] = {}
    last_activity: datetime

class AgentStatusUpdate(BaseModel):
    """Update agent status."""
    agent_id: str
    status: AgentStatus
    max_concurrent: int = Field(5, ge=1, le=50)

class InternalNote(BaseModel):
    """Internal collaboration note."""
    note: str = Field(..., min_length=1, max_length=5000)

class HandoffRules(BaseModel):
    """Handoff trigger configuration."""
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)
    sentiment_threshold: float = Field(0.3, ge=0.0, le=1.0)
    first_response_sla_minutes: int = Field(5, ge=1, le=1440)
    resolution_sla_minutes: int = Field(60, ge=5, le=10080)
    enable_vip_auto_route: bool = True
    enable_complex_query_detection: bool = True
    complex_query_keywords: Optional[List[str]] = None
    max_queue_wait_minutes: int = Field(30, ge=5)

class CSATSubmission(BaseModel):
    """Customer satisfaction submission."""
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)

class AgentRegistration(BaseModel):
    """Register new agent."""
    name: str
    language_proficiencies: List[str] = ["en"]
    skills: Dict[str, int] = {}
    is_supervisor: bool = False
    max_concurrent: int = Field(5, ge=1, le=50)

# ==================== Global State ====================
db_pool = None

# ==================== Database Initialization ====================
async def init_db():
    """Initialize database connection pool and create tables with RLS."""
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        min_size=5,
        max_size=20,
        command_timeout=60
    )
    
    async with db_pool.acquire() as conn:
        # Enable UUID extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        
        # Handoff requests table with RLS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handoff_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                conversation_id VARCHAR(255) NOT NULL,
                customer_id VARCHAR(255) NOT NULL,
                assigned_agent_id VARCHAR(255),
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                trigger_type VARCHAR(50) NOT NULL,
                priority_level VARCHAR(20) NOT NULL DEFAULT 'normal',
                reason TEXT,
                ai_confidence_score FLOAT,
                sentiment_score FLOAT,
                preferred_language VARCHAR(10),
                is_vip BOOLEAN DEFAULT FALSE,
                queue_position INT DEFAULT 0,
                required_skills TEXT[],
                created_at TIMESTAMP DEFAULT NOW(),
                assigned_at TIMESTAMP,
                resolved_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(tenant_id, conversation_id)
            );
            CREATE INDEX IF NOT EXISTS idx_handoff_tenant_status 
                ON handoff_requests(tenant_id, status);
            CREATE INDEX IF NOT EXISTS idx_handoff_agent 
                ON handoff_requests(assigned_agent_id);
            CREATE INDEX IF NOT EXISTS idx_handoff_priority
                ON handoff_requests(tenant_id, priority_level, created_at);
        """)
        
        # Agents table with RLS
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id VARCHAR(255) PRIMARY KEY,
                tenant_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'offline',
                current_conversations INT DEFAULT 0,
                max_concurrent INT DEFAULT 5,
                skills JSONB DEFAULT '{}',
                language_proficiencies TEXT[] DEFAULT ARRAY['en'],
                is_supervisor BOOLEAN DEFAULT FALSE,
                last_activity TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(tenant_id, id)
            );
            CREATE INDEX IF NOT EXISTS idx_agents_tenant_status 
                ON agents(tenant_id, status);
            CREATE INDEX IF NOT EXISTS idx_agents_availability
                ON agents(tenant_id, status, current_conversations);
        """)
        
        # Agent notes for internal collaboration
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_notes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                handoff_id UUID NOT NULL,
                agent_id VARCHAR(255) NOT NULL,
                note TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_notes_handoff FOREIGN KEY (handoff_id) REFERENCES handoff_requests(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_notes_handoff 
                ON agent_notes(handoff_id);
            CREATE INDEX IF NOT EXISTS idx_notes_tenant
                ON agent_notes(tenant_id);
        """)
        
        # CSAT responses table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS csat_responses (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                handoff_id UUID NOT NULL,
                rating INT NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(tenant_id, handoff_id),
                CONSTRAINT fk_csat_handoff FOREIGN KEY (handoff_id) REFERENCES handoff_requests(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_csat_tenant 
                ON csat_responses(tenant_id);
        """)
        
        # Handoff rules per tenant
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handoff_rules (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL UNIQUE,
                confidence_threshold FLOAT DEFAULT 0.6,
                sentiment_threshold FLOAT DEFAULT 0.3,
                first_response_sla_minutes INT DEFAULT 5,
                resolution_sla_minutes INT DEFAULT 60,
                enable_vip_auto_route BOOLEAN DEFAULT TRUE,
                enable_complex_query_detection BOOLEAN DEFAULT TRUE,
                complex_query_keywords TEXT[],
                max_queue_wait_minutes INT DEFAULT 30,
                custom_rules JSONB,
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # SLA tracking
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sla_tracking (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                handoff_id UUID NOT NULL,
                first_response_at TIMESTAMP,
                resolved_at TIMESTAMP,
                first_response_breached BOOLEAN DEFAULT FALSE,
                resolution_breached BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(tenant_id, handoff_id),
                CONSTRAINT fk_sla_handoff FOREIGN KEY (handoff_id) REFERENCES handoff_requests(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sla_breaches 
                ON sla_tracking(tenant_id) WHERE first_response_breached OR resolution_breached;
        """)

async def close_db():
    """Close database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()

# ==================== WebSocket Manager ====================
class ConnectionManager:
    """Manage WebSocket connections for real-time agent dashboard."""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.agent_tenant_map: Dict[str, str] = {}

    async def connect(self, agent_id: str, tenant_id: str, websocket: WebSocket):
        """Accept and register WebSocket connection."""
        await websocket.accept()
        if agent_id not in self.active_connections:
            self.active_connections[agent_id] = []
        self.active_connections[agent_id].append(websocket)
        self.agent_tenant_map[agent_id] = tenant_id

    def disconnect(self, agent_id: str, websocket: WebSocket):
        """Unregister WebSocket connection."""
        if agent_id in self.active_connections:
            self.active_connections[agent_id].remove(websocket)
            if not self.active_connections[agent_id]:
                del self.active_connections[agent_id]
                if agent_id in self.agent_tenant_map:
                    del self.agent_tenant_map[agent_id]

    async def broadcast_to_agent(self, agent_id: str, message: dict):
        """Send message to specific agent."""
        if agent_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[agent_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            
            for conn in disconnected:
                self.active_connections[agent_id].remove(conn)

    async def broadcast_to_tenant(self, tenant_id: str, message: dict, agent_ids: List[str]):
        """Broadcast message to all agents in tenant."""
        for agent_id in agent_ids:
            if agent_id in self.agent_tenant_map and self.agent_tenant_map[agent_id] == tenant_id:
                await self.broadcast_to_agent(agent_id, message)

manager = ConnectionManager()

# ==================== Authentication ====================
security = HTTPBearer(auto_error=False)


class AuthContext:
    """Authenticated user context from JWT token."""
    def __init__(self, tenant_id: str, user_id: str, role: str = "agent"):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = role


async def get_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthContext:
    """Validate JWT token and return auth context."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = credentials.credentials
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT secret not configured")

    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256", "RS256"])
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("sub") or payload.get("user_id")
        role = payload.get("role", "agent")

        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return AuthContext(tenant_id=tenant_id, user_id=user_id, role=role)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ==================== Utility Functions ====================

async def get_agent_ids_for_tenant(conn, tenant_id: str) -> List[str]:
    """Get all agent IDs for a tenant."""
    rows = await conn.fetch(
        "SELECT id FROM agents WHERE tenant_id = $1",
        tenant_id
    )
    return [row['id'] for row in rows]

async def calculate_queue_position(conn, handoff_id: str, tenant_id: str, priority_level: str) -> int:
    """Calculate queue position based on priority and creation time."""
    result = await conn.fetchval(
        """
        SELECT COUNT(*) FROM handoff_requests 
        WHERE tenant_id = $1 
            AND status = 'pending'
            AND (priority_level > $2 OR 
                 (priority_level = $2 AND created_at < 
                  (SELECT created_at FROM handoff_requests WHERE id = $3)))
        """,
        tenant_id, priority_level, handoff_id
    )
    return result + 1

async def estimate_wait_time(conn, queue_position: int, tenant_id: str) -> int:
    """Estimate wait time in seconds based on queue and avg resolution."""
    avg_resolution = await conn.fetchval(
        """
        SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - assigned_at))) 
        FROM handoff_requests 
        WHERE tenant_id = $1 AND resolved_at IS NOT NULL AND assigned_at IS NOT NULL
        LIMIT 100
        """,
        tenant_id
    )
    avg_time = int(avg_resolution) if avg_resolution else 300
    return max(queue_position * avg_time // 3, 60)

async def assign_to_best_agent(
    conn, 
    tenant_id: str, 
    language: str = "en",
    required_skills: Optional[List[str]] = None
) -> Optional[str]:
    """Find best available agent using round-robin, skills, and language matching."""
    import re as _re
    if required_skills and len(required_skills) > 0:
        # SECURITY: Validate skill name is alphanumeric+underscore only (no SQL injection)
        skill_name = required_skills[0]
        if not _re.match(r'^[a-zA-Z0-9_\-]{1,100}$', str(skill_name)):
            logger.warning("Invalid skill name rejected: %s", skill_name)
            required_skills = None

    if required_skills:
        agent = await conn.fetchrow(
            """
            SELECT id FROM agents
            WHERE tenant_id = $1
                AND status = 'online'
                AND current_conversations < max_concurrent
                AND ($2 = ANY(language_proficiencies) OR 'en' = ANY(language_proficiencies))
                AND skills -> $3 IS NOT NULL
            ORDER BY current_conversations ASC, last_activity DESC
            LIMIT 1
            """,
            tenant_id, language, required_skills[0]
        )
    else:
        agent = await conn.fetchrow(
            """
            SELECT id FROM agents
            WHERE tenant_id = $1
                AND status = 'online'
                AND current_conversations < max_concurrent
                AND ($2 = ANY(language_proficiencies) OR 'en' = ANY(language_proficiencies))
            ORDER BY current_conversations ASC, last_activity DESC
            LIMIT 1
            """,
            tenant_id, language
        )
    return agent['id'] if agent else None

async def check_sla_breach(conn, tenant_id: str, handoff_id: str):
    """Check and update SLA breach status."""
    handoff = await conn.fetchrow(
        "SELECT assigned_at, resolved_at, status FROM handoff_requests WHERE id = $1 AND tenant_id = $2",
        handoff_id, tenant_id
    )
    
    if not handoff:
        return
    
    rules = await conn.fetchrow(
        "SELECT first_response_sla_minutes, resolution_sla_minutes FROM handoff_rules WHERE tenant_id = $1",
        tenant_id
    )
    
    if not rules:
        return
    
    first_response_breach = False
    resolution_breach = False
    
    if handoff['assigned_at']:
        now = datetime.utcnow()
        response_time = (now - handoff['assigned_at']).total_seconds() / 60
        if response_time > rules['first_response_sla_minutes']:
            first_response_breach = True
    
    if handoff['resolved_at'] and handoff['assigned_at']:
        resolution_time = (handoff['resolved_at'] - handoff['assigned_at']).total_seconds() / 60
        if resolution_time > rules['resolution_sla_minutes']:
            resolution_breach = True
    
    await conn.execute(
        """
        INSERT INTO sla_tracking (tenant_id, handoff_id, first_response_breached, resolution_breached, first_response_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (tenant_id, handoff_id) DO UPDATE SET
            first_response_breached = $3, 
            resolution_breached = $4,
            first_response_at = COALESCE($5, sla_tracking.first_response_at)
        """,
        tenant_id, handoff_id, first_response_breach, resolution_breach, handoff['assigned_at']
    )

# ==================== FastAPI Application ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    await init_db()
    yield
    await close_db()

app = FastAPI(
    title="Priya Handoff Service",
    version="1.0.0",
    description="AI-to-human agent handoff management service",
    lifespan=lifespan
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="handoff")
init_sentry(service_name="handoff", service_port=9026)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="handoff")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# ==================== Handoff Endpoints ====================

@app.post("/api/v1/handoff/request", response_model=HandoffResponse)
async def request_handoff(
    request: HandoffRequest,
    auth: AuthContext = Depends(get_auth)
):
    """Request handoff from AI to human agent with priority routing."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        handoff = await conn.fetchrow(
            """
            INSERT INTO handoff_requests 
            (tenant_id, conversation_id, customer_id, trigger_type, reason, 
             ai_confidence_score, sentiment_score, preferred_language, is_vip, 
             status, priority_level, required_skills)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                status = 'pending', updated_at = NOW()
            RETURNING *
            """,
            tenant_id, request.conversation_id, request.customer_id, 
            request.trigger_type.value, request.reason,
            request.ai_confidence_score, request.sentiment_score,
            request.preferred_language, request.is_vip, 
            HandoffStatus.PENDING.value, request.priority_level.value,
            request.required_skills
        )
        
        queue_pos = await calculate_queue_position(
            conn, handoff['id'], tenant_id, request.priority_level.value
        )
        wait_time = await estimate_wait_time(conn, queue_pos, tenant_id)
        
        await conn.execute(
            "UPDATE handoff_requests SET queue_position = $1 WHERE id = $2",
            queue_pos, handoff['id']
        )
        
        agent_ids = await get_agent_ids_for_tenant(conn, tenant_id)
        await manager.broadcast_to_tenant(
            tenant_id,
            {
                "event": "new_handoff_request",
                "handoff_id": str(handoff['id']),
                "customer_id": request.customer_id,
                "is_vip": request.is_vip,
                "priority_level": request.priority_level.value,
                "queue_position": queue_pos,
                "trigger_type": request.trigger_type.value
            },
            agent_ids
        )
        
        return HandoffResponse(
            id=str(handoff['id']),
            conversation_id=handoff['conversation_id'],
            customer_id=handoff['customer_id'],
            status=HandoffStatus(handoff['status']),
            trigger_type=TriggerType(handoff['trigger_type']),
            queue_position=queue_pos,
            estimated_wait_time_seconds=wait_time,
            created_at=handoff['created_at']
        )

@app.get("/api/v1/handoff/queue")
async def get_queue(
    auth: AuthContext = Depends(get_auth),
    limit: int = Query(50, ge=1, le=500)
):
    """Get current queue for tenant sorted by priority."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        queue = await conn.fetch(
            """
            SELECT id, customer_id, is_vip, queue_position, trigger_type, 
                   priority_level, created_at, ai_confidence_score, sentiment_score
            FROM handoff_requests 
            WHERE tenant_id = $1 AND status = 'pending'
            ORDER BY priority_level DESC, queue_position ASC
            LIMIT $2
            """,
            tenant_id, limit
        )
        
        return {
            "queue_length": len(queue),
            "queue": [dict(row) for row in queue]
        }

@app.post("/api/v1/handoff/assign")
async def assign_handoff(
    handoff_id: str = Query(...),
    agent_id: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Assign conversation to agent (auto or manual)."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        handoff = await conn.fetchrow(
            "SELECT * FROM handoff_requests WHERE id = $1 AND tenant_id = $2",
            handoff_id, tenant_id
        )
        
        if not handoff:
            raise HTTPException(status_code=404, detail="Handoff not found")
        
        if not agent_id:
            agent_id = await assign_to_best_agent(
                conn, tenant_id, handoff['preferred_language'], handoff['required_skills']
            )
        
        if not agent_id:
            raise HTTPException(status_code=503, detail="No available agents")
        
        await conn.execute(
            """
            UPDATE handoff_requests 
            SET assigned_agent_id = $1, status = $2, assigned_at = NOW(), updated_at = NOW()
            WHERE id = $3 AND tenant_id = $4
            """,
            agent_id, HandoffStatus.ASSIGNED.value, handoff_id, tenant_id
        )
        
        await conn.execute(
            "UPDATE agents SET current_conversations = current_conversations + 1 WHERE id = $1 AND tenant_id = $2",
            agent_id, tenant_id
        )
        
        await manager.broadcast_to_agent(
            agent_id,
            {
                "event": "handoff_assigned",
                "handoff_id": handoff_id,
                "customer_id": handoff['customer_id'],
                "conversation_id": handoff['conversation_id'],
                "is_vip": handoff['is_vip'],
                "priority_level": handoff['priority_level']
            }
        )
        
        return {"status": "assigned", "agent_id": agent_id}

@app.put("/api/v1/handoff/{handoff_id}/transfer")
async def transfer_handoff(
    handoff_id: str,
    target_agent_id: str = Query(...),
    auth: AuthContext = Depends(get_auth)
):
    """Transfer conversation to another agent."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        handoff = await conn.fetchrow(
            "SELECT * FROM handoff_requests WHERE id = $1 AND tenant_id = $2",
            handoff_id, tenant_id
        )
        
        if not handoff:
            raise HTTPException(status_code=404, detail="Handoff not found")
        
        if handoff['assigned_agent_id']:
            await conn.execute(
                "UPDATE agents SET current_conversations = current_conversations - 1 WHERE id = $1 AND tenant_id = $2",
                handoff['assigned_agent_id'], tenant_id
            )
        
        await conn.execute(
            """
            UPDATE handoff_requests 
            SET assigned_agent_id = $1, status = $2, updated_at = NOW()
            WHERE id = $3 AND tenant_id = $4
            """,
            target_agent_id, HandoffStatus.TRANSFERRED.value, handoff_id, tenant_id
        )
        
        await conn.execute(
            "UPDATE agents SET current_conversations = current_conversations + 1 WHERE id = $1 AND tenant_id = $2",
            target_agent_id, tenant_id
        )
        
        await manager.broadcast_to_agent(
            target_agent_id,
            {
                "event": "handoff_transferred",
                "handoff_id": handoff_id,
                "customer_id": handoff['customer_id']
            }
        )
        
        return {"status": "transferred", "new_agent_id": target_agent_id}

@app.put("/api/v1/handoff/{handoff_id}/escalate")
async def escalate_handoff(
    handoff_id: str,
    auth: AuthContext = Depends(get_auth)
):
    """Escalate conversation to supervisor."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        supervisor = await conn.fetchrow(
            """
            SELECT id FROM agents 
            WHERE tenant_id = $1 AND is_supervisor = TRUE AND status = 'online'
            ORDER BY current_conversations ASC
            LIMIT 1
            """,
            tenant_id
        )
        
        if not supervisor:
            raise HTTPException(status_code=503, detail="No supervisors available")
        
        handoff = await conn.fetchrow(
            "SELECT assigned_agent_id FROM handoff_requests WHERE id = $1 AND tenant_id = $2",
            handoff_id, tenant_id
        )
        
        if handoff['assigned_agent_id']:
            await conn.execute(
                "UPDATE agents SET current_conversations = current_conversations - 1 WHERE id = $1 AND tenant_id = $2",
                handoff['assigned_agent_id'], tenant_id
            )
        
        await conn.execute(
            """
            UPDATE handoff_requests 
            SET assigned_agent_id = $1, status = $2, updated_at = NOW()
            WHERE id = $3 AND tenant_id = $4
            """,
            supervisor['id'], HandoffStatus.ESCALATED.value, handoff_id, tenant_id
        )
        
        await conn.execute(
            "UPDATE agents SET current_conversations = current_conversations + 1 WHERE id = $1 AND tenant_id = $2",
            supervisor['id'], tenant_id
        )
        
        return {"status": "escalated", "supervisor_id": supervisor['id']}

@app.put("/api/v1/handoff/{handoff_id}/resolve")
async def resolve_handoff(
    handoff_id: str,
    auth: AuthContext = Depends(get_auth)
):
    """Resolve/close handoff conversation."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        handoff = await conn.fetchrow(
            "SELECT assigned_agent_id FROM handoff_requests WHERE id = $1 AND tenant_id = $2",
            handoff_id, tenant_id
        )
        
        if not handoff:
            raise HTTPException(status_code=404, detail="Handoff not found")
        
        await conn.execute(
            """
            UPDATE handoff_requests 
            SET status = $1, resolved_at = NOW(), updated_at = NOW()
            WHERE id = $2 AND tenant_id = $3
            """,
            HandoffStatus.RESOLVED.value, handoff_id, tenant_id
        )
        
        if handoff['assigned_agent_id']:
            await conn.execute(
                "UPDATE agents SET current_conversations = current_conversations - 1 WHERE id = $1 AND tenant_id = $2",
                handoff['assigned_agent_id'], tenant_id
            )
        
        await check_sla_breach(conn, tenant_id, handoff_id)
        
        return {"status": "resolved", "handoff_id": handoff_id}

@app.put("/api/v1/handoff/{handoff_id}/return-to-ai")
async def return_to_ai(
    handoff_id: str,
    auth: AuthContext = Depends(get_auth)
):
    """Return conversation to AI for continued handling."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        handoff = await conn.fetchrow(
            "SELECT assigned_agent_id FROM handoff_requests WHERE id = $1 AND tenant_id = $2",
            handoff_id, tenant_id
        )
        
        if not handoff:
            raise HTTPException(status_code=404, detail="Handoff not found")
        
        await conn.execute(
            """
            UPDATE handoff_requests 
            SET status = $1, assigned_agent_id = NULL, updated_at = NOW()
            WHERE id = $2 AND tenant_id = $3
            """,
            HandoffStatus.RETURNED_TO_AI.value, handoff_id, tenant_id
        )
        
        if handoff['assigned_agent_id']:
            await conn.execute(
                "UPDATE agents SET current_conversations = current_conversations - 1 WHERE id = $1 AND tenant_id = $2",
                handoff['assigned_agent_id'], tenant_id
            )
        
        return {"status": "returned_to_ai", "handoff_id": handoff_id}

# ==================== Agent Management ====================

@app.post("/api/v1/handoff/agents/register")
async def register_agent(
    agent: AgentRegistration,
    agent_id: str = Query(...),
    auth: AuthContext = Depends(get_auth)
):
    """Register new agent for tenant."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agents (id, tenant_id, name, language_proficiencies, skills, is_supervisor, max_concurrent)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET
                name = $3, 
                language_proficiencies = $4,
                skills = $5,
                max_concurrent = $7
            """,
            agent_id, tenant_id, agent.name, agent.language_proficiencies,
            json.dumps(agent.skills), agent.is_supervisor, agent.max_concurrent
        )
        
        return {"agent_id": agent_id, "status": "registered"}

@app.get("/api/v1/handoff/agents/status")
async def get_agents_status(auth: AuthContext = Depends(get_auth)):
    """Get all agents' status and availability."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        agents = await conn.fetch(
            """
            SELECT id, name, status, current_conversations, max_concurrent, 
                   is_supervisor, language_proficiencies, skills, last_activity
            FROM agents 
            WHERE tenant_id = $1
            ORDER BY status DESC, current_conversations ASC
            """,
            tenant_id
        )
        
        return {
            "total_agents": len(agents),
            "agents": [dict(row) for row in agents]
        }

@app.put("/api/v1/handoff/agents/status")
async def update_agent_status(
    update: AgentStatusUpdate,
    auth: AuthContext = Depends(get_auth)
):
    """Update agent status (online, busy, away, offline)."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE agents 
            SET status = $1, max_concurrent = $2, last_activity = NOW()
            WHERE id = $3 AND tenant_id = $4
            """,
            update.status.value, update.max_concurrent, update.agent_id, tenant_id
        )
        
        await manager.broadcast_to_agent(
            update.agent_id,
            {"event": "status_updated", "status": update.status.value}
        )
        
        return {"status": "updated", "agent_id": update.agent_id}

# ==================== Notes and Context ====================

@app.post("/api/v1/handoff/{handoff_id}/notes")
async def add_internal_note(
    handoff_id: str,
    note_data: InternalNote,
    agent_id: str = Query(...),
    auth: AuthContext = Depends(get_auth)
):
    """Add internal collaboration note."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        note_id = await conn.fetchval(
            """
            INSERT INTO agent_notes (tenant_id, handoff_id, agent_id, note)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            tenant_id, handoff_id, agent_id, note_data.note
        )
        
        agent_ids = await get_agent_ids_for_tenant(conn, tenant_id)
        await manager.broadcast_to_tenant(
            tenant_id,
            {
                "event": "note_added",
                "handoff_id": handoff_id,
                "agent_id": agent_id,
                "note": note_data.note[:100]
            },
            agent_ids
        )
        
        return {"note_id": str(note_id), "created_at": datetime.utcnow()}

@app.get("/api/v1/handoff/{handoff_id}/context")
async def get_conversation_context(
    handoff_id: str,
    auth: AuthContext = Depends(get_auth)
):
    """Get conversation context with AI summary and history."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        handoff = await conn.fetchrow(
            """
            SELECT id, conversation_id, customer_id, trigger_type, reason, 
                   ai_confidence_score, sentiment_score, created_at, assigned_at
            FROM handoff_requests 
            WHERE id = $1 AND tenant_id = $2
            """,
            handoff_id, tenant_id
        )
        
        if not handoff:
            raise HTTPException(status_code=404, detail="Handoff not found")
        
        notes = await conn.fetch(
            """
            SELECT agent_id, note, created_at FROM agent_notes 
            WHERE handoff_id = $1 ORDER BY created_at DESC LIMIT 50
            """,
            handoff_id
        )
        
        return {
            "handoff": dict(handoff),
            "internal_notes": [dict(note) for note in notes],
            "ai_summary": f"Customer {handoff['customer_id']} initiated {handoff['trigger_type']} handoff. Confidence: {handoff['ai_confidence_score']}, Sentiment: {handoff['sentiment_score']}"
        }

@app.post("/api/v1/handoff/{handoff_id}/suggest")
async def get_ai_suggestion(
    handoff_id: str,
    auth: AuthContext = Depends(get_auth)
):
    """Get AI-suggested response for agent assist."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        handoff = await conn.fetchrow(
            "SELECT conversation_id, customer_id, sentiment_score FROM handoff_requests WHERE id = $1 AND tenant_id = $2",
            handoff_id, tenant_id
        )
        
        if not handoff:
            raise HTTPException(status_code=404, detail="Handoff not found")
    
    suggestion = "Thank you for your patience. An agent is now assisting you with your query."
    if handoff['sentiment_score'] and handoff['sentiment_score'] < 0.3:
        suggestion = "I sincerely apologize for any inconvenience. I'm here to help resolve your issue immediately."
    
    return {
        "suggestion": suggestion,
        "confidence": 0.85,
        "conversation_id": handoff['conversation_id']
    }

# ==================== CSAT & Feedback ====================

@app.post("/api/v1/handoff/{handoff_id}/csat")
async def submit_csat(
    handoff_id: str,
    csat: CSATSubmission,
    auth: AuthContext = Depends(get_auth)
):
    """Submit CSAT rating and comment post-handoff."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        csat_id = await conn.fetchval(
            """
            INSERT INTO csat_responses (tenant_id, handoff_id, rating, comment)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            tenant_id, handoff_id, csat.rating, csat.comment
        )
        
        return {"csat_id": str(csat_id), "rating": csat.rating, "submitted_at": datetime.utcnow()}

# ==================== SLA & Metrics ====================

@app.get("/api/v1/handoff/sla/breaches")
async def get_sla_breaches(
    auth: AuthContext = Depends(get_auth),
    limit: int = Query(50, ge=1, le=500)
):
    """Get SLA breaches for tenant."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        breaches = await conn.fetch(
            """
            SELECT s.handoff_id, h.customer_id, h.assigned_at, h.resolved_at,
                   s.first_response_breached, s.resolution_breached,
                   EXTRACT(EPOCH FROM (h.resolved_at - h.assigned_at))/60 as resolution_minutes
            FROM sla_tracking s
            JOIN handoff_requests h ON s.handoff_id = h.id
            WHERE s.tenant_id = $1 AND (s.first_response_breached OR s.resolution_breached)
            ORDER BY s.created_at DESC
            LIMIT $2
            """,
            tenant_id, limit
        )
        
        return {"breaches": [dict(row) for row in breaches]}

@app.put("/api/v1/handoff/rules")
async def update_handoff_rules(
    rules: HandoffRules,
    auth: AuthContext = Depends(get_auth)
):
    """Update handoff trigger rules per tenant."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO handoff_rules 
            (tenant_id, confidence_threshold, sentiment_threshold, 
             first_response_sla_minutes, resolution_sla_minutes,
             enable_vip_auto_route, enable_complex_query_detection,
             complex_query_keywords, max_queue_wait_minutes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (tenant_id) DO UPDATE SET
                confidence_threshold = $2,
                sentiment_threshold = $3,
                first_response_sla_minutes = $4,
                resolution_sla_minutes = $5,
                enable_vip_auto_route = $6,
                enable_complex_query_detection = $7,
                complex_query_keywords = $8,
                max_queue_wait_minutes = $9,
                updated_at = NOW()
            """,
            tenant_id, rules.confidence_threshold, rules.sentiment_threshold,
            rules.first_response_sla_minutes, rules.resolution_sla_minutes,
            rules.enable_vip_auto_route, rules.enable_complex_query_detection,
            rules.complex_query_keywords, rules.max_queue_wait_minutes
        )
        
        return {"status": "rules_updated"}

@app.get("/api/v1/handoff/metrics")
async def get_handoff_metrics(
    auth: AuthContext = Depends(get_auth),
    days: int = Query(7, ge=1, le=90)
):
    """Get handoff performance metrics."""
    tenant_id = auth.tenant_id
    
    async with db_pool.acquire() as conn:
        total_handoffs = await conn.fetchval(
            "SELECT COUNT(*) FROM handoff_requests WHERE tenant_id = $1",
            tenant_id
        )
        
        resolved = await conn.fetchval(
            "SELECT COUNT(*) FROM handoff_requests WHERE tenant_id = $1 AND status = 'resolved'",
            tenant_id
        )
        
        avg_resolution_time = await conn.fetchval(
            """
            SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - assigned_at))) / 60 
            FROM handoff_requests 
            WHERE tenant_id = $1 AND resolved_at IS NOT NULL AND assigned_at IS NOT NULL
            """,
            tenant_id
        )
        
        avg_csat = await conn.fetchval(
            "SELECT AVG(rating) FROM csat_responses WHERE tenant_id = $1",
            tenant_id
        )
        
        pending_count = await conn.fetchval(
            "SELECT COUNT(*) FROM handoff_requests WHERE tenant_id = $1 AND status = 'pending'",
            tenant_id
        )
        
        vip_count = await conn.fetchval(
            "SELECT COUNT(*) FROM handoff_requests WHERE tenant_id = $1 AND is_vip = TRUE",
            tenant_id
        )
        
        return {
            "total_handoffs": total_handoffs,
            "resolved_count": resolved,
            "pending_count": pending_count,
            "vip_count": vip_count,
            "avg_resolution_time_minutes": round(avg_resolution_time, 2) if avg_resolution_time else 0,
            "avg_csat": round(avg_csat, 2) if avg_csat else 0,
            "resolution_rate_percent": round((resolved / total_handoffs * 100) if total_handoffs else 0, 2)
        }

# ==================== WebSocket ====================

@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket, agent_id: str = Query(...), token: str = Query(...)):
    """Real-time agent dashboard WebSocket with JWT validation."""
    # Validate JWT from query param (browser WebSocket API limitation)
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        await websocket.close(code=1008)
        return
    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256", "RS256"])
        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return
    await manager.connect(agent_id, tenant_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("action") == "ping":
                await websocket.send_json({
                    "action": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            elif message.get("action") == "status_update":
                await manager.broadcast_to_agent(
                    agent_id,
                    {"event": "agent_online", "agent_id": agent_id}
                )
    except WebSocketDisconnect:
        manager.disconnect(agent_id, websocket)

# ==================== Health & Status ====================

@app.get("/api/v1/handoff/health")
async def health_check():
    """Health check endpoint."""
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {
            "status": "healthy",
            "service": "handoff",
            "port": SERVICE_PORT,
            "environment": ENVIRONMENT,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "handoff",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

# ==================== Main Entry Point ====================
if __name__ == "__main__":
    import uvicorn


    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SERVICE_PORT,
        workers=4 if ENVIRONMENT == "production" else 1
    )
