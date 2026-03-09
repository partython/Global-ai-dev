# Priya Global AI Sales Platform - Handoff Service

## Overview
Complete AI-to-human agent handoff management service for the Priya Global platform. Handles intelligent routing, queue management, SLA tracking, and customer satisfaction collection.

## Service Details
- **Port**: 9026
- **Framework**: FastAPI (async)
- **Database**: PostgreSQL with asyncpg
- **Multi-tenant**: Full tenant isolation with RLS
- **Lines of Code**: 1169

## Key Features

### 1. Handoff Triggers
- Customer explicitly requests human agent
- AI confidence score below configurable threshold
- Sentiment drops below threshold (frustrated customer)
- VIP customer auto-route
- Complex query detection
- Configurable custom trigger rules per tenant

### 2. Agent Queue Management
- Priority-based routing (Low, Normal, High, Critical)
- Round-robin assignment
- Skills-based routing (language, product expertise, department)
- Agent availability/status (online, busy, away, offline)
- Max concurrent conversations per agent
- Queue position tracking with wait time estimation
- Real-time queue notifications

### 3. Live Agent Tools
- Real-time conversation takeover
- AI-suggested responses (agent assist)
- Conversation context handover (full history + AI summary)
- Internal notes between agents
- Transfer between agents
- Escalation to supervisor

### 4. SLA Management
- First response time tracking
- Resolution time tracking
- SLA breach detection and alerts
- Configurable SLA thresholds per tenant
- Auto-escalation on SLA breach

### 5. CSAT Collection
- Post-handoff satisfaction survey
- 1-5 rating + optional comment
- CSAT scoring and trending analysis

## Core Endpoints

### Handoff Management
- `POST /api/v1/handoff/request` — Request handoff from AI to human
- `GET /api/v1/handoff/queue` — Get current queue for tenant
- `POST /api/v1/handoff/assign` — Assign conversation to agent
- `PUT /api/v1/handoff/{id}/transfer` — Transfer to another agent
- `PUT /api/v1/handoff/{id}/escalate` — Escalate to supervisor
- `PUT /api/v1/handoff/{id}/resolve` — Resolve/close handoff
- `PUT /api/v1/handoff/{id}/return-to-ai` — Return conversation to AI

### Agent Management
- `POST /api/v1/handoff/agents/register` — Register new agent
- `GET /api/v1/handoff/agents/status` — Get all agents' status
- `PUT /api/v1/handoff/agents/status` — Update agent status

### Context & Collaboration
- `GET /api/v1/handoff/{id}/context` — Get conversation context + AI summary
- `POST /api/v1/handoff/{id}/notes` — Add internal note
- `POST /api/v1/handoff/{id}/suggest` — Get AI-suggested response

### Customer Feedback
- `POST /api/v1/handoff/{id}/csat` — Submit CSAT rating

### SLA & Metrics
- `GET /api/v1/handoff/sla/breaches` — Get SLA breaches
- `PUT /api/v1/handoff/rules` — Update handoff trigger rules
- `GET /api/v1/handoff/metrics` — Get handoff performance metrics

### Real-time
- `WebSocket /ws/agent` — Real-time agent dashboard
- `GET /api/v1/handoff/health` — Health check

## Database Schema

### handoff_requests
- id (UUID)
- tenant_id (UUID) - Multi-tenant isolation
- conversation_id (VARCHAR)
- customer_id (VARCHAR)
- assigned_agent_id (VARCHAR)
- status (ENUM)
- trigger_type (ENUM)
- priority_level (ENUM)
- ai_confidence_score (FLOAT)
- sentiment_score (FLOAT)
- is_vip (BOOLEAN)
- queue_position (INT)

### agents
- id (VARCHAR)
- tenant_id (UUID) - Multi-tenant isolation
- name (VARCHAR)
- status (ENUM: online, busy, away, offline)
- current_conversations (INT)
- max_concurrent (INT)
- language_proficiencies (TEXT[])
- skills (JSONB)
- is_supervisor (BOOLEAN)

### agent_notes
- id (UUID)
- tenant_id (UUID)
- handoff_id (UUID) - FK
- agent_id (VARCHAR)
- note (TEXT)

### csat_responses
- id (UUID)
- tenant_id (UUID)
- handoff_id (UUID) - FK
- rating (INT 1-5)
- comment (TEXT)

### handoff_rules
- id (UUID)
- tenant_id (UUID) - Per-tenant config
- confidence_threshold (FLOAT)
- sentiment_threshold (FLOAT)
- first_response_sla_minutes (INT)
- resolution_sla_minutes (INT)
- enable_vip_auto_route (BOOLEAN)
- enable_complex_query_detection (BOOLEAN)

### sla_tracking
- id (UUID)
- tenant_id (UUID)
- handoff_id (UUID) - FK
- first_response_breached (BOOLEAN)
- resolution_breached (BOOLEAN)

## Environment Variables

```bash
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=priya
JWT_SECRET=dev-secret-key
ENVIRONMENT=development
```

## Security

- All database keys from `os.getenv()`
- Tenant isolation via tenant_id in every table
- Agent authentication via header tokens
- Input sanitization via Pydantic validators
- Row-Level Security (RLS) ready
- No hardcoded secrets

## WebSocket Protocol

### Agent Connection
```
WebSocket /ws/agent?agent_id=agent123&x_tenant_id=tenant_uuid
```

### Messages
```json
{
  "action": "ping",
  "timestamp": "2026-03-06T10:30:00"
}

{
  "event": "handoff_assigned",
  "handoff_id": "uuid",
  "customer_id": "cust123",
  "is_vip": false
}
```

## Async Performance

- Full async/await implementation
- asyncpg for non-blocking database operations
- Connection pooling (5-20 connections)
- Concurrent WebSocket handling
- Parallel broadcast capabilities

## Error Handling

- 404: Resource not found
- 401: Missing tenant ID
- 503: No available agents/supervisors
- Graceful WebSocket disconnection handling
- Comprehensive logging with timestamps

## Future Enhancements

- Machine learning for optimal agent routing
- Predictive hold time improvements
- Advanced sentiment analysis
- Callback queue options
- Agent coaching based on CSAT
- Advanced analytics dashboard
- Integration with third-party systems
