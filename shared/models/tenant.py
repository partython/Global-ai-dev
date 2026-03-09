"""
Tenant Models

Represents tenant (organization/account) entities in the platform.
Includes subscription tiers, plan limits, and tenant settings.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, HttpUrl

from .base import CreateDTO, ResponseDTO, UpdateDTO


# ─── Enums ───

class PlanTier(str, Enum):
    """Subscription plan tiers."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


# ─── Models ───

class TenantLimits(BaseModel):
    """Resource limits based on plan tier."""
    max_users: int = Field(description="Maximum team members")
    max_conversations_per_month: int = Field(description="Monthly conversation limit")
    max_channels: int = Field(description="Number of channels")
    max_api_keys: int = Field(description="Number of API keys")
    max_knowledge_base_articles: int = Field(description="KB articles")
    enable_ai_features: bool = Field(description="AI engine access")
    enable_analytics: bool = Field(description="Advanced analytics")
    enable_webhooks: bool = Field(description="Webhook support")
    enable_custom_domain: bool = Field(description="Custom domain support")
    rate_limit_requests_per_minute: int = Field(description="API rate limit")


class TenantSettings(BaseModel):
    """Tenant-specific configuration."""
    company_name: str = Field(..., min_length=1, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    timezone: str = Field(default="UTC", description="IANA timezone")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO 4217")
    website: Optional[HttpUrl] = None
    support_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    logo_url: Optional[HttpUrl] = None
    description: Optional[str] = Field(None, max_length=1000)
    is_verified: bool = Field(default=False, description="Verified business")

    class Config:
        json_schema_extra = {
            "example": {
                "company_name": "Acme Corp",
                "industry": "Technology",
                "country": "US",
                "timezone": "America/New_York",
                "currency": "USD",
                "website": "https://acme.com",
                "support_email": "support@acme.com"
            }
        }


class TenantBase(BaseModel):
    """Base tenant data (shared between create/update/response)."""
    settings: TenantSettings
    plan_tier: PlanTier = Field(default=PlanTier.FREE)
    is_active: bool = Field(default=True)

    class Config:
        from_attributes = True


class TenantCreate(CreateDTO):
    """Create tenant request."""
    settings: TenantSettings = Field(description="Tenant configuration")
    plan_tier: PlanTier = Field(default=PlanTier.FREE, description="Initial plan tier")


class TenantUpdate(UpdateDTO):
    """Update tenant request (PATCH - all fields optional)."""
    settings: Optional[TenantSettings] = None
    plan_tier: Optional[PlanTier] = None
    is_active: Optional[bool] = None


class TenantResponse(ResponseDTO):
    """Tenant response with all metadata."""
    tenant_id: UUID = Field(description="Tenant UUID")
    settings: TenantSettings
    plan_tier: PlanTier
    limits: TenantLimits = Field(description="Current plan limits")
    is_active: bool
    stripe_customer_id: Optional[str] = Field(None, description="Billing system ID")
    trial_ends_at: Optional[datetime] = Field(None, description="Trial expiration date")
    onboarding_completed: bool = Field(default=False)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "tenant_id": "123e4567-e89b-12d3-a456-426614174000",
                "settings": {
                    "company_name": "Acme Corp",
                    "country": "US"
                },
                "plan_tier": "professional",
                "limits": {
                    "max_users": 10,
                    "max_conversations_per_month": 10000
                },
                "is_active": True,
                "created_at": "2026-03-06T10:30:00Z",
                "updated_at": "2026-03-06T10:30:00Z"
            }
        }


class TenantWithLimits(BaseModel):
    """Tenant data with current resource usage."""
    tenant_id: UUID
    settings: TenantSettings
    plan_tier: PlanTier
    limits: TenantLimits
    current_users: int = Field(description="Current user count")
    current_channels: int = Field(description="Current channel count")
    conversations_this_month: int = Field(description="Current month usage")
    storage_used_gb: float = Field(description="Storage usage in GB")


# ─── Plan Tier Utilities ───

PLAN_LIMITS = {
    PlanTier.FREE: TenantLimits(
        max_users=2,
        max_conversations_per_month=100,
        max_channels=1,
        max_api_keys=1,
        max_knowledge_base_articles=10,
        enable_ai_features=False,
        enable_analytics=False,
        enable_webhooks=False,
        enable_custom_domain=False,
        rate_limit_requests_per_minute=10,
    ),
    PlanTier.STARTER: TenantLimits(
        max_users=5,
        max_conversations_per_month=1000,
        max_channels=3,
        max_api_keys=5,
        max_knowledge_base_articles=100,
        enable_ai_features=True,
        enable_analytics=True,
        enable_webhooks=True,
        enable_custom_domain=False,
        rate_limit_requests_per_minute=100,
    ),
    PlanTier.PROFESSIONAL: TenantLimits(
        max_users=20,
        max_conversations_per_month=10000,
        max_channels=10,
        max_api_keys=20,
        max_knowledge_base_articles=1000,
        enable_ai_features=True,
        enable_analytics=True,
        enable_webhooks=True,
        enable_custom_domain=True,
        rate_limit_requests_per_minute=500,
    ),
    PlanTier.ENTERPRISE: TenantLimits(
        max_users=500,
        max_conversations_per_month=1000000,
        max_channels=100,
        max_api_keys=100,
        max_knowledge_base_articles=10000,
        enable_ai_features=True,
        enable_analytics=True,
        enable_webhooks=True,
        enable_custom_domain=True,
        rate_limit_requests_per_minute=5000,
    ),
}


def get_limits_for_tier(tier: PlanTier) -> TenantLimits:
    """Get resource limits for a given plan tier."""
    return PLAN_LIMITS.get(tier, PLAN_LIMITS[PlanTier.FREE])
