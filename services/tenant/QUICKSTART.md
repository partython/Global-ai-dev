# Tenant Service - Quick Start Guide

Get the Tenant Service running in 5 minutes.

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Docker & Docker Compose (optional, but recommended)

## Option 1: Docker Compose (Recommended)

**Fastest way to get started.**

```bash
cd /mnt/Ai/priya-global/services/tenant

# Start services (PostgreSQL, Redis, Tenant Service)
docker-compose -f docker-compose.dev.yml up -d

# Check logs
docker-compose -f docker-compose.dev.yml logs -f tenant-service

# Service ready at: http://localhost:9002
# API docs at: http://localhost:9002/docs
```

**Stop services:**
```bash
docker-compose -f docker-compose.dev.yml down
```

---

## Option 2: Local Python (Manual)

**For development without Docker.**

### 1. Install Dependencies

```bash
cd /mnt/Ai/priya-global/services/tenant

pip install -r requirements.txt
```

### 2. Setup Environment

```bash
cp .env.example .env

# Edit .env with your PostgreSQL credentials
nano .env
```

Minimal config:
```bash
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=priya_global
PG_USER=priya_admin
PG_PASSWORD=your_password
```

### 3. Setup Database

```bash
# Create PostgreSQL database
createdb -U priya_admin priya_global

# Run migrations (if available)
# psql -U priya_admin -d priya_global < schema.sql
```

### 4. Start Service

```bash
# With auto-reload (development)
uvicorn main:app --host 0.0.0.0 --port 9002 --reload

# Or in background
nohup uvicorn main:app --host 0.0.0.0 --port 9002 > tenant.log 2>&1 &
```

Service ready at: `http://localhost:9002`

---

## Verify It's Working

### Health Check

```bash
curl http://localhost:9002/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "tenant",
  "port": 9002,
  "database": "connected",
  "timestamp": "2025-03-06T10:00:00Z"
}
```

### API Documentation

Visit: **http://localhost:9002/docs**

Interactive Swagger UI with all endpoints, request/response examples, and "Try it out" buttons.

---

## Test Onboarding Flow

### Step 1: Start Onboarding

```bash
curl -X POST http://localhost:9002/api/v1/onboarding/start \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "Test Corp",
    "email": "test@example.com"
  }'
```

**Response:**
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "step": 1,
  "step_name": "Welcome",
  "ai_message": "Welcome to Priya! I'm excited to help you set up your AI assistant. To get started, what's the name of your business?",
  "expected_fields": ["business_name"]
}
```

Save the `tenant_id` for the next steps.

### Step 2: Process Onboarding Step

```bash
TENANT_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X POST http://localhost:9002/api/v1/onboarding/step \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "'${TENANT_ID}'",
    "step": 1,
    "response": "Test Corp is an e-commerce business"
  }'
```

**Response (Step 1→2):**
```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "step": 2,
  "step_name": "Industry",
  "ai_message": "Great! What industry does your business operate in? (e.g., e-commerce, healthcare, finance, retail)",
  "expected_fields": ["industry"]
}
```

### Continue Through All Steps

```bash
# Step 2 → 3
curl -X POST http://localhost:9002/api/v1/onboarding/step \
  -d '{"tenant_id":"'${TENANT_ID}'","step":2,"response":"E-commerce"}'

# Step 3 → 4
curl -X POST http://localhost:9002/api/v1/onboarding/step \
  -d '{"tenant_id":"'${TENANT_ID}'","step":3,"response":"WhatsApp and Email"}'

# Step 4 → 5
curl -X POST http://localhost:9002/api/v1/onboarding/step \
  -d '{"tenant_id":"'${TENANT_ID}'","step":4,"response":"Shopify"}'

# Step 5 → 6
curl -X POST http://localhost:9002/api/v1/onboarding/step \
  -d '{"tenant_id":"'${TENANT_ID}'","step":5,"response":"Friendly tone"}'

# Step 6 (final)
curl -X POST http://localhost:9002/api/v1/onboarding/step \
  -d '{"tenant_id":"'${TENANT_ID}'","step":6,"response":"Looking great!"}'
```

### Check Onboarding Status

```bash
curl http://localhost:9002/api/v1/onboarding/status/${TENANT_ID}
```

---

## Common Issues

### PostgreSQL Connection Failed

**Error:** `could not connect to server: Connection refused`

**Solution:**
- Check PostgreSQL is running: `pg_isready`
- Verify connection string in `.env`
- For Docker: Check `docker ps` includes postgres container

### Port Already in Use

**Error:** `Address already in use`

**Solution:**
- Change port in startup command: `--port 9003`
- Or kill existing process: `lsof -i :9002` then `kill PID`

### Module Not Found

**Error:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:**
```bash
pip install -r requirements.txt
python -m pip install --upgrade pip
```

### Database Tables Not Found

**Error:** `relation "tenants" does not exist`

**Solution:**
- Run schema migrations
- Create tables manually (see README.md for SQL)

---

## Next Steps

1. **Read the docs:**
   - `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/tenant/README.md` - Full documentation
   - `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/tenant/API_EXAMPLES.md` - All API endpoints

2. **Run tests:**
   ```bash
   pip install pytest pytest-asyncio
   pytest test_tenant_service.py -v
   ```

3. **Explore API:**
   - Open http://localhost:9002/docs
   - Try out endpoints in the interactive UI

4. **Setup auth:**
   - Get JWT token from Auth Service (port 9001)
   - Use in Authorization header for protected endpoints

5. **Integrate with other services:**
   - Gateway (9000) - API routing
   - Auth Service (9001) - User authentication
   - AI Engine (9020) - LLM responses
   - Billing Service (9027) - Plan management

---

## Development Tips

### Hot Reload

When running locally with `--reload`, changes to `main.py` are auto-detected.

```bash
uvicorn main:app --host 0.0.0.0 --port 9002 --reload --reload-dirs=.
```

### Debug Logging

```bash
LOG_LEVEL=DEBUG uvicorn main:app --port 9002 --reload
```

### View Database

```bash
# Connect to PostgreSQL
psql -U priya_admin -d priya_global

# List tables
\dt

# View tenants
SELECT id, business_name, plan, status FROM tenants;

# View team members
SELECT email, role, status FROM team_members;
```

### Inspect API Requests

```bash
# View all database queries
LOG_LEVEL=DEBUG uvicorn main:app --port 9002

# Use curl with verbose
curl -v http://localhost:9002/health

# Or use httpie (better formatting)
pip install httpie
http http://localhost:9002/health
```

---

## Troubleshooting Onboarding

### Tenant Created But Can't Access

Onboarding creates a tenant without requiring auth. After onboarding:

1. **Create user account** via Auth Service (port 9001)
2. **Get JWT token** from Auth Service
3. **Now you can** call protected endpoints with the token

### Incomplete Onboarding

Check onboarding status:
```bash
curl http://localhost:9002/api/v1/onboarding/status/${TENANT_ID}
```

Response shows `current_step` and `data` collected so far. You can resume from where you left off.

### Reset Onboarding

To start fresh, you need to delete the tenant (soft delete):

```bash
# This requires a JWT token and owner role
curl -X DELETE http://localhost:9002/api/v1/tenants/${TENANT_ID} \
  -H "Authorization: Bearer ${JWT_TOKEN}"
```

---

## Performance Tips

1. **Use connection pooling:** Set `PG_POOL_MIN=5` and `PG_POOL_MAX=20` for production
2. **Enable query caching:** Redis integration (future feature)
3. **Monitor slow queries:** `log_min_duration_statement=1000` in PostgreSQL
4. **Profile with:** `pip install pyinstrument && python -m pyinstrument main:app`

---

## Production Deployment

When deploying to production:

1. **Security:**
   - Set proper JWT keys (not dev keys)
   - Enable HTTPS/TLS
   - Use strong database passwords
   - Enable PostgreSQL SSL mode

2. **Performance:**
   - Use connection pooling
   - Deploy 3+ replicas behind load balancer
   - Use read replicas for analytics queries

3. **Monitoring:**
   - Setup error tracking (Sentry)
   - Monitor API latency
   - Track database connection pool
   - Setup uptime monitoring

4. **Backup:**
   - Daily database backups
   - Point-in-time recovery capability
   - Test restore procedures monthly

---

## Support

For issues or questions:
- Check logs: `docker-compose logs tenant-service`
- Review documentation: `README.md`
- See API examples: `API_EXAMPLES.md`
- Run tests: `pytest test_tenant_service.py -v`

---

**Service is now running!** 🎉

Start with: http://localhost:9002/docs
