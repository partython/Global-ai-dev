"""
Conversation Service - Real-time Chat and Messaging

Manages conversations, messages, and real-time updates for the Priya Global Platform.
Features:
- REST API for conversation management
- WebSocket endpoints for real-time chat
- Redis pub/sub for cross-instance message distribution
- JWT authentication and tenant isolation
- Message persistence and history
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import redis.asyncio as aioredis

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.core.config import config
from shared.core.security import sanitize_input
from shared.middleware.auth import get_auth, AuthContext, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config
from shared.cache.redis_client import TenantCache
from shared.realtime.websocket_manager import get_websocket_manager
from shared.realtime.events import parse_ws_message, create_error_message, create_pong_message

logger = logging.getLogger("priya.conversation")

# ============================================================================
# Configuration
# ============================================================================

PORT = int(os.getenv("CONVERSATION_SERVICE_PORT", 9004))
SERVICE_NAME = "conversation"

# ============================================================================
# Pydantic Models
# ============================================================================

class Message(BaseModel):
    """A single message in a conversation"""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    sender_id: str
    sender_type: str = "user"  # user, agent, system
    content: str
    message_type: str = "text"  # text, file, system, action
    file_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_read: bool = False

    @validator("content")
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        if len(v) > 10000:
            raise ValueError("Message too long (max 10000 chars)")
        return sanitize_input(v.strip())


class Conversation(BaseModel):
    """A conversation thread"""
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    user_id: str
    agent_id: Optional[str] = None
    title: Optional[str] = None
    status: str = "active"  # active, closed, archived
    priority: str = "normal"  # low, normal, high, urgent
    channel: str = "webchat"  # webchat, whatsapp, email, phone, etc
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    message_count: int = 0


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation"""
    user_id: str
    title: Optional[str] = None
    channel: str = "webchat"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    """Request to send a message"""
    content: str
    message_type: str = "text"
    file_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# FastAPI Setup
# ============================================================================

app = FastAPI(
    title="Conversation Service",
    description="Real-time conversation and messaging service",
    version="1.0.0"
)

# Initialize Sentry
init_sentry(service_name="conversation", service_port=PORT)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="conversation")
app.add_middleware(TracingMiddleware)

# CORS
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
app.add_middleware(SentryTenantMiddleware)

# Event bus
event_bus = EventBus(service_name="conversation")

# Redis clients
redis_client: Optional[aioredis.Redis] = None
cache = TenantCache()
websocket_manager = None

# In-memory store (replace with database in production)
conversations: Dict[str, Conversation] = {}
messages: Dict[str, List[Message]] = {}

# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global redis_client, websocket_manager

    await event_bus.startup()

    # Initialize cache
    await cache.connect()
    logger.info("Cache client initialized")

    # Initialize Redis client
    redis_client = aioredis.from_url(config.redis.url, decode_responses=True)
    await redis_client.ping()
    logger.info("Redis client initialized")

    # Initialize WebSocket manager
    websocket_manager = get_websocket_manager()
    await websocket_manager.startup()
    logger.info("WebSocket manager initialized")

    logger.info("Conversation service started on port %s", PORT)


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    global redis_client, websocket_manager
    shutdown_tracing()

    await event_bus.shutdown()

    await cache.disconnect()
    logger.info("Cache disconnected")

    if redis_client:
        await redis_client.close()
        logger.info("Redis client closed")

    if websocket_manager:
        await websocket_manager.shutdown()
        logger.info("WebSocket manager closed")

    logger.info("Conversation service shutdown")

# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "conversation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/conversations", response_model=Dict[str, Any])
async def create_conversation(
    request: CreateConversationRequest,
    auth: AuthContext = Depends(require_role(["user", "agent"]))
):
    """Create a new conversation"""
    tenant_id = auth.tenant_id
    user_id = request.user_id

    # Validate user belongs to tenant (simplified)
    if user_id != auth.user_id and auth.role not in ["agent", "admin"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    conversation = Conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        title=request.title or f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        channel=request.channel,
        metadata=request.metadata,
    )

    conversations[conversation.conversation_id] = conversation
    messages[conversation.conversation_id] = []

    # Cache conversation
    await cache.set(
        tenant_id,
        "conversation",
        conversation.dict(),
        sub_key=conversation.conversation_id,
    )

    logger.info("Created conversation %s for tenant %s", conversation.conversation_id, tenant_id)

    # Publish event
    await event_bus.publish(EventType.CONVERSATION_CREATED, {
        "conversation_id": conversation.conversation_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
    })

    return conversation.dict()


@app.get("/api/v1/conversations/{conversation_id}", response_model=Dict[str, Any])
async def get_conversation(
    conversation_id: str,
    auth: AuthContext = Depends(require_role(["user", "agent"]))
):
    """Get conversation details"""
    tenant_id = auth.tenant_id

    # Try cache first
    cached = await cache.get(tenant_id, "conversation", sub_key=conversation_id)
    if cached:
        return cached

    # Fall back to memory
    if conversation_id in conversations:
        conv = conversations[conversation_id]
        if conv.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        return conv.dict()

    raise HTTPException(status_code=404, detail="Conversation not found")


@app.get("/api/v1/conversations/{conversation_id}/messages", response_model=Dict[str, Any])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = 50,
    offset: int = 0,
    auth: AuthContext = Depends(require_role(["user", "agent"]))
):
    """Get messages in a conversation"""
    tenant_id = auth.tenant_id

    # Verify conversation belongs to tenant
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversations[conversation_id].tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    conv_messages = messages.get(conversation_id, [])
    total = len(conv_messages)
    paginated = conv_messages[offset:offset + limit]

    return {
        "conversation_id": conversation_id,
        "messages": [m.dict() for m in paginated],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=Dict[str, Any])
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    auth: AuthContext = Depends(require_role(["user", "agent"]))
):
    """Send a message in a conversation"""
    tenant_id = auth.tenant_id
    user_id = auth.user_id

    # Verify conversation
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv = conversations[conversation_id]
    if conv.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Create message
    message = Message(
        conversation_id=conversation_id,
        sender_id=user_id,
        sender_type="agent" if auth.role == "agent" else "user",
        content=request.content,
        message_type=request.message_type,
        file_url=request.file_url,
        metadata=request.metadata,
    )

    # Store message
    if conversation_id not in messages:
        messages[conversation_id] = []
    messages[conversation_id].append(message)
    conv.message_count += 1
    conv.updated_at = datetime.now(timezone.utc)

    # Cache message in conversation context
    await cache.append_message_to_context(
        tenant_id,
        conversation_id,
        message.dict(),
    )

    logger.info("Message %s sent to conversation %s", message.message_id, conversation_id)

    # Publish event
    await event_bus.publish(EventType.MESSAGE_CREATED, {
        "message_id": message.message_id,
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "sender_id": user_id,
    })

    # Publish to WebSocket room for real-time delivery
    if websocket_manager:
        ws_message = {
            "type": "message",
            "message_id": message.message_id,
            "conversation_id": conversation_id,
            "sender_id": user_id,
            "sender_type": message.sender_type,
            "content": message.content,
            "timestamp": message.created_at.isoformat(),
        }
        await websocket_manager.send_to_room(f"conversation:{conversation_id}", ws_message)
        await websocket_manager._publish_message(f"conversation:{conversation_id}", ws_message)

    return message.dict()


@app.put("/api/v1/conversations/{conversation_id}", response_model=Dict[str, Any])
async def update_conversation(
    conversation_id: str,
    updates: Dict[str, Any],
    auth: AuthContext = Depends(require_role(["agent", "admin"]))
):
    """Update conversation (agent/admin only)"""
    tenant_id = auth.tenant_id

    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv = conversations[conversation_id]
    if conv.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Update allowed fields
    allowed_fields = {"status", "priority", "agent_id", "tags", "metadata"}
    for field in allowed_fields:
        if field in updates:
            setattr(conv, field, updates[field])

    conv.updated_at = datetime.now(timezone.utc)

    # Cache update
    await cache.set(
        tenant_id,
        "conversation",
        conv.dict(),
        sub_key=conversation_id,
    )

    logger.info("Updated conversation %s", conversation_id)

    # Publish update event
    await event_bus.publish(EventType.CONVERSATION_UPDATED, {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "updates": updates,
    })

    # Notify via WebSocket
    if websocket_manager:
        ws_message = {
            "type": "conversation_updated",
            "conversation_id": conversation_id,
            "updates": updates,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket_manager.send_to_room(f"conversation:{conversation_id}", ws_message)

    return conv.dict()


@app.delete("/api/v1/conversations/{conversation_id}")
async def close_conversation(
    conversation_id: str,
    reason: Optional[str] = None,
    auth: AuthContext = Depends(require_role(["agent", "admin"]))
):
    """Close a conversation"""
    tenant_id = auth.tenant_id

    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv = conversations[conversation_id]
    if conv.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    conv.status = "closed"
    conv.closed_at = datetime.now(timezone.utc)
    conv.updated_at = datetime.now(timezone.utc)

    # Flush conversation cache
    await cache.delete(tenant_id, "conversation", sub_key=conversation_id)

    logger.info("Closed conversation %s", conversation_id)

    # Publish event
    await event_bus.publish(EventType.CONVERSATION_CLOSED, {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "closed_by": auth.user_id,
        "reason": reason,
    })

    # Notify via WebSocket
    if websocket_manager:
        ws_message = {
            "type": "conversation_closed",
            "conversation_id": conversation_id,
            "closed_by": auth.user_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await websocket_manager.send_to_room(f"conversation:{conversation_id}", ws_message)
        # Close all connections in room
        room = f"conversation:{conversation_id}"
        connection_ids = websocket_manager.get_active_connections_for_room(room)
        for conn_id in connection_ids:
            await websocket_manager.close_connection(
                conn_id,
                code=1000,
                reason="Conversation closed"
            )

    return {"status": "closed", "conversation_id": conversation_id}


# ============================================================================
# WebSocket Endpoint (Mirror of Gateway but with persistence)
# ============================================================================

@app.websocket("/ws/live/{conversation_id}")
async def websocket_live_chat(websocket: WebSocket, conversation_id: str):
    """
    WebSocket endpoint for live chat in a conversation.
    Messages are persisted and broadcast across instances.
    """
    global websocket_manager

    if not websocket_manager:
        await websocket.close(code=status.WS_1011_SERVER_ERROR, reason="WebSocket not initialized")
        return

    # Get auth from query params or first message
    auth_token = websocket.query_params.get("token")
    if not auth_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token")
        return

    # Decode token with proper JWT signature verification
    try:
        import jwt
        from shared.core.config import settings
        claims = jwt.decode(auth_token, settings.JWT_SECRET_KEY, algorithms=["HS256", "RS256"])
        tenant_id = claims.get("tenant_id")
        user_id = claims.get("sub") or claims.get("user_id")
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    if not tenant_id or not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    # Verify conversation exists and belongs to tenant
    if conversation_id not in conversations:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Conversation not found")
        return

    if conversations[conversation_id].tenant_id != tenant_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    await websocket.accept()
    connection_id = None

    try:
        # Register with WebSocket manager
        room = f"conversation:{conversation_id}"
        connection_id = await websocket_manager.connect(
            websocket,
            tenant_id=tenant_id,
            user_id=user_id,
            rooms=[room],
        )

        # Start heartbeat
        heartbeat_task = await websocket_manager.start_heartbeat(connection_id)

        # Send welcome
        await websocket.send_json({
            "type": "connect",
            "connection_id": connection_id,
            "conversation_id": conversation_id,
            "status": "connected",
        })

        logger.info("Live chat connected: %s for conversation %s", connection_id, conversation_id)

        # Message loop
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "message").lower()

            if message_type == "message":
                # Create and persist message
                message = Message(
                    conversation_id=conversation_id,
                    sender_id=user_id,
                    sender_type="agent" if data.get("sender_type") == "agent" else "user",
                    content=data.get("content", ""),
                    message_type=data.get("message_type", "text"),
                    metadata=data.get("metadata", {}),
                )

                # Store in memory
                if conversation_id not in messages:
                    messages[conversation_id] = []
                messages[conversation_id].append(message)
                conversations[conversation_id].message_count += 1

                # Cache
                await cache.append_message_to_context(
                    tenant_id,
                    conversation_id,
                    message.dict(),
                )

                # Broadcast to room (local and cross-instance)
                ws_msg = {
                    "type": "message",
                    "message_id": message.message_id,
                    "conversation_id": conversation_id,
                    "sender_id": user_id,
                    "sender_type": message.sender_type,
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                }
                await websocket_manager.send_to_room(room, ws_msg)
                await websocket_manager._publish_message(room, ws_msg)

                # Publish event
                await event_bus.publish(EventType.MESSAGE_CREATED, {
                    "message_id": message.message_id,
                    "conversation_id": conversation_id,
                    "tenant_id": tenant_id,
                    "sender_id": user_id,
                })

            elif message_type == "typing":
                # Typing indicator - broadcast without persistence
                ws_msg = {
                    "type": "typing_start" if data.get("is_typing") else "typing_stop",
                    "conversation_id": conversation_id,
                    "sender_id": user_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await websocket_manager.send_to_room(room, ws_msg, exclude_connection_id=connection_id)

            elif message_type == "ping":
                await websocket.send_json(create_pong_message())

    except WebSocketDisconnect:
        logger.info("Live chat disconnected: %s", connection_id)
    except Exception as e:
        logger.error("WebSocket error in live chat: %s", e)
        try:
            await websocket.send_json(
                create_error_message("internal_error", "An error occurred")
            )
        except Exception:
            pass
    finally:
        if connection_id:
            await websocket_manager.disconnect(connection_id)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )
