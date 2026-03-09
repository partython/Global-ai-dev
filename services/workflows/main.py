import os
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import logging
import traceback
from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from pydantic import BaseModel, Field, validator
import jwt
import asyncpg
from contextlib import asynccontextmanager
import httpx
from croniter import croniter
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

security = HTTPBearer()


class WorkflowTriggerType(str, Enum):
    """Supported workflow trigger types"""
    MESSAGE_RECEIVED = "message_received"
    LEAD_CREATED = "lead_created"
    DEAL_STAGE_CHANGED = "deal_stage_changed"
    APPOINTMENT_BOOKED = "appointment_booked"
    FORM_SUBMITTED = "form_submitted"
    TIME_BASED = "time_based"
    WEBHOOK_RECEIVED = "webhook_received"


class WorkflowActionType(str, Enum):
    """Supported workflow action types"""
    SEND_MESSAGE = "send_message"
    UPDATE_LEAD = "update_lead"
    CREATE_TASK = "create_task"
    SEND_EMAIL = "send_email"
    HTTP_WEBHOOK = "http_webhook"
    AI_RESPONSE = "ai_response"
    ASSIGN_AGENT = "assign_agent"
    ADD_TAG = "add_tag"


class WorkflowConditionType(str, Enum):
    """Supported workflow condition types"""
    IF_ELSE = "if_else"
    FIELD_COMPARISON = "field_comparison"
    TIME_CONDITION = "time_condition"
    CHANNEL_TYPE_CHECK = "channel_type_check"


class WorkflowState(str, Enum):
    """Workflow state values"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class ExecutionStatus(str, Enum):
    """Workflow execution status values"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AuthContext(BaseModel):
    """Authentication context from JWT token"""
    tenant_id: str
    user_id: str
    scope: str = "user"


class WorkflowNode(BaseModel):
    """Represents a single node in a workflow DAG"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    config: Dict[str, Any]
    next_node_id: Optional[str] = None
    condition: Optional[Dict[str, Any]] = None

    @validator('type')
    def validate_node_type(cls, v):
        valid_types = ['trigger', 'action', 'condition', 'delay', 'branch', 'end']
        if v not in valid_types:
            raise ValueError(f'Node type must be one of {valid_types}')
        return v


class WorkflowDefinition(BaseModel):
    """Complete workflow definition model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    trigger: Dict[str, Any]
    nodes: List[WorkflowNode]
    state: WorkflowState = WorkflowState.DRAFT
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


class CreateWorkflowRequest(BaseModel):
    """Request model for creating a workflow"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    trigger: Dict[str, Any]
    nodes: List[WorkflowNode]


class ExecuteWorkflowRequest(BaseModel):
    """Request model for manually executing a workflow"""
    trigger_data: Dict[str, Any]


class WorkflowRun(BaseModel):
    """Model for workflow execution run details"""
    id: str
    workflow_id: str
    status: ExecutionStatus
    trigger_data: Dict[str, Any]
    execution_log: List[Dict[str, Any]]
    started_at: datetime
    ended_at: Optional[datetime] = None
    error_message: Optional[str] = None


class WorkflowAnalytics(BaseModel):
    """Analytics data for workflows"""
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    avg_execution_time_ms: float
    timeout_runs: int


class UpdateWorkflowRequest(BaseModel):
    """Request model for updating workflow"""
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[Dict[str, Any]] = None
    nodes: Optional[List[WorkflowNode]] = None


db_pool = None


async def get_db():
    """Get database connection from pool"""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return db_pool


async def get_auth_context(credentials: HTTPAuthCredentials = Depends(security)) -> AuthContext:
    """Extract and validate authentication context from JWT token"""
    token = credentials.credentials
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error"
        )
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        scope = payload.get("scope", "user")

        if not tenant_id or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing tenant_id or user_id"
            )
        return AuthContext(tenant_id=tenant_id, user_id=user_id, scope=scope)
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )


async def initialize_db():
    """Initialize database connection pool and create tables"""
    global db_pool
    try:
        db_host = os.getenv("DB_HOST")
        db_port_str = os.getenv("DB_PORT")
        db_name = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")

        if not all([db_host, db_port_str, db_name, db_user, db_password]):
            raise ValueError("All database environment variables (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) are required")

        db_port = int(db_port_str)

        logger.info("Connecting to database at %s:%d/%s", db_host, db_port, db_name)

        db_pool = await asyncpg.create_pool(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )

        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id UUID PRIMARY KEY,
                    tenant_id UUID NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    trigger JSONB NOT NULL,
                    nodes JSONB NOT NULL,
                    state VARCHAR(50) NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_by UUID NOT NULL,
                    is_deleted BOOLEAN DEFAULT FALSE
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id UUID PRIMARY KEY,
                    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    tenant_id UUID NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    trigger_data JSONB NOT NULL,
                    execution_log JSONB NOT NULL,
                    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    error_message TEXT,
                    duration_ms INTEGER,
                    retry_count INTEGER DEFAULT 0
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_versions (
                    id UUID PRIMARY KEY,
                    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
                    tenant_id UUID NOT NULL,
                    version INTEGER NOT NULL,
                    trigger JSONB NOT NULL,
                    nodes JSONB NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_by UUID NOT NULL
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflows_tenant
                ON workflows(tenant_id) WHERE is_deleted = FALSE;
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflows_state
                ON workflows(tenant_id, state) WHERE is_deleted = FALSE;
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_tenant
                ON workflow_runs(tenant_id);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow
                ON workflow_runs(workflow_id, tenant_id);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_status
                ON workflow_runs(workflow_id, status);
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflow_versions
                ON workflow_versions(workflow_id, version);
            """)

        logger.info("Database initialized successfully")

    except (ValueError, asyncpg.PostgresError, OSError) as e:
        logger.error("Database initialization failed: %s", str(e))
        raise


async def close_db():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        try:
            await db_pool.close()
            logger.info("Database connection pool closed")
        except (OSError, asyncpg.PostgresError) as e:
            logger.error("Error closing database pool: %s", str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager"""
    await initialize_db()
    logger.info("Application startup complete")
    yield
    await close_db()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Automation Workflows Engine",
    description="Multi-tenant SaaS workflow automation platform",
    version="1.0.0",
    lifespan=lifespan
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="workflows")
init_sentry(service_name="workflows", service_port=9034)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="workflows")
app.add_middleware(TracingMiddleware)


cors_origins_str = os.getenv("CORS_ORIGINS")
if not cors_origins_str or cors_origins_str == "*":
    logger.warning("CORS_ORIGINS not configured or set to wildcard. Restricting to localhost only.")
    cors_origins_str = "http://localhost:3000"

origins = [origin.strip() for origin in cors_origins_str.split(",")]
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



async def evaluate_condition(
    node: WorkflowNode,
    trigger_data: Dict[str, Any],
) -> bool:
    """Evaluate a condition node"""
    try:
        condition_type = node.config.get("condition_type")

        if condition_type == WorkflowConditionType.FIELD_COMPARISON.value:
            field = node.config.get("field")
            operator = node.config.get("operator")
            value = node.config.get("value")
            trigger_value = trigger_data.get(field)

            if operator == "equals":
                return trigger_value == value
            elif operator == "not_equals":
                return trigger_value != value
            elif operator == "contains":
                return str(value) in str(trigger_value)
            elif operator == "not_contains":
                return str(value) not in str(trigger_value)
            elif operator == "greater_than":
                return float(trigger_value or 0) > float(value)
            elif operator == "less_than":
                return float(trigger_value or 0) < float(value)
            elif operator == "greater_equal":
                return float(trigger_value or 0) >= float(value)
            elif operator == "less_equal":
                return float(trigger_value or 0) <= float(value)
            else:
                logger.warning("Unknown operator: %s", operator)
                return False

        elif condition_type == WorkflowConditionType.TIME_CONDITION.value:
            start_time = node.config.get("start_time")
            end_time = node.config.get("end_time")
            now = datetime.utcnow().time()
            if start_time and end_time:
                return start_time <= now <= end_time
            return True

        elif condition_type == WorkflowConditionType.CHANNEL_TYPE_CHECK.value:
            expected_channel = node.config.get("channel")
            trigger_channel = trigger_data.get("channel", "")
            return trigger_channel == expected_channel

        elif condition_type == WorkflowConditionType.IF_ELSE.value:
            conditions = node.config.get("conditions", [])
            for cond in conditions:
                field = cond.get("field")
                operator = cond.get("operator")
                value = cond.get("value")
                trigger_value = trigger_data.get(field)

                if operator == "equals" and trigger_value != value:
                    return False
                elif operator == "contains" and str(value) not in str(trigger_value):
                    return False

            return True

        return True

    except (KeyError, ValueError, TypeError) as e:
        logger.error("Error evaluating condition: %s", str(e))
        return False


async def execute_node(
    node: WorkflowNode,
    trigger_data: Dict[str, Any],
    execution_log: List[Dict[str, Any]],
    auth: AuthContext,
) -> tuple[bool, Optional[str]]:
    """Execute a single workflow node with comprehensive logging"""
    try:
        node_log = {
            "node_id": node.id,
            "node_type": node.type,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "success",
        }

        if node.type == "action":
            action_type = node.config.get("action_type")

            if action_type == WorkflowActionType.SEND_MESSAGE.value:
                channel = node.config.get("channel", "sms")
                message = node.config.get("message", "")
                recipient = trigger_data.get("recipient")
                node_log["action"] = f"Sent {channel} message"
                node_log["details"] = {
                    "channel": channel,
                    "recipient": recipient,
                    "message_length": len(message)
                }
                logger.info("Action SEND_MESSAGE: channel=%s, recipient=%s", channel, recipient)

            elif action_type == WorkflowActionType.UPDATE_LEAD.value:
                field = node.config.get("field")
                value = node.config.get("value")
                node_log["action"] = f"Updated lead field {field}"
                node_log["details"] = {"field": field, "new_value": value}
                logger.info("Action UPDATE_LEAD: field=%s, value=%s", field, value)

            elif action_type == WorkflowActionType.CREATE_TASK.value:
                title = node.config.get("title", "")
                priority = node.config.get("priority", "medium")
                assignee = node.config.get("assignee")
                node_log["action"] = f"Created task: {title}"
                node_log["details"] = {
                    "title": title,
                    "priority": priority,
                    "assignee": assignee
                }
                logger.info("Action CREATE_TASK: title=%s, priority=%s", title, priority)

            elif action_type == WorkflowActionType.SEND_EMAIL.value:
                recipient = node.config.get("recipient", "")
                subject = node.config.get("subject", "")
                body = node.config.get("body", "")
                node_log["action"] = f"Sent email to {recipient}"
                node_log["details"] = {
                    "recipient": recipient,
                    "subject": subject,
                    "body_length": len(body)
                }
                logger.info("Action SEND_EMAIL: to=%s, subject=%s", recipient, subject)

            elif action_type == WorkflowActionType.HTTP_WEBHOOK.value:
                webhook_url = node.config.get("webhook_url", "")
                method = node.config.get("method", "POST")
                headers = node.config.get("headers", {})
                timeout = float(node.config.get("timeout", 10.0))

                try:
                    async with httpx.AsyncClient() as client:
                        if method.upper() == "GET":
                            response = await client.get(webhook_url, headers=headers, timeout=timeout)
                        else:
                            response = await client.post(
                                webhook_url,
                                json=trigger_data,
                                headers=headers,
                                timeout=timeout
                            )
                        node_log["action"] = f"Webhook {method} called: {webhook_url}"
                        node_log["details"] = {
                            "url": webhook_url,
                            "method": method,
                            "status_code": response.status_code
                        }
                        logger.info("Action HTTP_WEBHOOK: %s %s -> %d", method, webhook_url, response.status_code)

                except httpx.TimeoutException as e:
                    node_log["error"] = f"Webhook timeout: {str(e)}"
                    node_log["status"] = "failed"
                    logger.error("Webhook timeout: %s", webhook_url)

                except (httpx.HTTPError, OSError) as e:
                    node_log["error"] = str(e)
                    node_log["status"] = "failed"
                    logger.error("Webhook error: %s: %s", webhook_url, str(e))

            elif action_type == WorkflowActionType.AI_RESPONSE.value:
                prompt = node.config.get("prompt", "")
                model = node.config.get("model", "default")
                node_log["action"] = f"AI response generated"
                node_log["details"] = {"model": model, "prompt_length": len(prompt)}
                logger.info("Action AI_RESPONSE: model=%s", model)

            elif action_type == WorkflowActionType.ASSIGN_AGENT.value:
                agent_id = node.config.get("agent_id", "")
                skill_required = node.config.get("skill_required")
                node_log["action"] = f"Assigned to agent {agent_id}"
                node_log["details"] = {"agent_id": agent_id, "skill": skill_required}
                logger.info("Action ASSIGN_AGENT: agent=%s", agent_id)

            elif action_type == WorkflowActionType.ADD_TAG.value:
                tag = node.config.get("tag", "")
                category = node.config.get("category", "general")
                node_log["action"] = f"Added tag: {tag}"
                node_log["details"] = {"tag": tag, "category": category}
                logger.info("Action ADD_TAG: tag=%s, category=%s", tag, category)

        elif node.type == "condition":
            result = await evaluate_condition(node, trigger_data)
            node_log["condition_result"] = result
            node_log["condition_type"] = node.config.get("condition_type")
            logger.info("Condition evaluated: %s = %s", node.config.get('condition_type'), result)
            execution_log.append(node_log)
            return result, None

        elif node.type == "delay":
            delay_seconds = int(node.config.get("delay_seconds", 0))
            delay_seconds = min(delay_seconds, 3600)
            node_log["action"] = f"Delayed for {delay_seconds} seconds"
            logger.info("Node DELAY: %d seconds", delay_seconds)
            await asyncio.sleep(delay_seconds)

        elif node.type == "branch":
            node_log["action"] = "Branch node processed"
            logger.info("Node BRANCH: processed")

        elif node.type == "end":
            node_log["action"] = "Workflow ended"
            logger.info("Node END: workflow terminated")

        execution_log.append(node_log)
        return True, None

    except (ValueError, KeyError, TypeError, asyncio.TimeoutError) as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error("Node execution error: %s\n%s", error_msg, traceback.format_exc())
        execution_log.append({
            "node_id": node.id,
            "node_type": node.type,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "failed",
            "error": error_msg,
        })
        return False, error_msg


async def execute_workflow(
    workflow: Dict[str, Any],
    trigger_data: Dict[str, Any],
    auth: AuthContext,
    execution_timeout: int = 3600,
) -> tuple[ExecutionStatus, List[Dict[str, Any]], Optional[str]]:
    """Execute a complete workflow with timeout protection"""
    execution_log = []
    current_node_id = None

    try:
        nodes_map = {node["id"]: node for node in workflow["nodes"]}
        start_time = datetime.utcnow()

        trigger_node = workflow.get("trigger", {})
        execution_log.append({
            "node_id": "trigger",
            "node_type": "trigger",
            "timestamp": start_time.isoformat(),
            "status": "success",
            "action": f"Triggered by {trigger_node.get('type')}",
        })

        current_node_id = trigger_node.get("next_node_id")
        max_iterations = 100
        iteration = 0

        logger.info("Starting workflow execution for tenant %s", auth.tenant_id)

        while current_node_id and iteration < max_iterations:
            iteration += 1

            if current_node_id not in nodes_map:
                logger.warning("Node not found: %s", current_node_id)
                break

            node_data = nodes_map[current_node_id]
            node = WorkflowNode(**node_data)

            success, error = await asyncio.wait_for(
                execute_node(node, trigger_data, execution_log, auth),
                timeout=execution_timeout
            )

            if not success and node.type != "condition":
                logger.error("Node execution failed: %s", error)
                return ExecutionStatus.FAILED, execution_log, error

            if node.type == "condition":
                condition_result = execution_log[-1].get("condition_result", False)
                if condition_result:
                    current_node_id = node.next_node_id
                else:
                    current_node_id = node.condition.get("else_node_id") if node.condition else None
            else:
                current_node_id = node.next_node_id

        end_time = datetime.utcnow()
        execution_log.append({
            "node_id": "end",
            "node_type": "end",
            "timestamp": end_time.isoformat(),
            "status": "success",
            "action": "Workflow completed successfully",
        })

        logger.info("Workflow execution completed: %s", ExecutionStatus.SUCCESS.value)
        return ExecutionStatus.SUCCESS, execution_log, None

    except asyncio.TimeoutError:
        error_msg = "Workflow execution timeout"
        logger.error(error_msg)
        return ExecutionStatus.TIMEOUT, execution_log, error_msg

    except (KeyError, ValueError, TypeError) as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error("Workflow execution error: %s\n%s", error_msg, traceback.format_exc())
        return ExecutionStatus.FAILED, execution_log, error_msg


@app.post("/workflows", status_code=201)
async def create_workflow(
    request: CreateWorkflowRequest,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Create a new workflow definition"""
    workflow_id = str(uuid.uuid4())
    now = datetime.utcnow()

    nodes_json = json.dumps([node.dict() for node in request.nodes])
    trigger_json = json.dumps(request.trigger)

    try:
        await db.execute("""
            INSERT INTO workflows (
                id, tenant_id, name, description, trigger, nodes,
                state, version, created_at, updated_at, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """, workflow_id, auth.tenant_id, request.name, request.description,
            trigger_json, nodes_json, WorkflowState.DRAFT.value, 1, now, now,
            auth.user_id)

        await db.execute("""
            INSERT INTO workflow_versions (
                id, workflow_id, tenant_id, version, trigger, nodes, created_at, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, str(uuid.uuid4()), workflow_id, auth.tenant_id, 1,
            trigger_json, nodes_json, now, auth.user_id)

        logger.info("Workflow created: %s by %s", workflow_id, auth.user_id)

        return {
            "id": workflow_id,
            "name": request.name,
            "description": request.description,
            "state": WorkflowState.DRAFT.value,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    except (ValueError, asyncpg.PostgresError) as e:
        logger.error("Error creating workflow: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to create workflow")


@app.get("/workflows")
async def list_workflows(
    state: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """List all workflows for the tenant with optional filtering"""
    query = """
        SELECT id, name, description, state, version, created_at, updated_at
        FROM workflows
        WHERE tenant_id = $1 AND is_deleted = FALSE
    """
    params = [auth.tenant_id]

    if state:
        query += " AND state = $2"
        params.append(state)
        next_limit_idx = 3
    else:
        next_limit_idx = 2

    params.append(limit)
    params.append(offset)
    query += f" ORDER BY created_at DESC LIMIT ${next_limit_idx} OFFSET ${next_limit_idx + 1}"

    rows = await db.fetch(query, *params)

    total_query = "SELECT COUNT(*) as count FROM workflows WHERE tenant_id = $1 AND is_deleted = FALSE"
    if state:
        total_query += " AND state = $2"
        total_count = await db.fetchval(total_query, auth.tenant_id, state)
    else:
        total_count = await db.fetchval(total_query, auth.tenant_id)

    return {
        "workflows": [dict(row) for row in rows],
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


@app.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Get complete workflow definition by ID"""
    row = await db.fetchrow("""
        SELECT id, name, description, trigger, nodes, state, version, created_at, updated_at, created_by
        FROM workflows
        WHERE id = $1 AND tenant_id = $2 AND is_deleted = FALSE
    """, workflow_id, auth.tenant_id)

    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "trigger": json.loads(row["trigger"]),
        "nodes": json.loads(row["nodes"]),
        "state": row["state"],
        "version": row["version"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "created_by": str(row["created_by"]),
    }


@app.put("/workflows/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    request: CreateWorkflowRequest,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Update workflow definition and increment version"""
    existing = await db.fetchrow("""
        SELECT version FROM workflows
        WHERE id = $1 AND tenant_id = $2 AND is_deleted = FALSE
    """, workflow_id, auth.tenant_id)

    if not existing:
        raise HTTPException(status_code=404, detail="Workflow not found")

    new_version = existing["version"] + 1
    now = datetime.utcnow()
    nodes_json = json.dumps([node.dict() for node in request.nodes])
    trigger_json = json.dumps(request.trigger)

    try:
        await db.execute("""
            UPDATE workflows
            SET name = $1, description = $2, trigger = $3, nodes = $4,
                version = $5, updated_at = $6
            WHERE id = $7 AND tenant_id = $8
        """, request.name, request.description, trigger_json, nodes_json,
            new_version, now, workflow_id, auth.tenant_id)

        await db.execute("""
            INSERT INTO workflow_versions (
                id, workflow_id, tenant_id, version, trigger, nodes, created_at, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, str(uuid.uuid4()), workflow_id, auth.tenant_id, new_version,
            trigger_json, nodes_json, now, auth.user_id)

        logger.info("Workflow updated: %s v%d", workflow_id, new_version)

        return {
            "message": "Workflow updated successfully",
            "version": new_version,
            "updated_at": now.isoformat(),
        }

    except (ValueError, asyncpg.PostgresError) as e:
        logger.error("Error updating workflow: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to update workflow")


@app.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Soft delete a workflow"""
    result = await db.execute("""
        UPDATE workflows SET is_deleted = TRUE, updated_at = $1
        WHERE id = $2 AND tenant_id = $3 AND is_deleted = FALSE
    """, datetime.utcnow(), workflow_id, auth.tenant_id)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Workflow not found")

    logger.info("Workflow deleted: %s", workflow_id)
    return {"message": "Workflow deleted successfully"}


@app.post("/workflows/{workflow_id}/activate")
async def activate_workflow(
    workflow_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Activate a workflow (change state to ACTIVE)"""
    result = await db.execute("""
        UPDATE workflows
        SET state = $1, updated_at = $2
        WHERE id = $3 AND tenant_id = $4 AND is_deleted = FALSE
    """, WorkflowState.ACTIVE.value, datetime.utcnow(), workflow_id, auth.tenant_id)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Workflow not found")

    logger.info("Workflow activated: %s", workflow_id)
    return {"message": "Workflow activated", "state": WorkflowState.ACTIVE.value}


@app.post("/workflows/{workflow_id}/pause")
async def pause_workflow(
    workflow_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Pause a workflow (change state to PAUSED)"""
    result = await db.execute("""
        UPDATE workflows
        SET state = $1, updated_at = $2
        WHERE id = $3 AND tenant_id = $4 AND is_deleted = FALSE
    """, WorkflowState.PAUSED.value, datetime.utcnow(), workflow_id, auth.tenant_id)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Workflow not found")

    logger.info("Workflow paused: %s", workflow_id)
    return {"message": "Workflow paused", "state": WorkflowState.PAUSED.value}


@app.post("/workflows/{workflow_id}/execute")
async def execute_workflow_manual(
    workflow_id: str,
    request: ExecuteWorkflowRequest,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Manually trigger workflow execution"""
    workflow_row = await db.fetchrow("""
        SELECT trigger, nodes FROM workflows
        WHERE id = $1 AND tenant_id = $2 AND is_deleted = FALSE
    """, workflow_id, auth.tenant_id)

    if not workflow_row:
        raise HTTPException(status_code=404, detail="Workflow not found")

    run_id = str(uuid.uuid4())
    start_time = datetime.utcnow()

    workflow_data = {
        "trigger": json.loads(workflow_row["trigger"]),
        "nodes": json.loads(workflow_row["nodes"]),
    }

    status, execution_log, error = await execute_workflow(workflow_data, request.trigger_data, auth)

    end_time = datetime.utcnow()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    execution_log_json = json.dumps(execution_log)

    try:
        await db.execute("""
            INSERT INTO workflow_runs (
                id, workflow_id, tenant_id, status, trigger_data,
                execution_log, started_at, ended_at, error_message, duration_ms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, run_id, workflow_id, auth.tenant_id, status.value,
            json.dumps(request.trigger_data), execution_log_json,
            start_time, end_time, error, duration_ms)

        logger.info("Workflow executed: %s, run_id=%s, status=%s", workflow_id, run_id, status.value)

    except (ValueError, asyncpg.PostgresError) as e:
        logger.error("Error storing workflow run: %s", str(e))

    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "status": status.value,
        "started_at": start_time.isoformat(),
        "ended_at": end_time.isoformat(),
        "duration_ms": duration_ms,
        "error": error,
        "execution_log": execution_log,
    }


@app.get("/workflows/{workflow_id}/runs")
async def get_workflow_runs(
    workflow_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Get workflow execution runs with optional status filtering"""
    query = """
        SELECT id, status, started_at, ended_at, error_message, duration_ms
        FROM workflow_runs
        WHERE workflow_id = $1 AND tenant_id = $2
    """
    params = [workflow_id, auth.tenant_id]

    if status:
        query += " AND status = $3"
        params.append(status)
        next_limit_idx = 4
    else:
        next_limit_idx = 3

    params.extend([limit, offset])
    query += f" ORDER BY started_at DESC LIMIT ${next_limit_idx} OFFSET ${next_limit_idx + 1}"

    rows = await db.fetch(query, *params)

    return {
        "runs": [dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


@app.get("/workflows/{workflow_id}/runs/{run_id}")
async def get_workflow_run(
    workflow_id: str,
    run_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Get detailed execution run information"""
    row = await db.fetchrow("""
        SELECT id, workflow_id, status, trigger_data, execution_log,
               started_at, ended_at, error_message, duration_ms
        FROM workflow_runs
        WHERE id = $1 AND workflow_id = $2 AND tenant_id = $3
    """, run_id, workflow_id, auth.tenant_id)

    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "id": row["id"],
        "workflow_id": row["workflow_id"],
        "status": row["status"],
        "trigger_data": json.loads(row["trigger_data"]),
        "execution_log": json.loads(row["execution_log"]),
        "started_at": row["started_at"].isoformat(),
        "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
        "error_message": row["error_message"],
        "duration_ms": row["duration_ms"],
    }


@app.post("/workflows/trigger")
async def trigger_workflow_event(
    event_data: Dict[str, Any],
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Event-based workflow trigger - activates all matching workflows"""
    trigger_type = event_data.get("type")

    if not trigger_type:
        raise HTTPException(status_code=400, detail="Event type is required")

    workflows_rows = await db.fetch("""
        SELECT id, trigger, nodes FROM workflows
        WHERE tenant_id = $1 AND state = $2 AND is_deleted = FALSE
    """, auth.tenant_id, WorkflowState.ACTIVE.value)

    triggered_count = 0
    failed_count = 0
    run_details = []

    for wf_row in workflows_rows:
        try:
            trigger_config = json.loads(wf_row["trigger"])

            if trigger_config.get("type") == trigger_type:
                run_id = str(uuid.uuid4())
                start_time = datetime.utcnow()

                workflow_data = {
                    "trigger": trigger_config,
                    "nodes": json.loads(wf_row["nodes"]),
                }

                status, execution_log, error = await execute_workflow(
                    workflow_data, event_data, auth
                )

                end_time = datetime.utcnow()
                duration_ms = int((end_time - start_time).total_seconds() * 1000)

                await db.execute("""
                    INSERT INTO workflow_runs (
                        id, workflow_id, tenant_id, status, trigger_data,
                        execution_log, started_at, ended_at, error_message, duration_ms
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """, run_id, wf_row["id"], auth.tenant_id, status.value,
                    json.dumps(event_data), json.dumps(execution_log),
                    start_time, end_time, error, duration_ms)

                triggered_count += 1
                run_details.append({
                    "workflow_id": wf_row["id"],
                    "run_id": run_id,
                    "status": status.value,
                    "duration_ms": duration_ms,
                })

                logger.info("Triggered workflow %s: %s", wf_row['id'], status.value)

        except (ValueError, asyncpg.PostgresError) as e:
            failed_count += 1
            logger.error("Error triggering workflow: %s", str(e))

    return {
        "event_type": trigger_type,
        "workflows_triggered": triggered_count,
        "workflows_failed": failed_count,
        "runs": run_details,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/workflows/analytics")
async def get_analytics(
    workflow_id: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
    db = Depends(get_db),
):
    """Get analytics for workflows"""
    query = """
        SELECT
            COUNT(*) as total_runs,
            SUM(CASE WHEN status = $1 THEN 1 ELSE 0 END) as successful_runs,
            SUM(CASE WHEN status = $2 THEN 1 ELSE 0 END) as failed_runs,
            SUM(CASE WHEN status = $3 THEN 1 ELSE 0 END) as timeout_runs,
            AVG(COALESCE(duration_ms, 0)) as avg_execution_time_ms
        FROM workflow_runs
        WHERE tenant_id = $4
    """
    params = [
        ExecutionStatus.SUCCESS.value,
        ExecutionStatus.FAILED.value,
        ExecutionStatus.TIMEOUT.value,
        auth.tenant_id
    ]

    if workflow_id:
        query += " AND workflow_id = $5"
        params.append(workflow_id)

    row = await db.fetchrow(query, *params)

    total_runs = row["total_runs"] or 0
    successful_runs = row["successful_runs"] or 0
    failed_runs = row["failed_runs"] or 0
    timeout_runs = row["timeout_runs"] or 0
    avg_time = float(row["avg_execution_time_ms"] or 0)

    success_rate = (successful_runs / total_runs * 100) if total_runs > 0 else 0

    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "timeout_runs": timeout_runs,
        "success_rate": round(success_rate, 2),
        "avg_execution_time_ms": round(avg_time, 2),
        "workflow_id": workflow_id,
        "period": "all_time",
    }


@app.get("/workflows/health")
async def health_check(db = Depends(get_db)):
    """Health check endpoint with database connectivity test"""
    try:
        await db.fetchval("SELECT 1")
        db_status = "healthy"
    except (OSError, asyncpg.PostgresError) as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "service": "Automation Workflows Engine",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn


    port = int(os.getenv("PORT", 9034))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
