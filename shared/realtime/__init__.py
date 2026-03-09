"""
Real-time Communication Package

Provides WebSocket support for real-time messaging, presence, and notifications.
- websocket_manager: Connection management with Redis pub/sub
- events: Standardized event schemas
"""

from .events import (
    WSEventType,
    WSMessage,
    ChatMessage,
    TypingIndicator,
    PresenceUpdate,
    ConversationAssignment,
    ConversationClosed,
    NotificationEvent,
    AgentStatusUpdate,
    DashboardMetrics,
    ErrorMessage,
    ACKMessage,
    ConnectionEvent,
    parse_ws_message,
    create_error_message,
    create_ack_message,
    create_ping_message,
    create_pong_message,
)
from .websocket_manager import (
    WebSocketManager,
    WSConnection,
    ConnectionStatus,
    get_websocket_manager,
)

__all__ = [
    # Event types
    "WSEventType",
    "WSMessage",
    "ChatMessage",
    "TypingIndicator",
    "PresenceUpdate",
    "ConversationAssignment",
    "ConversationClosed",
    "NotificationEvent",
    "AgentStatusUpdate",
    "DashboardMetrics",
    "ErrorMessage",
    "ACKMessage",
    "ConnectionEvent",
    "parse_ws_message",
    "create_error_message",
    "create_ack_message",
    "create_ping_message",
    "create_pong_message",
    # WebSocket manager
    "WebSocketManager",
    "WSConnection",
    "ConnectionStatus",
    "get_websocket_manager",
]
