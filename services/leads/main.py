import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from enum import Enum

import asyncpg
import jwt
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from contextlib import asynccontextmanager
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
PORT = 9027
ALGORITHM = "HS256"
SCORE_DECAY_RATE = 0.95  # Weekly decay factor
MIN_SCORE = 0
MAX_SCORE = 100

# Enums for pipeline and grades
class PipelineStage(str, Enum):
    NEW = "New"
    QUALIFIED = "Qualified"
    PROPOSAL = "Proposal"
    NEGOTIATION = "Negotiation"
    WON = "Won"
    LOST = "Lost"

class LeadGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"

class LeadChannel(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    WEB = "web"
    PHONE = "phone"
    REFERRAL = "referral"
    LINKEDIN = "linkedin"

# Pydantic Models
class AuthContext:
    def __init__(self, tenant_id: str, user_id: str, user_email: str):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.user_email = user_email

class LeadScoreRequest(BaseModel):
    engagement_score: float = Field(0, ge=0, le=100)
    demographic_score: float = Field(0, ge=0, le=100)
    behavior_score: float = Field(0, ge=0, le=100)
    intent_score: float = Field(0, ge=0, le=100)
    custom_factors: Optional[Dict[str, float]] = {}

class LeadCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    source_channel: LeadChannel
    initial_score: Optional[float] = 0
    custom_data: Optional[Dict[str, Any]] = {}
    
    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower()

class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    custom_data: Optional[Dict[str, Any]] = None

class LeadResponse(BaseModel):
    lead_id: str
    tenant_id: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    company: Optional[str]
    current_score: float
    lead_grade: str
    pipeline_stage: str
    source_channel: str
    assigned_to: Optional[str]
    deal_value: Optional[float]
    win_probability: Optional[float]
    created_at: datetime
    updated_at: datetime

class PipelineStageConfig(BaseModel):
    stage_name: str
    order: int
    stage_gate_requirements: Optional[Dict[str, Any]] = {}
    auto_advance: bool = False

class PipelineConfig(BaseModel):
    tenant_id: str
    stages: List[PipelineStageConfig]

class AdvancePipelineRequest(BaseModel):
    lead_id: str
    new_stage: str
    deal_value: Optional[float] = None
    win_probability: Optional[float] = Field(None, ge=0, le=1)

class AssignLeadRequest(BaseModel):
    lead_id: str
    assigned_to: str
    assignment_method: str = "manual"  # round-robin, skills-based, territory, manual

class DuplicateDetectionRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    service: str = "Lead Scoring & Sales Pipeline"
    version: str = "1.0.0"

# Global database connection pool
db_pool: Optional[asyncpg.Pool] = None

async def get_db_pool():
    return db_pool

async def get_auth_context(authorization: Optional[str] = Header(None)) -> AuthContext:
    """Extract and validate JWT token from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        
        secret = os.getenv("JWT_SECRET")
        if not secret:
            logger.error("JWT_SECRET environment variable not set")
            raise HTTPException(status_code=500, detail="Server configuration error")
        
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("sub")
        user_email = payload.get("email")
        
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token claims")
        
        return AuthContext(tenant_id=tenant_id, user_id=user_id, user_email=user_email)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

def calculate_lead_grade(score: float) -> LeadGrade:
    """Calculate lead grade based on score"""
    if score >= 90:
        return LeadGrade.A
    elif score >= 75:
        return LeadGrade.B
    elif score >= 50:
        return LeadGrade.C
    elif score >= 25:
        return LeadGrade.D
    else:
        return LeadGrade.F

def calculate_composite_score(request: LeadScoreRequest) -> float:
    """Calculate composite score from multiple factors"""
    base_score = (
        request.engagement_score * 0.3 +
        request.demographic_score * 0.25 +
        request.behavior_score * 0.25 +
        request.intent_score * 0.2
    )
    
    # Apply custom factors if provided
    if request.custom_factors:
        custom_weight = 0.1
        custom_score = sum(request.custom_factors.values()) / len(request.custom_factors) if request.custom_factors else 0
        base_score = base_score * (1 - custom_weight) + custom_score * custom_weight
    
    return min(max(base_score, MIN_SCORE), MAX_SCORE)

async def apply_score_decay(pool: asyncpg.Pool, tenant_id: str):
    """Apply score decay for inactive leads (weekly)"""
    query = """
    UPDATE leads
    SET current_score = current_score * $1,
        updated_at = NOW()
    WHERE tenant_id = $2
    AND updated_at < NOW() - INTERVAL '7 days'
    AND pipeline_stage != $3
    AND pipeline_stage != $4
    """
    async with pool.acquire() as conn:
        await conn.execute(query, SCORE_DECAY_RATE, tenant_id, PipelineStage.WON.value, PipelineStage.LOST.value)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database connection pool lifecycle"""
    global db_pool
    
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    
    if not all([db_name, db_user, db_password]):
        raise RuntimeError("Database credentials not configured")
    
    db_pool = await asyncpg.create_pool(
        user=db_user,
        password=db_password,
        database=db_name,
        host=db_host,
        port=db_port,
        min_size=2,
        max_size=10
    )
    
    logger.info("Database pool created")
    yield
    
    if db_pool:
        await db_pool.close()
        logger.info("Database pool closed")

app = FastAPI(
    title="Lead Scoring & Sales Pipeline Service",
    version="1.0.0",
    lifespan=lifespan
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="leads")
init_sentry(service_name="leads", service_port=9027)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="leads")
app.add_middleware(TracingMiddleware)


# CORS configuration
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Endpoints

@app.post("/api/v1/leads", response_model=LeadResponse)
async def create_lead(
    lead: LeadCreate,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Create a new lead"""
    lead_id = f"lead_{datetime.utcnow().timestamp()}_{auth.tenant_id}"
    current_score = lead.initial_score or 0
    lead_grade = calculate_lead_grade(current_score).value
    
    query = """
    INSERT INTO leads (
        lead_id, tenant_id, first_name, last_name, email, phone, company,
        current_score, lead_grade, pipeline_stage, source_channel, custom_data,
        created_at, updated_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), NOW())
    RETURNING lead_id, tenant_id, first_name, last_name, email, phone, company,
              current_score, lead_grade, pipeline_stage, source_channel, assigned_to,
              deal_value, win_probability, created_at, updated_at
    """
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                lead_id, auth.tenant_id, lead.first_name, lead.last_name,
                lead.email, lead.phone, lead.company, current_score, lead_grade,
                PipelineStage.NEW.value, lead.source_channel.value,
                json.dumps(lead.custom_data or {})
            )
        
        return LeadResponse(
            lead_id=row['lead_id'],
            tenant_id=row['tenant_id'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            email=row['email'],
            phone=row['phone'],
            company=row['company'],
            current_score=row['current_score'],
            lead_grade=row['lead_grade'],
            pipeline_stage=row['pipeline_stage'],
            source_channel=row['source_channel'],
            assigned_to=row['assigned_to'],
            deal_value=row['deal_value'],
            win_probability=row['win_probability'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Lead with this email already exists")
    except Exception as e:
        logger.error("Error creating lead: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to create lead")

@app.get("/api/v1/leads", response_model=Dict[str, Any])
async def list_leads(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    grade: Optional[str] = None,
    stage: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """List leads with filters and pagination"""
    query = "SELECT * FROM leads WHERE tenant_id = $1"
    params = [auth.tenant_id]
    param_count = 1
    
    if grade:
        param_count += 1
        query += f" AND lead_grade = ${param_count}"
        params.append(grade)
    
    if stage:
        param_count += 1
        query += f" AND pipeline_stage = ${param_count}"
        params.append(stage)
    
    valid_sort_fields = ['created_at', 'current_score', 'pipeline_stage']
    if sort_by not in valid_sort_fields:
        sort_by = 'created_at'

    order_sql = "DESC" if order.lower() == "desc" else "ASC"
    param_count += 1
    limit_param = param_count
    param_count += 1
    offset_param = param_count
    query += " ORDER BY " + sort_by + " " + order_sql + " LIMIT $" + str(limit_param) + " OFFSET $" + str(offset_param)
    query_with_limit = query
    params.extend([limit, skip])
    
    count_query = "SELECT COUNT(*) as total FROM leads WHERE tenant_id = $1"
    count_params = [auth.tenant_id]
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query_with_limit, *params)
            count_row = await conn.fetchrow(count_query, *count_params)
        
        leads = [
            LeadResponse(
                lead_id=row['lead_id'],
                tenant_id=row['tenant_id'],
                first_name=row['first_name'],
                last_name=row['last_name'],
                email=row['email'],
                phone=row['phone'],
                company=row['company'],
                current_score=row['current_score'],
                lead_grade=row['lead_grade'],
                pipeline_stage=row['pipeline_stage'],
                source_channel=row['source_channel'],
                assigned_to=row['assigned_to'],
                deal_value=row['deal_value'],
                win_probability=row['win_probability'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            for row in rows
        ]
        
        return {
            "total": count_row['total'],
            "skip": skip,
            "limit": limit,
            "leads": leads
        }
    except Exception as e:
        logger.error("Error listing leads: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to list leads")

@app.get("/api/v1/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: str,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Get lead detail"""
    query = "SELECT * FROM leads WHERE lead_id = $1 AND tenant_id = $2"
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, lead_id, auth.tenant_id)
        
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        
        return LeadResponse(
            lead_id=row['lead_id'],
            tenant_id=row['tenant_id'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            email=row['email'],
            phone=row['phone'],
            company=row['company'],
            current_score=row['current_score'],
            lead_grade=row['lead_grade'],
            pipeline_stage=row['pipeline_stage'],
            source_channel=row['source_channel'],
            assigned_to=row['assigned_to'],
            deal_value=row['deal_value'],
            win_probability=row['win_probability'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching lead: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch lead")

@app.put("/api/v1/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: str,
    lead_update: LeadUpdate,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Update lead information"""
    # Whitelist of allowed update fields to prevent SQL injection
    ALLOWED_FIELDS = {"first_name", "last_name", "email", "phone", "company", "custom_data"}
    update_parts = []
    params = [lead_id, auth.tenant_id]
    param_idx = 3

    for field, value in lead_update.dict(exclude_unset=True).items():
        if field not in ALLOWED_FIELDS:
            continue
        if field == "custom_data":
            update_parts.append("custom_data = $" + str(param_idx))
            params.append(json.dumps(value))
        else:
            update_parts.append(field + " = $" + str(param_idx))
            params.append(value)
        param_idx += 1

    if not update_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_parts.append("updated_at = NOW()")

    query = "UPDATE leads SET " + ", ".join(update_parts) + " WHERE lead_id = $1 AND tenant_id = $2 RETURNING *"
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
        
        if not row:
            raise HTTPException(status_code=404, detail="Lead not found")
        
        return LeadResponse(
            lead_id=row['lead_id'],
            tenant_id=row['tenant_id'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            email=row['email'],
            phone=row['phone'],
            company=row['company'],
            current_score=row['current_score'],
            lead_grade=row['lead_grade'],
            pipeline_stage=row['pipeline_stage'],
            source_channel=row['source_channel'],
            assigned_to=row['assigned_to'],
            deal_value=row['deal_value'],
            win_probability=row['win_probability'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating lead: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to update lead")

@app.post("/api/v1/leads/{lead_id}/score")
async def recalculate_score(
    lead_id: str,
    score_request: LeadScoreRequest,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Recalculate lead score based on factors"""
    new_score = calculate_composite_score(score_request)
    new_grade = calculate_lead_grade(new_score).value
    
    query = """
    UPDATE leads
    SET current_score = $1, lead_grade = $2, updated_at = NOW()
    WHERE lead_id = $3 AND tenant_id = $4
    RETURNING current_score, lead_grade
    """
    
    history_query = """
    INSERT INTO lead_score_history (lead_id, tenant_id, score, grade, created_at)
    VALUES ($1, $2, $3, $4, NOW())
    """
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, new_score, new_grade, lead_id, auth.tenant_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Lead not found")
            
            await conn.execute(history_query, lead_id, auth.tenant_id, new_score, new_grade)
        
        return {
            "lead_id": lead_id,
            "new_score": new_score,
            "new_grade": new_grade,
            "timestamp": datetime.utcnow()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error recalculating score: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to recalculate score")

@app.get("/api/v1/leads/{lead_id}/score-history")
async def get_score_history(
    lead_id: str,
    limit: int = Query(50, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Get lead score history"""
    query = """
    SELECT score, grade, created_at
    FROM lead_score_history
    WHERE lead_id = $1 AND tenant_id = $2
    ORDER BY created_at DESC
    LIMIT $3
    """
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, lead_id, auth.tenant_id, limit)
        
        return {
            "lead_id": lead_id,
            "history": [
                {
                    "score": float(row['score']),
                    "grade": row['grade'],
                    "timestamp": row['created_at']
                }
                for row in rows
            ]
        }
    except Exception as e:
        logger.error("Error fetching score history: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch score history")

@app.post("/api/v1/leads/{lead_id}/advance")
async def advance_pipeline_stage(
    lead_id: str,
    request: AdvancePipelineRequest,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Advance lead to next pipeline stage"""
    query = """
    UPDATE leads
    SET pipeline_stage = $1, updated_at = NOW(),
        deal_value = COALESCE($2, deal_value),
        win_probability = COALESCE($3, win_probability)
    WHERE lead_id = $4 AND tenant_id = $5
    RETURNING pipeline_stage, deal_value, win_probability
    """
    
    activity_query = """
    INSERT INTO lead_activity (lead_id, tenant_id, activity_type, details, created_at)
    VALUES ($1, $2, 'stage_advance', $3, NOW())
    """
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                request.new_stage,
                request.deal_value,
                request.win_probability,
                lead_id,
                auth.tenant_id
            )
            
            if not row:
                raise HTTPException(status_code=404, detail="Lead not found")
            
            await conn.execute(
                activity_query,
                lead_id,
                auth.tenant_id,
                json.dumps({"from_stage": "previous", "to_stage": request.new_stage})
            )
        
        return {
            "lead_id": lead_id,
            "new_stage": row['pipeline_stage'],
            "deal_value": row['deal_value'],
            "win_probability": row['win_probability'],
            "timestamp": datetime.utcnow()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error advancing stage: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to advance pipeline stage")

@app.post("/api/v1/leads/assign")
async def assign_lead(
    request: AssignLeadRequest,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Assign lead to sales agent"""
    query = """
    UPDATE leads
    SET assigned_to = $1, updated_at = NOW()
    WHERE lead_id = $2 AND tenant_id = $3
    RETURNING assigned_to
    """
    
    activity_query = """
    INSERT INTO lead_activity (lead_id, tenant_id, activity_type, details, created_at)
    VALUES ($1, $2, 'assignment', $3, NOW())
    """
    
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, request.assigned_to, request.lead_id, auth.tenant_id)
            
            if not row:
                raise HTTPException(status_code=404, detail="Lead not found")
            
            await conn.execute(
                activity_query,
                request.lead_id,
                auth.tenant_id,
                json.dumps({
                    "assigned_to": request.assigned_to,
                    "method": request.assignment_method
                })
            )
        
        return {
            "lead_id": request.lead_id,
            "assigned_to": row['assigned_to'],
            "timestamp": datetime.utcnow()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error assigning lead: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to assign lead")

@app.get("/api/v1/pipeline/stages")
async def get_pipeline_config(
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Get pipeline configuration for tenant"""
    query = """
    SELECT stage_name, order_index, stage_gate_requirements
    FROM pipeline_config
    WHERE tenant_id = $1
    ORDER BY order_index ASC
    """
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, auth.tenant_id)
        
        if not rows:
            return {
                "tenant_id": auth.tenant_id,
                "stages": [
                    {"stage_name": stage.value, "order": i+1, "stage_gate_requirements": {}}
                    for i, stage in enumerate(PipelineStage)
                    if stage.value not in [PipelineStage.WON.value, PipelineStage.LOST.value]
                ]
            }
        
        return {
            "tenant_id": auth.tenant_id,
            "stages": [
                {
                    "stage_name": row['stage_name'],
                    "order": row['order_index'],
                    "stage_gate_requirements": row['stage_gate_requirements'] or {}
                }
                for row in rows
            ]
        }
    except Exception as e:
        logger.error("Error fetching pipeline config: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch pipeline config")

@app.put("/api/v1/pipeline/stages")
async def configure_pipeline(
    config: PipelineConfig,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Configure pipeline stages for tenant"""
    delete_query = "DELETE FROM pipeline_config WHERE tenant_id = $1"
    insert_query = """
    INSERT INTO pipeline_config (tenant_id, stage_name, order_index, stage_gate_requirements)
    VALUES ($1, $2, $3, $4)
    """
    
    try:
        async with pool.acquire() as conn:
            await conn.execute(delete_query, auth.tenant_id)
            
            for stage in config.stages:
                await conn.execute(
                    insert_query,
                    auth.tenant_id,
                    stage.stage_name,
                    stage.order,
                    json.dumps(stage.stage_gate_requirements or {})
                )
        
        return {
            "tenant_id": auth.tenant_id,
            "message": "Pipeline configuration updated",
            "stages_count": len(config.stages)
        }
    except Exception as e:
        logger.error("Error configuring pipeline: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to configure pipeline")

@app.get("/api/v1/pipeline/analytics")
async def get_pipeline_analytics(
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Get pipeline analytics for tenant"""
    query = """
    SELECT
        pipeline_stage,
        COUNT(*) as lead_count,
        AVG(current_score) as avg_score,
        AVG(deal_value) as avg_deal_value,
        AVG(EXTRACT(DAY FROM (updated_at - created_at))) as avg_days_in_stage
    FROM leads
    WHERE tenant_id = $1
    GROUP BY pipeline_stage
    ORDER BY pipeline_stage
    """
    
    conversion_query = """
    SELECT
        COUNT(CASE WHEN pipeline_stage = $2 THEN 1 END)::float /
        COUNT(CASE WHEN pipeline_stage = $3 THEN 1 END) as conversion_rate
    FROM leads
    WHERE tenant_id = $1
    """
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, auth.tenant_id)
            conv_row = await conn.fetchrow(
                conversion_query,
                auth.tenant_id,
                PipelineStage.WON.value,
                PipelineStage.NEW.value
            )
        
        return {
            "tenant_id": auth.tenant_id,
            "stages_analytics": [
                {
                    "stage": row['pipeline_stage'],
                    "lead_count": row['lead_count'],
                    "avg_score": float(row['avg_score']) if row['avg_score'] else 0,
                    "avg_deal_value": float(row['avg_deal_value']) if row['avg_deal_value'] else 0,
                    "avg_days_in_stage": float(row['avg_days_in_stage']) if row['avg_days_in_stage'] else 0
                }
                for row in rows
            ],
            "conversion_rate": float(conv_row['conversion_rate']) if conv_row['conversion_rate'] else 0
        }
    except Exception as e:
        logger.error("Error fetching analytics: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

@app.get("/api/v1/pipeline/forecast")
async def get_revenue_forecast(
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Get revenue forecast based on pipeline"""
    query = """
    SELECT
        pipeline_stage,
        SUM(COALESCE(deal_value, 0) * COALESCE(win_probability, 0.5)) as weighted_value,
        COUNT(*) as lead_count
    FROM leads
    WHERE tenant_id = $1 AND pipeline_stage NOT IN ($2, $3)
    GROUP BY pipeline_stage
    ORDER BY pipeline_stage
    """
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, auth.tenant_id, PipelineStage.WON.value, PipelineStage.LOST.value)
        
        total_forecast = sum(float(row['weighted_value']) for row in rows)
        
        return {
            "tenant_id": auth.tenant_id,
            "forecast_by_stage": [
                {
                    "stage": row['pipeline_stage'],
                    "weighted_value": float(row['weighted_value']),
                    "lead_count": row['lead_count']
                }
                for row in rows
            ],
            "total_forecast": total_forecast,
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        logger.error("Error generating forecast: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to generate forecast")

@app.post("/api/v1/leads/deduplicate")
async def find_duplicates(
    request: DuplicateDetectionRequest,
    auth: AuthContext = Depends(get_auth_context),
    pool: asyncpg.Pool = Depends(get_db_pool)
):
    """Find potential duplicate leads"""
    query = "SELECT lead_id, first_name, last_name, email, phone FROM leads WHERE tenant_id = $1"
    conditions = []
    params = [auth.tenant_id]
    param_count = 1
    
    if request.email:
        param_count += 1
        conditions.append(f"email = ${param_count}")
        params.append(request.email.lower())
    elif request.phone:
        param_count += 1
        conditions.append(f"phone = ${param_count}")
        params.append(request.phone)
    elif request.first_name and request.last_name:
        param_count += 1
        param_count += 1
        conditions.append(f"LOWER(first_name) = LOWER(${param_count-1}) AND LOWER(last_name) = LOWER(${param_count})")
        params.extend([request.first_name, request.last_name])
    
    if not conditions:
        raise HTTPException(status_code=400, detail="Provide email, phone, or both name fields")
    
    query += " AND " + " OR ".join(conditions)
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        return {
            "duplicates_found": len(rows),
            "duplicates": [
                {
                    "lead_id": row['lead_id'],
                    "name": f"{row['first_name']} {row['last_name']}",
                    "email": row['email'],
                    "phone": row['phone']
                }
                for row in rows
            ]
        }
    except Exception as e:
        logger.error("Error detecting duplicates: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to detect duplicates")

@app.get("/api/v1/leads/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(status="healthy", timestamp=datetime.utcnow())

if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=PORT)
