"""
Priya Global — Tenant Configuration Service
Port: 9042

The critical bridge between onboarding and actual system configuration.
When a tenant completes onboarding, this service:
  1. Hydrates tenant profile (industry, timezone, currency, compliance)
  2. Provisions channel connections (WhatsApp, Email, SMS, Voice, WebChat)
  3. Generates tenant-scoped AI configuration (prompts, intents, persona)
  4. Sets up Redis cache namespaces
  5. Manages tenant lifecycle state machine
  6. Stores & rotates per-tenant channel credentials (encrypted)

This service is the SINGLE SOURCE OF TRUTH for tenant configuration.
All other services read tenant config from Redis cache (populated by this service).
"""

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import asyncpg
import jwt as pyjwt
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
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
logger = logging.getLogger("priya.tenant_config")

DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://app.currentglobal.com,https://admin.currentglobal.com"
).split(",")
CREDENTIAL_ENCRYPTION_KEY = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")
REDIS_URL = os.getenv("REDIS_URL", "")

# Validate at startup
if not JWT_SECRET:
    logger.warning("JWT_SECRET not configured — authentication will reject all requests")
if not DATABASE_URL:
    logger.warning("DATABASE_URL not configured — running in memory-only mode")
if not CREDENTIAL_ENCRYPTION_KEY:
    logger.warning("CREDENTIAL_ENCRYPTION_KEY not set — channel credentials cannot be encrypted")


# ============================================================================
# INDUSTRY TAXONOMY — ISO/NAICS-aligned standard categories
# ============================================================================

INDUSTRY_TAXONOMY = {
    "ecommerce": {
        "label": "E-Commerce & Retail",
        "default_intents": [
            "product_inquiry", "order_status", "returns_refunds", "pricing",
            "shipping_info", "cart_recovery", "product_recommendation",
            "inventory_check", "discount_inquiry", "size_guide"
        ],
        "escalation_triggers": [
            "damaged_product", "wrong_item", "refund_delayed", "payment_failed",
            "fraud_report", "legal_complaint"
        ],
        "ai_tone_default": "friendly_professional",
        "workflows": ["cart_abandonment", "order_followup", "review_request", "reorder_reminder"],
    },
    "healthcare": {
        "label": "Healthcare & Medical",
        "default_intents": [
            "appointment_booking", "appointment_reschedule", "symptom_inquiry",
            "prescription_refill", "insurance_query", "doctor_availability",
            "lab_results", "billing_inquiry", "treatment_info", "emergency_redirect"
        ],
        "escalation_triggers": [
            "emergency_symptoms", "medication_reaction", "urgent_pain",
            "mental_health_crisis", "insurance_denial", "legal_complaint"
        ],
        "ai_tone_default": "empathetic_professional",
        "workflows": ["appointment_reminder", "followup_care", "prescription_reminder", "satisfaction_survey"],
        "compliance_notes": "HIPAA compliance required. AI must never diagnose. Always redirect emergencies.",
    },
    "real_estate": {
        "label": "Real Estate & Property",
        "default_intents": [
            "property_inquiry", "schedule_viewing", "price_negotiation",
            "mortgage_info", "neighborhood_info", "documentation_status",
            "rental_inquiry", "maintenance_request", "lease_renewal"
        ],
        "escalation_triggers": [
            "legal_dispute", "contract_issue", "payment_default",
            "safety_concern", "discrimination_complaint"
        ],
        "ai_tone_default": "professional_consultative",
        "workflows": ["viewing_followup", "offer_tracking", "lease_expiry_reminder", "market_update"],
    },
    "education": {
        "label": "Education & Training",
        "default_intents": [
            "course_inquiry", "enrollment", "schedule_info", "fee_structure",
            "certificate_request", "faculty_info", "exam_schedule",
            "assignment_help", "placement_inquiry", "feedback"
        ],
        "escalation_triggers": [
            "harassment_report", "discrimination", "safety_concern",
            "fee_dispute", "credential_fraud"
        ],
        "ai_tone_default": "supportive_informative",
        "workflows": ["enrollment_followup", "assignment_reminder", "exam_prep", "alumni_engagement"],
    },
    "restaurant": {
        "label": "Restaurant & Food Service",
        "default_intents": [
            "menu_inquiry", "reservation", "order_takeout", "delivery_status",
            "allergy_info", "special_requests", "catering_inquiry",
            "feedback", "loyalty_points", "operating_hours"
        ],
        "escalation_triggers": [
            "food_poisoning", "allergy_reaction", "wrong_order",
            "foreign_object", "billing_dispute"
        ],
        "ai_tone_default": "warm_casual",
        "workflows": ["reservation_confirmation", "order_followup", "loyalty_reward", "seasonal_promotion"],
    },
    "finance": {
        "label": "Financial Services & Banking",
        "default_intents": [
            "account_inquiry", "transaction_status", "loan_inquiry",
            "investment_info", "card_services", "insurance_query",
            "dispute_filing", "kyc_update", "interest_rates", "branch_info"
        ],
        "escalation_triggers": [
            "fraud_suspected", "unauthorized_transaction", "account_locked",
            "identity_theft", "regulatory_complaint", "legal_action"
        ],
        "ai_tone_default": "formal_trustworthy",
        "workflows": ["payment_reminder", "kyc_renewal", "investment_update", "fraud_alert"],
        "compliance_notes": "Financial regulations apply. AI must not provide investment advice. PCI-DSS for card data.",
    },
    "automotive": {
        "label": "Automotive & Dealership",
        "default_intents": [
            "vehicle_inquiry", "test_drive_booking", "service_appointment",
            "parts_inquiry", "pricing_negotiation", "financing_options",
            "trade_in_value", "warranty_info", "recall_info", "insurance_quote"
        ],
        "escalation_triggers": [
            "safety_recall", "lemon_law", "warranty_denial",
            "accident_report", "financing_dispute"
        ],
        "ai_tone_default": "professional_enthusiastic",
        "workflows": ["test_drive_followup", "service_reminder", "lease_expiry", "new_model_alert"],
    },
    "travel": {
        "label": "Travel & Hospitality",
        "default_intents": [
            "booking_inquiry", "reservation_modify", "cancellation",
            "pricing_info", "availability_check", "loyalty_program",
            "special_requests", "local_info", "transport_info", "feedback"
        ],
        "escalation_triggers": [
            "medical_emergency", "safety_incident", "lost_luggage",
            "overbooking", "discrimination", "natural_disaster"
        ],
        "ai_tone_default": "warm_professional",
        "workflows": ["booking_confirmation", "pre_arrival", "checkout_followup", "loyalty_milestone"],
    },
    "saas": {
        "label": "SaaS & Technology",
        "default_intents": [
            "product_demo", "pricing_plans", "feature_inquiry", "technical_support",
            "integration_help", "account_management", "billing_inquiry",
            "upgrade_request", "bug_report", "api_documentation"
        ],
        "escalation_triggers": [
            "data_breach", "service_outage", "data_loss",
            "contract_dispute", "security_vulnerability", "compliance_audit"
        ],
        "ai_tone_default": "technical_friendly",
        "workflows": ["trial_conversion", "onboarding_drip", "feature_announcement", "renewal_reminder"],
    },
    "professional_services": {
        "label": "Professional Services (Legal, Consulting, Accounting)",
        "default_intents": [
            "consultation_booking", "service_inquiry", "pricing_estimate",
            "document_request", "case_status", "billing_inquiry",
            "referral", "feedback", "expertise_inquiry", "availability"
        ],
        "escalation_triggers": [
            "malpractice_claim", "conflict_of_interest", "deadline_missed",
            "confidentiality_breach", "fee_dispute"
        ],
        "ai_tone_default": "formal_professional",
        "workflows": ["consultation_followup", "document_reminder", "invoice_reminder", "client_check_in"],
    },
    "other": {
        "label": "Other / Custom",
        "default_intents": [
            "general_inquiry", "pricing", "appointment_booking",
            "feedback", "complaint", "product_info",
            "support_request", "billing", "availability", "contact_human"
        ],
        "escalation_triggers": [
            "legal_threat", "safety_concern", "fraud_report",
            "discrimination", "urgent_complaint"
        ],
        "ai_tone_default": "friendly_professional",
        "workflows": ["followup", "satisfaction_survey", "re_engagement"],
    },
}


# ============================================================================
# COUNTRY / COMPLIANCE REGISTRY
# ============================================================================

COUNTRY_COMPLIANCE_MAP = {
    # Format: country_code → {timezone, currency, compliance_framework, data_residency, language_default}
    "IN": {"timezone": "Asia/Kolkata", "currency": "INR", "compliance": "DPDPA", "residency": "ap-south-1", "language": "en"},
    "US": {"timezone": "America/New_York", "currency": "USD", "compliance": "CCPA", "residency": "us-east-1", "language": "en"},
    "GB": {"timezone": "Europe/London", "currency": "GBP", "compliance": "UK_GDPR", "residency": "eu-west-2", "language": "en"},
    "DE": {"timezone": "Europe/Berlin", "currency": "EUR", "compliance": "GDPR", "residency": "eu-central-1", "language": "de"},
    "FR": {"timezone": "Europe/Paris", "currency": "EUR", "compliance": "GDPR", "residency": "eu-west-1", "language": "fr"},
    "JP": {"timezone": "Asia/Tokyo", "currency": "JPY", "compliance": "APPI", "residency": "ap-northeast-1", "language": "ja"},
    "AU": {"timezone": "Australia/Sydney", "currency": "AUD", "compliance": "APPs", "residency": "ap-southeast-2", "language": "en"},
    "BR": {"timezone": "America/Sao_Paulo", "currency": "BRL", "compliance": "LGPD", "residency": "sa-east-1", "language": "pt"},
    "CA": {"timezone": "America/Toronto", "currency": "CAD", "compliance": "PIPEDA", "residency": "ca-central-1", "language": "en"},
    "AE": {"timezone": "Asia/Dubai", "currency": "AED", "compliance": "PDPL", "residency": "me-south-1", "language": "ar"},
    "SG": {"timezone": "Asia/Singapore", "currency": "SGD", "compliance": "PDPA", "residency": "ap-southeast-1", "language": "en"},
    "KR": {"timezone": "Asia/Seoul", "currency": "KRW", "compliance": "PIPA", "residency": "ap-northeast-2", "language": "ko"},
    "MX": {"timezone": "America/Mexico_City", "currency": "MXN", "compliance": "LFPDPPP", "residency": "us-east-1", "language": "es"},
    "ZA": {"timezone": "Africa/Johannesburg", "currency": "ZAR", "compliance": "POPIA", "residency": "af-south-1", "language": "en"},
    "SA": {"timezone": "Asia/Riyadh", "currency": "SAR", "compliance": "PDPL", "residency": "me-south-1", "language": "ar"},
    "IT": {"timezone": "Europe/Rome", "currency": "EUR", "compliance": "GDPR", "residency": "eu-south-1", "language": "it"},
    "ES": {"timezone": "Europe/Madrid", "currency": "EUR", "compliance": "GDPR", "residency": "eu-south-2", "language": "es"},
    "NL": {"timezone": "Europe/Amsterdam", "currency": "EUR", "compliance": "GDPR", "residency": "eu-west-1", "language": "nl"},
    "SE": {"timezone": "Europe/Stockholm", "currency": "SEK", "compliance": "GDPR", "residency": "eu-north-1", "language": "sv"},
    "CH": {"timezone": "Europe/Zurich", "currency": "CHF", "compliance": "FADP", "residency": "eu-central-1", "language": "de"},
    "ID": {"timezone": "Asia/Jakarta", "currency": "IDR", "compliance": "PDP", "residency": "ap-southeast-3", "language": "id"},
    "PH": {"timezone": "Asia/Manila", "currency": "PHP", "compliance": "DPA", "residency": "ap-southeast-1", "language": "en"},
    "NG": {"timezone": "Africa/Lagos", "currency": "NGN", "compliance": "NDPR", "residency": "af-south-1", "language": "en"},
    "KE": {"timezone": "Africa/Nairobi", "currency": "KES", "compliance": "DPA", "residency": "af-south-1", "language": "en"},
}

# Fallback for unlisted countries
DEFAULT_COUNTRY_CONFIG = {
    "timezone": "UTC", "currency": "USD", "compliance": "GDPR",
    "residency": "us-east-1", "language": "en"
}


# ============================================================================
# AI TONE PRESETS
# ============================================================================

AI_TONE_PRESETS = {
    "friendly_professional": {
        "description": "Warm but business-appropriate. Default for most industries.",
        "system_directive": "You are a friendly and professional assistant. Be warm, helpful, and personable while maintaining professionalism. Use conversational language but avoid slang. Address customers by name when known.",
        "temperature": 0.7,
    },
    "empathetic_professional": {
        "description": "Extra sensitivity for healthcare, counseling, crisis support.",
        "system_directive": "You are an empathetic and caring assistant. Show genuine concern for the person's wellbeing. Use gentle, reassuring language. Never minimize their concerns. Always acknowledge emotions before providing information.",
        "temperature": 0.6,
    },
    "formal_trustworthy": {
        "description": "Conservative and authoritative for finance, legal, government.",
        "system_directive": "You are a formal and trustworthy assistant. Use precise, professional language. Avoid casual expressions. Present information clearly and authoritatively. Always include relevant disclaimers.",
        "temperature": 0.4,
    },
    "warm_casual": {
        "description": "Relaxed and approachable for restaurants, entertainment, lifestyle.",
        "system_directive": "You are a warm and approachable assistant. Feel free to be casual and enthusiastic. Use friendly language, light humor when appropriate, and make the interaction feel personal and enjoyable.",
        "temperature": 0.8,
    },
    "professional_consultative": {
        "description": "Advisory tone for real estate, consulting, B2B.",
        "system_directive": "You are a knowledgeable consultant. Provide thoughtful, well-reasoned advice. Ask clarifying questions to understand needs. Present options with pros and cons. Be patient and thorough.",
        "temperature": 0.5,
    },
    "technical_friendly": {
        "description": "Tech-savvy but accessible for SaaS, developer tools.",
        "system_directive": "You are a technically knowledgeable assistant who communicates clearly. Explain technical concepts in accessible terms. Provide code examples when helpful. Be efficient and solution-oriented.",
        "temperature": 0.6,
    },
    "supportive_informative": {
        "description": "Patient and encouraging for education, training.",
        "system_directive": "You are a supportive and patient assistant. Encourage learning and curiosity. Break down complex topics into digestible pieces. Celebrate progress. Never make the person feel judged for not knowing something.",
        "temperature": 0.7,
    },
    "professional_enthusiastic": {
        "description": "Energetic but knowledgeable for automotive, sports, events.",
        "system_directive": "You are an enthusiastic and knowledgeable assistant. Show genuine excitement about the products and services. Be energetic but not pushy. Provide detailed information with passion.",
        "temperature": 0.7,
    },
    "warm_professional": {
        "description": "Hospitable and accommodating for travel, hospitality.",
        "system_directive": "You are a warm and accommodating assistant. Make every interaction feel like a hospitality experience. Anticipate needs, offer helpful suggestions, and ensure the person feels valued and well-taken-care-of.",
        "temperature": 0.7,
    },
    "formal_professional": {
        "description": "Strict formality for legal, government, compliance-heavy sectors.",
        "system_directive": "You are a formal and precise assistant. Use proper terminology. Be thorough and accurate. Always maintain professional boundaries. Include necessary legal or regulatory disclaimers.",
        "temperature": 0.3,
    },
}


# ============================================================================
# TENANT LIFECYCLE STATE MACHINE
# ============================================================================

class TenantState(str, Enum):
    CREATED = "created"                       # Auth just created the tenant
    EMAIL_VERIFIED = "email_verified"         # Owner verified email
    ONBOARDING_STARTED = "onboarding_started" # Started the wizard
    PROFILE_COMPLETE = "profile_complete"     # Business profile filled
    CHANNELS_PROVISIONED = "channels_provisioned"  # At least 1 channel ready
    AI_CONFIGURED = "ai_configured"           # AI persona + knowledge ready
    TEST_PASSED = "test_passed"               # Test conversation successful
    ACTIVE = "active"                         # Fully operational
    SUSPENDED = "suspended"                   # Payment failed / violation
    CANCELLED = "cancelled"                   # Tenant cancelled

# Valid state transitions
VALID_TRANSITIONS = {
    TenantState.CREATED: [TenantState.EMAIL_VERIFIED, TenantState.ONBOARDING_STARTED],
    TenantState.EMAIL_VERIFIED: [TenantState.ONBOARDING_STARTED],
    TenantState.ONBOARDING_STARTED: [TenantState.PROFILE_COMPLETE],
    TenantState.PROFILE_COMPLETE: [TenantState.CHANNELS_PROVISIONED],
    TenantState.CHANNELS_PROVISIONED: [TenantState.AI_CONFIGURED],
    TenantState.AI_CONFIGURED: [TenantState.TEST_PASSED],
    TenantState.TEST_PASSED: [TenantState.ACTIVE],
    TenantState.ACTIVE: [TenantState.SUSPENDED, TenantState.CANCELLED],
    TenantState.SUSPENDED: [TenantState.ACTIVE, TenantState.CANCELLED],
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
    role: str = "owner"


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
            role=payload.get("role", "owner"),
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_owner(auth: AuthContext = Depends(get_auth)) -> AuthContext:
    if auth.role not in ("owner", "super_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Owner access required")
    return auth


# ============================================================================
# DATABASE
# ============================================================================

db_pool: Optional[asyncpg.Pool] = None

SCHEMA_SQL = """
-- Tenant lifecycle state tracking
CREATE TABLE IF NOT EXISTS tenant_lifecycle (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL UNIQUE,
    current_state   TEXT NOT NULL DEFAULT 'created',
    previous_state  TEXT,
    state_data      JSONB DEFAULT '{}',
    transitioned_at TIMESTAMPTZ DEFAULT NOW(),
    transitioned_by TEXT
);

-- Full tenant configuration (hydrated from onboarding)
CREATE TABLE IF NOT EXISTS tenant_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           TEXT NOT NULL UNIQUE,
    business_name       TEXT NOT NULL,
    business_email      TEXT,
    business_phone      TEXT,
    business_url        TEXT,
    business_address    JSONB DEFAULT '{}',
    industry            TEXT NOT NULL DEFAULT 'other',
    industry_sub        TEXT,
    country_code        TEXT NOT NULL DEFAULT 'US',
    timezone            TEXT NOT NULL DEFAULT 'UTC',
    currency            TEXT NOT NULL DEFAULT 'USD',
    default_language    TEXT NOT NULL DEFAULT 'en',
    supported_languages TEXT[] DEFAULT ARRAY['en'],
    compliance_framework TEXT NOT NULL DEFAULT 'GDPR',
    data_residency_region TEXT DEFAULT 'us-east-1',
    business_size       TEXT DEFAULT 'small' CHECK (business_size IN ('solo', 'small', 'medium', 'large', 'enterprise')),
    logo_url            TEXT,
    brand_color_primary TEXT DEFAULT '#2563EB',
    brand_color_secondary TEXT DEFAULT '#1E40AF',
    favicon_url         TEXT,
    terms_accepted      BOOLEAN DEFAULT FALSE,
    terms_accepted_at   TIMESTAMPTZ,
    privacy_accepted    BOOLEAN DEFAULT FALSE,
    dpa_signed          BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Per-tenant AI configuration
CREATE TABLE IF NOT EXISTS tenant_ai_config (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL UNIQUE,
    brand_name      TEXT NOT NULL,
    ai_persona_name TEXT DEFAULT 'Assistant',
    tone_preset     TEXT NOT NULL DEFAULT 'friendly_professional',
    system_prompt_template TEXT NOT NULL,
    greeting_message TEXT,
    fallback_message TEXT DEFAULT 'I apologize, but I am not sure about that. Let me connect you with a team member who can help.',
    escalation_message TEXT DEFAULT 'Let me connect you with a specialist who can assist you better.',
    intents         JSONB NOT NULL DEFAULT '[]',
    escalation_triggers JSONB NOT NULL DEFAULT '[]',
    prohibited_topics JSONB DEFAULT '[]',
    custom_instructions TEXT,
    model_preference TEXT DEFAULT 'claude',
    temperature     DOUBLE PRECISION DEFAULT 0.7,
    max_tokens      INT DEFAULT 1024,
    knowledge_base_id TEXT,
    active_workflows JSONB DEFAULT '[]',
    operating_hours JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Channel connections — maps external identifiers to tenants
CREATE TABLE IF NOT EXISTS channel_connections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           TEXT NOT NULL,
    channel             TEXT NOT NULL CHECK (channel IN ('whatsapp', 'email', 'sms', 'voice', 'webchat', 'instagram', 'facebook', 'telegram')),
    channel_identifier  TEXT NOT NULL,
    display_name        TEXT,
    provider            TEXT,
    is_verified         BOOLEAN DEFAULT FALSE,
    is_active           BOOLEAN DEFAULT TRUE,
    webhook_url         TEXT,
    webhook_secret      TEXT,
    config_metadata     JSONB DEFAULT '{}',
    provisioned_at      TIMESTAMPTZ,
    verified_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel, channel_identifier)
);

-- Encrypted channel credentials
CREATE TABLE IF NOT EXISTS channel_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    channel         TEXT NOT NULL,
    credential_type TEXT NOT NULL,
    encrypted_value TEXT NOT NULL,
    key_version     INT DEFAULT 1,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    rotated_at      TIMESTAMPTZ,
    UNIQUE(tenant_id, channel, credential_type)
);

-- Tenant onboarding event log (immutable audit trail)
CREATE TABLE IF NOT EXISTS tenant_onboarding_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    event_data      JSONB DEFAULT '{}',
    performed_by    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE tenant_lifecycle ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_ai_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_onboarding_log ENABLE ROW LEVEL SECURITY;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tenant_lifecycle_tid ON tenant_lifecycle(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_profiles_tid ON tenant_profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_ai_config_tid ON tenant_ai_config(tenant_id);
CREATE INDEX IF NOT EXISTS idx_channel_conn_tid ON channel_connections(tenant_id, channel);
CREATE INDEX IF NOT EXISTS idx_channel_conn_identifier ON channel_connections(channel, channel_identifier);
CREATE INDEX IF NOT EXISTS idx_channel_creds_tid ON channel_credentials(tenant_id, channel);
CREATE INDEX IF NOT EXISTS idx_onboarding_log_tid ON tenant_onboarding_log(tenant_id, created_at DESC);
"""


async def init_db():
    global db_pool
    if not DATABASE_URL:
        return
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=15)
    async with db_pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Tenant config database initialized")


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Tenant Configuration Service started — %d industries, %d countries", len(INDUSTRY_TAXONOMY), len(COUNTRY_COMPLIANCE_MAP))
    yield
    if db_pool:
        await db_pool.close()


# ============================================================================
# APP
# ============================================================================

app = FastAPI(
    title="Priya Global — Tenant Configuration Service",
    version="1.0.0",
    lifespan=lifespan,
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="tenant_config")
init_sentry(service_name="tenant-config", service_port=9042)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="tenant-config")
app.add_middleware(TracingMiddleware)


cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "tenant-config",
        "industries": len(INDUSTRY_TAXONOMY),
        "countries": len(COUNTRY_COMPLIANCE_MAP),
    }


# ============================================================================
# REFERENCE DATA ENDPOINTS (public — used by frontend onboarding wizard)
# ============================================================================

@app.get("/api/v1/ref/industries")
async def list_industries():
    """List all supported industries for onboarding dropdown"""
    return {
        "industries": [
            {"id": k, "label": v["label"], "tone_default": v["ai_tone_default"]}
            for k, v in INDUSTRY_TAXONOMY.items()
        ]
    }


@app.get("/api/v1/ref/countries")
async def list_countries():
    """List all supported countries with compliance info"""
    return {
        "countries": [
            {
                "code": k,
                "timezone": v["timezone"],
                "currency": v["currency"],
                "compliance": v["compliance"],
                "language": v["language"],
            }
            for k, v in COUNTRY_COMPLIANCE_MAP.items()
        ]
    }


@app.get("/api/v1/ref/tones")
async def list_ai_tones():
    """List all AI tone presets"""
    return {
        "tones": [
            {"id": k, "description": v["description"]}
            for k, v in AI_TONE_PRESETS.items()
        ]
    }


# ============================================================================
# TENANT LIFECYCLE STATE MACHINE
# ============================================================================

@app.get("/api/v1/lifecycle")
async def get_lifecycle_state(auth: AuthContext = Depends(get_auth)):
    """Get current tenant lifecycle state"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db_pool.fetchrow(
        "SELECT * FROM tenant_lifecycle WHERE tenant_id = $1",
        auth.tenant_id,
    )
    if not row:
        return {"state": "created", "message": "Tenant not yet initialized. Begin onboarding."}

    return {
        "tenant_id": auth.tenant_id,
        "current_state": row["current_state"],
        "previous_state": row["previous_state"],
        "transitioned_at": row["transitioned_at"].isoformat() if row["transitioned_at"] else None,
        "next_steps": [s.value for s in VALID_TRANSITIONS.get(TenantState(row["current_state"]), [])],
    }


async def _transition_state(tenant_id: str, new_state: TenantState, performed_by: str, data: dict = None):
    """Internal: Advance the tenant state machine"""
    current = await db_pool.fetchval(
        "SELECT current_state FROM tenant_lifecycle WHERE tenant_id = $1",
        tenant_id,
    )

    if current:
        current_enum = TenantState(current)
        allowed = VALID_TRANSITIONS.get(current_enum, [])
        if new_state not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{current}' to '{new_state.value}'. Allowed: {[s.value for s in allowed]}"
            )
        await db_pool.execute(
            """
            UPDATE tenant_lifecycle
            SET current_state = $1, previous_state = $2, state_data = $3,
                transitioned_at = NOW(), transitioned_by = $4
            WHERE tenant_id = $5
            """,
            new_state.value, current, json.dumps(data or {}), performed_by, tenant_id,
        )
    else:
        await db_pool.execute(
            """
            INSERT INTO tenant_lifecycle (tenant_id, current_state, state_data, transitioned_by)
            VALUES ($1, $2, $3, $4)
            """,
            tenant_id, new_state.value, json.dumps(data or {}), performed_by,
        )

    # Audit log
    await db_pool.execute(
        """
        INSERT INTO tenant_onboarding_log (tenant_id, event_type, event_data, performed_by)
        VALUES ($1, $2, $3, $4)
        """,
        tenant_id, f"state_transition:{new_state.value}",
        json.dumps({"from": current, "to": new_state.value, **(data or {})}),
        performed_by,
    )
    logger.info("Tenant %s transitioned: %s → %s", tenant_id, current, new_state.value)


# ============================================================================
# ONBOARDING STEP 1: BUSINESS PROFILE
# ============================================================================

class BusinessProfileRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=200)
    business_email: Optional[str] = None
    business_phone: Optional[str] = None
    business_url: Optional[str] = None
    industry: str = Field(min_length=2, max_length=50)
    country_code: str = Field(min_length=2, max_length=2)
    default_language: str = Field(default="en", max_length=5)
    business_size: str = Field(default="small")
    terms_accepted: bool = True

    @field_validator("industry")
    @classmethod
    def validate_industry(cls, v):
        if v not in INDUSTRY_TAXONOMY:
            raise ValueError(f"Invalid industry. Must be one of: {', '.join(INDUSTRY_TAXONOMY.keys())}")
        return v

    @field_validator("country_code")
    @classmethod
    def validate_country(cls, v):
        v = v.upper()
        if v not in COUNTRY_COMPLIANCE_MAP and v not in ("XX",):  # XX = custom/other
            # Allow unlisted countries, will use defaults
            pass
        return v

    @field_validator("business_size")
    @classmethod
    def validate_size(cls, v):
        valid = ("solo", "small", "medium", "large", "enterprise")
        if v not in valid:
            raise ValueError(f"Must be one of: {', '.join(valid)}")
        return v


@app.post("/api/v1/onboarding/profile")
async def set_business_profile(body: BusinessProfileRequest, auth: AuthContext = Depends(require_owner)):
    """Step 1: Set business profile — hydrates tenant configuration"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    country_config = COUNTRY_COMPLIANCE_MAP.get(body.country_code.upper(), DEFAULT_COUNTRY_CONFIG)

    # Upsert tenant profile
    await db_pool.execute(
        """
        INSERT INTO tenant_profiles (
            tenant_id, business_name, business_email, business_phone, business_url,
            industry, country_code, timezone, currency, default_language,
            supported_languages, compliance_framework, data_residency_region,
            business_size, terms_accepted, terms_accepted_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW())
        ON CONFLICT (tenant_id) DO UPDATE SET
            business_name = $2, business_email = $3, business_phone = $4,
            business_url = $5, industry = $6, country_code = $7,
            timezone = $8, currency = $9, default_language = $10,
            supported_languages = $11, compliance_framework = $12,
            data_residency_region = $13, business_size = $14,
            terms_accepted = $15, terms_accepted_at = NOW(), updated_at = NOW()
        """,
        auth.tenant_id, body.business_name, body.business_email,
        body.business_phone, body.business_url, body.industry,
        body.country_code.upper(), country_config["timezone"],
        country_config["currency"], body.default_language,
        [body.default_language], country_config["compliance"],
        country_config["residency"], body.business_size,
        body.terms_accepted,
    )

    # Advance state
    await _transition_state(
        auth.tenant_id, TenantState.PROFILE_COMPLETE, auth.email,
        {"industry": body.industry, "country": body.country_code}
    )

    industry_data = INDUSTRY_TAXONOMY[body.industry]
    return {
        "message": "Business profile saved",
        "tenant_id": auth.tenant_id,
        "state": "profile_complete",
        "auto_configured": {
            "timezone": country_config["timezone"],
            "currency": country_config["currency"],
            "compliance": country_config["compliance"],
            "data_residency": country_config["residency"],
            "suggested_tone": industry_data["ai_tone_default"],
            "default_intents": len(industry_data["default_intents"]),
            "default_workflows": industry_data["workflows"],
        },
        "next_step": "channels",
    }


# ============================================================================
# ONBOARDING STEP 2: CHANNEL PROVISIONING
# ============================================================================

class ChannelProvisionRequest(BaseModel):
    channel: str
    channel_identifier: str = Field(min_length=1, max_length=500)
    display_name: Optional[str] = None
    provider: Optional[str] = None
    config_metadata: dict = {}

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v):
        valid = ("whatsapp", "email", "sms", "voice", "webchat", "instagram", "facebook", "telegram")
        if v not in valid:
            raise ValueError(f"Must be one of: {', '.join(valid)}")
        return v


@app.post("/api/v1/onboarding/channels")
async def provision_channel(body: ChannelProvisionRequest, auth: AuthContext = Depends(require_owner)):
    """Step 2: Provision a channel connection for the tenant"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # Generate webhook secret for this channel
    webhook_secret = secrets.token_hex(32)
    webhook_url = f"https://api.currentglobal.com/webhooks/{auth.tenant_id}/{body.channel}"

    try:
        row = await db_pool.fetchrow(
            """
            INSERT INTO channel_connections (
                tenant_id, channel, channel_identifier, display_name,
                provider, webhook_url, webhook_secret, config_metadata,
                provisioned_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
            ON CONFLICT (channel, channel_identifier) DO UPDATE SET
                tenant_id = $1, display_name = $4, provider = $5,
                webhook_url = $6, config_metadata = $8, updated_at = NOW()
            RETURNING *
            """,
            auth.tenant_id, body.channel, body.channel_identifier,
            body.display_name, body.provider, webhook_url,
            webhook_secret, json.dumps(body.config_metadata),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409,
            detail=f"This {body.channel} identifier is already connected to another tenant"
        )

    # Check if this is the first channel — transition state
    channel_count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM channel_connections WHERE tenant_id = $1 AND is_active = TRUE",
        auth.tenant_id,
    )

    if channel_count >= 1:
        # Try to transition (may already be in this state)
        try:
            await _transition_state(
                auth.tenant_id, TenantState.CHANNELS_PROVISIONED, auth.email,
                {"channel": body.channel, "total_channels": channel_count}
            )
        except HTTPException:
            pass  # Already in a later state, that's fine

    # Audit log
    await db_pool.execute(
        """
        INSERT INTO tenant_onboarding_log (tenant_id, event_type, event_data, performed_by)
        VALUES ($1, $2, $3, $4)
        """,
        auth.tenant_id, f"channel_provisioned:{body.channel}",
        json.dumps({"channel": body.channel, "identifier": body.channel_identifier}),
        auth.email,
    )

    return {
        "message": f"{body.channel} channel provisioned",
        "connection_id": str(row["id"]),
        "webhook_url": webhook_url,
        "webhook_secret": webhook_secret,
        "is_verified": False,
        "next_step": "Verify the channel to start receiving messages",
    }


@app.post("/api/v1/channels/{connection_id}/verify")
async def verify_channel(connection_id: str, auth: AuthContext = Depends(require_owner)):
    """Mark a channel connection as verified after provider validation"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        uuid.UUID(connection_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid connection ID")

    result = await db_pool.execute(
        """
        UPDATE channel_connections SET is_verified = TRUE, verified_at = NOW(), updated_at = NOW()
        WHERE id = $1::uuid AND tenant_id = $2
        """,
        connection_id, auth.tenant_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Channel connection not found")

    return {"message": "Channel verified", "connection_id": connection_id}


@app.get("/api/v1/channels")
async def list_channels(auth: AuthContext = Depends(get_auth)):
    """List all channel connections for the tenant"""
    if not db_pool:
        return {"channels": []}

    rows = await db_pool.fetch(
        """
        SELECT id, channel, channel_identifier, display_name, provider,
               is_verified, is_active, webhook_url, provisioned_at, verified_at
        FROM channel_connections
        WHERE tenant_id = $1
        ORDER BY channel, created_at
        """,
        auth.tenant_id,
    )
    return {"channels": [dict(r) for r in rows]}


# ============================================================================
# CHANNEL LOOKUP — Used by webhook handlers to find tenant
# ============================================================================

@app.get("/api/v1/channels/lookup")
async def lookup_tenant_by_channel(
    channel: str = Query(...),
    identifier: str = Query(...),
):
    """
    PUBLIC ENDPOINT — No auth required.
    Used by webhook handlers (WhatsApp, Email, SMS, Voice) to resolve
    which tenant owns a channel identifier.
    Rate-limited at the gateway level.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    valid_channels = ("whatsapp", "email", "sms", "voice", "webchat", "instagram", "facebook", "telegram")
    if channel not in valid_channels:
        raise HTTPException(status_code=400, detail="Invalid channel type")

    row = await db_pool.fetchrow(
        """
        SELECT tenant_id, channel, channel_identifier, display_name,
               provider, is_verified, is_active, config_metadata
        FROM channel_connections
        WHERE channel = $1 AND channel_identifier = $2
              AND is_active = TRUE
        """,
        channel, identifier,
    )

    if not row:
        raise HTTPException(status_code=404, detail="No tenant found for this channel identifier")

    if not row["is_verified"]:
        raise HTTPException(status_code=403, detail="Channel not verified")

    return {
        "tenant_id": row["tenant_id"],
        "channel": row["channel"],
        "display_name": row["display_name"],
        "provider": row["provider"],
        "config": json.loads(row["config_metadata"]) if isinstance(row["config_metadata"], str) else row["config_metadata"],
    }


# ============================================================================
# ONBOARDING STEP 3: AI CONFIGURATION
# ============================================================================

class AIConfigRequest(BaseModel):
    ai_persona_name: str = Field(default="Assistant", min_length=1, max_length=50)
    tone_preset: str = Field(default="friendly_professional")
    greeting_message: Optional[str] = None
    fallback_message: Optional[str] = None
    escalation_message: Optional[str] = None
    custom_instructions: Optional[str] = Field(default=None, max_length=2000)
    prohibited_topics: List[str] = []
    model_preference: str = Field(default="claude")
    operating_hours: dict = {}

    @field_validator("tone_preset")
    @classmethod
    def validate_tone(cls, v):
        if v not in AI_TONE_PRESETS:
            raise ValueError(f"Invalid tone. Must be one of: {', '.join(AI_TONE_PRESETS.keys())}")
        return v

    @field_validator("model_preference")
    @classmethod
    def validate_model(cls, v):
        valid = ("claude", "gpt4o", "gpt4o_mini")
        if v not in valid:
            raise ValueError(f"Must be one of: {', '.join(valid)}")
        return v


@app.post("/api/v1/onboarding/ai")
async def configure_ai(body: AIConfigRequest, auth: AuthContext = Depends(require_owner)):
    """Step 3: Configure tenant-scoped AI persona and behavior"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # Fetch tenant profile for industry-specific config
    profile = await db_pool.fetchrow(
        "SELECT business_name, industry, default_language FROM tenant_profiles WHERE tenant_id = $1",
        auth.tenant_id,
    )
    if not profile:
        raise HTTPException(status_code=400, detail="Complete business profile first")

    industry = profile["industry"]
    industry_data = INDUSTRY_TAXONOMY.get(industry, INDUSTRY_TAXONOMY["other"])
    tone_data = AI_TONE_PRESETS[body.tone_preset]

    # Build the tenant-specific system prompt
    system_prompt = _build_system_prompt(
        brand_name=profile["business_name"],
        persona_name=body.ai_persona_name,
        industry=industry,
        industry_data=industry_data,
        tone_data=tone_data,
        language=profile["default_language"],
        custom_instructions=body.custom_instructions,
        prohibited_topics=body.prohibited_topics,
        greeting=body.greeting_message,
        escalation_msg=body.escalation_message,
    )

    # Upsert AI config
    await db_pool.execute(
        """
        INSERT INTO tenant_ai_config (
            tenant_id, brand_name, ai_persona_name, tone_preset,
            system_prompt_template, greeting_message, fallback_message,
            escalation_message, intents, escalation_triggers,
            prohibited_topics, custom_instructions, model_preference,
            temperature, operating_hours
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
        ON CONFLICT (tenant_id) DO UPDATE SET
            brand_name = $2, ai_persona_name = $3, tone_preset = $4,
            system_prompt_template = $5, greeting_message = $6,
            fallback_message = $7, escalation_message = $8,
            intents = $9, escalation_triggers = $10,
            prohibited_topics = $11, custom_instructions = $12,
            model_preference = $13, temperature = $14,
            operating_hours = $15, updated_at = NOW()
        """,
        auth.tenant_id, profile["business_name"], body.ai_persona_name,
        body.tone_preset, system_prompt, body.greeting_message,
        body.fallback_message, body.escalation_message,
        json.dumps(industry_data["default_intents"]),
        json.dumps(industry_data["escalation_triggers"]),
        json.dumps(body.prohibited_topics), body.custom_instructions,
        body.model_preference, tone_data["temperature"],
        json.dumps(body.operating_hours),
    )

    # Advance state
    try:
        await _transition_state(
            auth.tenant_id, TenantState.AI_CONFIGURED, auth.email,
            {"tone": body.tone_preset, "persona": body.ai_persona_name}
        )
    except HTTPException:
        pass  # Already past this state

    return {
        "message": "AI configuration saved",
        "persona_name": body.ai_persona_name,
        "tone": body.tone_preset,
        "intents_configured": len(industry_data["default_intents"]),
        "escalation_triggers": len(industry_data["escalation_triggers"]),
        "system_prompt_preview": system_prompt[:300] + "...",
        "next_step": "test_conversation",
    }


def _build_system_prompt(
    brand_name: str,
    persona_name: str,
    industry: str,
    industry_data: dict,
    tone_data: dict,
    language: str,
    custom_instructions: Optional[str],
    prohibited_topics: List[str],
    greeting: Optional[str],
    escalation_msg: Optional[str],
) -> str:
    """Build a complete, tenant-scoped system prompt"""

    compliance_note = industry_data.get("compliance_notes", "")
    prohibited_block = ""
    if prohibited_topics:
        topics_str = ", ".join(prohibited_topics)
        prohibited_block = f"\n\nPROHIBITED TOPICS — Never discuss: {topics_str}. If asked, politely redirect."

    custom_block = ""
    if custom_instructions:
        custom_block = f"\n\nADDITIONAL INSTRUCTIONS FROM {brand_name.upper()}:\n{custom_instructions}"

    escalation_block = ""
    if industry_data.get("escalation_triggers"):
        triggers = ", ".join(industry_data["escalation_triggers"])
        esc_msg = escalation_msg or "Let me connect you with a specialist who can help."
        escalation_block = f"""

ESCALATION PROTOCOL:
If the conversation involves any of these triggers: {triggers}
Immediately respond with: "{esc_msg}"
Then flag the conversation for human handoff. Do NOT attempt to handle these yourself."""

    prompt = f"""You are {persona_name}, the AI assistant for {brand_name}.

IDENTITY:
- Your name is {persona_name}
- You represent {brand_name} exclusively
- You operate in the {industry_data['label']} industry
- Primary language: {language} (respond in the customer's language when possible)

BEHAVIOR:
{tone_data['system_directive']}

CAPABILITIES — You can help with:
{chr(10).join(f'- {intent.replace("_", " ").title()}' for intent in industry_data['default_intents'])}

GREETING:
When starting a conversation, use: "{greeting or f'Hello! Welcome to {brand_name}. How can I help you today?'}"

KNOWLEDGE BOUNDARIES:
- Only discuss topics related to {brand_name} and the {industry_data['label']} industry
- If asked about competitors, acknowledge them neutrally but redirect to {brand_name}'s offerings
- If you don't know something specific about {brand_name}, say so honestly and offer to connect with a team member
- Never fabricate product details, prices, or policies{prohibited_block}{escalation_block}

{f'COMPLIANCE: {compliance_note}' if compliance_note else ''}
{custom_block}

CONVERSATION RULES:
1. Always stay in character as {persona_name} for {brand_name}
2. Never reveal that you are an AI unless directly asked
3. Keep responses concise and actionable
4. Ask clarifying questions when the request is ambiguous
5. Track the conversation context and reference previous messages
6. If operating outside business hours, inform the customer and offer to take a message"""

    return prompt.strip()


# ============================================================================
# GET FULL TENANT AI CONFIG — Used by AI Engine at inference time
# ============================================================================

@app.get("/api/v1/ai-config")
async def get_ai_config(auth: AuthContext = Depends(get_auth)):
    """Fetch complete AI configuration for the tenant (called by AI Engine)"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    config = await db_pool.fetchrow(
        "SELECT * FROM tenant_ai_config WHERE tenant_id = $1",
        auth.tenant_id,
    )
    if not config:
        raise HTTPException(status_code=404, detail="AI not configured for this tenant. Complete onboarding first.")

    profile = await db_pool.fetchrow(
        "SELECT industry, country_code, default_language, supported_languages, compliance_framework FROM tenant_profiles WHERE tenant_id = $1",
        auth.tenant_id,
    )

    return {
        "tenant_id": auth.tenant_id,
        "brand_name": config["brand_name"],
        "persona_name": config["ai_persona_name"],
        "tone_preset": config["tone_preset"],
        "system_prompt": config["system_prompt_template"],
        "greeting_message": config["greeting_message"],
        "fallback_message": config["fallback_message"],
        "escalation_message": config["escalation_message"],
        "intents": json.loads(config["intents"]) if isinstance(config["intents"], str) else config["intents"],
        "escalation_triggers": json.loads(config["escalation_triggers"]) if isinstance(config["escalation_triggers"], str) else config["escalation_triggers"],
        "prohibited_topics": json.loads(config["prohibited_topics"]) if isinstance(config["prohibited_topics"], str) else config["prohibited_topics"],
        "custom_instructions": config["custom_instructions"],
        "model_preference": config["model_preference"],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "operating_hours": json.loads(config["operating_hours"]) if isinstance(config["operating_hours"], str) else config["operating_hours"],
        "industry": profile["industry"] if profile else None,
        "country": profile["country_code"] if profile else None,
        "language": profile["default_language"] if profile else "en",
        "compliance": profile["compliance_framework"] if profile else "GDPR",
    }


# ============================================================================
# ONBOARDING STEP 4: TEST CONVERSATION
# ============================================================================

@app.post("/api/v1/onboarding/test-pass")
async def mark_test_passed(auth: AuthContext = Depends(require_owner)):
    """Step 4: Mark test conversation as passed, advance to active"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    await _transition_state(
        auth.tenant_id, TenantState.TEST_PASSED, auth.email,
        {"tested_at": datetime.now(timezone.utc).isoformat()}
    )
    return {"message": "Test passed", "state": "test_passed", "next_step": "activate"}


@app.post("/api/v1/onboarding/activate")
async def activate_tenant(auth: AuthContext = Depends(require_owner)):
    """Final step: Activate the tenant for production"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # Verify all prerequisites
    profile = await db_pool.fetchval(
        "SELECT tenant_id FROM tenant_profiles WHERE tenant_id = $1", auth.tenant_id
    )
    if not profile:
        raise HTTPException(status_code=400, detail="Business profile not complete")

    channels = await db_pool.fetchval(
        "SELECT COUNT(*) FROM channel_connections WHERE tenant_id = $1 AND is_active = TRUE",
        auth.tenant_id,
    )
    if channels == 0:
        raise HTTPException(status_code=400, detail="At least one channel must be provisioned")

    ai_config = await db_pool.fetchval(
        "SELECT tenant_id FROM tenant_ai_config WHERE tenant_id = $1", auth.tenant_id
    )
    if not ai_config:
        raise HTTPException(status_code=400, detail="AI configuration not complete")

    # Activate
    await _transition_state(
        auth.tenant_id, TenantState.ACTIVE, auth.email,
        {"activated_at": datetime.now(timezone.utc).isoformat()}
    )

    logger.info("Tenant %s ACTIVATED by %s", auth.tenant_id, auth.email)

    return {
        "message": "Tenant activated! Your AI assistant is now live.",
        "tenant_id": auth.tenant_id,
        "state": "active",
        "channels_active": channels,
    }


# ============================================================================
# CREDENTIAL MANAGEMENT (encrypted storage)
# ============================================================================

class CredentialStore(BaseModel):
    channel: str
    credential_type: str = Field(min_length=1, max_length=100)
    credential_value: str = Field(min_length=1)
    expires_at: Optional[str] = None

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v):
        valid = ("whatsapp", "email", "sms", "voice", "webchat", "instagram", "facebook", "telegram")
        if v not in valid:
            raise ValueError(f"Invalid channel")
        return v


@app.post("/api/v1/credentials")
async def store_credential(body: CredentialStore, auth: AuthContext = Depends(require_owner)):
    """Store an encrypted channel credential"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    if not CREDENTIAL_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Encryption key not configured")

    # Simple HMAC-based encryption (in production: use AWS KMS or Vault)
    encrypted = _encrypt_credential(body.credential_value)

    expires = None
    if body.expires_at:
        try:
            expires = datetime.fromisoformat(body.expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expires_at format")

    await db_pool.execute(
        """
        INSERT INTO channel_credentials (tenant_id, channel, credential_type, encrypted_value, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (tenant_id, channel, credential_type)
        DO UPDATE SET encrypted_value = $4, expires_at = $5, rotated_at = NOW()
        """,
        auth.tenant_id, body.channel, body.credential_type, encrypted, expires,
    )

    return {"message": "Credential stored securely", "channel": body.channel, "type": body.credential_type}


@app.get("/api/v1/credentials/{channel}")
async def get_credentials(channel: str, auth: AuthContext = Depends(require_owner)):
    """List credential types for a channel (values are never returned in full)"""
    if not db_pool:
        return {"credentials": []}

    rows = await db_pool.fetch(
        """
        SELECT credential_type, expires_at, rotated_at, created_at
        FROM channel_credentials
        WHERE tenant_id = $1 AND channel = $2
        """,
        auth.tenant_id, channel,
    )
    return {"credentials": [dict(r) for r in rows]}


def _encrypt_credential(value: str) -> str:
    """Encrypt a credential value using AES-256-GCM (AEAD cipher).
    CRITICAL FIX: Replaced insecure XOR encryption with authenticated encryption.
    """
    if not CREDENTIAL_ENCRYPTION_KEY:
        raise ValueError("Encryption key not available")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

        # Derive a 256-bit key from the encryption key using PBKDF2
        salt = secrets.token_bytes(16)
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(CREDENTIAL_ENCRYPTION_KEY.encode())

        # Generate a random 12-byte nonce (96 bits) for GCM
        nonce = secrets.token_bytes(12)

        # Create cipher and encrypt with authentication
        cipher = AESGCM(key)
        ciphertext = cipher.encrypt(nonce, value.encode(), None)

        # Return format: salt:nonce:ciphertext (all hex-encoded)
        return f"{salt.hex()}:{nonce.hex()}:{ciphertext.hex()}"
    except ImportError:
        logger.error("cryptography library required for credential encryption")
        raise ValueError("Encryption library not available")


def _decrypt_credential(encrypted: str) -> str:
    """Decrypt a credential value using AES-256-GCM.
    CRITICAL FIX: Replaced insecure XOR decryption with authenticated decryption.
    """
    if not CREDENTIAL_ENCRYPTION_KEY:
        raise ValueError("Encryption key not available")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2



        parts = encrypted.split(":", 2)
        if len(parts) != 3:
            raise ValueError("Invalid encrypted format (expected salt:nonce:ciphertext)")

        salt = bytes.fromhex(parts[0])
        nonce = bytes.fromhex(parts[1])
        ciphertext = bytes.fromhex(parts[2])

        # Derive the same key using the stored salt
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(CREDENTIAL_ENCRYPTION_KEY.encode())

        # Decrypt with authentication verification
        cipher = AESGCM(key)
        plaintext = cipher.decrypt(nonce, ciphertext, None)
        return plaintext.decode()
    except ImportError:
        logger.error("cryptography library required for credential decryption")
        raise ValueError("Decryption library not available")
    except (ValueError, Exception) as e:
        logger.error("Credential decryption failed: %s", type(e).__name__)
        raise ValueError("Decryption failed")


# ============================================================================
# INTERNAL CREDENTIAL RETRIEVAL — used by channel services
# ============================================================================

@app.get("/api/v1/internal/credentials")
async def internal_get_credential(
    tenant_id: str = Query(...),
    channel: str = Query(...),
    credential_type: str = Query(...),
    auth: AuthContext = Depends(get_auth),
):
    """Internal endpoint for channel services to retrieve decrypted credentials.
    Only accessible by platform services (validated via JWT role)."""
    if auth.role not in ("service", "platform_admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Service-level access required")
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db_pool.fetchrow(
        """
        SELECT encrypted_value, expires_at
        FROM channel_credentials
        WHERE tenant_id = $1 AND channel = $2 AND credential_type = $3
        """,
        tenant_id, channel, credential_type,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Check expiry
    if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Credential expired")

    try:
        decrypted = _decrypt_credential(row["encrypted_value"])
    except ValueError:
        raise HTTPException(status_code=500, detail="Credential decryption failed")

    return {"value": decrypted, "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None}


# ============================================================================
# FULL TENANT CONFIG — aggregated read for caching
# ============================================================================

@app.get("/api/v1/config/full")
async def get_full_tenant_config(auth: AuthContext = Depends(get_auth)):
    """Fetch the complete tenant configuration bundle.
    This is what gets cached in Redis as t:{tenant_id}:config"""
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    profile = await db_pool.fetchrow(
        "SELECT * FROM tenant_profiles WHERE tenant_id = $1", auth.tenant_id
    )
    ai_config = await db_pool.fetchrow(
        "SELECT * FROM tenant_ai_config WHERE tenant_id = $1", auth.tenant_id
    )
    channels = await db_pool.fetch(
        """
        SELECT channel, channel_identifier, display_name, provider,
               is_verified, is_active, config_metadata
        FROM channel_connections WHERE tenant_id = $1 AND is_active = TRUE
        """,
        auth.tenant_id,
    )
    lifecycle = await db_pool.fetchrow(
        "SELECT current_state FROM tenant_lifecycle WHERE tenant_id = $1",
        auth.tenant_id,
    )

    return {
        "tenant_id": auth.tenant_id,
        "state": lifecycle["current_state"] if lifecycle else "unknown",
        "profile": dict(profile) if profile else None,
        "ai_config": dict(ai_config) if ai_config else None,
        "channels": [dict(c) for c in channels],
        "cache_key": f"t:{auth.tenant_id}:config",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# ONBOARDING AUDIT LOG
# ============================================================================

@app.get("/api/v1/onboarding/log")
async def get_onboarding_log(
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(require_owner),
):
    """View the onboarding event audit trail"""
    if not db_pool:
        return {"log": []}

    rows = await db_pool.fetch(
        """
        SELECT event_type, event_data, performed_by, created_at
        FROM tenant_onboarding_log
        WHERE tenant_id = $1
        ORDER BY created_at DESC LIMIT $2
        """,
        auth.tenant_id, limit,
    )
    return {"log": [dict(r) for r in rows]}
