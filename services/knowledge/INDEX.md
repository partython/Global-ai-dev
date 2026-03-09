# Knowledge Base v2 Service - Complete Documentation Index

## Quick Navigation

### 🚀 Getting Started
- **New to the service?** Start with [QUICKSTART.md](QUICKSTART.md) (5 minutes)
- **Need overview?** Read [README.md](README.md) (10 minutes)
- **Want full details?** See [MANIFEST.md](MANIFEST.md) (15 minutes)

### 📖 Documentation by Purpose

#### For Product Managers
1. [README.md](README.md) - Features & capabilities
2. [MANIFEST.md](MANIFEST.md) - Project overview

#### For Backend Developers
1. [QUICKSTART.md](QUICKSTART.md) - Local setup
2. [main.py](main.py) - Source code (978 lines)
3. [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) - Architecture details
4. [test_integration.py](test_integration.py) - Test examples

#### For DevOps Engineers
1. [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
2. [docker-compose.yml](docker-compose.yml) - Local stack
3. [Dockerfile](Dockerfile) - Container image
4. [.env.example](.env.example) - Configuration template

#### For Frontend Developers
1. [API_REFERENCE.md](API_REFERENCE.md) - All endpoints
2. [QUICKSTART.md](QUICKSTART.md) - Quick examples
3. [README.md](README.md) - Architecture overview

#### For Security Teams
1. [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) - Security section
2. [MANIFEST.md](MANIFEST.md) - Security checklist
3. [main.py](main.py) - Source code review

---

## File Guide

### Core Application

#### `main.py` (978 lines)
**The complete Knowledge Base v2 service**

Contents:
- Config & Pydantic models (175 lines)
- Database setup & pooling (50 lines)
- Authentication & JWT handling (100 lines)
- Database schema initialization (70 lines)
- Health & statistics endpoints (50 lines)
- Document management endpoints (200 lines)
- Search & embedding endpoints (150 lines)
- FAQ management endpoints (200 lines)
- Startup/shutdown handlers (20 lines)

**To understand the code:**
1. Start at line 80 (Config & Models)
2. Read auth functions (~160)
3. Check endpoints (200+)
4. Review database schema (~165)

### Configuration

#### `.env.example`
Template for environment variables
- Copy to `.env` before running
- Required: DB credentials, JWT_SECRET, OPENAI_API_KEY
- Optional: CHUNK_SIZE, CHUNK_OVERLAP, CORS_ORIGINS

#### `requirements.txt`
Python dependencies (9 packages)
- Install: `pip install -r requirements.txt`

### Docker & Deployment

#### `Dockerfile`
Production container image
- Base: Python 3.11-slim
- Installs system dependencies
- Runs uvicorn on port 9030

#### `docker-compose.yml`
Local development stack
- PostgreSQL 15 with pgvector
- Knowledge service
- Auto-initialization
- Health checks

### Documentation

#### `README.md` (311 lines) ⭐ START HERE
**User-friendly overview**

Sections:
- Features summary (document mgmt, RAG v2, FAQ, training data)
- Installation & setup
- Architecture overview
- API endpoints (summary)
- Security model
- Performance notes
- Troubleshooting

**Best for:** Understanding what the service does

#### `QUICKSTART.md` (256 lines) ⭐ SETUP GUIDE
**Get running in 5 minutes**

Sections:
- Prerequisites
- Setup (copy .env, edit secrets)
- Start service (docker-compose)
- Verify (health check)
- Generate JWT token
- Try example API calls
- Troubleshooting

**Best for:** First-time setup

#### `MANIFEST.md` (491 lines)
**Complete project overview**

Sections:
- Project summary
- File structure & descriptions
- Technology stack
- API endpoints list (all 14)
- Database schema (4 tables)
- Key features checklist
- Performance metrics
- Security checklist
- Deployment options
- Version history

**Best for:** Project context & reference

#### `TECHNICAL_SPEC.md` (644 lines) ⭐ DEEP DIVE
**Architecture & implementation details**

Sections:
1. Architecture (topology, data flows)
2. Database schema (detailed)
3. Security (auth, RLS, secrets)
4. API specification (all endpoints with examples)
5. Performance metrics
6. Concurrency & locking
7. Configuration options
8. Testing strategy
9. Monitoring & observability
10. Future enhancements

**Best for:** Understanding design decisions

#### `API_REFERENCE.md` (759 lines) ⭐ API DOCS
**Complete API endpoint documentation**

Endpoints documented:
- GET /health - Health check
- GET /stats - Statistics
- POST /documents - Upload
- GET /documents - List
- GET /documents/{id} - Get
- DELETE /documents/{id} - Delete
- POST /embed - Generate embedding
- POST /search - Hybrid search
- POST /chunks - Get context
- POST /faqs - Create FAQ
- GET /faqs - List FAQs
- PUT /faqs/{id} - Update
- DELETE /faqs/{id} - Delete
- POST /faqs/search - Search FAQs

**For each endpoint:**
- Full documentation
- Query parameters explained
- Request/response examples
- cURL examples
- Status codes
- Error handling

**Best for:** Building client integration

#### `DEPLOYMENT.md` (408 lines)
**Production deployment guide**

Sections:
- Quick start (local Docker)
- Production architecture
- Database setup (RDS)
- Kubernetes deployment
- Secrets & ConfigMaps
- Monitoring & alerting
- Performance tuning
- Backup & recovery
- Rollback procedures
- Load testing
- Troubleshooting
- Security checklist
- Cost optimization

**Best for:** DevOps & SRE teams

### Testing

#### `test_integration.py` (287 lines)
**Integration test examples**

Tests included:
- Health check
- Document operations (upload, list, get, delete)
- Embedding generation
- Search functionality
- FAQ CRUD
- Tenant isolation
- Error handling

**Run tests:**
```bash
pytest test_integration.py -v
```

---

## Common Tasks

### Task: Get Service Running Locally
1. Read: [QUICKSTART.md](QUICKSTART.md)
2. Run: `docker-compose up -d`
3. Verify: `curl http://localhost:9030/api/v1/knowledge/health`

### Task: Integrate with Frontend
1. Read: [API_REFERENCE.md](API_REFERENCE.md)
2. Check: [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) section 3 (Security)
3. Generate JWT token from your auth service
4. Call endpoints with `Authorization: Bearer <token>`

### Task: Deploy to Production
1. Read: [DEPLOYMENT.md](DEPLOYMENT.md)
2. Setup database (RDS with pgvector)
3. Create secrets (JWT_SECRET, OPENAI_API_KEY, DB credentials)
4. Deploy Kubernetes manifests
5. Monitor via CloudWatch/Prometheus

### Task: Understand Architecture
1. Read: [README.md](README.md) section 2 (Architecture)
2. Read: [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) sections 1-2
3. Review: [main.py](main.py) database schema section

### Task: Add New Feature
1. Review: [main.py](main.py) structure
2. Add: Pydantic model (around line 100)
3. Add: Database operations (use asyncpg)
4. Add: Endpoint handler (use Depends(verify_token))
5. Add: Tests to [test_integration.py](test_integration.py)

### Task: Investigate Performance Issue
1. Read: [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) section 5 (Performance)
2. Check: Logs via `docker-compose logs -f`
3. Query: `EXPLAIN ANALYZE` in PostgreSQL
4. Monitor: Database connections & slow queries
5. Tune: IVFFlat index, connection pool, chunk size

---

## Documentation Statistics

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| main.py | 978 | Code | Complete service |
| test_integration.py | 287 | Code | Tests & examples |
| TECHNICAL_SPEC.md | 644 | Doc | Architecture details |
| API_REFERENCE.md | 759 | Doc | API documentation |
| DEPLOYMENT.md | 408 | Doc | Production guide |
| MANIFEST.md | 491 | Doc | Project overview |
| README.md | 311 | Doc | User guide |
| QUICKSTART.md | 256 | Doc | Setup guide |
| INDEX.md | 200 | Doc | This file |
| Dockerfile | 20 | Config | Container image |
| docker-compose.yml | 45 | Config | Dev stack |
| requirements.txt | 9 | Config | Dependencies |
| .env.example | 30 | Config | Environment template |
| **TOTAL** | **4,438** | — | — |

---

## Key Concepts

### Multi-Tenancy
- Every table has `tenant_id` column
- JWT token contains `tenant_id`
- All queries filtered by `tenant_id`
- Strict data isolation guaranteed

### RAG (Retrieval-Augmented Generation)
- Extract relevant context from documents
- Feed context to LLM for better answers
- Combines vector search (semantic) + keyword search (exact)
- Dynamic context window optimization

### Hybrid Search
```
Query: "how to close deals"
  ↓
1. Vector Search (cosine similarity on embeddings)
   - Score: 0.92 for relevant passage
2. Keyword Search (BM25 on text)
   - Score: 0.75 for passage with "close"
3. Combine Scores
   - Final: (0.92 * 0.6) + (0.75 * 0.4) = 0.85
  ↓
Return top matching chunks
```

### Row-Level Security (RLS)
- Application enforces at query time
- Every query includes: `WHERE tenant_id = $1`
- Database doesn't need RLS policies
- Prevents accidental cross-tenant queries

---

## Important Security Notes

⚠️ **NEVER commit these files to version control:**
- `.env` (contains secrets)
- Database backups
- Private keys
- API credentials

✅ **DO commit:**
- `.env.example` (template)
- `.gitignore` (blocks secrets)
- Source code
- Documentation
- Tests

✅ **All secrets from environment:**
```python
JWT_SECRET = os.getenv("JWT_SECRET", "")  # Good
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # Good
password = "secret123"  # ❌ NEVER!
```

---

## Support Resources

### Debugging
- Check logs: `docker-compose logs knowledge-service`
- Health check: `curl http://localhost:9030/api/v1/knowledge/health`
- Database: `psql -h localhost -U postgres -d priya_global`

### Learning
- Study examples in [test_integration.py](test_integration.py)
- Review Pydantic models in [main.py](main.py) ~line 80
- Understand FastAPI basics (see README.md)

### Documentation
- API details: [API_REFERENCE.md](API_REFERENCE.md)
- Architecture: [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md)
- Deployment: [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Document Reading Order (Recommended)

1. **First 5 min:** [README.md](README.md) - What is this?
2. **Next 5 min:** [QUICKSTART.md](QUICKSTART.md) - Get it running
3. **Next 10 min:** [MANIFEST.md](MANIFEST.md) - Project overview
4. **Next 20 min:** [API_REFERENCE.md](API_REFERENCE.md) - How to use it
5. **Next 30 min:** [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) - How it works
6. **As needed:** [DEPLOYMENT.md](DEPLOYMENT.md) - Deploy to production

**Total reading time:** ~1 hour to full understanding

---

## Checklists

### Pre-Launch Checklist
- [ ] `.env` file created with all required secrets
- [ ] Database running and accessible
- [ ] OPENAI_API_KEY set and valid
- [ ] JWT_SECRET set (32+ characters)
- [ ] Health check passing
- [ ] Can upload document
- [ ] Can search documents
- [ ] Can create FAQ

### Pre-Production Checklist
- [ ] Database backups configured
- [ ] TLS/HTTPS enabled
- [ ] Rate limiting configured
- [ ] Monitoring & alerting setup
- [ ] Deployment runbook ready
- [ ] Rollback plan documented
- [ ] Security audit completed
- [ ] Load tested

### Code Review Checklist
- [ ] No hardcoded secrets
- [ ] All imports present
- [ ] Type hints complete
- [ ] Error handling comprehensive
- [ ] SQL parameterized (no injection)
- [ ] Tenant isolation enforced
- [ ] Tests pass
- [ ] Documentation updated

---

**Last Updated:** 2024-03-06  
**Service Version:** 2.0.0  
**Documentation Status:** Complete  
**Ready for Production:** ✅ YES
