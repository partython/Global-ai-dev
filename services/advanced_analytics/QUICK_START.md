# Advanced Analytics Dashboard - Quick Start

## File Location
`/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/advanced_analytics/main.py`

## File Statistics
- **Total Lines**: 969
- **No external files needed**: Single main.py with complete implementation
- **Authentication**: JWT with HTTPBearer
- **Database**: PostgreSQL with asyncpg
- **Port**: 9035

## Minimal Environment Setup

```bash
# Required environment variables (no defaults)
export JWT_SECRET="your-secret-key-here"
export DB_USER="postgres"
export DB_PASSWORD="your-password"
export DB_HOST="localhost"
export DB_NAME="priya"
export PORT=9035

# Optional
export CORS_ORIGINS="http://localhost:3000,https://yourdomain.com"
export DB_PORT=5432  # defaults to 5432
```

## Test the Service

```bash
# Health check
curl http://localhost:9035/advanced-analytics/health

# Get KPIs (requires JWT token in Authorization header)
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/kpis

# Get dashboard metrics
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/dashboard

# List reports
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/reports

# Get revenue forecast
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/forecast?days=90

# Get churn prediction for customer
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/churn/customer_123

# Get cohort analysis
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/cohorts

# Get attribution models
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/attribution

# Get executive summary
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/executive-summary?period=month

# Get benchmarks
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:9035/advanced-analytics/benchmarks

# WebSocket live metrics (requires token)
wscat -c "ws://localhost:9035/ws/live-metrics?token=YOUR_JWT_TOKEN"
```

## Sample JWT Token Generation

```python
import jwt
from datetime import datetime, timedelta

secret = "your-secret-key-here"

payload = {
    "tenant_id": "tenant_123",
    "user_id": "user_456",
    "email": "user@example.com",
    "scopes": ["analytics:read", "analytics:write"],
    "exp": datetime.utcnow() + timedelta(hours=24)
}

token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Authorization: Bearer {token}")
```

## Database Schema (PostgreSQL)

```sql
-- Conversations table
CREATE TABLE conversations (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    customer_id VARCHAR NOT NULL,
    status VARCHAR,
    response_time_ms FLOAT,
    csat_score FLOAT,
    converted BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Transactions table
CREATE TABLE transactions (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    customer_id VARCHAR NOT NULL,
    amount DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Analytics reports table
CREATE TABLE analytics_reports (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    name VARCHAR,
    description TEXT,
    query TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR
);

-- Journey touchpoints table
CREATE TABLE journey_touchpoints (
    id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    customer_id VARCHAR NOT NULL,
    channel VARCHAR,
    converted BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Enable RLS on all tables
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE journey_touchpoints ENABLE ROW LEVEL SECURITY;
```

## Architecture Overview

### Components

1. **Authentication Layer**
   - JWT validation with HS256
   - HTTPBearer security scheme
   - AuthContext with tenant isolation

2. **Database Layer**
   - asyncpg connection pooling (5-20 connections)
   - PostgreSQL with Row-Level Security
   - Query timeout: 60 seconds

3. **Analytics Service**
   - Isolated by tenant_id
   - Real-time metrics aggregation
   - Predictive models (linear regression, churn scoring)
   - Multi-touch attribution

4. **WebSocket Layer**
   - Per-tenant connection management
   - 5-second broadcast interval
   - Automatic cleanup on disconnect

5. **API Endpoints**
   - 16+ REST endpoints
   - 1 WebSocket endpoint
   - Automatic OpenAPI docs at `/docs`

## Key Classes

### AuthContext
```python
tenant_id: str          # Multi-tenant isolation key
user_id: str            # User identifier
email: str              # User email
scopes: List[str]       # Permission scopes
```

### AnalyticsService
```python
get_dashboard_metrics()     # Real-time KPIs
get_kpis()                  # Period comparison
create_report()             # Custom SQL reports
get_reports()               # List reports
export_report()             # CSV/PDF export
forecast_revenue()          # Linear regression
get_churn_score()           # Churn prediction
get_cohorts()               # Cohort analysis
get_attribution()           # Multi-touch attribution
get_executive_summary()     # C-suite dashboard
```

### DatabaseConnection
```python
connect()       # Establish connection pool
disconnect()    # Close pool gracefully
execute()       # Run query, return results
execute_one()   # Run query, return single value
```

## Performance Tips

1. **Indexing**: Add indexes on `tenant_id` and `created_at`
   ```sql
   CREATE INDEX idx_conversations_tenant_created 
   ON conversations(tenant_id, created_at);
   ```

2. **Statistics**: Enable periodic analysis
   ```sql
   ANALYZE conversations;
   ```

3. **Connection Pooling**: Adjust min/max based on load
   ```python
   await asyncpg.create_pool(..., min_size=10, max_size=30)
   ```

4. **Query Caching**: Implement Redis for frequent queries

## Monitoring

```bash
# Check service health
curl http://localhost:9035/advanced-analytics/health

# Monitor logs
tail -f /var/log/advanced-analytics.log

# Check database connection status
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;
```

## Troubleshooting

### JWT_SECRET not set
```
ValueError: JWT_SECRET environment variable not set
```
Fix: `export JWT_SECRET="your-secret"`

### Database connection failed
```
asyncpg.exceptions.InvalidCatalogNameError: database "priya" does not exist
```
Fix: Create database and tables per schema above

### CORS errors
```
Access to XMLHttpRequest has been blocked by CORS policy
```
Fix: Update `CORS_ORIGINS` environment variable

### WebSocket connection refused
```
Failed to establish a WebSocket connection
```
Fix: Ensure JWT token is valid and provided as query parameter

## Production Deployment

1. Use environment variables for all secrets
2. Enable PostgreSQL SSL connections
3. Set CORS_ORIGINS to your domain only
4. Use strong JWT_SECRET (32+ characters)
5. Monitor connection pool usage
6. Enable database backups
7. Use reverse proxy (nginx) for load balancing
8. Monitor logs for errors
