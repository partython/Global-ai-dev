# Lead Scoring & Sales Pipeline API Documentation

## Authentication

All endpoints (except health check) require a JWT token in the Authorization header:

```bash
Authorization: Bearer <jwt_token>
```

JWT payload must contain:
```json
{
  "sub": "user_id",
  "tenant_id": "tenant_id",
  "email": "user@example.com"
}
```

## Base URL

```
http://localhost:9027/api/v1
```

## Lead Management Endpoints

### Create Lead

```http
POST /leads
Content-Type: application/json
Authorization: Bearer <token>

{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "company": "Acme Corp",
  "source_channel": "web",
  "initial_score": 65.5,
  "custom_data": {
    "industry": "Technology",
    "employee_count": 500
  }
}
```

**Response (201 Created):**
```json
{
  "lead_id": "lead_1704067200.0_tenant123",
  "tenant_id": "tenant123",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "company": "Acme Corp",
  "current_score": 65.5,
  "lead_grade": "C",
  "pipeline_stage": "New",
  "source_channel": "web",
  "assigned_to": null,
  "deal_value": null,
  "win_probability": null,
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:00:00"
}
```

### List Leads

```http
GET /leads?skip=0&limit=20&grade=A&stage=Qualified&sort_by=created_at&order=desc
Authorization: Bearer <token>
```

**Query Parameters:**
- `skip` (int): Number of records to skip (default: 0)
- `limit` (int): Number of records to return (default: 20, max: 100)
- `grade` (string): Filter by lead grade (A/B/C/D/F)
- `stage` (string): Filter by pipeline stage
- `sort_by` (string): Sort field (created_at, current_score, pipeline_stage)
- `order` (string): Sort order (asc/desc)

**Response (200 OK):**
```json
{
  "total": 150,
  "skip": 0,
  "limit": 20,
  "leads": [
    {
      "lead_id": "lead_1704067200.0_tenant123",
      "tenant_id": "tenant123",
      "first_name": "John",
      "last_name": "Doe",
      "email": "john@example.com",
      "phone": "+1234567890",
      "company": "Acme Corp",
      "current_score": 65.5,
      "lead_grade": "C",
      "pipeline_stage": "New",
      "source_channel": "web",
      "assigned_to": "agent_001",
      "deal_value": 50000,
      "win_probability": 0.7,
      "created_at": "2024-01-01T12:00:00",
      "updated_at": "2024-01-01T12:00:00"
    }
  ]
}
```

### Get Lead Detail

```http
GET /leads/{lead_id}
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "lead_id": "lead_1704067200.0_tenant123",
  "tenant_id": "tenant123",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "+1234567890",
  "company": "Acme Corp",
  "current_score": 65.5,
  "lead_grade": "C",
  "pipeline_stage": "Qualified",
  "source_channel": "web",
  "assigned_to": "agent_001",
  "deal_value": 50000,
  "win_probability": 0.7,
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:30:00"
}
```

### Update Lead

```http
PUT /leads/{lead_id}
Content-Type: application/json
Authorization: Bearer <token>

{
  "first_name": "Jane",
  "phone": "+9876543210",
  "custom_data": {
    "industry": "Finance"
  }
}
```

**Response (200 OK):**
```json
{
  "lead_id": "lead_1704067200.0_tenant123",
  "tenant_id": "tenant123",
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "john@example.com",
  "phone": "+9876543210",
  "company": "Acme Corp",
  "current_score": 65.5,
  "lead_grade": "C",
  "pipeline_stage": "Qualified",
  "source_channel": "web",
  "assigned_to": "agent_001",
  "deal_value": 50000,
  "win_probability": 0.7,
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:31:00"
}
```

## Scoring Endpoints

### Recalculate Lead Score

```http
POST /leads/{lead_id}/score
Content-Type: application/json
Authorization: Bearer <token>

{
  "engagement_score": 85,
  "demographic_score": 75,
  "behavior_score": 80,
  "intent_score": 90,
  "custom_factors": {
    "referral_quality": 80,
    "partnership_fit": 75
  }
}
```

**Response (200 OK):**
```json
{
  "lead_id": "lead_1704067200.0_tenant123",
  "new_score": 82.5,
  "new_grade": "B",
  "timestamp": "2024-01-01T13:00:00"
}
```

### Get Score History

```http
GET /leads/{lead_id}/score-history?limit=50
Authorization: Bearer <token>
```

**Query Parameters:**
- `limit` (int): Maximum records to return (default: 50, max: 100)

**Response (200 OK):**
```json
{
  "lead_id": "lead_1704067200.0_tenant123",
  "history": [
    {
      "score": 82.5,
      "grade": "B",
      "timestamp": "2024-01-01T13:00:00"
    },
    {
      "score": 65.5,
      "grade": "C",
      "timestamp": "2024-01-01T12:00:00"
    }
  ]
}
```

## Pipeline Management Endpoints

### Advance Pipeline Stage

```http
POST /leads/{lead_id}/advance
Content-Type: application/json
Authorization: Bearer <token>

{
  "lead_id": "lead_1704067200.0_tenant123",
  "new_stage": "Proposal",
  "deal_value": 75000,
  "win_probability": 0.65
}
```

**Response (200 OK):**
```json
{
  "lead_id": "lead_1704067200.0_tenant123",
  "new_stage": "Proposal",
  "deal_value": 75000,
  "win_probability": 0.65,
  "timestamp": "2024-01-01T13:30:00"
}
```

### Assign Lead to Agent

```http
POST /leads/assign
Content-Type: application/json
Authorization: Bearer <token>

{
  "lead_id": "lead_1704067200.0_tenant123",
  "assigned_to": "agent_002",
  "assignment_method": "skills-based"
}
```

**Response (200 OK):**
```json
{
  "lead_id": "lead_1704067200.0_tenant123",
  "assigned_to": "agent_002",
  "timestamp": "2024-01-01T13:45:00"
}
```

### Get Pipeline Configuration

```http
GET /pipeline/stages
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "tenant_id": "tenant123",
  "stages": [
    {
      "stage_name": "New",
      "order": 1,
      "stage_gate_requirements": {}
    },
    {
      "stage_name": "Qualified",
      "order": 2,
      "stage_gate_requirements": {
        "min_score": 50
      }
    },
    {
      "stage_name": "Proposal",
      "order": 3,
      "stage_gate_requirements": {
        "requires_assignment": true
      }
    },
    {
      "stage_name": "Negotiation",
      "order": 4,
      "stage_gate_requirements": {}
    },
    {
      "stage_name": "Won",
      "order": 5,
      "stage_gate_requirements": {}
    },
    {
      "stage_name": "Lost",
      "order": 6,
      "stage_gate_requirements": {}
    }
  ]
}
```

### Configure Pipeline Stages

```http
PUT /pipeline/stages
Content-Type: application/json
Authorization: Bearer <token>

{
  "tenant_id": "tenant123",
  "stages": [
    {
      "stage_name": "New",
      "order": 1,
      "stage_gate_requirements": {}
    },
    {
      "stage_name": "Qualified",
      "order": 2,
      "stage_gate_requirements": {
        "min_score": 60,
        "required_fields": ["company", "phone"]
      }
    },
    {
      "stage_name": "Proposal",
      "order": 3,
      "auto_advance": false
    }
  ]
}
```

**Response (200 OK):**
```json
{
  "tenant_id": "tenant123",
  "message": "Pipeline configuration updated",
  "stages_count": 3
}
```

## Analytics Endpoints

### Get Pipeline Analytics

```http
GET /pipeline/analytics
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "tenant_id": "tenant123",
  "stages_analytics": [
    {
      "stage": "New",
      "lead_count": 45,
      "avg_score": 42.5,
      "avg_deal_value": 35000,
      "avg_days_in_stage": 3.2
    },
    {
      "stage": "Qualified",
      "lead_count": 30,
      "avg_score": 72.3,
      "avg_deal_value": 55000,
      "avg_days_in_stage": 5.8
    },
    {
      "stage": "Proposal",
      "lead_count": 15,
      "avg_score": 82.1,
      "avg_deal_value": 75000,
      "avg_days_in_stage": 7.2
    },
    {
      "stage": "Negotiation",
      "lead_count": 8,
      "avg_score": 88.5,
      "avg_deal_value": 95000,
      "avg_days_in_stage": 10.5
    },
    {
      "stage": "Won",
      "lead_count": 12,
      "avg_score": 92.0,
      "avg_deal_value": 120000,
      "avg_days_in_stage": 28.3
    }
  ],
  "conversion_rate": 0.26
}
```

### Get Revenue Forecast

```http
GET /pipeline/forecast
Authorization: Bearer <token>
```

**Response (200 OK):**
```json
{
  "tenant_id": "tenant123",
  "forecast_by_stage": [
    {
      "stage": "Qualified",
      "weighted_value": 1650000,
      "lead_count": 30
    },
    {
      "stage": "Proposal",
      "weighted_value": 1125000,
      "lead_count": 15
    },
    {
      "stage": "Negotiation",
      "weighted_value": 760000,
      "lead_count": 8
    }
  ],
  "total_forecast": 3535000,
  "timestamp": "2024-01-01T14:00:00"
}
```

## Duplicate Detection

### Find Duplicate Leads

```http
POST /leads/deduplicate
Content-Type: application/json
Authorization: Bearer <token>

{
  "email": "john@example.com"
}
```

Or by phone:
```json
{
  "phone": "+1234567890"
}
```

Or by name:
```json
{
  "first_name": "John",
  "last_name": "Doe"
}
```

**Response (200 OK):**
```json
{
  "duplicates_found": 2,
  "duplicates": [
    {
      "lead_id": "lead_1704067200.0_tenant123",
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "+1234567890"
    },
    {
      "lead_id": "lead_1704070800.0_tenant123",
      "name": "John Doe",
      "email": "john.doe@example.com",
      "phone": "+1234567890"
    }
  ]
}
```

## Health Check

```http
GET /leads/health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T14:00:00",
  "service": "Lead Scoring & Sales Pipeline",
  "version": "1.0.0"
}
```

## Error Responses

### 400 Bad Request
```json
{
  "detail": "No fields to update"
}
```

### 401 Unauthorized
```json
{
  "detail": "Missing authorization header"
}
```

### 404 Not Found
```json
{
  "detail": "Lead not found"
}
```

### 409 Conflict
```json
{
  "detail": "Lead with this email already exists"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to create lead"
}
```

## Source Channels

Supported values for `source_channel`:
- `whatsapp`
- `email`
- `web`
- `phone`
- `referral`
- `linkedin`

## Pipeline Stages

Default pipeline stages:
- `New` - Initial stage for newly created leads
- `Qualified` - Lead has passed initial qualification
- `Proposal` - Proposal has been sent
- `Negotiation` - In active negotiation
- `Won` - Deal closed successfully
- `Lost` - Deal lost or disqualified

## Rating Scales

All scores use a 0-100 scale:
- Engagement Score: 0-100
- Demographic Score: 0-100
- Behavior Score: 0-100
- Intent Score: 0-100
- Win Probability: 0-1 (0.0 to 1.0)

## Lead Grades

Grades are assigned based on composite score:
- **A**: 90-100 (Excellent)
- **B**: 75-89 (Good)
- **C**: 50-74 (Fair)
- **D**: 25-49 (Poor)
- **F**: 0-24 (Very Poor)
