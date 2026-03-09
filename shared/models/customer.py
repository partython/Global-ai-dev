"""
Customer Models

Represents end customers/contacts that interact with the platform.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from .base import CreateDTO, ResponseDTO, UpdateDTO


# ─── Enums ───

class CustomerSegment(str, Enum):
    """Customer segmentation for targeting."""
    VIP = "vip"
    REGULAR = "regular"
    AT_RISK = "at_risk"
    PROSPECT = "prospect"
    CHURNED = "churned"


class CustomerSource(str, Enum):
    """How customer was acquired."""
    ORGANIC = "organic"
    PAID_AD = "paid_ad"
    REFERRAL = "referral"
    PARTNER = "partner"
    DIRECT = "direct"
    UNKNOWN = "unknown"


# ─── Models ───

class CustomerContactInfo(BaseModel):
    """Customer contact details."""
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    whatsapp: Optional[str] = Field(None, max_length=20)
    telegram: Optional[str] = Field(None, max_length=100)
    instagram: Optional[str] = Field(None, max_length=100)
    facebook: Optional[str] = Field(None, max_length=100)
    twitter: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=500)

    def primary_contact(self) -> Optional[str]:
        """Get first available contact method."""
        return self.email or self.phone or self.whatsapp


class CustomerAddress(BaseModel):
    """Physical address."""
    street: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, min_length=2, max_length=2)


class CustomerBase(BaseModel):
    """Base customer data."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    contact_info: CustomerContactInfo
    address: Optional[CustomerAddress] = None
    segment: CustomerSegment = Field(default=CustomerSegment.REGULAR)
    source: CustomerSource = Field(default=CustomerSource.UNKNOWN)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    is_blocked: bool = Field(default=False)
    tags: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CustomerCreate(CreateDTO):
    """Create customer request."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=255)
    contact_info: CustomerContactInfo
    address: Optional[CustomerAddress] = None
    segment: CustomerSegment = Field(default=CustomerSegment.REGULAR)
    source: CustomerSource = Field(default=CustomerSource.UNKNOWN)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class CustomerUpdate(UpdateDTO):
    """Update customer request (PATCH - all fields optional)."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    contact_info: Optional[CustomerContactInfo] = None
    address: Optional[CustomerAddress] = None
    segment: Optional[CustomerSegment] = None
    source: Optional[CustomerSource] = None
    custom_fields: Optional[Dict[str, Any]] = None
    is_blocked: Optional[bool] = None
    tags: Optional[List[str]] = None


class CustomerResponse(ResponseDTO):
    """Customer response with full metadata."""
    tenant_id: UUID
    customer_id: UUID
    first_name: str
    last_name: Optional[str]
    display_name: str
    contact_info: CustomerContactInfo
    address: Optional[CustomerAddress]
    segment: CustomerSegment
    source: CustomerSource
    custom_fields: Dict[str, Any]
    is_blocked: bool
    tags: List[str]
    total_conversations: int = Field(default=0, description="Total interactions")
    total_messages: int = Field(default=0, description="Total messages sent")
    last_interaction_at: Optional[datetime] = Field(None)
    lifetime_value: Optional[float] = Field(None, description="LTV in currency")
    satisfaction_score: Optional[float] = Field(None, ge=0, le=5)

    @property
    def full_name(self) -> str:
        """Full name combining first and last."""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    class Config:
        json_schema_extra = {
            "example": {
                "id": "cust_123",
                "customer_id": "cust_123",
                "tenant_id": "tenant_123",
                "first_name": "John",
                "last_name": "Doe",
                "display_name": "John Doe",
                "contact_info": {
                    "email": "john@example.com",
                    "phone": "+1234567890"
                },
                "segment": "vip",
                "total_conversations": 10,
                "created_at": "2026-03-06T10:30:00Z"
            }
        }


class CustomerSummary(BaseModel):
    """Lightweight customer info for lists."""
    id: UUID
    display_name: str
    contact_info: CustomerContactInfo
    segment: CustomerSegment
    total_conversations: int
    last_interaction_at: Optional[datetime]


# ─── Customer Statistics ───

class CustomerStatistics(BaseModel):
    """Aggregated customer statistics."""
    total_customers: int
    active_customers: int
    segment_distribution: Dict[CustomerSegment, int]
    source_distribution: Dict[CustomerSource, int]
    avg_lifetime_value: Optional[float] = None
    churn_rate: Optional[float] = Field(None, ge=0, le=1)
    retention_rate: Optional[float] = Field(None, ge=0, le=1)
