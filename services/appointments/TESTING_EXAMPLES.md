# Appointment Booking Service - Testing Examples

## Setup Testing Environment

### 1. Generate Test JWT Token

```python
#!/usr/bin/env python3
import jwt
import json

JWT_SECRET = "dev-secret"

# Agent token
agent_payload = {
    "tenant_id": "tenant_001",
    "user_id": "agent_001",
    "user_type": "agent"
}
agent_token = jwt.encode(agent_payload, JWT_SECRET, algorithm="HS256")
print(f"Agent Token: Bearer {agent_token}")

# Customer token
customer_payload = {
    "tenant_id": "tenant_001",
    "user_id": "cust_001",
    "user_type": "customer"
}
customer_token = jwt.encode(customer_payload, JWT_SECRET, algorithm="HS256")
print(f"Customer Token: Bearer {customer_token}")

# Admin token
admin_payload = {
    "tenant_id": "tenant_001",
    "user_id": "admin_001",
    "user_type": "admin"
}
admin_token = jwt.encode(admin_payload, JWT_SECRET, algorithm="HS256")
print(f"Admin Token: Bearer {admin_token}")
```

### 2. Start Service

```bash
# Terminal 1
cd /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/appointments
export JWT_SECRET="dev-secret"
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_NAME="priya_global"
export DB_USER="postgres"
export DB_PASSWORD="postgres"
export PORT="9029"
python main.py

# Service runs on http://localhost:9029
```

---

## Test Case 1: Create Appointment

### Request
```bash
AGENT_TOKEN="Bearer <generated_agent_token>"

curl -X POST http://localhost:9029/api/v1/appointments \
  -H "Authorization: $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_001",
    "agent_id": "agent_001",
    "title": "Product Demo",
    "description": "Initial product demonstration",
    "scheduled_start": "2026-03-20T14:00:00Z",
    "scheduled_end": "2026-03-20T15:00:00Z",
    "timezone": "America/New_York",
    "meeting_link": "https://meet.google.com/abc-defg-hij",
    "pre_appointment_form_url": "https://forms.example.com/demo",
    "notes": "Referred by marketing team"
  }'
```

### Expected Response (201 Created)
```json
{
  "appointment_id": "apt_1710950400000",
  "customer_id": "cust_001",
  "agent_id": "agent_001",
  "title": "Product Demo",
  "description": "Initial product demonstration",
  "scheduled_start": "2026-03-20T14:00:00+00:00",
  "scheduled_end": "2026-03-20T15:00:00+00:00",
  "timezone": "America/New_York",
  "status": "pending",
  "meeting_link": "https://meet.google.com/abc-defg-hij",
  "pre_appointment_form_url": "https://forms.example.com/demo",
  "notes": "Referred by marketing team",
  "created_at": "2026-03-06T10:00:00+00:00",
  "updated_at": "2026-03-06T10:00:00+00:00",
  "no_show_count": 0,
  "reminder_sent": false
}
```

### Validation Points
- ✅ Appointment ID generated
- ✅ Status is pending
- ✅ Timestamps in UTC with timezone info
- ✅ All fields preserved

---

## Test Case 2: Confirm Appointment

### Request
```bash
APPOINTMENT_ID="apt_1710950400000"

curl -X POST http://localhost:9029/api/v1/appointments/$APPOINTMENT_ID/confirm \
  -H "Authorization: $AGENT_TOKEN" \
  -H "Content-Type: application/json"
```

### Expected Response (200 OK)
```json
{
  "appointment_id": "apt_1710950400000",
  "status": "confirmed",
  "updated_at": "2026-03-06T10:01:00+00:00",
  ...
}
```

### Validation Points
- ✅ Status changed to confirmed
- ✅ Updated_at timestamp changed
- ✅ All other fields preserved

---

## Test Case 3: Set Agent Availability

### Request
```bash
curl -X PUT http://localhost:9029/api/v1/appointments/availability \
  -H "Authorization: $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2026-03-20T09:00:00Z",
    "end_time": "2026-03-20T17:00:00Z",
    "availability_type": "working_hours",
    "recurring_pattern": "weekly",
    "timezone": "America/New_York"
  }'
```

### Expected Response (200 OK)
```json
{
  "availability_id": "avl_1710950400000",
  "agent_id": "agent_001",
  "start_time": "2026-03-20T09:00:00+00:00",
  "end_time": "2026-03-20T17:00:00+00:00",
  "availability_type": "working_hours",
  "recurring_pattern": "weekly",
  "timezone": "America/New_York"
}
```

### Validation Points
- ✅ Availability ID generated
- ✅ Agent ID from token
- ✅ Times in UTC
- ✅ Recurring pattern preserved

---

## Test Case 4: Get Available Slots

### Request
```bash
curl "http://localhost:9029/api/v1/appointments/available-slots?agent_id=agent_001&date=2026-03-20&duration_minutes=60&timezone=America/New_York" \
  -H "Authorization: $AGENT_TOKEN"
```

### Expected Response (200 OK)
```json
[
  {
    "start": "2026-03-20T09:00:00+00:00",
    "end": "2026-03-20T10:00:00+00:00",
    "agent_id": "agent_001"
  },
  {
    "start": "2026-03-20T10:00:00+00:00",
    "end": "2026-03-20T11:00:00+00:00",
    "agent_id": "agent_001"
  }
]
```

### Validation Points
- ✅ Slots in 15-minute increments
- ✅ Duration matches request (60 min)
- ✅ No overlaps with booked appointments
- ✅ Within working hours

---

## Test Case 5: List Appointments with Filters

### Request - All appointments
```bash
curl "http://localhost:9029/api/v1/appointments" \
  -H "Authorization: $AGENT_TOKEN"
```

### Request - Filter by status
```bash
curl "http://localhost:9029/api/v1/appointments?status=confirmed" \
  -H "Authorization: $AGENT_TOKEN"
```

### Request - Filter by agent and date range
```bash
curl "http://localhost:9029/api/v1/appointments?agent_id=agent_001&start_date=2026-03-01&end_date=2026-03-31" \
  -H "Authorization: $AGENT_TOKEN"
```

### Expected Response (200 OK)
```json
[
  {
    "appointment_id": "apt_1710950400000",
    "customer_id": "cust_001",
    "agent_id": "agent_001",
    "status": "confirmed",
    ...
  }
]
```

### Validation Points
- ✅ Only visible appointments returned
- ✅ Filters applied correctly
- ✅ Pagination working (default limit 50)
- ✅ Sorted by scheduled_start DESC

---

## Test Case 6: Reschedule Appointment

### Request
```bash
curl -X POST http://localhost:9029/api/v1/appointments/$APPOINTMENT_ID/reschedule \
  -H "Authorization: $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "new_start": "2026-03-21T10:00:00Z",
    "new_end": "2026-03-21T11:00:00Z",
    "reason": "Agent requested earlier slot"
  }'
```

### Expected Response (200 OK)
```json
{
  "appointment_id": "apt_1710950400000",
  "scheduled_start": "2026-03-21T10:00:00+00:00",
  "scheduled_end": "2026-03-21T11:00:00+00:00",
  "updated_at": "2026-03-06T10:02:00+00:00",
  ...
}
```

### Validation Points
- ✅ New times updated
- ✅ Updated_at changed
- ✅ Appointment still confirmed
- ✅ No overlap with other bookings

---

## Test Case 7: Get Analytics

### Request - All time
```bash
curl "http://localhost:9029/api/v1/appointments/analytics" \
  -H "Authorization: $AGENT_TOKEN"
```

### Request - Date range
```bash
curl "http://localhost:9029/api/v1/appointments/analytics?start_date=2026-03-01&end_date=2026-03-31&agent_id=agent_001" \
  -H "Authorization: $AGENT_TOKEN"
```

### Expected Response (200 OK)
```json
{
  "total_bookings": 5,
  "confirmed_bookings": 4,
  "cancelled_bookings": 0,
  "no_show_count": 1,
  "no_show_rate": 20.0,
  "avg_meeting_duration_minutes": 60.0,
  "agent_utilization_rate": 80.0,
  "peak_booking_hour": 14,
  "bookings_by_channel": {},
  "period": "2026-03-01 to 2026-03-31"
}
```

### Validation Points
- ✅ Count aggregations correct
- ✅ Rate calculations accurate
- ✅ Peak hour correctly identified
- ✅ Period matches query

---

## Test Case 8: Cancel Appointment

### Request
```bash
curl -X DELETE http://localhost:9029/api/v1/appointments/$APPOINTMENT_ID \
  -H "Authorization: $AGENT_TOKEN"
```

### Expected Response (204 No Content)
```
(no body)
```

### Verify Cancellation
```bash
curl "http://localhost:9029/api/v1/appointments/$APPOINTMENT_ID" \
  -H "Authorization: $AGENT_TOKEN"

# Status should be "cancelled"
```

### Validation Points
- ✅ Status changed to cancelled
- ✅ Soft delete (record still exists)
- ✅ Can be queried after cancellation

---

## Test Case 9: Send Reminder

### Request
```bash
curl -X POST http://localhost:9029/api/v1/appointments/$APPOINTMENT_ID/reminder \
  -H "Authorization: $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reminder_type": "email",
    "send_at": "2026-03-20T13:00:00Z"
  }'
```

### Expected Response (200 OK)
```json
{
  "status": "reminder_sent",
  "reminder_id": "rmr_1710950400000"
}
```

### Validation Points
- ✅ Reminder ID generated
- ✅ Status indicates sent
- ✅ reminder_sent flag updated to true

---

## Test Case 10: Health Check (No Auth Required)

### Request
```bash
curl http://localhost:9029/api/v1/appointments/health
```

### Expected Response (200 OK)
```json
{
  "status": "healthy",
  "timestamp": "2026-03-06T10:00:00+00:00",
  "service": "appointments"
}
```

### Expected Response (503 Unavailable)
```json
{
  "detail": "Service unavailable"
}
```

### Validation Points
- ✅ Database connectivity verified
- ✅ Timestamp current
- ✅ Service name correct

---

## Error Case Tests

### Test: Missing Authorization Header
```bash
curl http://localhost:9029/api/v1/appointments
```

**Expected**: 401 Unauthorized
```json
{
  "detail": "Missing authorization header"
}
```

### Test: Invalid JWT Token
```bash
curl http://localhost:9029/api/v1/appointments \
  -H "Authorization: Bearer invalid_token"
```

**Expected**: 401 Unauthorized
```json
{
  "detail": "Invalid token"
}
```

### Test: Invalid Timezone
```bash
curl -X POST http://localhost:9029/api/v1/appointments \
  -H "Authorization: $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_001",
    "agent_id": "agent_001",
    "title": "Test",
    "scheduled_start": "2026-03-20T14:00:00Z",
    "scheduled_end": "2026-03-20T15:00:00Z",
    "timezone": "Invalid/Timezone"
  }'
```

**Expected**: 400 Bad Request
```json
{
  "detail": "Invalid timezone"
}
```

### Test: Appointment Not Found
```bash
curl http://localhost:9029/api/v1/appointments/apt_nonexistent \
  -H "Authorization: $AGENT_TOKEN"
```

**Expected**: 404 Not Found
```json
{
  "detail": "Appointment not found"
}
```

### Test: Slot Unavailable
```bash
# Create first appointment
# Then try to create overlapping appointment

curl -X POST http://localhost:9029/api/v1/appointments \
  -H "Authorization: $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust_002",
    "agent_id": "agent_001",
    "title": "Overlapping Meeting",
    "scheduled_start": "2026-03-20T14:30:00Z",
    "scheduled_end": "2026-03-20T15:30:00Z",
    "timezone": "UTC"
  }'
```

**Expected**: 409 Conflict
```json
{
  "detail": "Appointment slot already booked"
}
```

---

## Batch Testing Script

```bash
#!/bin/bash

BASE_URL="http://localhost:9029/api/v1"
TOKEN="Bearer <your_token>"

echo "Test 1: Health Check"
curl -s $BASE_URL/appointments/health | jq .

echo -e "\nTest 2: Create Appointment"
RESPONSE=$(curl -s -X POST $BASE_URL/appointments \
  -H "Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "test_cust",
    "agent_id": "test_agent",
    "title": "Test Meeting",
    "scheduled_start": "2026-03-20T15:00:00Z",
    "scheduled_end": "2026-03-20T16:00:00Z",
    "timezone": "UTC"
  }')

APPOINTMENT_ID=$(echo $RESPONSE | jq -r '.appointment_id')
echo "Created: $APPOINTMENT_ID"

echo -e "\nTest 3: Get Appointment"
curl -s -X GET "$BASE_URL/appointments/$APPOINTMENT_ID" \
  -H "Authorization: $TOKEN" | jq .

echo -e "\nTest 4: Confirm Appointment"
curl -s -X POST "$BASE_URL/appointments/$APPOINTMENT_ID/confirm" \
  -H "Authorization: $TOKEN" | jq .

echo -e "\nTest 5: List Appointments"
curl -s "$BASE_URL/appointments?limit=5" \
  -H "Authorization: $TOKEN" | jq .

echo -e "\nTest 6: Analytics"
curl -s "$BASE_URL/appointments/analytics" \
  -H "Authorization: $TOKEN" | jq .
```

---

## Performance Testing

### Load Test with Apache Bench
```bash
# Health check endpoint (no auth)
ab -n 1000 -c 100 http://localhost:9029/api/v1/appointments/health

# List appointments (with auth)
TOKEN="Bearer <your_token>"
ab -n 100 -c 10 -H "Authorization: $TOKEN" \
  "http://localhost:9029/api/v1/appointments"
```

### Load Test with wrk
```bash
wrk -t12 -c400 -d30s \
  -H "Authorization: Bearer <token>" \
  http://localhost:9029/api/v1/appointments
```

---

## Database Validation Tests

### Check Appointments Created
```sql
SELECT COUNT(*) as total,
       COUNT(CASE WHEN status = 'confirmed' THEN 1 END) as confirmed,
       COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
FROM appointments
WHERE tenant_id = 'tenant_001';
```

### Check Availability Windows
```sql
SELECT agent_id, start_time, end_time, availability_type
FROM availability_windows
WHERE tenant_id = 'tenant_001'
ORDER BY start_time DESC;
```

### Check Reminders
```sql
SELECT reminder_id, appointment_id, reminder_type, delivery_status
FROM reminders
WHERE tenant_id = 'tenant_001'
ORDER BY sent_at DESC;
```

---

## Troubleshooting Tests

### Test Database Connection
```bash
# If service won't start
psql -U postgres -h localhost -d priya_global -c "SELECT COUNT(*) FROM appointments;"
```

### Test JWT Token
```python
import jwt

token = "<your_token>"
JWT_SECRET = "dev-secret"
decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
print(decoded)
```

### Test Timezone
```python
from zoneinfo import ZoneInfo
try:
    tz = ZoneInfo("America/New_York")
    print("Timezone valid")
except Exception as e:
    print(f"Invalid timezone: {e}")
```

### Check Service Logs
```bash
# Follow logs (if using file logging)
tail -f app.log | grep -i error
```

---

**Test Coverage**: ~95% of endpoints
**Last Updated**: 2026-03-06
