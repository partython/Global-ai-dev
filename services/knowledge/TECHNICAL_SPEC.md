# Knowledge Base v2 - Technical Specification

## Executive Summary

**Service:** Knowledge Base v2  
**Port:** 9030  
**Type:** Multi-tenant RAG with Document Management  
**Framework:** FastAPI + asyncpg  
**Database:** PostgreSQL with pgvector  
**Embeddings:** OpenAI text-embedding-3-small  
**Lines of Code:** ~978 (main.py)

## 1. Architecture

### 1.1 Service Topology
```
┌──────────────────────────────────────┐
│     FastAPI (async)                  │
│     - HTTPBearer JWT auth            │
│     - CORS middleware                │
│     - 14 API endpoints               │
└──────────┬───────────────────────────┘
           │
      asyncpg pool (5-20 conns)
           │
┌──────────▼──────────────────────────┐
│  PostgreSQL 15+ (RDS/self-hosted)   │
│  - pgvector extension                │
│  - 4 main tables                     │
│  - Tenant-based RLS                  │
│  - IVFFlat index for vectors         │
└──────────────────────────────────────┘
           │
      External API
           │
┌──────────▼──────────────────────────┐
│  OpenAI API                          │
│  - text-embedding-3-small            │
│  - 1536-dimensional vectors          │
│  - ~0.02$ per 1M tokens              │
└──────────────────────────────────────┘
```

### 1.2 Data Flow: Document Upload
```
1. User uploads file (PDF/DOCX/TXT/HTML/CSV)
   ↓
2. FastAPI validates file type
   ↓
3. Extract text content (with error handling)
   ↓
4. Chunk text (configurable: 512 chars, 100 overlap)
   ↓
5. For each chunk:
   - Call OpenAI embedding API
   - Store in document_chunks with embedding vector
   ↓
6. Insert document metadata
   ↓
7. Update kb_stats for tenant
   ↓
8. Return DocumentResponse with chunk_count
```

### 1.3 Data Flow: Hybrid Search
```
User Query: "how to close enterprise deals"
   ↓
1. Generate query embedding via OpenAI API
   ↓
2. Parallel search:
   ├─ Vector Search:
   │  - Find nearest neighbors using cosine distance
   │  - IVFFlat index: O(log n) lookup
   │  - Returns top_k with scores (0.0-1.0)
   │
   └─ Keyword Search:
      - BM25 scoring on all chunks
      - In-memory ranking
      - Returns top_k with scores (0.0-1.0)
   ↓
3. Merge results:
   - Deduplicate by chunk_id
   - Combined score = (vector*0.6 + keyword*0.4)
   ↓
4. Filter by min_score threshold
   ↓
5. Sort by combined score
   ↓
6. Return top_k SearchResults to user
```

## 2. Database Schema

### 2.1 Tables

#### documents
```sql
CREATE TABLE documents (
    doc_id UUID PRIMARY KEY,                    -- Unique identifier
    tenant_id UUID NOT NULL,                    -- RLS key
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    tags TEXT[],                                -- PostgreSQL array
    access_level VARCHAR(50) DEFAULT 'private', -- private|team|public
    file_type VARCHAR(20) NOT NULL,             -- pdf|docx|txt|html|csv
    file_size BIGINT NOT NULL,                  -- in bytes
    content TEXT NOT NULL,                      -- full extracted text
    chunk_count INT DEFAULT 0,                  -- for stats
    created_by UUID NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes:
-- idx_documents_tenant: Fast tenant filtering
-- idx_documents_category: Filter by category
```

#### document_chunks
```sql
CREATE TABLE document_chunks (
    chunk_id UUID PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,                    -- Denormalized for RLS
    chunk_index INT NOT NULL,                   -- Order in document
    content TEXT NOT NULL,                      -- Chunk text
    embedding vector(1536) NOT NULL,            -- pgvector column
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes:
-- idx_chunks_tenant: Tenant isolation
-- idx_chunks_doc: Document queries
-- idx_chunks_embedding: Vector similarity search (IVFFlat)
```

#### faqs
```sql
CREATE TABLE faqs (
    faq_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    category VARCHAR(100) NOT NULL,
    question VARCHAR(500) NOT NULL,
    answer TEXT NOT NULL,
    tags TEXT[],
    is_active BOOLEAN DEFAULT TRUE,
    helpful_count INT DEFAULT 0,                -- Upvotes
    unhelpful_count INT DEFAULT 0,              -- Downvotes
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes:
-- idx_faqs_tenant: Tenant isolation
-- idx_faqs_category: Category queries
```

#### kb_stats
```sql
CREATE TABLE kb_stats (
    stat_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL UNIQUE,             -- One row per tenant
    total_documents INT DEFAULT 0,
    total_chunks INT DEFAULT 0,
    total_faqs INT DEFAULT 0,
    total_embeddings INT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 2.2 Row-Level Security (RLS)

**Implementation Method:** Parameterized queries with tenant_id validation

**Protection:**
- Every query filters by `tenant_id` from JWT token
- Database doesn't enforce RLS, application layer enforces
- Strict namespace isolation in all searches

**Example:**
```python
# Search only returns results for authenticated tenant
await conn.fetch(
    "SELECT * FROM document_chunks 
     WHERE tenant_id = $1 AND ...",
    uuid.UUID(auth.tenant_id)  # From JWT
)
```

## 3. Security Architecture

### 3.1 Authentication
```
Client Request
   ↓
HTTPBearer extracts "Bearer <token>" from Authorization header
   ↓
JWT decode with HS256 algorithm
   ↓
Verify claims:
- sub (user_id)
- tenant_id
- email
- exp (expiration)
   ↓
Create AuthContext object
   ↓
Inject into endpoint handler
```

**Claims:**
```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "email": "user@company.com",
  "iat": 1704067200,
  "exp": 1704153600
}
```

### 3.2 Data Isolation
- **Tenant isolation:** Every query includes tenant_id parameter
- **No shared data:** Same table row visible only to its tenant
- **Cross-tenant prevention:** Any attempt returns 404 or empty results
- **No admin backdoors:** All endpoint handlers require auth

### 3.3 Secret Management
```python
# CORRECT: From environment
JWT_SECRET = os.getenv("JWT_SECRET", "")
EMBEDDING_API_KEY = os.getenv("OPENAI_API_KEY", "")

# NEVER: Hardcoded
JWT_SECRET = "secret123"  # ❌ WRONG
```

### 3.4 Secrets Required
```
DB_USER              - PostgreSQL username
DB_PASSWORD          - PostgreSQL password
JWT_SECRET           - For signing/verifying JWTs (min 32 chars)
OPENAI_API_KEY       - For embedding generation (sk-...)
CORS_ORIGINS         - Trusted frontend domains
```

## 4. API Specification

### 4.1 Health Check
```
GET /api/v1/knowledge/health

Response:
{
  "status": "healthy",
  "service": "knowledge-base-v2",
  "port": 9030
}

Notes:
- No auth required
- Used by load balancers for health checks
```

### 4.2 Document Upload
```
POST /api/v1/knowledge/documents

Auth: Required (HTTPBearer)

Query Params:
- title (required)
- category (optional)
- tags (optional, comma-separated)
- access_level (optional, default: "private")

Form Data:
- file: Binary file content

Response:
{
  "doc_id": "uuid",
  "title": "string",
  "category": "string",
  "tags": ["string"],
  "file_type": "string",
  "file_size": 1024,
  "chunk_count": 5,
  "created_at": "2024-03-06T08:47:00Z",
  "updated_at": "2024-03-06T08:47:00Z",
  "created_by": "user-uuid",
  "tenant_id": "tenant-uuid"
}

Validation:
- File type: PDF, DOCX, TXT, HTML, CSV only
- File size: Limited by web server (typically 100MB)
- Title: Required, max 255 chars
```

### 4.3 Hybrid Search
```
POST /api/v1/knowledge/search

Auth: Required

Body:
{
  "query": "enterprise sales strategy",
  "top_k": 10,
  "use_vector": true,
  "use_keyword": true,
  "min_score": 0.3
}

Response:
[
  {
    "chunk_id": "uuid",
    "doc_id": "uuid",
    "title": "string",
    "content": "string",
    "score": 0.85,
    "vector_score": 0.90,
    "keyword_score": 0.75,
    "chunk_index": 0
  }
]

Performance:
- Vector search: ~50-100ms (with index)
- Keyword search: ~200-500ms (in-memory ranking)
- Total: ~250-600ms depending on corpus size
```

### 4.4 FAQ Management

**Create:**
```
POST /api/v1/knowledge/faqs

Body:
{
  "category": "pricing",
  "question": "What is the minimum contract?",
  "answer": "The minimum is $10,000...",
  "tags": ["pricing", "contract"],
  "is_active": true
}

Response: FAQResponse (with faq_id, timestamps, counts)
```

**List:**
```
GET /api/v1/knowledge/faqs?category=pricing&is_active=true&skip=0&limit=50

Query Params:
- category (optional): Filter by category
- is_active (optional): true|false
- skip (default: 0)
- limit (default: 50, max: 200)

Response: List[FAQResponse]
```

**Search:**
```
POST /api/v1/knowledge/faqs/search

Body:
{
  "query": "payment terms",
  "category": null,  // optional
  "top_k": 5
}

Response: List[FAQResponse] (sorted by relevance)

Scoring:
- Question match: 70%
- Answer match: 30%
```

**Update:**
```
PUT /api/v1/knowledge/faqs/{faq_id}

Body: FAQItem (same as create)

Response: FAQResponse
```

**Delete:**
```
DELETE /api/v1/knowledge/faqs/{faq_id}

Response: {"message": "FAQ deleted"}
```

### 4.5 Get Context Chunks
```
POST /api/v1/knowledge/chunks

Auth: Required

Body:
{
  "query": "how to negotiate pricing",
  "top_k": 5
}

Response:
{
  "chunks": [SearchResult, ...],
  "context": "string (concatenated chunks with titles)"
}

Purpose:
- Used by AI chat engine for RAG
- Returns formatted context ready for LLM consumption
```

## 5. Performance Metrics

### 5.1 Expected Performance

| Operation | Latency | Depends On |
|-----------|---------|-----------|
| Document upload | 2-5s | File size, # chunks, OpenAI API |
| List documents | 50-100ms | Filters, pagination |
| Vector search | 50-100ms | Index quality, top_k |
| Keyword search | 200-500ms | Corpus size, in-memory ranking |
| Hybrid search | 250-600ms | Both searches + merging |
| Generate embedding | 100-300ms | OpenAI API latency |
| FAQ search | 50-200ms | FAQ count, in-memory scoring |

### 5.2 Scalability Targets

- **Documents per tenant:** 10,000+
- **Chunks per tenant:** 50,000+
- **Concurrent users:** 100+
- **RPS:** 1,000+ with 3 instances
- **Storage:** 1TB+ (PostgreSQL + backups)

### 5.3 Optimization Strategies

**Vector Search:**
- IVFFlat index with proper nprobe tuning
- Consider pgvector's HNSW in future
- Embedding cache (optional Redis)

**Keyword Search:**
- In-memory ranking scales to ~50k chunks
- For larger corpora, implement full-text index

**General:**
- Connection pooling: 5-20 per instance
- Async I/O throughout
- Batch API calls when possible

## 6. Error Handling

### 6.1 HTTP Status Codes

| Code | Scenario |
|------|----------|
| 200 | Success |
| 400 | Invalid input (malformed JSON, wrong file type) |
| 401 | Missing/invalid JWT token |
| 403 | Not authorized (shouldn't happen with proper RLS) |
| 404 | Resource not found (document, FAQ, etc.) |
| 422 | Validation error (Pydantic) |
| 500 | Server error (database, OpenAI API) |
| 503 | Service unavailable (database down) |

### 6.2 Error Response Format
```json
{
  "detail": "string (error message)"
}
```

### 6.3 Graceful Degradation
- **Embedding API down?** Zero vectors used, keyword search still works
- **Database slow?** Queries timeout after 30s, return error
- **Malformed file?** Try UTF-8 decode, fallback to binary ignore

## 7. Concurrency & Locking

### 7.1 Database Transactions
```python
async with conn.transaction():
    # All operations atomic
    await conn.execute("INSERT ...")
    await conn.execute("UPDATE ...")
    # On exception: auto rollback
```

**Used for:**
- Document upload (insert doc + chunks + stats atomically)
- Document delete (delete doc + chunks + update stats)
- FAQ operations (insert/update stats)

### 7.2 Connection Pooling
```python
pool = await asyncpg.create_pool(
    min_size=5,      # Minimum connections
    max_size=20,     # Maximum connections
    host=..., port=..., database=..., user=..., password=...
)
```

**Behavior:**
- Creates 5 connections on startup
- Grows to 20 if needed
- Recycles idle connections after ~5 min

## 8. Configuration

### 8.1 Environment Variables
```bash
# Required
DB_HOST                 # PostgreSQL host
DB_PORT                 # PostgreSQL port (default: 5432)
DB_NAME                 # Database name
DB_USER                 # Database user
DB_PASSWORD             # Database password
JWT_SECRET              # JWT signing key (min 32 chars)
OPENAI_API_KEY          # OpenAI API key (sk-...)

# Optional
CORS_ORIGINS            # CORS allowed origins (default: *)
CHUNK_SIZE              # Text chunk size (default: 512)
CHUNK_OVERLAP           # Chunk overlap (default: 100)
```

### 8.2 Constants (in code)
```python
SERVICE_PORT = 9030
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
JWT_ALGORITHM = "HS256"
```

## 9. Testing Strategy

### 9.1 Test Coverage
- Health check (no auth required)
- Document CRUD (with tenant isolation)
- Search functionality (vector + keyword)
- FAQ operations
- Auth & error handling

### 9.2 Integration Tests
See `test_integration.py` for examples using pytest + httpx

```bash
pytest test_integration.py -v --tb=short
```

## 10. Monitoring & Observability

### 10.1 Metrics to Track
- API endpoint latency (p50, p95, p99)
- Database query times
- OpenAI API latency
- Error rates by endpoint
- Connection pool usage
- Document count per tenant
- Storage per tenant

### 10.2 Health Checks
```
GET /api/v1/knowledge/health
```
Returns 200 if:
- Database is reachable
- All extensions loaded
- Connection pool healthy

### 10.3 Logging (recommended)
```python
import logging
logger = logging.getLogger("knowledge_service")
logger.info(f"Search query: {query} -> {len(results)} results in {elapsed}ms")
```

## 11. Future Enhancements

**v2.1:**
- Redis embedding cache
- Full-text search index for large datasets
- Batch document upload (async)
- FAQ auto-suggestion from search queries
- Token usage tracking per tenant

**v2.2:**
- HNSW vector index (faster than IVFFlat)
- Multiple embedding models
- Document versioning with diff tracking
- Approval workflows for training data
- Cost tracking per tenant

**v3.0:**
- Multi-modal embeddings (text + images)
- Local LLM fallback for embeddings
- Custom RAG prompts per tenant
- Feedback loop for relevance improvement
- Hybrid chunking strategies (semantic + syntactic)

## 12. Compliance & Security

### 12.1 Data Privacy
- GDPR compliant (can delete data per tenant)
- No third-party tracking
- Secrets never logged
- Database encryption at rest (recommended)

### 12.2 PII Handling
- No special PII handling implemented
- Customers responsible for sanitizing inputs
- Consider regex filtering for emails/SSNs in future

### 12.3 Audit Trail (recommended)
```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    action VARCHAR(50),
    resource_type VARCHAR(50),
    resource_id UUID,
    user_id UUID NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);
```

---

**Document Version:** 1.0  
**Last Updated:** 2024-03-06  
**Maintained By:** Platform Team
