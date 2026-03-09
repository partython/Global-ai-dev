"""
Appointment Booking Service - Global AI Sales Platform
Multi-tenant SaaS with async FastAPI and asyncpg
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
import logging

import asyncpg
import jwt
from fastapi import FastAPI, HTTPException, Depends, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pytz
from zoneinfo import ZoneInfo
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS & ENUMS
# ============================================================================

class AppointmentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class AvailabilityType(str, Enum):
    WORKING_HOURS = "working_hours"
    BREAK = "break"
    HOLIDAY = "holiday"
    UNAVAILABLE = "unavailable"


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class AuthContext:
    """JWT authentication context"""
    def __init__(self, tenant_id: str, user_id: str, user_type: str):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.user_type = user_type  # 'agent' or 'customer' or 'admin'


class CreateAppointmentRequest(BaseModel):
    customer_id: str
    agent_id: str
    title: str
    description: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    timezone: str = "UTC"
    meeting_link: Optional[str] = None
    pre_appointment_form_url: Optional[str] = None
    notes: Optional[str] = None


class UpdateAppointmentRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    meeting_link: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[AppointmentStatus] = None


class RescheduleRequest(BaseModel):
    new_start: datetime
    new_end: datetime
    reason: Optional[str] = None


class AppointmentResponse(BaseModel):
    appointment_id: str
    customer_id: str
    agent_id: str
    title: str
    description: Optional[str]
    scheduled_start: datetime
    scheduled_end: datetime
    timezone: str
    status: AppointmentStatus
    meeting_link: Optional[str]
    pre_appointment_form_url: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    no_show_count: int = 0
    reminder_sent: bool = False


class AvailabilityWindow(BaseModel):
    availability_id: str
    agent_id: str
    start_time: datetime
    end_time: datetime
    availability_type: AvailabilityType
    recurring_pattern: Optional[str] = None  # 'daily', 'weekly', 'monthly'
    timezone: str = "UTC"


class SetAvailabilityRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    availability_type: AvailabilityType
    recurring_pattern: Optional[str] = None
    timezone: str = "UTC"


class AvailableSlot(BaseModel):
    start: datetime
    end: datetime
    agent_id: str


class AvailableSlotsRequest(BaseModel):
    agent_id: Optional[str] = None
    date: str  # YYYY-MM-DD
    timezone: str = "UTC"
    duration_minutes: int = 60


class AnalyticsResponse(BaseModel):
    total_bookings: int
    confirmed_bookings: int
    cancelled_bookings: int
    no_show_count: int
    no_show_rate: float
    avg_meeting_duration_minutes: float
    agent_utilization_rate: float
    peak_booking_hour: Optional[int]
    bookings_by_channel: Dict[str, int]
    period: str


class ReminderRequest(BaseModel):
    reminder_type: str  # 'email', 'sms', 'push'
    send_at: Optional[datetime] = None


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    service: str = "appointments"


# ============================================================================
# DATABASE CONNECTION POOL
# ============================================================================

class DBPool:
    """Database connection pool management"""
    pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def init(cls):
        """Initialize connection pool"""
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = int(os.getenv("DB_PORT", "5432"))
        db_name = os.getenv("DB_NAME", "priya_global")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "")

        cls.pool = await asyncpg.create_pool(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            min_size=5,
            max_size=20,
            command_timeout=10,
        )
        logger.info("Database pool initialized")

    @classmethod
    async def close(cls):
        """Close connection pool"""
        if cls.pool:
            await cls.pool.close()
            logger.info("Database pool closed")

    @classmethod
    async def get_connection(cls):
        """Get connection from pool"""
        return await cls.pool.acquire()


# ============================================================================
# AUTHENTICATION
# ============================================================================

async def verify_token(authorization: Optional[str] = Header(None)) -> AuthContext:
    """Verify JWT token and return auth context"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid auth scheme")

        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise HTTPException(status_code=500, detail="Server configuration error")
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        return AuthContext(
            tenant_id=payload.get("tenant_id"),
            user_id=payload.get("user_id"),
            user_type=payload.get("user_type", "customer"),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="Appointment Booking Service",
    version="1.0.0",
    description="Multi-tenant appointment booking with calendar management",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="appointments")
init_sentry(service_name="appointments", service_port=9029)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="appointments")
app.add_middleware(TracingMiddleware)


# CORS Configuration
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)



# ============================================================================
# STARTUP & SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize database connection pool"""
    await DBPool.init()
    await event_bus.startup()


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool"""
    await DBPool.close()
    await event_bus.shutdown()
    shutdown_tracing()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def convert_timezone(dt: datetime, from_tz: str, to_tz: str) -> datetime:
    """Convert datetime between timezones"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(from_tz))
    else:
        dt = dt.astimezone(ZoneInfo(from_tz))
    return dt.astimezone(ZoneInfo(to_tz))


def validate_timezone(tz_str: str) -> bool:
    """Validate timezone string"""
    try:
        ZoneInfo(tz_str)
        return True
    except Exception:
        return False


async def check_agent_availability(
    conn: asyncpg.Connection,
    agent_id: str,
    start_time: datetime,
    end_time: datetime,
    tenant_id: str,
) -> bool:
    """Check if agent is available during time period"""
    query = """
        SELECT COUNT(*) as count FROM availability_windows
        WHERE agent_id = $1
        AND tenant_id = $2
        AND availability_type = $3
        AND start_time <= $4
        AND end_time >= $5
    """
    result = await conn.fetchval(query, agent_id, tenant_id, AvailabilityType.WORKING_HOURS, end_time, start_time)
    return result > 0


async def get_available_slots(
    conn: asyncpg.Connection,
    agent_id: str,
    date: str,
    duration_minutes: int,
    timezone: str,
    tenant_id: str,
) -> List[AvailableSlot]:
    """Get available appointment slots for an agent on a specific date"""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=ZoneInfo(timezone))
        end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=ZoneInfo(timezone))

        # Get working hours for the day
        query = """
            SELECT start_time, end_time FROM availability_windows
            WHERE agent_id = $1
            AND tenant_id = $2
            AND availability_type = $3
            AND start_time::date = $4
            ORDER BY start_time
        """
        windows = await conn.fetch(query, agent_id, tenant_id, AvailabilityType.WORKING_HOURS, target_date)

        if not windows:
            return []

        # Get booked appointments
        booked_query = """
            SELECT scheduled_start, scheduled_end FROM appointments
            WHERE agent_id = $1
            AND tenant_id = $2
            AND status != $3
            AND scheduled_start::date = $4
            ORDER BY scheduled_start
        """
        booked = await conn.fetch(booked_query, agent_id, tenant_id, AppointmentStatus.CANCELLED, target_date)

        slots = []
        for window in windows:
            current = window["start_time"]
            end = window["end_time"]

            while current + timedelta(minutes=duration_minutes) <= end:
                slot_end = current + timedelta(minutes=duration_minutes)
                is_available = True

                for booking in booked:
                    if not (slot_end <= booking["scheduled_start"] or current >= booking["scheduled_end"]):
                        is_available = False
                        break

                if is_available:
                    slots.append(AvailableSlot(start=current, end=slot_end, agent_id=agent_id))

                current += timedelta(minutes=15)  # 15-min slot increment

        return slots[:10]  # Return top 10 slots
    except Exception as e:
        logger.error("Error getting available slots: %s", e)
        return []


# ============================================================================
# APPOINTMENT ENDPOINTS
# ============================================================================

@app.post("/api/v1/appointments", response_model=AppointmentResponse)
async def create_appointment(
    request: CreateAppointmentRequest,
    auth: AuthContext = Depends(verify_token),
) -> AppointmentResponse:
    """Create a new appointment"""
    if not validate_timezone(request.timezone):
        raise HTTPException(status_code=400, detail="Invalid timezone")

    conn = await DBPool.get_connection()
    try:
        # Validate agent availability
        if not await check_agent_availability(conn, request.agent_id, request.scheduled_start, request.scheduled_end, auth.tenant_id):
            raise HTTPException(status_code=409, detail="Agent not available during requested time")

        # Check for overlapping appointments
        overlap_query = """
            SELECT COUNT(*) as count FROM appointments
            WHERE agent_id = $1
            AND tenant_id = $2
            AND status != $3
            AND scheduled_start < $4
            AND scheduled_end > $5
        """
        overlap = await conn.fetchval(overlap_query, request.agent_id, auth.tenant_id, AppointmentStatus.CANCELLED, request.scheduled_end, request.scheduled_start)
        if overlap > 0:
            raise HTTPException(status_code=409, detail="Appointment slot already booked")

        appointment_id = f"apt_{int(datetime.now().timestamp() * 1000)}"
        now = datetime.now(timezone.utc)

        insert_query = """
            INSERT INTO appointments (
                appointment_id, tenant_id, customer_id, agent_id, title,
                description, scheduled_start, scheduled_end, timezone,
                status, meeting_link, pre_appointment_form_url, notes,
                created_at, updated_at, reminder_sent, no_show_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
        """
        await conn.execute(
            insert_query,
            appointment_id, auth.tenant_id, request.customer_id, request.agent_id,
            request.title, request.description, request.scheduled_start, request.scheduled_end,
            request.timezone, AppointmentStatus.PENDING, request.meeting_link,
            request.pre_appointment_form_url, request.notes, now, now, False, 0
        )

        return AppointmentResponse(
            appointment_id=appointment_id,
            customer_id=request.customer_id,
            agent_id=request.agent_id,
            title=request.title,
            description=request.description,
            scheduled_start=request.scheduled_start,
            scheduled_end=request.scheduled_end,
            timezone=request.timezone,
            status=AppointmentStatus.PENDING,
            meeting_link=request.meeting_link,
            pre_appointment_form_url=request.pre_appointment_form_url,
            notes=request.notes,
            created_at=now,
            updated_at=now,
        )
    finally:
        await conn.close()


@app.get("/api/v1/appointments", response_model=List[AppointmentResponse])
async def list_appointments(
    agent_id: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    status: Optional[AppointmentStatus] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    auth: AuthContext = Depends(verify_token),
) -> List[AppointmentResponse]:
    """List appointments with filters"""
    conn = await DBPool.get_connection()
    try:
        query = "SELECT * FROM appointments WHERE tenant_id = $1"
        params = [auth.tenant_id]
        param_count = 1

        if agent_id:
            param_count += 1
            query += f" AND agent_id = ${param_count}"
            params.append(agent_id)

        if customer_id:
            param_count += 1
            query += f" AND customer_id = ${param_count}"
            params.append(customer_id)

        if status:
            param_count += 1
            query += f" AND status = ${param_count}"
            params.append(status)

        if start_date:
            param_count += 1
            query += f" AND scheduled_start >= ${param_count}"
            params.append(datetime.fromisoformat(start_date))

        if end_date:
            param_count += 1
            query += f" AND scheduled_end <= ${param_count}"
            params.append(datetime.fromisoformat(end_date))

        param_count += 1
        query += f" ORDER BY scheduled_start DESC LIMIT ${param_count}"
        params.append(limit)
        param_count += 1
        query += f" OFFSET ${param_count}"
        params.append(offset)
        rows = await conn.fetch(query, *params)

        return [
            AppointmentResponse(
                appointment_id=row["appointment_id"],
                customer_id=row["customer_id"],
                agent_id=row["agent_id"],
                title=row["title"],
                description=row["description"],
                scheduled_start=row["scheduled_start"],
                scheduled_end=row["scheduled_end"],
                timezone=row["timezone"],
                status=AppointmentStatus(row["status"]),
                meeting_link=row["meeting_link"],
                pre_appointment_form_url=row["pre_appointment_form_url"],
                notes=row["notes"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                no_show_count=row["no_show_count"],
                reminder_sent=row["reminder_sent"],
            )
            for row in rows
        ]
    finally:
        await conn.close()


@app.get("/api/v1/appointments/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: str,
    auth: AuthContext = Depends(verify_token),
) -> AppointmentResponse:
    """Get appointment details"""
    conn = await DBPool.get_connection()
    try:
        query = "SELECT * FROM appointments WHERE appointment_id = $1 AND tenant_id = $2"
        row = await conn.fetchrow(query, appointment_id, auth.tenant_id)

        if not row:
            raise HTTPException(status_code=404, detail="Appointment not found")

        return AppointmentResponse(
            appointment_id=row["appointment_id"],
            customer_id=row["customer_id"],
            agent_id=row["agent_id"],
            title=row["title"],
            description=row["description"],
            scheduled_start=row["scheduled_start"],
            scheduled_end=row["scheduled_end"],
            timezone=row["timezone"],
            status=AppointmentStatus(row["status"]),
            meeting_link=row["meeting_link"],
            pre_appointment_form_url=row["pre_appointment_form_url"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            no_show_count=row["no_show_count"],
            reminder_sent=row["reminder_sent"],
        )
    finally:
        await conn.close()


@app.put("/api/v1/appointments/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: str,
    request: UpdateAppointmentRequest,
    auth: AuthContext = Depends(verify_token),
) -> AppointmentResponse:
    """Update appointment"""
    conn = await DBPool.get_connection()
    try:
        query = "SELECT * FROM appointments WHERE appointment_id = $1 AND tenant_id = $2"
        appointment = await conn.fetchrow(query, appointment_id, auth.tenant_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        update_fields = []
        params = []
        param_count = 1

        # Whitelist allowed fields for update
        allowed_fields = {'title', 'description', 'scheduled_start', 'scheduled_end', 'meeting_link', 'notes', 'status'}

        for field, value in request.dict(exclude_unset=True).items():
            if field not in allowed_fields:
                continue
            param_count += 1
            update_fields.append(f"{field} = ${param_count}")
            params.append(value)

        params.append(datetime.now(timezone.utc))
        param_count += 1
        update_fields.append(f"updated_at = ${param_count}")
        params.append(appointment_id)
        params.append(auth.tenant_id)

        if update_fields:
            update_query = f"UPDATE appointments SET {', '.join(update_fields)} WHERE appointment_id = ${param_count + 1} AND tenant_id = ${param_count + 2} RETURNING *"
            updated = await conn.fetchrow(update_query, *params)

            return AppointmentResponse(
                appointment_id=updated["appointment_id"],
                customer_id=updated["customer_id"],
                agent_id=updated["agent_id"],
                title=updated["title"],
                description=updated["description"],
                scheduled_start=updated["scheduled_start"],
                scheduled_end=updated["scheduled_end"],
                timezone=updated["timezone"],
                status=AppointmentStatus(updated["status"]),
                meeting_link=updated["meeting_link"],
                pre_appointment_form_url=updated["pre_appointment_form_url"],
                notes=updated["notes"],
                created_at=updated["created_at"],
                updated_at=updated["updated_at"],
                no_show_count=updated["no_show_count"],
                reminder_sent=updated["reminder_sent"],
            )

        return AppointmentResponse(**appointment)
    finally:
        await conn.close()


@app.delete("/api/v1/appointments/{appointment_id}", status_code=204)
async def cancel_appointment(
    appointment_id: str,
    auth: AuthContext = Depends(verify_token),
):
    """Cancel appointment"""
    conn = await DBPool.get_connection()
    try:
        query = "SELECT * FROM appointments WHERE appointment_id = $1 AND tenant_id = $2"
        appointment = await conn.fetchrow(query, appointment_id, auth.tenant_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        update_query = """
            UPDATE appointments
            SET status = $1, updated_at = $2
            WHERE appointment_id = $3 AND tenant_id = $4
        """
        await conn.execute(update_query, AppointmentStatus.CANCELLED, datetime.now(timezone.utc), appointment_id, auth.tenant_id)
    finally:
        await conn.close()


@app.post("/api/v1/appointments/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: str,
    request: RescheduleRequest,
    auth: AuthContext = Depends(verify_token),
) -> AppointmentResponse:
    """Reschedule appointment"""
    conn = await DBPool.get_connection()
    try:
        query = "SELECT * FROM appointments WHERE appointment_id = $1 AND tenant_id = $2"
        appointment = await conn.fetchrow(query, appointment_id, auth.tenant_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        # Check new slot availability
        if not await check_agent_availability(conn, appointment["agent_id"], request.new_start, request.new_end, auth.tenant_id):
            raise HTTPException(status_code=409, detail="Agent not available at new time")

        update_query = """
            UPDATE appointments
            SET scheduled_start = $1, scheduled_end = $2, updated_at = $3
            WHERE appointment_id = $4 AND tenant_id = $5
            RETURNING *
        """
        updated = await conn.fetchrow(update_query, request.new_start, request.new_end, datetime.now(timezone.utc), appointment_id, auth.tenant_id)

        return AppointmentResponse(
            appointment_id=updated["appointment_id"],
            customer_id=updated["customer_id"],
            agent_id=updated["agent_id"],
            title=updated["title"],
            description=updated["description"],
            scheduled_start=updated["scheduled_start"],
            scheduled_end=updated["scheduled_end"],
            timezone=updated["timezone"],
            status=AppointmentStatus(updated["status"]),
            meeting_link=updated["meeting_link"],
            pre_appointment_form_url=updated["pre_appointment_form_url"],
            notes=updated["notes"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
            no_show_count=updated["no_show_count"],
            reminder_sent=updated["reminder_sent"],
        )
    finally:
        await conn.close()


@app.post("/api/v1/appointments/{appointment_id}/confirm", response_model=AppointmentResponse)
async def confirm_appointment(
    appointment_id: str,
    auth: AuthContext = Depends(verify_token),
) -> AppointmentResponse:
    """Confirm appointment booking"""
    conn = await DBPool.get_connection()
    try:
        query = "SELECT * FROM appointments WHERE appointment_id = $1 AND tenant_id = $2"
        appointment = await conn.fetchrow(query, appointment_id, auth.tenant_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        update_query = """
            UPDATE appointments
            SET status = $1, updated_at = $2
            WHERE appointment_id = $3 AND tenant_id = $4
            RETURNING *
        """
        updated = await conn.fetchrow(update_query, AppointmentStatus.CONFIRMED, datetime.now(timezone.utc), appointment_id, auth.tenant_id)

        return AppointmentResponse(
            appointment_id=updated["appointment_id"],
            customer_id=updated["customer_id"],
            agent_id=updated["agent_id"],
            title=updated["title"],
            description=updated["description"],
            scheduled_start=updated["scheduled_start"],
            scheduled_end=updated["scheduled_end"],
            timezone=updated["timezone"],
            status=AppointmentStatus(updated["status"]),
            meeting_link=updated["meeting_link"],
            pre_appointment_form_url=updated["pre_appointment_form_url"],
            notes=updated["notes"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
            no_show_count=updated["no_show_count"],
            reminder_sent=updated["reminder_sent"],
        )
    finally:
        await conn.close()


@app.get("/api/v1/appointments/available-slots", response_model=List[AvailableSlot])
async def get_available_slots_endpoint(
    request: AvailableSlotsRequest,
    auth: AuthContext = Depends(verify_token),
) -> List[AvailableSlot]:
    """Get available appointment slots"""
    if not validate_timezone(request.timezone):
        raise HTTPException(status_code=400, detail="Invalid timezone")

    conn = await DBPool.get_connection()
    try:
        if request.agent_id:
            return await get_available_slots(conn, request.agent_id, request.date, request.duration_minutes, request.timezone, auth.tenant_id)
        else:
            # Get all agents' available slots
            all_slots = []
            agent_query = "SELECT DISTINCT agent_id FROM appointments WHERE tenant_id = $1"
            agents = await conn.fetch(agent_query, auth.tenant_id)

            for agent in agents:
                slots = await get_available_slots(conn, agent["agent_id"], request.date, request.duration_minutes, request.timezone, auth.tenant_id)
                all_slots.extend(slots)

            return all_slots[:20]
    finally:
        await conn.close()


# ============================================================================
# AVAILABILITY ENDPOINTS
# ============================================================================

@app.put("/api/v1/appointments/availability", response_model=AvailabilityWindow)
async def set_availability(
    request: SetAvailabilityRequest,
    auth: AuthContext = Depends(verify_token),
) -> AvailabilityWindow:
    """Set agent availability window"""
    if not validate_timezone(request.timezone):
        raise HTTPException(status_code=400, detail="Invalid timezone")

    if auth.user_type != "agent":
        raise HTTPException(status_code=403, detail="Only agents can set availability")

    conn = await DBPool.get_connection()
    try:
        availability_id = f"avl_{int(datetime.now().timestamp() * 1000)}"

        insert_query = """
            INSERT INTO availability_windows (
                availability_id, tenant_id, agent_id, start_time, end_time,
                availability_type, recurring_pattern, timezone, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        await conn.execute(
            insert_query,
            availability_id, auth.tenant_id, auth.user_id, request.start_time,
            request.end_time, request.availability_type, request.recurring_pattern,
            request.timezone, datetime.now(timezone.utc)
        )

        return AvailabilityWindow(
            availability_id=availability_id,
            agent_id=auth.user_id,
            start_time=request.start_time,
            end_time=request.end_time,
            availability_type=request.availability_type,
            recurring_pattern=request.recurring_pattern,
            timezone=request.timezone,
        )
    finally:
        await conn.close()


@app.get("/api/v1/appointments/availability/{agent_id}", response_model=List[AvailabilityWindow])
async def get_agent_availability(
    agent_id: str,
    auth: AuthContext = Depends(verify_token),
) -> List[AvailabilityWindow]:
    """Get agent availability windows"""
    conn = await DBPool.get_connection()
    try:
        query = """
            SELECT * FROM availability_windows
            WHERE agent_id = $1 AND tenant_id = $2
            ORDER BY start_time DESC
            LIMIT 100
        """
        rows = await conn.fetch(query, agent_id, auth.tenant_id)

        return [
            AvailabilityWindow(
                availability_id=row["availability_id"],
                agent_id=row["agent_id"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                availability_type=AvailabilityType(row["availability_type"]),
                recurring_pattern=row["recurring_pattern"],
                timezone=row["timezone"],
            )
            for row in rows
        ]
    finally:
        await conn.close()


# ============================================================================
# REMINDER & NOTIFICATION
# ============================================================================

@app.post("/api/v1/appointments/{appointment_id}/reminder")
async def send_reminder(
    appointment_id: str,
    request: ReminderRequest,
    auth: AuthContext = Depends(verify_token),
):
    """Send appointment reminder"""
    conn = await DBPool.get_connection()
    try:
        query = "SELECT * FROM appointments WHERE appointment_id = $1 AND tenant_id = $2"
        appointment = await conn.fetchrow(query, appointment_id, auth.tenant_id)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        # Log reminder in database
        reminder_id = f"rmr_{int(datetime.now().timestamp() * 1000)}"
        insert_query = """
            INSERT INTO reminders (reminder_id, tenant_id, appointment_id, reminder_type, sent_at)
            VALUES ($1, $2, $3, $4, $5)
        """
        await conn.execute(insert_query, reminder_id, auth.tenant_id, appointment_id, request.reminder_type, datetime.now(timezone.utc))

        # Update reminder_sent flag
        update_query = "UPDATE appointments SET reminder_sent = true WHERE appointment_id = $1"
        await conn.execute(update_query, appointment_id)

        return {"status": "reminder_sent", "reminder_id": reminder_id}
    finally:
        await conn.close()


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@app.get("/api/v1/appointments/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    auth: AuthContext = Depends(verify_token),
) -> AnalyticsResponse:
    """Get booking analytics"""
    conn = await DBPool.get_connection()
    try:
        base_query = "WHERE tenant_id = $1"
        params = [auth.tenant_id]
        param_count = 1

        if start_date:
            param_count += 1
            base_query += f" AND scheduled_start >= ${param_count}"
            params.append(datetime.fromisoformat(start_date))

        if end_date:
            param_count += 1
            base_query += f" AND scheduled_end <= ${param_count}"
            params.append(datetime.fromisoformat(end_date))

        if agent_id:
            param_count += 1
            base_query += f" AND agent_id = ${param_count}"
            params.append(agent_id)

        # Total bookings
        total_query = f"SELECT COUNT(*) as count FROM appointments {base_query}"
        total = await conn.fetchval(total_query, *params)

        # Confirmed bookings
        confirmed_query = f"SELECT COUNT(*) as count FROM appointments {base_query} AND status = 'confirmed'"
        confirmed = await conn.fetchval(confirmed_query, *params)

        # Cancelled bookings
        cancelled_query = f"SELECT COUNT(*) as count FROM appointments {base_query} AND status = 'cancelled'"
        cancelled = await conn.fetchval(cancelled_query, *params)

        # No-show count
        noshow_query = f"SELECT COUNT(*) as count FROM appointments {base_query} AND status = 'no_show'"
        noshow = await conn.fetchval(noshow_query, *params)

        # Average meeting duration
        duration_query = f"""
            SELECT AVG(EXTRACT(EPOCH FROM (scheduled_end - scheduled_start))/60) as avg_duration
            FROM appointments {base_query} AND status != 'cancelled'
        """
        avg_duration = await conn.fetchval(duration_query, *params)

        # Peak booking hour
        peak_query = f"""
            SELECT EXTRACT(HOUR FROM scheduled_start) as hour, COUNT(*) as count
            FROM appointments {base_query}
            GROUP BY EXTRACT(HOUR FROM scheduled_start)
            ORDER BY count DESC LIMIT 1
        """
        peak_row = await conn.fetchrow(peak_query, *params)
        peak_hour = int(peak_row["hour"]) if peak_row else None

        return AnalyticsResponse(
            total_bookings=total or 0,
            confirmed_bookings=confirmed or 0,
            cancelled_bookings=cancelled or 0,
            no_show_count=noshow or 0,
            no_show_rate=((noshow or 0) / (total or 1)) * 100,
            avg_meeting_duration_minutes=float(avg_duration or 0),
            agent_utilization_rate=((confirmed or 0) / (total or 1)) * 100,
            peak_booking_hour=peak_hour,
            bookings_by_channel={},
            period=f"{start_date} to {end_date}" if start_date and end_date else "all_time",
        )
    finally:
        await conn.close()


# ============================================================================
# HEALTH & STATUS
# ============================================================================

@app.get("/api/v1/appointments/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint"""
    try:
        conn = await DBPool.get_connection()
        await conn.execute("SELECT 1")
        await conn.close()
        return HealthResponse(status="healthy", timestamp=datetime.now(timezone.utc))
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail="Service unavailable")


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Appointment Booking Service",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn



    port = int(os.getenv("PORT", "9029"))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
