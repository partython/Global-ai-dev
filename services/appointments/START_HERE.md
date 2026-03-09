# Appointment Booking Service - START HERE

## What You Have

A complete, production-ready appointment booking service for the Global AI Sales Platform with:

- **998 lines** of production code (main.py)
- **13 API endpoints** fully implemented
- **6 database tables** with RLS isolation
- **4,700+ lines** of comprehensive documentation
- **5 deployment options** (Docker, Compose, Systemd, ECS, Kubernetes)
- **Zero hardcoded secrets** - environment-based configuration
- **Enterprise security** - JWT, RLS, parameterized queries

## Quick Navigation

### I Want to Get Running Fast (5 minutes)
→ Read **[QUICKSTART.md](QUICKSTART.md)**

### I Want to Understand What This Does
→ Read **[README.md](README.md)**

### I Want to Test the API
→ Read **[TESTING_EXAMPLES.md](TESTING_EXAMPLES.md)**

### I Want API Documentation
→ Read **[API_DOCUMENTATION.md](API_DOCUMENTATION.md)**

### I Want to Deploy to Production
→ Read **[DEPLOYMENT.md](DEPLOYMENT.md)**

### I Want a Complete Overview
→ Read **[SERVICE_SUMMARY.md](SERVICE_SUMMARY.md)**

### I Need Help Navigating
→ Read **[INDEX.md](INDEX.md)**

## Five-Minute Startup

```bash
# 1. Go to the service directory
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/appointments

# 2. Create environment file
cp .env.example .env

# 3. Edit .env with your database credentials
# DATABASE_HOST, DATABASE_PORT, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD
# JWT_SECRET (generate something like: python -c "import secrets; print(secrets.token_urlsafe(32))")

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create PostgreSQL database and schema
# First ensure PostgreSQL is running, then:
psql -U postgres -d your_database < schema.sql

# 6. Start the service
python main.py
```

Service will be available at: **http://localhost:9029**

Health check: **http://localhost:9029/api/v1/appointments/health**

## Key Files

| File | Purpose | Read When |
|------|---------|-----------|
| **main.py** | Core service code (998 lines) | Understand implementation |
| **schema.sql** | Database schema | Setup PostgreSQL |
| **requirements.txt** | Python dependencies | Install packages |
| **.env.example** | Configuration template | Setup environment |
| **README.md** | Complete overview | Learn features |
| **QUICKSTART.md** | 5-minute setup | Get running fast |
| **API_DOCUMENTATION.md** | Full API reference | Use the service |
| **TESTING_EXAMPLES.md** | Test cases & examples | Test it out |
| **DEPLOYMENT.md** | Production setup | Deploy it |
| **SERVICE_SUMMARY.md** | Implementation details | Deep dive |
| **INDEX.md** | Navigation guide | Find what you need |

## What Each Service Does

### Appointment Management
- Create, read, update, delete appointments
- Confirm appointments
- Reschedule appointments
- Cancel appointments

### Calendar Management
- Set agent availability
- Get agent availability
- Get available time slots for booking
- Support recurring patterns (daily, weekly, monthly)

### Notifications
- Send appointment reminders (email, SMS, push, in-app)
- Track reminder delivery

### Analytics
- Booking counts and rates
- No-show tracking
- Average meeting duration
- Agent utilization rates
- Peak booking times

## Example API Call

```bash
# 1. Generate a JWT token (example)
TOKEN=$(python3 << 'PYTHON'
import jwt
payload = {
    "tenant_id": "tenant_001",
    "user_id": "agent_001",
    "user_type": "agent"
}
token = jwt.encode(payload, "your-jwt-secret", algorithm="HS256")
print(token)
PYTHON
)

# 2. Create an appointment
curl -X POST http://localhost:9029/api/v1/appointments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_001",
    "agent_id": "agent_001",
    "title": "Sales Demo",
    "scheduled_start": "2026-03-20T14:00:00Z",
    "scheduled_end": "2026-03-20T15:00:00Z",
    "timezone": "America/New_York"
  }'

# 3. Check health
curl http://localhost:9029/api/v1/appointments/health
```

## Tech Stack

- **Framework**: FastAPI (async Python web framework)
- **Database**: PostgreSQL with asyncpg
- **Authentication**: JWT tokens
- **Deployment**: Uvicorn ASGI server

All details in [README.md](README.md#technology-stack)

## Security Built-In

- JWT authentication on all endpoints
- Multi-tenant isolation (Row-Level Security)
- Parameterized SQL queries (no injection)
- All secrets from environment (no hardcoding)
- CORS whitelist from environment
- Timezone validation

Details in [README.md](README.md#security)

## Common Questions

### Q: How do I set up the database?
A: See [QUICKSTART.md - Database Setup](QUICKSTART.md)

### Q: What are all the API endpoints?
A: See [API_DOCUMENTATION.md](API_DOCUMENTATION.md)

### Q: How do I test this?
A: See [TESTING_EXAMPLES.md](TESTING_EXAMPLES.md)

### Q: How do I deploy to production?
A: See [DEPLOYMENT.md](DEPLOYMENT.md)

### Q: Where do I put my secrets?
A: In .env file (never in code) - see .env.example

### Q: What timezones are supported?
A: All IANA timezones (e.g., America/New_York, Europe/London, Asia/Tokyo)

### Q: Can multiple tenants use this?
A: Yes! Multi-tenant isolation built-in at database level

### Q: How do I integrate with Google Calendar?
A: Architecture is prepared. See [SERVICE_SUMMARY.md - Future Enhancements](SERVICE_SUMMARY.md#future-enhancement-hooks)

## Architecture Overview

```
Client (Web/Mobile)
        ↓
   FastAPI Service (Port 9029)
        ↓
   JWT Authentication
        ↓
   13 API Endpoints
        ↓
   AsyncPG Connection Pool
        ↓
   PostgreSQL Database (Multi-tenant RLS)
```

Each request:
1. Validates JWT token
2. Extracts tenant_id and user_id
3. Executes query with RLS isolation
4. Returns data for that tenant only

## What's Next?

1. **First Time**: Read QUICKSTART.md (5 minutes)
2. **Setup**: Follow QUICKSTART.md setup steps
3. **Test**: Use examples from TESTING_EXAMPLES.md
4. **Integrate**: Use API endpoints from API_DOCUMENTATION.md
5. **Deploy**: Follow DEPLOYMENT.md for production

## Support Resources

- **API Questions**: See API_DOCUMENTATION.md
- **Setup Issues**: See QUICKSTART.md "Common Issues"
- **Code Questions**: See SERVICE_SUMMARY.md
- **Deployment Help**: See DEPLOYMENT.md
- **Need Everything?**: See INDEX.md for complete map

## Files at a Glance

```
📁 /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/appointments/
├── main.py                      ← The service (run this)
├── schema.sql                   ← Database schema (run in PostgreSQL)
├── requirements.txt             ← Dependencies (pip install)
├── .env.example                 ← Configuration template (copy to .env)
├── README.md                    ← Feature overview
├── QUICKSTART.md               ← 5-minute setup
├── API_DOCUMENTATION.md        ← Complete API reference
├── TESTING_EXAMPLES.md         ← Test cases
├── SERVICE_SUMMARY.md          ← Implementation details
├── DEPLOYMENT.md               ← Production deployment
├── INDEX.md                    ← Navigation guide
└── START_HERE.md              ← This file
```

## Running on Port 9029

The service is configured to run on **port 9029** by default.

Change it in .env:
```
PORT=9029
HOST=0.0.0.0
```

## Next Steps

1. Copy .env.example to .env
2. Edit .env with your credentials
3. Run: `pip install -r requirements.txt`
4. Create database: `psql ... < schema.sql`
5. Start service: `python main.py`
6. Test health: `curl http://localhost:9029/api/v1/appointments/health`

**You're ready to go!**

---

For complete details, see:
- **Quick Setup**: [QUICKSTART.md](QUICKSTART.md)
- **Full Features**: [README.md](README.md)
- **All Endpoints**: [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- **Tests**: [TESTING_EXAMPLES.md](TESTING_EXAMPLES.md)
- **Production**: [DEPLOYMENT.md](DEPLOYMENT.md)

---

**Service Version**: 1.0.0
**Status**: Production Ready
**Created**: 2026-03-06
