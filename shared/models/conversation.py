"""
Conversation & Message Models

Represents conversations (chat threads) and messages across all channels.
Core business entity for the platform.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from .base import CreateDTO, ResponseDTO, UpdateDTO


# ─── Enums ───

class ConversationStatus(str, Enum):
    """Conversation lifecycle states."""
    ACTIVE = "active"           # Ongoing
    WAITING = "waiting"         # Waiting for customer reply
    RESOLVED = "resolved"       # Issue resolved, pending closure
    CLOSED = "closed"           # Conversation ended
    ARCHIVED = "archived"       # Archived for history


class MessageType(str, Enum):
    """Message content types."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    LOCATION = "location"
    TEMPLATE = "template"       # Pre-defined template message


class SenderType(str, Enum):
    """Who sent the message."""
    CUSTOMER = "customer"
    AGENT = "agent"
    AI = "ai"
    SYSTEM = "system"           # Automated system messages


class Channel(str, Enum):
    """Communication channels."""
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"
    VOICE = "voice"
    WEBCHAT = "webchat"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    TELEGRAM = "telegram"
    LINE = "line"
    TWITTER = "twitter"


# ─── Models ───

class ConversationMetadata(BaseModel):
    """Additional conversation context."""
    source_url: Optional[str] = Field(None, description="Page where conversation started")
    campaign_id: Optional[str] = Field(None, description="Marketing campaign ID")
    tags: List[str] = Field(default_factory=list)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class ConversationBase(BaseModel):
    """Base conversation data."""
    customer_id: UUID
    channel: Channel
    status: ConversationStatus = Field(default=ConversationStatus.ACTIVE)
    assigned_to: Optional[UUID] = Field(None, description="Assigned agent ID")
    metadata: ConversationMetadata = Field(default_factory=ConversationMetadata)

    class Config:
        from_attributes = True


class ConversationCreate(CreateDTO):
    """Create conversation request."""
    customer_id: UUID
    channel: Channel
    assigned_to: Optional[UUID] = None
    metadata: Optional[ConversationMetadata] = None


class ConversationUpdate(UpdateDTO):
    """Update conversation request (PATCH)."""
    status: Optional[ConversationStatus] = None
    assigned_to: Optional[UUID] = None
    metadata: Optional[ConversationMetadata] = None


class ConversationResponse(ResponseDTO):
    """Conversation response with full metadata."""
    tenant_id: UUID
    conversation_id: UUID
    customer_id: UUID
    channel: Channel
    status: ConversationStatus
    assigned_to: Optional[UUID]
    metadata: ConversationMetadata
    message_count: int = Field(description="Total messages in conversation")
    last_message_at: Optional[datetime] = Field(None, description="Timestamp of last message")
    resolved_at: Optional[datetime] = Field(None, description="When conversation was resolved")
    resolution_time_seconds: Optional[int] = Field(None, description="Time to resolution")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "customer_id": "123e4567-e89b-12d3-a456-426614174001",
                "channel": "whatsapp",
                "status": "active",
                "message_count": 5,
                "created_at": "2026-03-06T10:30:00Z"
            }
        }


class ConversationSummary(BaseModel):
    """Lightweight conversation info for lists."""
    id: UUID
    customer_id: UUID
    channel: Channel
    status: ConversationStatus
    assigned_to: Optional[UUID]
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime


# ─── Message Models ───

class MessageAttachment(BaseModel):
    """File/media attachment in a message."""
    file_id: Optional[UUID] = None
    url: str = Field(description="Download URL")
    filename: str
    mime_type: str
    size_bytes: int
    duration_seconds: Optional[float] = Field(None, description="For audio/video")


class MessageBase(BaseModel):
    """Base message data."""
    conversation_id: UUID
    message_type: MessageType = Field(default=MessageType.TEXT)
    sender_type: SenderType
    content: str = Field(..., max_length=10000)
    attachments: List[MessageAttachment] = Field(default_factory=list)

    class Config:
        from_attributes = True


class MessageCreate(CreateDTO):
    """Create message request."""
    conversation_id: UUID
    message_type: MessageType = Field(default=MessageType.TEXT)
    sender_type: SenderType
    content: str = Field(..., max_length=10000)
    sender_id: Optional[UUID] = None
    attachments: List[MessageAttachment] = Field(default_factory=list)


class MessageUpdate(UpdateDTO):
    """Update message request (limited fields)."""
    content: Optional[str] = None
    is_edited: Optional[bool] = None


class MessageResponse(ResponseDTO):
    """Message response with metadata."""
    tenant_id: UUID
    conversation_id: UUID
    message_type: MessageType
    sender_type: SenderType
    sender_id: Optional[UUID] = Field(None, description="User/Customer ID")
    content: str
    attachments: List[MessageAttachment]
    is_edited: bool = Field(default=False)
    edited_at: Optional[datetime] = None
    reaction_count: int = Field(default=0)
    read_by: List[UUID] = Field(default_factory=list, description="User IDs who read message")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "msg_123",
                "conversation_id": "conv_123",
                "sender_type": "customer",
                "message_type": "text",
                "content": "Hello, I need help",
                "created_at": "2026-03-06T10:30:00Z"
            }
        }


class MessageSummary(BaseModel):
    """Lightweight message info for conversation views."""
    id: UUID
    conversation_id: UUID
    sender_type: SenderType
    message_type: MessageType
    content: str
    created_at: datetime
    sender_id: Optional[UUID] = None


# ─── Conversation List Responses ───

class ConversationWithLatestMessage(ConversationResponse):
    """Conversation including its latest message."""
    latest_message: Optional[MessageSummary] = None


# ─── Analytics Models ───

class ConversationMetrics(BaseModel):
    """Conversation performance metrics."""
    total_conversations: int
    active_conversations: int
    resolved_conversations: int
    avg_resolution_time_seconds: int
    avg_messages_per_conversation: float
    customer_satisfaction_score: Optional[float] = Field(None, ge=0, le=5)
    first_response_time_seconds: Optional[int] = None


class ChannelMetrics(BaseModel):
    """Per-channel metrics."""
    channel: Channel
    conversation_count: int
    message_count: int
    avg_response_time_seconds: Optional[int] = None
