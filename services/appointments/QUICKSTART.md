# Appointment Booking Service - Quick Start Guide

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- pip package manager

## Installation

### 1. Clone/Create Environment

```bash
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/appointments
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Environment Variables

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 4. Initialize Database

```sql
-- Connect to PostgreSQL
psql -U postgres -d priya_global

-- Run schema setup
\i schema.sql

-- Verify tables
\dt
```

### 5. Start Service

```bash
python main.py
```

Service runs on `http://localhost:9029`

## Testing

### 1. Generate Test JWT Token

```python
import jwt
import json

secret = "dev-secret"
payload = {
    "tenant_id": "tenant_001",
    "user_id": "agent_001",
    "user_type": "agent"
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Bearer {token}")
```

### 2. Test Health Endpoint

```bash
curl http://localhost:9029/api/v1/appointments/health
```

### 3. Create Appointment

```bash
curl -X POST http://localhost:9029/api/v1/appointments \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_123",
    "agent_id": "agent_001",
    "title": "Sales Consultation",
    "scheduled_start": "2026-03-20T10:00:00Z",
    "scheduled_end": "2026-03-20T11:00:00Z",
    "timezone": "UTC"
  }'
```

### 4. List Appointments

```bash
curl http://localhost:9029/api/v1/appointments \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 5. Get Available Slots

```bash
curl "http://localhost:9029/api/v1/appointments/available-slots?agent_id=agent_001&date=2026-03-20&duration_minutes=60&timezone=UTC" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 6. Get Analytics

```bash
curl "http://localhost:9029/api/v1/appointments/analytics?start_date=2026-03-01&end_date=2026-03-31" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Database Maintenance

### Check Appointments

```sql
SELECT appointment_id, customer_id, agent_id, status, scheduled_start
FROM appointments
WHERE tenant_id = 'tenant_001'
ORDER BY scheduled_start DESC
LIMIT 10;
```

### Check Agent Availability

```sql
SELECT agent_id, start_time, end_time, availability_type, recurring_pattern
FROM availability_windows
WHERE tenant_id = 'tenant_001'
AND agent_id = 'agent_001'
ORDER BY start_time DESC;
```

### Get Analytics Data

```sql
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN status = 'confirmed' THEN 1 END) as confirmed,
    COUNT(CASE WHEN status = 'no_show' THEN 1 END) as no_shows
FROM appointments
WHERE tenant_id = 'tenant_001'
AND scheduled_start >= CURRENT_DATE - INTERVAL '30 days';
```

## Common Issues

### Database Connection Error

```
Error: could not connect to server
```

**Solution**: Check PostgreSQL is running and credentials are correct in .env

### Invalid Token

```
Error: Invalid token
```

**Solution**: Generate new token with correct secret and tenant_id

### Timezone Error

```
Error: Invalid timezone
```

**Solution**: Use valid IANA timezone (e.g., America/New_York, Europe/London, Asia/Tokyo)

### Appointment Slot Conflict

```
Error: Appointment slot already booked (409)
```

**Solution**: Choose different time slot or check agent availability

## Performance Optimization

### Add Database Indexes (Already Included)

```sql
-- Check existing indexes
SELECT * FROM pg_indexes WHERE tablename = 'appointments';
```

### Monitor Connection Pool

```python
# In main.py, DBPool status
pool = DBPool.pool
print(f"Pool size: {pool._holders}")
```

### Query Performance

```sql
-- Enable query logging
SET log_statement = 'all';
SET log_duration = 'on';

-- Analyze slow queries
EXPLAIN ANALYZE SELECT * FROM appointments WHERE tenant_id = 'tenant_001';
```

## Deployment Checklist

- [ ] Set strong JWT_SECRET in production
- [ ] Configure CORS_ORIGINS to allowed domains
- [ ] Set secure DB_PASSWORD
- [ ] Enable SSL/TLS for database connection
- [ ] Configure logging level to INFO or WARNING
- [ ] Set up database backups
- [ ] Configure monitoring/alerting
- [ ] Test JWT token validation
- [ ] Verify timezone handling
- [ ] Load test connection pool

## Next Steps

1. Review README.md for complete API documentation
2. Check schema.sql for advanced table configuration
3. Implement Google Calendar integration
4. Add email/SMS reminder functionality
5. Set up monitoring and alerting
6. Configure automated backups

## Support

For issues or questions:
1. Check logs: `tail -f app.log`
2. Review error messages in response
3. Check environment variables
4. Verify database connectivity
5. Test JWT tokens

---

**Service Ready at**: http://localhost:9029
**API Docs** (when available): http://localhost:9029/docs
**Health Check**: http://localhost:9029/api/v1/appointments/health
