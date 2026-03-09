# WebSocket Quick Start Guide

Get real-time messaging working in 5 minutes.

## Setup

### 1. Ensure Redis is Running
```bash
docker run -d -p 6379:6379 redis:latest
# or
redis-server
```

### 2. Environment Variables
```env
REDIS_URL=redis://localhost:6379/0
CONVERSATION_SERVICE_PORT=9004
```

### 3. Install Dependencies
Already included in requirements.txt:
- fastapi
- websockets
- redis[asyncio]
- pydantic

### 4. Start Services

Gateway (WebSocket + REST proxy):
```bash
cd services/gateway
python main.py
# Runs on http://localhost:9001
```

Conversation Service (WebSocket + REST):
```bash
cd services/conversation
python main.py
# Runs on http://localhost:9004
```

## Quick Test

### Browser Console (Chrome DevTools)

```javascript
// Connect to conversation chat
const token = "your_jwt_token";
const ws = new WebSocket(
  `ws://localhost:9001/ws/conversations/conv123?token=${token}`
);

ws.onopen = () => {
  console.log("Connected!");
  // Send a message
  ws.send(JSON.stringify({
    type: "message",
    content: "Hello world!",
    sender_id: "user123"
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log("Received:", message);
};

ws.onerror = (error) => {
  console.error("Error:", error);
};

ws.onclose = () => {
  console.log("Disconnected");
};
```

### curl (for testing without auth)

```bash
# Create conversation
curl -X POST http://localhost:9004/api/v1/conversations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "user_id": "user123",
    "title": "Test Chat",
    "channel": "webchat"
  }'

# Get conversation
curl http://localhost:9004/api/v1/conversations/conv_id \
  -H "Authorization: Bearer YOUR_TOKEN"

# Send message via REST
curl -X POST http://localhost:9004/api/v1/conversations/conv_id/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "content": "Hello from REST!"
  }'
```

## WebSocket Endpoints

| Endpoint | Purpose | Auth | Rooms |
|----------|---------|------|-------|
| `/ws/conversations/{id}` | Live chat | JWT Header | `conversation:{id}` |
| `/ws/dashboard` | Dashboard updates | JWT Header | `dashboard:{tenant}` |
| `/ws/agent` | Agent presence | JWT Header | `agent:{id}`, `agent_queue:{tenant}` |
| `/ws/live/{id}` | Live chat with persistence | JWT Query | `conversation:{id}` |

## Message Types

### Send from Client

```javascript
// Chat message
{
  "type": "message",
  "content": "Hello!",
  "conversation_id": "conv123"
}

// Typing indicator
{
  "type": "typing",
  "is_typing": true,
  "conversation_id": "conv123"
}

// Heartbeat response
{
  "type": "pong"
}

// Agent status
{
  "type": "agent_status",
  "status": "available"  // or "busy", "offline"
}
```

### Receive from Server

```javascript
// Connection established
{
  "type": "connect",
  "connection_id": "conn_uuid",
  "status": "connected"
}

// Chat message
{
  "type": "message",
  "message_id": "msg_uuid",
  "sender_id": "user123",
  "content": "Hello!",
  "timestamp": "2026-03-06T20:15:30Z"
}

// Typing indicator
{
  "type": "typing_start",
  "sender_id": "user456"
}

// Heartbeat ping
{
  "type": "ping",
  "timestamp": "2026-03-06T20:15:30Z"
}

// Error
{
  "type": "error",
  "error_code": "rate_limit_exceeded",
  "message": "Too many messages"
}
```

## Common Tasks

### Broadcast to All Users in Conversation

```python
# In your service
await websocket_manager.send_to_room(
    f"conversation:{conversation_id}",
    {
        "type": "message",
        "content": "System announcement",
        "sender_type": "system"
    }
)
```

### Send to Specific User

```python
# All connections of a user
await websocket_manager.send_to_user(
    tenant_id,
    user_id,
    {"type": "notification", "body": "New message"}
)
```

### Notify Dashboard

```python
# Update all dashboard viewers in a tenant
await websocket_manager.send_to_room(
    f"dashboard:{tenant_id}",
    {
        "type": "metrics_update",
        "active_conversations": 25,
        "total_agents_online": 8
    }
)
```

### Close Connection

```python
# Gracefully close
await websocket_manager.close_connection(
    connection_id,
    code=1000,
    reason="Conversation ended"
)
```

## Debugging

### View Metrics
```bash
curl http://localhost:9001/ws/metrics | jq
```

Example output:
```json
{
  "connections": {
    "total": 42,
    "by_tenant": {
      "tenant_123": 15,
      "tenant_456": 27
    },
    "by_room": {
      "conversation:conv1": 2,
      "dashboard:tenant_123": 5
    }
  },
  "metrics": {
    "total_connections": 42,
    "total_messages": 1523,
    "total_errors": 2,
    "pubsub_messages": 487
  }
}
```

### Enable Debug Logging

```python
import logging
logging.getLogger("priya.realtime").setLevel(logging.DEBUG)
```

### Test Redis Connection

```bash
redis-cli ping
# Should return: PONG

redis-cli
> SUBSCRIBE priya:ws:room:*
# Should see pub/sub messages
```

## Troubleshooting

### Connection Refused
- Check Redis is running: `redis-cli ping`
- Check port 9001 (gateway) or 9004 (conversation) are accessible
- Verify firewall allows WebSocket connections

### Authentication Fails
- Verify JWT token is valid and not expired
- Check `Authorization: Bearer {token}` header format
- Token must contain `tenant_id` and `sub`/`user_id` claims

### Messages Not Received
- Check WebSocket is in "connected" state
- Verify you're sending to correct room
- Check Redis pub/sub: `redis-cli SUBSCRIBE priya:ws:room:*`

### Slow Message Delivery
- Check Redis latency: `redis-cli --latency`
- Monitor network connectivity
- Check service CPU/memory usage

## Next Steps

1. **Integrate with your frontend**
   - Use socket.io client library or raw WebSocket API
   - Handle reconnection logic
   - Implement offline message queuing

2. **Add authentication**
   - Generate JWT tokens for users
   - Implement token refresh logic
   - Add rate limiting per user

3. **Monitor in production**
   - Set up alerts on `/ws/metrics` endpoint
   - Track error rates and latency
   - Monitor Redis memory usage

4. **Scale horizontally**
   - Deploy multiple gateway instances
   - Use sticky sessions or load balancer affinity
   - Redis pub/sub handles cross-instance messaging automatically

## Example: Complete Chat Widget

```html
<!DOCTYPE html>
<html>
<head>
  <title>Priya Chat</title>
  <style>
    #messages { height: 400px; border: 1px solid #ccc; overflow-y: auto; }
    #message { width: 300px; }
  </style>
</head>
<body>
  <div id="messages"></div>
  <input id="message" type="text" placeholder="Type message...">
  <button onclick="sendMessage()">Send</button>

  <script>
    const token = "your_jwt_token";
    const conversationId = "conv_123";
    const userId = "user_456";

    const ws = new WebSocket(
      `ws://localhost:9001/ws/conversations/${conversationId}`,
      [],
      {
        headers: { Authorization: `Bearer ${token}` }
      }
    );

    ws.onopen = () => {
      addMessage("System", "Connected!", "system");
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "message") {
        addMessage(msg.sender_id, msg.content, msg.sender_type);
      } else if (msg.type === "typing_start") {
        showTyping(msg.sender_id);
      }
    };

    function sendMessage() {
      const input = document.getElementById("message");
      const content = input.value.trim();

      if (content) {
        ws.send(JSON.stringify({
          type: "message",
          content: content,
          sender_id: userId
        }));
        input.value = "";
      }
    }

    function addMessage(sender, content, type = "user") {
      const div = document.getElementById("messages");
      const p = document.createElement("p");
      p.innerHTML = `<strong>${sender}:</strong> ${content}`;
      p.style.color = type === "system" ? "gray" : "black";
      div.appendChild(p);
      div.scrollTop = div.scrollHeight;
    }

    function showTyping(userId) {
      console.log(`${userId} is typing...`);
    }

    // Send typing indicator
    let typingTimeout;
    document.getElementById("message").onkeypress = () => {
      clearTimeout(typingTimeout);
      ws.send(JSON.stringify({
        type: "typing",
        is_typing: true,
        conversation_id: conversationId
      }));

      typingTimeout = setTimeout(() => {
        ws.send(JSON.stringify({
          type: "typing",
          is_typing: false,
          conversation_id: conversationId
        }));
      }, 3000);
    };
  </script>
</body>
</html>
```

## Support

For issues:
1. Check logs: `grep -i websocket services/gateway/logs.txt`
2. Monitor metrics: `curl http://localhost:9001/ws/metrics`
3. Test Redis: `redis-cli ping`
4. Check auth: Verify JWT token contents
