# Knowledge Base v2 Service - Deployment Guide

## Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- OpenAI API Key

### Step 1: Configure Environment
```bash
cp .env.example .env

# Edit .env and add your OPENAI_API_KEY
nano .env
```

### Step 2: Start Service
```bash
docker-compose up -d

# Check logs
docker-compose logs -f knowledge-service
```

### Step 3: Verify Service
```bash
curl http://localhost:9030/api/v1/knowledge/health
```

## Production Deployment

### Architecture Recommendation
```
Load Balancer (Nginx/ALB)
  ↓
Knowledge Service Cluster (2-3 instances)
  ↓
PostgreSQL with pgvector (RDS or self-hosted)
  ↓
OpenAI API (embeddings)
```

### Step 1: Database Setup (RDS)

```sql
-- Connect to your PostgreSQL database
psql -h your-rds-endpoint.rds.amazonaws.com -U postgres -d priya_global

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Verify installation
SELECT * FROM pg_extension WHERE extname = 'vector';
```

### Step 2: Kubernetes Deployment

**knowledge-deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: knowledge-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: knowledge-service
  template:
    metadata:
      labels:
        app: knowledge-service
    spec:
      containers:
      - name: knowledge-service
        image: your-registry/knowledge-v2:latest
        ports:
        - containerPort: 9030
        env:
        - name: DB_HOST
          valueFrom:
            configMapKeyRef:
              name: knowledge-config
              key: db_host
        - name: DB_USER
          valueFrom:
            secretKeyRef:
              name: knowledge-secrets
              key: db_user
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: knowledge-secrets
              key: db_password
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: knowledge-secrets
              key: openai_api_key
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef:
              name: knowledge-secrets
              key: jwt_secret
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/v1/knowledge/health
            port: 9030
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/knowledge/health
            port: 9030
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: knowledge-service
spec:
  selector:
    app: knowledge-service
  type: ClusterIP
  ports:
  - port: 9030
    targetPort: 9030
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: knowledge-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: knowledge-service
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Step 3: Create Secrets and ConfigMaps

```bash
# Create secrets
kubectl create secret generic knowledge-secrets \
  --from-literal=db_user=postgres \
  --from-literal=db_password=<your-secure-password> \
  --from-literal=openai_api_key=sk-... \
  --from-literal=jwt_secret=<your-jwt-secret>

# Create configmap
kubectl create configmap knowledge-config \
  --from-literal=db_host=priya-postgres.c9akciq32.us-east-1.rds.amazonaws.com \
  --from-literal=db_name=priya_global \
  --from-literal=chunk_size=512 \
  --from-literal=chunk_overlap=100
```

### Step 4: Deploy

```bash
# Deploy
kubectl apply -f knowledge-deployment.yaml

# Check rollout status
kubectl rollout status deployment/knowledge-service

# View logs
kubectl logs -f -l app=knowledge-service --max-log-requests=10
```

## Monitoring & Observability

### Prometheus Metrics (Optional Enhancement)
Add to main.py:
```python
from prometheus_client import Counter, Histogram

search_counter = Counter('knowledge_searches', 'Total searches')
search_latency = Histogram('knowledge_search_latency', 'Search latency')
```

### CloudWatch Logs (AWS)
```bash
# View logs
aws logs tail /aws/ecs/knowledge-service --follow

# Query logs
aws logs filter-log-events \
  --log-group-name /aws/ecs/knowledge-service \
  --filter-pattern "ERROR"
```

### Alerting Rules

**High Vector Search Latency:**
```
rate(knowledge_search_latency_sum[5m]) / rate(knowledge_search_latency_count[5m]) > 5s
```

**Embedding API Failures:**
```
rate(embedding_errors[1m]) > 0.1
```

**Database Connection Pool Exhausted:**
```
pool_connections_active > 18
```

## Performance Tuning

### PostgreSQL Configuration

```sql
-- Connection pooling
max_connections = 200
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 16MB

-- Vector index optimization
SET maintenance_work_mem = 512MB;
REINDEX INDEX idx_chunks_embedding;

-- Monitor index size
SELECT pg_size_pretty(pg_relation_size('idx_chunks_embedding'));

-- Analyze query plans
EXPLAIN ANALYZE
SELECT * FROM document_chunks
WHERE tenant_id = 'xxx'::uuid
ORDER BY embedding <-> $1::vector
LIMIT 10;
```

### Service Tuning

```bash
# Increase async worker count
python -m uvicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker

# Enable TLS
python main.py --ssl-keyfile=/path/to/key.pem --ssl-certfile=/path/to/cert.pem
```

## Backup & Disaster Recovery

### Database Backup

```bash
# Full backup
pg_dump -h your-rds-endpoint -U postgres -d priya_global | gzip > kb_backup_$(date +%Y%m%d).sql.gz

# Backup with custom format (faster restore)
pg_dump -h your-rds-endpoint -U postgres -Fc -d priya_global > kb_backup_$(date +%Y%m%d).dump
```

### Restore from Backup

```bash
# From custom format
pg_restore -h your-rds-endpoint -U postgres -d priya_global kb_backup_20240306.dump

# From SQL backup
gunzip < kb_backup_20240306.sql.gz | psql -h your-rds-endpoint -U postgres -d priya_global
```

### Vector Index Rebuild

```sql
-- If index gets corrupted
REINDEX INDEX CONCURRENTLY idx_chunks_embedding;

-- Verify integrity
SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL;
```

## Rollback Procedure

```bash
# Kubernetes rollback
kubectl rollout history deployment/knowledge-service
kubectl rollout undo deployment/knowledge-service --to-revision=1

# Docker rollback
docker service update --image knowledge-service:v1.0 knowledge-service

# Verify
curl -H "Authorization: Bearer <token>" \
  http://knowledge-service:9030/api/v1/knowledge/stats
```

## Load Testing

```bash
# Using Apache Bench
ab -c 100 -n 10000 \
  -H "Authorization: Bearer <token>" \
  http://knowledge-service:9030/api/v1/knowledge/health

# Using wrk
wrk -t12 -c400 -d30s \
  -H "Authorization: Bearer <token>" \
  http://knowledge-service:9030/api/v1/knowledge/search \
  -s load_test.lua
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker logs knowledge-v2

# Verify database connectivity
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"

# Check JWT_SECRET is set
echo $JWT_SECRET
```

### Embedding API Failures
```bash
# Test OpenAI API
curl https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "test", "model": "text-embedding-3-small"}'
```

### Slow Vector Search
```bash
# Check index size and vacuum
VACUUM ANALYZE document_chunks;

# Rebuild index with larger ivfflat lists
REINDEX INDEX idx_chunks_embedding;

# Check for slow queries
SELECT * FROM pg_stat_statements 
WHERE query LIKE '%embedding%'
ORDER BY mean_time DESC;
```

## Security Checklist

- [ ] JWT_SECRET is >32 characters
- [ ] DB_PASSWORD is strong (>20 chars, mixed case)
- [ ] CORS_ORIGINS only includes trusted domains
- [ ] HTTPS enabled in production
- [ ] Database encryption at rest enabled
- [ ] Secrets stored in secrets manager (not env files)
- [ ] API rate limiting configured
- [ ] WAF rules enabled (if using ALB/CloudFront)
- [ ] Regular security patches applied
- [ ] Database backups encrypted
- [ ] Audit logging enabled

## Cost Optimization

### Database
- Use RDS Reserved Instances (40% savings)
- Enable automated backups (cheaper than manual)
- Use read replicas for reporting only

### Compute
- Use spot instances for batch processing
- Right-size instance types (CPU/memory)
- Enable auto-scaling based on metrics

### API Costs
- Cache embeddings where possible
- Batch embedding requests
- Use cheaper embedding model if possible
- Monitor usage closely

## Support

For issues:
1. Check logs: `kubectl logs -f deployment/knowledge-service`
2. Verify database: `SELECT version();`
3. Test connectivity: `curl http://service:9030/api/v1/knowledge/health`
4. Check configuration: `kubectl get configmap knowledge-config -o yaml`
