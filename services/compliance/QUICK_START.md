# Compliance & GDPR Service - Quick Start Guide

## Installation

```bash
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/compliance

pip install fastapi uvicorn pydantic pyjwt asyncpg python-multipart
```

## Environment Setup

Create `.env` file:

```bash
# Required
JWT_SECRET=your-super-secret-key-minimum-32-chars
DB_HOST=localhost
DB_NAME=priya_compliance
DB_USER=postgres
DB_PASSWORD=your-db-password

# Optional (defaults shown)
DB_PORT=5432
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
DATA_RETENTION_DEFAULT_DAYS=2555
DSAR_EXPIRATION_DAYS=45
PII_MASKING_CHARS=4
```

## Running the Service

```bash
# Direct execution
python main.py

# Or with uvicorn
uvicorn main:app --host 0.0.0.0 --port 9038

# With reload for development
uvicorn main:app --host 0.0.0.0 --port 9038 --reload
```

Service will be available at: `http://localhost:9038`

## Health Check (No Auth)

```bash
curl -X GET http://localhost:9038/compliance/health
```

## JWT Token Format

Create a token with payload:

```json
{
  "tenant_id": "tenant_123",
  "user_id": "user_456",
  "email": "user@example.com",
  "iat": 1640000000,
  "exp": 1640086400
}
```

Sign with your JWT_SECRET using HS256.

## Common Workflows

### 1. Submit DSAR Request

```bash
curl -X POST http://localhost:9038/compliance/dsar \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_123",
    "email": "customer@example.com",
    "data_types": ["profile", "orders", "activity_logs"]
  }'
```

### 2. Record Consent

```bash
curl -X POST http://localhost:9038/compliance/consent \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_123",
    "consent_type": "marketing_email",
    "status": "opted_in",
    "regions": ["gdpr", "ccpa"]
  }'
```

### 3. Create Retention Policy

```bash
curl -X POST http://localhost:9038/compliance/retention-policy \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "region": "gdpr",
    "retention_days": 365,
    "data_category": "customer_activity",
    "auto_purge_enabled": true,
    "policy_id": "pol_123",
    "tenant_id": "tenant_123"
  }'
```

### 4. Get Audit Logs (PII Access Only)

```bash
curl -X GET "http://localhost:9038/compliance/audit-log?days=30&pii_only=true" \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

### 5. Report Data Breach

```bash
curl -X POST http://localhost:9038/compliance/breach-report \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "breach_type": "unauthorized_access",
    "affected_customers": 150,
    "severity": "high",
    "description": "Unauthorized access to customer database",
    "affected_data_categories": ["email", "phone", "profile"]
  }'
```

### 6. Generate Compliance Report

```bash
curl -X GET "http://localhost:9038/compliance/reports?region=gdpr&days=90" \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

## Database Setup

PostgreSQL must be running. Service auto-creates tables on startup.

```bash
# Create database
createdb priya_compliance

# Connection test
psql -h localhost -U postgres -d priya_compliance -c "SELECT 1"
```

## API Response Examples

### DSAR Created (201)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "tenant_123",
  "customer_id": "cust_123",
  "status": "pending",
  "data_export_url": null,
  "requested_at": "2026-03-06T10:00:00",
  "completed_at": null,
  "expires_at": "2026-04-20T10:00:00",
  "retention_days": 45
}
```

### Health Check (200)

```json
{
  "status": "healthy",
  "timestamp": "2026-03-06T10:00:00",
  "database": "healthy",
  "version": "1.0.0"
}
```

### Error Response (401)

```json
{
  "detail": "Invalid token"
}
```

## Key Features at a Glance

| Feature | Endpoint | Auth |
|---------|----------|------|
| Submit DSAR | POST /dsar | JWT |
| List DSARs | GET /dsar | JWT |
| Get DSAR | GET /dsar/{id} | JWT |
| Record Consent | POST /consent | JWT |
| Get Consents | GET /consent/{id} | JWT |
| Cookie Consent | POST /cookie-consent | JWT |
| Retention Policy | POST /retention-policy | JWT |
| List Policies | GET /retention-policies | JWT |
| Audit Logs | GET /audit-log | JWT |
| Anonymize Data | POST /anonymize | JWT |
| Mask PII | POST /mask-pii | JWT |
| Report Breach | POST /breach-report | JWT |
| Create DPA | POST /dpa | JWT |
| Log Transfer | POST /cross-border-transfer | JWT |
| Reports | GET /reports | JWT |
| Health | GET /health | NO |

## Testing with Python

```python
import requests
import jwt
from datetime import datetime, timedelta

# Create JWT token
SECRET = "your-jwt-secret"
token = jwt.encode({
    "tenant_id": "tenant_123",
    "user_id": "user_456",
    "email": "user@example.com",
    "iat": datetime.utcnow(),
    "exp": datetime.utcnow() + timedelta(hours=24)
}, SECRET, algorithm="HS256")

# Test health
response = requests.get("http://localhost:9038/compliance/health")
print(response.json())

# Test DSAR
headers = {"Authorization": f"Bearer {token}"}
data = {
    "customer_id": "cust_123",
    "email": "test@example.com",
    "data_types": ["profile"]
}
response = requests.post(
    "http://localhost:9038/compliance/dsar",
    json=data,
    headers=headers
)
print(response.json())
```

## Troubleshooting

### Database Connection Error

```
ValueError: Database credentials must be provided via environment variables
```

Check that DB_HOST, DB_NAME, DB_USER, DB_PASSWORD are set.

### JWT Secret Missing

```
ValueError: JWT_SECRET environment variable must be set
```

Set JWT_SECRET before running.

### Port Already in Use

```bash
# Change port
uvicorn main:app --host 0.0.0.0 --port 9039
```

### Database Not Ready

```bash
# Check PostgreSQL
psql -h localhost -U postgres -c "SELECT 1"

# Create database if missing
createdb priya_compliance
```

## Documentation Files

- `main.py` - Full implementation (1155 lines)
- `README.md` - Complete feature documentation
- `ENDPOINTS.md` - API reference with examples
- `IMPLEMENTATION_SUMMARY.txt` - Detailed technical spec
- `QUICK_START.md` - This file

## Support & Monitoring

Check logs for:
- Token validation failures
- Database connection issues
- Audit trail completeness
- Breach report submissions

Monitor endpoints:
- `/compliance/health` - Service health
- `/compliance/audit-log` - Compliance audit trail
- `/compliance/reports` - Compliance metrics

## Regional Compliance Reminders

- **GDPR**: 30-day DSAR response, 72-hour breach notification
- **CCPA**: Consumer rights, opt-out mechanism
- **LGPD**: Data processing records, retention rules
- **POPI**: Cross-border restrictions, accountability

