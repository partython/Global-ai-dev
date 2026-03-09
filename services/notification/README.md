# Notification Service - Priya Global AI Sales Platform

Complete notification delivery system for the Priya Global Platform running on **Port 9024**.

## Overview

The Notification Service handles ALL notification delivery across the platform, including:
- Push notifications via Firebase Cloud Messaging (FCM)
- Real-time in-app notifications via WebSocket
- Notification center with read/unread/archive states
- Tenant-scoped templates with variable substitution
- Do-not-disturb schedules and delivery preferences
- Device token management

## Architecture

### Multi-Tenant Design
- Every notification has `tenant_id` for isolation
- Row Level Security (RLS) enforced at database level
- Connection-level tenant context via `SET LOCAL app.current_tenant_id`
- No data leakage between tenants even with application bugs

### Real-Time Notifications
- WebSocket connections managed by `ConnectionManager`
- Token-based authentication on WebSocket
- Per-user and per-topic broadcasting
- Graceful handling of disconnections

### Delivery Pipeline
1. Notification stored in database
2. Delivery rules checked (DND, preferences, mute status)
3. Channels determined (push, in-app, email)
4. Async delivery via background tasks
5. FCM delivery for push notifications
6. WebSocket broadcast for in-app delivery

## API Endpoints

### Health Check
```
GET /api/v1/notifications/health
```
Returns service health status.

### Send Notification (Single User)
```
POST /api/v1/notifications/send
Content-Type: application/json
Authorization: Bearer <token>

{
  "user_id": "user_uuid",
  "notification_type": "message",
  "title": "New message from John",
  "body": "Hi there!",
  "data": {"conversation_id": "conv_123"},
  "priority": "normal",
  "channels": ["in_app", "push"],
  "ttl_seconds": 86400
}
```

### Broadcast Notification (Tenant/Topic/Role)
```
POST /api/v1/notifications/broadcast
Content-Type: application/json
Authorization: Bearer <token>

{
  "title": "System Maintenance",
  "body": "Scheduled maintenance at 2 AM",
  "target_type": "tenant",  # or "topic", "role"
  "target_value": "tenant_uuid",
  "priority": "high",
  "channels": ["in_app", "push"]
}
```

### Get User's Notifications
```
GET /api/v1/notifications?limit=50&offset=0&unread_only=false
Authorization: Bearer <token>
```

Returns paginated list of notifications for authenticated user.

### Mark Notification as Read
```
PUT /api/v1/notifications/{notification_id}/read
Authorization: Bearer <token>
```

### Mark All Notifications as Read
```
PUT /api/v1/notifications/read-all
Authorization: Bearer <token>
```

### Archive Notification (Soft Delete)
```
DELETE /api/v1/notifications/{notification_id}
Authorization: Bearer <token>
```

### Register Device for Push
```
POST /api/v1/notifications/devices/register
Content-Type: application/json
Authorization: Bearer <token>

{
  "device_token": "fcm_token_...",
  "device_type": "ios",
  "device_name": "iPhone 14 Pro",
  "app_version": "2.1.0",
  "os_version": "17.2"
}
```

### Unregister Device
```
DELETE /api/v1/notifications/devices/{device_token}
Authorization: Bearer <token>
```

### Get User's Notification Preferences
```
GET /api/v1/notifications/preferences
Authorization: Bearer <token>
```

### Update Notification Preferences
```
PUT /api/v1/notifications/preferences
Content-Type: application/json
Authorization: Bearer <token>

{
  "do_not_disturb_enabled": true,
  "do_not_disturb_start": "22:00",
  "do_not_disturb_end": "08:00",
  "preferred_channels": ["in_app", "push"],
  "mute_all": false,
  "notification_sounds": true,
  "notification_badges": true,
  "marketing_emails": true,
  "system_alerts": true,
  "per_type_preferences": {
    "message": true,
    "cart_abandoned": false
  }
}
```

### Create Notification Template
```
POST /api/v1/notifications/templates
Content-Type: application/json
Authorization: Bearer <token>

{
  "name": "New Message Template",
  "notification_type": "message",
  "title_template": "Message from {{sender_name}}",
  "body_template": "{{message_preview}}",
  "language": "en",
  "variables": ["sender_name", "message_preview"],
  "priority": "normal",
  "channels": ["in_app", "push"]
}
```

### List Notification Templates
```
GET /api/v1/notifications/templates?notification_type=message&language=en
Authorization: Bearer <token>
```

### Real-Time WebSocket Connection
```
WebSocket /ws/notifications?token=<jwt_token>
```

Connection stays open for real-time notification delivery.

**Client → Server:**
```json
{"type": "ping"}
```

**Server → Client (Notification):**
```json
{
  "type": "notification",
  "id": "notif_uuid",
  "title": "New message",
  "body": "Hello!",
  "data": {"conversation_id": "..."},
  "priority": "normal",
  "timestamp": "2026-03-06T10:30:00Z"
}
```

## Notification Types

Predefined notification types:
- `message` - New message or conversation
- `lead_score` - Lead score change alert
- `cart_abandoned` - Shopping cart abandoned
- `order_status` - Order status update
- `campaign_alert` - Campaign performance alert
- `system_alert` - System or billing alert
- `team_mention` - Team mention or assignment

## Priority Levels

- `low` - Background, respects DND
- `normal` - Standard, respects DND
- `high` - Important, may bypass some DND rules
- `urgent` - Critical, always delivered (bypasses DND)

## Do-Not-Disturb (DND) Rules

- User can set DND window (e.g., 22:00 - 08:00)
- Regular and high priority notifications deferred until DND ends
- Urgent priority always bypasses DND
- DND can be enabled/disabled per user

## Delivery Channels

- `push` - Firebase Cloud Messaging (FCM) to mobile/web
- `in_app` - WebSocket real-time delivery
- `email` - Email delivery (integration point)

## Database Schema

### notifications table
```sql
CREATE TABLE notifications (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL,
  notification_type VARCHAR(50) NOT NULL,
  title VARCHAR(200) NOT NULL,
  body VARCHAR(1000) NOT NULL,
  data JSONB,
  priority VARCHAR(20) DEFAULT 'normal',
  is_read BOOLEAN DEFAULT false,
  is_archived BOOLEAN DEFAULT false,
  created_at TIMESTAMP NOT NULL,
  read_at TIMESTAMP,
  archived_at TIMESTAMP
);
```

### device_tokens table
```sql
CREATE TABLE device_tokens (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL,
  device_token VARCHAR(512) NOT NULL,
  device_type VARCHAR(20) NOT NULL,
  device_name VARCHAR(200),
  app_version VARCHAR(20),
  os_version VARCHAR(20),
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
```

### notification_preferences table
```sql
CREATE TABLE notification_preferences (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  user_id UUID NOT NULL,
  do_not_disturb_enabled BOOLEAN DEFAULT false,
  do_not_disturb_start VARCHAR(5),  -- HH:MM format
  do_not_disturb_end VARCHAR(5),    -- HH:MM format
  preferred_channels TEXT[] DEFAULT ARRAY['in_app', 'push'],
  mute_all BOOLEAN DEFAULT false,
  notification_sounds BOOLEAN DEFAULT true,
  notification_badges BOOLEAN DEFAULT true,
  marketing_emails BOOLEAN DEFAULT true,
  system_alerts BOOLEAN DEFAULT true,
  per_type_preferences JSONB DEFAULT '{}',
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
```

### notification_templates table
```sql
CREATE TABLE notification_templates (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  name VARCHAR(100) NOT NULL,
  notification_type VARCHAR(50) NOT NULL,
  title_template VARCHAR(200) NOT NULL,
  body_template VARCHAR(1000) NOT NULL,
  data_template JSONB,
  language VARCHAR(10) DEFAULT 'en',
  variables TEXT[] DEFAULT ARRAY[]::TEXT[],
  priority VARCHAR(20) DEFAULT 'normal',
  channels TEXT[] DEFAULT ARRAY['in_app', 'push'],
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
```

## Environment Variables

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=priya_platform
DB_USER=postgres
DB_PASSWORD=***
DB_POOL_MIN=10
DB_POOL_MAX=50

# FCM Configuration
FCM_SERVER_KEY=***
FCM_PROJECT_ID=priya-global-xxx

# Service Configuration
LOG_LEVEL=INFO
JWT_SECRET_KEY=***
JWT_ALGORITHM=RS256
CORS_ORIGINS=http://localhost:3000,https://app.priyaglobal.com
```

## Security Features

1. **JWT Authentication**: All endpoints require valid Bearer token
2. **Tenant Isolation**: RLS policies enforce per-tenant data access
3. **WebSocket Auth**: Token validation on connection
4. **Input Sanitization**: All user inputs sanitized
5. **Rate Limiting**: Inherited from gateway
6. **PII Masking**: Sensitive data masked in logs
7. **CORS Configuration**: Controlled by config

## Example Usage

### Using Python aiohttp Client

```python
import aiohttp

async def send_notification(token: str):
    async with aiohttp.ClientSession() as session:
        payload = {
            "user_id": "user_123",
            "notification_type": "message",
            "title": "New Message",
            "body": "You have a new message",
            "priority": "normal",
            "channels": ["in_app", "push"]
        }
        
        async with session.post(
            "http://localhost:9024/api/v1/notifications/send",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            return await resp.json()
```

### Using JavaScript WebSocket

```javascript
// Connect to real-time notification stream
const ws = new WebSocket(`ws://localhost:9024/ws/notifications?token=${jwtToken}`);

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log("Received notification:", notification);
  // Update UI with notification
};

ws.onclose = () => {
  console.log("WebSocket disconnected");
  // Attempt reconnection
};
```

## Performance Considerations

- **Connection Pool**: 10-50 database connections
- **WebSocket Manager**: Efficiently manages thousands of concurrent connections
- **Async Tasks**: Non-blocking FCM delivery
- **Batch Delivery**: Broadcasting to multiple users in parallel
- **Template Caching**: Templates cached per tenant

## Monitoring

Key metrics to monitor:
- Active WebSocket connections per user
- Notification delivery latency (in-app vs push)
- FCM delivery success rate
- Database query performance
- Background task queue depth
- Error rates by notification type

## Troubleshooting

### Notifications not receiving
1. Check device token is registered and active
2. Verify do-not-disturb window and priority level
3. Check notification preferences for muted types
4. Verify WebSocket connection is active
5. Check FCM credentials and project ID

### WebSocket disconnections
1. Verify token is valid and not expired
2. Check network connectivity
3. Verify CORS configuration
4. Check firewall rules

### High latency
1. Monitor database connection pool
2. Check FCM API rate limits
3. Monitor background task queue
4. Check network latency to FCM

## Contributing

When adding new notification types:
1. Add to `NOTIFICATION_TYPES` constant
2. Create templates for the type
3. Add per-type preference field
4. Update documentation
5. Add tests for delivery rules

## License

Proprietary - Priya Global Inc.
