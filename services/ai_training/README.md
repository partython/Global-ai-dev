# AI Training & Fine-tuning Service

A multi-tenant SaaS FastAPI service for managing AI model training, fine-tuning, prompt templates, quality monitoring, and persona management.

## Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL 12+
- Environment variables set (see below)

### Installation

```bash
pip install fastapi uvicorn asyncpg pyjwt python-multipart httpx
```

### Run Service

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/ai_training"
export JWT_SECRET="your-secret-key-here"
export CORS_ORIGINS="http://localhost:3000,http://localhost:8000"
export OPENAI_API_KEY="sk-..."  # Optional

python /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/ai_training/main.py
```

Service will be available at `http://localhost:9036`

## Architecture Overview

### Multi-Tenant Design
- Every query includes `tenant_id` from JWT for Row-Level Security (RLS)
- AuthContext extracts tenant_id and user_id from JWT token
- No cross-tenant data access possible

### Async First
- Built on FastAPI with async/await
- asyncpg for efficient database operations
- Connection pooling (5-20 connections)
- httpx for async HTTP calls to OpenAI

### Security
- JWT authentication with HTTPBearer
- All secrets from environment variables
- No hardcoded credentials
- CORS configurable via environment

## Features

### 1. Training Data Management
- Store conversation pairs (input → ideal response)
- Quality scoring (excellent, good, fair, poor)
- Data labeling for categorization
- Custom metadata support
- List with pagination

**Endpoints:**
- POST /ai-training/data
- GET /ai-training/data

### 2. Fine-tuning Pipeline
- Create fine-tuning jobs
- OpenAI API integration (fire-and-forget)
- Model versioning with timestamps
- Track training progress and metrics
- Support for A/B testing with different model versions
- Hyperparameter configuration

**Endpoints:**
- POST /ai-training/jobs
- GET /ai-training/jobs
- GET /ai-training/jobs/{id}

### 3. Prompt Template Engine
- Store and version prompt templates
- Variable injection support
- Usage tracking
- Performance metrics (avg_performance)
- Automatic version increment on updates

**Endpoints:**
- POST /ai-training/templates
- GET /ai-training/templates
- PUT /ai-training/templates/{id}

### 4. Response Quality Monitoring
- Auto-evaluate AI responses
- Track quality scores (relevance, accuracy, tone)
- Flag low-quality responses for review
- Aggregate quality report over time period
- Feedback loop support

**Endpoints:**
- GET /ai-training/quality

### 5. Persona Management
- Define AI personas with tone and vocabulary
- Industry-specific response patterns
- Multi-language support
- Version tracking
- Custom metadata

**Endpoints:**
- POST /ai-training/personas
- GET /ai-training/personas
- PUT /ai-training/personas/{id}

## Database Schema

### training_data
```
- id (UUID, PK)
- tenant_id (UUID) - for RLS
- input_text (TEXT)
- ideal_response (TEXT)
- quality_score (VARCHAR) - excellent|good|fair|poor
- labels (JSONB) - array of strings
- metadata (JSONB)
- created_at, updated_at (TIMESTAMP)
```

### finetuning_jobs
```
- id (UUID, PK)
- tenant_id (UUID) - for RLS
- name (VARCHAR)
- model (VARCHAR)
- status (VARCHAR) - pending|running|completed|failed
- training_data_count (INT)
- metrics (JSONB)
- model_version (VARCHAR) - e.g., v1709784523.0
- external_job_id (VARCHAR) - OpenAI job ID
- created_at, updated_at (TIMESTAMP)
```

### prompt_templates
```
- id (UUID, PK)
- tenant_id (UUID) - for RLS
- name (VARCHAR)
- template (TEXT)
- variables (JSONB) - array of variable names
- description (TEXT)
- version (INT) - auto-incremented
- metadata (JSONB)
- usage_count (INT)
- avg_performance (DECIMAL)
- created_at, updated_at (TIMESTAMP)
```

### quality_evaluations
```
- id (UUID, PK)
- tenant_id (UUID) - for RLS
- response_id (VARCHAR)
- quality_score (VARCHAR)
- relevance (DECIMAL 0-1)
- accuracy (DECIMAL 0-1)
- tone_match (DECIMAL 0-1)
- is_flagged (BOOLEAN)
- feedback (TEXT)
- created_at, updated_at (TIMESTAMP)
```

### personas
```
- id (UUID, PK)
- tenant_id (UUID) - for RLS
- name (VARCHAR)
- tone (VARCHAR) - professional, casual, friendly, etc
- vocabulary_level (VARCHAR) - simple, moderate, advanced
- industry (VARCHAR)
- language (VARCHAR) - default 'en'
- response_patterns (JSONB) - array of patterns
- metadata (JSONB)
- version (INT)
- created_at, updated_at (TIMESTAMP)
```

## Environment Variables

### Required
- `DATABASE_URL`: PostgreSQL connection string
  - Format: `postgresql://user:password@host:port/database`
  - Example: `postgresql://postgres:pass@localhost:5432/ai_training`
  - No default value (will raise error if missing)

- `JWT_SECRET`: Secret key for JWT signing
  - Use a cryptographically secure random string
  - Example: `openssl rand -hex 32`
  - No default value (will raise error if missing)

### Optional
- `OPENAI_API_KEY`: OpenAI API key for fine-tuning integration
  - Format: `sk-...`
  - If not set, OpenAI API calls will gracefully fail

- `CORS_ORIGINS`: Comma-separated list of allowed origins
  - Default: `http://localhost:3000`
  - Example: `http://localhost:3000,http://localhost:8000,https://app.example.com`

## API Examples

### Create Training Data
```bash
curl -X POST http://localhost:9036/ai-training/data \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "input_text": "What is machine learning?",
    "ideal_response": "Machine learning is...",
    "quality_score": "good",
    "labels": ["qa", "ml-basics"],
    "metadata": {"source": "training"}
  }'
```

### Create Fine-tuning Job
```bash
curl -X POST http://localhost:9036/ai-training/jobs \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Customer Service Model v1",
    "model": "gpt-3.5-turbo",
    "hyperparameters": {"learning_rate": 0.1}
  }'
```

### Create Prompt Template
```bash
curl -X POST http://localhost:9036/ai-training/templates \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Customer Support",
    "template": "You are a helpful support agent. Customer question: {question}",
    "variables": ["question"],
    "description": "For customer support interactions"
  }'
```

### Create Persona
```bash
curl -X POST http://localhost:9036/ai-training/personas \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Professional Support Agent",
    "tone": "professional",
    "vocabulary_level": "moderate",
    "industry": "customer-support",
    "language": "en",
    "response_patterns": ["Acknowledge concern", "Provide solution", "Follow up"]
  }'
```

### Get Quality Report
```bash
curl -X GET "http://localhost:9036/ai-training/quality?days=7" \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

### Health Check
```bash
curl http://localhost:9036/ai-training/health
```

## Code Statistics

- **File**: main.py
- **Lines**: 812
- **Framework**: FastAPI
- **Database**: PostgreSQL (asyncpg)
- **Authentication**: JWT + HTTPBearer
- **Port**: 9036

## Key Design Decisions

1. **Async/Await Throughout**: All operations are async for high concurrency
2. **Tenant Isolation**: Every query filters by tenant_id from JWT
3. **Fire-and-Forget OpenAI**: Jobs submitted asynchronously, polling happens separately
4. **Version Tracking**: Templates and personas auto-increment versions
5. **Flexible Metadata**: All entities support custom metadata (JSONB)
6. **Graceful Degradation**: OpenAI API failures don't crash the service
7. **Connection Pooling**: 5-20 async connections for efficiency
8. **No Hardcoded Secrets**: All sensitive config from environment

## Security Checklist

- [x] JWT authentication for all endpoints except /health
- [x] HTTPBearer for token extraction
- [x] AuthContext for tenant isolation
- [x] WHERE tenant_id = $X in all queries
- [x] All secrets from environment variables
- [x] No default values for JWT_SECRET or DB password
- [x] CORS configurable via environment
- [x] Connection string from environment
- [x] Parameterized queries (preventing SQL injection)
- [x] Error handling without leaking sensitive info

## Testing

See separate test file for comprehensive test coverage including:
- Authentication and authorization
- Tenant isolation
- All CRUD operations
- Quality reporting
- Edge cases and error scenarios
