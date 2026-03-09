# Appointment Booking Service

A comprehensive multi-tenant SaaS appointment booking and calendar management service for the Global AI Sales Platform.

## Features

### 1. Calendar Management
- Agent availability scheduling (working hours, breaks, holidays)
- Timezone-aware scheduling (support all IANA timezones)
- Buffer time between appointments
- Multi-agent calendar view
- Recurring availability patterns

### 2. Booking System
- Customer self-service booking
- AI-suggested appointment slots
- Booking confirmation and reminders
- Rescheduling and cancellation
- No-show tracking
- Waitlist management support

### 3. Integration Ready
- Google Calendar sync hooks (configurable per tenant)
- Outlook/Microsoft Calendar sync hooks
- Meeting link generation (Zoom/Google Meet/Teams URLs)
- Pre-appointment survey/form support

### 4. Analytics
- Booking rate by channel
- No-show rate tracking
- Average meeting duration
- Agent utilization rates
- Peak booking times

## Technology Stack

- **Framework**: FastAPI (async)
- **Database**: PostgreSQL with asyncpg
- **Authentication**: JWT (PyJWT)
- **Timezone Support**: zoneinfo
- **Deployment**: Uvicorn

## Environment Variables

Required environment variables (no hardcoded secrets):

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=priya_global
DB_USER=postgres
DB_PASSWORD=<secure-password>

# Service
PORT=9029
HOST=0.0.0.0

# Authentication
JWT_SECRET=<secure-jwt-secret>

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

## Database Schema

### appointments
```sql
CREATE TABLE appointments (
    appointment_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    customer_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    scheduled_start TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_end TIMESTAMP WITH TIME ZONE NOT NULL,
    timezone VARCHAR(63) NOT NULL,
    status VARCHAR(50) NOT NULL,
    meeting_link VARCHAR(2048),
    pre_appointment_form_url VARCHAR(2048),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reminder_sent BOOLEAN DEFAULT FALSE,
    no_show_count INTEGER DEFAULT 0,
    
    -- RLS Policy
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL)
);

CREATE INDEX idx_appointments_tenant ON appointments(tenant_id);
CREATE INDEX idx_appointments_agent_date ON appointments(agent_id, scheduled_start);
CREATE INDEX idx_appointments_customer ON appointments(customer_id);
CREATE INDEX idx_appointments_status ON appointments(status);
```

### availability_windows
```sql
CREATE TABLE availability_windows (
    availability_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    availability_type VARCHAR(50) NOT NULL,
    recurring_pattern VARCHAR(50),
    timezone VARCHAR(63) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL)
);

CREATE INDEX idx_availability_tenant_agent ON availability_windows(tenant_id, agent_id);
CREATE INDEX idx_availability_date_range ON availability_windows(start_time, end_time);
```

### reminders
```sql
CREATE TABLE reminders (
    reminder_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    appointment_id VARCHAR(255) NOT NULL,
    reminder_type VARCHAR(50) NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL,
    
    CONSTRAINT rls_tenant CHECK (tenant_id IS NOT NULL),
    FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id)
);

CREATE INDEX idx_reminders_tenant ON reminders(tenant_id);
CREATE INDEX idx_reminders_appointment ON reminders(appointment_id);
```

## API Endpoints

### Appointment Management

#### Create Appointment
```
POST /api/v1/appointments
Authorization: Bearer <token>

{
    "customer_id": "cust_123",
    "agent_id": "agent_456",
    "title": "Sales Consultation",
    "description": "Initial consultation",
    "scheduled_start": "2026-03-20T10:00:00Z",
    "scheduled_end": "2026-03-20T11:00:00Z",
    "timezone": "America/New_York",
    "meeting_link": "https://meet.google.com/abc-defg-hij",
    "notes": "Customer interested in premium plan"
}
```

#### List Appointments
```
GET /api/v1/appointments?agent_id=agent_456&status=confirmed&limit=50
Authorization: Bearer <token>
```

#### Get Appointment Detail
```
GET /api/v1/appointments/{appointment_id}
Authorization: Bearer <token>
```

#### Update Appointment
```
PUT /api/v1/appointments/{appointment_id}
Authorization: Bearer <token>

{
    "title": "Updated Title",
    "notes": "Updated notes"
}
```

#### Cancel Appointment
```
DELETE /api/v1/appointments/{appointment_id}
Authorization: Bearer <token>
```

#### Reschedule Appointment
```
POST /api/v1/appointments/{appointment_id}/reschedule
Authorization: Bearer <token>

{
    "new_start": "2026-03-21T14:00:00Z",
    "new_end": "2026-03-21T15:00:00Z",
    "reason": "Customer requested time change"
}
```

#### Confirm Appointment
```
POST /api/v1/appointments/{appointment_id}/confirm
Authorization: Bearer <token>
```

### Availability Management

#### Set Agent Availability
```
PUT /api/v1/appointments/availability
Authorization: Bearer <token>

{
    "start_time": "2026-03-20T09:00:00Z",
    "end_time": "2026-03-20T17:00:00Z",
    "availability_type": "working_hours",
    "recurring_pattern": "weekly",
    "timezone": "America/New_York"
}
```

#### Get Agent Availability
```
GET /api/v1/appointments/availability/{agent_id}
Authorization: Bearer <token>
```

#### Get Available Slots
```
GET /api/v1/appointments/available-slots?agent_id=agent_456&date=2026-03-20&duration_minutes=60&timezone=UTC
Authorization: Bearer <token>
```

### Notifications & Reminders

#### Send Reminder
```
POST /api/v1/appointments/{appointment_id}/reminder
Authorization: Bearer <token>

{
    "reminder_type": "email",
    "send_at": "2026-03-20T09:00:00Z"
}
```

### Analytics

#### Get Analytics
```
GET /api/v1/appointments/analytics?start_date=2026-03-01&end_date=2026-03-31&agent_id=agent_456
Authorization: Bearer <token>
```

Response:
```json
{
    "total_bookings": 45,
    "confirmed_bookings": 42,
    "cancelled_bookings": 2,
    "no_show_count": 1,
    "no_show_rate": 2.22,
    "avg_meeting_duration_minutes": 45.5,
    "agent_utilization_rate": 93.33,
    "peak_booking_hour": 14,
    "bookings_by_channel": {},
    "period": "2026-03-01 to 2026-03-31"
}
```

### Health Check

#### Health Status
```
GET /api/v1/appointments/health
```

## Security

### Multi-Tenant Isolation (RLS)
- Every query includes `tenant_id` check
- JWT token contains tenant_id
- Row-level security enforced at database and application level

### Authentication
- Bearer token authentication with JWT
- Token validation on every protected endpoint
- User type validation (agent, customer, admin)

### Data Protection
- All secrets from environment variables
- Parameterized SQL queries (no SQL injection)
- CORS from configurable origins
- Timezone validation

## Running the Service

### Development
```bash
pip install -r requirements.txt
export JWT_SECRET="dev-secret"
export DB_PASSWORD="dev-password"
python main.py
```

### Production
```bash
pip install -r requirements.txt
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:9029
```

## Architecture

### Database Connection Pool
- Async connection pooling with asyncpg
- Min 5, Max 20 connections
- 10-second command timeout
- Automatic connection cleanup

### Timezone Handling
- All timestamps stored in UTC
- Conversion to user timezone for display
- IANA timezone validation
- Support for all standard timezones

### Availability Logic
- Check working hours before booking
- Detect overlapping appointments
- Support recurring patterns
- 15-minute slot increments

### Analytics
- Count-based metrics
- Duration calculations
- Utilization rates
- Peak hour detection

## Testing

```bash
# Test appointment creation
curl -X POST http://localhost:9029/api/v1/appointments \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @appointment.json

# Test health check
curl http://localhost:9029/api/v1/appointments/health

# Test analytics
curl http://localhost:9029/api/v1/appointments/analytics \
  -H "Authorization: Bearer <token>"
```

## Error Handling

- 400: Bad Request (invalid timezone, invalid data)
- 401: Unauthorized (missing/invalid token)
- 403: Forbidden (insufficient permissions)
- 404: Not Found (appointment/agent not found)
- 409: Conflict (slot unavailable, overlapping appointment)
- 503: Service Unavailable (database connection issue)

## Deployment Notes

- Service runs on port 9029 by default
- Requires PostgreSQL database
- Needs JWT_SECRET for token validation
- CORS origins configurable per environment
- Connection pool auto-scales based on load
- All database operations are async/non-blocking

## Future Enhancements

- Google Calendar integration webhooks
- Outlook Calendar sync
- Zoom/Google Meet auto-link generation
- Email/SMS reminder queue
- Advanced waitlist management
- Custom timezone per tenant
- Bulk appointment operations
- Meeting recording integration
