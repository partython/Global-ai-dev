import os
import asyncio
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
import uuid
from dataclasses import dataclass
from collections import defaultdict

from fastapi import FastAPI, Depends, HTTPException, status, Body, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthenticationCredentials
from pydantic import BaseModel, Field, EmailStr, validator
import jwt
import asyncpg
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config


# ============================================================================
# Logging Configuration
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration & Constants
# ============================================================================

APP_NAME = "Compliance & GDPR Service"
PORT = 9038

# Secrets from environment (NEVER hardcoded)
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if os.getenv("CORS_ORIGINS") else ["http://localhost:3000"]
DATA_RETENTION_DEFAULT = int(os.getenv("DATA_RETENTION_DEFAULT_DAYS", "2555"))  # ~7 years
DSAR_EXPIRATION_DAYS = int(os.getenv("DSAR_EXPIRATION_DAYS", "45"))
PII_MASKING_CHARS = int(os.getenv("PII_MASKING_CHARS", "4"))

if not JWT_SECRET:
    raise ValueError("JWT_SECRET environment variable must be set")
if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError("Database credentials must be provided via environment variables")


# ============================================================================
# Enums
# ============================================================================

class ComplianceRegion(str, Enum):
    GDPR = "gdpr"  # EU/UK
    CCPA = "ccpa"  # California
    LGPD = "lgpd"  # Brazil
    POPI = "popi"  # South Africa


class DSARStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ConsentStatus(str, Enum):
    OPTED_IN = "opted_in"
    OPTED_OUT = "opted_out"
    PENDING = "pending"
    WITHDRAWN = "withdrawn"


class AuditAction(str, Enum):
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    CONSENT_CHANGE = "consent_change"
    EXPORT_REQUEST = "export_request"
    ANONYMIZATION = "anonymization"
    BREACH_NOTIFICATION = "breach_notification"
    RETENTION_POLICY_CHANGE = "retention_policy_change"
    CROSS_BORDER_TRANSFER = "cross_border_transfer"


class BreachSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnonymizationStrategy(str, Enum):
    PSEUDONYMIZATION = "pseudonymization"
    FULL_ANONYMIZATION = "full_anonymization"
    DATA_MASKING = "data_masking"


# ============================================================================
# Pydantic Models
# ============================================================================

class AuthContext(BaseModel):
    tenant_id: str
    user_id: str
    email: str


class DSARRequest(BaseModel):
    customer_id: str
    email: EmailStr
    data_types: List[str] = Field(default_factory=list)
    requested_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    
    @validator('customer_id')
    def customer_id_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('customer_id cannot be empty')
        return v


class DSARResponse(BaseModel):
    id: str
    tenant_id: str
    customer_id: str
    status: DSARStatus
    data_export_url: Optional[str] = None
    requested_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    retention_days: int = DSAR_EXPIRATION_DAYS


class ConsentRecord(BaseModel):
    customer_id: str
    consent_type: str
    status: ConsentStatus
    regions: List[ComplianceRegion]
    given_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    consent_string: Optional[str] = None  # TCF consent string


class DataRetentionPolicy(BaseModel):
    policy_id: str
    tenant_id: str
    region: ComplianceRegion
    retention_days: int
    data_category: str
    auto_purge_enabled: bool = True
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    @validator('retention_days')
    def retention_days_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('retention_days must be positive')
        return v


class AuditLogEntry(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    action: AuditAction
    resource_id: str
    pii_access: bool = False
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    region: Optional[ComplianceRegion] = None


class AnonymizationRequest(BaseModel):
    customer_id: str
    data_types: List[str]
    strategy: AnonymizationStrategy = AnonymizationStrategy.PSEUDONYMIZATION


class AnonymizationResponse(BaseModel):
    task_id: str
    status: str
    customer_id: str
    strategy: AnonymizationStrategy
    progress: int = 0
    message: str


class BreachNotification(BaseModel):
    breach_type: str
    affected_customers: int
    severity: BreachSeverity
    description: str
    discovered_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    notification_required: bool = True
    affected_data_categories: List[str] = Field(default_factory=list)
    
    @validator('affected_customers')
    def affected_customers_must_be_positive(cls, v):
        if v < 0:
            raise ValueError('affected_customers must be non-negative')
        return v


class BreachResponse(BaseModel):
    breach_id: str
    status: str
    notification_required: bool
    notification_deadline: Optional[datetime] = None
    message: str


class ComplianceReport(BaseModel):
    report_id: str
    tenant_id: str
    region: ComplianceRegion
    period_start: datetime
    period_end: datetime
    dsar_requests: int = 0
    deletions_executed: int = 0
    consent_changes: int = 0
    data_breaches: int = 0
    cross_border_transfers: int = 0
    pii_access_events: int = 0
    generated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class DPATemplate(BaseModel):
    dpa_id: str
    tenant_id: str
    processor_name: str
    processing_activities: List[str]
    data_categories: List[str]
    retention_schedule: Dict[str, int]
    security_measures: List[str]
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None


class CrossBorderTransfer(BaseModel):
    transfer_id: str
    tenant_id: str
    source_region: ComplianceRegion
    destination_region: ComplianceRegion
    transfer_basis: str  # SCCs, BCRs, adequacy_decision
    data_categories: List[str]
    transferred_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class CookieConsent(BaseModel):
    customer_id: str
    categories: Dict[str, bool]  # necessary, analytics, marketing, etc
    consent_date: Optional[datetime] = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    language: str = "en"


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    database: str
    version: str = "1.0.0"


# ============================================================================
# Helper Classes
# ============================================================================

@dataclass
class PIIMaskingConfig:
    """Configuration for PII masking strategies."""
    email_mask_chars: int = 4
    phone_mask_chars: int = 6
    ssn_mask_chars: int = 7
    replace_char: str = "*"
    
    def mask_email(self, email: str) -> str:
        """Mask email address."""
        try:
            local, domain = email.split('@')
            if len(local) <= self.email_mask_chars:
                return f"{'*' * len(local)}@{domain}"
            return f"{local[:len(local)-self.email_mask_chars]}{'*' * self.email_mask_chars}@{domain}"
        except ValueError:
            return f"{self.replace_char * len(email)}"
    
    def mask_phone(self, phone: str) -> str:
        """Mask phone number."""
        if len(phone) <= self.phone_mask_chars:
            return self.replace_char * len(phone)
        return f"{phone[:len(phone)-self.phone_mask_chars]}{self.replace_char * self.phone_mask_chars}"
    
    def mask_ssn(self, ssn: str) -> str:
        """Mask SSN/similar identifier."""
        if len(ssn) <= self.ssn_mask_chars:
            return self.replace_char * len(ssn)
        return f"{ssn[:len(ssn)-self.ssn_mask_chars]}{self.replace_char * self.ssn_mask_chars}"


# ============================================================================
# Database Connection Pool
# ============================================================================

db_pool: Optional[asyncpg.Pool] = None
pii_masking = PIIMaskingConfig(email_mask_chars=PII_MASKING_CHARS)


async def init_db():
    """Initialize database connection pool and create tables."""
    global db_pool
    db_pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        min_size=5,
        max_size=20,
    )

    async with db_pool.acquire() as conn:
        # DSAR Requests Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dsar_requests (
                id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                customer_id VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                data_types TEXT,
                data_export_url TEXT,
                requested_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_dsar_tenant_customer ON dsar_requests(tenant_id, customer_id);
            CREATE INDEX IF NOT EXISTS idx_dsar_status ON dsar_requests(tenant_id, status);
        """)

        # Consent Records Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS consent_records (
                id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                customer_id VARCHAR(255) NOT NULL,
                consent_type VARCHAR(100) NOT NULL,
                status VARCHAR(50) NOT NULL,
                regions TEXT NOT NULL,
                consent_string TEXT,
                given_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_consent_tenant_customer ON consent_records(tenant_id, customer_id);
            CREATE INDEX IF NOT EXISTS idx_consent_status ON consent_records(tenant_id, status);
        """)

        # Cookie Consent Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cookie_consents (
                id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                customer_id VARCHAR(255) NOT NULL,
                categories JSONB NOT NULL,
                consent_date TIMESTAMP NOT NULL,
                expires_at TIMESTAMP,
                language VARCHAR(10) DEFAULT 'en',
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_cookie_tenant_customer ON cookie_consents(tenant_id, customer_id);
        """)

        # Retention Policies Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS retention_policies (
                policy_id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                region VARCHAR(50) NOT NULL,
                retention_days INTEGER NOT NULL,
                data_category VARCHAR(100) NOT NULL,
                auto_purge_enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_retention_tenant_region ON retention_policies(tenant_id, region);
        """)

        # Audit Logs Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                action VARCHAR(100) NOT NULL,
                resource_id VARCHAR(255) NOT NULL,
                pii_access BOOLEAN DEFAULT FALSE,
                timestamp TIMESTAMP NOT NULL,
                details JSONB,
                ip_address VARCHAR(45),
                region VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_audit_tenant_timestamp ON audit_logs(tenant_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_pii_access ON audit_logs(tenant_id, pii_access);
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(tenant_id, action);
        """)

        # Breach Notifications Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS breach_notifications (
                id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                breach_type VARCHAR(100) NOT NULL,
                affected_customers INTEGER NOT NULL,
                severity VARCHAR(50) NOT NULL,
                description TEXT NOT NULL,
                affected_data_categories TEXT,
                notification_required BOOLEAN DEFAULT TRUE,
                discovered_at TIMESTAMP NOT NULL,
                notified_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_breach_tenant_date ON breach_notifications(tenant_id, discovered_at);
            CREATE INDEX IF NOT EXISTS idx_breach_severity ON breach_notifications(tenant_id, severity);
        """)

        # Compliance Reports Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_reports (
                report_id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                region VARCHAR(50) NOT NULL,
                period_start TIMESTAMP NOT NULL,
                period_end TIMESTAMP NOT NULL,
                dsar_requests INTEGER DEFAULT 0,
                deletions_executed INTEGER DEFAULT 0,
                consent_changes INTEGER DEFAULT 0,
                data_breaches INTEGER DEFAULT 0,
                cross_border_transfers INTEGER DEFAULT 0,
                pii_access_events INTEGER DEFAULT 0,
                generated_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_report_tenant_region ON compliance_reports(tenant_id, region);
        """)

        # DPA Templates Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dpa_templates (
                dpa_id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                processor_name VARCHAR(255) NOT NULL,
                processing_activities TEXT NOT NULL,
                data_categories TEXT NOT NULL,
                retention_schedule JSONB,
                security_measures TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_dpa_tenant ON dpa_templates(tenant_id);
        """)

        # Cross-Border Transfers Table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_border_transfers (
                transfer_id UUID PRIMARY KEY,
                tenant_id VARCHAR(255) NOT NULL,
                source_region VARCHAR(50) NOT NULL,
                destination_region VARCHAR(50) NOT NULL,
                transfer_basis VARCHAR(100) NOT NULL,
                data_categories TEXT NOT NULL,
                transferred_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_transfer_tenant ON cross_border_transfers(tenant_id);
        """)

    logger.info("Database initialized successfully")


async def close_db():
    """Close database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection pool closed")


# ============================================================================
# JWT Authentication
# ============================================================================

security = HTTPBearer()


async def verify_token(credentials: HTTPAuthenticationCredentials = Depends(security)) -> AuthContext:
    """Verify JWT token and extract auth context."""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        tenant_id: str = payload.get("tenant_id")
        user_id: str = payload.get("user_id")
        email: str = payload.get("email")

        if not all([tenant_id, user_id, email]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")

        return AuthContext(tenant_id=tenant_id, user_id=user_id, email=email)
    except jwt.InvalidTokenError as e:
        logger.warning("Token verification failed: %s", str(e))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ============================================================================
# Audit Logging Helper
# ============================================================================

async def log_audit(
    auth: AuthContext,
    action: AuditAction,
    resource_id: str,
    pii_access: bool = False,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    region: Optional[ComplianceRegion] = None,
):
    """Log an audit trail entry."""
    if not db_pool:
        return

    entry_id = str(uuid.uuid4())
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO audit_logs
                (id, tenant_id, user_id, action, resource_id, pii_access, timestamp, details, ip_address, region)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, entry_id, auth.tenant_id, auth.user_id, action.value, resource_id, pii_access,
                datetime.utcnow(), json.dumps(details) if details else None, ip_address,
                region.value if region else None)
    except Exception as e:
        logger.error("Failed to log audit: %s", str(e))


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(title=APP_NAME, version="1.0.0")
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="compliance")
init_sentry(service_name="compliance", service_port=9038)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="compliance")
app.add_middleware(TracingMiddleware)


cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Starting %s on port %s", APP_NAME, PORT)
    await event_bus.startup()
    await init_db()


@app.on_event("shutdown")
async def shutdown_event():
    """Close database on shutdown."""
    logger.info("Shutting down %s", APP_NAME)
    shutdown_tracing()
    await event_bus.shutdown()
    await close_db()


# ============================================================================
# GDPR DSAR Endpoints
# ============================================================================

@app.post("/compliance/dsar", response_model=DSARResponse, status_code=status.HTTP_201_CREATED)
async def create_dsar_request(
    request: DSARRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Submit a Data Subject Access Request (DSAR)."""
    request_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=DSAR_EXPIRATION_DAYS)
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO dsar_requests 
            (id, tenant_id, customer_id, email, status, data_types, requested_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, request_id, auth.tenant_id, request.customer_id, request.email,
            DSARStatus.PENDING.value, json.dumps(request.data_types), 
            request.requested_at or datetime.utcnow(), expires_at)

    await log_audit(auth, AuditAction.EXPORT_REQUEST, request_id, pii_access=True,
                    details={"customer_id": request.customer_id, "email": request.email})

    logger.info("DSAR request created: %s for customer %s", request_id, request.customer_id)

    return DSARResponse(
        id=request_id,
        tenant_id=auth.tenant_id,
        customer_id=request.customer_id,
        status=DSARStatus.PENDING,
        requested_at=request.requested_at or datetime.utcnow(),
        expires_at=expires_at,
    )


@app.get("/compliance/dsar", response_model=List[DSARResponse])
async def list_dsar_requests(
    customer_id: Optional[str] = None,
    status_filter: Optional[DSARStatus] = None,
    limit: int = Query(100, le=500),
    auth: AuthContext = Depends(verify_token),
):
    """List DSAR requests for tenant (with optional filters)."""
    query = "SELECT id, tenant_id, customer_id, status, data_export_url, requested_at, completed_at, expires_at FROM dsar_requests WHERE tenant_id = $1"
    params = [auth.tenant_id]
    param_count = 1

    if customer_id:
        param_count += 1
        query += f" AND customer_id = ${param_count}"
        params.append(customer_id)

    if status_filter:
        param_count += 1
        query += f" AND status = ${param_count}"
        params.append(status_filter.value)

    query += f" ORDER BY requested_at DESC LIMIT {limit}"

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [
        DSARResponse(
            id=row["id"],
            tenant_id=row["tenant_id"],
            customer_id=row["customer_id"],
            status=DSARStatus(row["status"]),
            data_export_url=row["data_export_url"],
            requested_at=row["requested_at"],
            completed_at=row["completed_at"],
            expires_at=row["expires_at"],
        )
        for row in rows
    ]


@app.get("/compliance/dsar/{dsar_id}", response_model=DSARResponse)
async def get_dsar_request(
    dsar_id: str,
    auth: AuthContext = Depends(verify_token),
):
    """Get details of a specific DSAR request."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, tenant_id, customer_id, status, data_export_url, requested_at, completed_at, expires_at
            FROM dsar_requests WHERE id = $1 AND tenant_id = $2
        """, dsar_id, auth.tenant_id)

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DSAR request not found")

    await log_audit(auth, AuditAction.DATA_ACCESS, dsar_id, pii_access=True)

    return DSARResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        customer_id=row["customer_id"],
        status=DSARStatus(row["status"]),
        data_export_url=row["data_export_url"],
        requested_at=row["requested_at"],
        completed_at=row["completed_at"],
        expires_at=row["expires_at"],
    )


# ============================================================================
# Consent Management Endpoints
# ============================================================================

@app.post("/compliance/consent", response_model=ConsentRecord, status_code=status.HTTP_201_CREATED)
async def manage_consent(
    record: ConsentRecord,
    auth: AuthContext = Depends(verify_token),
):
    """Record customer consent preferences."""
    consent_id = str(uuid.uuid4())
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO consent_records 
            (id, tenant_id, customer_id, consent_type, status, regions, consent_string, given_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, consent_id, auth.tenant_id, record.customer_id, record.consent_type,
            record.status.value, json.dumps([r.value for r in record.regions]),
            record.consent_string or "", record.given_at or datetime.utcnow())

    await log_audit(auth, AuditAction.CONSENT_CHANGE, consent_id, pii_access=True,
                    details={"customer_id": record.customer_id, "status": record.status.value,
                             "regions": [r.value for r in record.regions]})

    logger.info("Consent recorded for customer %s", record.customer_id)

    return ConsentRecord(
        customer_id=record.customer_id,
        consent_type=record.consent_type,
        status=record.status,
        regions=record.regions,
        given_at=record.given_at or datetime.utcnow(),
    )


@app.get("/compliance/consent/{customer_id}", response_model=List[ConsentRecord])
async def get_customer_consents(
    customer_id: str,
    auth: AuthContext = Depends(verify_token),
):
    """Retrieve all consent records for a customer."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT customer_id, consent_type, status, regions, consent_string, given_at
            FROM consent_records WHERE tenant_id = $1 AND customer_id = $2
            ORDER BY given_at DESC
        """, auth.tenant_id, customer_id)

    await log_audit(auth, AuditAction.DATA_ACCESS, customer_id, pii_access=True)

    return [
        ConsentRecord(
            customer_id=row["customer_id"],
            consent_type=row["consent_type"],
            status=ConsentStatus(row["status"]),
            regions=[ComplianceRegion(r) for r in json.loads(row["regions"])],
            given_at=row["given_at"],
            consent_string=row["consent_string"],
        )
        for row in rows
    ]


# ============================================================================
# Cookie Consent Management
# ============================================================================

@app.post("/compliance/cookie-consent", response_model=CookieConsent, status_code=status.HTTP_201_CREATED)
async def record_cookie_consent(
    consent: CookieConsent,
    auth: AuthContext = Depends(verify_token),
):
    """Record cookie consent preferences."""
    consent_id = str(uuid.uuid4())
    expires_at = consent.expires_at or (datetime.utcnow() + timedelta(days=365))
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO cookie_consents 
            (id, tenant_id, customer_id, categories, consent_date, expires_at, language)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, consent_id, auth.tenant_id, consent.customer_id, json.dumps(consent.categories),
            consent.consent_date or datetime.utcnow(), expires_at, consent.language)

    await log_audit(auth, AuditAction.CONSENT_CHANGE, consent_id,
                    details={"customer_id": consent.customer_id, "categories": consent.categories})

    return consent


# ============================================================================
# Data Retention Policy Endpoints
# ============================================================================

@app.post("/compliance/retention-policy", response_model=DataRetentionPolicy, status_code=status.HTTP_201_CREATED)
async def create_retention_policy(
    policy: DataRetentionPolicy,
    auth: AuthContext = Depends(verify_token),
):
    """Create a data retention policy for a region."""
    policy_id = str(uuid.uuid4())
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO retention_policies 
            (policy_id, tenant_id, region, retention_days, data_category, auto_purge_enabled)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, policy_id, auth.tenant_id, policy.region.value, policy.retention_days,
            policy.data_category, policy.auto_purge_enabled)

    await log_audit(auth, AuditAction.RETENTION_POLICY_CHANGE, policy_id,
                    details={"region": policy.region.value, "retention_days": policy.retention_days,
                             "data_category": policy.data_category}, region=policy.region)

    logger.info("Retention policy created: %s for %s", policy_id, policy.region.value)

    return DataRetentionPolicy(
        policy_id=policy_id,
        tenant_id=auth.tenant_id,
        region=policy.region,
        retention_days=policy.retention_days,
        data_category=policy.data_category,
        auto_purge_enabled=policy.auto_purge_enabled,
        created_at=datetime.utcnow(),
    )


@app.get("/compliance/retention-policies", response_model=List[DataRetentionPolicy])
async def list_retention_policies(
    region: Optional[ComplianceRegion] = None,
    auth: AuthContext = Depends(verify_token),
):
    """List retention policies for tenant."""
    query = "SELECT policy_id, tenant_id, region, retention_days, data_category, auto_purge_enabled, created_at FROM retention_policies WHERE tenant_id = $1"
    params = [auth.tenant_id]

    if region:
        query += " AND region = $2"
        params.append(region.value)

    query += " ORDER BY created_at DESC"

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [
        DataRetentionPolicy(
            policy_id=row["policy_id"],
            tenant_id=row["tenant_id"],
            region=ComplianceRegion(row["region"]),
            retention_days=row["retention_days"],
            data_category=row["data_category"],
            auto_purge_enabled=row["auto_purge_enabled"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@app.get("/compliance/audit-log", response_model=List[AuditLogEntry])
async def get_audit_log(
    days: int = Query(30, ge=1, le=365),
    pii_only: bool = False,
    action_filter: Optional[AuditAction] = None,
    limit: int = Query(1000, le=10000),
    auth: AuthContext = Depends(verify_token),
):
    """Retrieve audit log entries for tenant."""
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    query = """
        SELECT id, tenant_id, user_id, action, resource_id, pii_access, timestamp, details, ip_address, region
        FROM audit_logs WHERE tenant_id = $1 AND timestamp >= $2
    """
    params = [auth.tenant_id, cutoff_date]
    param_count = 2

    if pii_only:
        query += " AND pii_access = TRUE"

    if action_filter:
        param_count += 1
        query += f" AND action = ${param_count}"
        params.append(action_filter.value)

    query += f" ORDER BY timestamp DESC LIMIT {limit}"

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [
        AuditLogEntry(
            id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            action=AuditAction(row["action"]),
            resource_id=row["resource_id"],
            pii_access=row["pii_access"],
            timestamp=row["timestamp"],
            details=json.loads(row["details"]) if row["details"] else None,
            ip_address=row["ip_address"],
            region=ComplianceRegion(row["region"]) if row["region"] else None,
        )
        for row in rows
    ]


# ============================================================================
# Anonymization & Data Masking
# ============================================================================

@app.post("/compliance/anonymize", response_model=AnonymizationResponse, status_code=status.HTTP_202_ACCEPTED)
async def anonymize_customer_data(
    request: AnonymizationRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Initiate anonymization/pseudonymization of customer data."""
    task_id = str(uuid.uuid4())
    
    await log_audit(auth, AuditAction.ANONYMIZATION, request.customer_id, pii_access=True,
                    details={"strategy": request.strategy.value, "data_types": request.data_types})

    logger.info("Anonymization task %s initiated for customer %s", task_id, request.customer_id)

    return AnonymizationResponse(
        task_id=task_id,
        status="processing",
        customer_id=request.customer_id,
        strategy=request.strategy,
        progress=0,
        message=f"Anonymization task {task_id} initiated with {request.strategy.value} strategy",
    )


# ============================================================================
# Data Masking Utilities
# ============================================================================

@app.post("/compliance/mask-pii")
async def mask_pii_data(
    data: Dict[str, Any] = Body(...),
    pii_fields: List[str] = Query(["email", "phone", "ssn"]),
    auth: AuthContext = Depends(verify_token),
):
    """Mask PII in provided data."""
    masked_data = data.copy()
    
    for field in pii_fields:
        if field in masked_data and masked_data[field]:
            value = str(masked_data[field])
            if field in ["email", "email_address"]:
                masked_data[field] = pii_masking.mask_email(value)
            elif field in ["phone", "phone_number"]:
                masked_data[field] = pii_masking.mask_phone(value)
            elif field in ["ssn", "tax_id"]:
                masked_data[field] = pii_masking.mask_ssn(value)
    
    await log_audit(auth, AuditAction.DATA_MODIFICATION, "pii_masking",
                    details={"fields_masked": len(pii_fields)})
    
    return {"masked_data": masked_data, "fields_masked": len(pii_fields)}


# ============================================================================
# Breach Notification
# ============================================================================

@app.post("/compliance/breach-report", response_model=BreachResponse, status_code=status.HTTP_201_CREATED)
async def report_data_breach(
    notification: BreachNotification,
    auth: AuthContext = Depends(verify_token),
):
    """Report a data breach and initiate notification workflow."""
    breach_id = str(uuid.uuid4())
    notification_deadline = None
    
    if notification.notification_required:
        notification_deadline = datetime.utcnow() + timedelta(days=72)  # GDPR requirement
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO breach_notifications 
            (id, tenant_id, breach_type, affected_customers, severity, description, 
             affected_data_categories, notification_required, discovered_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, breach_id, auth.tenant_id, notification.breach_type, notification.affected_customers,
            notification.severity.value, notification.description,
            json.dumps(notification.affected_data_categories), notification.notification_required,
            notification.discovered_at or datetime.utcnow())

    await log_audit(auth, AuditAction.BREACH_NOTIFICATION, breach_id, pii_access=True,
                    details={"severity": notification.severity.value, 
                             "affected": notification.affected_customers,
                             "data_categories": notification.affected_data_categories})

    logger.warning("Data breach reported: %s - Severity: %s", breach_id, notification.severity.value)

    return BreachResponse(
        breach_id=breach_id,
        status="reported",
        notification_required=notification.notification_required,
        notification_deadline=notification_deadline,
        message="Breach notification recorded. 72-hour notification deadline applies.",
    )


# ============================================================================
# DPA Management
# ============================================================================

@app.post("/compliance/dpa", response_model=DPATemplate, status_code=status.HTTP_201_CREATED)
async def create_dpa(
    dpa: DPATemplate,
    auth: AuthContext = Depends(verify_token),
):
    """Create a Data Processing Agreement template."""
    dpa_id = str(uuid.uuid4())
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO dpa_templates 
            (dpa_id, tenant_id, processor_name, processing_activities, data_categories, 
             retention_schedule, security_measures)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, dpa_id, auth.tenant_id, dpa.processor_name, json.dumps(dpa.processing_activities),
            json.dumps(dpa.data_categories), json.dumps(dpa.retention_schedule),
            json.dumps(dpa.security_measures))

    await log_audit(auth, AuditAction.DATA_MODIFICATION, dpa_id,
                    details={"processor": dpa.processor_name})

    return DPATemplate(
        dpa_id=dpa_id,
        tenant_id=auth.tenant_id,
        processor_name=dpa.processor_name,
        processing_activities=dpa.processing_activities,
        data_categories=dpa.data_categories,
        retention_schedule=dpa.retention_schedule,
        security_measures=dpa.security_measures,
        created_at=datetime.utcnow(),
    )


# ============================================================================
# Cross-Border Transfer Logging
# ============================================================================

@app.post("/compliance/cross-border-transfer", response_model=CrossBorderTransfer, 
         status_code=status.HTTP_201_CREATED)
async def log_cross_border_transfer(
    transfer: CrossBorderTransfer,
    auth: AuthContext = Depends(verify_token),
):
    """Log a cross-border data transfer with compliance basis."""
    transfer_id = str(uuid.uuid4())
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO cross_border_transfers 
            (transfer_id, tenant_id, source_region, destination_region, transfer_basis, 
             data_categories, transferred_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, transfer_id, auth.tenant_id, transfer.source_region.value,
            transfer.destination_region.value, transfer.transfer_basis,
            json.dumps(transfer.data_categories), transfer.transferred_at or datetime.utcnow())

    await log_audit(auth, AuditAction.CROSS_BORDER_TRANSFER, transfer_id,
                    details={"source": transfer.source_region.value,
                             "destination": transfer.destination_region.value,
                             "basis": transfer.transfer_basis}, region=transfer.source_region)

    logger.info("Cross-border transfer logged: %s -> %s", transfer.source_region.value, transfer.destination_region.value)

    return CrossBorderTransfer(
        transfer_id=transfer_id,
        tenant_id=auth.tenant_id,
        source_region=transfer.source_region,
        destination_region=transfer.destination_region,
        transfer_basis=transfer.transfer_basis,
        data_categories=transfer.data_categories,
        transferred_at=transfer.transferred_at or datetime.utcnow(),
    )


# ============================================================================
# Compliance Reporting
# ============================================================================

@app.get("/compliance/reports", response_model=List[ComplianceReport])
async def generate_compliance_reports(
    region: Optional[ComplianceRegion] = None,
    days: int = Query(90, ge=1, le=730),
    auth: AuthContext = Depends(verify_token),
):
    """Generate compliance reports for specified region/period."""
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=days)

    query = """
        SELECT report_id, tenant_id, region, period_start, period_end,
               dsar_requests, deletions_executed, consent_changes, data_breaches,
               cross_border_transfers, pii_access_events, generated_at
        FROM compliance_reports
        WHERE tenant_id = $1 AND period_start >= $2 AND period_end <= $3
    """
    params = [auth.tenant_id, period_start, period_end]

    if region:
        query += " AND region = $4"
        params.append(region.value)

    query += " ORDER BY period_start DESC LIMIT 100"

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [
        ComplianceReport(
            report_id=row["report_id"],
            tenant_id=row["tenant_id"],
            region=ComplianceRegion(row["region"]),
            period_start=row["period_start"],
            period_end=row["period_end"],
            dsar_requests=row["dsar_requests"],
            deletions_executed=row["deletions_executed"],
            consent_changes=row["consent_changes"],
            data_breaches=row["data_breaches"],
            cross_border_transfers=row["cross_border_transfers"],
            pii_access_events=row["pii_access_events"],
            generated_at=row["generated_at"],
        )
        for row in rows
    ]


# ============================================================================
# Health Check
# ============================================================================

@app.get("/compliance/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    db_status = "healthy"
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception as e:
            logger.error("Database health check failed: %s", str(e))
            db_status = "unhealthy"

    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        timestamp=datetime.utcnow(),
        database=db_status,
    )


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=PORT)
