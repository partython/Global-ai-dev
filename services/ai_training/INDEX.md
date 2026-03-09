# AI Training & Fine-tuning Service - Index

## Service Files

### main.py (812 lines)
**Primary service file - Production Ready**
- Location: `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/ai_training/main.py`
- Complete FastAPI implementation with all 15 endpoints
- Multi-tenant SaaS architecture with JWT authentication
- PostgreSQL database with asyncpg driver
- Includes automatic schema initialization

**Key Sections:**
1. Lines 1-50: Imports and module docstring
2. Lines 52-90: Enums (TrainingStatus, QualityScore)
3. Lines 92-106: AuthContext class (JWT token container)
4. Lines 108-320: Pydantic request/response models (9 models)
5. Lines 322-342: Database class (async connection pool + schema)
6. Lines 344-356: Startup/shutdown events
7. Lines 357-398: Training data endpoints (POST/GET /ai-training/data)
8. Lines 399-488: Fine-tuning endpoints (POST/GET /jobs, GET /jobs/{id})
9. Lines 489-564: Prompt template endpoints (POST/GET/PUT)
10. Lines 565-607: Quality monitoring endpoint (GET /quality)
11. Lines 609-696: Persona management endpoints (POST/GET/PUT)
12. Lines 698-706: Health check endpoint
13. Lines 708-785: Helper functions (_format_* and _submit_to_openai)
14. Lines 787-812: Main entry point (uvicorn.run)

### README.md (8.3 KB)
**Comprehensive documentation**
- Quick start guide with installation instructions
- Architecture overview and design decisions
- Feature descriptions with examples
- Database schema documentation
- Environment variable reference
- API usage examples with curl commands
- Security checklist
- Code statistics and key patterns

### ENDPOINTS.md (6.0 KB)
**API Reference Documentation**
- Service details (port, framework, database)
- Complete endpoint listing with details:
  - Request/response models
  - Query parameters
  - Path parameters
  - Authentication requirements
  - Feature descriptions
- Database schema reference
- Environment variables (required/optional)
- Architecture details

### INDEX.md (this file)
**Quick navigation and file reference**

## Quick Access

### To Start Service
```bash
python /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/ai_training/main.py
```

### Environment Setup
```bash
export DATABASE_URL="postgresql://user:pass@host:5432/db"
export JWT_SECRET="$(openssl rand -hex 32)"
export CORS_ORIGINS="http://localhost:3000"
```

### Health Check
```bash
curl http://localhost:9036/ai-training/health
```

## Endpoints Summary

### Training Data (2)
- `POST /ai-training/data` - Create training data
- `GET /ai-training/data` - List training data

### Fine-tuning (3)
- `POST /ai-training/jobs` - Create job
- `GET /ai-training/jobs` - List jobs
- `GET /ai-training/jobs/{id}` - Get job details

### Prompt Templates (3)
- `POST /ai-training/templates` - Create template
- `GET /ai-training/templates` - List templates
- `PUT /ai-training/templates/{id}` - Update template

### Quality (1)
- `GET /ai-training/quality` - Quality report

### Personas (3)
- `POST /ai-training/personas` - Create persona
- `GET /ai-training/personas` - List personas
- `PUT /ai-training/personas/{id}` - Update persona

### Health (1)
- `GET /ai-training/health` - Health check

## Features at a Glance

1. **Training Data Management** (lines 357-398)
   - Quality scoring
   - Data labeling
   - Metadata support
   - Pagination

2. **Fine-tuning Pipeline** (lines 399-488)
   - OpenAI API integration
   - Model versioning
   - Progress tracking
   - A/B testing support

3. **Prompt Template Engine** (lines 489-564)
   - Version tracking
   - Variable injection
   - Performance metrics
   - Update history

4. **Quality Monitoring** (lines 565-607)
   - Auto-evaluation
   - Flagging system
   - Aggregate reports
   - Feedback loops

5. **Persona Management** (lines 609-696)
   - Tone configuration
   - Vocabulary levels
   - Industry patterns
   - Multi-language support

## Security Features

- JWT Bearer authentication (HTTPBearer + PyJWT)
- Row-Level Security (RLS) via tenant_id
- All secrets from environment variables
- NO hardcoded credentials
- Parameterized SQL queries
- CORS configurable via environment
- Connection pooling with async support

## Technology Stack

- **Framework**: FastAPI (async)
- **Database**: PostgreSQL + asyncpg
- **Auth**: PyJWT + HTTPBearer
- **HTTP**: httpx (async)
- **Server**: Uvicorn
- **Port**: 9036

## Database Tables (5)

1. `training_data` - Conversation pairs with quality scores
2. `finetuning_jobs` - Job tracking with metrics
3. `prompt_templates` - Versioned templates with usage stats
4. `quality_evaluations` - Quality metrics with flagging
5. `personas` - AI personas with multi-language support

All tables include:
- UUID primary keys
- tenant_id for RLS
- Timestamps (created_at, updated_at)
- Indexes for performance

## Code Quality Metrics

- Type hints throughout
- Comprehensive docstrings
- Error handling with HTTPException
- Input validation with Pydantic
- Async/await patterns
- Connection pooling (5-20 connections)
- Graceful degradation for external APIs

## Deployment Checklist

1. Install dependencies:
   ```bash
   pip install fastapi uvicorn asyncpg pyjwt python-multipart httpx
   ```

2. Create PostgreSQL database:
   ```bash
   createdb ai_training
   ```

3. Set environment variables:
   ```bash
   export DATABASE_URL="postgresql://..."
   export JWT_SECRET="..."
   ```

4. Run service:
   ```bash
   python main.py
   ```

5. Verify health:
   ```bash
   curl http://localhost:9036/ai-training/health
   ```

## Required Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (no default)
- `JWT_SECRET` - JWT signing secret (no default)

## Optional Environment Variables

- `OPENAI_API_KEY` - For OpenAI fine-tuning
- `CORS_ORIGINS` - Default: "http://localhost:3000"

## Production Readiness

All components are production-ready:
- ✓ Type-safe with full type hints
- ✓ Error handling and validation
- ✓ Security best practices implemented
- ✓ Async performance optimized
- ✓ Database schema well-designed
- ✓ Documentation comprehensive
- ✓ No external dependencies on local files

## Support Documentation

For detailed information, refer to:
- README.md - Complete guide and examples
- ENDPOINTS.md - API reference
- main.py docstrings - Code-level documentation

## Version Information

- **Version**: 1.0.0
- **Created**: 2026-03-06
- **Status**: Production Ready
- **Lines of Code**: 812
- **Test Coverage**: Ready for integration tests
