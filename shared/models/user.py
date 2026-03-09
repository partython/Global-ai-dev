"""
User Models

Represents user (team member) entities in the platform.
Includes roles, permissions, preferences, and profile information.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from .base import CreateDTO, ResponseDTO, UpdateDTO


# ─── Enums ───

class UserRole(str, Enum):
    """User roles with escalating permission levels."""
    OWNER = "owner"           # Full access, billing control
    ADMIN = "admin"           # All features, user management
    MANAGER = "manager"       # Team management, basic analytics
    AGENT = "agent"           # Conversation handling only
    VIEWER = "viewer"         # Read-only access


# ─── Models ───

class UserProfile(BaseModel):
    """User profile information."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)
    bio: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)
    department: Optional[str] = Field(None, max_length=100)

    @property
    def full_name(self) -> str:
        """Full name combined from first and last."""
        return f"{self.first_name} {self.last_name}".strip()

    class Config:
        json_schema_extra = {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "phone": "+1234567890",
                "department": "Support"
            }
        }


class UserPreferences(BaseModel):
    """User interface and notification preferences."""
    language: str = Field(default="en", min_length=2, max_length=5)
    timezone: str = Field(default="UTC")
    email_notifications: bool = Field(default=True)
    daily_digest: bool = Field(default=False)
    theme: str = Field(default="light", description="light | dark | auto")
    notifications_enabled: bool = Field(default=True)
    mute_all_until: Optional[datetime] = Field(None, description="Snooze notifications until")

    class Config:
        json_schema_extra = {
            "example": {
                "language": "en",
                "timezone": "America/New_York",
                "email_notifications": True,
                "theme": "dark"
            }
        }


class UserBase(BaseModel):
    """Base user data (shared between create/update/response)."""
    email: EmailStr
    profile: UserProfile
    role: UserRole
    is_active: bool = Field(default=True)
    is_email_verified: bool = Field(default=False)

    class Config:
        from_attributes = True


class UserCreate(CreateDTO):
    """Create user request."""
    email: EmailStr = Field(description="User email (must be unique per tenant)")
    password: str = Field(..., min_length=8, max_length=128, description="Password (will be hashed)")
    profile: UserProfile
    role: UserRole = Field(default=UserRole.AGENT)


class UserUpdate(UpdateDTO):
    """Update user request (PATCH - all fields optional)."""
    profile: Optional[UserProfile] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    preferences: Optional[UserPreferences] = None


class UserResponse(ResponseDTO):
    """User response with all metadata."""
    tenant_id: UUID = Field(description="User's tenant")
    email: EmailStr
    profile: UserProfile
    role: UserRole
    is_active: bool
    is_email_verified: bool
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    last_login_at: Optional[datetime] = Field(None)
    password_changed_at: Optional[datetime] = Field(None)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "tenant_id": "123e4567-e89b-12d3-a456-426614174001",
                "email": "john@acme.com",
                "profile": {
                    "first_name": "John",
                    "last_name": "Doe"
                },
                "role": "admin",
                "is_active": True,
                "is_email_verified": True,
                "created_at": "2026-03-06T10:30:00Z",
                "updated_at": "2026-03-06T10:30:00Z"
            }
        }


class UserSessionResponse(BaseModel):
    """User info returned during authentication."""
    user_id: UUID
    tenant_id: UUID
    email: EmailStr
    profile: UserProfile
    role: UserRole
    is_active: bool
    is_email_verified: bool
    preferences: UserPreferences
    access_token: str = Field(description="JWT access token")
    refresh_token: str = Field(description="JWT refresh token")
    token_expires_at: datetime = Field(description="Access token expiration")


class UserListResponse(BaseModel):
    """User info for list endpoints (less detailed than full response)."""
    id: UUID
    email: EmailStr
    profile: UserProfile
    role: UserRole
    is_active: bool
    is_email_verified: bool
    last_login_at: Optional[datetime] = None


# ─── Permission Utilities ───

ROLE_PERMISSIONS = {
    UserRole.OWNER: {
        "all_features": True,
        "manage_billing": True,
        "delete_tenant": True,
        "invite_users": True,
        "manage_users": True,
        "view_analytics": True,
        "access_api": True,
    },
    UserRole.ADMIN: {
        "manage_users": True,
        "invite_users": True,
        "view_analytics": True,
        "access_api": True,
        "manage_channels": True,
        "manage_workflows": True,
    },
    UserRole.MANAGER: {
        "invite_users": True,
        "view_analytics": True,
        "manage_team": True,
        "access_api": False,
    },
    UserRole.AGENT: {
        "handle_conversations": True,
        "access_api": False,
    },
    UserRole.VIEWER: {
        "view_only": True,
        "access_api": False,
    },
}


def can_user_access(role: UserRole, permission: str) -> bool:
    """Check if user role has a specific permission."""
    permissions = ROLE_PERMISSIONS.get(role, {})
    return permissions.get(permission, False)
