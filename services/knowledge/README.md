# Knowledge Base v2 Service

Multi-tenant RAG (Retrieval-Augmented Generation) with Document Management for the Global AI Sales Platform.

**Port:** 9030

## Features

### Document Management
- Upload documents (PDF, DOCX, TXT, HTML, CSV)
- Document versioning and metadata tracking
- Categorization and tagging system
- Access control (private, team, public)
- Bulk upload support via API
- Automatic text extraction and chunking

### RAG v2 (Retrieval-Augmented Generation)
- Configurable text chunking with overlap
- Vector embeddings via OpenAI API
- **Hybrid Search:** Combines vector similarity + BM25 keyword matching
- Per-tenant namespace isolation (strict data safety)
- Relevance scoring and re-ranking
- Context window optimization for AI engines
- Dynamic context assembly for chat models

### FAQ Management
- Create, read, update, delete FAQs
- Categorized FAQ organization
- Full-text search across FAQs
- Helpfulness tracking (helpful/unhelpful votes)
- Auto-tagging and filtering
- Active/inactive FAQ status

### Training Data Integration
- Product catalog ingestion
- Custom response templates
- Tone/style configuration per tenant
- Training data quality scoring
- Batch processing support

## Environment Variables

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=priya_global
DB_USER=postgres
DB_PASSWORD=<secure_password>

# Security
JWT_SECRET=<your-jwt-secret>
CORS_ORIGINS=http://localhost:3000,https://app.example.com

# Embeddings (OpenAI)
OPENAI_API_KEY=<sk-...>

# Service Configuration
CHUNK_SIZE=512          # Text chunk size in characters
CHUNK_OVERLAP=100       # Overlap between chunks
```

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run service
python main.py
```

## Architecture

### Database Schema

**documents** table:
- `doc_id` (UUID PK)
- `tenant_id` (UUID) - Multi-tenancy key
- `title`, `category`, `tags`
- `file_type`, `file_size`, `content`
- `chunk_count`, `access_level`
- RLS enforced via tenant_id

**document_chunks** table:
- `chunk_id` (UUID PK)
- `doc_id` (FK to documents)
- `tenant_id` (UUID) - Strict isolation
- `chunk_index`, `content`
- `embedding` (vector(1536)) - pgvector column
- IVFFlat index for fast vector search

**faqs** table:
- `faq_id` (UUID PK)
- `tenant_id` (UUID) - Strict RLS
- `category`, `question`, `answer`
- `tags`, `is_active`
- `helpful_count`, `unhelpful_count`

**kb_stats** table:
- Real-time statistics per tenant
- Document counts, chunk counts, storage metrics

### Embedding Model
- **Model:** text-embedding-3-small
- **Dimension:** 1536
- **Provider:** OpenAI API
- **Fallback:** Zero vectors on API failure (allows graceful degradation)

## API Endpoints

### Health & Stats
```
GET /api/v1/knowledge/health          - Health check
GET /api/v1/knowledge/stats            - KB statistics (requires auth)
```

### Document Management
```
POST   /api/v1/knowledge/documents     - Upload document
GET    /api/v1/knowledge/documents     - List documents (with filters)
GET    /api/v1/knowledge/documents/{doc_id}  - Get document details
DELETE /api/v1/knowledge/documents/{doc_id}  - Delete document
```

### Search & Embeddings
```
POST /api/v1/knowledge/search   - Hybrid search (vector + keyword)
POST /api/v1/knowledge/embed    - Generate embedding for text
POST /api/v1/knowledge/chunks   - Get context chunks for query
```

### FAQ Management
```
POST   /api/v1/knowledge/faqs          - Create FAQ
GET    /api/v1/knowledge/faqs          - List FAQs
PUT    /api/v1/knowledge/faqs/{faq_id} - Update FAQ
DELETE /api/v1/knowledge/faqs/{faq_id} - Delete FAQ
POST   /api/v1/knowledge/faqs/search   - Search FAQs
```

## Usage Examples

### Upload Document
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/documents \
  -H "Authorization: Bearer <jwt_token>" \
  -F "file=@document.pdf" \
  -F "title=Sales Playbook" \
  -F "category=training" \
  -F "tags=sales,training,2024"
```

### Hybrid Search
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/search \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "how to close enterprise deals",
    "top_k": 10,
    "use_vector": true,
    "use_keyword": true,
    "min_score": 0.3
  }'
```

### Get Context Chunks (For AI Engine)
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/chunks \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "enterprise pricing strategy",
    "top_k": 5
  }'
```

### Create FAQ
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/faqs \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "pricing",
    "question": "What discounts apply to multi-year contracts?",
    "answer": "Multi-year contracts typically receive 15-20% discount...",
    "tags": ["discount", "contract"],
    "is_active": true
  }'
```

## Security

### Multi-Tenancy (Critical)
- Every query includes `tenant_id` from JWT token
- RLS (Row-Level Security) via SQL parameterization
- Strict namespace isolation in document_chunks table
- No cross-tenant data leakage possible

### Authentication
- JWT Bearer token validation
- Claims extraction: `sub` (user_id), `tenant_id`, `email`
- Token verification with HS256 algorithm

### Data Protection
- All secrets from environment variables (never hardcoded)
- Parameterized SQL queries (prevents injection)
- HTTPS required in production
- CORS configured from environment

## Performance Considerations

### Vector Search
- IVFFlat index for O(log n) vector search
- Cosine distance metric
- Default top_k=10, max=100

### Keyword Search
- BM25-like scoring
- In-memory ranking (scales to ~10k chunks per tenant)
- Combined with vector search via re-ranking

### Chunking Strategy
- Default: 512 char chunks with 100 char overlap
- Configurable via env vars
- Preserves context across chunk boundaries

### Caching
- LRU cache for repeated embeddings
- Connection pooling (5-20 connections)
- Async I/O throughout

## Monitoring & Logging

```bash
# View service logs
tail -f logs/knowledge-service.log

# Check database connection stats
psql -c "SELECT count(*) FROM pg_stat_activity WHERE application_name = 'knowledge-v2';"

# Monitor vector search performance
EXPLAIN ANALYZE SELECT * FROM document_chunks ORDER BY embedding <-> $1 LIMIT 10;
```

## Troubleshooting

### Embedding API Failures
- Service gracefully falls back to zero vectors
- Documents still searchable by keyword
- Fix: Verify OPENAI_API_KEY and rate limits

### Vector Search Slow
- Rebuild IVFFlat index: `REINDEX INDEX idx_chunks_embedding;`
- Increase max_wal_size in PostgreSQL
- Consider partitioning by tenant_id

### Out of Memory
- Chunk size too large (increase CHUNK_OVERLAP, reduce CHUNK_SIZE)
- Too many results in keyword search (reduce top_k)
- Large files (>100MB) should be pre-processed

## Production Deployment

1. **Database Setup**
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```

2. **Scale Requirements**
   - Min 2 instances behind load balancer
   - 10-20 DB connections per instance
   - Redis for embedding cache (optional)

3. **Monitoring**
   - Track vector search latency
   - Monitor DB connection usage
   - Alert on embedding API errors

4. **Backup**
   - Daily database snapshots
   - Vector index reconstruction plan
   - Document storage backup

## Development

```bash
# Run tests
pytest tests/ -v

# Type checking
mypy main.py

# Code formatting
black main.py
isort main.py
```

## Contributing

Follow PEP 8 style guide. All PRs require:
- Type hints
- Docstrings
- Tests for new endpoints
- No hardcoded secrets

## License

Proprietary - Global AI Sales Platform
