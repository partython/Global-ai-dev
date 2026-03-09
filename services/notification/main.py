"""
Priya Global Notification Service (Port 9024)

Complete notification delivery system for the Priya Global Platform.
- Push notifications via Firebase Cloud Messaging (FCM)
- In-app real-time notifications via WebSocket
- Notification center with read/unread/archive states
- Tenant-scoped notification templates with variable substitution
- Multi-language template support
- Delivery rules: do-not-disturb schedules, channel preferences, priority-based routing
- Device token management per user
- Notification preferences and delivery scheduling
- All data is tenant-isolated with Row Level Security (RLS)

ARCHITECTURE:
- Async FastAPI service with asyncpg for database
- WebSocket connections for real-time notification delivery
- Background tasks for batch processing and FCM delivery
- Template engine with variable substitution support
- Delivery rule engine for DND schedules and channel preferences

SECURITY:
- JWT token validation on all endpoints
- Tenant isolation via RLS and connection context
- WebSocket authentication via token
- Input sanitization for all user inputs
- All configuration from environment variables
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from uuid import uuid4

import aiohttp
import asyncpg
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

# Add shared core to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import (
    mask_pii,
    sanitize_input,
    validate_access_token,
)
from shared.middleware.auth import AuthContext, get_auth
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# ─── Configure Logging ───

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("priya.notifications")

# ─── Constants ───

NOTIFICATION_TYPES = {
    "message": "New message or conversation",
    "lead_score": "Lead score change alert",
    "cart_abandoned": "Shopping cart abandoned",
    "order_status": "Order status update",
    "campaign_alert": "Campaign performance alert",
    "system_alert": "System or billing alert",
    "team_mention": "Team mention or assignment",
}

PRIORITY_LEVELS = {"low", "normal", "high", "urgent"}
CHANNELS = {"push", "in_app", "email"}

# Global WebSocket connection manager
class ConnectionManager:
    """Manages active WebSocket connections per tenant/user."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """Register a new WebSocket connection."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info("WebSocket connected for user %s", user_id)

    def disconnect(self, user_id: str, websocket: WebSocket):
        """Unregister a WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info("WebSocket disconnected for user %s", user_id)

    async def broadcast_to_user(self, user_id: str, message: dict):
        """Send message to all connections for a user."""
        if user_id in self.active_connections:
            dead_connections = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error("Error sending to WebSocket: %s", e)
                    dead_connections.append(connection)
            # Clean up dead connections
            for conn in dead_connections:
                self.disconnect(user_id, conn)

    async def broadcast_to_tenant_topic(
        self, tenant_id: str, topic: str, message: dict
    ):
        """Broadcast to all users subscribed to a topic in tenant."""
        # In a production system, you'd track topic subscriptions
        # For now, we broadcast to all active connections
        for user_id in self.active_connections:
            await self.broadcast_to_user(user_id, message)


manager = ConnectionManager()


# ─── Pydantic Models ───


class DeviceRegistration(BaseModel):
    """Device token registration for push notifications."""

    device_token: str = Field(min_length=10, max_length=512)
    device_type: str = Field(pattern="^(ios|android|web)$")
    device_name: Optional[str] = None
    app_version: Optional[str] = None
    os_version: Optional[str] = None


class SendNotificationRequest(BaseModel):
    """Request to send a single notification."""

    user_id: str = Field(min_length=1)
    notification_type: str = Field(pattern="^[a-z_]+$")
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=1000)
    data: Optional[Dict[str, str]] = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    channels: Optional[List[str]] = Field(default=["in_app", "push"])
    scheduled_for: Optional[datetime] = None
    ttl_seconds: Optional[int] = Field(default=86400, le=2592000)  # Max 30 days

    @validator("notification_type")
    def validate_type(cls, v):
        if v not in NOTIFICATION_TYPES:
            raise ValueError(f"Invalid notification type: {v}")
        return v

    @validator("channels")
    def validate_channels(cls, v):
        if not v:
            return ["in_app", "push"]
        for channel in v:
            if channel not in CHANNELS:
                raise ValueError(f"Invalid channel: {channel}")
        return v


class BroadcastNotificationRequest(BaseModel):
    """Request to broadcast to tenant or topic."""

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=1000)
    data: Optional[Dict[str, str]] = None
    target_type: str = Field(pattern="^(tenant|topic|role)$")
    target_value: str = Field(min_length=1, max_length=200)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    channels: Optional[List[str]] = Field(default=["in_app"])


class NotificationTemplateRequest(BaseModel):
    """Create or update notification template."""

    name: str = Field(min_length=1, max_length=100)
    notification_type: str
    title_template: str = Field(min_length=1, max_length=200)
    body_template: str = Field(min_length=1, max_length=1000)
    data_template: Optional[Dict[str, str]] = None
    language: str = Field(default="en", pattern="^[a-z]{2}$")
    variables: List[str] = Field(default=[])
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    channels: List[str] = Field(default=["in_app", "push"])

    @validator("notification_type")
    def validate_type(cls, v):
        if v not in NOTIFICATION_TYPES:
            raise ValueError(f"Invalid notification type: {v}")
        return v


class NotificationPreferencesRequest(BaseModel):
    """Update notification preferences for user."""

    do_not_disturb_start: Optional[str] = Field(
        None, pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"
    )  # HH:MM
    do_not_disturb_end: Optional[str] = Field(None, pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")
    do_not_disturb_enabled: bool = False
    preferred_channels: List[str] = Field(default=["in_app", "push"])
    mute_all: bool = False
    notification_sounds: bool = True
    notification_badges: bool = True
    marketing_emails: bool = True
    system_alerts: bool = True
    per_type_preferences: Optional[Dict[str, bool]] = None


class NotificationResponse(BaseModel):
    """Notification in notification center."""

    id: str
    tenant_id: str
    user_id: str
    notification_type: str
    title: str
    body: str
    data: Optional[Dict[str, str]] = None
    priority: str
    is_read: bool
    is_archived: bool
    created_at: str
    read_at: Optional[str] = None
    archived_at: Optional[str] = None


class TemplateResponse(BaseModel):
    """Notification template response."""

    id: str
    name: str
    notification_type: str
    title_template: str
    body_template: str
    language: str
    priority: str
    channels: List[str]
    created_at: str
    updated_at: str


class PreferencesResponse(BaseModel):
    """User notification preferences."""

    user_id: str
    do_not_disturb_start: Optional[str] = None
    do_not_disturb_end: Optional[str] = None
    do_not_disturb_enabled: bool
    preferred_channels: List[str]
    mute_all: bool
    notification_sounds: bool
    notification_badges: bool
    marketing_emails: bool
    system_alerts: bool
    per_type_preferences: Dict[str, bool]
    updated_at: str


# ─── Initialize FastAPI App ───

app = FastAPI(
    title="Priya Global Notification Service",
    description="Unified notification delivery system",
    version="1.0.0",
)
# Initialize Sentry error tracking
init_sentry(service_name="notification", service_port=9024)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="notification")
app.add_middleware(TracingMiddleware)


# CORS Configuration
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



# Initialize event bus
event_bus = EventBus(service_name="notification")

# ─── Lifecycle Events ───


@app.on_event("startup")
async def startup_event():
    """Initialize database and HTTP client."""
    await db.initialize()

    await event_bus.startup()
    logger.info("Notification Service started on port 9024")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup."""
    await db.close()
    shutdown_tracing()

    await event_bus.shutdown()
    logger.info("Notification Service shut down")


# ─── Health Check ───


@app.get("/api/v1/notifications/health", tags=["Health"])
async def health_check():
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "service": "notifications",
        "version": "1.0.0",
        "timestamp": utc_now().isoformat(),
    }


# ─── Helper Functions ───


def substitute_template_variables(template: str, variables: Dict[str, str]) -> str:
    """Substitute {{var}} placeholders with actual values."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


async def should_deliver(
    user_id: str, tenant_id: str, priority: str
) -> bool:
    """Check if notification should be delivered based on DND and preferences."""
    async with db.tenant_connection(tenant_id) as conn:
        prefs = await conn.fetchrow(
            """
            SELECT do_not_disturb_enabled, do_not_disturb_start, do_not_disturb_end, mute_all
            FROM notification_preferences
            WHERE user_id = $1
            """,
            user_id,
        )

        if not prefs or not prefs["do_not_disturb_enabled"]:
            return True

        # Urgent priority bypasses DND
        if priority == "urgent":
            return True

        # Check if current time is within DND window
        now = utc_now().time()
        start_str = prefs.get("do_not_disturb_start")
        end_str = prefs.get("do_not_disturb_end")

        if start_str and end_str:
            start = datetime.strptime(start_str, "%H:%M").time()
            end = datetime.strptime(end_str, "%H:%M").time()

            if start <= now <= end:
                return False

        return True


async def send_fcm_notification(
    device_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
    priority: str = "high",
) -> bool:
    """Send notification via Firebase Cloud Messaging."""
    fcm_key = os.getenv("FCM_SERVER_KEY")
    if not fcm_key:
        logger.warning("FCM_SERVER_KEY not configured")
        return False

    payload = {
        "notification": {"title": title, "body": body},
        "data": data or {},
        "android": {"priority": priority},
        "webpush": {
            "headers": {"TTL": "86400"},
            "data": data or {},
        },
        "apns": {
            "payload": {
                "aps": {
                    "alert": {"title": title, "body": body},
                    "sound": "default",
                    "badge": 1,
                }
            }
        },
        "token": device_token,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://fcm.googleapis.com/v1/projects/{}/messages:send".format(
                    os.getenv("FCM_PROJECT_ID", "")
                ),
                json={"message": payload},
                headers={"Authorization": f"Bearer {fcm_key}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    logger.info("FCM notification sent to %s", sanitize_input(device_token))
                    return True
                else:
                    logger.error("FCM error: %s", resp.status)
                    return False
    except Exception as e:
        logger.error("FCM delivery failed: %s", e)
        return False


async def deliver_notification(
    notification_id: str,
    user_id: str,
    tenant_id: str,
    title: str,
    body: str,
    channels: List[str],
    data: Optional[Dict[str, str]] = None,
    priority: str = "normal",
):
    """Deliver notification through configured channels."""
    # In-app delivery via WebSocket
    if "in_app" in channels:
        message = {
            "type": "notification",
            "id": notification_id,
            "title": title,
            "body": body,
            "data": data,
            "priority": priority,
            "timestamp": utc_now().isoformat(),
        }
        await manager.broadcast_to_user(user_id, message)

    # Push delivery via FCM
    if "push" in channels:
        async with db.tenant_connection(tenant_id) as conn:
            devices = await conn.fetch(
                """
                SELECT device_token FROM device_tokens
                WHERE user_id = $1 AND is_active = true
                """,
                user_id,
            )

        for device in devices:
            # Background task for FCM delivery
            await send_fcm_notification(
                device["device_token"],
                title,
                body,
                data,
                "high" if priority in ["high", "urgent"] else "normal",
            )


# ─── Send Notification Endpoint ───


@app.post("/api/v1/notifications/send", tags=["Notifications"])
async def send_notification(
    req: SendNotificationRequest,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Send a notification to a specific user."""
    # Verify user can send to this recipient (same tenant)
    async with db.tenant_connection(auth.tenant_id) as conn:
        recipient = await conn.fetchrow(
            "SELECT id FROM users WHERE id = $1", req.user_id
        )
        if not recipient:
            raise HTTPException(status_code=404, detail="User not found")

    notification_id = generate_uuid()
    now = utc_now()

    async with db.tenant_connection(auth.tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO notifications
            (id, tenant_id, user_id, notification_type, title, body, data,
             priority, is_read, is_archived, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            notification_id,
            auth.tenant_id,
            req.user_id,
            req.notification_type,
            sanitize_input(req.title),
            sanitize_input(req.body),
            json.dumps(req.data) if req.data else None,
            req.priority,
            False,
            False,
            now,
        )

        # Check delivery rules
        should_send = await should_deliver(
            req.user_id, auth.tenant_id, req.priority
        )

    if should_send:
        background_tasks.add_task(
            deliver_notification,
            notification_id,
            req.user_id,
            auth.tenant_id,
            req.title,
            req.body,
            req.channels or ["in_app", "push"],
            req.data,
            req.priority,
        )

    logger.info(
        f"Notification {notification_id} queued for user {mask_pii(req.user_id)}"
    )

    return {
        "id": notification_id,
        "status": "queued",
        "delivered": should_send,
        "channels": req.channels,
    }


# ─── Broadcast Notification Endpoint ───


@app.post("/api/v1/notifications/broadcast", tags=["Notifications"])
async def broadcast_notification(
    req: BroadcastNotificationRequest,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """Broadcast notification to tenant/topic/role."""
    auth.require_role("owner", "admin")

    async with db.tenant_connection(auth.tenant_id) as conn:
        target_users = []

        if req.target_type == "tenant":
            # Broadcast to all users in tenant
            users = await conn.fetch(
                "SELECT id FROM users WHERE tenant_id = $1 AND status = 'active'",
                auth.tenant_id,
            )
            target_users = [u["id"] for u in users]

        elif req.target_type == "topic":
            # Broadcast to users subscribed to topic
            users = await conn.fetch(
                """
                SELECT DISTINCT user_id FROM notification_topic_subscriptions
                WHERE tenant_id = $1 AND topic = $2
                """,
                auth.tenant_id,
                req.target_value,
            )
            target_users = [u["user_id"] for u in users]

        elif req.target_type == "role":
            # Broadcast to users with specific role
            users = await conn.fetch(
                "SELECT id FROM users WHERE tenant_id = $1 AND role = $2 AND status = 'active'",
                auth.tenant_id,
                req.target_value,
            )
            target_users = [u["id"] for u in users]

    broadcast_id = generate_uuid()
    logger.info("Broadcasting to %s users", len(target_users))

    # Send to each user
    for user_id in target_users:
        background_tasks.add_task(
            deliver_notification,
            generate_uuid(),
            user_id,
            auth.tenant_id,
            req.title,
            req.body,
            req.channels,
            req.data,
            req.priority,
        )

    return {
        "broadcast_id": broadcast_id,
        "target_count": len(target_users),
        "status": "queued",
    }


# ─── Get Notifications Endpoint ───


@app.get("/api/v1/notifications", response_model=List[NotificationResponse], tags=["Notifications"])
async def get_notifications(
    auth: AuthContext = Depends(get_auth),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = False,
    archived_only: bool = False,
):
    """Get notifications for current user."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        query = """
            SELECT id, tenant_id, user_id, notification_type, title, body, data,
                   priority, is_read, is_archived, created_at, read_at, archived_at
            FROM notifications
            WHERE user_id = $1
        """
        params = [auth.user_id]

        if unread_only:
            query += " AND is_read = false AND is_archived = false"
        elif archived_only:
            query += " AND is_archived = true"
        else:
            query += " AND is_archived = false"

        query += " ORDER BY created_at DESC LIMIT $2 OFFSET $3"
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

    notifications = [
        NotificationResponse(
            id=r["id"],
            tenant_id=r["tenant_id"],
            user_id=r["user_id"],
            notification_type=r["notification_type"],
            title=r["title"],
            body=r["body"],
            data=json.loads(r["data"]) if r["data"] else None,
            priority=r["priority"],
            is_read=r["is_read"],
            is_archived=r["is_archived"],
            created_at=r["created_at"].isoformat() if r["created_at"] else None,
            read_at=r["read_at"].isoformat() if r["read_at"] else None,
            archived_at=r["archived_at"].isoformat() if r["archived_at"] else None,
        )
        for r in rows
    ]

    return notifications


# ─── Mark as Read Endpoint ───


@app.put("/api/v1/notifications/{notification_id}/read", tags=["Notifications"])
async def mark_as_read(
    notification_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Mark notification as read."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        # Verify ownership
        notif = await conn.fetchrow(
            "SELECT id FROM notifications WHERE id = $1 AND user_id = $2",
            notification_id,
            auth.user_id,
        )
        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found")

        await conn.execute(
            """
            UPDATE notifications
            SET is_read = true, read_at = $3
            WHERE id = $1 AND tenant_id = $2
            """,
            notification_id,
            auth.tenant_id,
            utc_now(),
        )

    return {"status": "read", "id": notification_id}


# ─── Mark All as Read Endpoint ───


@app.put("/api/v1/notifications/read-all", tags=["Notifications"])
async def mark_all_as_read(auth: AuthContext = Depends(get_auth)):
    """Mark all unread notifications as read."""
    now = utc_now()

    async with db.tenant_connection(auth.tenant_id) as conn:
        result = await conn.execute(
            """
            UPDATE notifications
            SET is_read = true, read_at = $3
            WHERE user_id = $1 AND tenant_id = $2 AND is_read = false AND is_archived = false
            """,
            auth.user_id,
            auth.tenant_id,
            now,
        )

    count = int(result.split()[-1]) if result else 0
    return {"status": "updated", "count": count}


# ─── Archive Notification Endpoint ───


@app.delete("/api/v1/notifications/{notification_id}", tags=["Notifications"])
async def archive_notification(
    notification_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Archive (soft delete) a notification."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        # Verify ownership
        notif = await conn.fetchrow(
            "SELECT id FROM notifications WHERE id = $1 AND user_id = $2",
            notification_id,
            auth.user_id,
        )
        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found")

        await conn.execute(
            """
            UPDATE notifications
            SET is_archived = true, archived_at = $3
            WHERE id = $1 AND tenant_id = $2
            """,
            notification_id,
            auth.tenant_id,
            utc_now(),
        )

    return {"status": "archived", "id": notification_id}


# ─── Register Device Token Endpoint ───


@app.post("/api/v1/notifications/devices/register", tags=["Devices"])
async def register_device(
    req: DeviceRegistration,
    auth: AuthContext = Depends(get_auth),
):
    """Register device token for push notifications."""
    device_id = generate_uuid()
    now = utc_now()

    async with db.tenant_connection(auth.tenant_id) as conn:
        # Check if token already exists
        existing = await conn.fetchrow(
            "SELECT id FROM device_tokens WHERE user_id = $1 AND device_token = $2",
            auth.user_id,
            sanitize_input(req.device_token),
        )

        if existing:
            # Update last seen
            await conn.execute(
                "UPDATE device_tokens SET updated_at = $3 WHERE id = $1 AND tenant_id = $2",
                existing["id"],
                auth.tenant_id,
                now,
            )
            device_id = existing["id"]
        else:
            # Insert new device
            await conn.execute(
                """
                INSERT INTO device_tokens
                (id, tenant_id, user_id, device_token, device_type, device_name,
                 app_version, os_version, is_active, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                device_id,
                auth.tenant_id,
                auth.user_id,
                sanitize_input(req.device_token),
                req.device_type,
                sanitize_input(req.device_name) if req.device_name else None,
                req.app_version,
                req.os_version,
                True,
                now,
                now,
            )

    logger.info(
        f"Device registered for user {mask_pii(auth.user_id)} - {req.device_type}"
    )

    return {
        "device_id": device_id,
        "status": "registered",
        "device_type": req.device_type,
    }


# ─── Unregister Device Token Endpoint ───


@app.delete("/api/v1/notifications/devices/{device_token}", tags=["Devices"])
async def unregister_device(
    device_token: str,
    auth: AuthContext = Depends(get_auth),
):
    """Unregister device token."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        # Verify ownership
        device = await conn.fetchrow(
            "SELECT id FROM device_tokens WHERE user_id = $1 AND device_token = $2",
            auth.user_id,
            sanitize_input(device_token),
        )
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        await conn.execute(
            "UPDATE device_tokens SET is_active = false WHERE id = $1 AND tenant_id = $2",
            device["id"],
            auth.tenant_id,
        )

    return {"status": "unregistered", "device_token": device_token}


# ─── Get Preferences Endpoint ───


@app.get(
    "/api/v1/notifications/preferences",
    response_model=PreferencesResponse,
    tags=["Preferences"],
)
async def get_preferences(auth: AuthContext = Depends(get_auth)):
    """Get notification preferences for current user."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        prefs = await conn.fetchrow(
            """
            SELECT user_id, do_not_disturb_start, do_not_disturb_end,
                   do_not_disturb_enabled, preferred_channels, mute_all,
                   notification_sounds, notification_badges, marketing_emails,
                   system_alerts, per_type_preferences, updated_at
            FROM notification_preferences
            WHERE user_id = $1
            """,
            auth.user_id,
        )

    if not prefs:
        # Return defaults
        now = utc_now()
        return PreferencesResponse(
            user_id=auth.user_id,
            do_not_disturb_enabled=False,
            preferred_channels=["in_app", "push"],
            mute_all=False,
            notification_sounds=True,
            notification_badges=True,
            marketing_emails=True,
            system_alerts=True,
            per_type_preferences={},
            updated_at=now.isoformat(),
        )

    return PreferencesResponse(
        user_id=prefs["user_id"],
        do_not_disturb_start=prefs["do_not_disturb_start"],
        do_not_disturb_end=prefs["do_not_disturb_end"],
        do_not_disturb_enabled=prefs["do_not_disturb_enabled"],
        preferred_channels=prefs["preferred_channels"] or ["in_app", "push"],
        mute_all=prefs["mute_all"],
        notification_sounds=prefs["notification_sounds"],
        notification_badges=prefs["notification_badges"],
        marketing_emails=prefs["marketing_emails"],
        system_alerts=prefs["system_alerts"],
        per_type_preferences=prefs["per_type_preferences"] or {},
        updated_at=prefs["updated_at"].isoformat() if prefs["updated_at"] else None,
    )


# ─── Update Preferences Endpoint ───


@app.put(
    "/api/v1/notifications/preferences",
    response_model=PreferencesResponse,
    tags=["Preferences"],
)
async def update_preferences(
    req: NotificationPreferencesRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Update notification preferences."""
    now = utc_now()

    async with db.tenant_connection(auth.tenant_id) as conn:
        # Check if preferences exist
        existing = await conn.fetchrow(
            "SELECT id FROM notification_preferences WHERE user_id = $1",
            auth.user_id,
        )

        if existing:
            await conn.execute(
                """
                UPDATE notification_preferences
                SET do_not_disturb_start = $2,
                    do_not_disturb_end = $3,
                    do_not_disturb_enabled = $4,
                    preferred_channels = $5,
                    mute_all = $6,
                    notification_sounds = $7,
                    notification_badges = $8,
                    marketing_emails = $9,
                    system_alerts = $10,
                    per_type_preferences = $11,
                    updated_at = $12
                WHERE user_id = $1
                """,
                auth.user_id,
                req.do_not_disturb_start,
                req.do_not_disturb_end,
                req.do_not_disturb_enabled,
                req.preferred_channels,
                req.mute_all,
                req.notification_sounds,
                req.notification_badges,
                req.marketing_emails,
                req.system_alerts,
                json.dumps(req.per_type_preferences or {}),
                now,
            )
        else:
            await conn.execute(
                """
                INSERT INTO notification_preferences
                (id, tenant_id, user_id, do_not_disturb_start, do_not_disturb_end,
                 do_not_disturb_enabled, preferred_channels, mute_all,
                 notification_sounds, notification_badges, marketing_emails,
                 system_alerts, per_type_preferences, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                """,
                generate_uuid(),
                auth.tenant_id,
                auth.user_id,
                req.do_not_disturb_start,
                req.do_not_disturb_end,
                req.do_not_disturb_enabled,
                req.preferred_channels,
                req.mute_all,
                req.notification_sounds,
                req.notification_badges,
                req.marketing_emails,
                req.system_alerts,
                json.dumps(req.per_type_preferences or {}),
                now,
                now,
            )

    logger.info("Preferences updated for user %s", mask_pii(auth.user_id))

    return PreferencesResponse(
        user_id=auth.user_id,
        do_not_disturb_start=req.do_not_disturb_start,
        do_not_disturb_end=req.do_not_disturb_end,
        do_not_disturb_enabled=req.do_not_disturb_enabled,
        preferred_channels=req.preferred_channels,
        mute_all=req.mute_all,
        notification_sounds=req.notification_sounds,
        notification_badges=req.notification_badges,
        marketing_emails=req.marketing_emails,
        system_alerts=req.system_alerts,
        per_type_preferences=req.per_type_preferences or {},
        updated_at=now.isoformat(),
    )


# ─── Create Notification Template Endpoint ───


@app.post(
    "/api/v1/notifications/templates",
    response_model=TemplateResponse,
    tags=["Templates"],
)
async def create_template(
    req: NotificationTemplateRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Create a notification template for tenant."""
    auth.require_role("owner", "admin")

    template_id = generate_uuid()
    now = utc_now()

    async with db.tenant_connection(auth.tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO notification_templates
            (id, tenant_id, name, notification_type, title_template, body_template,
             data_template, language, variables, priority, channels, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            template_id,
            auth.tenant_id,
            sanitize_input(req.name),
            req.notification_type,
            sanitize_input(req.title_template),
            sanitize_input(req.body_template),
            json.dumps(req.data_template) if req.data_template else None,
            req.language,
            json.dumps(req.variables),
            req.priority,
            req.channels,
            now,
            now,
        )

    logger.info("Template %s created by %s", sanitize_input(req.name), mask_pii(auth.user_id))

    return TemplateResponse(
        id=template_id,
        name=req.name,
        notification_type=req.notification_type,
        title_template=req.title_template,
        body_template=req.body_template,
        language=req.language,
        priority=req.priority,
        channels=req.channels,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )


# ─── List Templates Endpoint ───


@app.get(
    "/api/v1/notifications/templates",
    response_model=List[TemplateResponse],
    tags=["Templates"],
)
async def list_templates(
    auth: AuthContext = Depends(get_auth),
    notification_type: Optional[str] = None,
    language: str = "en",
):
    """List notification templates for tenant."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        query = """
            SELECT id, name, notification_type, title_template, body_template,
                   language, priority, channels, created_at, updated_at
            FROM notification_templates
            WHERE language = $1
        """
        params = [language]

        if notification_type:
            query += " AND notification_type = $2"
            params.append(notification_type)

        query += " ORDER BY created_at DESC"

        rows = await conn.fetch(query, *params)

    templates = [
        TemplateResponse(
            id=r["id"],
            name=r["name"],
            notification_type=r["notification_type"],
            title_template=r["title_template"],
            body_template=r["body_template"],
            language=r["language"],
            priority=r["priority"],
            channels=r["channels"],
            created_at=r["created_at"].isoformat() if r["created_at"] else None,
            updated_at=r["updated_at"].isoformat() if r["updated_at"] else None,
        )
        for r in rows
    ]

    return templates


# ─── WebSocket Endpoint for Real-Time Notifications ───


@app.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """Real-time WebSocket connection for notifications."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Validate token
    claims = validate_access_token(token)
    if not claims:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")

    await manager.connect(user_id, websocket)

    try:
        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_text()
            # Could handle client-side commands here
            # For now, just keep the connection alive
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(user_id, websocket)
        logger.info("WebSocket disconnected for user %s", user_id)


# ─── Main Entry Point ───


if __name__ == "__main__":
    import uvicorn



    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9024,
        workers=4,
        reload=os.getenv("ENV") == "development",
    )
