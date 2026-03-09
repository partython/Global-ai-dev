# Conversation Intelligence Service

## Overview

Enterprise-grade conversation intelligence service for the Global AI Sales Platform. Provides real-time sentiment analysis, topic extraction, sales intelligence, and AI-powered coaching insights across multi-tenant environments.

**Service**: Conversation Intelligence  
**Port**: 9028 (configurable via `CONV_INTEL_PORT`)  
**Framework**: FastAPI with async/await  
**Database**: PostgreSQL with asyncpg  
**Auth**: JWT Bearer tokens with tenant-based RLS

## Features

### 1. Conversation Analytics
- **Real-time Sentiment Analysis**: Per-message sentiment scoring (positive/neutral/negative)
- **Topic Extraction**: Automatic topic categorization from conversation content
- **Intent Classification**: Buyer intent detection (buy, inquire, complain, return, escalate)
- **Conversation Summarization**: AI-powered summaries using Claude/GPT-4
- **Key Moments Detection**: Identifies objections, buying signals, escalation triggers

### 2. Sales Intelligence
- **Talk-to-Listen Ratio**: Agent vs customer speaking time analysis
- **Response Time Tracking**: Average agent response latency
- **Competitor Mention Detection**: Identifies competitor references
- **Objection Pattern Recognition**: Tracks common objection types
- **Upsell/Cross-sell Opportunity Detection**: Identifies buying signals
- **Customer Pain Point Extraction**: Extracts recurring pain points

### 3. Coaching & Training
- **Agent Performance Scoring**: Conversation-level performance metrics
- **Best Practice Pattern Identification**: Extracts successful patterns
- **Coaching Suggestions**: AI-generated coaching recommendations
- **Conversation Quality Scoring**: Empathy, resolution, professionalism metrics

### 4. Reporting
- **Conversation Trend Analysis**: Trends over configurable time periods
- **Topic Distribution**: Topic frequency analysis
- **Sentiment Trends**: Sentiment tracking per customer/agent
- **Keyword Frequency Analysis**: High-value keyword extraction

## API Endpoints

### Analysis & Intelligence
- `POST /api/v1/intel/analyze` — Analyze a conversation
- `GET /api/v1/intel/conversation/{conversation_id}` — Get analysis results
- `GET /api/v1/intel/sentiment/{conversation_id}` — Sentiment timeline
- `GET /api/v1/intel/topics` — Topic distribution
- `GET /api/v1/intel/keywords` — Keyword analysis
- `POST /api/v1/intel/summarize/{conversation_id}` — Generate AI summary

### Coaching & Performance
- `GET /api/v1/intel/coaching/{agent_id}` — Agent coaching insights
- `GET /api/v1/intel/opportunities` — Sales opportunities detected

### Analytics
- `GET /api/v1/intel/trends` — Conversation trends
- `GET /api/v1/intel/health` — Health check

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost/aisales

# Service Configuration
CONV_INTEL_PORT=9028
JWT_SECRET_KEY=your-secret-key-change-in-production

# AI/LLM APIs (optional - fallback pattern)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# CORS Configuration
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
```

## Database Schema

### Tables (All with Tenant RLS)

**conversations**
- Multi-tenant conversation storage
- Messages in JSONB format
- Metadata for custom fields
- Timestamps for auditing

**sentiment_timeline**
- Per-message sentiment scores
- Confidence metrics
- Indexed for fast retrieval

**conversation_analysis**
- Aggregated analysis results
- Topics, intents, key moments
- Sales metrics (objections, opportunities)
- Pain points extraction

**agent_metrics**
- Agent-level aggregated metrics
- Performance scores
- Objection patterns
- Last updated tracking

**sales_opportunities**
- Detected sales opportunities
- Opportunity types and confidence
- Recommendations

**Indexes**
- tenant_id (RLS enforcement)
- conversation_id (fast lookups)
- agent_id (agent metrics)
- created_at (time-based queries)

## Authentication & Security

### JWT Token Format
```json
{
  "tenant_id": "uuid-here",
  "user_id": "user-id-here",
  "roles": ["admin", "analyst"]
}
```

### Row-Level Security (RLS)
All queries filter by `tenant_id` from JWT token. No cross-tenant data leakage possible.

### API Security
- HTTPBearer token validation
- JWT signature verification
- Parameterized SQL (no injection)
- CORS with environment-based origin control

## Analysis Algorithms

### Sentiment Analysis
- Keyword-based scoring (positive/negative word detection)
- Confidence scoring based on keyword density
- Production: Integrate ML model or external API

### Topic Extraction
- Pattern matching for predefined topics
- Multi-topic support per message
- Confidence scoring

### Intent Classification
- Rule-based intent detection
- Priority-ordered matching
- Fallback to 'inquire' intent

### Key Moments Detection
- Objection patterns (but, however, concerned)
- Buying signals (ready, let's go, sign)
- Escalation triggers (angry, complaint)

### Sales Metrics
- Talk ratio = agent_words / (agent_words + customer_words)
- Response time = avg time between customer/agent messages
- Opportunity detection from key moments

## Usage Examples

### 1. Analyze a Conversation

```bash
curl -X POST http://localhost:9028/api/v1/intel/analyze \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "conv-123",
    "customer_id": "cust-456",
    "agent_id": "agent-789",
    "messages": [
      {
        "speaker": "agent",
        "text": "Hi, how can I help?",
        "timestamp": "2026-03-06T10:00:00Z",
        "speaker_role": "agent"
      },
      {
        "speaker": "customer",
        "text": "I'm interested in your pricing",
        "timestamp": "2026-03-06T10:00:30Z",
        "speaker_role": "customer"
      }
    ]
  }'
```

### 2. Get Agent Coaching Insights

```bash
curl http://localhost:9028/api/v1/intel/coaching/agent-789 \
  -H "Authorization: Bearer <jwt-token>"
```

### 3. Get Sales Opportunities

```bash
curl "http://localhost:9028/api/v1/intel/opportunities?days=30" \
  -H "Authorization: Bearer <jwt-token>"
```

### 4. Summarize Conversation

```bash
curl -X POST http://localhost:9028/api/v1/intel/summarize/conv-123 \
  -H "Authorization: Bearer <jwt-token>"
```

## Performance Characteristics

- **Async Operations**: All DB calls are non-blocking via asyncpg
- **Connection Pooling**: 5-20 connections managed automatically
- **Query Optimization**: Indexed on tenant_id, conversation_id, agent_id
- **Response Times**: Sentiment analysis ~50ms, LLM summaries ~2-3s
- **Scalability**: Horizontal scaling via load balancer

## Error Handling

- 401: Invalid/missing JWT token
- 404: Resource not found (conversation, agent)
- 500: Server errors (database, API calls)
- Graceful fallbacks for LLM API failures
- Database connection pooling with timeouts

## LLM Integration

### Fallback Pattern
1. Try Anthropic API (Claude 3.5 Sonnet)
2. Fallback to OpenAI API (GPT-4o-mini)
3. Return mock response if both fail

### Use Cases
- Conversation summarization
- Coaching suggestion generation
- Pain point extraction
- Best practice identification

## Deployment

### Docker
```bash
docker build -t conv-intel:latest .
docker run -p 9028:9028 \
  -e DATABASE_URL=postgresql://... \
  -e ANTHROPIC_API_KEY=... \
  -e JWT_SECRET_KEY=... \
  conv-intel:latest
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: conversation-intelligence
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: conv-intel
        image: conv-intel:latest
        ports:
        - containerPort: 9028
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
```

## Monitoring & Logging

- Health check: `GET /api/v1/intel/health`
- Logs all analysis operations
- Error tracking and reporting
- Database connection pool metrics

## Contributing

1. Follow async/await patterns
2. Always parameterize SQL queries
3. Test with actual conversation data
4. Validate LLM integration
5. Update README for new features

## License

Proprietary - Global AI Sales Platform
