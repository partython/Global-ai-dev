# Deployment Guide

## Quick Start

### 1. Install Dependencies
```bash
pip install \
  fastapi==0.104.1 \
  uvicorn==0.24.0 \
  asyncpg==0.29.0 \
  pyjwt==2.8.1 \
  httpx==0.25.2 \
  pydantic==2.5.0 \
  croniter==2.0.1
```

### 2. Configure Environment Variables
```bash
# Database Configuration
export DB_HOST="postgres.example.com"
export DB_PORT="5432"
export DB_NAME="workflows_production"
export DB_USER="workflows_user"
export DB_PASSWORD="<strong-password>"

# Security
export JWT_SECRET="<32+ character random key>"

# CORS
export CORS_ORIGINS="https://app.example.com,https://admin.example.com"

# Server
export PORT="9034"
export HOST="0.0.0.0"
```

### 3. Create Database (PostgreSQL)
```sql
-- Run as superuser
CREATE DATABASE workflows_production;
CREATE USER workflows_user WITH PASSWORD '<strong-password>';
ALTER ROLE workflows_user SET client_encoding TO 'utf8';
ALTER ROLE workflows_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE workflows_user SET default_transaction_deferrable TO on;
GRANT ALL PRIVILEGES ON DATABASE workflows_production TO workflows_user;
GRANT USAGE ON SCHEMA public TO workflows_user;
GRANT CREATE ON SCHEMA public TO workflows_user;
```

### 4. Generate JWT Secret
```bash
# Generate 32-byte random key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 5. Run the Service
```bash
# Development
python /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/workflows/main.py

# Production with Gunicorn
gunicorn \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:9034 \
  main:app
```

## Docker Deployment

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV PORT=9034
ENV HOST=0.0.0.0

EXPOSE 9034

CMD ["python", "main.py"]
```

### requirements.txt
```
fastapi==0.104.1
uvicorn==0.24.0
asyncpg==0.29.0
pyjwt==2.8.1
httpx==0.25.2
pydantic==2.5.0
croniter==2.0.1
```

### Build & Run
```bash
docker build -t workflows-engine:1.0 .

docker run -d \
  --name workflows \
  -p 9034:9034 \
  -e DB_HOST=postgres \
  -e DB_PASSWORD=<password> \
  -e JWT_SECRET=<secret> \
  workflows-engine:1.0
```

## Docker Compose

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: workflows_production
      POSTGRES_USER: workflows_user
      POSTGRES_PASSWORD: secure_password_here
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U workflows_user -d workflows_production"]
      interval: 10s
      timeout: 5s
      retries: 5

  workflows:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: workflows_production
      DB_USER: workflows_user
      DB_PASSWORD: secure_password_here
      JWT_SECRET: your-secret-key-here
      CORS_ORIGINS: "http://localhost:3000"
      PORT: 9034
      HOST: 0.0.0.0
    ports:
      - "9034:9034"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9034/workflows/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  postgres_data:
```

Run with: `docker-compose up -d`

## Kubernetes Deployment

### ConfigMap
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: workflows-config
  namespace: default
data:
  DB_HOST: postgres.default.svc.cluster.local
  DB_PORT: "5432"
  DB_NAME: workflows_production
  CORS_ORIGINS: "https://app.example.com"
  PORT: "9034"
  HOST: "0.0.0.0"
```

### Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: workflows-secret
  namespace: default
type: Opaque
stringData:
  DB_USER: workflows_user
  DB_PASSWORD: <base64-encoded-password>
  JWT_SECRET: <base64-encoded-secret>
```

### Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workflows-engine
  namespace: default
spec:
  replicas: 3
  selector:
    matchLabels:
      app: workflows-engine
  template:
    metadata:
      labels:
        app: workflows-engine
    spec:
      containers:
      - name: workflows
        image: workflows-engine:1.0
        ports:
        - containerPort: 9034
        envFrom:
        - configMapRef:
            name: workflows-config
        - secretRef:
            name: workflows-secret
        livenessProbe:
          httpGet:
            path: /workflows/health
            port: 9034
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /workflows/health
            port: 9034
          initialDelaySeconds: 20
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### Service
```yaml
apiVersion: v1
kind: Service
metadata:
  name: workflows-engine-service
  namespace: default
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 9034
    protocol: TCP
  selector:
    app: workflows-engine
```

## Monitoring & Logging

### Prometheus Metrics (Add to main.py if needed)
```python
from prometheus_client import Counter, Histogram

workflow_executions = Counter(
    'workflow_executions_total',
    'Total workflow executions',
    ['status']
)

execution_duration = Histogram(
    'workflow_execution_duration_seconds',
    'Workflow execution duration'
)
```

### Health Check
```bash
curl http://localhost:9034/workflows/health
```

Response:
```json
{
  "status": "healthy",
  "service": "Automation Workflows Engine",
  "database": "healthy",
  "timestamp": "2026-03-06T10:30:45.123456",
  "version": "1.0.0"
}
```

### Logging Configuration

Logs go to stdout (container-friendly):
```bash
docker logs workflows
```

Log levels:
- INFO: Normal operations
- WARNING: Non-critical issues
- ERROR: Failed operations with stack traces

### Example Monitoring
```bash
# Watch logs in real-time
docker logs -f workflows

# Check recent error logs
docker logs workflows 2>&1 | grep ERROR

# Count workflow executions by status
docker logs workflows 2>&1 | grep "status=" | sort | uniq -c
```

## Performance Tuning

### PostgreSQL Connection Pool
```python
# In main.py initialize_db():
db_pool = await asyncpg.create_pool(
    ...
    min_size=5,      # Minimum connections
    max_size=20,     # Maximum connections
    command_timeout=60,
)
```

Adjust based on:
- Expected concurrent users: `(users / 100) * 2` = min_size
- Peak concurrency: `(peak_users / 10)` = max_size

### Uvicorn Workers
```bash
gunicorn \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --worker-connections 100 \
  --max-requests 1000 \
  main:app
```

For N CPUs: `--workers (2 * N) + 1`

## Backup & Recovery

### Database Backup
```bash
# Full backup
pg_dump -U workflows_user -h postgres.example.com workflows_production \
  > workflows_backup_$(date +%Y%m%d).sql

# Compressed backup
pg_dump -U workflows_user -h postgres.example.com workflows_production \
  | gzip > workflows_backup_$(date +%Y%m%d).sql.gz
```

### Database Restore
```bash
psql -U workflows_user -h postgres.example.com workflows_production \
  < workflows_backup_20260306.sql
```

## Security Checklist

- [ ] JWT_SECRET is 32+ random characters
- [ ] Database password is strong (16+ chars, mixed case, numbers, symbols)
- [ ] DB credentials are in environment variables (never hardcoded)
- [ ] CORS_ORIGINS restricted to known domains
- [ ] SSL/TLS enabled for all external connections
- [ ] Database user has minimal required permissions
- [ ] Regular database backups scheduled
- [ ] Rate limiting configured (if exposed to internet)
- [ ] API keys/tokens rotated regularly
- [ ] Database connection pooling optimized

## Scaling Considerations

1. **Horizontal Scaling**: Deploy multiple instances behind load balancer
2. **Database**: Use read replicas for analytics queries
3. **Caching**: Add Redis for session/token caching
4. **Message Queue**: Use Celery/RabbitMQ for long-running workflows
5. **CDN**: Cache static API documentation

## Troubleshooting

### Database Connection Failed
```bash
# Check connectivity
psql -U workflows_user -h postgres.example.com -d workflows_production -c "SELECT 1"

# Check environment variables
env | grep DB_
```

### JWT Token Invalid
```bash
# Verify token generation (use same JWT_SECRET)
python -c "
import jwt
secret = 'your-secret-key'
token = jwt.encode({'tenant_id': '123', 'user_id': '456'}, secret)
print(token)
"
```

### Workflow Timeout
- Increase execution timeout in execute_workflow()
- Check for long-running webhook calls
- Optimize database queries
- Review workflow logic for infinite loops

## Maintenance

### Regular Tasks
- [ ] Monitor disk space for logs
- [ ] Review slow query logs
- [ ] Update Python dependencies monthly
- [ ] Rotate JWT secrets quarterly
- [ ] Archive old workflow runs
- [ ] Test backup/restore procedures

### Database Maintenance
```sql
-- Analyze query performance
ANALYZE workflows;
ANALYZE workflow_runs;

-- Vacuum dead tuples
VACUUM ANALYZE;

-- Reindex if needed
REINDEX TABLE workflows;
```

---

Production-ready deployment with monitoring, scaling, and disaster recovery.
