# Appointment Booking Service - Deployment Guide

## Production Deployment Checklist

### 1. Pre-Deployment Setup

#### 1.1 Environment Configuration
- [ ] Generate secure JWT_SECRET (minimum 32 characters)
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] Set strong DB_PASSWORD
- [ ] Configure CORS_ORIGINS to production domains
- [ ] Set LOG_LEVEL to INFO (or WARNING)
- [ ] Verify all environment variables in .env

#### 1.2 Database Preparation
```bash
# Connect to PostgreSQL in production environment
psql -h <prod_db_host> -U <prod_db_user> -d priya_global

# Run schema initialization
\i schema.sql

# Verify tables created
\dt

# Check indexes
\di

# Test connection from app server
```

#### 1.3 Dependencies Installation
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Deployment Options

### Option A: Docker Deployment (Recommended)

#### Create Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Expose port
EXPOSE 9029

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:9029/api/v1/appointments/health')"

# Run application
CMD ["python", "main.py"]
```

#### Build and Run
```bash
# Build image
docker build -t appointments-service:1.0.0 .

# Run container
docker run -d \
  --name appointments-service \
  -p 9029:9029 \
  -e DB_HOST="<db_host>" \
  -e DB_PORT="5432" \
  -e DB_NAME="priya_global" \
  -e DB_USER="postgres" \
  -e DB_PASSWORD="<secure_password>" \
  -e JWT_SECRET="<secure_secret>" \
  -e CORS_ORIGINS="https://app.example.com,https://api.example.com" \
  -e PORT="9029" \
  -e LOG_LEVEL="INFO" \
  appointments-service:1.0.0

# View logs
docker logs -f appointments-service
```

#### Docker Compose
```yaml
version: '3.8'

services:
  appointments:
    build: .
    container_name: appointments-service
    ports:
      - "9029:9029"
    environment:
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: priya_global
      DB_USER: postgres
      DB_PASSWORD: ${DB_PASSWORD}
      JWT_SECRET: ${JWT_SECRET}
      CORS_ORIGINS: ${CORS_ORIGINS}
      PORT: 9029
      LOG_LEVEL: INFO
    depends_on:
      - postgres
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9029/api/v1/appointments/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s

  postgres:
    image: postgres:15
    container_name: postgres-priya
    environment:
      POSTGRES_DB: priya_global
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/schema.sql
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  postgres_data:
```

---

### Option B: Gunicorn + Systemd (Linux)

#### 1. Create systemd service file
```bash
sudo nano /etc/systemd/system/appointments-service.service
```

```ini
[Unit]
Description=Appointment Booking Service
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/appointments
Environment="PATH=/opt/appointments/venv/bin"
Environment="DB_HOST=localhost"
Environment="DB_PORT=5432"
Environment="DB_NAME=priya_global"
Environment="DB_USER=postgres"
Environment="DB_PASSWORD={{ SECURE_PASSWORD }}"
Environment="JWT_SECRET={{ SECURE_SECRET }}"
Environment="CORS_ORIGINS=https://app.example.com"
Environment="PORT=9029"
Environment="LOG_LEVEL=INFO"

ExecStart=/opt/appointments/venv/bin/gunicorn \
    main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:9029 \
    --access-logfile - \
    --error-logfile - \
    --log-level info

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 2. Enable and start service
```bash
sudo systemctl daemon-reload
sudo systemctl enable appointments-service
sudo systemctl start appointments-service

# Verify status
sudo systemctl status appointments-service

# View logs
sudo journalctl -u appointments-service -f
```

---

### Option C: AWS Elastic Container Service (ECS)

#### 1. Create ECR Repository
```bash
aws ecr create-repository --repository-name appointments-service --region us-east-1
```

#### 2. Build and push image
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and tag
docker build -t <account-id>.dkr.ecr.us-east-1.amazonaws.com/appointments-service:1.0.0 .

# Push to ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/appointments-service:1.0.0
```

#### 3. Create ECS Task Definition
```json
{
  "family": "appointments-service",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "appointments-service",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/appointments-service:1.0.0",
      "portMappings": [
        {
          "containerPort": 9029,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "PORT",
          "value": "9029"
        }
      ],
      "secrets": [
        {
          "name": "DB_HOST",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:<account>:secret:db-host"
        },
        {
          "name": "DB_PASSWORD",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:<account>:secret:db-password"
        },
        {
          "name": "JWT_SECRET",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:<account>:secret:jwt-secret"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/appointments-service",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:9029/api/v1/appointments/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 10
      }
    }
  ]
}
```

#### 4. Create ECS Service
```bash
aws ecs create-service \
  --cluster priya-global \
  --service-name appointments-service \
  --task-definition appointments-service:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=appointments-service,containerPort=9029 \
  --region us-east-1
```

---

### Option D: Kubernetes Deployment

#### 1. Create ConfigMap for non-sensitive config
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: appointments-config
  namespace: priya-global
data:
  PORT: "9029"
  LOG_LEVEL: "INFO"
```

#### 2. Create Secret for sensitive data
```bash
kubectl create secret generic appointments-secrets \
  --from-literal=DB_HOST=<db_host> \
  --from-literal=DB_PORT=5432 \
  --from-literal=DB_NAME=priya_global \
  --from-literal=DB_USER=postgres \
  --from-literal=DB_PASSWORD=<secure_password> \
  --from-literal=JWT_SECRET=<secure_secret> \
  --from-literal=CORS_ORIGINS="https://app.example.com" \
  -n priya-global
```

#### 3. Create Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: appointments-service
  namespace: priya-global
spec:
  replicas: 3
  selector:
    matchLabels:
      app: appointments-service
  template:
    metadata:
      labels:
        app: appointments-service
    spec:
      containers:
      - name: appointments-service
        image: <registry>/appointments-service:1.0.0
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 9029
        envFrom:
        - configMapRef:
            name: appointments-config
        - secretRef:
            name: appointments-secrets
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /api/v1/appointments/health
            port: 9029
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /api/v1/appointments/health
            port: 9029
          initialDelaySeconds: 5
          periodSeconds: 10
        securityContext:
          runAsNonRoot: true
          readOnlyRootFilesystem: true
          allowPrivilegeEscalation: false
        volumeMounts:
        - name: tmp
          mountPath: /tmp
      volumes:
      - name: tmp
        emptyDir: {}
```

#### 4. Create Service
```yaml
apiVersion: v1
kind: Service
metadata:
  name: appointments-service
  namespace: priya-global
spec:
  selector:
    app: appointments-service
  ports:
  - protocol: TCP
    port: 80
    targetPort: 9029
  type: LoadBalancer
```

---

## Post-Deployment Verification

### 1. Health Check
```bash
curl https://app.example.com/api/v1/appointments/health
```

### 2. Database Connectivity Test
```bash
# Connect to database
psql -h <prod_host> -U postgres -d priya_global

# Verify tables exist
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
```

### 3. JWT Token Validation
```bash
# Generate test token with production secret
python -c "
import jwt
payload = {'tenant_id': 'test', 'user_id': 'test', 'user_type': 'agent'}
token = jwt.encode(payload, 'YOUR_JWT_SECRET', algorithm='HS256')
print(f'Bearer {token}')
"

# Test API call
curl -X GET https://app.example.com/api/v1/appointments \
  -H "Authorization: Bearer <token>"
```

### 4. SSL/TLS Verification
```bash
# Check certificate validity
openssl s_client -connect app.example.com:443

# Test HTTPS connection
curl -I https://app.example.com/api/v1/appointments/health
```

---

## Monitoring & Alerting

### 1. Prometheus Metrics (Optional)

Add to main.py:
```python
from prometheus_client import Counter, Histogram, generate_latest
import time

appointment_created = Counter('appointments_created_total', 'Total appointments created')
appointment_duration = Histogram('appointment_duration_seconds', 'Appointment duration')

@app.middleware("http")
async def add_metrics(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    appointment_duration.observe(duration)
    return response

@app.get("/metrics")
async def metrics():
    return generate_latest()
```

### 2. Logging

Add structured logging:
```python
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'service': 'appointments',
            'message': record.getMessage(),
            'module': record.module
        }
        return json.dumps(log_data)

handler = logging.FileHandler('app.log')
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
```

### 3. Alerting Rules

```yaml
groups:
- name: appointments
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
    for: 5m
    annotations:
      summary: "High error rate detected"

  - alert: DBConnectionFailed
    expr: up{job="appointments-db"} == 0
    for: 1m
    annotations:
      summary: "Database connection failed"

  - alert: HighLatency
    expr: histogram_quantile(0.99, rate(request_duration_seconds_bucket[5m])) > 1
    for: 5m
    annotations:
      summary: "High API latency"
```

---

## Backup & Recovery

### 1. Database Backup
```bash
# Daily backup
pg_dump -h <host> -U postgres priya_global > /backup/priya_global_$(date +%Y%m%d).sql

# Compressed backup
pg_dump -h <host> -U postgres priya_global | gzip > /backup/priya_global_$(date +%Y%m%d).sql.gz
```

### 2. Backup Rotation
```bash
# Keep last 30 days of backups
find /backup -name "priya_global_*.sql.gz" -mtime +30 -delete
```

### 3. Restore Procedure
```bash
# Restore from backup
gunzip < /backup/priya_global_20260306.sql.gz | \
  psql -h <host> -U postgres -d priya_global
```

---

## Scaling

### Horizontal Scaling

#### Database Connection Pool Tuning
```python
# In main.py DBPool.init()
pool = await asyncpg.create_pool(
    ...,
    min_size=10,      # Increase for more services
    max_size=30,      # Max connections
)
```

#### Load Balancing
```nginx
upstream appointments {
    server 10.0.1.10:9029;
    server 10.0.1.11:9029;
    server 10.0.1.12:9029;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    location /api/v1/appointments {
        proxy_pass http://appointments;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Security Hardening

### 1. Network Security
- [ ] Use VPC with private subnets
- [ ] Restrict database access to app servers only
- [ ] Enable SSL/TLS for all connections
- [ ] Use WAF rules for API protection

### 2. Application Security
- [ ] Enable HSTS header
- [ ] Set security headers
- [ ] Implement rate limiting
- [ ] Add request validation
- [ ] Enable CORS whitelist

### 3. Database Security
- [ ] Enable SSL for PostgreSQL
- [ ] Use IAM authentication
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Encryption at rest

---

## Maintenance

### Regular Tasks
- **Daily**: Monitor logs and metrics
- **Weekly**: Check database size and backups
- **Monthly**: Review performance metrics
- **Quarterly**: Security audit and updates
- **Yearly**: Capacity planning

### Updates
```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Rebuild Docker image
docker build -t appointments-service:1.0.1 .
docker push <registry>/appointments-service:1.0.1

# Deploy new version
# (using your deployment strategy)
```

---

## Troubleshooting Deployment

### Service won't start
```bash
# Check logs
docker logs appointments-service

# Check environment variables
env | grep DB_

# Test database connection
psql -h $DB_HOST -U $DB_USER -d $DB_NAME
```

### High memory usage
```bash
# Check pool size
SELECT count(*) FROM pg_stat_activity;

# Reduce max_size in connection pool
# Restart service
```

### Slow queries
```bash
# Enable query logging
SET log_statement = 'all';

# Analyze slow queries
EXPLAIN ANALYZE SELECT ...

# Add missing indexes
```

---

**Version**: 1.0.0
**Last Updated**: 2026-03-06
**Status**: Production Ready
