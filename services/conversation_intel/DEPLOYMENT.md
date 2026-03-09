# Deployment Guide - Conversation Intelligence Service

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Docker & Docker Compose (optional)
- Git

### Setup with Docker Compose (Recommended)

```bash
# Clone/navigate to service directory
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/conversation_intel

# Set environment variables
export ANTHROPIC_API_KEY=sk-ant-your-key
export OPENAI_API_KEY=sk-your-key

# Start services
docker-compose up -d

# Verify service is running
curl http://localhost:9028/api/v1/intel/health
```

### Manual Setup (Without Docker)

```bash
# 1. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export DATABASE_URL="postgresql://user:password@localhost:5432/aisales_prod"
export JWT_SECRET_KEY="dev-key-change-in-production"
export ANTHROPIC_API_KEY="sk-ant-your-key"
export OPENAI_API_KEY="sk-your-key"
export CORS_ORIGINS="http://localhost:3000"

# 4. Run the service
python main.py
```

Service will be available at `http://localhost:9028`

## Production Deployment

### Environment Setup

Create a `.env` file with production values:

```bash
# Database
DATABASE_URL=postgresql://user:password@prod-db.internal:5432/aisales
DB_POOL_MIN_SIZE=10
DB_POOL_MAX_SIZE=30
DB_COMMAND_TIMEOUT=60

# Security (CHANGE THESE!)
JWT_SECRET_KEY=use-a-strong-random-key-min-32-chars
JWT_ALGORITHM=HS256

# LLM APIs
ANTHROPIC_API_KEY=sk-ant-your-production-key
OPENAI_API_KEY=sk-your-production-key

# Network
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
CONV_INTEL_PORT=9028
```

### Option 1: Docker Container Deployment

```bash
# Build image
docker build -t aisales-conv-intel:v1.0.0 .

# Tag for registry
docker tag aisales-conv-intel:v1.0.0 your-registry.com/aisales-conv-intel:v1.0.0

# Push to registry
docker push your-registry.com/aisales-conv-intel:v1.0.0

# Run container
docker run -d \
  --name conversation-intel \
  -p 9028:9028 \
  --env-file .env.production \
  --health-cmd="curl -f http://localhost:9028/api/v1/intel/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  your-registry.com/aisales-conv-intel:v1.0.0
```

### Option 2: Kubernetes Deployment

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: aisales

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: conv-intel-config
  namespace: aisales
data:
  CONV_INTEL_PORT: "9028"
  CORS_ORIGINS: "https://yourdomain.com"
  LOG_LEVEL: "INFO"

---
apiVersion: v1
kind: Secret
metadata:
  name: conv-intel-secrets
  namespace: aisales
type: Opaque
data:
  database-url: <base64-encoded-url>
  jwt-secret-key: <base64-encoded-key>
  anthropic-api-key: <base64-encoded-key>
  openai-api-key: <base64-encoded-key>

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: conversation-intelligence
  namespace: aisales
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: conversation-intelligence
      version: v1
  template:
    metadata:
      labels:
        app: conversation-intelligence
        version: v1
    spec:
      serviceAccountName: conv-intel-sa
      
      initContainers:
      - name: wait-for-db
        image: busybox:latest
        command: ['sh', '-c', 'until nc -z postgres.aisales 5432; do echo waiting for db; sleep 2; done']
      
      containers:
      - name: conversation-intelligence
        image: your-registry.com/aisales-conv-intel:v1.0.0
        imagePullPolicy: IfNotPresent
        
        ports:
        - containerPort: 9028
          name: http
          protocol: TCP
        
        envFrom:
        - configMapRef:
            name: conv-intel-config
        - secretRef:
            name: conv-intel-secrets
        
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: conv-intel-secrets
              key: database-url
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: conv-intel-secrets
              key: jwt-secret-key
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: conv-intel-secrets
              key: anthropic-api-key
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: conv-intel-secrets
              key: openai-api-key
        
        livenessProbe:
          httpGet:
            path: /api/v1/intel/health
            port: 9028
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        
        readinessProbe:
          httpGet:
            path: /api/v1/intel/health
            port: 9028
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
        
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        
        securityContext:
          runAsNonRoot: true
          runAsUser: 1000
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop:
            - ALL
        
        volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: cache
          mountPath: /app/.cache
      
      volumes:
      - name: tmp
        emptyDir: {}
      - name: cache
        emptyDir: {}

---
apiVersion: v1
kind: Service
metadata:
  name: conversation-intelligence
  namespace: aisales
spec:
  type: ClusterIP
  ports:
  - port: 9028
    targetPort: 9028
    protocol: TCP
    name: http
  selector:
    app: conversation-intelligence

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: conversation-intelligence-hpa
  namespace: aisales
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: conversation-intelligence
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
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 15
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
      - type: Pods
        value: 2
        periodSeconds: 15
      selectPolicy: Max

---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: conv-intel-sa
  namespace: aisales
```

Deploy to Kubernetes:

```bash
kubectl apply -f deployment.yaml

# Monitor rollout
kubectl rollout status deployment/conversation-intelligence -n aisales

# View logs
kubectl logs -f deployment/conversation-intelligence -n aisales

# Port forward for testing
kubectl port-forward -n aisales svc/conversation-intelligence 9028:9028
```

### Option 3: Systemd Service (Linux)

Create `/etc/systemd/system/conversation-intel.service`:

```ini
[Unit]
Description=Conversation Intelligence Service
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=aisales
Group=aisales
WorkingDirectory=/opt/aisales/conversation_intel
EnvironmentFile=/opt/aisales/conversation_intel/.env
ExecStart=/opt/aisales/conversation_intel/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9028

Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=conv-intel

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable conversation-intel
sudo systemctl start conversation-intel
sudo systemctl status conversation-intel
```

## Database Initialization

### Automatic (Recommended)

The service automatically creates tables and indexes on startup via the `ensure_tables()` function.

### Manual

```sql
-- Run SQL from main.py ensure_tables() function
-- Or use psql:
psql -U conv_intel -d aisales_prod -f init.sql
```

## Monitoring & Observability

### Health Checks

```bash
# Service health
curl http://localhost:9028/api/v1/intel/health

# Database connection test
curl http://localhost:9028/api/v1/intel/health | jq .status
```

### Logging

Logs are sent to stdout/stderr. Use your log aggregator:

```bash
# View logs (Docker)
docker logs conversation-intel

# View logs (Kubernetes)
kubectl logs -f deployment/conversation-intelligence -n aisales

# View logs (Systemd)
journalctl -u conversation-intel -f
```

### Metrics

Integrate with Prometheus by adding:

```bash
# Add to monitoring scrape config
scrape_configs:
- job_name: 'conversation-intel'
  static_configs:
  - targets: ['localhost:9028']
  metrics_path: '/metrics'
```

## Database Backup & Recovery

### Automated Backup

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR="/backups/aisales"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

pg_dump -U conv_intel -h localhost aisales_prod | \
  gzip > "$BACKUP_DIR/aisales_$TIMESTAMP.sql.gz"

# Keep only last 30 days
find "$BACKUP_DIR" -name "aisales_*.sql.gz" -mtime +30 -delete
```

Schedule with cron:

```bash
# 2 AM daily
0 2 * * * /path/to/backup.sh
```

### Restore from Backup

```bash
# Decompress and restore
gunzip < aisales_20260306_020000.sql.gz | \
  psql -U conv_intel -d aisales_prod
```

## Performance Tuning

### Database Connection Pool

```python
# In main.py, adjust pool settings
db_pool = await asyncpg.create_pool(
    DATABASE_URL,
    min_size=10,        # Increase for high concurrency
    max_size=30,        # Increase for peak loads
    command_timeout=60  # Adjust for long queries
)
```

### PostgreSQL Optimization

```sql
-- Connection pooling (pgBouncer recommended)
-- In postgresql.conf:
max_connections = 200
shared_buffers = 256MB      # 25% of system RAM
effective_cache_size = 1GB  # 50% of system RAM
work_mem = 16MB
maintenance_work_mem = 64MB

-- Create indexes for common queries
CREATE INDEX idx_conversations_tenant_date ON conversations(tenant_id, created_at DESC);
CREATE INDEX idx_analysis_sentiment ON conversation_analysis(overall_sentiment);
CREATE INDEX idx_agent_metrics_performance ON agent_metrics(performance_score DESC);
```

### API Server Tuning

```bash
# Increase worker processes
python -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 9028 \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --max-requests 10000 \
  --max-requests-jitter 1000
```

## Security Checklist

- [ ] Change JWT_SECRET_KEY to a strong random value
- [ ] Use HTTPS in production
- [ ] Set CORS_ORIGINS to your domain only
- [ ] Enable WAF/rate limiting
- [ ] Use TLS for database connections
- [ ] Rotate API keys regularly
- [ ] Enable audit logging
- [ ] Implement request signing
- [ ] Use secrets management (Vault, Sealed Secrets)
- [ ] Enable container security scanning
- [ ] Implement network policies in Kubernetes

## Scaling Strategy

### Horizontal Scaling
1. Deploy multiple replicas (3+ recommended)
2. Use load balancer (nginx, HAProxy, AWS ALB)
3. Configure database connection pooling
4. Use read replicas for read-heavy workloads

### Vertical Scaling
1. Increase pod resources
2. Optimize database indexes
3. Cache frequently accessed data
4. Implement query timeouts

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
docker logs conversation-intel
# Verify environment variables
env | grep -i conv_intel
```

### Database connection errors
```bash
# Test connectivity
psql -U conv_intel -h localhost -d aisales_prod -c "SELECT 1"
# Check pool exhaustion
curl http://localhost:9028/api/v1/intel/health
```

### Slow queries
```sql
-- Enable slow query log
SET log_min_duration_statement = 1000;
-- Check execution plans
EXPLAIN ANALYZE SELECT * FROM conversations WHERE tenant_id = '...';
```

### Out of memory
```bash
# Reduce pool size
DB_POOL_MAX_SIZE=15

# Monitor memory usage
docker stats conversation-intel
```

## Maintenance Tasks

### Weekly
- Review application logs for errors
- Monitor database size growth
- Check backup completion

### Monthly
- Update dependencies: `pip install --upgrade -r requirements.txt`
- Rotate secrets/API keys
- Review performance metrics
- Clean old data (conversations older than 90 days if needed)

### Quarterly
- Security scanning and patching
- Capacity planning review
- Disaster recovery drill

## Contact & Support

- Issues: Check service logs and health endpoint
- Documentation: See README.md
- Bug reports: Submit to platform team
