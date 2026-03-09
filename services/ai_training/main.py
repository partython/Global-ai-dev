"""
AI Training & Fine-tuning Service
Multi-tenant SaaS FastAPI service for managing AI model training,
fine-tuning, prompt templates, quality monitoring, and persona management.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

import asyncpg
import jwt
from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import httpx

from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config


# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Constants
PORT = 9036
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Models
class TrainingStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class QualityScore(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class AuthContext:
    """JWT authentication context with tenant isolation."""
    def __init__(self, tenant_id: str, user_id: str, exp: int):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.exp = exp


# Request/Response Models
class TrainingDataRequest(BaseModel):
    input_text: str = Field(..., min_length=1, max_length=5000)
    ideal_response: str = Field(..., min_length=1, max_length=5000)
    quality_score: Optional[QualityScore] = None
    labels: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class TrainingDataResponse(BaseModel):
    id: str
    tenant_id: str
    input_text: str
    ideal_response: str
    quality_score: Optional[str]
    labels: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FinetuningJobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model: str = Field(default="gpt-3.5-turbo")
    training_data_ids: Optional[List[str]] = None
    hyperparameters: Optional[Dict[str, Any]] = None


class FinetuningJobResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    model: str
    status: str
    training_data_count: int
    metrics: Dict[str, Any]
    model_version: str
    external_job_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class PromptTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    template: str = Field(..., min_length=1)
    variables: List[str] = []
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PromptTemplateResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    template: str
    variables: List[str]
    description: Optional[str]
    version: int
    metadata: Dict[str, Any]
    usage_count: int
    avg_performance: Optional[float]
    created_at: datetime
    updated_at: datetime


class QualityReportResponse(BaseModel):
    total_responses_evaluated: int
    excellent_count: int
    good_count: int
    fair_count: int
    poor_count: int
    overall_score: float
    flagged_responses: List[Dict[str, Any]]


class PersonaRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    tone: str = Field(..., description="Communication tone (professional, casual, friendly, etc)")
    vocabulary_level: str = Field(..., description="Vocabulary level (simple, moderate, advanced)")
    industry: Optional[str] = None
    language: str = Field(default="en")
    response_patterns: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class PersonaResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    tone: str
    vocabulary_level: str
    industry: Optional[str]
    language: str
    response_patterns: List[str]
    metadata: Dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    service: str
    version: str


# Database Layer
class Database:
    """Async PostgreSQL database client with connection pooling."""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Initialize database connection pool."""
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        
        self.pool = await asyncpg.create_pool(
            db_url,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )
        await self._init_schema()
    
    async def disconnect(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
    
    async def _init_schema(self):
        """Initialize database schema if not exists."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS training_data (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    input_text TEXT NOT NULL,
                    ideal_response TEXT NOT NULL,
                    quality_score VARCHAR(20),
                    labels JSONB DEFAULT '[]'::jsonb,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_training_data_tenant 
                    ON training_data(tenant_id);
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS finetuning_jobs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    model VARCHAR(255) NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    training_data_count INT DEFAULT 0,
                    metrics JSONB DEFAULT '{}'::jsonb,
                    model_version VARCHAR(50),
                    external_job_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_finetuning_jobs_tenant 
                    ON finetuning_jobs(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_finetuning_jobs_status 
                    ON finetuning_jobs(status);
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt_templates (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    template TEXT NOT NULL,
                    variables JSONB DEFAULT '[]'::jsonb,
                    description TEXT,
                    version INT DEFAULT 1,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    usage_count INT DEFAULT 0,
                    avg_performance DECIMAL(5,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_prompt_templates_tenant 
                    ON prompt_templates(tenant_id);
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS quality_evaluations (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    response_id VARCHAR(255) NOT NULL,
                    quality_score VARCHAR(20) NOT NULL,
                    relevance DECIMAL(3,2),
                    accuracy DECIMAL(3,2),
                    tone_match DECIMAL(3,2),
                    is_flagged BOOLEAN DEFAULT FALSE,
                    feedback TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_quality_evaluations_tenant 
                    ON quality_evaluations(tenant_id);
                CREATE INDEX IF NOT EXISTS idx_quality_evaluations_flagged 
                    ON quality_evaluations(is_flagged);
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS personas (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    tone VARCHAR(100) NOT NULL,
                    vocabulary_level VARCHAR(100) NOT NULL,
                    industry VARCHAR(100),
                    language VARCHAR(10) DEFAULT 'en',
                    response_patterns JSONB DEFAULT '[]'::jsonb,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    version INT DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_personas_tenant 
                    ON personas(tenant_id);
            """)
    
    async def execute(self, query: str, *args):
        """Execute a query without returning results."""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def fetch_one(self, query: str, *args):
        """Fetch a single row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetch_all(self, query: str, *args):
        """Fetch multiple rows."""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)


# JWT Authentication
security = HTTPBearer()
db = Database()


def decode_jwt(token: str) -> AuthContext:
    """Decode and validate JWT token."""
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise ValueError("JWT_SECRET environment variable not set")
    
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        return AuthContext(
            tenant_id=payload.get("tenant_id"),
            user_id=payload.get("user_id"),
            exp=payload.get("exp")
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        ) from e


async def get_auth_context(credentials: HTTPAuthCredentials = Depends(security)) -> AuthContext:
    """Dependency to get authenticated context."""
    return decode_jwt(credentials.credentials)


# Initialize FastAPI app
app = FastAPI(
    title="AI Training & Fine-tuning Service",
    version="1.0.0",
    description="Multi-tenant AI model training and fine-tuning platform"
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="ai_training")
init_sentry(service_name="ai-training", service_port=9036)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="ai-training")
app.add_middleware(TracingMiddleware)


# CORS middleware - validate origins
if "*" in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["http://localhost:3000"]

cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



# Startup and Shutdown
@app.on_event("startup")
async def startup():
    """Connect to database on startup."""
    await db.connect()


@app.on_event("shutdown")
async def shutdown():
    """Close database connection on shutdown."""
    await event_bus.shutdown()
    await db.disconnect()
    shutdown_tracing()


# Training Data Endpoints
@app.post("/ai-training/data", response_model=TrainingDataResponse)
async def create_training_data(
    request: TrainingDataRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create new training data entry with quality scoring and labels."""
    data_id = str(uuid.uuid4())
    
    await db.execute("""
        INSERT INTO training_data 
        (id, tenant_id, input_text, ideal_response, quality_score, labels, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, data_id, auth.tenant_id, request.input_text, request.ideal_response,
    request.quality_score, json.dumps(request.labels or []),
    json.dumps(request.metadata or {}))
    
    row = await db.fetch_one(
        "SELECT * FROM training_data WHERE id = $1 AND tenant_id = $2",
        data_id, auth.tenant_id
    )
    
    return _format_training_data(row)


@app.get("/ai-training/data", response_model=List[TrainingDataResponse])
async def list_training_data(
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth_context)
):
    """List all training data for tenant with pagination."""
    rows = await db.fetch_all("""
        SELECT * FROM training_data 
        WHERE tenant_id = $1 
        ORDER BY created_at DESC 
        LIMIT $2 OFFSET $3
    """, auth.tenant_id, limit, skip)
    
    return [_format_training_data(row) for row in rows]


# Fine-tuning Job Endpoints
@app.post("/ai-training/jobs", response_model=FinetuningJobResponse)
async def create_finetuning_job(
    request: FinetuningJobRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create fine-tuning job with OpenAI API integration."""
    job_id = str(uuid.uuid4())
    model_version = f"v{datetime.utcnow().timestamp()}"
    
    # Count training data if specific IDs provided
    training_count = 0
    if request.training_data_ids:
        result = await db.fetch_one("""
            SELECT COUNT(*) as count FROM training_data 
            WHERE tenant_id = $1 AND id = ANY($2::uuid[])
        """, auth.tenant_id, request.training_data_ids)
        training_count = result["count"]
    else:
        result = await db.fetch_one(
            "SELECT COUNT(*) as count FROM training_data WHERE tenant_id = $1",
            auth.tenant_id
        )
        training_count = result["count"]
    
    # Submit to OpenAI API asynchronously (fire and forget pattern)
    external_job_id = await _submit_to_openai(
        request.model,
        request.training_data_ids or [],
        request.hyperparameters or {}
    )
    
    await db.execute("""
        INSERT INTO finetuning_jobs 
        (id, tenant_id, name, model, training_data_count, model_version, external_job_id, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    """, job_id, auth.tenant_id, request.name, request.model,
    training_count, model_version, external_job_id, "running")
    
    row = await db.fetch_one(
        "SELECT * FROM finetuning_jobs WHERE id = $1 AND tenant_id = $2",
        job_id, auth.tenant_id
    )
    
    return _format_finetuning_job(row)


@app.get("/ai-training/jobs", response_model=List[FinetuningJobResponse])
async def list_finetuning_jobs(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth_context)
):
    """List fine-tuning jobs with optional status filter."""
    if status:
        rows = await db.fetch_all("""
            SELECT * FROM finetuning_jobs 
            WHERE tenant_id = $1 AND status = $2
            ORDER BY created_at DESC 
            LIMIT $3 OFFSET $4
        """, auth.tenant_id, status, limit, skip)
    else:
        rows = await db.fetch_all("""
            SELECT * FROM finetuning_jobs 
            WHERE tenant_id = $1 
            ORDER BY created_at DESC 
            LIMIT $2 OFFSET $3
        """, auth.tenant_id, limit, skip)
    
    return [_format_finetuning_job(row) for row in rows]


@app.get("/ai-training/jobs/{job_id}", response_model=FinetuningJobResponse)
async def get_finetuning_job(
    job_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Get specific fine-tuning job with progress and metrics."""
    row = await db.fetch_one(
        "SELECT * FROM finetuning_jobs WHERE id = $1 AND tenant_id = $2",
        job_id, auth.tenant_id
    )
    
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return _format_finetuning_job(row)


# Prompt Template Endpoints
@app.post("/ai-training/templates", response_model=PromptTemplateResponse)
async def create_prompt_template(
    request: PromptTemplateRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create versioned prompt template with variable injection support."""
    template_id = str(uuid.uuid4())
    
    await db.execute("""
        INSERT INTO prompt_templates 
        (id, tenant_id, name, template, variables, description, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, template_id, auth.tenant_id, request.name, request.template,
    json.dumps(request.variables), request.description,
    json.dumps(request.metadata or {}))
    
    row = await db.fetch_one(
        "SELECT * FROM prompt_templates WHERE id = $1 AND tenant_id = $2",
        template_id, auth.tenant_id
    )
    
    return _format_prompt_template(row)


@app.get("/ai-training/templates", response_model=List[PromptTemplateResponse])
async def list_prompt_templates(
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth_context)
):
    """List all prompt templates for tenant."""
    rows = await db.fetch_all("""
        SELECT * FROM prompt_templates 
        WHERE tenant_id = $1 
        ORDER BY created_at DESC 
        LIMIT $2 OFFSET $3
    """, auth.tenant_id, limit, skip)
    
    return [_format_prompt_template(row) for row in rows]


@app.put("/ai-training/templates/{template_id}", response_model=PromptTemplateResponse)
async def update_prompt_template(
    template_id: str,
    request: PromptTemplateRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Update prompt template with version tracking."""
    row = await db.fetch_one(
        "SELECT version FROM prompt_templates WHERE id = $1 AND tenant_id = $2",
        template_id, auth.tenant_id
    )
    
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    
    new_version = row["version"] + 1
    
    await db.execute("""
        UPDATE prompt_templates 
        SET template = $1, variables = $2, description = $3, 
            metadata = $4, version = $5, updated_at = CURRENT_TIMESTAMP
        WHERE id = $6 AND tenant_id = $7
    """, request.template, json.dumps(request.variables),
    request.description, json.dumps(request.metadata or {}),
    new_version, template_id, auth.tenant_id)
    
    updated_row = await db.fetch_one(
        "SELECT * FROM prompt_templates WHERE id = $1 AND tenant_id = $2",
        template_id, auth.tenant_id
    )
    
    return _format_prompt_template(updated_row)


# Quality Monitoring Endpoints
@app.get("/ai-training/quality", response_model=QualityReportResponse)
async def get_quality_report(
    days: int = 7,
    auth: AuthContext = Depends(get_auth_context)
):
    """Get quality monitoring report with auto-evaluation metrics."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    summary = await db.fetch_one("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN quality_score = 'excellent' THEN 1 ELSE 0 END) as excellent,
            SUM(CASE WHEN quality_score = 'good' THEN 1 ELSE 0 END) as good,
            SUM(CASE WHEN quality_score = 'fair' THEN 1 ELSE 0 END) as fair,
            SUM(CASE WHEN quality_score = 'poor' THEN 1 ELSE 0 END) as poor,
            AVG(COALESCE((
                CASE WHEN quality_score = 'excellent' THEN 1.0
                WHEN quality_score = 'good' THEN 0.75
                WHEN quality_score = 'fair' THEN 0.5
                ELSE 0.25 END
            ), 0.5)) as avg_score
        FROM quality_evaluations 
        WHERE tenant_id = $1 AND created_at >= $2
    """, auth.tenant_id, cutoff_date)
    
    flagged = await db.fetch_all("""
        SELECT response_id, quality_score, relevance, accuracy, tone_match, feedback
        FROM quality_evaluations 
        WHERE tenant_id = $1 AND is_flagged = TRUE 
        ORDER BY created_at DESC LIMIT 20
    """, auth.tenant_id)
    
    return QualityReportResponse(
        total_responses_evaluated=summary["total"] or 0,
        excellent_count=summary["excellent"] or 0,
        good_count=summary["good"] or 0,
        fair_count=summary["fair"] or 0,
        poor_count=summary["poor"] or 0,
        overall_score=float(summary["avg_score"] or 0.5),
        flagged_responses=[dict(row) for row in flagged]
    )


# Persona Management Endpoints
@app.post("/ai-training/personas", response_model=PersonaResponse)
async def create_persona(
    request: PersonaRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create AI persona with tone, vocabulary, and industry-specific patterns."""
    persona_id = str(uuid.uuid4())
    
    await db.execute("""
        INSERT INTO personas 
        (id, tenant_id, name, tone, vocabulary_level, industry, language, response_patterns, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """, persona_id, auth.tenant_id, request.name, request.tone,
    request.vocabulary_level, request.industry, request.language,
    json.dumps(request.response_patterns or []),
    json.dumps(request.metadata or {}))
    
    row = await db.fetch_one(
        "SELECT * FROM personas WHERE id = $1 AND tenant_id = $2",
        persona_id, auth.tenant_id
    )
    
    return _format_persona(row)


@app.get("/ai-training/personas", response_model=List[PersonaResponse])
async def list_personas(
    language: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(get_auth_context)
):
    """List personas with optional language filter for multi-language support."""
    if language:
        rows = await db.fetch_all("""
            SELECT * FROM personas 
            WHERE tenant_id = $1 AND language = $2
            ORDER BY created_at DESC 
            LIMIT $3 OFFSET $4
        """, auth.tenant_id, language, limit, skip)
    else:
        rows = await db.fetch_all("""
            SELECT * FROM personas 
            WHERE tenant_id = $1 
            ORDER BY created_at DESC 
            LIMIT $2 OFFSET $3
        """, auth.tenant_id, limit, skip)
    
    return [_format_persona(row) for row in rows]


@app.put("/ai-training/personas/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: str,
    request: PersonaRequest,
    auth: AuthContext = Depends(get_auth_context)
):
    """Update persona with version tracking."""
    row = await db.fetch_one(
        "SELECT version FROM personas WHERE id = $1 AND tenant_id = $2",
        persona_id, auth.tenant_id
    )
    
    if not row:
        raise HTTPException(status_code=404, detail="Persona not found")
    
    new_version = row["version"] + 1
    
    await db.execute("""
        UPDATE personas 
        SET tone = $1, vocabulary_level = $2, industry = $3, 
            response_patterns = $4, metadata = $5, version = $6,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $7 AND tenant_id = $8
    """, request.tone, request.vocabulary_level, request.industry,
    json.dumps(request.response_patterns or []),
    json.dumps(request.metadata or {}), new_version, persona_id, auth.tenant_id)
    
    updated_row = await db.fetch_one(
        "SELECT * FROM personas WHERE id = $1 AND tenant_id = $2",
        persona_id, auth.tenant_id
    )
    
    return _format_persona(updated_row)


# Health Check Endpoint
@app.get("/ai-training/health", response_model=HealthResponse)
async def health_check():
    """Service health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        service="AI Training & Fine-tuning",
        version="1.0.0"
    )


# Helper Functions
def _format_training_data(row: asyncpg.Record) -> TrainingDataResponse:
    """Format database row to TrainingDataResponse."""
    return TrainingDataResponse(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        input_text=row["input_text"],
        ideal_response=row["ideal_response"],
        quality_score=row["quality_score"],
        labels=json.loads(row["labels"]),
        metadata=json.loads(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )


def _format_finetuning_job(row: asyncpg.Record) -> FinetuningJobResponse:
    """Format database row to FinetuningJobResponse."""
    return FinetuningJobResponse(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        name=row["name"],
        model=row["model"],
        status=row["status"],
        training_data_count=row["training_data_count"],
        metrics=json.loads(row["metrics"]),
        model_version=row["model_version"],
        external_job_id=row["external_job_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )


def _format_prompt_template(row: asyncpg.Record) -> PromptTemplateResponse:
    """Format database row to PromptTemplateResponse."""
    return PromptTemplateResponse(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        name=row["name"],
        template=row["template"],
        variables=json.loads(row["variables"]),
        description=row["description"],
        version=row["version"],
        metadata=json.loads(row["metadata"]),
        usage_count=row["usage_count"],
        avg_performance=float(row["avg_performance"]) if row["avg_performance"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )


def _format_persona(row: asyncpg.Record) -> PersonaResponse:
    """Format database row to PersonaResponse."""
    return PersonaResponse(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        name=row["name"],
        tone=row["tone"],
        vocabulary_level=row["vocabulary_level"],
        industry=row["industry"],
        language=row["language"],
        response_patterns=json.loads(row["response_patterns"]),
        metadata=json.loads(row["metadata"]),
        version=row["version"],
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )


async def _submit_to_openai(
    model: str,
    training_data_ids: List[str],
    hyperparameters: Dict[str, Any]
) -> Optional[str]:
    """Submit training job to OpenAI API."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/fine_tuning/jobs",
                headers={"Authorization": f"Bearer {openai_api_key}"},
                json={
                    "training_file": "file_placeholder",
                    "model": model,
                    "hyperparameters": hyperparameters
                },
                timeout=30.0
            )
            if response.status_code == 200:
                return response.json().get("id")
    except Exception as e:
        logger.warning("Failed to submit to OpenAI: %s", str(e))

    return None


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )
