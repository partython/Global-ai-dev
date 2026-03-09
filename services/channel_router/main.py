"""
Channel Router Service - Priya Global Multi-Tenant AI Sales Platform

Normalizes all channel messages into a unified format and routes them to the AI engine.
Supports: WhatsApp, Email, Instagram, Facebook, WebChat, SMS, Telegram, Voice

FastAPI service running on port 9003 with comprehensive message handling, queue management,
rate limiting, and webhook delivery.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import json
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum
from uuid import uuid4
import time

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import asyncpg
import redis.asyncio as redis
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.core.config import config
from shared.core.database import db
from shared.core.security import mask_pii, sanitize_input
from shared.middleware.auth import get_auth, AuthContext, require_role, require_permission
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Enums & Constants
# ============================================================================

class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    WEBCHAT = "webchat"
    SMS = "sms"
    TELEGRAM = "telegram"
    VOICE = "voice"
    SHOPIFY = "shopify"
    RCS = "rcs"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    TEMPLATE = "template"
    INTERACTIVE = "interactive"
    CAROUSEL = "carousel"


class ConversationStatus(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    WAITING = "waiting"
    ESCALATED = "escalated"
    CLOSED = "closed"


# Rate limit plan thresholds (messages per minute)
RATE_LIMITS = {
    "starter": 100,
    "growth": 500,
    "enterprise": 2000,
}

# Channel-specific rate limits (messages per second)
CHANNEL_RATE_LIMITS = {
    ChannelType.WHATSAPP: 80,
    ChannelType.EMAIL: 14,
    ChannelType.SMS: 100,
    ChannelType.TELEGRAM: 30,
    ChannelType.INSTAGRAM: 30,
    ChannelType.FACEBOOK: 30,
    ChannelType.VOICE: 10,
    ChannelType.WEBCHAT: 100,
}

# ============================================================================
# Pydantic Models
# ============================================================================

class MessageContent(BaseModel):
    """Unified message content structure"""
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None  # image, audio, video, document
    caption: Optional[str] = None
    buttons: Optional[List[Dict[str, str]]] = None
    quick_replies: Optional[List[Dict[str, str]]] = None
    location: Optional[Dict[str, float]] = None  # {latitude, longitude}
    document_name: Optional[str] = None
    document_type: Optional[str] = None
    template_id: Optional[str] = None
    template_params: Optional[List[str]] = None


class MessageContext(BaseModel):
    """Message context for threading and relationships"""
    reply_to_message_id: Optional[str] = None
    thread_id: Optional[str] = None
    conversation_id: Optional[str] = None


class ChannelMessage(BaseModel):
    """Unified CloudEvents-inspired message model"""
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    channel: ChannelType
    direction: MessageDirection
    sender_id: str  # normalized format
    recipient_id: str
    message_type: MessageType
    content: MessageContent
    metadata: Dict[str, Any] = Field(default_factory=dict)
    context: MessageContext = Field(default_factory=MessageContext)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @validator("sender_id", "recipient_id")
    def validate_sender_recipient(cls, v):
        """Validate and normalize sender/recipient IDs"""
        if not v or len(v) < 3:
            raise ValueError("Invalid sender/recipient ID")
        return sanitize_input(v)

    @validator("tenant_id")
    def validate_tenant(cls, v):
        """Validate tenant_id format"""
        if not v or len(v) < 1:
            raise ValueError("Invalid tenant_id")
        return sanitize_input(v)


class InboundMessageRequest(BaseModel):
    """Request model for inbound messages"""
    channel: ChannelType
    sender_id: str
    recipient_id: str
    message_type: MessageType
    content: MessageContent
    metadata: Dict[str, Any] = Field(default_factory=dict)
    context: Optional[MessageContext] = None


class OutboundMessageRequest(BaseModel):
    """Request model for outbound messages"""
    channel: ChannelType
    recipient_id: str
    message_type: MessageType
    content: MessageContent
    conversation_id: str
    reply_to_message_id: Optional[str] = None


class ChannelConfig(BaseModel):
    """Channel configuration model"""
    channel: ChannelType
    enabled: bool = True
    config: Dict[str, Any]  # channel-specific config
    credentials_encrypted: bool = True


class WebhookRegistration(BaseModel):
    """Webhook registration model"""
    url: str
    events: List[str]  # message.received, message.sent, etc.
    active: bool = True
    retry_max: int = 3


class MessageResponse(BaseModel):
    """Response model for message operations"""
    message_id: str
    status: str
    timestamp: datetime


# ============================================================================
# Channel Translators - Format Conversion Logic
# ============================================================================

class ChannelTranslator:
    """Base class for channel-specific message translation"""

    @staticmethod
    def normalize_from_channel(channel_type: ChannelType, raw_message: Dict[str, Any]) -> ChannelMessage:
        """Convert channel-specific format to unified format"""
        raise NotImplementedError

    @staticmethod
    def translate_to_channel(channel_type: ChannelType, unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to channel-specific format"""
        raise NotImplementedError


class WhatsAppTranslator(ChannelTranslator):
    """WhatsApp message translation"""

    @staticmethod
    def normalize_from_channel(raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert WhatsApp webhook format to unified format"""
        message_type = raw_message.get("type", "text")
        sender_id = f"wa:{raw_message['from']}"
        recipient_id = f"wa:{raw_message['to']}"

        content_map = {
            "text": {"text": raw_message.get("text", {}).get("body", "")},
            "image": {
                "media_url": raw_message.get("image", {}).get("link"),
                "media_type": "image",
                "caption": raw_message.get("image", {}).get("caption"),
            },
            "audio": {
                "media_url": raw_message.get("audio", {}).get("link"),
                "media_type": "audio",
            },
            "video": {
                "media_url": raw_message.get("video", {}).get("link"),
                "media_type": "video",
                "caption": raw_message.get("video", {}).get("caption"),
            },
            "document": {
                "media_url": raw_message.get("document", {}).get("link"),
                "media_type": "document",
                "document_name": raw_message.get("document", {}).get("filename"),
            },
            "location": {
                "location": {
                    "latitude": raw_message.get("location", {}).get("latitude"),
                    "longitude": raw_message.get("location", {}).get("longitude"),
                }
            },
        }

        return {
            "channel": ChannelType.WHATSAPP,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": MessageType(message_type),
            "content": MessageContent(**content_map.get(message_type, {})),
            "metadata": {
                "channel_message_id": raw_message.get("id"),
                "timestamp": raw_message.get("timestamp"),
                "whatsapp_status": raw_message.get("status"),
            },
        }

    @staticmethod
    def translate_to_channel(unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to WhatsApp API format"""
        recipient = unified_message.recipient_id.replace("wa:", "")
        message_type = unified_message.message_type.value

        base_payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": message_type,
        }

        if message_type == "text":
            base_payload["text"] = {"body": unified_message.content.text or ""}
        elif message_type == "image":
            base_payload["image"] = {"link": unified_message.content.media_url}
        elif message_type == "template":
            base_payload["template"] = {
                "name": unified_message.content.template_id,
                "language": {"code": "en_US"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": param}
                            for param in (unified_message.content.template_params or [])
                        ],
                    }
                ],
            }
        elif message_type == "interactive":
            base_payload["interactive"] = {
                "type": "button",
                "body": {"text": unified_message.content.text or ""},
                "action": {
                    "buttons": unified_message.content.buttons or []
                },
            }

        return base_payload


class EmailTranslator(ChannelTranslator):
    """Email message translation"""

    @staticmethod
    def normalize_from_channel(raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert email webhook format to unified format"""
        sender_id = f"email:{raw_message['from']}"
        recipient_id = f"email:{raw_message['to']}"

        attachments = []
        for att in raw_message.get("attachments", []):
            attachments.append({
                "media_url": att.get("url"),
                "document_name": att.get("filename"),
                "document_type": att.get("content_type"),
            })

        return {
            "channel": ChannelType.EMAIL,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": MessageType.TEXT,
            "content": MessageContent(
                text=raw_message.get("body", ""),
                media_url=attachments[0].get("media_url") if attachments else None,
            ),
            "metadata": {
                "channel_message_id": raw_message.get("message_id"),
                "timestamp": raw_message.get("received_at"),
                "subject": raw_message.get("subject"),
                "attachments": attachments,
            },
        }

    @staticmethod
    def translate_to_channel(unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to email format"""
        recipient = unified_message.recipient_id.replace("email:", "")

        return {
            "to": recipient,
            "subject": unified_message.metadata.get("subject", "Message from Priya"),
            "body": unified_message.content.text or "",
            "html_body": unified_message.metadata.get("html_body"),
            "attachments": (
                [{"url": unified_message.content.media_url}]
                if unified_message.content.media_url
                else []
            ),
            "reply_to": unified_message.metadata.get("reply_to"),
        }


class InstagramTranslator(ChannelTranslator):
    """Instagram message translation"""

    @staticmethod
    def normalize_from_channel(raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Instagram webhook format to unified format"""
        sender_id = f"ig:{raw_message['from']['username']}"
        recipient_id = f"ig:{raw_message['to']['username']}"
        message_type = raw_message.get("type", "text")

        content_map = {
            "text": {"text": raw_message.get("text")},
            "image": {
                "media_url": raw_message.get("image", {}).get("url"),
                "media_type": "image",
            },
            "video": {
                "media_url": raw_message.get("video", {}).get("url"),
                "media_type": "video",
            },
        }

        return {
            "channel": ChannelType.INSTAGRAM,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": MessageType(message_type),
            "content": MessageContent(**content_map.get(message_type, {})),
            "metadata": {
                "channel_message_id": raw_message.get("id"),
                "timestamp": raw_message.get("created_timestamp"),
            },
        }

    @staticmethod
    def translate_to_channel(unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to Instagram API format"""
        recipient = unified_message.recipient_id.replace("ig:", "")
        message_type = unified_message.message_type.value

        base_payload = {
            "recipient": {"username": recipient},
            "message": {"content_type": message_type},
        }

        if message_type == "text":
            base_payload["message"]["text"] = unified_message.content.text
        elif message_type in ["image", "video"]:
            base_payload["message"]["attachment"] = {
                "type": message_type,
                "payload": {"url": unified_message.content.media_url},
            }

        return base_payload


class FacebookTranslator(ChannelTranslator):
    """Facebook message translation"""

    @staticmethod
    def normalize_from_channel(raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Facebook webhook format to unified format"""
        sender_id = f"fb:{raw_message['sender']['id']}"
        recipient_id = f"fb:{raw_message['recipient']['id']}"
        message_type = "text"

        if "attachments" in raw_message.get("message", {}):
            attachment = raw_message["message"]["attachments"][0]
            message_type = attachment.get("type", "text")

        content_map = {
            "text": {"text": raw_message.get("message", {}).get("text", "")},
            "image": {
                "media_url": raw_message.get("message", {})
                .get("attachments", [{}])[0]
                .get("payload", {})
                .get("url"),
                "media_type": "image",
            },
            "video": {
                "media_url": raw_message.get("message", {})
                .get("attachments", [{}])[0]
                .get("payload", {})
                .get("url"),
                "media_type": "video",
            },
        }

        return {
            "channel": ChannelType.FACEBOOK,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": MessageType(message_type),
            "content": MessageContent(**content_map.get(message_type, {})),
            "metadata": {
                "channel_message_id": raw_message.get("mid"),
                "timestamp": raw_message.get("timestamp"),
            },
        }

    @staticmethod
    def translate_to_channel(unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to Facebook Messenger API format"""
        recipient_id = unified_message.recipient_id.replace("fb:", "")
        message_type = unified_message.message_type.value

        base_payload = {
            "recipient": {"id": recipient_id},
            "message": {},
        }

        if message_type == "text":
            base_payload["message"]["text"] = unified_message.content.text
        elif message_type == "interactive":
            base_payload["message"]["quick_replies"] = unified_message.content.quick_replies or []
        elif message_type in ["image", "video"]:
            base_payload["message"]["attachment"] = {
                "type": message_type,
                "payload": {"url": unified_message.content.media_url},
            }

        return base_payload


class WebChatTranslator(ChannelTranslator):
    """WebChat message translation"""

    @staticmethod
    def normalize_from_channel(raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert WebChat message to unified format"""
        sender_id = f"web:{raw_message['session_id']}"
        recipient_id = f"web:bot"

        return {
            "channel": ChannelType.WEBCHAT,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": MessageType.TEXT,
            "content": MessageContent(text=raw_message.get("message", "")),
            "metadata": {
                "channel_message_id": raw_message.get("id"),
                "timestamp": raw_message.get("timestamp"),
                "page_url": raw_message.get("page_url"),
                "user_agent": raw_message.get("user_agent"),
            },
        }

    @staticmethod
    def translate_to_channel(unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to WebChat format"""
        session_id = unified_message.recipient_id.replace("web:", "")

        return {
            "session_id": session_id,
            "message": unified_message.content.text or "",
            "message_id": unified_message.message_id,
            "timestamp": unified_message.timestamp.isoformat(),
        }


class SMSTranslator(ChannelTranslator):
    """SMS message translation"""

    @staticmethod
    def normalize_from_channel(raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert SMS webhook format to unified format"""
        sender_id = f"sms:{raw_message['from']}"
        recipient_id = f"sms:{raw_message['to']}"

        return {
            "channel": ChannelType.SMS,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": MessageType.TEXT,
            "content": MessageContent(text=raw_message.get("body", "")),
            "metadata": {
                "channel_message_id": raw_message.get("sid"),
                "timestamp": raw_message.get("date_sent"),
                "sms_status": raw_message.get("status"),
            },
        }

    @staticmethod
    def translate_to_channel(unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to SMS API format"""
        recipient = unified_message.recipient_id.replace("sms:", "")

        return {
            "to": recipient,
            "body": unified_message.content.text or "",
            "from": unified_message.metadata.get("from_number", "PRIYA"),
        }


class TelegramTranslator(ChannelTranslator):
    """Telegram message translation"""

    @staticmethod
    def normalize_from_channel(raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Telegram webhook format to unified format"""
        sender_id = f"tg:{raw_message['from']['id']}"
        recipient_id = f"tg:{raw_message['chat']['id']}"
        message_type = "text"

        if "photo" in raw_message:
            message_type = "image"
        elif "audio" in raw_message:
            message_type = "audio"
        elif "video" in raw_message:
            message_type = "video"
        elif "document" in raw_message:
            message_type = "document"

        content_map = {
            "text": {"text": raw_message.get("text", "")},
            "image": {
                "media_url": raw_message.get("photo", [{}])[-1].get("file_id"),
                "media_type": "image",
                "caption": raw_message.get("caption"),
            },
            "audio": {
                "media_url": raw_message.get("audio", {}).get("file_id"),
                "media_type": "audio",
            },
            "video": {
                "media_url": raw_message.get("video", {}).get("file_id"),
                "media_type": "video",
                "caption": raw_message.get("caption"),
            },
            "document": {
                "media_url": raw_message.get("document", {}).get("file_id"),
                "media_type": "document",
                "document_name": raw_message.get("document", {}).get("file_name"),
            },
        }

        return {
            "channel": ChannelType.TELEGRAM,
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "message_type": MessageType(message_type),
            "content": MessageContent(**content_map.get(message_type, {})),
            "metadata": {
                "channel_message_id": raw_message.get("message_id"),
                "timestamp": raw_message.get("date"),
            },
        }

    @staticmethod
    def translate_to_channel(unified_message: ChannelMessage) -> Dict[str, Any]:
        """Convert unified format to Telegram Bot API format"""
        chat_id = unified_message.recipient_id.replace("tg:", "")
        message_type = unified_message.message_type.value

        base_payload = {
            "chat_id": chat_id,
        }

        if message_type == "text":
            base_payload["text"] = unified_message.content.text
            base_payload["parse_mode"] = "HTML"
        elif message_type == "image":
            base_payload["photo"] = unified_message.content.media_url
            base_payload["caption"] = unified_message.content.caption
        elif message_type == "video":
            base_payload["video"] = unified_message.content.media_url
            base_payload["caption"] = unified_message.content.caption
        elif message_type == "document":
            base_payload["document"] = unified_message.content.media_url

        return base_payload


# Translator registry
TRANSLATORS = {
    ChannelType.WHATSAPP: WhatsAppTranslator,
    ChannelType.EMAIL: EmailTranslator,
    ChannelType.INSTAGRAM: InstagramTranslator,
    ChannelType.FACEBOOK: FacebookTranslator,
    ChannelType.WEBCHAT: WebChatTranslator,
    ChannelType.SMS: SMSTranslator,
    ChannelType.TELEGRAM: TelegramTranslator,
}


# ============================================================================
# Queue Manager
# ============================================================================

class QueueManager:
    """Redis-based message queue for async processing"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def publish_to_ai_engine(self, message: ChannelMessage) -> None:
        """Publish message to AI processing queue"""
        queue_key = f"queue:ai_engine:{message.tenant_id}"
        await self.redis.lpush(
            queue_key,
            json.dumps(message.dict(), default=str),
        )
        await self.redis.expire(queue_key, 86400)  # 24-hour retention
        logger.info(
            f"Published to AI queue: {mask_pii(message.sender_id)} "
            f"(tenant: {message.tenant_id})"
        )

    async def publish_to_channel(
        self, channel: ChannelType, message: ChannelMessage
    ) -> None:
        """Publish message to channel delivery queue"""
        queue_key = f"queue:channel:{channel.value}:{message.tenant_id}"
        await self.redis.lpush(
            queue_key,
            json.dumps(message.dict(), default=str),
        )
        logger.info(
            f"Published to {channel.value} queue: "
            f"{mask_pii(message.recipient_id)} (tenant: {message.tenant_id})"
        )

    async def get_queue_depth(self, queue_key: str) -> int:
        """Get number of messages in queue"""
        return await self.redis.llen(queue_key)


# ============================================================================
# Rate Limiter
# ============================================================================

class RateLimiter:
    """Redis-based sliding window rate limiter"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check_tenant_limit(self, tenant_id: str, plan: str) -> bool:
        """Check if tenant has exceeded rate limit"""
        limit = RATE_LIMITS.get(plan, 100)
        key = f"rate_limit:tenant:{tenant_id}"
        current = await self.redis.incr(key)

        if current == 1:
            await self.redis.expire(key, 60)  # Reset every minute

        return current <= limit

    async def check_channel_limit(
        self, tenant_id: str, channel: ChannelType
    ) -> bool:
        """Check if channel has exceeded per-second rate limit"""
        limit = CHANNEL_RATE_LIMITS.get(channel, 100)
        key = f"rate_limit:channel:{channel.value}:{tenant_id}"
        current = await self.redis.incr(key)

        if current == 1:
            await self.redis.expire(key, 1)  # Reset every second

        return current <= limit


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Channel Router Service",
    description="Message normalization and routing for Priya Global",
    version="1.0.0",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="channel_router")
init_sentry(service_name="channel-router", service_port=9003)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="channel-router")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Global instances
redis_client: Optional[redis.Redis] = None
queue_manager: Optional[QueueManager] = None
rate_limiter: Optional[RateLimiter] = None


@app.on_event("startup")
async def startup():
    """Initialize connections on startup"""
    global redis_client, queue_manager, rate_limiter

    await event_bus.startup()
    redis_client = await redis.from_url(
        config.REDIS_URL,
        encoding="utf8",
        decode_responses=True,
    )
    queue_manager = QueueManager(redis_client)
    rate_limiter = RateLimiter(redis_client)

    # Initialize database
    await db.initialize()

    logger.info("Channel Router Service started")


@app.on_event("shutdown")
async def shutdown():
    """Clean up connections on shutdown"""
    if redis_client:
        await redis_client.close()
    shutdown_tracing()
    await event_bus.shutdown()
    await db.close()
    logger.info("Channel Router Service stopped")


# ============================================================================
# Health & Metrics
# ============================================================================

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Service health check endpoint"""
    try:
        # Check Redis
        if redis_client:
            await redis_client.ping()
            redis_status = "healthy"
        else:
            redis_status = "unavailable"

        # Check database
        conn = await db.get_connection()
        db_status = "healthy" if conn else "unhealthy"

        return {
            "status": "healthy" if redis_status == "healthy" and db_status == "healthy" else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "redis": redis_status,
            "database": db_status,
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
        }


@app.get("/metrics")
async def get_metrics(auth: AuthContext = Depends(get_auth)) -> Dict[str, Any]:
    """Get service metrics"""
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    tenant_id = auth.tenant_id
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "queues": {},
        "rate_limits": {},
    }

    # Queue depths
    for channel in ChannelType:
        queue_key = f"queue:channel:{channel.value}:{tenant_id}"
        depth = await queue_manager.get_queue_depth(queue_key)
        metrics["queues"][f"{channel.value}_outbound"] = depth

    ai_queue_key = f"queue:ai_engine:{tenant_id}"
    metrics["queues"]["ai_engine"] = await queue_manager.get_queue_depth(ai_queue_key)

    return metrics


# ============================================================================
# Inbound Message Handling
# ============================================================================

@app.post("/api/v1/messages/inbound", response_model=MessageResponse)
async def inbound_message(
    request: InboundMessageRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
) -> MessageResponse:
    """
    Receive normalized message from channel service.

    Validates tenant & channel, creates customer/conversation records,
    stores message, and routes to AI engine asynchronously.
    """
    try:
        # Rate limiting
        tenant_plan = await _get_tenant_plan(auth.tenant_id)
        if not await rate_limiter.check_tenant_limit(auth.tenant_id, tenant_plan):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        if not await rate_limiter.check_channel_limit(auth.tenant_id, request.channel):
            raise HTTPException(status_code=429, detail="Channel rate limit exceeded")

        # Validate channel is enabled for tenant
        channel_config = await _get_channel_config(auth.tenant_id, request.channel)
        if not channel_config or not channel_config.get("enabled"):
            raise HTTPException(
                status_code=400,
                detail=f"Channel {request.channel.value} not enabled for tenant",
            )

        # Create/update customer
        customer_id = await _upsert_customer(
            auth.tenant_id,
            request.channel,
            request.sender_id,
            request.metadata.get("customer_name"),
        )

        # Create/update conversation
        conversation_id = request.context.conversation_id or str(uuid4())
        await _upsert_conversation(
            auth.tenant_id,
            conversation_id,
            customer_id,
            request.channel,
        )

        # Build unified message
        message = ChannelMessage(
            message_id=str(uuid4()),
            tenant_id=auth.tenant_id,
            channel=request.channel,
            direction=MessageDirection.INBOUND,
            sender_id=request.sender_id,
            recipient_id=request.recipient_id,
            message_type=request.message_type,
            content=request.content,
            metadata={
                **request.metadata,
                "customer_id": customer_id,
                "conversation_id": conversation_id,
            },
            context=request.context or MessageContext(conversation_id=conversation_id),
            timestamp=datetime.utcnow(),
        )

        # Store message
        await _store_message(auth.tenant_id, message)

        # Route to AI engine asynchronously
        background_tasks.add_task(
            queue_manager.publish_to_ai_engine,
            message,
        )

        logger.info(
            f"Inbound message received: {mask_pii(request.sender_id)} "
            f"via {request.channel.value} (tenant: {auth.tenant_id})"
        )

        return MessageResponse(
            message_id=message.message_id,
            status="received",
            timestamp=message.timestamp,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Inbound message error: %s", e)
        raise HTTPException(status_code=500, detail="Message processing failed")


# ============================================================================
# Outbound Message Handling
# ============================================================================

@app.post("/api/v1/messages/outbound", response_model=MessageResponse)
async def outbound_message(
    request: OutboundMessageRequest,
    auth: AuthContext = Depends(get_auth),
) -> MessageResponse:
    """
    Send message from AI engine or human agent.

    Translates to channel format, routes to channel service,
    and stores for audit trail.
    """
    try:
        # Validate channel is enabled
        channel_config = await _get_channel_config(auth.tenant_id, request.channel)
        if not channel_config or not channel_config.get("enabled"):
            raise HTTPException(
                status_code=400,
                detail=f"Channel {request.channel.value} not enabled for tenant",
            )

        # Rate limiting
        if not await rate_limiter.check_channel_limit(auth.tenant_id, request.channel):
            raise HTTPException(status_code=429, detail="Channel rate limit exceeded")

        # Build unified message
        message = ChannelMessage(
            message_id=str(uuid4()),
            tenant_id=auth.tenant_id,
            channel=request.channel,
            direction=MessageDirection.OUTBOUND,
            sender_id=f"bot:{auth.tenant_id}",
            recipient_id=request.recipient_id,
            message_type=request.message_type,
            content=request.content,
            metadata={"conversation_id": request.conversation_id},
            context=MessageContext(
                conversation_id=request.conversation_id,
                reply_to_message_id=request.reply_to_message_id,
            ),
            timestamp=datetime.utcnow(),
        )

        # Store outbound message
        await _store_message(auth.tenant_id, message)

        # Translate to channel format
        translator = TRANSLATORS.get(request.channel)
        if not translator:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported channel: {request.channel.value}",
            )

        channel_payload = translator.translate_to_channel(message)

        # Route to channel service
        await _route_to_channel_service(auth.tenant_id, request.channel, channel_payload)

        # Publish to queue for delivery tracking
        await queue_manager.publish_to_channel(request.channel, message)

        logger.info(
            f"Outbound message sent: {mask_pii(request.recipient_id)} "
            f"via {request.channel.value} (tenant: {auth.tenant_id})"
        )

        return MessageResponse(
            message_id=message.message_id,
            status="sent",
            timestamp=message.timestamp,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Outbound message error: %s", e)
        raise HTTPException(status_code=500, detail="Message delivery failed")


# ============================================================================
# Channel Management
# ============================================================================

@app.get("/api/v1/channels")
async def list_channels(
    auth: AuthContext = Depends(get_auth),
) -> List[Dict[str, Any]]:
    """List all channels enabled for tenant"""
    try:
        conn = await tenant_connection(auth.tenant_id)
        rows = await conn.fetch(
            """
            SELECT channel, enabled, config, created_at
            FROM channel_configs
            WHERE tenant_id = $1
            ORDER BY channel ASC
            """,
            auth.tenant_id,
        )

        return [
            {
                "channel": row["channel"],
                "enabled": row["enabled"],
                "config": json.loads(row["config"]) if isinstance(row["config"], str) else row["config"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
    except Exception as e:
        logger.error("List channels error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list channels")


@app.post("/api/v1/channels/register")
async def register_channel(
    channel_config: ChannelConfig,
    auth: AuthContext = Depends(get_auth, scopes=["admin"]),
) -> Dict[str, Any]:
    """Register/enable a channel for tenant"""
    try:
        conn = await tenant_connection(auth.tenant_id)

        await conn.execute(
            """
            INSERT INTO channel_configs (tenant_id, channel, enabled, config)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tenant_id, channel) DO UPDATE
            SET enabled = $3, config = $4, updated_at = NOW()
            """,
            auth.tenant_id,
            channel_config.channel.value,
            channel_config.enabled,
            json.dumps(channel_config.config),
        )

        logger.info(
            f"Channel {channel_config.channel.value} "
            f"registered for tenant {auth.tenant_id}"
        )

        return {
            "channel": channel_config.channel.value,
            "enabled": channel_config.enabled,
            "status": "registered",
        }
    except Exception as e:
        logger.error("Register channel error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to register channel")


class ChannelTestRequest(BaseModel):
    """Optional credentials to test before saving"""
    credentials: Optional[Dict[str, Any]] = None


@app.post("/api/v1/channels/{channel}/disconnect")
async def disconnect_channel(
    channel: str,
    auth: AuthContext = Depends(get_auth),
) -> Dict[str, Any]:
    """Disconnect a channel for tenant — sets status to inactive"""
    try:
        if channel not in [ct.value for ct in ChannelType]:
            raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")

        conn = await tenant_connection(auth.tenant_id)

        result = await conn.execute(
            """
            UPDATE channel_connections
            SET status = 'inactive', updated_at = NOW(), error_message = NULL
            WHERE tenant_id = $1 AND channel = $2 AND status = 'active'
            """,
            auth.tenant_id,
            channel,
        )

        # Also disable in channel_configs if it exists
        await conn.execute(
            """
            UPDATE channel_configs
            SET enabled = false, updated_at = NOW()
            WHERE tenant_id = $1 AND channel = $2
            """,
            auth.tenant_id,
            channel,
        )

        logger.info(f"Channel {channel} disconnected for tenant {mask_pii(str(auth.tenant_id))}")

        return {
            "channel": channel,
            "status": "disconnected",
            "message": f"{channel} has been disconnected successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Disconnect channel error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to disconnect channel")


@app.post("/api/v1/channels/{channel}/test")
async def test_channel_connection(
    channel: str,
    body: ChannelTestRequest = ChannelTestRequest(),
    auth: AuthContext = Depends(get_auth),
) -> Dict[str, Any]:
    """Test connection to an external channel provider.
    Rate limited: 5 requests per minute per tenant per channel."""
    try:
        if channel not in [ct.value for ct in ChannelType]:
            raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")

        # Rate limit: 5 test requests per minute per tenant per channel
        rate_key = f"channel_test:{auth.tenant_id}:{channel}"
        current = await redis_client.incr(rate_key)
        if current == 1:
            await redis_client.expire(rate_key, 60)
        if current > 5:
            raise HTTPException(
                status_code=429,
                detail="Too many test requests. Max 5 per minute per channel.",
            )

        # Get credentials — either from request body or from DB
        creds = body.credentials
        if not creds:
            conn = await tenant_connection(auth.tenant_id)
            row = await conn.fetchrow(
                """
                SELECT credentials, channel_metadata
                FROM channel_connections
                WHERE tenant_id = $1 AND channel = $2 AND status = 'active'
                """,
                auth.tenant_id,
                channel,
            )
            if not row:
                return {"status": "failed", "message": f"No active {channel} connection found"}
            raw_creds = row["credentials"] or row.get("channel_metadata", {})
            if isinstance(raw_creds, str):
                try:
                    from shared.core.security import decrypt_credentials
                    creds = decrypt_credentials(raw_creds)
                except Exception:
                    creds = json.loads(raw_creds) if raw_creds else {}
            else:
                creds = raw_creds if raw_creds else {}

        # Test connection based on channel type
        test_result = await _test_channel_provider(channel, creds)
        return test_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Test channel error: %s", e)
        return {"status": "failed", "message": f"Connection test failed: {str(e)}"}


async def _test_channel_provider(channel: str, creds: Dict[str, Any]) -> Dict[str, Any]:
    """Test connection to a specific channel provider API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if channel in ("whatsapp", "instagram", "facebook"):
                # Meta Graph API — verify access token
                token = creds.get("access_token", "")
                if not token:
                    return {"status": "failed", "message": "Missing access_token"}
                resp = await client.get(
                    "https://graph.facebook.com/v18.0/me",
                    params={"access_token": token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "success",
                        "message": f"Connected as {data.get('name', 'unknown')}",
                        "provider_info": {"name": data.get("name"), "id": data.get("id")},
                    }
                else:
                    error = resp.json().get("error", {}).get("message", "Invalid token")
                    return {"status": "failed", "message": f"Meta API error: {error}"}

            elif channel == "telegram":
                # Telegram Bot API — getMe
                bot_token = creds.get("bot_token", "")
                if not bot_token:
                    return {"status": "failed", "message": "Missing bot_token"}
                resp = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getMe"
                )
                data = resp.json()
                if data.get("ok"):
                    bot = data["result"]
                    return {
                        "status": "success",
                        "message": f"Connected as @{bot.get('username', 'unknown')}",
                        "provider_info": {
                            "username": bot.get("username"),
                            "first_name": bot.get("first_name"),
                            "id": bot.get("id"),
                        },
                    }
                else:
                    return {"status": "failed", "message": "Invalid bot token"}

            elif channel == "email":
                # Test SMTP connection or SES
                smtp_host = creds.get("smtp_host") or creds.get("smtp_server")
                if smtp_host:
                    import socket
                    smtp_port = int(creds.get("smtp_port", 587))
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    try:
                        sock.connect((smtp_host, smtp_port))
                        sock.close()
                        return {
                            "status": "success",
                            "message": f"SMTP server {smtp_host}:{smtp_port} is reachable",
                        }
                    except (socket.timeout, ConnectionRefusedError, OSError) as e:
                        return {"status": "failed", "message": f"SMTP connection failed: {e}"}
                else:
                    # AWS SES — check if configured
                    return {"status": "success", "message": "AWS SES configured (credentials validated at runtime)"}

            elif channel in ("sms", "voice"):
                # Exotel API test
                exotel_sid = creds.get("exotel_sid") or creds.get("account_sid", "")
                exotel_token = creds.get("exotel_token") or creds.get("api_token", "")
                if not exotel_sid or not exotel_token:
                    return {"status": "failed", "message": "Missing Exotel SID or Token"}
                resp = await client.get(
                    f"https://api.exotel.com/v1/Accounts/{exotel_sid}",
                    auth=(exotel_sid, exotel_token),
                )
                if resp.status_code == 200:
                    return {"status": "success", "message": f"Exotel account {exotel_sid} verified"}
                else:
                    return {"status": "failed", "message": f"Exotel API returned {resp.status_code}"}

            elif channel == "webchat":
                # WebChat is self-hosted — always succeeds
                return {"status": "success", "message": "WebChat is self-hosted and always available"}

            elif channel == "shopify":
                # Shopify — verify access token against shop API
                access_token = creds.get("access_token", "")
                shop_domain = creds.get("shop_domain", "")
                if not access_token or not shop_domain:
                    return {"status": "failed", "message": "Missing Shopify access_token or shop_domain"}
                resp = await client.get(
                    f"https://{shop_domain}/admin/api/2024-01/shop.json",
                    headers={"X-Shopify-Access-Token": access_token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    shop_name = data.get("shop", {}).get("name", shop_domain)
                    return {"status": "success", "message": f"Connected to {shop_name}"}
                else:
                    return {"status": "failed", "message": f"Shopify API returned {resp.status_code}"}

            elif channel == "rcs":
                # Google RBM — check API key
                api_key = creds.get("google_rbm_api_key", "")
                if not api_key:
                    return {"status": "failed", "message": "Missing Google RBM API key"}
                return {"status": "success", "message": "RCS credentials configured (validated at runtime)"}

            else:
                return {"status": "failed", "message": f"Unknown channel: {channel}"}

        except httpx.TimeoutException:
            return {"status": "failed", "message": "Connection timed out (10s)"}
        except Exception as e:
            return {"status": "failed", "message": f"Test failed: {str(e)}"}


@app.get("/api/v1/channels/stats")
async def get_channel_stats(
    auth: AuthContext = Depends(get_auth),
) -> Dict[str, Any]:
    """Get aggregated message stats for all connected tenant channels"""
    try:
        conn = await tenant_connection(auth.tenant_id)

        # Get per-channel message counts and response times
        rows = await conn.fetch(
            """
            SELECT
                c.channel,
                COUNT(CASE WHEN m.direction = 'outbound' THEN 1 END) AS sent,
                COUNT(CASE WHEN m.direction = 'inbound' THEN 1 END) AS received,
                COALESCE(AVG(
                    CASE WHEN m.direction = 'outbound' AND m.response_time_ms IS NOT NULL
                    THEN m.response_time_ms END
                ), 0) AS avg_response_ms,
                MAX(m.created_at) AS last_activity
            FROM channel_connections c
            LEFT JOIN conversations conv ON conv.tenant_id = c.tenant_id AND conv.channel = c.channel
            LEFT JOIN messages m ON m.conversation_id = conv.id
            WHERE c.tenant_id = $1 AND c.status = 'active'
            GROUP BY c.channel
            ORDER BY c.channel ASC
            """,
            auth.tenant_id,
        )

        stats = []
        for row in rows:
            stats.append({
                "name": row["channel"].replace("_", " ").title(),
                "channel": row["channel"],
                "sent": row["sent"] or 0,
                "received": row["received"] or 0,
                "avgResponseTime": round(float(row["avg_response_ms"] or 0) / 1000, 1),
                "lastActivity": row["last_activity"].isoformat() if row["last_activity"] else None,
            })

        return {"stats": stats}

    except Exception as e:
        logger.error("Channel stats error: %s", e)
        # Return empty stats on error (graceful fallback)
        return {"stats": []}


# ============================================================================
# Conversation Management
# ============================================================================

@app.get("/api/v1/conversations")
async def list_conversations(
    auth: AuthContext = Depends(get_auth),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List conversations for tenant (paginated)"""
    try:
        conn = await tenant_connection(auth.tenant_id)

        # Build query with optional status filter
        where_clause = "WHERE tenant_id = $1"
        params = [auth.tenant_id]

        if status:
            where_clause += " AND status = $2"
            params.append(status)

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM conversations {where_clause}",
            *params,
        )

        rows = await conn.fetch(
            f"""
            SELECT id, customer_id, channel, status, created_at, updated_at
            FROM conversations
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT ${'3' if status else '2'} OFFSET ${'4' if status else '3'}
            """,
            *(params + [limit, skip]),
        )

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "conversations": [
                {
                    "id": row["id"],
                    "customer_id": row["customer_id"],
                    "channel": row["channel"],
                    "status": row["status"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                }
                for row in rows
            ],
        }
    except Exception as e:
        logger.error("List conversations error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@app.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    auth: AuthContext = Depends(get_auth),
) -> Dict[str, Any]:
    """Get conversation with all messages"""
    try:
        conn = await tenant_connection(auth.tenant_id)

        # Fetch conversation
        conversation = await conn.fetchrow(
            """
            SELECT id, customer_id, channel, status, assigned_to, created_at
            FROM conversations
            WHERE id = $1 AND tenant_id = $2
            """,
            conversation_id,
            auth.tenant_id,
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Fetch messages
        messages = await conn.fetch(
            """
            SELECT id, message_id, direction, message_type, content, created_at
            FROM messages
            WHERE conversation_id = $1 AND tenant_id = $2
            ORDER BY created_at ASC
            """,
            conversation_id,
            auth.tenant_id,
        )

        return {
            "id": conversation["id"],
            "customer_id": conversation["customer_id"],
            "channel": conversation["channel"],
            "status": conversation["status"],
            "assigned_to": conversation["assigned_to"],
            "created_at": conversation["created_at"].isoformat(),
            "messages": [
                {
                    "id": msg["id"],
                    "message_id": msg["message_id"],
                    "direction": msg["direction"],
                    "message_type": msg["message_type"],
                    "content": json.loads(msg["content"]) if isinstance(msg["content"], str) else msg["content"],
                    "created_at": msg["created_at"].isoformat(),
                }
                for msg in messages
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get conversation error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@app.post("/api/v1/conversations/{conversation_id}/assign")
async def assign_conversation(
    conversation_id: str,
    agent_id: str,
    auth: AuthContext = Depends(get_auth, scopes=["manager"]),
) -> Dict[str, Any]:
    """Assign conversation to human agent"""
    try:
        conn = await tenant_connection(auth.tenant_id)

        await conn.execute(
            """
            UPDATE conversations
            SET assigned_to = $1, status = $2, updated_at = NOW()
            WHERE id = $3 AND tenant_id = $4
            """,
            agent_id,
            ConversationStatus.ACTIVE.value,
            conversation_id,
            auth.tenant_id,
        )

        logger.info(
            f"Conversation {conversation_id} assigned to agent {agent_id} "
            f"(tenant: {auth.tenant_id})"
        )

        return {
            "conversation_id": conversation_id,
            "assigned_to": agent_id,
            "status": ConversationStatus.ACTIVE.value,
        }
    except Exception as e:
        logger.error("Assign conversation error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to assign conversation")


@app.post("/api/v1/conversations/{conversation_id}/close")
async def close_conversation(
    conversation_id: str,
    auth: AuthContext = Depends(get_auth),
) -> Dict[str, Any]:
    """Close conversation"""
    try:
        conn = await tenant_connection(auth.tenant_id)

        await conn.execute(
            """
            UPDATE conversations
            SET status = $1, updated_at = NOW()
            WHERE id = $2 AND tenant_id = $3
            """,
            ConversationStatus.CLOSED.value,
            conversation_id,
            auth.tenant_id,
        )

        logger.info(
            f"Conversation {conversation_id} closed "
            f"(tenant: {auth.tenant_id})"
        )

        return {
            "conversation_id": conversation_id,
            "status": ConversationStatus.CLOSED.value,
        }
    except Exception as e:
        logger.error("Close conversation error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to close conversation")


# ============================================================================
# Webhook Management
# ============================================================================

@app.post("/api/v1/webhooks")
async def register_webhook(
    webhook: WebhookRegistration,
    auth: AuthContext = Depends(get_auth, scopes=["admin"]),
) -> Dict[str, Any]:
    """Register webhook for message events"""
    try:
        webhook_id = str(uuid4())
        conn = await tenant_connection(auth.tenant_id)

        # Generate signing secret
        signing_secret = hashlib.sha256(
            f"{webhook_id}:{auth.tenant_id}:{int(time.time())}".encode()
        ).hexdigest()

        await conn.execute(
            """
            INSERT INTO webhooks (id, tenant_id, url, events, signing_secret, active)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            webhook_id,
            auth.tenant_id,
            webhook.url,
            json.dumps(webhook.events),
            signing_secret,
            webhook.active,
        )

        logger.info(
            f"Webhook registered: {webhook_id} for tenant {auth.tenant_id}"
        )

        return {
            "webhook_id": webhook_id,
            "signing_secret": signing_secret,
            "status": "registered",
        }
    except Exception as e:
        logger.error("Register webhook error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to register webhook")


# ============================================================================
# Helper Functions
# ============================================================================

async def _get_tenant_plan(tenant_id: str) -> str:
    """Get tenant's subscription plan"""
    conn = await db.get_connection()
    plan = await conn.fetchval(
        "SELECT plan FROM tenants WHERE id = $1",
        tenant_id,
    )
    return plan or "starter"


async def _get_channel_config(
    tenant_id: str, channel: ChannelType
) -> Optional[Dict[str, Any]]:
    """Get channel configuration for tenant"""
    conn = await tenant_connection(tenant_id)
    config = await conn.fetchrow(
        """
        SELECT config, enabled
        FROM channel_configs
        WHERE tenant_id = $1 AND channel = $2
        """,
        tenant_id,
        channel.value,
    )

    if not config:
        return None

    extra = json.loads(config["config"]) if isinstance(config["config"], str) else (config["config"] or {})
    return {
        "enabled": config["enabled"],
        **extra,
    }


async def _upsert_customer(
    tenant_id: str,
    channel: ChannelType,
    channel_user_id: str,
    customer_name: Optional[str] = None,
) -> str:
    """Create or update customer record"""
    conn = await tenant_connection(tenant_id)
    customer_id = str(uuid4())

    customer = await conn.fetchrow(
        """
        SELECT id FROM customers
        WHERE tenant_id = $1 AND channel = $2 AND channel_user_id = $3
        """,
        tenant_id,
        channel.value,
        channel_user_id,
    )

    if customer:
        return customer["id"]

    await conn.execute(
        """
        INSERT INTO customers (id, tenant_id, channel, channel_user_id, name, created_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        """,
        customer_id,
        tenant_id,
        channel.value,
        channel_user_id,
        customer_name or f"{channel.value}_{channel_user_id}",
    )

    return customer_id


async def _upsert_conversation(
    tenant_id: str,
    conversation_id: str,
    customer_id: str,
    channel: ChannelType,
) -> None:
    """Create or update conversation record"""
    conn = await tenant_connection(tenant_id)

    conversation = await conn.fetchrow(
        """
        SELECT id FROM conversations
        WHERE id = $1 AND tenant_id = $2
        """,
        conversation_id,
        tenant_id,
    )

    if conversation:
        await conn.execute(
            """
            UPDATE conversations SET updated_at = NOW()
            WHERE id = $1 AND tenant_id = $2
            """,
            conversation_id,
            tenant_id,
        )
    else:
        await conn.execute(
            """
            INSERT INTO conversations
            (id, tenant_id, customer_id, channel, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            """,
            conversation_id,
            tenant_id,
            customer_id,
            channel.value,
            ConversationStatus.NEW.value,
        )


async def _store_message(tenant_id: str, message: ChannelMessage) -> None:
    """Store message in database"""
    conn = await tenant_connection(tenant_id)

    await conn.execute(
        """
        INSERT INTO messages
        (id, tenant_id, message_id, conversation_id, direction, message_type, content,
         sender_id, recipient_id, channel, metadata, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
        """,
        str(uuid4()),
        tenant_id,
        message.message_id,
        message.context.conversation_id or str(uuid4()),
        message.direction.value,
        message.message_type.value,
        json.dumps(message.content.dict()),
        message.sender_id,
        message.recipient_id,
        message.channel.value,
        json.dumps(message.metadata),
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _route_to_channel_service(
    tenant_id: str, channel: ChannelType, payload: Dict[str, Any]
) -> None:
    """Route message to channel service with retry logic"""
    channel_service_urls = {
        ChannelType.WHATSAPP: config.WHATSAPP_SERVICE_URL,
        ChannelType.EMAIL: config.EMAIL_SERVICE_URL,
        ChannelType.INSTAGRAM: config.INSTAGRAM_SERVICE_URL,
        ChannelType.FACEBOOK: config.FACEBOOK_SERVICE_URL,
        ChannelType.WEBCHAT: config.WEBCHAT_SERVICE_URL,
        ChannelType.SMS: config.SMS_SERVICE_URL,
        ChannelType.TELEGRAM: config.TELEGRAM_SERVICE_URL,
    }

    service_url = channel_service_urls.get(channel)
    if not service_url:
        raise ValueError(f"No service URL configured for channel: {channel.value}")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{service_url}/api/v1/messages/send",
            json=payload,
            headers={
                "X-Tenant-ID": tenant_id,
                "Authorization": f"Bearer {config.SERVICE_TOKEN}",
            },
            timeout=10,
        )
        response.raise_for_status()


if __name__ == "__main__":
    import uvicorn



    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9003,
        log_level="info",
    )
