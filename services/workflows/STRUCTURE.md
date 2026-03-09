# Code Structure Overview

## File: main.py (1142 lines)

### Section 1: Imports & Setup (Lines 1-25)
- FastAPI, async components
- Database: asyncpg
- Authentication: JWT, HTTPBearer
- HTTP Client: httpx
- Validation: Pydantic
- Logging configuration

### Section 2: Enums (Lines 27-60)
- WorkflowTriggerType (7 trigger types)
- WorkflowActionType (8 action types)
- WorkflowConditionType (4 condition types)
- WorkflowState (3 states)
- ExecutionStatus (5 statuses)

### Section 3: Pydantic Models (Lines 62-125)
- AuthContext - JWT payload
- WorkflowNode - DAG node
- WorkflowDefinition - Complete workflow
- CreateWorkflowRequest - API request model
- ExecuteWorkflowRequest - Execution request
- WorkflowRun - Execution run details
- WorkflowAnalytics - Analytics model
- UpdateWorkflowRequest - Update request model

### Section 4: Database Functions (Lines 127-175)
- get_db() - Connection pool getter
- get_auth_context() - JWT validation & extraction
- initialize_db() - Pool setup & table creation
- close_db() - Connection cleanup
- lifespan() - App lifecycle context manager

### Section 5: Core Engine (Lines 177-300)
- evaluate_condition() - Condition logic evaluation
  - Field comparison (equals, contains, greater_than, etc.)
  - Time conditions
  - Channel type checks
  - IF/ELSE branching

- execute_node() - Single node execution
  - Action execution (send, update, create, email, webhook, AI, assign, tag)
  - Condition evaluation
  - Delay handling
  - Branch processing
  - Comprehensive logging

- execute_workflow() - Complete workflow execution
  - DAG traversal
  - Timeout protection
  - Node iteration limit (100)
  - Status tracking
  - Error handling

### Section 6: FastAPI App Setup (Lines 302-320)
- App initialization
- CORS middleware configuration
- Lifespan context manager

### Section 7: Workflow CRUD Endpoints (Lines 322-450)

**POST /workflows** (Lines 322-350)
- Create new workflow
- Version 1 initialization
- Soft history tracking
- Status: 201 Created

**GET /workflows** (Lines 352-380)
- List all workflows
- Pagination support
- Optional state filtering
- Tenant RLS

**GET /workflows/{workflow_id}** (Lines 382-400)
- Get workflow details
- Full definition retrieval
- JSON deserialization

**PUT /workflows/{workflow_id}** (Lines 402-435)
- Update workflow
- Version increment
- History tracking
- Soft deletes respected

**DELETE /workflows/{workflow_id}** (Lines 437-450)
- Soft delete workflow
- Updated timestamp
- Tenant RLS

### Section 8: Workflow State Endpoints (Lines 452-490)

**POST /workflows/{workflow_id}/activate** (Lines 452-470)
- Change state to ACTIVE
- Workflow ready for execution
- Timestamp update

**POST /workflows/{workflow_id}/pause** (Lines 472-490)
- Change state to PAUSED
- Pause active workflows
- Timestamp update

### Section 9: Execution Endpoints (Lines 492-570)

**POST /workflows/{workflow_id}/execute** (Lines 492-550)
- Manual workflow trigger
- Full execution
- Logging to workflow_runs
- Response with execution_log

**GET /workflows/{workflow_id}/runs** (Lines 552-570)
- List workflow runs
- Status filtering
- Pagination

### Section 10: Run Details & Triggering (Lines 572-680)

**GET /workflows/{workflow_id}/runs/{run_id}** (Lines 572-600)
- Get full run details
- Execution log retrieval
- Error message inspection

**POST /workflows/trigger** (Lines 602-680)
- Event-based workflow trigger
- Matches by trigger type
- Activates all matching workflows
- Batch execution
- Comprehensive run tracking

### Section 11: Analytics & Health (Lines 682-750)

**GET /workflows/analytics** (Lines 682-730)
- Success rate calculation
- Total runs count
- Failure/timeout tracking
- Average execution time
- Optional workflow filtering

**GET /workflows/health** (Lines 732-750)
- Database connectivity test
- Service status
- Version info
- Timestamp

### Section 12: Entry Point (Lines 1140-1142)
- Uvicorn server startup
- Environment variable configuration
- Port 9034 default

## Key Features by Line Range

| Feature | Lines | Description |
|---------|-------|-------------|
| Authentication | 140-160 | JWT validation with HTTPBearer |
| Database Init | 162-230 | Pool + 3 tables + indexes |
| Condition Eval | 280-330 | 4 condition types with operators |
| Node Execution | 332-410 | 8 action types + logging |
| Workflow Engine | 412-480 | DAG traversal + timeout |
| CRUD Ops | 495-570 | Create, read, update, delete |
| State Management | 572-610 | Draft/Active/Paused |
| Event Triggering | 612-700 | Event-based activation |
| Analytics | 702-750 | Metrics & statistics |
| Health Check | 752-760 | Monitoring |

## Database Schema (Auto-Created)

```sql
-- Main workflow definitions
workflows (
  id UUID PK,
  tenant_id UUID (RLS),
  name VARCHAR(255),
  description TEXT,
  trigger JSONB,
  nodes JSONB,
  state VARCHAR(50),
  version INTEGER,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  created_by UUID,
  is_deleted BOOLEAN
)

-- Execution history
workflow_runs (
  id UUID PK,
  workflow_id UUID FK,
  tenant_id UUID (RLS),
  status VARCHAR(50),
  trigger_data JSONB,
  execution_log JSONB,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  error_message TEXT,
  duration_ms INTEGER,
  retry_count INTEGER
)

-- Version history
workflow_versions (
  id UUID PK,
  workflow_id UUID FK,
  tenant_id UUID (RLS),
  version INTEGER,
  trigger JSONB,
  nodes JSONB,
  created_at TIMESTAMP,
  created_by UUID
)
```

## Async/Await Pattern

- All database operations: `await db.execute()`, `await db.fetch()`
- HTTP calls: `async with httpx.AsyncClient()`
- Delays: `await asyncio.sleep()`
- Timeouts: `asyncio.wait_for()`
- Connection pool: async context manager

## Error Handling

- HTTP 401: Invalid JWT
- HTTP 404: Resource not found
- HTTP 400: Bad request (missing fields)
- HTTP 500: Database/execution errors
- All caught exceptions logged with traceback

## Tenant Isolation

Every query includes `tenant_id` filtering:
```python
WHERE tenant_id = $1 AND ...  # All queries
```

No cross-tenant data leakage possible due to:
- Parameter binding
- Explicit WHERE clauses
- Indexed on (tenant_id, ...)

## Secrets Management

No hardcoded values. All from environment:
- `JWT_SECRET` - Token signing key
- `DB_*` - Database credentials (5 vars)
- `CORS_ORIGINS` - Client origins
- `PORT`, `HOST` - Server binding

## Response Format

All endpoints return JSON with consistent structure:
```json
{
  "field": "value",
  "error": "optional error message",
  "timestamp": "ISO8601"
}
```

## Logging Format

```
TIMESTAMP - MODULE - LEVEL - MESSAGE
2026-03-06 10:30:45 - root - INFO - Workflow created: id by user
```

Every significant operation logged:
- Workflow creation/update/delete
- Execution start/end
- Action execution
- Condition evaluation
- Error events
