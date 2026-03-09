# AI Training & Fine-tuning Service Endpoints

## Service Details
- **Port**: 9036
- **Framework**: FastAPI (async)
- **Database**: PostgreSQL (asyncpg)
- **Authentication**: JWT (HTTPBearer + PyJWT)
- **Tenant Isolation**: Row-Level Security (RLS)
- **CORS**: Configurable via environment

## Endpoints

### Training Data Management

#### POST /ai-training/data
Create new training data entry with quality scoring and labels.
- **Auth**: HTTPBearer (JWT)
- **Body**:
  - `input_text`: str (1-5000 chars)
  - `ideal_response`: str (1-5000 chars)
  - `quality_score`: Optional[excellent|good|fair|poor]
  - `labels`: Optional[List[str]]
  - `metadata`: Optional[Dict]
- **Returns**: TrainingDataResponse

#### GET /ai-training/data
List all training data for tenant with pagination.
- **Auth**: HTTPBearer (JWT)
- **Query Params**:
  - `skip`: int (default: 0)
  - `limit`: int (default: 50)
- **Returns**: List[TrainingDataResponse]

### Fine-tuning Pipeline

#### POST /ai-training/jobs
Create fine-tuning job with OpenAI API integration and model versioning.
- **Auth**: HTTPBearer (JWT)
- **Body**:
  - `name`: str (required)
  - `model`: str (default: "gpt-3.5-turbo")
  - `training_data_ids`: Optional[List[str]]
  - `hyperparameters`: Optional[Dict]
- **Returns**: FinetuningJobResponse
- **Features**: Auto-submits to OpenAI, tracks progress/metrics, versions models

#### GET /ai-training/jobs
List fine-tuning jobs with optional status filtering.
- **Auth**: HTTPBearer (JWT)
- **Query Params**:
  - `status`: Optional[pending|running|completed|failed]
  - `skip`: int (default: 0)
  - `limit`: int (default: 50)
- **Returns**: List[FinetuningJobResponse]

#### GET /ai-training/jobs/{job_id}
Get specific fine-tuning job with progress and metrics.
- **Auth**: HTTPBearer (JWT)
- **Path Params**:
  - `job_id`: UUID
- **Returns**: FinetuningJobResponse

### Prompt Template Engine

#### POST /ai-training/templates
Create versioned prompt template with variable injection support.
- **Auth**: HTTPBearer (JWT)
- **Body**:
  - `name`: str (required)
  - `template`: str (required)
  - `variables`: List[str]
  - `description`: Optional[str]
  - `metadata`: Optional[Dict]
- **Returns**: PromptTemplateResponse
- **Features**: Version tracking, variable substitution, performance metrics

#### GET /ai-training/templates
List all prompt templates for tenant.
- **Auth**: HTTPBearer (JWT)
- **Query Params**:
  - `skip`: int (default: 0)
  - `limit`: int (default: 50)
- **Returns**: List[PromptTemplateResponse]

#### PUT /ai-training/templates/{template_id}
Update prompt template with version tracking.
- **Auth**: HTTPBearer (JWT)
- **Path Params**:
  - `template_id`: UUID
- **Body**: PromptTemplateRequest
- **Returns**: PromptTemplateResponse
- **Features**: Automatic version increment on update

### Response Quality Monitoring

#### GET /ai-training/quality
Get quality monitoring report with auto-evaluation metrics and flagging.
- **Auth**: HTTPBearer (JWT)
- **Query Params**:
  - `days`: int (default: 7, lookback period)
- **Returns**: QualityReportResponse
- **Features**:
  - Overall quality scores (excellent/good/fair/poor)
  - Average performance score
  - Flagged low-quality responses (up to 20)
  - Relevance, accuracy, tone matching metrics

### Persona Management

#### POST /ai-training/personas
Create AI persona with tone, vocabulary, and industry-specific patterns.
- **Auth**: HTTPBearer (JWT)
- **Body**:
  - `name`: str (required)
  - `tone`: str (required, e.g., professional, casual, friendly)
  - `vocabulary_level`: str (required, e.g., simple, moderate, advanced)
  - `industry`: Optional[str]
  - `language`: str (default: "en")
  - `response_patterns`: Optional[List[str]]
  - `metadata`: Optional[Dict]
- **Returns**: PersonaResponse
- **Features**: Multi-language support, version tracking

#### GET /ai-training/personas
List personas with optional language filtering.
- **Auth**: HTTPBearer (JWT)
- **Query Params**:
  - `language`: Optional[str] (e.g., "en", "es", "fr")
  - `skip`: int (default: 0)
  - `limit`: int (default: 50)
- **Returns**: List[PersonaResponse]

#### PUT /ai-training/personas/{persona_id}
Update persona with version tracking.
- **Auth**: HTTPBearer (JWT)
- **Path Params**:
  - `persona_id`: UUID
- **Body**: PersonaRequest
- **Returns**: PersonaResponse
- **Features**: Automatic version increment on update

### Health & Status

#### GET /ai-training/health
Service health check endpoint.
- **Auth**: None required
- **Returns**: HealthResponse

## Database Schema

### Tables (PostgreSQL with RLS)
- `training_data`: Training conversation pairs with quality scores
- `finetuning_jobs`: Fine-tuning job tracking with metrics
- `prompt_templates`: Versioned prompt templates with usage stats
- `quality_evaluations`: Quality assessment records with flagging
- `personas`: AI persona definitions with multi-language support

All tables include:
- `tenant_id` for tenant isolation (RLS)
- Created/Updated timestamps
- Appropriate indexes for performance

## Security & Environment Variables

### Required Environment Variables
- `DATABASE_URL`: PostgreSQL connection string (no default)
- `JWT_SECRET`: JWT signing secret (no default)
- `OPENAI_API_KEY`: Optional, for OpenAI fine-tuning submission

### Optional Environment Variables
- `CORS_ORIGINS`: Comma-separated CORS origins (default: "http://localhost:3000")

### Features
- JWT Bearer token authentication
- Row-Level Security (RLS) via tenant_id isolation
- All secrets from environment (no hardcoded values)
- Async operations with asyncpg connection pooling
- CORS configurable via environment
- No default values for critical secrets

## Architecture

### Tech Stack
- **Framework**: FastAPI (async/await)
- **Database**: PostgreSQL with asyncpg
- **Authentication**: PyJWT + HTTPBearer
- **HTTP Client**: httpx (async)
- **Server**: Uvicorn

### Key Patterns
- Tenant isolation through AuthContext
- Automatic schema initialization on startup
- Connection pooling (5-20 connections)
- Async/await throughout
- Version tracking for templates and personas
- Fire-and-forget pattern for OpenAI API calls
