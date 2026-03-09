# Deployment Guide

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Docker and Docker Compose (for containerized deployment)

## Local Development Setup

### 1. Clone and Setup

```bash
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/leads
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database credentials and JWT secret
```

### 3. Initialize Database

```bash
# Option A: Using psql directly
psql -h localhost -U postgres -d leads_db -f init_db.sql

# Option B: Using Python with asyncpg
python -c "
import asyncpg
import asyncio
from pathlib import Path

async def init_db():
    conn = await asyncpg.connect(
        user='postgres',
        password='your_password',
        database='leads_db',
        host='localhost'
    )
    schema = Path('init_db.sql').read_text()
    await conn.execute(schema)
    await conn.close()

asyncio.run(init_db())
"
```

### 4. Run Service Locally

```bash
# Development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 9027

# Production mode
python main.py
```

Service will be available at `http://localhost:9027`

## Docker Deployment

### 1. Build Docker Image

```bash
docker build -t leads-service:latest .
```

### 2. Run with Docker Compose (Recommended)

```bash
# Create .env file with your configuration
cp .env.example .env
# Edit .env as needed

# Start services
docker-compose up -d

# View logs
docker-compose logs -f leads_service

# Stop services
docker-compose down
```

### 3. Manual Docker Run

```bash
# Create network
docker network create leads_network

# Run PostgreSQL
docker run -d \
  --name leads_db \
  --network leads_network \
  -e POSTGRES_DB=leads_db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=your_password \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15-alpine

# Wait for DB to be ready
sleep 10

# Initialize database
docker exec leads_db psql -U postgres -d leads_db -f /docker-entrypoint-initdb.d/init.sql

# Run service
docker run -d \
  --name leads_service \
  --network leads_network \
  -p 9027:9027 \
  -e DB_HOST=leads_db \
  -e DB_NAME=leads_db \
  -e DB_USER=postgres \
  -e DB_PASSWORD=your_password \
  -e JWT_SECRET=your_jwt_secret \
  leads-service:latest
```

## Kubernetes Deployment

### 1. Create Namespace

```bash
kubectl create namespace leads
```

### 2. Create Secrets

```bash
kubectl create secret generic leads-db-secret \
  --from-literal=username=postgres \
  --from-literal=password=$(openssl rand -base64 32) \
  -n leads

kubectl create secret generic leads-jwt-secret \
  --from-literal=jwt-secret=$(openssl rand -base64 32) \
  -n leads
```

### 3. Create ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: leads-config
  namespace: leads
data:
  DB_HOST: "postgres-service"
  DB_PORT: "5432"
  DB_NAME: "leads_db"
  CORS_ORIGINS: "https://yourdomain.com"
```

### 4. Deploy PostgreSQL

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: leads
spec:
  selector:
    app: postgres
  ports:
    - port: 5432
  type: ClusterIP
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: leads
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        env:
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: leads-db-secret
              key: password
        - name: POSTGRES_DB
          value: leads_db
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        emptyDir: {}
```

### 5. Deploy Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: leads-service
  namespace: leads
spec:
  selector:
    app: leads
  ports:
    - port: 9027
      targetPort: 9027
  type: LoadBalancer
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: leads-service
  namespace: leads
spec:
  replicas: 3
  selector:
    matchLabels:
      app: leads
  template:
    metadata:
      labels:
        app: leads
    spec:
      containers:
      - name: leads-service
        image: leads-service:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 9027
        env:
        - name: DB_HOST
          valueFrom:
            configMapKeyRef:
              name: leads-config
              key: DB_HOST
        - name: DB_NAME
          valueFrom:
            configMapKeyRef:
              name: leads-config
              key: DB_NAME
        - name: DB_USER
          valueFrom:
            secretKeyRef:
              name: leads-db-secret
              key: username
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: leads-db-secret
              key: password
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: leads-jwt-secret
              key: jwt-secret
        livenessProbe:
          httpGet:
            path: /api/v1/leads/health
            port: 9027
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/leads/health
            port: 9027
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

## Environment Variables for Production

```bash
# Database
DB_HOST=<your-db-host>
DB_PORT=5432
DB_NAME=leads_db
DB_USER=<your-db-user>
DB_PASSWORD=<your-db-password>

# JWT
JWT_SECRET=<generate-with-openssl-rand-base64-32>

# CORS
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Logging
LOG_LEVEL=WARNING

# Feature flags
ENABLE_AUTO_SCORING=true
ENABLE_SCORE_DECAY=true
```

## Health Checks

The service provides a health check endpoint at `/api/v1/leads/health`

```bash
curl http://localhost:9027/api/v1/leads/health
```

## Monitoring and Logging

### View Service Logs

```bash
# Docker
docker-compose logs -f leads_service

# Kubernetes
kubectl logs -f deployment/leads-service -n leads

# Local
tail -f leads_service.log
```

### Key Metrics to Monitor

- Database connection pool usage
- Query response times
- Error rates by endpoint
- JWT token validation failures
- Lead creation/update rates

## Scaling Considerations

1. **Database**: Use connection pooling (configured in service)
2. **Caching**: Implement Redis for score caching if needed
3. **Async Processing**: Use task queues for bulk operations
4. **Load Balancing**: Use horizontal scaling with load balancer
5. **Database Replication**: Set up read replicas for high load

## Backup Strategy

### PostgreSQL Backups

```bash
# Full backup
pg_dump -h localhost -U postgres leads_db > leads_db_$(date +%Y%m%d_%H%M%S).sql

# Backup with compression
pg_dump -h localhost -U postgres -F c leads_db > leads_db.dump

# Restore from backup
psql -h localhost -U postgres leads_db < backup.sql
```

### Automated Backups

```bash
# Add to crontab for daily backups
0 2 * * * /usr/bin/pg_dump -h localhost -U postgres leads_db | gzip > /backups/leads_db_$(date +\%Y\%m\%d).sql.gz
```

## Troubleshooting

### Database Connection Issues

```bash
# Test connection
psql -h <host> -U <user> -d leads_db

# Check connection pool status
# In service logs: "Database pool created"
```

### JWT Authentication Failures

```bash
# Verify JWT secret matches across services
echo $JWT_SECRET

# Decode JWT (for debugging)
python -c "import jwt; print(jwt.decode('<token>', '<secret>', algorithms=['HS256']))"
```

### High Query Times

```bash
# Check slow queries in PostgreSQL
SELECT query, mean_time FROM pg_stat_statements 
ORDER BY mean_time DESC LIMIT 10;

# Add indexes if needed
CREATE INDEX idx_leads_tenant_stage_created ON leads(tenant_id, pipeline_stage, created_at);
```

## Performance Tuning

### PostgreSQL Optimization

```sql
-- Analyze query plans
EXPLAIN ANALYZE SELECT * FROM leads WHERE tenant_id = 'tenant123' AND pipeline_stage = 'New';

-- Vacuum and analyze
VACUUM ANALYZE leads;

-- Check index bloat
SELECT schemaname, tablename, indexname, pg_size_pretty(pg_relation_size(indexrelid)) 
FROM pg_stat_user_indexes;
```

### Connection Pool Tuning

Adjust in main.py:
```python
db_pool = await asyncpg.create_pool(
    ...
    min_size=5,      # Increase for high concurrency
    max_size=20,     # Max connections
)
```

## Security Hardening

1. **Use HTTPS**: Deploy behind reverse proxy with SSL/TLS
2. **Rate Limiting**: Implement rate limiting on endpoints
3. **Input Validation**: All inputs validated with Pydantic
4. **CORS**: Configure for specific domains only
5. **Secrets Management**: Use environment variables, never hardcode
6. **Database**: Use parameterized queries (already implemented)
7. **JWT**: Use strong secret and configure expiry

## CI/CD Pipeline

### GitHub Actions Example

```yaml
name: Deploy Leads Service

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: leads_db
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: docker/setup-buildx-action@v2
      - uses: docker/build-push-action@v4
        with:
          push: true
          tags: registry.example.com/leads-service:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Kubernetes
        run: |
          kubectl set image deployment/leads-service \
            leads-service=registry.example.com/leads-service:${{ github.sha }} \
            -n leads
```
