"""
API Key Models for Priya Global Platform

API Key Authentication Scheme:
- Format: priya_{environment}_{tenant_id_prefix}_{random_32_chars}
- Example: priya_prod_acme_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6

Features:
- Key rotation support (multiple active keys per tenant)
- Scope-based permissions (READ, WRITE, ADMIN)
- Rate limiting per key
- Key expiration support
- Usage auditing and logging
- Tenant isolation via prefix matching
"""

from enum import Enum
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


class APIKeyScope(str, Enum):
    """API Key permission scopes"""
    READ = "read"           # Read-only access (GET, HEAD, OPTIONS)
    WRITE = "write"         # Write access (POST, PUT, PATCH)
    ADMIN = "admin"         # Full administrative access
    WEBHOOK = "webhook"     # Webhook callback signing only


class APIKeyStatus(str, Enum):
    """API Key lifecycle status"""
    ACTIVE = "active"       # Currently valid and usable
    ROTATED = "rotated"     # Replaced by newer key (no longer used)
    REVOKED = "revoked"     # Explicitly disabled by user
    EXPIRED = "expired"     # Past expiration date


class RateLimitConfig(BaseModel):
    """Rate limiting configuration per API key"""
    requests_per_minute: int = Field(default=60, ge=1, le=10000)
    requests_per_hour: int = Field(default=3600, ge=1, le=600000)
    burst_size: int = Field(default=10, ge=1, le=100)

    class Config:
        description = "Rate limiting applied to this API key"


class APIKeyCreate(BaseModel):
    """Request to create a new API key"""
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable key name")
    scopes: List[APIKeyScope] = Field(
        default=[APIKeyScope.READ],
        description="Permission scopes for this key"
    )
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=3650,
        description="Optional expiration in days (max 10 years). None = never expires."
    )
    rate_limit: Optional[RateLimitConfig] = Field(
        default=None,
        description="Optional custom rate limiting. Uses tenant defaults if not specified."
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional custom metadata (JSON). Use for integration references, etc."
    )

    @validator("scopes")
    def validate_scopes(cls, v):
        if not v:
            raise ValueError("At least one scope required")
        return v


class APIKeyResponse(BaseModel):
    """Response when API key is created (includes the actual key, shown only once)"""
    key_id: str = Field(..., description="Unique identifier for the key")
    name: str
    api_key: str = Field(..., description="The actual API key. Save this - it won't be shown again!")
    scopes: List[APIKeyScope]
    rate_limit: RateLimitConfig
    status: APIKeyStatus
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    class Config:
        description = "New API key details (key shown only once)"


class APIKeyInfo(BaseModel):
    """API key information (without the actual key, for listing/viewing)"""
    key_id: str
    name: str
    key_preview: str = Field(..., description="First 8 + last 4 chars: priya_prod_****_****o5p6")
    scopes: List[APIKeyScope]
    rate_limit: RateLimitConfig
    status: APIKeyStatus
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    usage_count: int = Field(default=0, description="Total API calls made with this key")


class APIKeyContext(BaseModel):
    """Authenticated context after successful API key validation"""
    tenant_id: str = Field(..., description="Tenant ID extracted from key")
    key_id: str = Field(..., description="API key identifier")
    scopes: List[APIKeyScope] = Field(..., description="Allowed operations")
    rate_limit: RateLimitConfig = Field(..., description="Rate limiting for this request")
    expires_at: Optional[datetime] = Field(None, description="Key expiration time")
    can_read: bool = Field(..., description="User can perform read operations")
    can_write: bool = Field(..., description="User can perform write operations")
    is_admin: bool = Field(..., description="User has admin access")

    @property
    def can_webhook(self) -> bool:
        """Check if key can be used for webhook signing"""
        return APIKeyScope.WEBHOOK in self.scopes

    def has_scope(self, scope: APIKeyScope) -> bool:
        """Check if key has a specific scope"""
        return scope in self.scopes

    def requires_scope(self, scope: APIKeyScope) -> bool:
        """Raise exception if key doesn't have required scope"""
        if not self.has_scope(scope):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key scope '{scope.value}' required"
            )


class APIKeyUpdateRequest(BaseModel):
    """Request to update an API key"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    scopes: Optional[List[APIKeyScope]] = None
    rate_limit: Optional[RateLimitConfig] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        description = "Update API key configuration"


class APIKeyRotationRequest(BaseModel):
    """Request to rotate (replace) an API key"""
    expires_old_key_in_hours: int = Field(
        default=24,
        ge=1,
        le=720,
        description="Hours until the old key is revoked (grace period for migration)"
    )
    preserve_scopes: bool = Field(
        default=True,
        description="Copy scopes from old key to new key"
    )

    class Config:
        description = "Request to rotate an API key with grace period"


class APIKeyAuditLog(BaseModel):
    """Audit log entry for API key usage"""
    key_id: str
    tenant_id: str
    timestamp: datetime
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    path: str = Field(..., description="Request path")
    status_code: int
    response_time_ms: int
    ip_address: str = Field(..., description="Client IP (with privacy considerations)")
    user_agent: str = Field(..., description="Client user agent")
    error: Optional[str] = None
    rate_limit_remaining: int

    class Config:
        description = "Audit trail for API key operations"


class APIKeyListResponse(BaseModel):
    """Paginated list of API keys for a tenant"""
    keys: List[APIKeyInfo]
    total: int
    page: int
    per_page: int

    class Config:
        description = "Paginated list of API keys (secrets not included)"
