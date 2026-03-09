# Compliance & GDPR Service - API Endpoints

## Service Information
- **Port**: 9038
- **Auth**: JWT Bearer token required (except /health)
- **RLS**: Tenant isolation on all protected endpoints
- **Base Path**: /compliance

## Endpoints Summary

### GDPR DSAR (3 endpoints)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | /dsar | 201 | Submit Data Subject Access Request |
| GET | /dsar | 200 | List DSAR requests (with filters) |
| GET | /dsar/{id} | 200 | Get DSAR details |

**Filters**: customer_id, status (pending/in_progress/completed/failed/expired)
**Pagination**: limit (1-500, default 100)

### Consent Management (3 endpoints)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | /consent | 201 | Record consent preferences |
| GET | /consent/{customer_id} | 200 | Retrieve customer consents |
| POST | /cookie-consent | 201 | Record cookie preferences |

**Regions**: GDPR, CCPA, LGPD, POPI
**Consent Statuses**: opted_in, opted_out, pending, withdrawn
**Cookie Categories**: necessary, analytics, marketing, etc.

### Data Retention (2 endpoints)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | /retention-policy | 201 | Create retention policy |
| GET | /retention-policies | 200 | List policies (with filters) |

**Filters**: region (gdpr/ccpa/lgpd/popi)
**Validation**: retention_days > 0

### Audit Logging (1 endpoint)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | /audit-log | 200 | Retrieve audit trail |

**Filters**: 
- days (1-365, default 30)
- pii_only (boolean)
- action_filter (data_access, data_modification, etc.)
**Limit**: 1-10000 (default 1000)
**Index**: tenant_id, timestamp, action

### Anonymization (2 endpoints)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | /anonymize | 202 | Initiate anonymization task |
| POST | /mask-pii | 200 | On-demand PII masking |

**Strategies**: pseudonymization, full_anonymization, data_masking
**PII Fields**: email, phone, ssn

### Breach Notification (1 endpoint)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | /breach-report | 201 | Report data breach |

**Severity**: low, medium, high, critical
**Notification Deadline**: 72 hours (GDPR)

### Data Processing Agreements (1 endpoint)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | /dpa | 201 | Create DPA template |

**Includes**: processor name, activities, data categories, retention, security

### Cross-Border Transfers (1 endpoint)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | /cross-border-transfer | 201 | Log transfer with compliance basis |

**Transfer Basis**: SCCs, BCRs, adequacy_decision
**Regions**: GDPR, CCPA, LGPD, POPI

### Compliance Reporting (1 endpoint)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | /reports | 200 | Generate compliance reports |

**Filters**: region (optional)
**Period**: days (1-730, default 90)
**Metrics**: DSAR count, deletions, consent changes, breaches, transfers, PII access

### Health Check (1 endpoint)

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | /health | 200 | Service health status |

**No Auth Required**
**Returns**: status, database health, timestamp

---

## Total Endpoints: 16

### Breakdown
- Protected (JWT required): 15
- Public: 1

## Request/Response Patterns

### JWT Bearer Token
```
Authorization: Bearer <jwt-token>
```

### Token Claims Required
```json
{
  "tenant_id": "string",
  "user_id": "string",
  "email": "string"
}
```

### Error Responses

| Code | Meaning |
|------|---------|
| 200 | OK |
| 201 | Created |
| 202 | Accepted (async) |
| 400 | Bad Request (validation) |
| 401 | Unauthorized (invalid token) |
| 404 | Not Found |
| 422 | Unprocessable Entity (Pydantic validation) |
| 500 | Server Error |

### Validation Rules

- customer_id: required, non-empty
- email: valid email format (EmailStr)
- retention_days: required, > 0
- affected_customers: >= 0
- limit: 1-10000
- days: 1-365 (audit) or 1-730 (reports)

## Audit Actions Logged

1. DATA_ACCESS - Read operations
2. DATA_MODIFICATION - Create/update operations
3. DATA_DELETION - Delete operations
4. CONSENT_CHANGE - Consent record changes
5. EXPORT_REQUEST - DSAR submissions
6. ANONYMIZATION - Anonymization tasks
7. BREACH_NOTIFICATION - Breach reports
8. RETENTION_POLICY_CHANGE - Policy updates
9. CROSS_BORDER_TRANSFER - Transfer logs

## Regional Compliance Notes

### GDPR (EU/UK)
- 45-day DSAR expiration
- 72-hour breach notification
- Data residency enforced
- Right to be forgotten support

### CCPA (California)
- Consumer opt-out tracking
- Data sales disclosure
- Retention policies

### LGPD (Brazil)
- Data processing records
- Purpose limitation
- Retention requirements

### POPI (South Africa)
- Cross-border restrictions
- Data minimization
- Processing accountability

## Performance Metrics

- **Connection Pool**: 5-20 async connections
- **Index Coverage**: All queries optimized
- **Pagination**: Prevent large result sets
- **Cache**: Retention policies static
- **Rate Limit**: Per-tenant enforcement

## Database Tables (9)

1. dsar_requests
2. consent_records
3. cookie_consents
4. retention_policies
5. audit_logs (immutable)
6. breach_notifications
7. compliance_reports
8. dpa_templates
9. cross_border_transfers

---

Generated: 2026-03-06
Service Version: 1.0.0
