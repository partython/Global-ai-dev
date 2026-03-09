# Knowledge Base v2 - Quick Start Guide

Get up and running in 5 minutes!

## 1. Prerequisites
```bash
# Required
- Docker & Docker Compose
- OpenAI API Key (https://platform.openai.com/api-keys)
- curl or Postman

# Optional
- Python 3.11+ (for local development)
```

## 2. Setup (2 minutes)

```bash
# Clone/navigate to service directory
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/knowledge

# Create .env from template
cp .env.example .env

# Edit .env and add your OpenAI API key
# OPENAI_API_KEY=sk-...
```

## 3. Start Service (1 minute)

```bash
# Start all services (PostgreSQL + Knowledge Service)
docker-compose up -d

# Check if running
docker-compose ps

# View logs
docker-compose logs -f knowledge-service
```

## 4. Verify Installation (1 minute)

```bash
# Health check
curl http://localhost:9030/api/v1/knowledge/health

# Expected response
{
  "status": "healthy",
  "service": "knowledge-base-v2",
  "port": 9030
}
```

## 5. Create JWT Token (for testing)

```bash
# Using Python
python3 << 'EOF'
import jwt
import json
from datetime import datetime, timedelta
import uuid

SECRET = "dev-secret-key-change-in-production"
TENANT_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())

payload = {
    "sub": USER_ID,
    "tenant_id": TENANT_ID,
    "email": "test@example.com",
    "iat": datetime.utcnow(),
    "exp": datetime.utcnow() + timedelta(hours=24)
}

token = jwt.encode(payload, SECRET, algorithm="HS256")
print(f"Token: {token}")
print(f"Tenant ID: {TENANT_ID}")
EOF
```

## 6. Try It Out! (1 minute)

### Upload a document
```bash
# Save token and tenant ID from previous step
TOKEN="<your-jwt-token>"
TENANT_ID="<your-tenant-id>"

# Create test document
echo "The best sales technique is to listen first and ask questions. Understanding customer pain points is key to closing deals." > test_doc.txt

# Upload
curl -X POST http://localhost:9030/api/v1/knowledge/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_doc.txt" \
  -F "title=Sales Tips" \
  -F "category=training" \
  -F "tags=sales,tips"

# Response includes doc_id, chunk_count, etc.
```

### Search documents
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "how to close deals",
    "top_k": 5,
    "use_vector": true,
    "use_keyword": true
  }'
```

### Create FAQ
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/faqs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "pricing",
    "question": "What payment terms do you offer?",
    "answer": "We offer monthly, quarterly, and annual billing with net-30 payment terms.",
    "tags": ["pricing", "payment"],
    "is_active": true
  }'
```

### Get stats
```bash
curl -X GET http://localhost:9030/api/v1/knowledge/stats \
  -H "Authorization: Bearer $TOKEN"

# Shows:
# - total_documents
# - total_chunks
# - total_faqs
# - storage_bytes
```

## API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/knowledge/health` | Health check |
| GET | `/api/v1/knowledge/stats` | KB statistics |
| POST | `/api/v1/knowledge/documents` | Upload document |
| GET | `/api/v1/knowledge/documents` | List documents |
| GET | `/api/v1/knowledge/documents/{doc_id}` | Get document |
| DELETE | `/api/v1/knowledge/documents/{doc_id}` | Delete document |
| POST | `/api/v1/knowledge/search` | Hybrid search |
| POST | `/api/v1/knowledge/embed` | Generate embedding |
| POST | `/api/v1/knowledge/chunks` | Get context chunks |
| POST | `/api/v1/knowledge/faqs` | Create FAQ |
| GET | `/api/v1/knowledge/faqs` | List FAQs |
| PUT | `/api/v1/knowledge/faqs/{faq_id}` | Update FAQ |
| DELETE | `/api/v1/knowledge/faqs/{faq_id}` | Delete FAQ |
| POST | `/api/v1/knowledge/faqs/search` | Search FAQs |

## Troubleshooting

**Service won't start:**
```bash
# Check Docker logs
docker-compose logs knowledge-service

# Verify OPENAI_API_KEY is set in .env
grep OPENAI_API_KEY .env

# Restart
docker-compose restart knowledge-service
```

**Database connection error:**
```bash
# Check PostgreSQL is running
docker-compose logs postgres

# Verify credentials in .env match docker-compose.yml
```

**Embedding API error:**
```bash
# Test OpenAI API directly
curl https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "input": "test",
    "model": "text-embedding-3-small"
  }'
```

**Invalid token error:**
```bash
# Regenerate token with matching SECRET
# SECRET must be: "dev-secret-key-change-in-production"
```

## Next Steps

1. **Read full docs:** `README.md`
2. **Deploy to production:** `DEPLOYMENT.md`
3. **Run integration tests:** `python -m pytest test_integration.py -v`
4. **Integrate with AI engine:** Use `/api/v1/knowledge/chunks` endpoint
5. **Monitor in production:** Check deployment guide for monitoring setup

## Architecture

```
┌─────────────┐
│  FastAPI    │
│  Async API  │──── JWT Auth
└──────┬──────┘
       │
   asyncpg
       │
┌──────▼──────────────────────┐
│  PostgreSQL + pgvector      │
│  - documents                │
│  - document_chunks (with    │
│    embeddings vector(1536)) │
│  - faqs                     │
│  - kb_stats                 │
└─────┬────────────────────────┘
      │
      ├─► Vector Search (IVFFlat index)
      └─► Keyword Search (BM25 scoring)

│ External │
├─────────┐
│ OpenAI  │ ─► text-embedding-3-small
│ API     │     (1536-dim vectors)
└─────────┘
```

## Key Features

✅ **Multi-tenant:** Strict data isolation per tenant
✅ **Hybrid Search:** Vector + keyword for best results
✅ **Async:** Fast, non-blocking operations
✅ **Secure:** JWT auth + RLS on all tables
✅ **Scalable:** Connection pooling, efficient indexing
✅ **Production-ready:** Health checks, error handling, monitoring

## Support

- Check logs: `docker-compose logs -f`
- Test endpoint: `curl http://localhost:9030/api/v1/knowledge/health`
- Review code: `cat main.py | less`

Happy building! 🚀
