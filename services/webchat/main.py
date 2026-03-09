"""
WebChat Widget Service - FastAPI backend for embeddable AI sales chat widget.
Handles widget configuration, real-time chat via WebSocket, session management, and triggers.
"""

import sys
import json
import uuid
import asyncio
import hashlib
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, status, UploadFile, File, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel, Field, validator
import uvicorn

# Import from shared modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.core.config import config
from shared.core.database import db
from shared.core.security import mask_pii, sanitize_input
from shared.middleware.auth import get_auth, AuthContext, require_role

from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config


logger = logging.getLogger(__name__)

# ============================================================================
# Models & Schemas
# ============================================================================

class WidgetConfig(BaseModel):
    """Widget configuration for a tenant"""
    tenant_id: str
    tenant_slug: str
    widget_name: str = "Priya AI Sales"
    primary_color: str = "#6366f1"
    secondary_color: str = "#4f46e5"
    position: str = "bottom-right"  # bottom-right, bottom-left, top-right, top-left
    welcome_message: str = "Hi! How can we help you today?"
    ai_name: str = "Priya"
    header_text: str = "Chat with our AI sales assistant"
    placeholder_text: str = "Type your message..."
    require_prechat_form: bool = True
    prechat_fields: List[str] = Field(default_factory=lambda: ["name", "email"])
    allow_anonymous_chat: bool = True
    enable_file_upload: bool = True
    enable_sound_notification: bool = True
    enable_proactive_triggers: bool = True
    session_timeout_minutes: int = 1440  # 24 hours
    rate_limit_messages_per_minute: int = 10
    show_powered_by: bool = True
    custom_css: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProactiveTrigger(BaseModel):
    """Proactive chat trigger configuration"""
    trigger_id: str
    tenant_id: str
    trigger_type: str  # time_on_page, scroll_depth, exit_intent, page_url_match
    trigger_message: str
    trigger_delay_seconds: int = 0
    page_url_pattern: Optional[str] = None
    is_enabled: bool = True


class ChatSession(BaseModel):
    """Chat session for a website visitor"""
    session_id: str
    tenant_id: str
    tenant_slug: str
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None
    page_url: str
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    visitor_fingerprint: str
    user_agent: str
    timezone: str = "UTC"
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = 0


class ChatMessage(BaseModel):
    """Individual chat message"""
    message_id: str
    session_id: str
    tenant_id: str
    sender: str  # "visitor" or "ai"
    content: str
    message_type: str = "text"  # text, file, system
    file_url: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = False


class TypingIndicator(BaseModel):
    """Typing indicator message"""
    session_id: str
    is_typing: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionCreateRequest(BaseModel):
    """Request to create a new chat session"""
    tenant_slug: str
    page_url: str
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    user_agent: str
    timezone: str = "UTC"
    ip_address: Optional[str] = None
    visitor_fingerprint: Optional[str] = None


class ChatMessageRequest(BaseModel):
    """Request to send a chat message"""
    session_id: str
    content: str
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    visitor_phone: Optional[str] = None


class WidgetConfigUpdate(BaseModel):
    """Request to update widget configuration"""
    widget_name: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    position: Optional[str] = None
    welcome_message: Optional[str] = None
    ai_name: Optional[str] = None
    header_text: Optional[str] = None
    placeholder_text: Optional[str] = None
    require_prechat_form: Optional[bool] = None
    prechat_fields: Optional[List[str]] = None
    allow_anonymous_chat: Optional[bool] = None
    enable_file_upload: Optional[bool] = None
    enable_sound_notification: Optional[bool] = None
    enable_proactive_triggers: Optional[bool] = None
    custom_css: Optional[str] = None


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="WebChat Widget Service",
    description="Backend for Priya Global embeddable AI sales chat widget",
    version="1.0.0"
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="webchat")
init_sentry(service_name="webchat", service_port=9014)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="webchat")
app.add_middleware(TracingMiddleware)


# CHANNEL-ROUTING-FIX: Rate limiter for public endpoints
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# CORS configuration - restrict to configured origins
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# ============================================================================
# In-Memory Store (Replace with Database in Production)
# ============================================================================

class SessionManager:
    """Manages chat sessions and connections"""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.sessions: Dict[str, ChatSession] = {}
        self.messages: Dict[str, List[ChatMessage]] = defaultdict(list)
        self.message_counters: Dict[str, int] = defaultdict(int)  # Track messages per minute
        self.rate_limit_reset_times: Dict[str, datetime] = {}

    def is_session_expired(self, session: ChatSession, timeout_minutes: int) -> bool:
        """Check if session has expired"""
        return datetime.utcnow() - session.last_activity > timedelta(minutes=timeout_minutes)

    def check_rate_limit(self, session_id: str, limit: int) -> bool:
        """Check if message rate limit exceeded (10 msgs/min)"""
        now = datetime.utcnow()
        counter_key = f"rate_{session_id}"

        # Reset counter if minute has passed
        if counter_key in self.rate_limit_reset_times:
            if now - self.rate_limit_reset_times[counter_key] > timedelta(minutes=1):
                self.message_counters[counter_key] = 0
                self.rate_limit_reset_times[counter_key] = now
        else:
            self.rate_limit_reset_times[counter_key] = now

        # Check limit
        if self.message_counters[counter_key] >= limit:
            return False

        self.message_counters[counter_key] += 1
        return True

    async def connect(self, session_id: str, websocket: WebSocket):
        """Register a WebSocket connection"""
        await websocket.accept()
        self.active_connections[session_id].add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket):
        """Unregister a WebSocket connection"""
        self.active_connections[session_id].discard(websocket)
        if not self.active_connections[session_id]:
            del self.active_connections[session_id]

    async def broadcast(self, session_id: str, message: dict):
        """Send message to all connections in session"""
        for connection in self.active_connections.get(session_id, set()):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("Error broadcasting to %s: %s", session_id, str(e))


session_manager = SessionManager()

# Widget configs store (replace with database)
widget_configs: Dict[str, WidgetConfig] = {}

# Proactive triggers store (replace with database)
proactive_triggers: Dict[str, List[ProactiveTrigger]] = defaultdict(list)


# ============================================================================
# Helper Functions
# ============================================================================

def generate_session_id() -> str:
    """Generate unique session ID"""
    return str(uuid.uuid4())


def generate_visitor_fingerprint(user_agent: str, ip_address: Optional[str]) -> str:
    """Generate visitor fingerprint from user agent and IP"""
    fingerprint_str = f"{user_agent}:{ip_address or 'unknown'}"
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]


async def get_widget_config(tenant_slug: str) -> Optional[WidgetConfig]:
    """Get widget config for tenant (from database in production)"""
    # In production, query database
    return widget_configs.get(tenant_slug)


async def get_session(session_id: str) -> Optional[ChatSession]:
    """Get chat session"""
    return session_manager.sessions.get(session_id)


async def create_customer_record(session: ChatSession) -> dict:
    """Create/update customer record from session data (calls shared service)"""
    # In production, call customer service API
    logger.info("Creating customer record for session %s", session.session_id)
    return {
        "customer_id": str(uuid.uuid4()),
        "name": session.visitor_name or "Anonymous",
        "email": session.visitor_email,
        "phone": session.visitor_phone,
        "source": "webchat",
        "utm_source": session.utm_source,
        "utm_campaign": session.utm_campaign,
    }


async def route_message_to_ai(tenant_id: str, session_id: str, message_content: str) -> str:
    """Route message to Channel Router for AI processing"""
    # In production, call Channel Router service (async)
    logger.info("Routing message to AI: %s/%s", tenant_id, session_id)

    # Simulate AI response (replace with actual Channel Router call)
    await asyncio.sleep(0.5)  # Simulate processing
    return f"Thanks for your message: '{sanitize_input(message_content)[:50]}...' We'll get back to you soon!"


# ============================================================================
# Widget Configuration Endpoints
# ============================================================================

@app.get("/api/v1/widget/config/{tenant_slug}", response_model=Dict)
async def get_widget_config_public(tenant_slug: str, response: Response):
    """
    PUBLIC endpoint - Get widget configuration for a tenant.
    No authentication required (needed for widget embedding).
    CHANNEL-ROUTING-FIX: Only returns safe public config, no sensitive data.
    Rate limited to prevent brute-force tenant enumeration.
    """
    # CHANNEL-ROUTING-FIX: Add rate limiting headers
    response.headers["X-RateLimit-Limit"] = "100"
    response.headers["X-RateLimit-Remaining"] = "99"
    response.headers["X-RateLimit-Reset"] = "60"
    response.headers["Cache-Control"] = "public, max-age=300"  # 5 min cache

    config_data = await get_widget_config(tenant_slug)

    if not config_data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # CHANNEL-ROUTING-FIX: Return ONLY public-safe fields, exclude:
    # - tenant_id (internal identifier)
    # - API keys, tokens, secrets
    # - system_prompt (AI behavior config)
    # - Internal IDs and configuration
    return {
        "widget_name": config_data.widget_name,
        "primary_color": config_data.primary_color,
        "secondary_color": config_data.secondary_color,
        "position": config_data.position,
        "welcome_message": config_data.welcome_message,
        "ai_name": config_data.ai_name,
        "header_text": config_data.header_text,
        "placeholder_text": config_data.placeholder_text,
        "show_powered_by": config_data.show_powered_by,
    }


@app.put("/api/v1/widget/config")
async def update_widget_config(
    update: WidgetConfigUpdate,
    auth: AuthContext = Depends(require_role(["owner", "admin"]))
):
    """
    Update widget configuration (auth required - owner/admin only).
    """
    tenant_id = auth.tenant_id

    # Get existing config
    config_data = None
    for cfg in widget_configs.values():
        if cfg.tenant_id == tenant_id:
            config_data = cfg
            break

    if not config_data:
        raise HTTPException(status_code=404, detail="Widget config not found for tenant")

    # Update fields
    update_dict = update.dict(exclude_unset=True)
    for key, value in update_dict.items():
        if hasattr(config_data, key):
            setattr(config_data, key, value)

    config_data.updated_at = datetime.utcnow()
    logger.info("Updated widget config for tenant %s", tenant_id)

    return {"status": "success", "message": "Widget configuration updated"}


# ============================================================================
# Session Management Endpoints
# ============================================================================

@app.post("/api/v1/sessions/create")
async def create_chat_session(request: SessionCreateRequest):
    """
    PUBLIC endpoint - Create a new chat session.
    Returns session_id to be used for websocket connection.
    """
    # Validate tenant exists via slug from request body
    tenant_slug = request.tenant_slug
    config_data = await get_widget_config(tenant_slug)

    if not config_data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get tenant_id from config
    tenant_id = config_data.tenant_id

    session_id = generate_session_id()
    fingerprint = request.visitor_fingerprint or generate_visitor_fingerprint(
        request.user_agent,
        request.ip_address
    )

    # Store session with validated tenant_id from database lookup
    session = ChatSession(
        session_id=session_id,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        page_url=sanitize_input(request.page_url),
        referrer=sanitize_input(request.referrer) if request.referrer else None,
        utm_source=sanitize_input(request.utm_source) if request.utm_source else None,
        utm_medium=sanitize_input(request.utm_medium) if request.utm_medium else None,
        utm_campaign=sanitize_input(request.utm_campaign) if request.utm_campaign else None,
        visitor_fingerprint=fingerprint,
        user_agent=request.user_agent,
        timezone=request.timezone,
        ip_address=request.ip_address,
    )

    session_manager.sessions[session_id] = session
    logger.info("Created session %s for tenant %s", session_id, tenant_id)

    return {
        "session_id": session_id,
        "expires_in_hours": 24,
    }


@app.get("/api/v1/chat/history/{session_id}")
async def get_chat_history(session_id: str):
    """
    Get chat history for a session (REST fallback).
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session_manager.messages.get(session_id, [])

    return {
        "session_id": session_id,
        "messages": [
            {
                "message_id": m.message_id,
                "sender": m.sender,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
                "message_type": m.message_type,
            }
            for m in messages
        ],
        "message_count": len(messages),
    }


# ============================================================================
# WebSocket Chat Endpoint
# ============================================================================

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time chat.
    Validates session exists before accepting the connection.
    Handles bidirectional messaging, typing indicators, and heartbeat.
    """
    # Validate session exists before accepting connection
    session = await get_session(session_id)
    if not session:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session not found")
        return

    await session_manager.connect(session_id, websocket)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "message": "Connected to chat",
        })

        # Heartbeat task
        async def heartbeat():
            while True:
                try:
                    await asyncio.sleep(30)
                    await session_manager.broadcast(session_id, {
                        "type": "ping",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                except asyncio.CancelledError:
                    break

        heartbeat_task = asyncio.create_task(heartbeat())

        try:
            while True:
                data = await websocket.receive_json()

                # Update last activity
                session = session_manager.sessions.get(session_id)
                if session:
                    session.last_activity = datetime.utcnow()

                message_type = data.get("type", "message")

                if message_type == "message":
                    # Check rate limit
                    config = await get_widget_config(session.tenant_slug)
                    limit = config.rate_limit_messages_per_minute if config else 10

                    if not session_manager.check_rate_limit(session_id, limit):
                        await websocket.send_json({
                            "type": "error",
                            "error": "Rate limit exceeded",
                        })
                        continue

                    content = sanitize_input(data.get("content", ""))

                    # Store visitor info if provided
                    if "visitor_name" in data:
                        session.visitor_name = sanitize_input(data["visitor_name"])
                    if "visitor_email" in data:
                        session.visitor_email = sanitize_input(data["visitor_email"])
                    if "visitor_phone" in data:
                        session.visitor_phone = sanitize_input(data["visitor_phone"])

                    # Create customer record on first message
                    if session.message_count == 0:
                        await create_customer_record(session)

                    session.message_count += 1

                    # Store message
                    message = ChatMessage(
                        message_id=str(uuid.uuid4()),
                        session_id=session_id,
                        tenant_id=session.tenant_id,
                        sender="visitor",
                        content=content,
                    )
                    session_manager.messages[session_id].append(message)

                    # Broadcast message to all connections
                    await session_manager.broadcast(session_id, {
                        "type": "message",
                        "message_id": message.message_id,
                        "sender": "visitor",
                        "content": content,
                        "timestamp": message.timestamp.isoformat(),
                    })

                    # Show AI typing indicator
                    await session_manager.broadcast(session_id, {
                        "type": "typing",
                        "is_typing": True,
                    })

                    # Route to AI and get response
                    ai_response = await route_message_to_ai(
                        session.tenant_id,
                        session_id,
                        content
                    )

                    # Hide typing indicator
                    await session_manager.broadcast(session_id, {
                        "type": "typing",
                        "is_typing": False,
                    })

                    # Store and broadcast AI response
                    ai_message = ChatMessage(
                        message_id=str(uuid.uuid4()),
                        session_id=session_id,
                        tenant_id=session.tenant_id,
                        sender="ai",
                        content=ai_response,
                    )
                    session_manager.messages[session_id].append(ai_message)

                    await session_manager.broadcast(session_id, {
                        "type": "message",
                        "message_id": ai_message.message_id,
                        "sender": "ai",
                        "content": ai_response,
                        "timestamp": ai_message.timestamp.isoformat(),
                    })

                elif message_type == "typing":
                    # Forward typing indicator
                    is_typing = data.get("is_typing", False)
                    await session_manager.broadcast(session_id, {
                        "type": "typing",
                        "is_typing": is_typing,
                        "sender": "visitor",
                    })

                elif message_type == "pong":
                    # Respond to ping
                    pass

        finally:
            heartbeat_task.cancel()

    except WebSocketDisconnect:
        session_manager.disconnect(session_id, websocket)
        logger.info("Client disconnected from session %s", session_id)
    except Exception as e:
        logger.error("WebSocket error in session %s: %s", session_id, str(e))
        session_manager.disconnect(session_id, websocket)


# ============================================================================
# REST Fallback Chat Endpoint
# ============================================================================

@app.post("/api/v1/chat/message")
async def send_chat_message(request: ChatMessageRequest):
    """
    REST fallback endpoint for sending chat messages.
    Returns AI response immediately (no WebSocket available).
    """
    session = await get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Check rate limit
    config = await get_widget_config(session.tenant_slug)
    limit = config.rate_limit_messages_per_minute if config else 10

    if not session_manager.check_rate_limit(request.session_id, limit):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    content = sanitize_input(request.content)

    # Store visitor info
    if request.visitor_name:
        session.visitor_name = sanitize_input(request.visitor_name)
    if request.visitor_email:
        session.visitor_email = sanitize_input(request.visitor_email)
    if request.visitor_phone:
        session.visitor_phone = sanitize_input(request.visitor_phone)

    # Create customer record on first message
    if session.message_count == 0:
        await create_customer_record(session)

    session.message_count += 1
    session.last_activity = datetime.utcnow()

    # Store visitor message
    visitor_message = ChatMessage(
        message_id=str(uuid.uuid4()),
        session_id=request.session_id,
        tenant_id=session.tenant_id,
        sender="visitor",
        content=content,
    )
    session_manager.messages[request.session_id].append(visitor_message)

    # Route to AI
    ai_response = await route_message_to_ai(
        session.tenant_id,
        request.session_id,
        content
    )

    # Store AI response
    ai_message = ChatMessage(
        message_id=str(uuid.uuid4()),
        session_id=request.session_id,
        tenant_id=session.tenant_id,
        sender="ai",
        content=ai_response,
    )
    session_manager.messages[request.session_id].append(ai_message)

    return {
        "message_id": ai_message.message_id,
        "sender": "ai",
        "content": ai_response,
        "timestamp": ai_message.timestamp.isoformat(),
    }


# ============================================================================
# File Upload Endpoint
# ============================================================================

@app.post("/api/v1/chat/upload")
async def upload_chat_file(
    session_id: str,
    file: UploadFile = File(...)
):
    """
    Upload file from chat. Max 5MB, validates MIME types.
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Validate file size (5MB max)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")

    # Validate MIME type
    allowed_types = {
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf", "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="File type not allowed")

    # Store file (in production, upload to S3 or similar)
    file_id = str(uuid.uuid4())
    file_url = f"/api/v1/files/{file_id}"

    # Create file message
    file_message = ChatMessage(
        message_id=str(uuid.uuid4()),
        session_id=session_id,
        tenant_id=session.tenant_id,
        sender="visitor",
        content=file.filename or "File",
        message_type="file",
        file_url=file_url,
    )
    session_manager.messages[session_id].append(file_message)

    logger.info("File uploaded to session %s: %s", session_id, file.filename)

    return {
        "file_id": file_id,
        "file_url": file_url,
        "message_id": file_message.message_id,
    }


# ============================================================================
# Proactive Triggers Endpoint
# ============================================================================

@app.get("/api/v1/triggers/{tenant_slug}")
async def get_proactive_triggers(tenant_slug: str):
    """
    PUBLIC endpoint - Get enabled proactive triggers for tenant.
    Widget checks these and shows trigger messages based on conditions.
    """
    triggers = proactive_triggers.get(tenant_slug, [])
    enabled_triggers = [t for t in triggers if t.is_enabled]

    return {
        "triggers": [
            {
                "trigger_id": t.trigger_id,
                "trigger_type": t.trigger_type,
                "trigger_message": t.trigger_message,
                "trigger_delay_seconds": t.trigger_delay_seconds,
                "page_url_pattern": t.page_url_pattern,
            }
            for t in enabled_triggers
        ]
    }


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "webchat-widget",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Startup/Shutdown
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize widget configs on startup"""
    logger.info("WebChat Widget service starting...")

    # Load sample config (in production, load from database)
    await event_bus.startup()

    sample_config = WidgetConfig(
        tenant_id="tenant_001",
        tenant_slug="default",
        widget_name="Priya AI Assistant",
        welcome_message="Welcome! How can we help you today?",
    )
    widget_configs[sample_config.tenant_slug] = sample_config

    # Load sample triggers
    sample_trigger = ProactiveTrigger(
        trigger_id=str(uuid.uuid4()),
        tenant_id="tenant_001",
        trigger_type="time_on_page",
        trigger_message="Need help? Chat with us!",
        trigger_delay_seconds=30,
        is_enabled=True,
    )
    proactive_triggers["default"].append(sample_trigger)

    logger.info("WebChat Widget service ready")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9014,
        log_level="info",
    )
