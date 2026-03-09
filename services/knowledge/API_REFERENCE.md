# Knowledge Base v2 - API Reference

Base URL: `http://localhost:9030/api/v1/knowledge`

**Authentication:** All endpoints except `/health` require `Authorization: Bearer <JWT_TOKEN>` header.

---

## Health Check

### GET /health
Check service health and database connectivity.

**Auth:** Not required

**Response:**
```json
{
  "status": "healthy",
  "service": "knowledge-base-v2",
  "port": 9030
}
```

**Status Codes:**
- `200` - Healthy
- `503` - Service unavailable (database down)

---

## Statistics

### GET /stats
Get knowledge base statistics for the authenticated tenant.

**Auth:** Required (JWT)

**Response:**
```json
{
  "total_documents": 42,
  "total_chunks": 215,
  "total_faqs": 8,
  "total_embeddings": 215,
  "categories": {
    "training": 15,
    "product": 20,
    "support": 7
  },
  "file_types": {
    "txt": 20,
    "pdf": 15,
    "docx": 7
  },
  "storage_bytes": 5242880
}
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized

---

## Document Management

### POST /documents
Upload a new document.

**Auth:** Required

**Query Parameters:**
| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| title | string | Yes | — | Max 255 chars |
| category | string | No | null | Free-form category |
| tags | string | No | "" | Comma-separated |
| access_level | string | No | "private" | private, team, public |

**Form Data:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| file | file | Yes | PDF, DOCX, TXT, HTML, or CSV |

**Example:**
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/documents \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf" \
  -F "title=Sales Playbook" \
  -F "category=training" \
  -F "tags=sales,2024,enterprise"
```

**Response:**
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Sales Playbook",
  "category": "training",
  "tags": ["sales", "2024", "enterprise"],
  "access_level": "private",
  "file_type": "pdf",
  "file_size": 1024000,
  "chunk_count": 12,
  "created_at": "2024-03-06T08:47:00Z",
  "updated_at": "2024-03-06T08:47:00Z",
  "created_by": "user-uuid",
  "tenant_id": "tenant-uuid"
}
```

**Status Codes:**
- `200` - Document uploaded successfully
- `400` - Invalid file type or malformed request
- `401` - Unauthorized
- `422` - Validation error

---

### GET /documents
List all documents for the tenant.

**Auth:** Required

**Query Parameters:**
| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| category | string | null | Filter by category |
| skip | integer | 0 | Pagination offset |
| limit | integer | 20 | Max 100 results |

**Example:**
```bash
curl -X GET "http://localhost:9030/api/v1/knowledge/documents?category=training&skip=0&limit=20" \
  -H "Authorization: Bearer <token>"
```

**Response:**
```json
[
  {
    "doc_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Sales Playbook",
    "category": "training",
    "tags": ["sales", "2024"],
    "access_level": "private",
    "file_type": "pdf",
    "file_size": 1024000,
    "chunk_count": 12,
    "created_at": "2024-03-06T08:47:00Z",
    "updated_at": "2024-03-06T08:47:00Z",
    "created_by": "user-uuid",
    "tenant_id": "tenant-uuid"
  }
]
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized

---

### GET /documents/{doc_id}
Get details of a specific document.

**Auth:** Required

**Path Parameters:**
| Parameter | Type | Notes |
|-----------|------|-------|
| doc_id | UUID | Document ID |

**Example:**
```bash
curl -X GET http://localhost:9030/api/v1/knowledge/documents/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer <token>"
```

**Response:**
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Sales Playbook",
  "category": "training",
  "tags": ["sales", "2024"],
  "access_level": "private",
  "file_type": "pdf",
  "file_size": 1024000,
  "chunk_count": 12,
  "created_at": "2024-03-06T08:47:00Z",
  "updated_at": "2024-03-06T08:47:00Z",
  "created_by": "user-uuid",
  "tenant_id": "tenant-uuid"
}
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized
- `404` - Document not found

---

### DELETE /documents/{doc_id}
Delete a document and its chunks.

**Auth:** Required

**Path Parameters:**
| Parameter | Type |
|-----------|------|
| doc_id | UUID |

**Example:**
```bash
curl -X DELETE http://localhost:9030/api/v1/knowledge/documents/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer <token>"
```

**Response:**
```json
{
  "message": "Document deleted"
}
```

**Status Codes:**
- `200` - Document deleted
- `401` - Unauthorized
- `404` - Document not found

---

## Search & Embeddings

### POST /embed
Generate embeddings for a text string.

**Auth:** Required

**Body:**
```json
{
  "text": "The best enterprise sales strategies focus on value-based selling"
}
```

**Example:**
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/embed \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"text": "enterprise sales"}'
```

**Response:**
```json
{
  "embedding": [0.001, 0.002, ..., 0.999],  // 1536-dimensional vector
  "dimension": 1536
}
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized
- `500` - Embedding generation failed (check OpenAI API)

---

### POST /search
Hybrid search combining vector similarity and keyword matching.

**Auth:** Required

**Body:**
```json
{
  "query": "how to close enterprise deals",
  "top_k": 10,
  "use_vector": true,
  "use_keyword": true,
  "min_score": 0.3
}
```

**Body Parameters:**
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| query | string | Required | Search query |
| top_k | integer | 10 | Results to return (max 100) |
| use_vector | boolean | true | Enable vector similarity |
| use_keyword | boolean | true | Enable keyword search |
| min_score | float | 0.3 | Minimum relevance (0.0-1.0) |

**Example:**
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "enterprise pricing strategy",
    "top_k": 5,
    "min_score": 0.5
  }'
```

**Response:**
```json
[
  {
    "chunk_id": "660f9511-f3ac-52e5-b827-557766551111",
    "doc_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Sales Playbook",
    "content": "Enterprise pricing typically follows value-based models...",
    "score": 0.87,
    "vector_score": 0.92,
    "keyword_score": 0.78,
    "chunk_index": 3
  },
  {
    "chunk_id": "770g0622-g4bd-63f6-c938-668877662222",
    "doc_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Sales Playbook",
    "content": "Consider multi-year contracts with volume discounts...",
    "score": 0.72,
    "vector_score": 0.68,
    "keyword_score": 0.82,
    "chunk_index": 5
  }
]
```

**Score Calculation:**
```
combined_score = (vector_score * 0.6) + (keyword_score * 0.4)
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized
- `500` - Vector/keyword search error

---

### POST /chunks
Get context chunks for a query (used by AI engine for RAG).

**Auth:** Required

**Body:**
```json
{
  "query": "contract negotiation best practices",
  "top_k": 5
}
```

**Body Parameters:**
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| query | string | Required | Query string |
| top_k | integer | 5 | Max 20 chunks |

**Example:**
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/chunks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query": "negotiation tactics", "top_k": 5}'
```

**Response:**
```json
{
  "chunks": [
    {
      "chunk_id": "...",
      "doc_id": "...",
      "title": "Sales Playbook",
      "content": "Always ask for next steps...",
      "score": 0.89,
      "vector_score": 0.91,
      "keyword_score": 0.85,
      "chunk_index": 2
    }
  ],
  "context": "[Sales Playbook]\nAlways ask for next steps...\n\n[Training Guide]\nNegotiation begins with..."
}
```

**Purpose:**
Use the `context` field as input to your LLM/AI engine for RAG. It's pre-formatted with titles and concatenated chunks.

**Status Codes:**
- `200` - Success
- `401` - Unauthorized

---

## FAQ Management

### POST /faqs
Create a new FAQ.

**Auth:** Required

**Body:**
```json
{
  "category": "pricing",
  "question": "What payment terms do you offer?",
  "answer": "We offer monthly, quarterly, and annual billing with net-30 payment terms.",
  "tags": ["pricing", "payment", "billing"],
  "is_active": true
}
```

**Body Parameters:**
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| category | string | Yes | FAQ category |
| question | string | Yes | Max 500 chars |
| answer | string | Yes | FAQ answer |
| tags | array | No | Tags for filtering |
| is_active | boolean | No | Default: true |

**Example:**
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/faqs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "pricing",
    "question": "What is your minimum contract value?",
    "answer": "The minimum contract is $10,000 annually.",
    "tags": ["pricing"],
    "is_active": true
  }'
```

**Response:**
```json
{
  "faq_id": "880h1733-h5ce-74g7-d949-779988773333",
  "category": "pricing",
  "question": "What is your minimum contract value?",
  "answer": "The minimum contract is $10,000 annually.",
  "tags": ["pricing"],
  "is_active": true,
  "helpful_count": 0,
  "unhelpful_count": 0,
  "created_at": "2024-03-06T09:00:00Z",
  "updated_at": "2024-03-06T09:00:00Z",
  "tenant_id": "tenant-uuid"
}
```

**Status Codes:**
- `200` - FAQ created
- `401` - Unauthorized
- `422` - Validation error

---

### GET /faqs
List FAQs for the tenant.

**Auth:** Required

**Query Parameters:**
| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| category | string | null | Filter by category |
| is_active | boolean | null | Filter by active status |
| skip | integer | 0 | Pagination offset |
| limit | integer | 50 | Max 200 results |

**Example:**
```bash
curl -X GET "http://localhost:9030/api/v1/knowledge/faqs?category=pricing&is_active=true&limit=10" \
  -H "Authorization: Bearer <token>"
```

**Response:**
```json
[
  {
    "faq_id": "880h1733-h5ce-74g7-d949-779988773333",
    "category": "pricing",
    "question": "What is your minimum contract value?",
    "answer": "The minimum contract is $10,000 annually.",
    "tags": ["pricing"],
    "is_active": true,
    "helpful_count": 3,
    "unhelpful_count": 0,
    "created_at": "2024-03-06T09:00:00Z",
    "updated_at": "2024-03-06T09:00:00Z",
    "tenant_id": "tenant-uuid"
  }
]
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized

---

### PUT /faqs/{faq_id}
Update an existing FAQ.

**Auth:** Required

**Path Parameters:**
| Parameter | Type |
|-----------|------|
| faq_id | UUID |

**Body:**
```json
{
  "category": "pricing",
  "question": "What is your minimum contract value?",
  "answer": "The minimum contract is now $15,000 annually.",
  "tags": ["pricing", "updated"],
  "is_active": true
}
```

**Example:**
```bash
curl -X PUT http://localhost:9030/api/v1/knowledge/faqs/880h1733-h5ce-74g7-d949-779988773333 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "pricing",
    "question": "What is your minimum contract value?",
    "answer": "The minimum contract is now $15,000 annually.",
    "tags": ["pricing"],
    "is_active": true
  }'
```

**Response:**
```json
{
  "faq_id": "880h1733-h5ce-74g7-d949-779988773333",
  "category": "pricing",
  "question": "What is your minimum contract value?",
  "answer": "The minimum contract is now $15,000 annually.",
  "tags": ["pricing"],
  "is_active": true,
  "helpful_count": 3,
  "unhelpful_count": 0,
  "created_at": "2024-03-06T09:00:00Z",
  "updated_at": "2024-03-06T09:15:00Z",
  "tenant_id": "tenant-uuid"
}
```

**Status Codes:**
- `200` - FAQ updated
- `401` - Unauthorized
- `404` - FAQ not found
- `422` - Validation error

---

### DELETE /faqs/{faq_id}
Delete an FAQ.

**Auth:** Required

**Path Parameters:**
| Parameter | Type |
|-----------|------|
| faq_id | UUID |

**Example:**
```bash
curl -X DELETE http://localhost:9030/api/v1/knowledge/faqs/880h1733-h5ce-74g7-d949-779988773333 \
  -H "Authorization: Bearer <token>"
```

**Response:**
```json
{
  "message": "FAQ deleted"
}
```

**Status Codes:**
- `200` - FAQ deleted
- `401` - Unauthorized
- `404` - FAQ not found

---

### POST /faqs/search
Search FAQs by keyword.

**Auth:** Required

**Body:**
```json
{
  "query": "payment terms",
  "category": "pricing",
  "top_k": 5
}
```

**Body Parameters:**
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| query | string | Required | Search query |
| category | string | null | Filter by category |
| top_k | integer | 5 | Max 50 results |

**Example:**
```bash
curl -X POST http://localhost:9030/api/v1/knowledge/faqs/search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "minimum contract value",
    "top_k": 5
  }'
```

**Response:**
```json
[
  {
    "faq_id": "880h1733-h5ce-74g7-d949-779988773333",
    "category": "pricing",
    "question": "What is your minimum contract value?",
    "answer": "The minimum contract is $10,000 annually.",
    "tags": ["pricing"],
    "is_active": true,
    "helpful_count": 3,
    "unhelpful_count": 0,
    "created_at": "2024-03-06T09:00:00Z",
    "updated_at": "2024-03-06T09:00:00Z",
    "tenant_id": "tenant-uuid"
  }
]
```

**Scoring:**
```
score = (question_match * 0.7) + (answer_match * 0.3)
```

**Status Codes:**
- `200` - Success
- `401` - Unauthorized

---

## Error Handling

All error responses follow this format:

```json
{
  "detail": "Error description"
}
```

### Common Errors

**401 Unauthorized**
```json
{
  "detail": "Invalid token"
}
```
**Fix:** Ensure `Authorization: Bearer <token>` header is present and token is valid.

**404 Not Found**
```json
{
  "detail": "Document not found"
}
```
**Fix:** Verify resource ID exists and belongs to your tenant.

**422 Validation Error**
```json
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```
**Fix:** Check request body format matches API specification.

**500 Server Error**
```json
{
  "detail": "Database connection failed"
}
```
**Fix:** Check service logs, verify database is running.

---

## Pagination

Use `skip` and `limit` for pagination:

```bash
# Page 1 (first 20)
curl "http://localhost:9030/api/v1/knowledge/documents?skip=0&limit=20"

# Page 2 (next 20)
curl "http://localhost:9030/api/v1/knowledge/documents?skip=20&limit=20"

# Page 3
curl "http://localhost:9030/api/v1/knowledge/documents?skip=40&limit=20"
```

---

## Rate Limiting

**Currently:** No built-in rate limiting. Implement at gateway level (Nginx, ALB, API Gateway).

**Recommended:**
- 1,000 requests/minute per tenant
- 100 requests/minute for search endpoints

---

## Batch Operations

**Document Bulk Upload:** Use `/documents` endpoint in a loop with minimal delay between requests.

**FAQ Bulk Create:** Implement in your client; API doesn't have batch endpoint yet.

---

## Versioning

**Current API Version:** v1  
**Breaking Changes:** Will increment to v2 (e.g., `/api/v2/knowledge/...`)

---

**Last Updated:** 2024-03-06  
**Next Review:** 2024-04-06
