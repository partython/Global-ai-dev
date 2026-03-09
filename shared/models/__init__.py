"""
Priya Global Platform - Shared Models Package

Central location for all Pydantic data models used across microservices.
Ensures consistent request/response formats and data validation.

USAGE:
    from shared.models import (
        TenantResponse,
        UserResponse,
        ConversationResponse,
        PaginatedResponse,
        ErrorResponse,
    )
"""

# ─── Base Models ───
from .base import (
    CreateDTO,
    ErrorResponse,
    HealthCheck,
    PaginatedResponse,
    PaginationParams,
    RequestMetadata,
    ResponseDTO,
    SortOrder,
    SuccessResponse,
    TenantModel,
    UpdateDTO,
    BaseDTO,
)

# ─── Tenant Models ───
from .tenant import (
    PlanTier,
    TenantCreate,
    TenantLimits,
    TenantResponse,
    TenantSettings,
    TenantUpdate,
    TenantWithLimits,
    get_limits_for_tier,
    PLAN_LIMITS,
)

# ─── User Models ───
from .user import (
    UserCreate,
    UserListResponse,
    UserPreferences,
    UserProfile,
    UserResponse,
    UserRole,
    UserSessionResponse,
    UserUpdate,
    can_user_access,
    ROLE_PERMISSIONS,
)

# ─── Conversation Models ───
from .conversation import (
    Channel,
    ConversationCreate,
    ConversationMetadata,
    ConversationMetrics,
    ConversationResponse,
    ConversationStatus,
    ConversationSummary,
    ConversationUpdate,
    ConversationWithLatestMessage,
    ChannelMetrics,
    MessageAttachment,
    MessageCreate,
    MessageResponse,
    MessageSummary,
    MessageType,
    MessageUpdate,
    SenderType,
)

# ─── Customer Models ───
from .customer import (
    CustomerAddress,
    CustomerContactInfo,
    CustomerCreate,
    CustomerResponse,
    CustomerSegment,
    CustomerSource,
    CustomerStatistics,
    CustomerSummary,
    CustomerUpdate,
)

__all__ = [
    # Base
    "CreateDTO",
    "UpdateDTO",
    "ResponseDTO",
    "BaseDTO",
    "ErrorResponse",
    "SuccessResponse",
    "HealthCheck",
    "PaginatedResponse",
    "PaginationParams",
    "RequestMetadata",
    "SortOrder",
    "TenantModel",
    # Tenant
    "PlanTier",
    "TenantCreate",
    "TenantUpdate",
    "TenantResponse",
    "TenantSettings",
    "TenantLimits",
    "TenantWithLimits",
    "get_limits_for_tier",
    "PLAN_LIMITS",
    # User
    "UserRole",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserProfile",
    "UserPreferences",
    "UserSessionResponse",
    "UserListResponse",
    "can_user_access",
    "ROLE_PERMISSIONS",
    # Conversation
    "Channel",
    "ConversationStatus",
    "ConversationCreate",
    "ConversationUpdate",
    "ConversationResponse",
    "ConversationSummary",
    "ConversationWithLatestMessage",
    "ConversationMetadata",
    "ConversationMetrics",
    "MessageType",
    "SenderType",
    "MessageAttachment",
    "MessageCreate",
    "MessageUpdate",
    "MessageResponse",
    "MessageSummary",
    "ChannelMetrics",
    # Customer
    "CustomerSegment",
    "CustomerSource",
    "CustomerContactInfo",
    "CustomerAddress",
    "CustomerCreate",
    "CustomerUpdate",
    "CustomerResponse",
    "CustomerSummary",
    "CustomerStatistics",
]
