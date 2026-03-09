# Code Examples - Plugin SDK Service

## 1. Installing a Plugin

```bash
curl -X POST http://localhost:9025/api/v1/plugins/install \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{
    "plugin_id": "123e4567-e89b-12d3-a456-426614174000",
    "config": {
      "api_key": "sk_test_123",
      "max_retries": 5
    }
  }'
```

Response:
```json
{
  "status": "installed",
  "plugin_id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "CRM Sync Plugin",
  "version": "1.2.0"
}
```

## 2. Publishing a Plugin to Marketplace

```bash
curl -X POST http://localhost:9025/api/v1/plugins/developer/publish \
  -H "X-API-Key: pk_dev_1234567890abcdef" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Analytics Dashboard",
    "version": "1.0.0",
    "description": "Real-time analytics dashboard for sales metrics",
    "category": "analytics",
    "permissions": ["read:leads", "read:orders", "write:reports"],
    "webhook_url": "https://plugin.example.com/webhooks",
    "config_schema": {
      "type": "object",
      "properties": {
        "theme": {"type": "string"},
        "refresh_interval": {"type": "integer"}
      }
    }
  }'
```

Response:
```json
{
  "plugin_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Analytics Dashboard",
  "version": "1.0.0",
  "status": "published"
}
```

## 3. Emitting an Event to Plugin Subscribers

```bash
curl -X POST http://localhost:9025/api/v1/plugins/events/emit \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "lead.scored",
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "data": {
      "lead_id": "lead_abc123",
      "score": 85,
      "segment": "enterprise",
      "timestamp": "2024-03-06T10:30:00Z"
    }
  }'
```

Response:
```json
{
  "status": "emitted",
  "event_type": "lead.scored",
  "subscribed_plugins": 3,
  "delivered": 3
}
```

## 4. Subscribing Plugin to Event

```bash
curl -X POST http://localhost:9025/api/v1/plugins/550e8400-e29b-41d4-a716-446655440001/subscribe/message.received \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json"
```

Response:
```json
{
  "status": "subscribed",
  "plugin_id": "550e8400-e29b-41d4-a716-446655440001",
  "event_type": "message.received"
}
```

## 5. Creating Scoped API Key for Plugin

```bash
curl -X POST http://localhost:9025/api/v1/plugins/550e8400-e29b-41d4-a716-446655440001/api-keys \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "read-write",
    "rate_limit": 5000
  }'
```

Response:
```json
{
  "api_key": "pk_550e8400e29b41d4a716446655440000_abcdef1234567890",
  "scope": "read-write",
  "rate_limit": 5000,
  "message": "Store this key securely. You won't be able to see it again."
}
```

## 6. Registering a Developer

```bash
curl -X POST http://localhost:9025/api/v1/plugins/developer/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dev@example.com",
    "company": "Tech Innovations Inc",
    "name": "Jane Developer"
  }'
```

Response:
```json
{
  "developer_id": "dev_550e8400e29b41d4a716",
  "email": "dev@example.com",
  "api_key": "pk_dev_123abc456def789",
  "message": "Store API key securely. You won't be able to see it again."
}
```

## 7. Getting Plugin Analytics

```bash
curl -X GET 'http://localhost:9025/api/v1/plugins/550e8400-e29b-41d4-a716-446655440001/analytics?days=7' \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

Response:
```json
{
  "plugin_id": "550e8400-e29b-41d4-a716-446655440001",
  "resource_usage": {
    "api_calls": 1250,
    "webhook_calls": 487,
    "error_count": 12,
    "last_used": "2024-03-06T09:45:00"
  },
  "analytics": [
    {
      "event_type": "lead.scored",
      "success_count": 245,
      "failure_count": 3,
      "avg_latency_ms": 234.5,
      "date": "2024-03-06"
    },
    {
      "event_type": "message.received",
      "success_count": 189,
      "failure_count": 1,
      "avg_latency_ms": 145.2,
      "date": "2024-03-06"
    }
  ],
  "period_days": 7
}
```

## 8. Updating Plugin Configuration

```bash
curl -X PUT http://localhost:9025/api/v1/plugins/550e8400-e29b-41d4-a716-446655440001/config \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "api_key": "sk_live_new_key",
      "webhook_timeout": 45,
      "enable_batching": true,
      "batch_size": 100
    }
  }'
```

Response:
```json
{
  "status": "updated",
  "plugin_id": "550e8400-e29b-41d4-a716-446655440001",
  "config": {
    "api_key": "sk_live_new_key",
    "webhook_timeout": 45,
    "enable_batching": true,
    "batch_size": 100
  }
}
```

## 9. Listing Marketplace Plugins

```bash
curl -X GET 'http://localhost:9025/api/v1/plugins/marketplace?category=analytics&limit=10' \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

Response:
```json
{
  "plugins": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Analytics Dashboard",
      "version": "1.0.0",
      "author": "Tech Innovations Inc",
      "description": "Real-time analytics dashboard for sales metrics",
      "category": "analytics",
      "permissions": ["read:leads", "read:orders", "write:reports"],
      "webhook_url": "https://plugin.example.com/webhooks",
      "config_schema": { "type": "object" },
      "created_at": "2024-03-01T10:00:00"
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

## 10. Health Check

```bash
curl -X GET http://localhost:9025/api/v1/plugins/health
```

Response:
```json
{
  "status": "healthy",
  "database": "healthy",
  "timestamp": "2024-03-06T10:30:00.123456",
  "service": "plugin-sdk",
  "port": 9025
}
```

## 11. Webhook Signature Verification (Python Example)

```python
import hmac
import hashlib
import json

def verify_plugin_webhook(payload_str: str, signature: str, secret: str) -> bool:
    """Verify webhook signature from Plugin SDK"""
    expected_signature = hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

# In webhook handler
payload_str = request.get_data(as_text=True)
signature = request.headers.get('X-Webhook-Signature')

if verify_plugin_webhook(payload_str, signature, os.getenv('WEBHOOK_SECRET')):
    event = json.loads(payload_str)
    # Process event
else:
    return "Invalid signature", 401
```

## 12. Plugin Developer API Key Usage

```bash
# As a developer, use your API key to publish plugins
curl -X POST http://localhost:9025/api/v1/plugins/developer/publish \
  -H "X-API-Key: pk_dev_your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Email Campaign Plugin",
    "version": "2.3.1",
    "description": "Send targeted email campaigns",
    "category": "integration",
    "permissions": ["read:contacts", "write:campaigns", "read:templates"],
    "webhook_url": "https://email-plugin.example.com/api/webhook"
  }'
```

## 13. Complete Plugin Installation & Setup Workflow

```python
import httpx
import json

class PluginClient:
    def __init__(self, base_url: str, tenant_id: str):
        self.base_url = base_url
        self.tenant_id = tenant_id
        self.headers = {"X-Tenant-ID": tenant_id}
    
    async def install_plugin(self, plugin_id: str, config: dict) -> dict:
        """Install plugin for this tenant"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/plugins/install",
                headers=self.headers,
                json={"plugin_id": plugin_id, "config": config}
            )
            return response.json()
    
    async def subscribe_to_event(self, plugin_id: str, event_type: str) -> dict:
        """Subscribe plugin to event"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/plugins/{plugin_id}/subscribe/{event_type}",
                headers=self.headers
            )
            return response.json()
    
    async def emit_event(self, event_type: str, data: dict) -> dict:
        """Emit event to subscribers"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/plugins/events/emit",
                headers=self.headers,
                json={
                    "event_type": event_type,
                    "tenant_id": self.tenant_id,
                    "data": data
                }
            )
            return response.json()

# Usage
client = PluginClient("http://localhost:9025", "550e8400-e29b-41d4-a716-446655440000")
install = await client.install_plugin("plugin-id", {"key": "value"})
subscribe = await client.subscribe_to_event(install["plugin_id"], "lead.scored")
emit = await client.emit_event("lead.scored", {"lead_id": "123", "score": 85})
```

## Error Response Examples

### Invalid Tenant ID
```json
{
  "detail": "X-Tenant-ID header required"
}
```

### Plugin Not Found
```json
{
  "detail": "Plugin not found"
}
```

### Invalid Webhook Signature
```json
{
  "detail": "Invalid signature"
}
```

### Duplicate Installation
```json
{
  "detail": "Plugin already installed"
}
```

### Invalid UUID Format
```json
{
  "detail": "Invalid UUID format"
}
```
