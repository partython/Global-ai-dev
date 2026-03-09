"""
Tenant Service for Priya Global Platform
Port: 9002

Manages:
- Workspace/Tenant configuration and settings
- Team member management and role-based access
- AI onboarding flow (conversational, AI-driven)
- Feature flags and plan management
- Usage tracking and limits enforcement
- Tenant isolation via RLS

SECURITY CRITICAL:
- PSI AI (Tenant #1) knowledge CANNOT leak to other tenants
- All operations use tenant_connection() with RLS
- Admin endpoints use strict RBAC enforcement
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, EmailStr, Field, validator

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import sanitize_input, sanitize_slug, sanitize_email, mask_pii
from shared.middleware.auth import AuthContext, get_auth, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logger = logging.getLogger("priya.tenant")

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────


class TenantBrandingUpdate(BaseModel):
    """Update tenant branding (logo, colors, favicon)."""
    logo_url: Optional[str] = Field(None, max_length=2048)
    favicon_url: Optional[str] = Field(None, max_length=2048)
    primary_color: Optional[str] = Field(None, regex=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: Optional[str] = Field(None, regex=r"^#[0-9A-Fa-f]{6}$")
    accent_color: Optional[str] = Field(None, regex=r"^#[0-9A-Fa-f]{6}$")


class AIPersonalityConfig(BaseModel):
    """AI personality and greeting configuration."""
    tone: str = Field(..., regex="^(friendly|professional|casual)$")
    greeting: str = Field(..., min_length=10, max_length=500)
    system_prompt: Optional[str] = Field(None, max_length=2000)
    language: str = Field(default="en", regex="^[a-z]{2}$")

    @validator("greeting", "system_prompt", pre=True)
    def sanitize_text(cls, v):
        if v:
            return sanitize_input(v, max_length=2000)
        return v


class TenantSettingsUpdate(BaseModel):
    """Update general tenant settings."""
    business_name: Optional[str] = Field(None, min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, min_length=2, max_length=2)
    timezone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, regex="^[a-z]{2}$")

    @validator("business_name", "industry", pre=True)
    def sanitize_text(cls, v):
        if v:
            return sanitize_input(v, max_length=255)
        return v


class TeamMemberRole(BaseModel):
    """Update team member role."""
    role: str = Field(..., regex="^(owner|admin|member)$")


class TeamMemberInvite(BaseModel):
    """Invite a new team member."""
    email: EmailStr
    role: str = Field(default="member", regex="^(admin|member)$")

    @validator("email", pre=True)
    def validate_email(cls, v):
        sanitized = sanitize_email(v)
        if not sanitized:
            raise ValueError("Invalid email address")
        return sanitized


class TransferOwnership(BaseModel):
    """Transfer tenant ownership to another member."""
    new_owner_email: EmailStr

    @validator("new_owner_email", pre=True)
    def validate_email(cls, v):
        sanitized = sanitize_email(v)
        if not sanitized:
            raise ValueError("Invalid email address")
        return sanitized


class OnboardingStartRequest(BaseModel):
    """Start an onboarding session."""
    business_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr

    @validator("business_name", pre=True)
    def sanitize_text(cls, v):
        if v:
            return sanitize_input(v, max_length=255)
        return v


class OnboardingStepRequest(BaseModel):
    """Process an onboarding step."""
    tenant_id: str
    step: int = Field(..., ge=1, le=6)
    response: str = Field(..., min_length=1, max_length=2000)

    @validator("response", pre=True)
    def sanitize_text(cls, v):
        if v:
            return sanitize_input(v, max_length=2000)
        return v


class FeatureFlagsUpdate(BaseModel):
    """Update feature flags for a tenant."""
    features: Dict[str, bool]


class PlanUpgradeRequest(BaseModel):
    """Upgrade or downgrade plan."""
    plan: str = Field(..., regex="^(starter|growth|enterprise)$")


class TenantResponse(BaseModel):
    """Tenant details response."""
    id: str
    business_name: str
    slug: str
    plan: str
    status: str
    owner_id: str
    owner_email: str
    created_at: str
    settings: Dict[str, Any]
    branding: Dict[str, Any]
    ai_config: Dict[str, Any]
    team_count: int


class TeamMemberResponse(BaseModel):
    """Team member response."""
    id: str
    email: str
    role: str
    joined_at: str
    invited_by: Optional[str]
    status: str


class UsageStatsResponse(BaseModel):
    """Usage statistics response."""
    tenant_id: str
    conversations_used: int
    conversations_limit: int
    storage_used_mb: float
    storage_limit_mb: float
    team_members_used: int
    team_members_limit: int
    channels_enabled: List[str]
    plan: str


class OnboardingStatusResponse(BaseModel):
    """Onboarding progress response."""
    tenant_id: str
    current_step: int
    completed: bool
    started_at: str
    completed_at: Optional[str]
    data: Dict[str, Any]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    port: int
    database: str
    timestamp: str


# ─────────────────────────────────────────────────────────────────────────────
# Plan Limits Configuration
# ─────────────────────────────────────────────────────────────────────────────

PLAN_LIMITS = {
    "starter": {
        "max_team_members": 2,
        "max_channels": 3,
        "max_conversations_per_month": 1000,
        "storage_limit_mb": 1000,
        "features": {
            "whatsapp": True,
            "email": True,
            "web_chat": True,
            "voice": False,
            "social": False,
            "sms": False,
            "ai_personality": True,
            "custom_branding": False,
            "api_access": False,
        }
    },
    "growth": {
        "max_team_members": 10,
        "max_channels": 999,
        "max_conversations_per_month": 5000,
        "storage_limit_mb": 10000,
        "features": {
            "whatsapp": True,
            "email": True,
            "web_chat": True,
            "voice": True,
            "social": True,
            "sms": True,
            "ai_personality": True,
            "custom_branding": True,
            "api_access": False,
        }
    },
    "enterprise": {
        "max_team_members": 999999,
        "max_channels": 999999,
        "max_conversations_per_month": 999999,
        "storage_limit_mb": 999999,
        "features": {
            "whatsapp": True,
            "email": True,
            "web_chat": True,
            "voice": True,
            "social": True,
            "sms": True,
            "ai_personality": True,
            "custom_branding": True,
            "api_access": True,
        }
    }
}

# Default AI personality for new tenants
DEFAULT_AI_CONFIG = {
    "tone": "friendly",
    "greeting": "Hi! I'm here to help. What can I do for you today?",
    "system_prompt": "You are a helpful AI assistant for a business.",
    "language": "en"
}

# ─────────────────────────────────────────────────────────────────────────────
# Onboarding Flow Steps
# ─────────────────────────────────────────────────────────────────────────────

ONBOARDING_STEPS = {
    1: {
        "name": "Welcome",
        "ai_message": "Welcome to Priya! I'm excited to help you set up your AI assistant. To get started, what's the name of your business?",
        "fields": ["business_name"],
    },
    2: {
        "name": "Industry",
        "ai_message": "Great! What industry does your business operate in? (e.g., e-commerce, healthcare, finance, retail)",
        "fields": ["industry"],
    },
    3: {
        "name": "Channels",
        "ai_message": "Which communication channels would you like to enable? (e.g., WhatsApp, Email, Web Chat, SMS, Social Media)",
        "fields": ["channels"],
    },
    4: {
        "name": "E-commerce",
        "ai_message": "Do you have an e-commerce platform? (Shopify, WooCommerce, Magento, or skip for now)",
        "fields": ["ecommerce_platform"],
    },
    5: {
        "name": "AI Personality",
        "ai_message": "What tone would you like your AI to use? (Friendly, Professional, or Casual)",
        "fields": ["ai_tone", "greeting"],
    },
    6: {
        "name": "Test Conversation",
        "ai_message": "Let's test your AI! Go ahead and send a message and I'll respond to show you how it works.",
        "fields": ["test_response"],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Tenant Service",
    description="Workspace and team management for Priya Global",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="tenant")
init_sentry(service_name="tenant", service_port=9002)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="tenant")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



# ─────────────────────────────────────────────────────────────────────────────
# Middleware & Startup/Shutdown
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Initialize database connection pool."""
    logger.info("Tenant Service starting on port %d", config.ports.tenant)

    await event_bus.startup()
    await db.initialize()
    logger.info("Database pool initialized")


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool."""
    logger.info("Tenant Service shutting down")
    shutdown_tracing()

    await event_bus.shutdown()
    await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Service health check."""
    return HealthResponse(
        status="healthy",
        service="tenant",
        port=config.ports.tenant,
        database="connected",
        timestamp=utc_now().isoformat(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tenant/Workspace Management
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """
    Get tenant details (owner/admin only).
    SECURITY: Enforces RBAC - only owner and admin can view.
    """
    # Verify user belongs to this tenant
    if auth.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access other tenant's data",
        )

    # Check role
    auth.require_role("owner", "admin")

    # Fetch tenant with RLS
    tenant = await db.fetch_one(
        tenant_id,
        """
        SELECT
            id, business_name, slug, plan, status, owner_id,
            owner_email, created_at, settings, branding, ai_config
        FROM tenants
        WHERE id = $1
        """,
        tenant_id,
    )

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Count team members
    team_count_row = await db.fetch_one(
        tenant_id,
        "SELECT COUNT(*) as count FROM team_members WHERE status = 'active'",
    )
    team_count = team_count_row['count'] if team_count_row else 0

    return TenantResponse(
        id=tenant['id'],
        business_name=tenant['business_name'],
        slug=tenant['slug'],
        plan=tenant['plan'],
        status=tenant['status'],
        owner_id=tenant['owner_id'],
        owner_email=tenant['owner_email'],
        created_at=tenant['created_at'],
        settings=tenant['settings'] or {},
        branding=tenant['branding'] or {},
        ai_config=tenant['ai_config'] or DEFAULT_AI_CONFIG,
        team_count=team_count,
    )


@app.put("/api/v1/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    updates: TenantSettingsUpdate,
    auth: AuthContext = Depends(get_auth),
):
    """
    Update tenant settings.
    SECURITY: Owner/admin only. Updates are persisted to settings JSONB column.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    # Build update query
    update_data = {}
    if updates.business_name:
        update_data['business_name'] = updates.business_name
    if updates.industry:
        update_data['industry'] = updates.industry
    if updates.country:
        update_data['country'] = updates.country
    if updates.timezone:
        update_data['timezone'] = updates.timezone
    if updates.language:
        update_data['language'] = updates.language

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updates provided",
        )

    # Fetch current settings
    tenant = await db.fetch_one(
        tenant_id,
        "SELECT settings FROM tenants WHERE id = $1",
        tenant_id,
    )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    current_settings = tenant['settings'] or {}
    current_settings.update(update_data)

    # Update tenant
    updated = await db.insert_returning(
        tenant_id,
        """
        UPDATE tenants
        SET settings = $1, updated_at = $2
        WHERE id = $3
        RETURNING id, business_name, slug, plan, status, owner_id, owner_email,
                  created_at, settings, branding, ai_config
        """,
        current_settings,
        utc_now().isoformat(),
        tenant_id,
    )

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Log audit event
    logger.info(
        "Tenant %s settings updated by user %s",
        mask_pii(tenant_id),
        mask_pii(auth.user_id),
    )

    team_count_row = await db.fetch_one(
        tenant_id,
        "SELECT COUNT(*) as count FROM team_members WHERE status = 'active'",
    )
    team_count = team_count_row['count'] if team_count_row else 0

    return TenantResponse(
        id=updated['id'],
        business_name=updated['business_name'],
        slug=updated['slug'],
        plan=updated['plan'],
        status=updated['status'],
        owner_id=updated['owner_id'],
        owner_email=updated['owner_email'],
        created_at=updated['created_at'],
        settings=updated['settings'] or {},
        branding=updated['branding'] or {},
        ai_config=updated['ai_config'] or DEFAULT_AI_CONFIG,
        team_count=team_count,
    )


@app.put("/api/v1/tenants/{tenant_id}/branding")
async def update_branding(
    tenant_id: str,
    branding: TenantBrandingUpdate,
    auth: AuthContext = Depends(get_auth),
):
    """
    Update tenant branding (logo, colors, favicon).
    SECURITY: Admin/owner only.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    # Fetch current branding
    tenant = await db.fetch_one(
        tenant_id,
        "SELECT branding FROM tenants WHERE id = $1",
        tenant_id,
    )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    current_branding = tenant['branding'] or {}

    # Update only provided fields
    if branding.logo_url:
        current_branding['logo_url'] = branding.logo_url
    if branding.favicon_url:
        current_branding['favicon_url'] = branding.favicon_url
    if branding.primary_color:
        current_branding['primary_color'] = branding.primary_color
    if branding.secondary_color:
        current_branding['secondary_color'] = branding.secondary_color
    if branding.accent_color:
        current_branding['accent_color'] = branding.accent_color

    await db.execute(
        tenant_id,
        """
        UPDATE tenants
        SET branding = $1, updated_at = $2
        WHERE id = $3
        """,
        current_branding,
        utc_now().isoformat(),
        tenant_id,
    )

    logger.info("Tenant %s branding updated", mask_pii(tenant_id))

    return {"status": "success", "branding": current_branding}


@app.put("/api/v1/tenants/{tenant_id}/ai-config")
async def update_ai_config(
    tenant_id: str,
    config_update: AIPersonalityConfig,
    auth: AuthContext = Depends(get_auth),
):
    """
    Configure AI personality, greeting, system prompt.
    SECURITY: Admin/owner only. Prevents AI config leakage to other tenants.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    # Build AI config
    ai_config = {
        "tone": config_update.tone,
        "greeting": config_update.greeting,
        "language": config_update.language,
    }

    if config_update.system_prompt:
        ai_config["system_prompt"] = config_update.system_prompt

    await db.execute(
        tenant_id,
        """
        UPDATE tenants
        SET ai_config = $1, updated_at = $2
        WHERE id = $3
        """,
        ai_config,
        utc_now().isoformat(),
        tenant_id,
    )

    # CRITICAL: Log this change for audit
    logger.info(
        "Tenant %s AI config updated (tone=%s) by user %s",
        mask_pii(tenant_id),
        config_update.tone,
        mask_pii(auth.user_id),
    )

    return {"status": "success", "ai_config": ai_config}


@app.get("/api/v1/tenants/{tenant_id}/usage", response_model=UsageStatsResponse)
async def get_usage_stats(
    tenant_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """
    Get current usage stats (conversations, storage, team members).
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin", "member")

    # Fetch tenant plan
    tenant = await db.fetch_one(
        tenant_id,
        "SELECT plan, settings FROM tenants WHERE id = $1",
        tenant_id,
    )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    plan = tenant['plan']
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['starter'])

    # Get team member count
    team_row = await db.fetch_one(
        tenant_id,
        "SELECT COUNT(*) as count FROM team_members WHERE status = 'active'",
    )
    team_count = team_row['count'] if team_row else 0

    # Get conversation count (from analytics/conversation tables)
    # For now, return 0 - this would be calculated from actual conversation data
    conversations_count = 0

    # Get storage used (would come from media/file storage service)
    storage_used_mb = 0.0

    # Get enabled channels from settings
    channels = tenant['settings'].get('channels', []) if tenant['settings'] else []

    return UsageStatsResponse(
        tenant_id=tenant_id,
        conversations_used=conversations_count,
        conversations_limit=limits['max_conversations_per_month'],
        storage_used_mb=storage_used_mb,
        storage_limit_mb=limits['storage_limit_mb'],
        team_members_used=team_count,
        team_members_limit=limits['max_team_members'],
        channels_enabled=channels,
        plan=plan,
    )


@app.delete("/api/v1/tenants/{tenant_id}")
async def soft_delete_tenant(
    tenant_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """
    Soft-delete tenant (owner only).
    SECURITY: Owner authorization only. Prevents accidental deletion.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner")

    # Soft delete
    await db.execute(
        tenant_id,
        """
        UPDATE tenants
        SET status = 'deleted', deleted_at = $1, updated_at = $1
        WHERE id = $2
        """,
        utc_now().isoformat(),
        tenant_id,
    )

    logger.warning(
        "Tenant %s soft-deleted by owner %s",
        mask_pii(tenant_id),
        mask_pii(auth.user_id),
    )

    return {"status": "success", "message": "Tenant marked for deletion"}


# ─────────────────────────────────────────────────────────────────────────────
# Team Management
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/tenants/{tenant_id}/members", response_model=List[TeamMemberResponse])
async def list_team_members(
    tenant_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """List all team members in the workspace."""
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    members = await db.fetch_all(
        tenant_id,
        """
        SELECT id, email, role, joined_at, invited_by, status
        FROM team_members
        WHERE status IN ('active', 'invited')
        ORDER BY joined_at DESC
        """,
    )

    return [
        TeamMemberResponse(
            id=m['id'],
            email=m['email'],
            role=m['role'],
            joined_at=m['joined_at'],
            invited_by=m['invited_by'],
            status=m['status'],
        )
        for m in members
    ]


@app.post("/api/v1/tenants/{tenant_id}/members/invite")
async def invite_team_member(
    tenant_id: str,
    invite: TeamMemberInvite,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = None,
):
    """
    Invite a new team member by email.
    SECURITY: Admin/owner only. Enforces max_team_members limit from plan.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    # Fetch tenant and plan limits
    tenant = await db.fetch_one(
        tenant_id,
        "SELECT plan FROM tenants WHERE id = $1",
        tenant_id,
    )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    plan = tenant['plan']
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['starter'])

    # Check team member limit
    team_count_row = await db.fetch_one(
        tenant_id,
        "SELECT COUNT(*) as count FROM team_members WHERE status IN ('active', 'invited')",
    )
    current_count = team_count_row['count'] if team_count_row else 0

    if current_count >= limits['max_team_members']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team member limit reached for current plan",
        )

    # Check if already invited/member
    existing = await db.fetch_one(
        tenant_id,
        "SELECT id FROM team_members WHERE email = $1 AND status IN ('active', 'invited')",
        invite.email,
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already invited or a member",
        )

    # Create invitation
    invitation_id = generate_uuid()
    await db.insert_returning(
        tenant_id,
        """
        INSERT INTO team_members
        (id, email, role, status, invited_by, invited_at, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        invitation_id,
        invite.email,
        invite.role,
        "invited",
        auth.user_id,
        utc_now().isoformat(),
        utc_now().isoformat(),
    )

    logger.info(
        "Team member invited: tenant=%s, email=%s, role=%s, invited_by=%s",
        mask_pii(tenant_id),
        mask_pii(invite.email),
        invite.role,
        mask_pii(auth.user_id),
    )

    # Background task: Send invitation email (would be handled by notification service)
    # For now, just log it

    return {
        "status": "success",
        "message": "Invitation sent successfully",
        "invitation_id": invitation_id,
    }


@app.put("/api/v1/tenants/{tenant_id}/members/{user_id}/role")
async def update_member_role(
    tenant_id: str,
    user_id: str,
    role_update: TeamMemberRole,
    auth: AuthContext = Depends(get_auth),
):
    """
    Change team member role.
    SECURITY: Admin/owner only. Cannot change owner role.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    # Fetch member
    member = await db.fetch_one(
        tenant_id,
        "SELECT role, email FROM team_members WHERE id = $1",
        user_id,
    )

    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Prevent changing owner role
    if member['role'] == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change owner role. Use transfer-ownership endpoint.",
        )

    # Update role
    await db.execute(
        tenant_id,
        """
        UPDATE team_members
        SET role = $1, updated_at = $2
        WHERE id = $3
        """,
        role_update.role,
        utc_now().isoformat(),
        user_id,
    )

    logger.info(
        "Team member role updated: tenant=%s, member=%s, new_role=%s, by=%s",
        mask_pii(tenant_id),
        mask_pii(member['email']),
        role_update.role,
        mask_pii(auth.user_id),
    )

    return {"status": "success", "new_role": role_update.role}


@app.delete("/api/v1/tenants/{tenant_id}/members/{user_id}")
async def remove_team_member(
    tenant_id: str,
    user_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """
    Remove a team member from workspace.
    SECURITY: Admin/owner only. Cannot remove owner.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    # Fetch member
    member = await db.fetch_one(
        tenant_id,
        "SELECT role, email FROM team_members WHERE id = $1",
        user_id,
    )

    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if member['role'] == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove owner. Use transfer-ownership first.",
        )

    # Soft delete
    await db.execute(
        tenant_id,
        """
        UPDATE team_members
        SET status = 'removed', removed_at = $1, updated_at = $1
        WHERE id = $2
        """,
        utc_now().isoformat(),
        user_id,
    )

    logger.info(
        "Team member removed: tenant=%s, member=%s, by=%s",
        mask_pii(tenant_id),
        mask_pii(member['email']),
        mask_pii(auth.user_id),
    )

    return {"status": "success", "message": "Member removed from team"}


@app.post("/api/v1/tenants/{tenant_id}/members/transfer-ownership")
async def transfer_ownership(
    tenant_id: str,
    transfer: TransferOwnership,
    auth: AuthContext = Depends(get_auth),
):
    """
    Transfer tenant ownership to another team member.
    SECURITY: Current owner only. Requires new owner to be an active team member.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner")

    # Find new owner in team
    new_owner = await db.fetch_one(
        tenant_id,
        "SELECT id, role FROM team_members WHERE email = $1 AND status = 'active'",
        transfer.new_owner_email,
    )

    if not new_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="New owner must be an active team member",
        )

    # Update tenant owner
    await db.execute(
        tenant_id,
        """
        UPDATE tenants
        SET owner_id = $1, owner_email = $2, updated_at = $3
        WHERE id = $4
        """,
        new_owner['id'],
        transfer.new_owner_email,
        utc_now().isoformat(),
        tenant_id,
    )

    # Change old owner to admin, new owner to owner
    await db.execute(
        tenant_id,
        """
        UPDATE team_members
        SET role = 'admin', updated_at = $1
        WHERE id = $2
        """,
        utc_now().isoformat(),
        auth.user_id,
    )

    await db.execute(
        tenant_id,
        """
        UPDATE team_members
        SET role = 'owner', updated_at = $1
        WHERE id = $2
        """,
        utc_now().isoformat(),
        new_owner['id'],
    )

    logger.warning(
        "Ownership transferred: tenant=%s, from=%s, to=%s",
        mask_pii(tenant_id),
        mask_pii(auth.user_id),
        mask_pii(new_owner['id']),
    )

    return {
        "status": "success",
        "message": "Ownership transferred successfully",
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI Onboarding Flow (Conversational)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v1/onboarding/start")
async def start_onboarding(request: OnboardingStartRequest):
    """
    Start an onboarding session. Returns AI greeting.
    Creates tenant record with onboarding state.
    """
    # Create tenant
    tenant_id = generate_uuid()
    tenant_slug = sanitize_slug(request.business_name)

    # Initialize onboarding state
    onboarding_state = {
        "step": 1,
        "started_at": utc_now().isoformat(),
        "completed": False,
        "data": {
            "business_name": request.business_name,
            "email": request.email,
        }
    }

    initial_settings = {
        "business_name": request.business_name,
        "onboarding": onboarding_state,
    }

    # Insert tenant (no tenant isolation needed for creation)
    async with db.admin_connection() as conn:
        await conn.execute(
            """
            INSERT INTO tenants
            (id, business_name, slug, plan, status, owner_email, owner_id,
             settings, ai_config, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            tenant_id,
            request.business_name,
            tenant_slug,
            "starter",  # Default plan
            "onboarding",
            request.email,
            generate_uuid(),  # Placeholder owner_id, will be updated after auth signup
            initial_settings,
            DEFAULT_AI_CONFIG,
            utc_now().isoformat(),
        )

    # Get AI message for step 1
    step_info = ONBOARDING_STEPS[1]

    logger.info(
        "Onboarding started: tenant=%s, email=%s, business=%s",
        mask_pii(tenant_id),
        mask_pii(request.email),
        request.business_name,
    )

    return {
        "tenant_id": tenant_id,
        "step": 1,
        "step_name": step_info["name"],
        "ai_message": step_info["ai_message"],
        "expected_fields": step_info["fields"],
    }


@app.post("/api/v1/onboarding/step")
async def process_onboarding_step(step_request: OnboardingStepRequest):
    """
    Process an onboarding step. The AI asks the next question.

    Flow:
    Step 1: Welcome (business name)
    Step 2: Industry
    Step 3: Channels
    Step 4: E-commerce connection
    Step 5: AI personality
    Step 6: Test conversation
    Step 7: Complete (go live)
    """
    tenant_id = step_request.tenant_id
    current_step = step_request.step
    user_response = step_request.response

    # Fetch tenant with onboarding state
    async with db.admin_connection() as conn:
        tenant = await conn.fetchrow(
            "SELECT settings FROM tenants WHERE id = $1",
            tenant_id,
        )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    settings = tenant['settings'] or {}
    onboarding = settings.get('onboarding', {})
    onboarding_data = onboarding.get('data', {})

    # Validate step
    if current_step < 1 or current_step >= 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid step number",
        )

    # Save user response
    step_key = ONBOARDING_STEPS[current_step]["name"].lower().replace(" ", "_")
    onboarding_data[step_key] = user_response

    # Determine next step
    next_step = current_step + 1
    is_complete = next_step > 6

    # Update onboarding state
    if is_complete:
        onboarding['completed'] = True
        onboarding['completed_at'] = utc_now().isoformat()
    else:
        onboarding['step'] = next_step

    onboarding['data'] = onboarding_data
    settings['onboarding'] = onboarding

    # Persist to database
    async with db.admin_connection() as conn:
        await conn.execute(
            """
            UPDATE tenants
            SET settings = $1, updated_at = $2
            WHERE id = $3
            """,
            settings,
            utc_now().isoformat(),
            tenant_id,
        )

    logger.info(
        "Onboarding step processed: tenant=%s, step=%d, next_step=%d",
        mask_pii(tenant_id),
        current_step,
        next_step,
    )

    if is_complete:
        return {
            "tenant_id": tenant_id,
            "step": current_step,
            "completed": True,
            "ai_message": "Congratulations! Your workspace is ready. Let's go live!",
            "next_action": "complete",
        }

    # Get AI message for next step
    step_info = ONBOARDING_STEPS[next_step]

    return {
        "tenant_id": tenant_id,
        "step": next_step,
        "step_name": step_info["name"],
        "ai_message": step_info["ai_message"],
        "expected_fields": step_info["fields"],
        "previous_response": user_response,
    }


@app.get("/api/v1/onboarding/status/{tenant_id}", response_model=OnboardingStatusResponse)
async def get_onboarding_status(tenant_id: str):
    """Get onboarding progress for a tenant."""
    async with db.admin_connection() as conn:
        tenant = await conn.fetchrow(
            "SELECT settings, created_at FROM tenants WHERE id = $1",
            tenant_id,
        )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    settings = tenant['settings'] or {}
    onboarding = settings.get('onboarding', {})

    return OnboardingStatusResponse(
        tenant_id=tenant_id,
        current_step=onboarding.get('step', 1),
        completed=onboarding.get('completed', False),
        started_at=onboarding.get('started_at', tenant['created_at']),
        completed_at=onboarding.get('completed_at'),
        data=onboarding.get('data', {}),
    )


@app.post("/api/v1/onboarding/complete")
async def complete_onboarding(
    tenant_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """
    Mark onboarding as complete. Transitions tenant to 'active'.
    SECURITY: Only owner can complete onboarding.
    """
    # Use admin connection to update
    async with db.admin_connection() as conn:
        tenant = await conn.fetchrow(
            "SELECT settings FROM tenants WHERE id = $1",
            tenant_id,
        )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    settings = tenant['settings'] or {}
    onboarding = settings.get('onboarding', {})
    onboarding['completed'] = True
    onboarding['completed_at'] = utc_now().isoformat()
    settings['onboarding'] = onboarding

    # Update tenant status
    async with db.admin_connection() as conn:
        await conn.execute(
            """
            UPDATE tenants
            SET status = 'active', settings = $1, updated_at = $2
            WHERE id = $3
            """,
            settings,
            utc_now().isoformat(),
            tenant_id,
        )

    logger.info("Onboarding completed: tenant=%s", mask_pii(tenant_id))

    return {
        "status": "success",
        "message": "Workspace is now active!",
        "tenant_id": tenant_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Feature Flags
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/tenants/{tenant_id}/features")
async def get_feature_flags(
    tenant_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get feature flags for tenant based on plan."""
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Fetch tenant plan
    tenant = await db.fetch_one(
        tenant_id,
        "SELECT plan FROM tenants WHERE id = $1",
        tenant_id,
    )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    plan = tenant['plan']
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['starter'])

    return {
        "plan": plan,
        "features": limits['features'],
    }


@app.put("/api/v1/tenants/{tenant_id}/features")
async def update_feature_flags(
    tenant_id: str,
    flags: FeatureFlagsUpdate,
    auth: AuthContext = Depends(get_auth),
):
    """
    Update feature flags (admin only).
    SECURITY: Admin cannot enable features beyond plan limits.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    # Fetch tenant
    tenant = await db.fetch_one(
        tenant_id,
        "SELECT plan, settings FROM tenants WHERE id = $1",
        tenant_id,
    )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    plan = tenant['plan']
    plan_features = PLAN_LIMITS[plan]['features']

    # Validate: cannot enable features beyond plan
    for feature, enabled in flags.features.items():
        if enabled and not plan_features.get(feature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Feature not available in current plan",
            )

    # Update settings
    settings = tenant['settings'] or {}
    settings['feature_flags'] = flags.features

    await db.execute(
        tenant_id,
        """
        UPDATE tenants
        SET settings = $1, updated_at = $2
        WHERE id = $3
        """,
        settings,
        utc_now().isoformat(),
        tenant_id,
    )

    logger.info("Feature flags updated: tenant=%s", mask_pii(tenant_id))

    return {
        "status": "success",
        "features": flags.features,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Plan Management
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/tenants/{tenant_id}/plan")
async def get_plan_details(
    tenant_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get current plan details and limits."""
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    tenant = await db.fetch_one(
        tenant_id,
        "SELECT plan FROM tenants WHERE id = $1",
        tenant_id,
    )

    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    plan = tenant['plan']
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS['starter'])

    return {
        "plan": plan,
        "limits": limits,
    }


@app.put("/api/v1/tenants/{tenant_id}/plan")
async def update_plan(
    tenant_id: str,
    plan_request: PlanUpgradeRequest,
    auth: AuthContext = Depends(get_auth),
):
    """
    Upgrade or downgrade plan (triggers billing).
    SECURITY: Owner/admin only. Would trigger billing service in production.
    """
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    auth.require_role("owner", "admin")

    new_plan = plan_request.plan

    if new_plan not in PLAN_LIMITS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan",
        )

    # TODO: Call billing service to process plan change
    # For now, just update the tenant record

    await db.execute(
        tenant_id,
        """
        UPDATE tenants
        SET plan = $1, updated_at = $2
        WHERE id = $3
        """,
        new_plan,
        utc_now().isoformat(),
        tenant_id,
    )

    logger.info(
        "Plan changed: tenant=%s, new_plan=%s, by=%s",
        mask_pii(tenant_id),
        new_plan,
        mask_pii(auth.user_id),
    )

    limits = PLAN_LIMITS[new_plan]

    return {
        "status": "success",
        "plan": new_plan,
        "limits": limits,
        "message": "Plan updated successfully",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Error Handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error("Unhandled exception: %s", str(exc), exc_info=True)
    return {
        "error": "Internal server error",
        "detail": str(exc) if config.debug else "An error occurred",
    }


if __name__ == "__main__":
    import uvicorn



    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.ports.tenant,
        log_level=config.log_level.lower(),
    )
