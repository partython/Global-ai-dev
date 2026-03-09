"""
WebSocket Event Schemas and Types

Standardized message types for all real-time communication across the Priya platform.
Ensures consistency between client and server WebSocket handling.
"""

import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, validator

logger = logging.getLogger("priya.realtime.events")


class WSEventType(str, Enum):
    """All possible WebSocket event types"""
    # Connection lifecycle
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"

    # Messaging
    MESSAGE = "message"
    MESSAGE_UPDATE = "message_update"
    MESSAGE_DELETE = "message_delete"
    MESSAGE_READ = "message_read"

    # Typing indicators
    TYPING_START = "typing_start"
    TYPING_STOP = "typing_stop"

    # Presence
    PRESENCE_UPDATE = "presence_update"
    USER_ONLINE = "user_online"
    USER_OFFLINE = "user_offline"

    # Conversation events
    CONVERSATION_ASSIGNED = "conversation_assigned"
    CONVERSATION_CLOSED = "conversation_closed"
    CONVERSATION_TRANSFERRED = "conversation_transferred"
    CONVERSATION_UPDATED = "conversation_updated"

    # Agent events
    AGENT_STATUS = "agent_status"
    AGENT_AVAILABLE = "agent_available"
    AGENT_BUSY = "agent_busy"
    AGENT_OFFLINE = "agent_offline"

    # Notifications
    NOTIFICATION = "notification"
    ALERT = "alert"
    SYSTEM_ALERT = "system_alert"

    # Dashboard updates
    DASHBOARD_UPDATE = "dashboard_update"
    METRICS_UPDATE = "metrics_update"

    # Heartbeat/control
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    ACK = "ack"


class WSMessage(BaseModel):
    """Base WebSocket message structure"""
    type: WSEventType
    message_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    room: str  # conversation:{id}, tenant:{id}, agent:{id}, dashboard:{tenant_id}, broadcast
    data: Dict[str, Any] = Field(default_factory=dict)
    sender_id: Optional[str] = None
    sender_type: Optional[str] = None  # user, agent, system
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = False  # Keep enum type, not string value

    def to_json_compatible(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "type": self.type.value,
            "message_id": self.message_id,
            "room": self.room,
            "data": self.data,
            "sender_id": self.sender_id,
            "sender_type": self.sender_type,
            "timestamp": self.timestamp.isoformat(),
        }


class ChatMessage(BaseModel):
    """Incoming chat message from client"""
    type: str = "message"
    content: str
    conversation_id: str
    sender_id: str

    @validator("content")
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        if len(v) > 10000:
            raise ValueError("Message too long (max 10000 chars)")
        return v.strip()


class TypingIndicator(BaseModel):
    """Typing indicator event"""
    type: str = "typing"
    conversation_id: str
    is_typing: bool
    sender_id: str


class PresenceUpdate(BaseModel):
    """User presence update"""
    type: str = "presence"
    user_id: str
    status: str  # online, offline, idle, busy
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationAssignment(BaseModel):
    """Conversation assigned to agent"""
    type: str = "conversation_assigned"
    conversation_id: str
    agent_id: str
    agent_name: str
    queue_time_seconds: Optional[int] = None
    priority: Optional[str] = None


class ConversationClosed(BaseModel):
    """Conversation closed by agent"""
    type: str = "conversation_closed"
    conversation_id: str
    closed_by: str  # user_id or agent_id
    reason: Optional[str] = None
    duration_seconds: Optional[int] = None
    survey_link: Optional[str] = None


class NotificationEvent(BaseModel):
    """Generic notification event"""
    type: str = "notification"
    title: str
    body: str
    notification_id: str
    level: str = "info"  # info, warning, error, critical
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentStatusUpdate(BaseModel):
    """Agent status change"""
    type: str = "agent_status"
    agent_id: str
    status: str  # available, busy, offline, on_break
    active_conversations: int = 0
    queue_position: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DashboardMetrics(BaseModel):
    """Dashboard real-time metrics"""
    type: str = "metrics_update"
    tenant_id: str
    active_conversations: int
    total_agents_online: int
    avg_response_time_seconds: float
    conversations_today: int
    average_rating: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorMessage(BaseModel):
    """WebSocket error message"""
    type: str = "error"
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ACKMessage(BaseModel):
    """Acknowledgment message"""
    type: str = "ack"
    message_id: str  # ID of message being acknowledged
    status: str = "received"  # received, processed, failed
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConnectionEvent(BaseModel):
    """Connection establishment/handshake"""
    type: str = "connect"
    connection_id: str
    user_id: str
    tenant_id: str
    rooms: List[str] = Field(default_factory=list)
    auth_token: Optional[str] = None  # JWT token for auth


def parse_ws_message(data: Dict[str, Any]) -> Optional[WSMessage]:
    """
    Parse incoming WebSocket data into appropriate message type.

    Args:
        data: Raw dict from WebSocket receive_json()

    Returns:
        Parsed message or None if invalid
    """
    try:
        message_type = data.get("type", "").lower()

        if not message_type:
            logger.warning("Received message without type")
            return None

        # Map type strings to event types
        event_type_map = {
            "message": WSEventType.MESSAGE,
            "message_update": WSEventType.MESSAGE_UPDATE,
            "typing": WSEventType.TYPING_START,
            "presence": WSEventType.PRESENCE_UPDATE,
            "conversation_assigned": WSEventType.CONVERSATION_ASSIGNED,
            "conversation_closed": WSEventType.CONVERSATION_CLOSED,
            "notification": WSEventType.NOTIFICATION,
            "agent_status": WSEventType.AGENT_STATUS,
            "metrics": WSEventType.METRICS_UPDATE,
            "ping": WSEventType.PING,
            "pong": WSEventType.PONG,
            "error": WSEventType.ERROR,
            "ack": WSEventType.ACK,
        }

        event_type = event_type_map.get(message_type, WSEventType.MESSAGE)

        message = WSMessage(
            type=event_type,
            room=data.get("room", ""),
            data=data.get("data", {}),
            sender_id=data.get("sender_id"),
            sender_type=data.get("sender_type"),
        )

        return message

    except Exception as e:
        logger.error(f"Error parsing WebSocket message: {e}")
        return None


def create_error_message(
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create standardized error message"""
    error = ErrorMessage(
        error_code=error_code,
        message=message,
        details=details,
    )
    return error.dict()


def create_ack_message(message_id: str, status: str = "received") -> Dict[str, Any]:
    """Create acknowledgment message"""
    ack = ACKMessage(message_id=message_id, status=status)
    return ack.dict()


def create_ping_message() -> Dict[str, Any]:
    """Create heartbeat ping message"""
    return {
        "type": "ping",
        "timestamp": datetime.utcnow().isoformat(),
    }


def create_pong_message() -> Dict[str, Any]:
    """Create heartbeat pong response"""
    return {
        "type": "pong",
        "timestamp": datetime.utcnow().isoformat(),
    }
