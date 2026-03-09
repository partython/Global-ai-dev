# Quick Start Guide - Lead Scoring & Sales Pipeline Service

## Installation & Setup (5 minutes)

### 1. Prerequisites Check
```bash
# Verify Python 3.9+
python3 --version

# Verify PostgreSQL is running
psql --version

# Verify Docker (optional)
docker --version
```

### 2. Local Development Setup

```bash
# Navigate to service directory
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/leads

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Edit .env with your database credentials
nano .env  # or use your preferred editor
```

### 3. Database Setup

```bash
# Create database
createdb -U postgres leads_db

# Initialize schema
psql -U postgres -d leads_db -f init_db.sql

# Verify tables created
psql -U postgres -d leads_db -c "\dt"
```

### 4. Start the Service

```bash
# Option A: Development mode (with auto-reload)
uvicorn main:app --reload --host 0.0.0.0 --port 9027

# Option B: Production mode
python main.py

# Option C: Docker Compose (includes PostgreSQL)
docker-compose up
```

Service will be available at: **http://localhost:9027**

## Testing the Service

### 1. Health Check
```bash
curl http://localhost:9027/api/v1/leads/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "service": "Lead Scoring & Sales Pipeline",
  "version": "1.0.0"
}
```

### 2. Generate Test JWT Token
```bash
python3 << 'PYTHON'
import jwt
import json

secret = "your_jwt_secret"  # From your .env file
payload = {
    "sub": "user_123",
    "tenant_id": "tenant_456",
    "email": "user@example.com"
}

token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Token: {token}")
PYTHON
```

### 3. Create a Lead
```bash
TOKEN="<your_jwt_token>"

curl -X POST http://localhost:9027/api/v1/leads \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "company": "Acme Corp",
    "source_channel": "web",
    "initial_score": 65.5,
    "custom_data": {
      "industry": "Technology",
      "employee_count": 500
    }
  }'
```

### 4. List Leads
```bash
curl -X GET "http://localhost:9027/api/v1/leads?skip=0&limit=10&sort_by=created_at&order=desc" \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Recalculate Lead Score
```bash
LEAD_ID="lead_1234567890_tenant_456"

curl -X POST http://localhost:9027/api/v1/leads/$LEAD_ID/score \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "engagement_score": 85,
    "demographic_score": 75,
    "behavior_score": 80,
    "intent_score": 90
  }'
```

### 6. Get Pipeline Analytics
```bash
curl -X GET http://localhost:9027/api/v1/pipeline/analytics \
  -H "Authorization: Bearer $TOKEN"
```

## Environment Configuration

### Required Variables (.env)
```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=leads_db
DB_USER=postgres
DB_PASSWORD=your_secure_password

# JWT Secret
JWT_SECRET=your_jwt_secret_key_here

# CORS (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

### Optional Variables
```bash
# Logging
LOG_LEVEL=INFO

# Service
SERVICE_ENV=development

# Feature flags
ENABLE_AUTO_SCORING=true
ENABLE_SCORE_DECAY=true
```

## Docker Compose Quick Start (Easiest)

```bash
# Start everything in one command
docker-compose up -d

# View logs
docker-compose logs -f leads_service

# Stop services
docker-compose down
```

This will:
- Create and start PostgreSQL database
- Initialize database schema
- Start the leads service
- All on the correct network

## Common Tasks

### View Service Logs
```bash
# Local
tail -f leads_service.log

# Docker
docker-compose logs -f leads_service

# Kubernetes
kubectl logs -f deployment/leads-service -n leads
```

### Reset Database
```bash
# Drop and recreate (development only)
dropdb -U postgres leads_db
createdb -U postgres leads_db
psql -U postgres -d leads_db -f init_db.sql
```

### Backup Database
```bash
pg_dump -U postgres leads_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore Database
```bash
psql -U postgres -d leads_db < backup_20240101_120000.sql
```

## Troubleshooting

### Database Connection Error
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql  # Linux
brew services list              # macOS

# Test connection
psql -h localhost -U postgres -d leads_db -c "SELECT 1"
```

### JWT Token Errors
```bash
# Verify JWT_SECRET in .env matches your token
echo $JWT_SECRET

# Generate new token with correct secret
python3 << 'PYTHON'
import jwt
secret = "your_jwt_secret_from_env"
token = jwt.encode({"sub": "user", "tenant_id": "t1"}, secret)
print(token)
PYTHON
```

### Port Already in Use
```bash
# Find what's using port 9027
lsof -i :9027

# Kill the process
kill -9 <PID>

# Or use a different port
uvicorn main:app --port 9028
```

### Import Errors
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Verify Python packages
pip list | grep -E "fastapi|asyncpg|pyjwt"
```

## Next Steps

1. **Read the Full Documentation**
   - `README.md` - Features overview
   - `API_DOCUMENTATION.md` - Complete API reference
   - `PROJECT_SUMMARY.md` - Architecture details

2. **Deploy to Production**
   - See `DEPLOYMENT.md` for production setup
   - Docker, Kubernetes, or Cloud provider options

3. **Customize for Your Needs**
   - Modify scoring weights in `main.py` line ~400
   - Add custom pipeline stages
   - Integrate with your auth system

4. **Add Tests**
   - Run: `pytest test_example.py -v`
   - Add more tests for your custom logic

## API Endpoints Cheat Sheet

```bash
# Create lead
POST /api/v1/leads

# List leads
GET /api/v1/leads?skip=0&limit=20

# Get lead detail
GET /api/v1/leads/{lead_id}

# Update lead
PUT /api/v1/leads/{lead_id}

# Score lead
POST /api/v1/leads/{lead_id}/score

# Score history
GET /api/v1/leads/{lead_id}/score-history

# Advance pipeline
POST /api/v1/leads/{lead_id}/advance

# Assign lead
POST /api/v1/leads/assign

# Pipeline config
GET /api/v1/pipeline/stages
PUT /api/v1/pipeline/stages

# Analytics
GET /api/v1/pipeline/analytics
GET /api/v1/pipeline/forecast

# Duplicates
POST /api/v1/leads/deduplicate

# Health
GET /api/v1/leads/health
```

## Performance Tips

1. **Connection Pooling**: Configured for 2-10 connections (adjust in main.py)
2. **Indexes**: Database indexes on tenant_id, email, stage, created_at
3. **Pagination**: Always use limit/skip for large datasets
4. **Caching**: Consider Redis for frequently accessed data
5. **Async**: All operations are async/await optimized

## Support & Documentation

- **API Docs**: http://localhost:9027/docs (Swagger UI)
- **ReDoc**: http://localhost:9027/redoc
- **Help**: See `API_DOCUMENTATION.md` for detailed endpoint specs

---

**Ready to go!** 🚀

Service is now ready to accept requests. See the examples above or refer to `API_DOCUMENTATION.md` for more details.
