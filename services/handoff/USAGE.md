# Handoff Service - Usage Guide

## Starting the Service

```bash
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/handoff
pip install -r requirements.txt
python main.py
```

Service will be available at `http://localhost:9026`

## API Examples

All requests require the `X-Tenant-ID` header.

### 1. Request Handoff from AI to Human

**Request:**
```bash
curl -X POST http://localhost:9026/api/v1/handoff/request \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "conversation_id": "conv_123456",
    "customer_id": "cust_789",
    "trigger_type": "customer_request",
    "reason": "Customer explicitly requested a human agent",
    "ai_confidence_score": 0.45,
    "sentiment_score": 0.25,
    "preferred_language": "en",
    "is_vip": true,
    "priority_level": "high"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "conversation_id": "conv_123456",
  "customer_id": "cust_789",
  "assigned_agent_id": null,
  "status": "pending",
  "trigger_type": "customer_request",
  "queue_position": 1,
  "estimated_wait_time_seconds": 120,
  "created_at": "2026-03-06T10:30:00"
}
```

### 2. Get Current Queue

**Request:**
```bash
curl http://localhost:9026/api/v1/handoff/queue \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Accept: application/json"
```

**Response:**
```json
{
  "queue_length": 3,
  "queue": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "customer_id": "cust_789",
      "is_vip": true,
      "queue_position": 1,
      "trigger_type": "customer_request",
      "priority_level": "high",
      "created_at": "2026-03-06T10:30:00"
    }
  ]
}
```

### 3. Register Agent

**Request:**
```bash
curl -X POST "http://localhost:9026/api/v1/handoff/agents/register?agent_id=agent_001" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "name": "John Smith",
    "language_proficiencies": ["en", "es", "fr"],
    "skills": {
      "sales": 9,
      "support": 8,
      "technical": 7
    },
    "is_supervisor": false,
    "max_concurrent": 5
  }'
```

### 4. Assign Handoff to Agent

**Request:**
```bash
curl -X POST "http://localhost:9026/api/v1/handoff/assign?handoff_id=550e8400-e29b-41d4-a716-446655440001&agent_id=agent_001" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "status": "assigned",
  "agent_id": "agent_001"
}
```

### 5. Get Agent Status

**Request:**
```bash
curl http://localhost:9026/api/v1/handoff/agents/status \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "total_agents": 5,
  "agents": [
    {
      "id": "agent_001",
      "name": "John Smith",
      "status": "online",
      "current_conversations": 2,
      "max_concurrent": 5,
      "is_supervisor": false,
      "language_proficiencies": ["en", "es", "fr"],
      "skills": {"sales": 9, "support": 8},
      "last_activity": "2026-03-06T10:30:00"
    }
  ]
}
```

### 6. Update Agent Status

**Request:**
```bash
curl -X PUT http://localhost:9026/api/v1/handoff/agents/status \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "agent_id": "agent_001",
    "status": "busy",
    "max_concurrent": 5
  }'
```

### 7. Add Internal Note

**Request:**
```bash
curl -X POST "http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/notes?agent_id=agent_001" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "note": "Customer is upset about billing. Offered 20% discount."
  }'
```

### 8. Get Conversation Context

**Request:**
```bash
curl http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/context \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "handoff": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "conversation_id": "conv_123456",
    "customer_id": "cust_789",
    "trigger_type": "customer_request",
    "reason": "Customer explicitly requested a human agent",
    "ai_confidence_score": 0.45,
    "sentiment_score": 0.25
  },
  "internal_notes": [
    {
      "agent_id": "agent_001",
      "note": "Customer is upset about billing. Offered 20% discount.",
      "created_at": "2026-03-06T10:35:00"
    }
  ],
  "ai_summary": "Customer cust_789 initiated customer_request handoff. Confidence: 0.45, Sentiment: 0.25"
}
```

### 9. Get AI Suggestion

**Request:**
```bash
curl -X POST http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/suggest \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "suggestion": "I sincerely apologize for any inconvenience. I'm here to help resolve your issue immediately.",
  "confidence": 0.85,
  "conversation_id": "conv_123456"
}
```

### 10. Submit CSAT Rating

**Request:**
```bash
curl -X POST http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/csat \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "rating": 5,
    "comment": "Excellent service and quick resolution!"
  }'
```

### 11. Transfer to Another Agent

**Request:**
```bash
curl -X PUT "http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/transfer?target_agent_id=agent_002" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

### 12. Escalate to Supervisor

**Request:**
```bash
curl -X PUT http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/escalate \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

### 13. Resolve Handoff

**Request:**
```bash
curl -X PUT http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/resolve \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

### 14. Return to AI

**Request:**
```bash
curl -X PUT http://localhost:9026/api/v1/handoff/550e8400-e29b-41d4-a716-446655440001/return-to-ai \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

### 15. Get Metrics

**Request:**
```bash
curl "http://localhost:9026/api/v1/handoff/metrics?days=7" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "total_handoffs": 145,
  "resolved_count": 138,
  "pending_count": 5,
  "vip_count": 12,
  "avg_resolution_time_minutes": 8.5,
  "avg_csat": 4.6,
  "resolution_rate_percent": 95.17
}
```

### 16. Get SLA Breaches

**Request:**
```bash
curl "http://localhost:9026/api/v1/handoff/sla/breaches?limit=10" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000"
```

### 17. Update Handoff Rules

**Request:**
```bash
curl -X PUT http://localhost:9026/api/v1/handoff/rules \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{
    "confidence_threshold": 0.7,
    "sentiment_threshold": 0.2,
    "first_response_sla_minutes": 3,
    "resolution_sla_minutes": 45,
    "enable_vip_auto_route": true,
    "enable_complex_query_detection": true,
    "complex_query_keywords": ["billing", "refund", "legal"],
    "max_queue_wait_minutes": 20
  }'
```

### 18. Health Check

**Request:**
```bash
curl http://localhost:9026/api/v1/handoff/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "handoff",
  "port": 9026,
  "environment": "development",
  "timestamp": "2026-03-06T10:30:00"
}
```

## WebSocket Connection

Connect to real-time agent dashboard:

```bash
wscat -c "ws://localhost:9026/ws/agent?agent_id=agent_001&x_tenant_id=550e8400-e29b-41d4-a716-446655440000"
```

Send ping to keep connection alive:
```json
{"action": "ping"}
```

Receive messages like:
```json
{
  "event": "handoff_assigned",
  "handoff_id": "550e8400-e29b-41d4-a716-446655440001",
  "customer_id": "cust_789",
  "conversation_id": "conv_123456",
  "is_vip": true,
  "priority_level": "high"
}
```

## Multi-Tenant Isolation

The service enforces complete tenant isolation at the database level. Every table includes `tenant_id` and all queries filter by tenant. This ensures:

- Agents only see their tenant's handoffs
- Queue visibility is tenant-specific
- Metrics are tenant-scoped
- CSAT data is tenant-isolated

## Error Responses

### Missing Tenant ID
```json
{
  "detail": "Missing X-Tenant-ID header"
}
```
Status: 401

### Handoff Not Found
```json
{
  "detail": "Handoff not found"
}
```
Status: 404

### No Available Agents
```json
{
  "detail": "No available agents"
}
```
Status: 503

## Performance Tips

1. **Batch Operations**: Group multiple agent status updates
2. **Query Limits**: Use pagination with `limit` parameter
3. **WebSocket**: Keep connections alive with periodic pings
4. **Connection Pool**: Service maintains 5-20 DB connections
5. **Async**: All I/O is non-blocking for high concurrency

## Testing

Run the test suite:
```bash
pytest tests/
pytest tests/test_handoff.py -v
```

Load test the service:
```bash
ab -n 10000 -c 100 http://localhost:9026/api/v1/handoff/health
```
