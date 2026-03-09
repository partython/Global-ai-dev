# Compliance & GDPR Service

Multi-tenant SaaS compliance service with comprehensive GDPR, CCPA, LGPD, and POPI support.

## Overview

**Location**: `/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/compliance/main.py`
**Port**: 9038
**Lines of Code**: 1155
**Architecture**: FastAPI async with asyncpg, JWT auth, tenant RLS

## Technology Stack

- **Framework**: FastAPI (async)
- **Database**: PostgreSQL with asyncpg connection pooling
- **Authentication**: JWT (HTTPBearer) with PyJWT
- **CORS**: Configurable from environment
- **Logging**: Python logging module

## Configuration

All secrets from environment variables (NO hardcoded values):

```bash
JWT_SECRET=<your-secret-key>  # REQUIRED
DB_HOST=<postgres-host>       # REQUIRED
DB_PORT=5432                  # default
DB_NAME=<database-name>       # REQUIRED
DB_USER=<db-user>             # REQUIRED
DB_PASSWORD=<db-password>     # REQUIRED
CORS_ORIGINS=http://localhost:3000,https://app.example.com
DATA_RETENTION_DEFAULT_DAYS=2555  # ~7 years
DSAR_EXPIRATION_DAYS=45
PII_MASKING_CHARS=4
```

## Features & Endpoints

### 1. GDPR Data Subject Access Requests (DSAR)

- **POST /compliance/dsar** - Submit DSAR
  - Input: customer_id, email, data_types
  - Output: DSAR request with ID, status, expiration
  - Logs: Export request audit trail
  - Expiration: 45 days (configurable)

- **GET /compliance/dsar** - List DSAR requests
  - Filters: customer_id, status
  - Pagination: limit (max 500)
  - Returns: List with status, dates

- **GET /compliance/dsar/{id}** - Get DSAR details
  - RLS: Tenant isolation
  - Audit: Data access logging

### 2. Consent Management

- **POST /compliance/consent** - Record consent
  - Regions: GDPR, CCPA, LGPD, POPI
  - Statuses: opted_in, opted_out, pending, withdrawn
  - TCF consent string support

- **GET /compliance/consent/{customer_id}** - Retrieve consents
  - Chronological order
  - Audit logging

- **POST /compliance/cookie-consent** - Cookie banner preferences
  - Categories: necessary, analytics, marketing
  - Expiration tracking
  - Language support

### 3. Data Retention Policies

- **POST /compliance/retention-policy** - Create policy
  - Region-specific retention (GDPR, CCPA, LGPD, POPI)
  - Data categories
  - Auto-purge scheduling
  - Validation: retention_days > 0

- **GET /compliance/retention-policies** - List policies
  - Regional filtering
  - Audit trail

### 4. Audit Logging (Immutable Trail)

- **GET /compliance/audit-log** - Retrieve audit logs
  - PII access tracking (pii_access flag)
  - Action filtering
  - Time range: 1-365 days
  - Limit: up to 10,000 records
  - Indexed on: tenant_id, timestamp, action

Actions logged:
- DATA_ACCESS
- DATA_MODIFICATION
- DATA_DELETION
- CONSENT_CHANGE
- EXPORT_REQUEST
- ANONYMIZATION
- BREACH_NOTIFICATION
- RETENTION_POLICY_CHANGE
- CROSS_BORDER_TRANSFER

### 5. Anonymization & Data Masking

- **POST /compliance/anonymize** - Initiate anonymization
  - Strategies: pseudonymization, full_anonymization, data_masking
  - Async task processing (202 response)
  - PII tracking in audit

- **POST /compliance/mask-pii** - On-demand PII masking
  - Fields: email, phone, ssn
  - Masking rules configured
  - Returns masked data

### 6. Breach Notification

- **POST /compliance/breach-report** - Report data breach
  - Severity: low, medium, high, critical
  - Affected customers count
  - Data categories affected
  - GDPR 72-hour notification deadline
  - Audit logging with severity level

### 7. Data Processing Agreements (DPA)

- **POST /compliance/dpa** - Create DPA template
  - Processor info
  - Processing activities
  - Data categories
  - Retention schedule
  - Security measures
  - Tenant-specific templates

### 8. Cross-Border Transfer Logging

- **POST /compliance/cross-border-transfer** - Log transfers
  - Source/destination regions
  - Transfer basis (SCCs, BCRs, adequacy)
  - Data categories
  - Compliance audit trail
  - Regional restrictions enforced

### 9. Compliance Reporting

- **GET /compliance/reports** - Generate compliance reports
  - Metrics: DSAR count, deletions, consent changes, breaches
  - Regional breakdown
  - Period: 1-730 days
  - Compliance dashboard data

### 10. Health Check

- **GET /compliance/health** - Service health
  - Database connectivity
  - Status: healthy/degraded
  - Timestamp

## Database Schema

### Tables Created

1. **dsar_requests**
   - Indexes: tenant_customer, status
   - Tracks: ID, status, email, expiration

2. **consent_records**
   - Indexes: tenant_customer, status
   - Stores: consent type, regions, TCF string

3. **cookie_consents**
   - Categories (JSONB)
   - Expiration tracking

4. **retention_policies**
   - Indexes: tenant_region
   - Enforces region-specific rules

5. **audit_logs**
   - Indexes: tenant_timestamp, pii_access, action
   - Immutable: INSERT only
   - Fields: action, PII flag, IP, region, details (JSONB)

6. **breach_notifications**
   - Indexes: tenant_date, severity
   - Notification tracking
   - 72-hour deadline

7. **compliance_reports**
   - Indexes: tenant_region
   - Metrics aggregation

8. **dpa_templates**
   - Processor agreements
   - Security measures (JSONB)

9. **cross_border_transfers**
   - Transfer basis tracking
   - Regional compliance

## Security Features

### Authentication
- **JWT Bearer Token** with PyJWT
- Tenant ID required in token
- User ID and email context
- Token validation on every request

### Tenant Row-Level Security (RLS)
- Every query filters by tenant_id
- No cross-tenant data access
- Enforced at query level

### PII Protection
- PII access flagged in audit logs
- Email masking (4 chars configurable)
- Phone masking
- SSN masking
- On-demand anonymization

### Secrets Management
- NO hardcoded credentials
- JWT_SECRET required (raises error if missing)
- DB credentials from environment
- CORS origins configurable

### Audit Trail
- All data access logged
- Immutable append-only logs
- IP tracking
- Region tracking
- Detailed JSON metadata

## Regional Compliance

### Supported Regions
- **GDPR** (EU/UK): 45-day DSAR, 30-day breach notification
- **CCPA** (California): Consumer rights, opt-out tracking
- **LGPD** (Brazil): Data processing, retention rules
- **POPI** (South Africa): Cross-border controls

### Data Residency
- Region-specific retention policies
- Cross-border transfer logging
- Transfer basis documentation
- Compliance basis tracking

## Performance Optimization

- **Connection Pooling**: 5-20 asyncpg connections
- **Indexes**: On all frequent queries
- **Pagination**: Limit 100-10,000 records
- **Query Parameters**: Type-safe with Pydantic
- **Async/await**: Non-blocking database operations

## Error Handling

- HTTP 400: Invalid input (validation)
- HTTP 401: Token invalid/missing
- HTTP 404: Resource not found
- HTTP 422: Validation error
- HTTP 500: Database/server errors logged

## Compliance Standards

- GDPR (EU 2016/679)
- CCPA (California Consumer Privacy Act)
- LGPD (Lei Geral de Proteção de Dados)
- POPI (Protection of Personal Information Act)
- TCF (Transparency & Consent Framework)

## Example Usage

```bash
# Set environment
export JWT_SECRET="your-secret"
export DB_HOST="localhost"
export DB_NAME="compliance_db"
export DB_USER="postgres"
export DB_PASSWORD="postgres"

# Run service
python main.py

# Health check
curl -X GET http://localhost:9038/compliance/health

# Create DSAR (with JWT token)
curl -X POST http://localhost:9038/compliance/dsar \
  -H "Authorization: Bearer <jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_123",
    "email": "user@example.com",
    "data_types": ["profile", "activity", "logs"]
  }'
```

## Monitoring

- Logger configured at INFO level
- Database health checks
- Audit trail queries for compliance
- Report generation for metrics

## Future Enhancements

- Async task queue for bulk operations
- S3/blob storage for export files
- Email notification for DSAR completion
- Automated purging scheduled jobs
- GraphQL API layer
- API rate limiting per tenant
- Webhook notifications for breaches
