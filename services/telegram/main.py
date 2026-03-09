"""
Telegram Channel Service - Priya Global Multi-Tenant AI Sales Platform

Handles inbound/outbound Telegram messages with bot API integration.
Multi-tenant bot token routing with support for text, media, inline keyboards,
group chats, and configurable bot commands per tenant.

FastAPI service running on port 9016 with comprehensive Telegram bot management,
message handling, media processing, and analytics.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import json
import logging
import re
import hmac
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import asyncpg
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import mask_pii, sanitize_input
from shared.middleware.auth import get_auth, AuthContext, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Constants & Enums
# ============================================================================

class MessageType(str, Enum):
    """Telegram message types"""
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    VOICE = "voice"
    LOCATION = "location"
    CONTACT = "contact"
    STICKER = "sticker"
    ANIMATION = "animation"


class MessageDirection(str, Enum):
    """Message direction"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, Enum):
    """Message status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class BotCommand(str, Enum):
    """Configurable bot commands"""
    START = "start"
    HELP = "help"
    STATUS = "status"


# ============================================================================
# Pydantic Models
# ============================================================================

class TelegramUser(BaseModel):
    """Telegram user info"""
    id: int
    is_bot: bool
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None


class TelegramChat(BaseModel):
    """Telegram chat/group info"""
    id: int
    type: str  # private, group, supergroup, channel
    title: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class InlineKeyboardButton(BaseModel):
    """Inline keyboard button"""
    text: str
    callback_data: Optional[str] = None
    url: Optional[str] = None


class InlineKeyboard(BaseModel):
    """Inline keyboard markup"""
    buttons: List[List[InlineKeyboardButton]]  # 2D array


class SendMessageRequest(BaseModel):
    """Request to send Telegram message"""
    chat_id: int
    message_type: MessageType = MessageType.TEXT
    content: str  # Text content for text messages
    photo_url: Optional[str] = None
    video_url: Optional[str] = None
    document_url: Optional[str] = None
    caption: Optional[str] = None
    inline_keyboard: Optional[InlineKeyboard] = None
    parse_mode: str = "HTML"  # HTML, Markdown, MarkdownV2
    disable_notifications: bool = False
    reply_to_message_id: Optional[int] = None

    @validator("content")
    def validate_content(cls, v):
        if len(v) > 4096:  # Telegram limit
            raise ValueError("Message content exceeds maximum length (4096 chars)")
        return v


class TelegramMessage(BaseModel):
    """Telegram message record"""
    id: str
    tenant_id: str
    telegram_message_id: int
    telegram_user_id: int
    telegram_chat_id: int
    message_type: MessageType
    content: str
    status: MessageStatus
    direction: MessageDirection
    media_url: Optional[str] = None
    caption: Optional[str] = None
    reply_to_id: Optional[int] = None
    edited_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TelegramBotConfig(BaseModel):
    """Bot configuration per tenant"""
    id: str
    tenant_id: str
    bot_token: str  # Store hashed
    bot_username: str
    bot_name: str
    webhook_url: str
    commands: Dict[str, str]  # command -> description
    is_active: bool
    created_at: datetime
    updated_at: datetime


class BotCommandConfig(BaseModel):
    """Bot command configuration"""
    command: str
    description: str


class TelegramAnalytics(BaseModel):
    """Telegram analytics for tenant"""
    period_start: datetime
    period_end: datetime
    total_messages: int = 0
    total_inbound: int = 0
    total_outbound: int = 0
    total_text: int = 0
    total_media: int = 0
    unique_users: int = 0
    unique_groups: int = 0
    avg_response_time_seconds: float = 0.0
    bot_command_usage: Dict[str, int] = Field(default_factory=dict)


class CallbackQuery(BaseModel):
    """Telegram callback query from inline button"""
    id: str
    user: TelegramUser
    chat_instance: str
    message_id: int
    data: str


# ============================================================================
# Telegram Bot API Client
# ============================================================================

class TelegramBotClient:
    """Direct Telegram Bot API client (no python-telegram-bot library)"""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict] = None,
        disable_notifications: bool = False,
        reply_to_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send text message"""
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_notification": disable_notifications,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id

            response = await client.post(f"{self.base_url}/sendMessage", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def send_photo(
        self,
        chat_id: int,
        photo: str,  # URL or file_id
        caption: Optional[str] = None,
        reply_markup: Optional[Dict] = None,
        disable_notifications: bool = False,
    ) -> Dict[str, Any]:
        """Send photo"""
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "photo": photo,
                "disable_notification": disable_notifications,
            }
            if caption:
                payload["caption"] = caption
                payload["parse_mode"] = "HTML"
            if reply_markup:
                payload["reply_markup"] = reply_markup

            response = await client.post(f"{self.base_url}/sendPhoto", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def send_video(
        self,
        chat_id: int,
        video: str,
        caption: Optional[str] = None,
        reply_markup: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Send video"""
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "video": video,
                "disable_notification": False,
            }
            if caption:
                payload["caption"] = caption
                payload["parse_mode"] = "HTML"
            if reply_markup:
                payload["reply_markup"] = reply_markup

            response = await client.post(f"{self.base_url}/sendVideo", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def send_document(
        self,
        chat_id: int,
        document: str,
        caption: Optional[str] = None,
        reply_markup: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Send document"""
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "document": document,
            }
            if caption:
                payload["caption"] = caption
                payload["parse_mode"] = "HTML"
            if reply_markup:
                payload["reply_markup"] = reply_markup

            response = await client.post(f"{self.base_url}/sendDocument", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def send_audio(
        self,
        chat_id: int,
        audio: str,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send audio file"""
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "audio": audio,
            }
            if caption:
                payload["caption"] = caption

            response = await client.post(f"{self.base_url}/sendAudio", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def send_voice(
        self,
        chat_id: int,
        voice: str,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send voice message"""
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "voice": voice,
            }
            if caption:
                payload["caption"] = caption

            response = await client.post(f"{self.base_url}/sendVoice", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def send_location(
        self,
        chat_id: int,
        latitude: float,
        longitude: float,
        reply_markup: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Send location"""
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "latitude": latitude,
                "longitude": longitude,
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            response = await client.post(f"{self.base_url}/sendLocation", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str,
        show_alert: bool = False,
    ) -> Dict[str, Any]:
        """Answer callback query (button click)"""
        async with httpx.AsyncClient() as client:
            payload = {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
            }
            response = await client.post(f"{self.base_url}/answerCallbackQuery", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def set_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """Register webhook URL"""
        async with httpx.AsyncClient() as client:
            payload = {
                "url": webhook_url,
                "allowed_updates": [
                    "message",
                    "edited_message",
                    "channel_post",
                    "callback_query",
                    "my_chat_member",
                ],
            }
            response = await client.post(f"{self.base_url}/setWebhook", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def delete_webhook(self) -> Dict[str, Any]:
        """Delete webhook"""
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/deleteWebhook")
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def set_my_commands(self, commands: List[Dict[str, str]]) -> Dict[str, Any]:
        """Set bot commands menu"""
        async with httpx.AsyncClient() as client:
            payload = {"commands": commands}
            response = await client.post(f"{self.base_url}/setMyCommands", json=payload)
            response.raise_for_status()
            return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_file(self, file_id: str) -> Dict[str, Any]:
        """Get file info from Telegram"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/getFile", params={"file_id": file_id})
            response.raise_for_status()
            return response.json()


# ============================================================================
# FastAPI App & Routes
# ============================================================================

app = FastAPI(
    title="Telegram Channel Service",
    description="Multi-tenant Telegram bot management",
    version="1.0.0",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="telegram")
init_sentry(service_name="telegram", service_port=9016)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="telegram")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# In-memory bot client cache (key: tenant_id → TelegramBotClient)
bot_clients: Dict[str, TelegramBotClient] = {}


@app.on_event("startup")
async def startup():
    """Initialize database on service start"""
    await db.initialize()
    await event_bus.startup()
    logger.info("Telegram Service started on port 9016")


@app.on_event("shutdown")
async def shutdown():
    """Close database on service shutdown"""
    await db.close()
    shutdown_tracing()


# ─── Bot Setup ───


@app.post("/api/v1/bots/register")
async def register_bot(
    bot_token: str,
    webhook_url: str,
    auth: AuthContext = Depends(get_auth),
):
    """Register Telegram bot for tenant"""
    tenant_id = auth.tenant_id

    # Validate bot token with Telegram
    bot_client = TelegramBotClient(bot_token)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            response.raise_for_status()
            bot_info = response.json()
            if not bot_info.get("ok"):
                raise HTTPException(status_code=400, detail="Invalid bot token")

            bot_data = bot_info["result"]
            bot_username = bot_data["username"]
            bot_name = bot_data["first_name"]
    except httpx.HTTPError as e:
        logger.error("Bot validation error: %s", str(e))
        raise HTTPException(status_code=400, detail="Failed to validate bot token")

    # Set webhook
    try:
        await bot_client.set_webhook(webhook_url)
    except Exception as e:
        logger.error("Failed to set webhook: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to set webhook")

    # Store bot config in database
    bot_id = str(uuid4())
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO telegram_bot_configs (
                id, tenant_id, bot_token, bot_username, bot_name,
                webhook_url, is_active, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (tenant_id) DO UPDATE
            SET bot_token = EXCLUDED.bot_token, is_active = true,
                webhook_url = EXCLUDED.webhook_url, updated_at = EXCLUDED.updated_at
            """,
            bot_id, tenant_id, bot_token, bot_username, bot_name,
            webhook_url, True, utc_now(), utc_now()
        )

    # Cache bot client
    bot_clients[tenant_id] = bot_client

    logger.info("Bot registered: @%s for tenant %s", bot_username, tenant_id)

    return {
        "bot_id": bot_id,
        "bot_username": bot_username,
        "bot_name": bot_name,
        "webhook_url": webhook_url,
        "status": "active",
    }


@app.get("/api/v1/bots/config")
async def get_bot_config(auth: AuthContext = Depends(get_auth)):
    """Get bot configuration for tenant"""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        config_row = await conn.fetchrow(
            "SELECT * FROM telegram_bot_configs WHERE tenant_id = $1",
            tenant_id
        )

    if not config_row:
        raise HTTPException(status_code=404, detail="Bot not configured")

    return {
        "id": config_row["id"],
        "bot_username": config_row["bot_username"],
        "bot_name": config_row["bot_name"],
        "is_active": config_row["is_active"],
        "commands": config_row.get("commands", {}),
        "created_at": config_row["created_at"],
    }


# ─── Webhook ───


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request):
    """Receive Telegram updates (message, callback_query, etc.)"""
    # Verify webhook signature using Telegram's secret_token
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    expected_token = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

    if not expected_token or not hmac.compare_digest(secret_token, expected_token):
        logger.warning("Invalid Telegram webhook token")
        raise HTTPException(status_code=403, detail="Invalid webhook token")

    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Extract tenant_id from update (sent in webhook setup)
    tenant_id = data.get("tenant_id")
    if not tenant_id:
        # Try to infer from bot token in database
        logger.warning("Webhook missing tenant_id")
        return {"ok": False}

    # Get bot client - validate tenant exists in database
    if tenant_id not in bot_clients:
        try:
            async with db.tenant_connection(tenant_id) as conn:
                config_row = await conn.fetchrow(
                    "SELECT bot_token FROM telegram_bot_configs WHERE tenant_id = $1 AND is_active = true",
                    tenant_id
                )
        except Exception as e:
            logger.error("Database error looking up tenant %s: %s", tenant_id, str(e))
            return {"ok": False}

        if not config_row:
            logger.warning("Bot not found or inactive for tenant %s", tenant_id)
            return {"ok": False}
        bot_clients[tenant_id] = TelegramBotClient(config_row["bot_token"])

    bot_client = bot_clients[tenant_id]

    # Process different update types
    if "message" in data:
        await _process_message(data["message"], tenant_id, bot_client)
    elif "callback_query" in data:
        await _process_callback_query(data["callback_query"], tenant_id, bot_client)
    elif "my_chat_member" in data:
        await _process_chat_member(data["my_chat_member"], tenant_id)

    return {"ok": True}


async def _process_message(message_data: Dict[str, Any], tenant_id: str, bot_client: TelegramBotClient):
    """Process inbound message"""
    message_id = message_data.get("message_id")
    from_user = message_data.get("from", {})
    chat = message_data.get("chat", {})
    user_id = from_user.get("id")
    chat_id = chat.get("id")
    text = message_data.get("text", "")
    caption = message_data.get("caption", "")

    # Determine message type
    if "text" in message_data:
        msg_type = MessageType.TEXT
        content = text
    elif "photo" in message_data:
        msg_type = MessageType.PHOTO
        content = caption
        media_url = message_data["photo"][-1].get("file_id")
    elif "video" in message_data:
        msg_type = MessageType.VIDEO
        content = caption
        media_url = message_data["video"].get("file_id")
    elif "document" in message_data:
        msg_type = MessageType.DOCUMENT
        content = caption
        media_url = message_data["document"].get("file_id")
    elif "audio" in message_data:
        msg_type = MessageType.AUDIO
        content = caption
        media_url = message_data["audio"].get("file_id")
    elif "voice" in message_data:
        msg_type = MessageType.VOICE
        content = caption
        media_url = message_data["voice"].get("file_id")
    elif "location" in message_data:
        msg_type = MessageType.LOCATION
        location = message_data["location"]
        content = f"Location: {location.get('latitude')},{location.get('longitude')}"
        media_url = None
    elif "contact" in message_data:
        msg_type = MessageType.CONTACT
        contact = message_data["contact"]
        content = f"Contact: {contact.get('first_name')} {contact.get('phone_number')}"
        media_url = None
    else:
        logger.warning("Unknown message type in %s", message_data)
        return

    # Check for bot commands
    if msg_type == MessageType.TEXT and text.startswith("/"):
        command = text.split()[0].lstrip("/")
        await _handle_bot_command(command, user_id, chat_id, tenant_id, bot_client)

    # Store message
    record_id = str(uuid4())
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO telegram_messages (
                id, tenant_id, telegram_message_id, telegram_user_id,
                telegram_chat_id, message_type, content, status, direction,
                media_url, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            """,
            record_id, tenant_id, message_id, user_id, chat_id,
            msg_type.value, sanitize_input(content), MessageStatus.DELIVERED,
            MessageDirection.INBOUND, media_url, utc_now(), utc_now()
        )

    logger.info("Inbound message: %s from user %s in chat %s", record_id, user_id, chat_id)

    # Forward to Channel Router
    await _forward_to_channel_router(tenant_id, "telegram", {
        "message_id": message_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "type": msg_type.value,
        "content": content,
        "media_url": media_url,
    })


async def _process_callback_query(query_data: Dict[str, Any], tenant_id: str, bot_client: TelegramBotClient):
    """Process inline button click"""
    query_id = query_data.get("id")
    from_user = query_data.get("from", {})
    user_id = from_user.get("id")
    button_data = query_data.get("data", "")
    message_id = query_data.get("message", {}).get("message_id")
    chat_id = query_data.get("message", {}).get("chat", {}).get("id")

    logger.info("Callback query from user %s: %s", user_id, button_data)

    # Answer callback query
    try:
        await bot_client.answer_callback_query(
            query_id,
            f"Button pressed: {button_data}",
            show_alert=False
        )
    except Exception as e:
        logger.error("Failed to answer callback: %s", str(e))

    # Forward to Channel Router for custom handling
    await _forward_to_channel_router(tenant_id, "telegram_callback", {
        "callback_query_id": query_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "data": button_data,
    })


async def _process_chat_member(member_data: Dict[str, Any], tenant_id: str):
    """Process bot added/removed from group"""
    chat = member_data.get("chat", {})
    chat_id = chat.get("id")
    new_member = member_data.get("new_chat_member", {})
    status = new_member.get("status")  # member, administrator, left, kicked

    logger.info("Chat member update: chat %s, status %s", chat_id, status)


async def _handle_bot_command(command: str, user_id: int, chat_id: int, tenant_id: str, bot_client: TelegramBotClient):
    """Handle bot commands (/start, /help, /status)"""
    if command == "start":
        response = f"Welcome to PriyaAI! I'm here to help with your sales inquiries."
    elif command == "help":
        response = "Available commands:\n/start - Start conversation\n/help - Show this help\n/status - Bot status"
    elif command == "status":
        response = "Bot is online and ready to assist."
    else:
        response = f"Unknown command: /{command}"

    try:
        await bot_client.send_message(chat_id, response)
    except Exception as e:
        logger.error("Failed to send command response: %s", str(e))


async def _forward_to_channel_router(tenant_id: str, channel: str, payload: Dict[str, Any]):
    """Forward inbound message to Channel Router service"""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"http://localhost:{config.ports.channel_router}/api/v1/inbound",
                json={
                    "tenant_id": tenant_id,
                    "channel": channel,
                    "payload": payload,
                },
                timeout=10,
            )
        except httpx.HTTPError as e:
            logger.error("Failed to forward to Channel Router: %s", str(e))


# ─── API Endpoints ───


@app.post("/api/v1/send")
async def send_message(
    request: SendMessageRequest,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = None,
):
    """Send Telegram message"""
    tenant_id = auth.tenant_id

    # Get bot client for tenant
    if tenant_id not in bot_clients:
        async with db.tenant_connection(tenant_id) as conn:
            config_row = await conn.fetchrow(
                "SELECT bot_token FROM telegram_bot_configs WHERE tenant_id = $1 AND is_active = true",
                tenant_id
            )
        if not config_row:
            raise HTTPException(status_code=404, detail="Bot not configured")
        bot_clients[tenant_id] = TelegramBotClient(config_row["bot_token"])

    bot_client = bot_clients[tenant_id]

    # Build reply markup if keyboard provided
    reply_markup = None
    if request.inline_keyboard:
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": btn.text,
                        "callback_data": btn.callback_data or btn.text,
                        "url": btn.url,
                    }
                    for btn in row
                    if btn.callback_data or btn.url
                ]
                for row in request.inline_keyboard.buttons
            ]
        }

    # Send based on message type
    try:
        if request.message_type == MessageType.TEXT:
            response = await bot_client.send_message(
                request.chat_id,
                request.content,
                parse_mode=request.parse_mode,
                reply_markup=reply_markup,
                disable_notifications=request.disable_notifications,
                reply_to_message_id=request.reply_to_message_id,
            )
        elif request.message_type == MessageType.PHOTO:
            response = await bot_client.send_photo(
                request.chat_id,
                request.photo_url or request.content,
                caption=request.caption,
                reply_markup=reply_markup,
                disable_notifications=request.disable_notifications,
            )
        elif request.message_type == MessageType.VIDEO:
            response = await bot_client.send_video(
                request.chat_id,
                request.video_url or request.content,
                caption=request.caption,
                reply_markup=reply_markup,
            )
        elif request.message_type == MessageType.DOCUMENT:
            response = await bot_client.send_document(
                request.chat_id,
                request.document_url or request.content,
                caption=request.caption,
                reply_markup=reply_markup,
            )
        elif request.message_type == MessageType.AUDIO:
            response = await bot_client.send_audio(
                request.chat_id,
                request.content,
                caption=request.caption,
            )
        elif request.message_type == MessageType.VOICE:
            response = await bot_client.send_voice(
                request.chat_id,
                request.content,
                caption=request.caption,
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported message type")

    except httpx.HTTPError as e:
        logger.error("Failed to send message: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to send message")

    # Store outbound message record
    if response.get("ok"):
        message_id = response.get("result", {}).get("message_id")
        record_id = str(uuid4())

        async with db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO telegram_messages (
                    id, tenant_id, telegram_message_id, telegram_chat_id,
                    message_type, content, status, direction, caption,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                record_id, tenant_id, message_id, request.chat_id,
                request.message_type.value, sanitize_input(request.content),
                MessageStatus.SENT, MessageDirection.OUTBOUND,
                request.caption, utc_now(), utc_now()
            )

        logger.info("Message sent: %s to chat %s", message_id, request.chat_id)

        return {
            "message_id": message_id,
            "chat_id": request.chat_id,
            "status": "sent",
            "type": request.message_type.value,
        }
    else:
        raise HTTPException(status_code=500, detail="Telegram API error")


@app.get("/api/v1/messages/{message_id}")
async def get_message(
    message_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get message details"""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        message = await conn.fetchrow(
            "SELECT * FROM telegram_messages WHERE id = $1 AND tenant_id = $2",
            message_id, tenant_id
        )

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    return TelegramMessage(
        id=message["id"],
        tenant_id=message["tenant_id"],
        telegram_message_id=message["telegram_message_id"],
        telegram_user_id=message.get("telegram_user_id", 0),
        telegram_chat_id=message["telegram_chat_id"],
        message_type=message["message_type"],
        content=message["content"],
        status=message["status"],
        direction=message["direction"],
        media_url=message.get("media_url"),
        caption=message.get("caption"),
        created_at=message["created_at"],
        updated_at=message["updated_at"],
    ).dict()


@app.post("/api/v1/commands")
async def set_commands(
    commands: List[BotCommandConfig],
    auth: AuthContext = Depends(get_auth),
):
    """Configure bot commands for tenant"""
    tenant_id = auth.tenant_id

    if tenant_id not in bot_clients:
        raise HTTPException(status_code=404, detail="Bot not configured")

    bot_client = bot_clients[tenant_id]

    try:
        await bot_client.set_my_commands([
            {"command": cmd.command, "description": cmd.description}
            for cmd in commands
        ])
    except Exception as e:
        logger.error("Failed to set commands: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to set commands")

    # Store commands in database
    commands_dict = {cmd.command: cmd.description for cmd in commands}
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE telegram_bot_configs SET commands = $1, updated_at = $2 WHERE tenant_id = $3",
            json.dumps(commands_dict), utc_now(), tenant_id
        )

    logger.info("Commands updated for tenant %s: %d commands", tenant_id, len(commands))

    return {"commands": len(commands), "status": "updated"}


# ─── Analytics ───


@app.get("/api/v1/analytics")
async def get_analytics(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    auth: AuthContext = Depends(get_auth),
):
    """Get Telegram analytics for tenant"""
    tenant_id = auth.tenant_id

    try:
        period_start = datetime.fromisoformat(start_date)
        period_end = datetime.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (use YYYY-MM-DD)")

    async with db.tenant_connection(tenant_id) as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) as total_messages,
                COUNT(*) FILTER (WHERE direction = 'inbound') as total_inbound,
                COUNT(*) FILTER (WHERE direction = 'outbound') as total_outbound,
                COUNT(*) FILTER (WHERE message_type = 'text') as total_text,
                COUNT(*) FILTER (WHERE message_type IN ('photo', 'video', 'document', 'audio', 'voice', 'location') ) as total_media,
                COUNT(DISTINCT telegram_user_id) as unique_users,
                COUNT(DISTINCT telegram_chat_id) as unique_chats
            FROM telegram_messages
            WHERE tenant_id = $1 AND created_at >= $2 AND created_at <= $3
            """,
            tenant_id, period_start, period_end
        )

    return TelegramAnalytics(
        period_start=period_start,
        period_end=period_end,
        total_messages=stats["total_messages"] or 0,
        total_inbound=stats["total_inbound"] or 0,
        total_outbound=stats["total_outbound"] or 0,
        total_text=stats["total_text"] or 0,
        total_media=stats["total_media"] or 0,
        unique_users=stats["unique_users"] or 0,
        unique_groups=stats["unique_chats"] or 0,
    ).dict()


@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "telegram",
        "port": config.ports.telegram,
    }


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=config.ports.telegram)
