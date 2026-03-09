# Appointment Booking Service - Complete API Documentation

## Base URL
```
http://localhost:9029/api/v1
```

## Authentication
All endpoints (except health check) require Bearer token in Authorization header:
```
Authorization: Bearer <JWT_TOKEN>
```

## Response Format
All responses are JSON. Errors include status code and detail message.

---

## Appointment Endpoints

### 1. Create Appointment
**POST** `/appointments`

Create a new appointment for a customer with an agent.

#### Request
```json
{
  "customer_id": "cust_123",
  "agent_id": "agent_456",
  "title": "Product Demo",
  "description": "Demonstration of premium features",
  "scheduled_start": "2026-03-20T14:00:00Z",
  "scheduled_end": "2026-03-20T15:00:00Z",
  "timezone": "America/New_York",
  "meeting_link": "https://meet.google.com/abc-defg",
  "pre_appointment_form_url": "https://forms.example.com/demo",
  "notes": "Discussed with marketing team"
}
```

#### Response (201 Created)
```json
{
  "appointment_id": "apt_1710950400000",
  "customer_id": "cust_123",
  "agent_id": "agent_456",
  "title": "Product Demo",
  "description": "Demonstration of premium features",
  "scheduled_start": "2026-03-20T14:00:00Z",
  "scheduled_end": "2026-03-20T15:00:00Z",
  "timezone": "America/New_York",
  "status": "pending",
  "meeting_link": "https://meet.google.com/abc-defg",
  "pre_appointment_form_url": "https://forms.example.com/demo",
  "notes": "Discussed with marketing team",
  "created_at": "2026-03-06T10:00:00Z",
  "updated_at": "2026-03-06T10:00:00Z",
  "no_show_count": 0,
  "reminder_sent": false
}
```

#### Status Codes
- `201` - Appointment created successfully
- `400` - Invalid timezone or missing required fields
- `401` - Unauthorized
- `409` - Agent not available or slot already booked

---

### 2. List Appointments
**GET** `/appointments`

Retrieve list of appointments with optional filters.

#### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| agent_id | string | No | Filter by agent |
| customer_id | string | No | Filter by customer |
| status | enum | No | Filter by status (pending, confirmed, completed, cancelled, no_show) |
| start_date | string | No | ISO format datetime filter (>=) |
| end_date | string | No | ISO format datetime filter (<=) |
| limit | integer | No | Max results (default: 50, max: 100) |
| offset | integer | No | Pagination offset (default: 0) |

#### Example Request
```
GET /appointments?agent_id=agent_456&status=confirmed&limit=20&offset=0
Authorization: Bearer <token>
```

#### Response (200 OK)
```json
[
  {
    "appointment_id": "apt_1710950400000",
    "customer_id": "cust_123",
    "agent_id": "agent_456",
    "title": "Product Demo",
    "status": "confirmed",
    "scheduled_start": "2026-03-20T14:00:00Z",
    "scheduled_end": "2026-03-20T15:00:00Z",
    ...
  }
]
```

---

### 3. Get Appointment Details
**GET** `/appointments/{appointment_id}`

Retrieve detailed information about a specific appointment.

#### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| appointment_id | string | Unique appointment identifier |

#### Example Request
```
GET /appointments/apt_1710950400000
Authorization: Bearer <token>
```

#### Response (200 OK)
```json
{
  "appointment_id": "apt_1710950400000",
  "customer_id": "cust_123",
  "agent_id": "agent_456",
  "title": "Product Demo",
  "description": "Demonstration of premium features",
  "scheduled_start": "2026-03-20T14:00:00Z",
  "scheduled_end": "2026-03-20T15:00:00Z",
  "timezone": "America/New_York",
  "status": "confirmed",
  "meeting_link": "https://meet.google.com/abc-defg",
  "pre_appointment_form_url": "https://forms.example.com/demo",
  "notes": "Discussed with marketing team",
  "created_at": "2026-03-06T10:00:00Z",
  "updated_at": "2026-03-06T10:00:00Z",
  "no_show_count": 0,
  "reminder_sent": true
}
```

#### Status Codes
- `200` - Appointment found
- `401` - Unauthorized
- `404` - Appointment not found

---

### 4. Update Appointment
**PUT** `/appointments/{appointment_id}`

Update appointment details (title, notes, meeting link, etc.).

#### Request Body
```json
{
  "title": "Updated Product Demo",
  "notes": "Changed scope based on feedback",
  "meeting_link": "https://zoom.us/j/123456",
  "status": "confirmed"
}
```

#### Response (200 OK)
Returns updated appointment object.

#### Status Codes
- `200` - Appointment updated
- `400` - Invalid data
- `401` - Unauthorized
- `404` - Appointment not found

---

### 5. Cancel Appointment
**DELETE** `/appointments/{appointment_id}`

Cancel an appointment (soft delete - marks status as cancelled).

#### Example Request
```
DELETE /appointments/apt_1710950400000
Authorization: Bearer <token>
```

#### Response (204 No Content)
No response body on success.

#### Status Codes
- `204` - Appointment cancelled
- `401` - Unauthorized
- `404` - Appointment not found

---

### 6. Reschedule Appointment
**POST** `/appointments/{appointment_id}/reschedule`

Move appointment to a different time slot.

#### Request Body
```json
{
  "new_start": "2026-03-21T10:00:00Z",
  "new_end": "2026-03-21T11:00:00Z",
  "reason": "Customer requested different time"
}
```

#### Response (200 OK)
Returns updated appointment object with new times.

#### Status Codes
- `200` - Appointment rescheduled
- `401` - Unauthorized
- `404` - Appointment not found
- `409` - New slot unavailable

---

### 7. Confirm Appointment
**POST** `/appointments/{appointment_id}/confirm`

Move appointment from pending to confirmed status.

#### Example Request
```
POST /appointments/apt_1710950400000/confirm
Authorization: Bearer <token>
```

#### Response (200 OK)
Returns appointment with status updated to "confirmed".

#### Status Codes
- `200` - Appointment confirmed
- `401` - Unauthorized
- `404` - Appointment not found

---

## Availability Endpoints

### 8. Set Agent Availability
**PUT** `/appointments/availability`

Define working hours, breaks, or holidays for an agent. Only agents can set their own availability.

#### Request Body
```json
{
  "start_time": "2026-03-20T09:00:00Z",
  "end_time": "2026-03-20T17:00:00Z",
  "availability_type": "working_hours",
  "recurring_pattern": "weekly",
  "timezone": "America/New_York"
}
```

#### Availability Types
- `working_hours` - Agent is available for appointments
- `break` - Agent on break (not bookable)
- `holiday` - Agent on holiday (not bookable)
- `unavailable` - Agent not available

#### Recurring Patterns
- `null` - Single occurrence
- `daily` - Every day
- `weekly` - Every week on same day
- `monthly` - Every month on same date

#### Response (200 OK)
```json
{
  "availability_id": "avl_1710950400000",
  "agent_id": "agent_456",
  "start_time": "2026-03-20T09:00:00Z",
  "end_time": "2026-03-20T17:00:00Z",
  "availability_type": "working_hours",
  "recurring_pattern": "weekly",
  "timezone": "America/New_York"
}
```

#### Status Codes
- `200` - Availability created
- `400` - Invalid timezone
- `401` - Unauthorized
- `403` - Only agents can set availability

---

### 9. Get Agent Availability
**GET** `/appointments/availability/{agent_id}`

Retrieve all availability windows for an agent.

#### Path Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| agent_id | string | Agent identifier |

#### Example Request
```
GET /appointments/availability/agent_456
Authorization: Bearer <token>
```

#### Response (200 OK)
```json
[
  {
    "availability_id": "avl_1710950400000",
    "agent_id": "agent_456",
    "start_time": "2026-03-20T09:00:00Z",
    "end_time": "2026-03-20T17:00:00Z",
    "availability_type": "working_hours",
    "recurring_pattern": "weekly",
    "timezone": "America/New_York"
  }
]
```

---

### 10. Get Available Slots
**GET** `/appointments/available-slots`

Get available appointment slots for booking. Returns slots in 15-minute increments.

#### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| agent_id | string | No | Filter by agent (if not provided, returns all agents' slots) |
| date | string | Yes | YYYY-MM-DD format |
| timezone | string | Yes | IANA timezone for display |
| duration_minutes | integer | No | Slot duration in minutes (default: 60) |

#### Example Request
```
GET /appointments/available-slots?agent_id=agent_456&date=2026-03-20&timezone=America/New_York&duration_minutes=45
Authorization: Bearer <token>
```

#### Response (200 OK)
```json
[
  {
    "start": "2026-03-20T09:00:00Z",
    "end": "2026-03-20T09:45:00Z",
    "agent_id": "agent_456"
  },
  {
    "start": "2026-03-20T10:00:00Z",
    "end": "2026-03-20T10:45:00Z",
    "agent_id": "agent_456"
  }
]
```

#### Status Codes
- `200` - Slots available
- `400` - Invalid timezone or date format
- `401` - Unauthorized

---

## Notification Endpoints

### 11. Send Reminder
**POST** `/appointments/{appointment_id}/reminder`

Send appointment reminder to customer (email, SMS, push).

#### Request Body
```json
{
  "reminder_type": "email",
  "send_at": "2026-03-20T13:00:00Z"
}
```

#### Reminder Types
- `email` - Send email reminder
- `sms` - Send SMS reminder
- `push` - Send push notification
- `in_app` - In-app notification

#### Response (200 OK)
```json
{
  "status": "reminder_sent",
  "reminder_id": "rmr_1710950400000"
}
```

#### Status Codes
- `200` - Reminder sent
- `401` - Unauthorized
- `404` - Appointment not found

---

## Analytics Endpoints

### 12. Get Analytics
**GET** `/appointments/analytics`

Retrieve booking and performance analytics for a time period.

#### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| start_date | string | No | ISO format (e.g., 2026-03-01) |
| end_date | string | No | ISO format (e.g., 2026-03-31) |
| agent_id | string | No | Filter by specific agent |

#### Example Request
```
GET /appointments/analytics?start_date=2026-03-01&end_date=2026-03-31&agent_id=agent_456
Authorization: Bearer <token>
```

#### Response (200 OK)
```json
{
  "total_bookings": 45,
  "confirmed_bookings": 42,
  "cancelled_bookings": 2,
  "no_show_count": 1,
  "no_show_rate": 2.22,
  "avg_meeting_duration_minutes": 47.5,
  "agent_utilization_rate": 93.33,
  "peak_booking_hour": 14,
  "bookings_by_channel": {
    "web": 30,
    "phone": 12,
    "mobile": 3
  },
  "period": "2026-03-01 to 2026-03-31"
}
```

#### Metrics Explained
- **no_show_rate**: Percentage of appointments marked as no_show
- **agent_utilization_rate**: Percentage of confirmed vs total bookings
- **peak_booking_hour**: Hour of day with most bookings (0-23)
- **avg_meeting_duration_minutes**: Average time from start to end

---

## Health & Status

### 13. Health Check
**GET** `/appointments/health`

Check service and database connectivity.

#### Example Request
```
GET /appointments/health
```

#### Response (200 OK)
```json
{
  "status": "healthy",
  "timestamp": "2026-03-06T10:30:45Z",
  "service": "appointments"
}
```

#### Response (503 Service Unavailable)
```json
{
  "detail": "Service unavailable"
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid timezone"
}
```

### 401 Unauthorized
```json
{
  "detail": "Missing authorization header"
}
```

### 403 Forbidden
```json
{
  "detail": "Only agents can set availability"
}
```

### 404 Not Found
```json
{
  "detail": "Appointment not found"
}
```

### 409 Conflict
```json
{
  "detail": "Agent not available during requested time"
}
```

### 503 Service Unavailable
```json
{
  "detail": "Service unavailable"
}
```

---

## Status Values

Appointments can have the following status values:
- `pending` - Just created, not yet confirmed
- `confirmed` - Customer has confirmed the appointment
- `completed` - Appointment has occurred
- `cancelled` - Appointment was cancelled
- `no_show` - Customer did not attend
- `rescheduled` - Appointment was moved to different time

---

## Timezone Support

Service supports all IANA timezones. Examples:
- America/New_York
- America/Los_Angeles
- Europe/London
- Europe/Paris
- Asia/Tokyo
- Asia/Shanghai
- Australia/Sydney
- UTC

---

## Rate Limiting

No rate limiting enforced by default. Implement based on requirements:
- Suggested: 100 requests/minute per tenant
- Health check: 60 requests/minute

---

## Batch Operations

For efficiency with multiple operations:

### Create Multiple Appointments (Recommended Pattern)
```bash
for appointment in appointments.json; do
  curl -X POST http://localhost:9029/api/v1/appointments \
    -H "Authorization: Bearer <token>" \
    -d @appointment.json
done
```

### Update Bulk Availabilities
```bash
# Use scheduled job to update recurring patterns
```

---

## Pagination

List endpoints support pagination:
- Default limit: 50
- Max limit: 100
- Offset-based pagination

Example:
```
GET /appointments?limit=20&offset=0    # First page
GET /appointments?limit=20&offset=20   # Second page
GET /appointments?limit=20&offset=40   # Third page
```

---

## Filtering Examples

### Get All Confirmed Appointments
```
GET /appointments?status=confirmed
```

### Get Agent's Appointments for Date Range
```
GET /appointments?agent_id=agent_456&start_date=2026-03-01&end_date=2026-03-31
```

### Get Pending Customer Appointments
```
GET /appointments?customer_id=cust_123&status=pending
```

---

## Webhook Hooks (Future)

Planned webhook events:
- `appointment.created`
- `appointment.confirmed`
- `appointment.cancelled`
- `appointment.rescheduled`
- `appointment.completed`
- `appointment.no_show`

---

## Performance Tips

1. **Use specific filters** - Filter by agent/customer when possible
2. **Paginate large results** - Use limit and offset
3. **Cache timezone info** - IANA timezones don't change
4. **Batch availability updates** - Set recurring patterns instead of individual entries
5. **Index common queries** - Already configured in schema

---

Version: 1.0.0 | Last Updated: 2026-03-06
