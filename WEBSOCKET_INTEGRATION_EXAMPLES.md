# WebSocket Integration Examples

Real-world code examples for integrating WebSocket functionality.

## 1. Frontend Integration

### JavaScript/TypeScript Client

```typescript
// websocket-client.ts
import { EventEmitter } from 'events';

interface WSMessage {
  type: string;
  [key: string]: any;
}

export class ConversationWebSocket extends EventEmitter {
  private ws: WebSocket | null = null;
  private url: string;
  private token: string;
  private conversationId: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;

  constructor(url: string, token: string, conversationId: string) {
    super();
    this.url = url;
    this.token = token;
    this.conversationId = conversationId;
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(
          `${this.url}/ws/conversations/${this.conversationId}`,
          [],
        );

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          this.emit('connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message: WSMessage = JSON.parse(event.data);
            this.handleMessage(message);
          } catch (e) {
            console.error('Failed to parse message:', e);
          }
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.emit('error', error);
          reject(error);
        };

        this.ws.onclose = () => {
          console.log('WebSocket closed');
          this.emit('disconnected');
          this.attemptReconnect();
        };

        // Send auth token
        setTimeout(() => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws?.send(JSON.stringify({
              type: 'auth',
              token: this.token,
            }));
          }
        }, 100);

      } catch (error) {
        reject(error);
      }
    });
  }

  sendMessage(content: string): void {
    if (!this.isConnected()) {
      console.error('WebSocket not connected');
      return;
    }

    this.ws?.send(JSON.stringify({
      type: 'message',
      content,
      conversation_id: this.conversationId,
    }));
  }

  sendTypingIndicator(isTyping: boolean): void {
    if (!this.isConnected()) return;

    this.ws?.send(JSON.stringify({
      type: 'typing',
      is_typing: isTyping,
      conversation_id: this.conversationId,
    }));
  }

  private handleMessage(message: WSMessage): void {
    switch (message.type) {
      case 'connect':
        this.emit('message', { type: 'system', body: 'Connected to conversation' });
        break;

      case 'message':
        this.emit('message', {
          id: message.message_id,
          sender: message.sender_id,
          content: message.content,
          timestamp: new Date(message.timestamp),
        });
        break;

      case 'typing_start':
        this.emit('typing', { userId: message.sender_id, isTyping: true });
        break;

      case 'typing_stop':
        this.emit('typing', { userId: message.sender_id, isTyping: false });
        break;

      case 'error':
        this.emit('error', { code: message.error_code, message: message.message });
        break;

      case 'ping':
        this.sendPong();
        break;

      default:
        this.emit('message', message);
    }
  }

  private sendPong(): void {
    this.ws?.send(JSON.stringify({ type: 'pong' }));
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.emit('error', { message: 'Max reconnection attempts reached' });
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    setTimeout(() => {
      this.connect().catch((e) => {
        console.error('Reconnection failed:', e);
      });
    }, delay);
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  disconnect(): void {
    this.ws?.close(1000, 'Normal closure');
    this.ws = null;
  }
}
```

### React Component

```tsx
// ConversationChat.tsx
import React, { useEffect, useState, useRef } from 'react';
import { ConversationWebSocket } from './websocket-client';

interface Message {
  id: string;
  sender: string;
  content: string;
  timestamp: Date;
  type?: 'user' | 'agent' | 'system';
}

export const ConversationChat: React.FC<{
  conversationId: string;
  token: string;
}> = ({ conversationId, token }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [connected, setConnected] = useState(false);
  const [otherTyping, setOtherTyping] = useState<string | null>(null);

  const wsRef = useRef<ConversationWebSocket | null>(null);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const ws = new ConversationWebSocket(
      process.env.REACT_APP_WS_URL || 'ws://localhost:9001',
      token,
      conversationId,
    );

    wsRef.current = ws;

    ws.on('connected', () => setConnected(true));
    ws.on('disconnected', () => setConnected(false));

    ws.on('message', (msg: Message) => {
      setMessages((prev) => [...prev, msg]);
    });

    ws.on('typing', ({ userId, isTyping }: any) => {
      if (isTyping) {
        setOtherTyping(userId);
      } else {
        setOtherTyping(null);
      }
    });

    ws.on('error', (error: any) => {
      console.error('WebSocket error:', error);
      // Show error toast
    });

    ws.connect().catch((e) => {
      console.error('Failed to connect:', e);
    });

    return () => {
      ws.disconnect();
    };
  }, [conversationId, token]);

  const handleSendMessage = () => {
    if (inputValue.trim()) {
      wsRef.current?.sendMessage(inputValue);
      setInputValue('');
      setIsTyping(false);
    }
  };

  const handleInputChange = (value: string) => {
    setInputValue(value);

    // Send typing indicator
    if (!isTyping && value.length > 0) {
      setIsTyping(true);
      wsRef.current?.sendTypingIndicator(true);
    }

    // Clear typing indicator after 3 seconds of inactivity
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }

    typingTimeoutRef.current = setTimeout(() => {
      setIsTyping(false);
      wsRef.current?.sendTypingIndicator(false);
    }, 3000);
  };

  return (
    <div className="conversation-chat">
      <div className="chat-header">
        <h2>Conversation</h2>
        <span className={`status ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? '● Connected' : '○ Disconnected'}
        </span>
      </div>

      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.type}`}>
            <div className="message-sender">{msg.sender}</div>
            <div className="message-content">{msg.content}</div>
            <div className="message-time">
              {msg.timestamp.toLocaleTimeString()}
            </div>
          </div>
        ))}
        {otherTyping && (
          <div className="message typing">
            <div className="message-sender">{otherTyping}</div>
            <div className="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        )}
      </div>

      <div className="chat-input">
        <input
          type="text"
          value={inputValue}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
          placeholder="Type a message..."
          disabled={!connected}
        />
        <button
          onClick={handleSendMessage}
          disabled={!connected || !inputValue.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
};
```

## 2. Backend Integration

### Python Service Integration

```python
# services/notification/main.py
from shared.realtime.websocket_manager import get_websocket_manager
from shared.events.event_bus import EventBus, EventType

class NotificationService:
    def __init__(self):
        self.ws_manager = get_websocket_manager()
        self.event_bus = EventBus(service_name="notification")

    async def notify_conversation_assignment(
        self,
        conversation_id: str,
        agent_id: str,
        tenant_id: str,
    ):
        """Notify users in conversation about assignment"""
        message = {
            "type": "conversation_assigned",
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Send to conversation room
        await self.ws_manager.send_to_room(
            f"conversation:{conversation_id}",
            message
        )

        # Publish for cross-instance delivery
        await self.ws_manager._publish_message(
            f"conversation:{conversation_id}",
            message
        )

        # Also publish event
        await self.event_bus.publish(EventType.CONVERSATION_ASSIGNED, {
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "tenant_id": tenant_id,
        })

    async def send_notification_to_user(
        self,
        tenant_id: str,
        user_id: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
    ):
        """Send notification to specific user"""
        message = {
            "type": "notification",
            "title": title,
            "body": body,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Send to all user's connections
        await self.ws_manager.send_to_user(
            tenant_id,
            user_id,
            message
        )

    async def broadcast_to_tenant(
        self,
        tenant_id: str,
        message_type: str,
        data: Dict,
    ):
        """Broadcast message to all users in tenant"""
        message = {
            "type": message_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.ws_manager.send_to_room(
            f"tenant:{tenant_id}",
            message
        )

        # Publish for cross-instance
        await self.ws_manager._publish_message(
            f"tenant:{tenant_id}",
            message
        )
```

### Dashboard Metrics Service

```python
# services/analytics/realtime_metrics.py
import asyncio
from shared.realtime.websocket_manager import get_websocket_manager

class RealtimeMetricsService:
    def __init__(self, update_interval: int = 5):
        self.ws_manager = get_websocket_manager()
        self.update_interval = update_interval
        self.running = False

    async def start(self):
        """Start publishing metrics"""
        self.running = True
        asyncio.create_task(self._metrics_loop())
        logger.info("Realtime metrics service started")

    async def stop(self):
        """Stop publishing metrics"""
        self.running = False
        logger.info("Realtime metrics service stopped")

    async def _metrics_loop(self):
        """Periodically publish metrics to dashboards"""
        while self.running:
            try:
                # Get active tenants
                tenants = await self._get_active_tenants()

                for tenant_id in tenants:
                    # Calculate metrics
                    metrics = await self._calculate_metrics(tenant_id)

                    # Send to dashboard room
                    message = {
                        "type": "metrics_update",
                        "tenant_id": tenant_id,
                        **metrics,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                    await self.ws_manager.send_to_room(
                        f"dashboard:{tenant_id}",
                        message
                    )

                    # Publish for cross-instance
                    await self.ws_manager._publish_message(
                        f"dashboard:{tenant_id}",
                        message
                    )

                await asyncio.sleep(self.update_interval)

            except Exception as e:
                logger.error(f"Metrics loop error: {e}")
                await asyncio.sleep(self.update_interval)

    async def _calculate_metrics(self, tenant_id: str) -> Dict:
        """Calculate current metrics for tenant"""
        # Query from database/cache
        return {
            "active_conversations": await self._count_active_conversations(tenant_id),
            "total_agents_online": await self._count_agents_online(tenant_id),
            "avg_response_time_seconds": await self._avg_response_time(tenant_id),
            "conversations_today": await self._count_today(tenant_id),
            "average_rating": await self._avg_rating(tenant_id),
        }

    async def _get_active_tenants(self) -> List[str]:
        # Implementation
        pass

    async def _count_active_conversations(self, tenant_id: str) -> int:
        # Implementation
        pass

    # ... other helper methods
```

### Event Bus Integration

```python
# In any service that receives events
from shared.events.event_bus import EventBus, EventType
from shared.realtime.websocket_manager import get_websocket_manager

async def on_message_created(event_data: Dict):
    """Handle message created event"""
    ws_manager = get_websocket_manager()

    message_id = event_data["message_id"]
    conversation_id = event_data["conversation_id"]
    sender_id = event_data["sender_id"]

    # Broadcast to conversation room
    await ws_manager.send_to_room(
        f"conversation:{conversation_id}",
        {
            "type": "message",
            "message_id": message_id,
            "sender_id": sender_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

# Register handler
event_bus = EventBus(service_name="my_service")
event_bus.subscribe(EventType.MESSAGE_CREATED, on_message_created)
```

## 3. Testing Examples

### Unit Test

```python
# tests/test_websocket_manager.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from shared.realtime.websocket_manager import WebSocketManager

@pytest.mark.asyncio
async def test_connection_lifecycle():
    """Test connect and disconnect"""
    manager = WebSocketManager()
    await manager.startup()

    # Create mock WebSocket
    mock_ws = AsyncMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.close = AsyncMock()

    # Connect
    conn_id = await manager.connect(
        mock_ws,
        tenant_id="tenant1",
        user_id="user1",
        rooms=["room1"]
    )

    assert conn_id in manager.connections
    assert manager.connections[conn_id].user_id == "user1"
    assert "room1" in manager.connections[conn_id].rooms

    # Disconnect
    await manager.disconnect(conn_id)

    assert conn_id not in manager.connections

    await manager.shutdown()

@pytest.mark.asyncio
async def test_send_to_room():
    """Test broadcasting to room"""
    manager = WebSocketManager()
    await manager.startup()

    # Create two connections in same room
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()

    conn1 = await manager.connect(mock_ws1, "tenant1", "user1", ["room1"])
    conn2 = await manager.connect(mock_ws2, "tenant1", "user2", ["room1"])

    # Send message
    message = {"type": "message", "content": "Hello"}
    count = await manager.send_to_room("room1", message)

    assert count == 2
    assert mock_ws1.send_json.call_count == 1
    assert mock_ws2.send_json.call_count == 1

    await manager.shutdown()

@pytest.mark.asyncio
async def test_tenant_isolation():
    """Test that connections don't cross tenants"""
    manager = WebSocketManager()
    await manager.startup()

    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()

    # Connect to same room but different tenants
    conn1 = await manager.connect(mock_ws1, "tenant1", "user1", ["room1"])
    conn2 = await manager.connect(mock_ws2, "tenant2", "user2", ["room1"])

    # Send to room - both should receive
    await manager.send_to_room("room1", {"type": "message"})

    # But if we send to tenant, only that tenant gets it
    await manager.send_to_tenant("tenant1", {"type": "notification"})
    assert mock_ws1.send_json.call_count == 2  # message + notification
    assert mock_ws2.send_json.call_count == 1  # only message

    await manager.shutdown()
```

### Integration Test

```python
# tests/test_websocket_endpoint.py
import asyncio
from fastapi.testclient import TestClient
from websockets.client import connect

@pytest.mark.asyncio
async def test_websocket_chat():
    """Test WebSocket chat endpoint"""
    token = create_test_jwt("tenant1", "user1")

    # Connect client 1
    async with connect(
        f"ws://localhost:9001/ws/conversations/conv1?token={token}"
    ) as ws1:
        # Receive connection message
        conn_msg = await ws1.recv()
        assert json.loads(conn_msg)["type"] == "connect"

        # Create second connection
        async with connect(
            f"ws://localhost:9001/ws/conversations/conv1?token={token}"
        ) as ws2:
            # Send message from ws1
            await ws1.send(json.dumps({
                "type": "message",
                "content": "Hello from user 1"
            }))

            # Both should receive it
            msg1 = await asyncio.wait_for(ws1.recv(), timeout=1)
            msg2 = await asyncio.wait_for(ws2.recv(), timeout=1)

            parsed1 = json.loads(msg1)
            parsed2 = json.loads(msg2)

            assert parsed1["type"] == "message"
            assert parsed1["content"] == "Hello from user 1"
            assert parsed2["type"] == "message"
```

## 4. Deployment Configuration

### Docker Compose

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  gateway:
    image: priya/gateway:latest
    ports:
      - "9001:9001"
    environment:
      REDIS_URL: redis://redis:6379/0
      REDIS_MAX_CONNECTIONS: 50
      ENVIRONMENT: production
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9001/health"]
      interval: 10s
      timeout: 3s
      retries: 3

  conversation:
    image: priya/conversation:latest
    ports:
      - "9004:9004"
    environment:
      REDIS_URL: redis://redis:6379/0
      REDIS_MAX_CONNECTIONS: 50
      CONVERSATION_SERVICE_PORT: 9004
      ENVIRONMENT: production
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9004/health"]
      interval: 10s
      timeout: 3s
      retries: 3

volumes:
  redis_data:
```

## Summary

These examples demonstrate:
- ✅ Complete frontend integration (React)
- ✅ Backend service integration (Python)
- ✅ Real-time metrics broadcasting
- ✅ Event bus integration
- ✅ Unit and integration testing
- ✅ Deployment configuration

Ready for production deployment!
