"""
Knowledge Base v2 Service - Multi-tenant RAG with Document Management
Global AI Sales Platform
"""

import os
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from functools import lru_cache

import asyncpg
import jwt
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Query, Header
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import numpy as np
from sqlalchemy import text

from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# ============================================================================
# CONFIG & MODELS
# ============================================================================

app = FastAPI(
    title="Knowledge Base v2",
    version="2.0.0",
    description="Multi-tenant RAG & Document Management Service"
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="knowledge")
init_sentry(service_name="knowledge", service_port=9030)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="knowledge")
app.add_middleware(TracingMiddleware)


# CORS Configuration
cors_origins = os.getenv("CORS_ORIGINS")
if not cors_origins:
    raise RuntimeError("CORS_ORIGINS environment variable must be set")
CORS_ORIGINS = cors_origins.split(",")
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Security
security = HTTPBearer()
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable must be set")
JWT_ALGORITHM = "HS256"

# Database
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    raise RuntimeError("All DB_* environment variables must be set")

# Embeddings
EMBEDDING_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# Service config
SERVICE_PORT = 9030
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AuthContext(BaseModel):
    """JWT Auth context"""
    user_id: str
    tenant_id: str
    email: str
    # ACCESS-CONTROL-FIX: Added role for access level filtering
    role: str = "user"


class DocumentUploadRequest(BaseModel):
    title: str
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    access_level: str = "private"  # private, team, public


class DocumentResponse(BaseModel):
    doc_id: str
    title: str
    category: Optional[str]
    tags: List[str]
    access_level: str
    file_type: str
    file_size: int
    chunk_count: int
    created_at: str
    updated_at: str
    created_by: str
    tenant_id: str


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, le=100)
    use_vector: bool = True
    use_keyword: bool = True
    min_score: float = 0.3


class SearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    content: str
    score: float
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    chunk_index: int


class EmbeddingRequest(BaseModel):
    text: str


class EmbeddingResponse(BaseModel):
    embedding: List[float]
    dimension: int


class FAQItem(BaseModel):
    category: str
    question: str
    answer: str
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True


class FAQResponse(BaseModel):
    faq_id: str
    category: str
    question: str
    answer: str
    tags: List[str]
    is_active: bool
    helpful_count: int
    unhelpful_count: int
    created_at: str
    updated_at: str
    tenant_id: str


class FAQSearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    top_k: int = Field(default=5, le=50)


class ChunksRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, le=20)


class ChunksResponse(BaseModel):
    chunks: List[SearchResult]
    context: str


class StatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_faqs: int
    total_embeddings: int
    categories: Dict[str, int]
    file_types: Dict[str, int]
    storage_bytes: int


# ============================================================================
# DATABASE CONNECTION POOL
# ============================================================================

pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=int(DB_PORT),
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            min_size=5,
            max_size=20,
        )
        # Initialize pgvector extension
        async with pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    return pool


# ============================================================================
# AUTH & HELPERS
# ============================================================================

async def verify_token(credentials: HTTPAuthCredentials = Depends(security)) -> AuthContext:
    """Verify JWT token and extract auth context"""
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        email = payload.get("email")
        # ACCESS-CONTROL-FIX: Extract role for document access filtering
        role = payload.get("role", "user")

        if not all([user_id, tenant_id, email]):
            raise HTTPException(status_code=401, detail="Invalid token")

        return AuthContext(user_id=user_id, tenant_id=tenant_id, email=email, role=role)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_embedding(text: str) -> List[float]:
    """Call external embedding API (OpenAI)"""
    import httpx
    
    if not EMBEDDING_API_KEY:
        raise HTTPException(status_code=500, detail="Embedding API not configured")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            json={"input": text, "model": EMBEDDING_MODEL},
            headers={"Authorization": f"Bearer {EMBEDDING_API_KEY}"},
            timeout=30.0,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Embedding generation failed")
        data = response.json()
        return data["data"][0]["embedding"]


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks"""
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end == text_len:
            break
        start = end - overlap
    
    return chunks if chunks else [text]


def bm25_score(query: str, text: str) -> float:
    """Simple BM25-like keyword scoring"""
    query_terms = query.lower().split()
    text_lower = text.lower()
    matches = sum(1 for term in query_terms if term in text_lower)
    return matches / (len(query_terms) + 1e-6)


def vector_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Cosine similarity between vectors"""
    arr1 = np.array(vec1)
    arr2 = np.array(vec2)
    return float(np.dot(arr1, arr2) / (np.linalg.norm(arr1) * np.linalg.norm(arr2) + 1e-10))


def build_access_control_filter(user_id: str, user_role: str) -> tuple[str, List]:
    """
    # ACCESS-CONTROL-FIX
    Build SQL WHERE clause for document access control based on user role and access_level.
    Returns: (WHERE_clause, params_list)

    Access rules:
    - "public" documents: visible to everyone
    - "team" documents: visible to all authenticated users in the tenant
    - "private" documents: visible only to creator (creator_id = user_id)
    """
    # All users can see public documents
    # Authenticated users can see team documents
    # Only creator can see private documents
    where_clause = """
        (d.access_level = 'public'
         OR d.access_level = 'team'
         OR (d.access_level = 'private' AND d.created_by = $PARAM_USER_ID$))
    """
    params = [user_id]
    return where_clause, params


# ============================================================================
# DATABASE SCHEMA (Auto-initialization)
# ============================================================================

async def init_db(conn: asyncpg.Connection):
    """Initialize database schema"""
    schema = """
    -- Documents table
    CREATE TABLE IF NOT EXISTS documents (
        doc_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        title VARCHAR(255) NOT NULL,
        category VARCHAR(100),
        tags TEXT[],
        access_level VARCHAR(50) DEFAULT 'private',
        file_type VARCHAR(20) NOT NULL,
        file_size BIGINT NOT NULL,
        content TEXT NOT NULL,
        chunk_count INT DEFAULT 0,
        created_by UUID NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(tenant_id, category);
    
    -- Document chunks with embeddings
    CREATE TABLE IF NOT EXISTS document_chunks (
        chunk_id UUID PRIMARY KEY,
        doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
        tenant_id UUID NOT NULL,
        chunk_index INT NOT NULL,
        content TEXT NOT NULL,
        embedding vector(1536),
        created_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON document_chunks(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_id);
    CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops);
    
    -- FAQs
    CREATE TABLE IF NOT EXISTS faqs (
        faq_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL,
        category VARCHAR(100) NOT NULL,
        question VARCHAR(500) NOT NULL,
        answer TEXT NOT NULL,
        tags TEXT[],
        is_active BOOLEAN DEFAULT TRUE,
        helpful_count INT DEFAULT 0,
        unhelpful_count INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_faqs_tenant ON faqs(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_faqs_category ON faqs(tenant_id, category);
    
    -- Knowledge base stats
    CREATE TABLE IF NOT EXISTS kb_stats (
        stat_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL UNIQUE,
        total_documents INT DEFAULT 0,
        total_chunks INT DEFAULT 0,
        total_faqs INT DEFAULT 0,
        total_embeddings INT DEFAULT 0,
        storage_bytes BIGINT DEFAULT 0,
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    for statement in schema.split(";"):
        if statement.strip():
            await conn.execute(statement)


# ============================================================================
# ENDPOINTS: HEALTH & STATS
# ============================================================================

@app.get("/api/v1/knowledge/health")
async def health_check():
    """Health check endpoint"""
    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "healthy", "service": "knowledge-base-v2", "port": SERVICE_PORT}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.get("/api/v1/knowledge/stats", response_model=StatsResponse)
async def get_stats(auth: AuthContext = Depends(verify_token)):
    """Get knowledge base statistics for tenant"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Get or create stats record
        stats = await conn.fetchrow(
            "SELECT * FROM kb_stats WHERE tenant_id = $1",
            uuid.UUID(auth.tenant_id)
        )
        
        if not stats:
            stats_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO kb_stats (stat_id, tenant_id) VALUES ($1, $2)",
                stats_id, uuid.UUID(auth.tenant_id)
            )
            stats = await conn.fetchrow(
                "SELECT * FROM kb_stats WHERE tenant_id = $1",
                uuid.UUID(auth.tenant_id)
            )
        
        # Get category breakdown
        categories = await conn.fetch(
            "SELECT category, COUNT(*) as count FROM documents WHERE tenant_id = $1 AND category IS NOT NULL GROUP BY category",
            uuid.UUID(auth.tenant_id)
        )
        
        # Get file type breakdown
        file_types = await conn.fetch(
            "SELECT file_type, COUNT(*) as count FROM documents WHERE tenant_id = $1 GROUP BY file_type",
            uuid.UUID(auth.tenant_id)
        )
        
        return StatsResponse(
            total_documents=stats["total_documents"],
            total_chunks=stats["total_chunks"],
            total_faqs=stats["total_faqs"],
            total_embeddings=stats["total_embeddings"],
            categories={row["category"]: row["count"] for row in categories if row["category"]},
            file_types={row["file_type"]: row["count"] for row in file_types},
            storage_bytes=stats["storage_bytes"],
        )


# ============================================================================
# ENDPOINTS: DOCUMENT MANAGEMENT
# ============================================================================

@app.post("/api/v1/knowledge/documents", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Query(...),
    category: Optional[str] = Query(None),
    tags: str = Query(""),
    access_level: str = Query("private"),
    auth: AuthContext = Depends(verify_token),
):
    """Upload and process a document"""
    doc_id = uuid.uuid4()
    
    # Validate file type
    allowed_types = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                     "text/plain", "text/html", "text/csv"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    
    # Read and process file with size limit (50MB max)
    MAX_KB_UPLOAD = 50 * 1024 * 1024
    content = await file.read()
    file_size = len(content)
    if file_size > MAX_KB_UPLOAD:
        raise HTTPException(status_code=413, detail="File exceeds 50MB limit")
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    # Extract text from file (simplified - normally use pdf2image, python-docx, etc.)
    try:
        if file.content_type == "text/plain":
            text = content.decode("utf-8")
        elif file.content_type == "text/html":
            import html2text
            text = html2text.html2text(content.decode("utf-8"))
        elif file.content_type == "text/csv":
            text = content.decode("utf-8")
        else:
            text = content.decode("utf-8", errors="ignore")[:5000]  # Fallback
    except Exception as e:
        raise HTTPException(status_code=400, detail="File parsing error")
    
    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    file_type = file.filename.split(".")[-1] if file.filename else "unknown"
    
    # Chunk text
    chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Insert document
            await conn.execute(
                """INSERT INTO documents (doc_id, tenant_id, title, category, tags, access_level, 
                   file_type, file_size, content, chunk_count, created_by, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())""",
                doc_id, uuid.UUID(auth.tenant_id), title, category, tag_list, access_level,
                file_type, file_size, text, len(chunks), uuid.UUID(auth.user_id)
            )
            
            # Insert chunks with embeddings
            for idx, chunk in enumerate(chunks):
                chunk_id = uuid.uuid4()
                try:
                    embedding = await get_embedding(chunk)
                except Exception:
                    embedding = [0.0] * EMBEDDING_DIMENSION  # Fallback to zeros
                
                await conn.execute(
                    """INSERT INTO document_chunks (chunk_id, doc_id, tenant_id, chunk_index, content, embedding, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
                    chunk_id, doc_id, uuid.UUID(auth.tenant_id), idx, chunk, embedding
                )
            
            # Update stats
            await conn.execute(
                """INSERT INTO kb_stats (stat_id, tenant_id, total_documents, total_chunks, storage_bytes)
                   VALUES ($1, $2, 1, $3, $4)
                   ON CONFLICT (tenant_id) DO UPDATE SET 
                   total_documents = total_documents + 1,
                   total_chunks = total_chunks + $3,
                   storage_bytes = storage_bytes + $4""",
                uuid.uuid4(), uuid.UUID(auth.tenant_id), len(chunks), file_size
            )
    
    return DocumentResponse(
        doc_id=str(doc_id),
        title=title,
        category=category,
        tags=tag_list,
        access_level=access_level,
        file_type=file_type,
        file_size=file_size,
        chunk_count=len(chunks),
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
        created_by=auth.user_id,
        tenant_id=auth.tenant_id,
    )


@app.get("/api/v1/knowledge/documents", response_model=List[DocumentResponse])
async def list_documents(
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(verify_token),
):
    """List documents for tenant with access control"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # # ACCESS-CONTROL-FIX: Add access level filtering
        query = """SELECT * FROM documents d
                   WHERE d.tenant_id = $1
                   AND (d.access_level = 'public'
                        OR d.access_level = 'team'
                        OR (d.access_level = 'private' AND d.created_by = $2))"""
        params = [uuid.UUID(auth.tenant_id), uuid.UUID(auth.user_id)]

        if category:
            query += " AND d.category = $3"
            params.append(category)

        query += " ORDER BY d.created_at DESC LIMIT $" + str(len(params) + 1) + " OFFSET $" + str(len(params) + 2)
        params.extend([limit, skip])

        docs = await conn.fetch(query, *params)

        return [
            DocumentResponse(
                doc_id=str(doc["doc_id"]),
                title=doc["title"],
                category=doc["category"],
                tags=doc["tags"] or [],
                access_level=doc["access_level"],
                file_type=doc["file_type"],
                file_size=doc["file_size"],
                chunk_count=doc["chunk_count"],
                created_at=doc["created_at"].isoformat(),
                updated_at=doc["updated_at"].isoformat(),
                created_by=str(doc["created_by"]),
                tenant_id=str(doc["tenant_id"]),
            )
            for doc in docs
        ]


@app.get("/api/v1/knowledge/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, auth: AuthContext = Depends(verify_token)):
    """Get document details with access control"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # # ACCESS-CONTROL-FIX: Enforce access level permissions
        doc = await conn.fetchrow("""
            SELECT * FROM documents
            WHERE doc_id = $1 AND tenant_id = $2
            AND (access_level = 'public'
                 OR access_level = 'team'
                 OR (access_level = 'private' AND created_by = $3))
        """, uuid.UUID(doc_id), uuid.UUID(auth.tenant_id), uuid.UUID(auth.user_id))

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found or access denied")

        return DocumentResponse(
            doc_id=str(doc["doc_id"]),
            title=doc["title"],
            category=doc["category"],
            tags=doc["tags"] or [],
            access_level=doc["access_level"],
            file_type=doc["file_type"],
            file_size=doc["file_size"],
            chunk_count=doc["chunk_count"],
            created_at=doc["created_at"].isoformat(),
            updated_at=doc["updated_at"].isoformat(),
            created_by=str(doc["created_by"]),
            tenant_id=str(doc["tenant_id"]),
        )


@app.delete("/api/v1/knowledge/documents/{doc_id}")
async def delete_document(doc_id: str, auth: AuthContext = Depends(verify_token)):
    """Delete document and associated chunks"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            doc = await conn.fetchrow(
                "SELECT * FROM documents WHERE doc_id = $1 AND tenant_id = $2",
                uuid.UUID(doc_id), uuid.UUID(auth.tenant_id)
            )
            
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Delete chunks
            await conn.execute(
                "DELETE FROM document_chunks WHERE doc_id = $1",
                uuid.UUID(doc_id)
            )
            
            # Delete document
            await conn.execute(
                "DELETE FROM documents WHERE doc_id = $1",
                uuid.UUID(doc_id)
            )
            
            # Update stats
            await conn.execute(
                """UPDATE kb_stats SET 
                   total_documents = total_documents - 1,
                   total_chunks = total_chunks - $1,
                   storage_bytes = storage_bytes - $2
                   WHERE tenant_id = $3""",
                doc["chunk_count"], doc["file_size"], uuid.UUID(auth.tenant_id)
            )
    
    return {"message": "Document deleted"}


# ============================================================================
# ENDPOINTS: SEARCH & EMBEDDINGS
# ============================================================================

@app.post("/api/v1/knowledge/embed", response_model=EmbeddingResponse)
async def generate_embedding(
    request: EmbeddingRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Generate embedding for text"""
    embedding = await get_embedding(request.text)
    return EmbeddingResponse(embedding=embedding, dimension=len(embedding))


@app.post("/api/v1/knowledge/search", response_model=List[SearchResult])
async def hybrid_search(
    request: SearchRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Hybrid search: vector similarity + BM25 keyword search"""
    pool = await get_db_pool()
    
    # Get query embedding
    query_embedding = await get_embedding(request.query)
    
    async with pool.acquire() as conn:
        # # ACCESS-CONTROL-FIX: Vector search with access level filtering
        vector_results = []
        if request.use_vector:
            results = await conn.fetch(
                """SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content,
                   d.title, d.tenant_id,
                   (c.embedding <-> $1::vector) as distance
                   FROM document_chunks c
                   JOIN documents d ON c.doc_id = d.doc_id
                   WHERE c.tenant_id = $2
                   AND (d.access_level = 'public'
                        OR d.access_level = 'team'
                        OR (d.access_level = 'private' AND d.created_by = $4))
                   ORDER BY distance ASC
                   LIMIT $3""",
                query_embedding, uuid.UUID(auth.tenant_id), request.top_k, uuid.UUID(auth.user_id)
            )
            
            for row in results:
                vec_score = 1.0 / (1.0 + row["distance"])
                if vec_score >= request.min_score:
                    vector_results.append({
                        "chunk_id": str(row["chunk_id"]),
                        "doc_id": str(row["doc_id"]),
                        "title": row["title"],
                        "content": row["content"],
                        "vector_score": vec_score,
                        "keyword_score": None,
                        "chunk_index": row["chunk_index"],
                    })
        
        # # ACCESS-CONTROL-FIX: Keyword search with access level filtering
        keyword_results = []
        if request.use_keyword:
            all_chunks = await conn.fetch(
                """SELECT c.chunk_id, c.doc_id, c.chunk_index, c.content, d.title
                   FROM document_chunks c
                   JOIN documents d ON c.doc_id = d.doc_id
                   WHERE c.tenant_id = $1
                   AND (d.access_level = 'public'
                        OR d.access_level = 'team'
                        OR (d.access_level = 'private' AND d.created_by = $2))""",
                uuid.UUID(auth.tenant_id), uuid.UUID(auth.user_id)
            )
            
            scored = []
            for row in all_chunks:
                score = bm25_score(request.query, row["content"])
                if score > 0:
                    scored.append({
                        "chunk_id": str(row["chunk_id"]),
                        "doc_id": str(row["doc_id"]),
                        "title": row["title"],
                        "content": row["content"],
                        "vector_score": None,
                        "keyword_score": score,
                        "chunk_index": row["chunk_index"],
                    })
            
            keyword_results = sorted(scored, key=lambda x: x["keyword_score"], reverse=True)[:request.top_k]
        
        # Merge and deduplicate results
        combined = {}
        for result in vector_results:
            combined[result["chunk_id"]] = result
        for result in keyword_results:
            if result["chunk_id"] in combined:
                combined[result["chunk_id"]]["keyword_score"] = result["keyword_score"]
            else:
                combined[result["chunk_id"]] = result
        
        # Re-rank by combined score
        final_results = []
        for chunk_id, result in combined.items():
            vector_score = result["vector_score"] or 0.0
            keyword_score = result["keyword_score"] or 0.0
            combined_score = (vector_score * 0.6) + (keyword_score * 0.4)
            
            if combined_score >= request.min_score:
                final_results.append(SearchResult(
                    chunk_id=result["chunk_id"],
                    doc_id=result["doc_id"],
                    title=result["title"],
                    content=result["content"],
                    score=combined_score,
                    vector_score=result["vector_score"],
                    keyword_score=result["keyword_score"],
                    chunk_index=result["chunk_index"],
                ))
        
        return sorted(final_results, key=lambda x: x.score, reverse=True)[:request.top_k]


@app.post("/api/v1/knowledge/chunks", response_model=ChunksResponse)
async def get_chunks(
    request: ChunksRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Get context chunks for a query (used by AI engine)"""
    search_request = SearchRequest(
        query=request.query,
        top_k=request.top_k,
        use_vector=True,
        use_keyword=True,
        min_score=0.3
    )
    
    results = await hybrid_search(search_request, auth)
    context = "\n\n".join([f"[{r.title}]\n{r.content}" for r in results])
    
    return ChunksResponse(chunks=results, context=context)


# ============================================================================
# ENDPOINTS: FAQ MANAGEMENT
# ============================================================================

@app.post("/api/v1/knowledge/faqs", response_model=FAQResponse)
async def create_faq(
    request: FAQItem,
    auth: AuthContext = Depends(verify_token),
):
    """Create FAQ"""
    faq_id = uuid.uuid4()
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO faqs (faq_id, tenant_id, category, question, answer, tags, is_active)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                faq_id, uuid.UUID(auth.tenant_id), request.category, request.question,
                request.answer, request.tags, request.is_active
            )
            
            # Update stats
            await conn.execute(
                """INSERT INTO kb_stats (stat_id, tenant_id, total_faqs) VALUES ($1, $2, 1)
                   ON CONFLICT (tenant_id) DO UPDATE SET total_faqs = total_faqs + 1""",
                uuid.uuid4(), uuid.UUID(auth.tenant_id)
            )
    
    return FAQResponse(
        faq_id=str(faq_id),
        category=request.category,
        question=request.question,
        answer=request.answer,
        tags=request.tags,
        is_active=request.is_active,
        helpful_count=0,
        unhelpful_count=0,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
        tenant_id=auth.tenant_id,
    )


@app.get("/api/v1/knowledge/faqs", response_model=List[FAQResponse])
async def list_faqs(
    category: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(verify_token),
):
    """List FAQs for tenant"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = "SELECT * FROM faqs WHERE tenant_id = $1"
        params = [uuid.UUID(auth.tenant_id)]
        
        if category:
            query += " AND category = $2"
            params.append(category)
        
        if is_active is not None:
            query += " AND is_active = $" + str(len(params) + 1)
            params.append(is_active)
        
        query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1) + " OFFSET $" + str(len(params) + 2)
        params.extend([limit, skip])
        
        faqs = await conn.fetch(query, *params)
        
        return [
            FAQResponse(
                faq_id=str(faq["faq_id"]),
                category=faq["category"],
                question=faq["question"],
                answer=faq["answer"],
                tags=faq["tags"] or [],
                is_active=faq["is_active"],
                helpful_count=faq["helpful_count"],
                unhelpful_count=faq["unhelpful_count"],
                created_at=faq["created_at"].isoformat(),
                updated_at=faq["updated_at"].isoformat(),
                tenant_id=str(faq["tenant_id"]),
            )
            for faq in faqs
        ]


@app.put("/api/v1/knowledge/faqs/{faq_id}", response_model=FAQResponse)
async def update_faq(
    faq_id: str,
    request: FAQItem,
    auth: AuthContext = Depends(verify_token),
):
    """Update FAQ"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        faq = await conn.fetchrow(
            "SELECT * FROM faqs WHERE faq_id = $1 AND tenant_id = $2",
            uuid.UUID(faq_id), uuid.UUID(auth.tenant_id)
        )
        
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ not found")
        
        await conn.execute(
            """UPDATE faqs SET category = $1, question = $2, answer = $3, tags = $4, 
               is_active = $5, updated_at = NOW()
               WHERE faq_id = $6""",
            request.category, request.question, request.answer, request.tags,
            request.is_active, uuid.UUID(faq_id)
        )
    
    return FAQResponse(
        faq_id=faq_id,
        category=request.category,
        question=request.question,
        answer=request.answer,
        tags=request.tags,
        is_active=request.is_active,
        helpful_count=faq["helpful_count"],
        unhelpful_count=faq["unhelpful_count"],
        created_at=faq["created_at"].isoformat(),
        updated_at=datetime.utcnow().isoformat(),
        tenant_id=str(faq["tenant_id"]),
    )


@app.delete("/api/v1/knowledge/faqs/{faq_id}")
async def delete_faq(faq_id: str, auth: AuthContext = Depends(verify_token)):
    """Delete FAQ"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            faq = await conn.fetchrow(
                "SELECT * FROM faqs WHERE faq_id = $1 AND tenant_id = $2",
                uuid.UUID(faq_id), uuid.UUID(auth.tenant_id)
            )
            
            if not faq:
                raise HTTPException(status_code=404, detail="FAQ not found")
            
            await conn.execute("DELETE FROM faqs WHERE faq_id = $1", uuid.UUID(faq_id))
            
            # Update stats
            await conn.execute(
                "UPDATE kb_stats SET total_faqs = total_faqs - 1 WHERE tenant_id = $1",
                uuid.UUID(auth.tenant_id)
            )
    
    return {"message": "FAQ deleted"}


@app.post("/api/v1/knowledge/faqs/search", response_model=List[FAQResponse])
async def search_faqs(
    request: FAQSearchRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Search FAQs by keyword"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        faqs = await conn.fetch(
            "SELECT * FROM faqs WHERE tenant_id = $1 AND is_active = TRUE",
            uuid.UUID(auth.tenant_id)
        )
        
        # Score FAQs
        scored = []
        for faq in faqs:
            if request.category and faq["category"] != request.category:
                continue
            
            q_score = bm25_score(request.query, faq["question"])
            a_score = bm25_score(request.query, faq["answer"])
            score = (q_score * 0.7) + (a_score * 0.3)
            
            if score > 0:
                scored.append((faq, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [
            FAQResponse(
                faq_id=str(faq["faq_id"]),
                category=faq["category"],
                question=faq["question"],
                answer=faq["answer"],
                tags=faq["tags"] or [],
                is_active=faq["is_active"],
                helpful_count=faq["helpful_count"],
                unhelpful_count=faq["unhelpful_count"],
                created_at=faq["created_at"].isoformat(),
                updated_at=faq["updated_at"].isoformat(),
                tenant_id=str(faq["tenant_id"]),
            )
            for faq, _ in scored[:request.top_k]
        ]


# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize database and pool"""
    global pool

    await event_bus.startup()
    pool = await get_db_pool()
    
    # Initialize schema
    async with pool.acquire() as conn:
        await init_db(conn)


@app.on_event("shutdown")
async def shutdown():
    """Close database pool"""
    global pool
    shutdown_tracing()

    await event_bus.shutdown()
    if pool:
        await pool.close()


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT, log_level="info")
