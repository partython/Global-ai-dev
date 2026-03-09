# Priya Global Platform — Docker Guide

Complete Docker setup for 36 FastAPI microservices + 1 Next.js dashboard.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│           Priya Global Platform (Docker Stack)              │
└─────────────────────────────────────────────────────────────┘
                            
├─ Infrastructure Layer
│  ├─ PostgreSQL 16          (Database: priya_global)
│  ├─ Redis 7                (Cache & Pubsub)
│  └─ Kafka 3.7              (Event Streaming)
│
├─ Layer 0: Gateway
│  └─ gateway:9000           (API Entry Point)
│
├─ Layer 1: Identity & Multi-tenancy
│  ├─ auth:9001              (Authentication/JWT)
│  ├─ tenant:9002            (Tenant Management)
│  └─ tenant-config:9042     (Configuration Service)
│
├─ Layer 2: Routing & Intelligence
│  ├─ channel-router:9003    (Message Routing)
│  └─ ai-engine:9004         (Core AI/ML)
│
├─ Layer 3: Communication Channels (7 services)
│  ├─ whatsapp:9010          (WhatsApp Business)
│  ├─ email:9011             (SMTP/Email)
│  ├─ voice:9012             (VOIP Integration)
│  ├─ social:9013            (FB, Instagram, etc)
│  ├─ webchat:9014           (Web Widget)
│  ├─ sms:9015               (SMS Provider)
│  └─ telegram:9016          (Telegram Bot)
│
├─ Layer 4: Business Logic (8 services)
│  ├─ billing:9020           (Payment Processing)
│  ├─ analytics:9021         (Basic Analytics)
│  ├─ marketing:9022         (Campaign Management)
│  ├─ ecommerce:9023         (E-commerce Integration)
│  ├─ notification:9024      (Notification Hub)
│  ├─ plugins:9025           (Plugin System)
│  ├─ handoff:9026           (Agent Handoff)
│  └─ leads:9027             (Lead Management)
│
├─ Layer 5: Advanced Features (9 services)
│  ├─ conversation-intel:9028    (NLP Analysis)
│  ├─ appointments:9029          (Calendar/Scheduling)
│  ├─ knowledge:9030             (FAQ/Documentation)
│  ├─ voice-ai:9031             (Voice Assistant)
│  ├─ video:9032                (Video Streaming)
│  ├─ rcs:9033                  (Rich Communication)
│  ├─ workflows:9034            (Automation)
│  ├─ advanced-analytics:9035   (ML Analytics)
│  ├─ ai-training:9036          (Model Training)
│  └─ marketplace:9037          (App Marketplace)
│
├─ Layer 6: Platform Operations (4 services)
│  ├─ compliance:9038        (Compliance/Audit)
│  ├─ health-monitor:9039    (System Health)
│  ├─ cdn-manager:9040       (CDN & Assets)
│  └─ deployment:9041        (CI/CD)
│
└─ Frontend
   └─ dashboard:3000         (Next.js Admin Panel)
```

## Files Structure

```
priya-global/
├── Dockerfile.python-base      Multi-stage Python base image
├── Dockerfile.service          Generic microservice template
├── Dockerfile.dashboard        Next.js 14 dashboard
├── docker-compose.yml          Complete dev stack
├── .dockerignore               Build exclusions
├── Makefile                    Convenience commands
├── requirements.txt            Python dependencies
├── config/                     Configuration files
├── shared/                     Shared Python modules
├── services/                   36 microservices
│   ├── gateway/
│   ├── auth/
│   ├── tenant/
│   ├── ... (33 more services)
│   └── tenant_config/
└── dashboard/                  Next.js frontend
```

## Docker Files Explained

### 1. Dockerfile.python-base

Multi-stage build that all Python services inherit from:

**Stage 1 - Builder:**
- Installs compilation dependencies (gcc, libpq-dev, libffi-dev)
- Builds all Python packages with pip
- Creates a clean `/install` directory

**Stage 2 - Runtime:**
- Starts fresh from python:3.11-slim-bookworm
- Adds only runtime dependencies (libpq5, curl, tini)
- Creates non-root user `priya` for security
- Copies built packages from builder stage
- Includes shared code (shared/, config/)
- Sets up healthcheck endpoint
- Uses tini as PID 1 for proper signal handling

**Key Features:**
- Multi-stage build minimizes final image size (roughly 50% smaller)
- Non-root user prevents container escape
- Tini ensures graceful shutdown (SIGTERM handling)
- Shared code is read-only (chmod 555)

### 2. Dockerfile.service

Extends python-base for individual microservices:

**Build Arguments:**
```dockerfile
--build-arg SERVICE_NAME=gateway
--build-arg SERVICE_PORT=9000
--build-arg WORKERS=2  # Optional
```

**Key Features:**
- Adds service-specific code from `services/{SERVICE_NAME}/`
- Configures uvicorn with workers and httptools
- Sets environment variables (SERVICE_PORT, WORKERS, PYTHONPATH)
- Service-specific healthcheck
- Non-root user enforcement

**Example Build:**
```bash
docker build -f Dockerfile.service \
  --build-arg SERVICE_NAME=gateway \
  --build-arg SERVICE_PORT=9000 \
  -t priya-global/gateway:latest .
```

### 3. Dockerfile.dashboard

Multi-stage Next.js build:

**Stage 1 - deps:**
- Installs node_modules (npm ci or yarn)
- Optimized for layer caching

**Stage 2 - builder:**
- Copies dependencies and source
- Runs `npm run build`
- Accepts build args: NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SENTRY_DSN, etc.

**Stage 3 - runner:**
- Minimal Alpine image (Node.js 20)
- Copies only built artifacts (.next/standalone, .next/static)
- Non-root user `priya`
- Healthcheck on port 3000

### 4. docker-compose.yml

Complete local development stack with:

**Key Features:**
- Service profiles for selective startup (core, channels, business, advanced, ops, infra)
- YAML anchors (`x-python-service`) for DRY configuration
- 3 infrastructure services (PostgreSQL, Redis, Kafka)
- 36 microservices with proper port mapping
- 1 Next.js dashboard
- Health checks for all services
- Custom bridge network (172.28.0.0/16)
- Named volumes for persistence

**Profiles:**
- `infra` — PostgreSQL, Redis, Kafka
- `core` — Gateway, Auth, Tenant, Channel Router, AI Engine, Tenant Config
- `channels` — 7 communication channels
- `business` — 8 business logic services
- `advanced` — 9 advanced feature services
- `ops` — 4 operational services

### 5. .dockerignore

Excludes unnecessary files from build context:
- Version control (.git, .gitignore)
- Dependencies (node_modules, __pycache__)
- IDE files (.vscode, .idea)
- Tests and documentation
- Environment files (.env but not .env.example)
- Build artifacts (.next, dist/)

### 6. Makefile

Convenience commands for common operations:

```bash
make help                   # Show all commands
make build                  # Build all images
make build-base             # Build python-base only
make build-services         # Build all 36 microservices
make build-dashboard        # Build dashboard only

make up-infra              # Start infrastructure
make up-core               # Start core services
make up-channels           # Start channel services
make up-business           # Start business services
make up-advanced           # Start advanced services
make up-ops                # Start operational services
make up                    # Start everything

make down                  # Stop all services
make restart               # Restart all services
make logs                  # Tail all logs
make ps                    # Show running services

make up-gateway            # Start specific service
make logs-gateway          # Tail logs for service
make restart-gateway       # Restart service

make db-shell              # PostgreSQL shell
make redis-shell           # Redis CLI
make clean                 # Remove containers & volumes
```

## Quick Start Guide

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum (16GB recommended)
- 20GB disk space

### 1. Start Infrastructure Only

```bash
make up-infra
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- Kafka (port 9092, 9093)

```bash
make db-shell              # Connect to PostgreSQL
make redis-shell           # Connect to Redis
```

### 2. Start Core Platform (Recommended)

```bash
make up-core
```

This starts infrastructure + 5 core services:
- gateway:9000
- auth:9001
- tenant:9002
- channel-router:9003
- ai-engine:9004
- tenant-config:9042
- dashboard:3000

### 3. Add Services Selectively

```bash
make up-channels           # Add 7 channel services
make up-business           # Add 8 business services
make up-advanced           # Add 9 advanced services
make up-ops                # Add 4 operational services
```

### 4. Start Everything

```bash
make up
```

### 5. Monitor Services

```bash
make ps                    # List running services
make logs                  # Stream all logs
make logs-gateway          # Logs for specific service
```

### 6. Stop and Clean Up

```bash
make down                  # Stop all services (keeps volumes)
make clean                 # Remove everything including volumes
```

## Building Images

### Build All Images

```bash
make build
```

This:
1. Builds `priya-global/python-base:latest`
2. Builds all 36 microservice images
3. Builds `priya-global/dashboard:latest`

### Build Individual Images

```bash
# Build a single service
docker build -f Dockerfile.service \
  --build-arg SERVICE_NAME=billing \
  --build-arg SERVICE_PORT=9020 \
  -t priya-global/billing:latest .

# Build dashboard with custom API URL
docker build -f Dockerfile.dashboard \
  --build-arg NEXT_PUBLIC_API_URL=http://api.example.com \
  -t priya-global/dashboard:latest .
```

### Push to Registry

```bash
# Tag for registry
docker tag priya-global/python-base:latest \
  registry.example.com/priya-global/python-base:latest

# Push
docker push registry.example.com/priya-global/python-base:latest

# Or using Makefile with REGISTRY var
REGISTRY=registry.example.com make build
```

## Environment Configuration

Create `.env` file in project root:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://priya:priya_dev_2024@postgres:5432/priya_global

# Cache
REDIS_URL=redis://redis:6379/0

# Message Queue
KAFKA_BOOTSTRAP_SERVERS=kafka:9092

# Monitoring
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0
SENTRY_ENABLED=true

# API Configuration
API_HOST=0.0.0.0
WORKERS_PER_SERVICE=2

# Dashboard
NEXT_PUBLIC_API_URL=http://localhost:9000
NEXT_PUBLIC_ENVIRONMENT=development
```

## Service Communication

### Internal Service-to-Service

Services communicate via internal Docker network:

```python
# From gateway service calling another service
import httpx

async def call_auth_service():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://auth:9001/verify",
            timeout=5.0
        )
        return response.json()
```

### External API Calls

Use exposed ports for testing:

```bash
# Gateway API
curl http://localhost:9000/health

# Auth service
curl http://localhost:9001/health

# Dashboard
curl http://localhost:3000/
```

## Scaling Services

### Scale Horizontally (Multiple Instances)

```bash
# Start 3 instances of billing service
docker compose up -d --scale billing=3
```

Note: Requires load balancer (e.g., nginx) in front.

### Scale by Worker Count

Modify docker-compose.yml:

```yaml
billing:
  <<: *python-service
  build:
    args:
      WORKERS: "8"  # Increase from 2 to 8
```

Then rebuild:

```bash
make build-services
make restart-billing
```

## Debugging

### View Logs

```bash
# All services
make logs

# Specific service
make logs-gateway

# Follow logs for auth service
docker compose logs -f --tail=100 auth

# View container filesystem
docker exec -it priya-gateway ls -la /app/services/gateway/
```

### Execute Commands in Container

```bash
# Run Python REPL in auth service
docker exec -it priya-auth python

# Check environment variables
docker exec priya-gateway env | grep SERVICE

# Test database connection
docker exec priya-auth psql -h postgres -U priya -d priya_global -c "SELECT 1"
```

### Inspect Network

```bash
# View network
docker network inspect priya-net

# Ping service from gateway
docker exec priya-gateway ping redis

# Check DNS resolution
docker exec priya-gateway nslookup postgres
```

## Performance Optimization

### For Development

```yaml
# docker-compose.yml - reduce workers
WORKERS: "1"
```

### For Production

1. Use separate docker-compose file:

```bash
docker compose -f docker-compose.prod.yml up -d
```

2. Increase workers:

```dockerfile
ENV WORKERS=4
```

3. Add reverse proxy (nginx/traefik):

```yaml
services:
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - gateway
```

4. Use dedicated cache/queue infrastructure
5. Enable Redis persistence
6. Configure PostgreSQL connection pooling
7. Use separate Kafka brokers

## Security Considerations

### Container Security

1. Non-root user: Services run as `priya` user
2. Read-only filesystem: Shared modules are read-only
3. Health checks: All services have health endpoints
4. Network isolation: Services on internal bridge network
5. Signal handling: Tini ensures graceful shutdown

### Secret Management

Never commit `.env` with secrets:

```bash
# Use .env.example as template
cp .env.example .env

# Add secrets to .env (git ignored)
echo "DATABASE_PASSWORD=actual_password" >> .env

# In CI/CD, inject secrets from vault
docker compose --env-file secrets.env up -d
```

### Port Exposure

Only expose necessary ports:

```yaml
# Avoid exposing all microservice ports in production
# Use API gateway as single entry point
ports:
  - "9000:9000"  # Gateway only
  # Remove individual service ports
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
make logs-servicename

# Check if port is in use
lsof -i :9000

# Check resource constraints
docker stats
```

### Database Connection Issues

```bash
# Test from container
docker exec priya-gateway psql -h postgres -U priya -d priya_global

# Check PostgreSQL logs
docker logs priya-postgres

# Verify network connectivity
docker exec priya-gateway ping postgres
```

### High Memory Usage

```bash
# View resource usage
docker stats

# Limit container memory in docker-compose.yml
services:
  gateway:
    deploy:
      resources:
        limits:
          memory: 512M
```

### Services Can't Communicate

```bash
# Check network
docker network ls
docker network inspect priya-net

# Verify DNS resolution
docker exec priya-gateway nslookup auth

# Check firewall/port bindings
docker port priya-gateway
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build & Push
on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: docker/setup-buildx-action@v1
      - uses: docker/login-action@v1
        with:
          registry: ${{ secrets.REGISTRY }}
          username: ${{ secrets.REGISTRY_USER }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      - uses: docker/build-push-action@v2
        with:
          file: ./Dockerfile.service
          build-args: |
            SERVICE_NAME=gateway
            SERVICE_PORT=9000
          push: true
          tags: registry.example.com/priya-global/gateway:${{ github.sha }}
```

## Performance Metrics

Typical image sizes:

- `python-base` — 450MB
- Individual service — 500MB
- Dashboard — 380MB

Startup times (with warm cache):

- Infrastructure (postgres, redis, kafka) — 10-15s
- Core services (5 services) — 5-8s
- Full platform (41 services) — 30-45s

## References

- [Docker Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Compose File Specification](https://docs.docker.com/compose/compose-file/)
- [Python in Docker](https://docs.docker.com/language/python/)
- [Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)

