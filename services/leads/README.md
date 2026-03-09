# Lead Scoring & Sales Pipeline Service

A comprehensive multi-tenant SaaS service for lead management, scoring, and sales pipeline automation built with FastAPI and asyncpg.

## Features

### 1. AI-Powered Lead Scoring Engine
- **Multi-factor scoring**: Engagement, demographics, behavior, intent signals
- **Configurable rules**: Per-tenant scoring configurations
- **Auto-decay**: Weekly score decay for inactive leads
- **Score history**: Complete audit trail of score changes
- **Lead grades**: Automatic assignment (A/B/C/D/F)

### 2. Sales Pipeline Management
- **Configurable stages**: Per-tenant pipeline stages
- **Stage gates**: Conditions to advance between stages
- **Velocity tracking**: Time spent in each stage
- **Deal tracking**: Value and win probability weighting
- **Revenue forecasting**: Based on weighted pipeline

### 3. Lead Lifecycle Management
- **Multi-channel creation**: WhatsApp, Email, Web, Phone, Referral, LinkedIn
- **Lead assignment**: Manual, round-robin, skills-based, territory
- **Nurturing sequences**: Automated follow-ups (extensible)
- **Conversion tracking**: Track conversions through pipeline
- **Duplicate detection**: Email, phone, or name-based matching

### 4. Pipeline Analytics
- **Conversion rates**: By stage analysis
- **Win/loss analysis**: Across pipeline stages
- **Cycle time**: Average time in each stage
- **Revenue forecast**: Weighted by probability
- **Agent performance**: By pipeline activity

## Environment Variables

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=leads_db
DB_USER=postgres
DB_PASSWORD=<secret>

# JWT
JWT_SECRET=<your-jwt-secret>

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

## Database Schema

```sql
-- Leads table
CREATE TABLE leads (
    lead_id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    phone VARCHAR,
    company VARCHAR,
    current_score FLOAT DEFAULT 0,
    lead_grade VARCHAR DEFAULT 'F',
    pipeline_stage VARCHAR DEFAULT 'New',
    source_channel VARCHAR NOT NULL,
    assigned_to VARCHAR,
    deal_value FLOAT,
    win_probability FLOAT,
    custom_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
CREATE INDEX idx_leads_tenant_id ON leads(tenant_id);
CREATE INDEX idx_leads_email_tenant ON leads(email, tenant_id);
CREATE INDEX idx_leads_stage_tenant ON leads(pipeline_stage, tenant_id);

-- Lead score history
CREATE TABLE lead_score_history (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR NOT NULL,
    tenant_id VARCHAR NOT NULL,
    score FLOAT NOT NULL,
    grade VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
CREATE INDEX idx_score_history_lead ON lead_score_history(lead_id);

-- Lead activity tracking
CREATE TABLE lead_activity (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR NOT NULL,
    tenant_id VARCHAR NOT NULL,
    activity_type VARCHAR NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
CREATE INDEX idx_activity_lead ON lead_activity(lead_id);

-- Pipeline configuration
CREATE TABLE pipeline_config (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR NOT NULL UNIQUE,
    stage_name VARCHAR NOT NULL,
    order_index INT NOT NULL,
    stage_gate_requirements JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
```

## API Endpoints

### Lead Management
- `POST /api/v1/leads` - Create lead
- `GET /api/v1/leads` - List leads (with filters, pagination)
- `GET /api/v1/leads/{lead_id}` - Get lead detail
- `PUT /api/v1/leads/{lead_id}` - Update lead
- `POST /api/v1/leads/deduplicate` - Find duplicates
- `GET /api/v1/leads/health` - Health check

### Scoring
- `POST /api/v1/leads/{lead_id}/score` - Recalculate score
- `GET /api/v1/leads/{lead_id}/score-history` - Get score history

### Pipeline
- `POST /api/v1/leads/{lead_id}/advance` - Advance stage
- `POST /api/v1/leads/assign` - Assign to agent
- `GET /api/v1/pipeline/stages` - Get pipeline config
- `PUT /api/v1/pipeline/stages` - Configure pipeline
- `GET /api/v1/pipeline/analytics` - Pipeline analytics
- `GET /api/v1/pipeline/forecast` - Revenue forecast

## Authentication

All endpoints require JWT authentication via `Authorization: Bearer <token>` header.

Token payload must include:
- `sub`: user_id
- `tenant_id`: tenant_id
- `email`: user_email

## Scoring Algorithm

Composite score calculated as:
- Engagement: 30%
- Demographics: 25%
- Behavior: 25%
- Intent: 20%
- Custom factors: up to 10%

Grade assignment:
- A: 90-100
- B: 75-89
- C: 50-74
- D: 25-49
- F: 0-24

## Service Architecture

- **Async/await**: All database operations are non-blocking
- **Connection pooling**: asyncpg connection pool for efficiency
- **Tenant isolation**: RLS via tenant_id in all queries
- **Error handling**: Comprehensive exception handling with logging
- **Input validation**: Pydantic models with validators
- **Security**: JWT auth, parameterized queries, CORS

## Running the Service

```bash
# Install dependencies
pip install fastapi uvicorn asyncpg pyjwt python-multipart

# Run the service
python main.py

# Service runs on http://localhost:9027
```

## Example Usage

### Create a Lead
```bash
curl -X POST http://localhost:9027/api/v1/leads \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "company": "Acme Corp",
    "source_channel": "web"
  }'
```

### Recalculate Score
```bash
curl -X POST http://localhost:9027/api/v1/leads/{lead_id}/score \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "engagement_score": 85,
    "demographic_score": 75,
    "behavior_score": 80,
    "intent_score": 90
  }'
```

### Get Pipeline Analytics
```bash
curl -X GET http://localhost:9027/api/v1/pipeline/analytics \
  -H "Authorization: Bearer <token>"
```

## Notes

- All timestamps are in UTC
- Lead IDs are generated as `lead_{timestamp}_{tenant_id}`
- Database queries use parameterized statements to prevent SQL injection
- All secrets must be provided via environment variables
- Service handles concurrent requests with asyncpg connection pooling
