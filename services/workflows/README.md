# Automation Workflows Engine

A comprehensive multi-tenant SaaS workflow automation platform built with FastAPI, asyncpg, and JWT authentication.

## Overview

The Automation Workflows Engine provides a visual workflow builder backend that supports complex workflow definitions as JSON DAGs (Directed Acyclic Graphs), with comprehensive execution, versioning, and analytics capabilities.

**Location:** `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/workflows/main.py`
**Port:** 9034
**Lines:** 1142

## Features Implemented

### 1. Visual Workflow Builder Backend
- Store workflow definitions as JSON DAGs
- Node types: trigger, condition, action, delay, branch, end
- Support for complex workflow logic with branching
- Comprehensive node configuration system

### 2. Trigger Types
- **MESSAGE_RECEIVED** - Triggered when a message is received
- **LEAD_CREATED** - Triggered on new lead creation
- **DEAL_STAGE_CHANGED** - Triggered on deal stage change
- **APPOINTMENT_BOOKED** - Triggered on appointment booking
- **FORM_SUBMITTED** - Triggered on form submission
- **TIME_BASED** - Time-based triggers (cron support)
- **WEBHOOK_RECEIVED** - External webhook triggers

### 3. Action Types
- **SEND_MESSAGE** - Send message via any channel (SMS, email, etc.)
- **UPDATE_LEAD** - Update lead field values
- **CREATE_TASK** - Create tasks with priority and assignee
- **SEND_EMAIL** - Send emails with subject and body
- **HTTP_WEBHOOK** - Call external HTTP webhooks
- **AI_RESPONSE** - Generate AI responses
- **ASSIGN_AGENT** - Assign to specific agents
- **ADD_TAG** - Tag records with categories

### 4. Condition Types
- **IF_ELSE** - Basic if/else branching
- **FIELD_COMPARISON** - Compare field values with operators
- **TIME_CONDITION** - Execute based on time windows
- **CHANNEL_TYPE_CHECK** - Check message channel type

### 5. Workflow Execution Engine
- Async execution with proper error handling
- Step-by-step logging of all actions
- Automatic retry on failure support
- Timeout handling (default 3600s)
- DAG traversal with condition evaluation
- Maximum iteration protection (100 iterations)

### 6. Version Control
- Automatic version increment on updates
- Version history tracking in `workflow_versions` table
- Rollback capability (retrieve previous versions)
- Draft/active/paused states

### 7. Analytics & Monitoring
- Total runs count
- Success/failure rates
- Timeout tracking
- Average execution time calculation
- Per-workflow and tenant-level analytics

## API Endpoints

### Workflow Management
- `POST /workflows` - Create new workflow
- `GET /workflows` - List workflows (with filtering)
- `GET /workflows/{workflow_id}` - Get workflow details
- `PUT /workflows/{workflow_id}` - Update workflow
- `DELETE /workflows/{workflow_id}` - Delete workflow (soft delete)

### Workflow State
- `POST /workflows/{workflow_id}/activate` - Activate workflow
- `POST /workflows/{workflow_id}/pause` - Pause workflow

### Execution
- `POST /workflows/{workflow_id}/execute` - Manual trigger
- `POST /workflows/trigger` - Event-based trigger
- `GET /workflows/{workflow_id}/runs` - List runs
- `GET /workflows/{workflow_id}/runs/{run_id}` - Get run details

### Analytics & Health
- `GET /workflows/analytics` - Get analytics data
- `GET /workflows/health` - Health check with DB status

## Security Features

### Authentication & Authorization
- **JWT Authentication** - HTTPBearer + PyJWT
- **AuthContext** - Tenant and user ID extraction
- **Token Validation** - Signature verification with configurable secret

### Multi-Tenancy
- **Row-Level Security (RLS)** - All queries filtered by tenant_id
- **Data Isolation** - Complete tenant data segregation
- **Soft Deletes** - Logical deletion with is_deleted flag

### Secrets Management
- **No Hardcoded Secrets** - All secrets from environment variables
- Environment variables:
  - `JWT_SECRET` - JWT signing secret
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
  - `CORS_ORIGINS` - Comma-separated CORS origins
  - `PORT` - Service port (default 9034)
  - `HOST` - Bind host (default 0.0.0.0)

## Database Schema

### workflows table
- `id` (UUID) - Primary key
- `tenant_id` (UUID) - Multi-tenant isolation
- `name`, `description` - Workflow metadata
- `trigger` (JSONB) - Trigger configuration
- `nodes` (JSONB) - Workflow nodes/DAG
- `state` (VARCHAR) - draft/active/paused
- `version` (INTEGER) - Current version
- `created_at`, `updated_at` - Timestamps
- `created_by` (UUID) - Creator
- `is_deleted` (BOOLEAN) - Soft delete flag

### workflow_runs table
- `id` (UUID) - Run ID
- `workflow_id` (UUID) - Foreign key
- `tenant_id` (UUID) - Tenant isolation
- `status` (VARCHAR) - pending/running/success/failed/timeout
- `trigger_data` (JSONB) - Input data
- `execution_log` (JSONB) - Step-by-step log
- `started_at`, `ended_at` - Timestamps
- `error_message` (TEXT) - Failure details
- `duration_ms` (INTEGER) - Execution time
- `retry_count` (INTEGER) - Retry counter

### workflow_versions table
- `id` (UUID) - Version ID
- `workflow_id` (UUID) - Foreign key
- `tenant_id` (UUID) - Tenant isolation
- `version` (INTEGER) - Version number
- `trigger` (JSONB) - Trigger at version
- `nodes` (JSONB) - Nodes at version
- `created_at` - Timestamp
- `created_by` (UUID) - Modifier

## Technologies Used

- **Framework:** FastAPI 0.x
- **Database:** PostgreSQL with asyncpg
- **Authentication:** PyJWT with HTTPBearer
- **HTTP Client:** httpx (async)
- **Validation:** Pydantic
- **Server:** Uvicorn
- **Logging:** Python logging module
- **Scheduling:** croniter (for time-based triggers)

## Environment Setup

```bash
# Database
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=workflows_db
export DB_USER=postgres
export DB_PASSWORD=postgres

# Authentication
export JWT_SECRET=your-secret-key-here

# CORS
export CORS_ORIGINS=http://localhost:3000,http://localhost:8080

# Server
export PORT=9034
export HOST=0.0.0.0
```

## Running the Service

```bash
# Install dependencies
pip install fastapi uvicorn asyncpg pyjwt httpx croniter

# Run the service
python main.py

# Or with uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 9034
```

## Example Usage

### Create a Workflow
```bash
curl -X POST http://localhost:9034/workflows \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "New Lead Notification",
    "description": "Send notification when lead is created",
    "trigger": {
      "type": "lead_created",
      "next_node_id": "action-1"
    },
    "nodes": [
      {
        "id": "action-1",
        "type": "action",
        "config": {
          "action_type": "send_message",
          "channel": "email",
          "message": "New lead received"
        }
      }
    ]
  }'
```

### Activate a Workflow
```bash
curl -X POST http://localhost:9034/workflows/{workflow_id}/activate \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

### Execute Workflow
```bash
curl -X POST http://localhost:9034/workflows/{workflow_id}/execute \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "trigger_data": {
      "lead_id": "123",
      "name": "John Doe",
      "email": "john@example.com"
    }
  }'
```

### Get Analytics
```bash
curl http://localhost:9034/workflows/analytics \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

## Error Handling

- **401 Unauthorized** - Invalid or expired JWT token
- **404 Not Found** - Workflow or run not found
- **500 Internal Server Error** - Database or execution errors
- Comprehensive error logging with stack traces

## Logging

The service implements structured logging with:
- Timestamp
- Component name
- Log level
- Message
- Stack traces on errors

Example log output:
```
2026-03-06 10:30:45 - root - INFO - Workflow created: workflow-id by user-id
2026-03-06 10:30:46 - root - INFO - Starting workflow execution for tenant tenant-id
2026-03-06 10:30:46 - root - INFO - Action SEND_MESSAGE: channel=email, recipient=user@example.com
```

## Performance Considerations

- Connection pool: 5-20 connections
- Query timeout: 60 seconds
- Execution timeout: 3600 seconds (configurable per run)
- Maximum workflow iterations: 100 (prevents infinite loops)
- Async/await for non-blocking I/O
- Indexed queries for tenant_id and workflow_id

## Testing the Service

```bash
# Health check
curl http://localhost:9034/workflows/health

# Expected response:
{
  "status": "healthy",
  "service": "Automation Workflows Engine",
  "database": "healthy",
  "timestamp": "2026-03-06T10:30:45.123456",
  "version": "1.0.0"
}
```

## Implementation Highlights

1. **Complete DAG Support** - Proper node traversal with condition evaluation
2. **Comprehensive Logging** - Every node execution is logged with details
3. **Error Resilience** - Graceful error handling and timeout protection
4. **Multi-Tenant Security** - Complete data isolation at database level
5. **JWT Authentication** - Secure token-based authentication
6. **Version History** - Full workflow version tracking
7. **Analytics** - Real-time execution metrics
8. **Soft Deletes** - Non-destructive deletion for data recovery

---

Built with FastAPI & PostgreSQL | Multi-tenant SaaS Ready | 1142 Lines
