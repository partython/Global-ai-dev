# Conversation Intelligence Service - Architecture Guide

## System Overview

The Conversation Intelligence Service is a multi-tenant SaaS microservice providing real-time conversation analysis, sales intelligence, and coaching insights for the Global AI Sales Platform.

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                       │
│  (Web App, Mobile, Admin Dashboard, Agent Tools)            │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTPS + JWT Bearer Token
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Application (Port 9028)                 │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Middleware                                          │  │
│  │  - CORS Validation                                   │  │
│  │  - JWT Authentication                               │  │
│  │  - Request Logging                                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Routes (v1)                                     │  │
│  │  - /api/v1/intel/analyze                            │  │
│  │  - /api/v1/intel/conversation/*                     │  │
│  │  - /api/v1/intel/sentiment/*                        │  │
│  │  - /api/v1/intel/topics                             │  │
│  │  - /api/v1/intel/keywords                           │  │
│  │  - /api/v1/intel/summarize/*                        │  │
│  │  - /api/v1/intel/coaching/*                         │  │
│  │  - /api/v1/intel/opportunities                      │  │
│  │  - /api/v1/intel/trends                             │  │
│  │  - /api/v1/intel/health                             │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                    │
│          ┌──────────────┼──────────────┐                    │
│          ▼              ▼              ▼                    │
│  ┌────────────┐ ┌──────────┐ ┌──────────────┐             │
│  │ Analysis   │ │ Database │ │ LLM APIs     │             │
│  │ Engines    │ │ Layer    │ │ (Fallback)   │             │
│  └────────────┘ └──────────┘ └──────────────┘             │
│                                                              │
│  Analysis Engines:                                           │
│  - Sentiment Analysis (keyword-based)                       │
│  - Topic Extraction                                         │
│  - Intent Classification                                    │
│  - Key Moments Detection                                    │
│  - Pain Point Extraction                                    │
│  - Competitor Mention Detection                             │
│  - Talk Ratio Calculation                                   │
│                                                              │
└──────────┬───────────────────────────┬──────────────────────┘
           │                           │
           ▼ (asyncpg pool)            ▼ (aiohttp)
┌──────────────────────────┐ ┌──────────────────────────────┐
│  PostgreSQL Database     │ │  External LLM APIs           │
│  (Multi-tenant with RLS) │ │                              │
│                          │ │  1. Anthropic (Claude)       │
│  Tables:                 │ │     - Text summarization     │
│  - conversations         │ │     - Coaching suggestions   │
│  - sentiment_timeline    │ │                              │
│  - conversation_analysis │ │  2. OpenAI (GPT-4)          │
│  - agent_metrics         │ │     - Fallback if Claude     │
│  - sales_opportunities   │ │       unavailable            │
│                          │ │                              │
│  Indexes:                │ │  3. Local fallback           │
│  - tenant_id (RLS)       │ │     - Mock responses         │
│  - conversation_id       │ │                              │
│  - agent_id              │ └──────────────────────────────┘
│  - created_at            │
│                          │
└──────────────────────────┘
```

## Core Components

### 1. Authentication & Security

**AuthContext Class**
```python
tenant_id: str          # Multi-tenant isolation
user_id: str            # User identification
roles: List[str]        # Role-based access control
```

**JWT Token Verification**
- Uses PyJWT for token validation
- Extracts tenant_id for query filtering
- Supports role-based authorization
- HTTPBearer scheme for API

**Row-Level Security (RLS)**
- All queries filtered by `tenant_id`
- Prevents cross-tenant data access
- Enforced at database layer

### 2. Analysis Engines

#### Sentiment Analysis
- **Algorithm**: Keyword-based scoring
- **Positive Words**: good, great, excellent, amazing, love, perfect
- **Negative Words**: bad, terrible, awful, hate, poor, horrible
- **Output**: sentiment (positive/neutral/negative), score (0.0-1.0), confidence

#### Topic Extraction
- **Keywords**: pricing, product, service, delivery, quality, integration
- **Method**: Pattern matching on message text
- **Output**: topic list with message indices

#### Intent Classification
- **Intents**: buy, inquire, complain, return, escalate
- **Pattern Matching**: Keywords per intent category
- **Fallback**: Default to 'inquire'

#### Key Moments Detection
- **Objections**: "but", "however", "concerned", "doubt"
- **Buying Signals**: "ready", "let's go", "sign", "proceed"
- **Escalation**: "angry", "frustrated", "complaint"
- **Confidence**: 0.8 static (can be AI-enhanced)

#### Sales Metrics
- **Talk Ratio**: agent_words / (agent_words + customer_words)
- **Response Time**: avg time between customer message and agent reply
- **Competitor Mentions**: Exact string matching against known competitors
- **Pain Points**: Customer-only messages with pain keywords

### 3. Database Layer

**Connection Management**
- AsyncPG connection pool (5-20 connections)
- Automatic connection recycling
- Query timeout: 60 seconds
- Lazy initialization on app startup

**Data Persistence**
- Conversation storage with full message history
- Per-message sentiment scoring
- Aggregated analysis results
- Agent performance metrics
- Sales opportunity tracking

**Query Patterns**
- Parameterized queries (prevent SQL injection)
- Tenant-based filtering in all SELECT queries
- Bulk inserts for performance
- Conflict handling for updates (UPSERT)

### 4. LLM Integration

**Fallback Pattern**
1. Try Anthropic Claude (primary)
2. Fallback to OpenAI GPT-4 (secondary)
3. Return mock response (tertiary)

**Use Cases**
- Conversation summarization (200-500 tokens)
- Coaching suggestion generation
- Pain point extraction
- Best practice identification

**Error Handling**
- API timeout: 30 seconds
- Network error recovery
- Graceful degradation

### 5. API Layers

#### Synchronous Request Flow
```
POST /api/v1/intel/analyze
    ├─ JWT Validation ✓
    ├─ Tenant RLS ✓
    ├─ Store conversation
    ├─ Sentiment analysis (per message)
    ├─ Topic extraction
    ├─ Intent classification
    ├─ Key moments detection
    ├─ Sales metrics calculation
    ├─ Database persistence
    └─ Return ConversationAnalysis
```

#### Asynchronous Operations
- All database operations (asyncpg)
- All HTTP calls to LLM APIs (aiohttp)
- Concurrent processing via async/await

## Data Flow

### 1. Conversation Analysis Workflow

```
Input: ConversationAnalysisRequest
  │
  ├─ Parse messages (agent & customer)
  │
  ├─ For each message:
  │  ├─ Sentiment analysis
  │  ├─ Topic extraction
  │  ├─ Competitor mention detection
  │  └─ Store in sentiment_timeline table
  │
  ├─ Aggregate analysis:
  │  ├─ Topic distribution
  │  ├─ Intent classification
  │  ├─ Key moments detection
  │  ├─ Pain points extraction
  │  └─ Sales metrics (talk ratio, response time)
  │
  ├─ Store in conversation_analysis table
  │
  ├─ Detect opportunities:
  │  └─ Create sales_opportunities records
  │
  └─ Return: ConversationAnalysis response
```

### 2. Agent Coaching Workflow

```
GET /api/v1/intel/coaching/{agent_id}
  │
  ├─ Fetch agent metrics (if exists)
  │
  ├─ Fallback: Calculate from conversations
  │  ├─ Count total conversations
  │  ├─ Calculate average sentiment
  │  ├─ Extract objection patterns
  │  ├─ Identify improvement areas
  │  └─ Recognize strengths
  │
  └─ Return: AgentCoachingInsight
```

### 3. Reporting Workflows

**Topic Distribution**
```
GET /api/v1/intel/topics?days=30
  │
  ├─ Query conversation_analysis for past 30 days
  ├─ Extract topics array from each row
  ├─ Count occurrences per topic
  └─ Return: {topic: count, ...}
```

**Keyword Analysis**
```
GET /api/v1/intel/keywords?days=30
  │
  ├─ Query conversations for past 30 days
  ├─ Extract all messages
  ├─ Tokenize into words
  ├─ Filter: len > 3, exclude stop words
  ├─ Count frequency per keyword
  └─ Return: Top 20 keywords
```

**Conversation Trends**
```
GET /api/v1/intel/trends?days=30
  │
  ├─ GROUP BY DATE(created_at)
  ├─ Calculate:
  │  ├─ Conversation count
  │  ├─ Average sentiment (positive ratio)
  │  └─ Top topics per day
  │
  └─ Return: [{date, count, sentiment, topics}, ...]
```

## Performance Characteristics

### Query Performance

**Indexed Queries** (< 50ms typical)
- `WHERE tenant_id = ? AND conversation_id = ?`
- `WHERE tenant_id = ? AND agent_id = ?`
- `WHERE tenant_id = ? AND created_at > ?`

**Aggregation Queries** (100-500ms typical)
- Topic distribution (GROUP BY on JSONB)
- Keyword frequency (JSON array expansion)
- Trend analysis (GROUP BY DATE)

**LLM API Calls** (2-10 seconds typical)
- Summarization: ~3 seconds
- Coaching suggestions: ~2-5 seconds

### Scalability

**Horizontal Scaling**
- Multiple service instances (3+ recommended)
- Load balancer (nginx, HAProxy)
- Stateless design (no local session storage)
- Database connection pooling across instances

**Vertical Scaling**
- Increase asyncpg pool size for high concurrency
- PostgreSQL shared buffers optimization
- Query result caching (Redis optional)

**Database Optimization**
- Partitioning by tenant_id (future enhancement)
- Index optimization based on query patterns
- Connection pooling with PgBouncer
- Read replicas for reporting queries

## Security Architecture

### Tenant Isolation

**Multi-Tenant Pattern**
```sql
-- Every query follows this pattern:
SELECT * FROM table WHERE tenant_id = $1 AND ...

-- Prevention of cross-tenant access
-- Enforced at application and DB levels
```

**JWT Claims**
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "roles": ["admin"]
}
```

### API Security

**Authentication**
- HTTPBearer token scheme
- JWT signature verification (HS256)
- Token expiration (external to service)

**Authorization**
- Role-based access control (future enhancement)
- Tenant-based resource filtering
- No direct ID manipulation allowed

**Data Protection**
- Parameterized SQL (no injection)
- CORS origin validation
- HTTPS enforcement (in production)

### Secrets Management

**Never Hardcoded**
```python
# Correct ✓
api_key = os.getenv("ANTHROPIC_API_KEY")

# Wrong ✗
api_key = "sk-ant-xxx"
```

**Environment Variables**
- JWT_SECRET_KEY (change per environment)
- DATABASE_URL (credentials in URL)
- API keys (Anthropic, OpenAI)
- CORS_ORIGINS (production domain)

## Deployment Patterns

### Local Development
```bash
docker-compose up  # PostgreSQL + Service
```

### Containerized (Docker)
```bash
docker build -t conv-intel:v1
docker run -p 9028:9028 --env-file .env conv-intel:v1
```

### Orchestrated (Kubernetes)
```bash
kubectl apply -f deployment.yaml
# 3 replicas, auto-scaling, health checks
```

### Traditional (Systemd)
```bash
systemctl start conversation-intel
systemctl status conversation-intel
```

## Monitoring & Observability

### Health Checks
```
GET /api/v1/intel/health
```

**Response**
```json
{
  "status": "healthy",
  "service": "Conversation Intelligence",
  "version": "1.0.0",
  "timestamp": "2026-03-06T10:30:00Z"
}
```

### Logging
- StandardOutput: Structured JSON (recommended)
- StandardError: Error tracking
- Log Aggregation: ELK, Datadog, CloudWatch

### Metrics (Future Enhancement)
- Request latency histogram
- Database pool utilization
- API call success/failure rates
- Sentiment distribution timeline
- Top keywords trend

## Future Enhancements

1. **ML-Based Analysis**
   - Replace keyword-based sentiment with transformer model
   - Intent classification with NER/sequence classification
   - Entity extraction (company names, products, prices)

2. **Advanced Caching**
   - Redis for query results
   - Agent metrics cache with TTL
   - Topic distribution cache

3. **Real-Time Processing**
   - WebSocket connections for live analysis
   - Event streaming (Kafka) for message ingestion
   - Real-time dashboard updates

4. **Enhanced Reporting**
   - Time-series data aggregation
   - Custom report generation
   - Export to CSV/Excel
   - Scheduled reports via email

5. **AI Coaching**
   - Personalized recommendations per agent
   - Training content recommendations
   - Skill gap analysis

6. **Compliance & Audit**
   - Audit logging for all data access
   - Data retention policies
   - GDPR right-to-be-forgotten support
   - Conversation anonymization

## Testing Strategy

**Unit Tests**
- Individual analysis functions (sentiment, topics, intent)
- Database query parameterization
- Error handling

**Integration Tests**
- Full conversation analysis flow
- API endpoint validation
- Database round-trip verification

**Load Tests**
- 100+ concurrent conversations
- Query performance under load
- Database connection pool behavior

**Security Tests**
- JWT validation edge cases
- SQL injection attempts
- Cross-tenant access prevention
- CORS origin validation

## Documentation References

- **README.md**: Feature overview and usage
- **DEPLOYMENT.md**: Production deployment guide
- **ARCHITECTURE.md**: This document
- **Code Comments**: Inline documentation

---

**Last Updated**: 2026-03-06  
**Version**: 1.0.0  
**Maintainer**: Global AI Sales Platform Team
