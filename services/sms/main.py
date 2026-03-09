"""
SMS Channel Service - Priya Global Multi-Tenant AI Sales Platform

Handles inbound/outbound SMS with carrier routing.
Direct carrier partnerships: Exotel (India), Bandwidth (US/Canada), Vonage (UK/AU/EU).
Auto-routes by phone number country code. Manages templates, opt-out, DLR tracking,
and regulatory compliance (TCPA, TRAI DND, GDPR).

FastAPI service running on port 9015 with comprehensive SMS management,
template substitution, delivery reporting, and analytics.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import json
import logging
import re
import hmac
import hashlib
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import asyncpg
import httpx
import redis.asyncio as aioredis
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import mask_pii, sanitize_input, verify_webhook_signature
from shared.middleware.auth import get_auth, AuthContext, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis client for rate limiting and replay protection
redis_client: Optional[aioredis.Redis] = None

# Security constants
WEBHOOK_REPLAY_WINDOW = 300  # 5 minutes — reject replayed webhooks
WEBHOOK_RATE_LIMIT = 200  # max webhooks per minute per carrier
SEND_RATE_LIMIT_PER_MINUTE = 100  # max SMS sends per tenant per minute
MAX_ANALYTICS_RANGE_DAYS = 90  # max date range for analytics queries

# ============================================================================
# Constants & Enums
# ============================================================================

class SMSStatus(str, Enum):
    """SMS lifecycle statuses"""
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNDELIVERABLE = "undeliverable"
    REJECTED = "rejected"


class SMSDirection(str, Enum):
    """SMS direction"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CarrierType(str, Enum):
    """Carrier types"""
    EXOTEL = "exotel"          # India +91
    BANDWIDTH = "bandwidth"    # US/Canada +1
    VONAGE = "vonage"          # UK/AU/EU +44, +61, +33, +49


class ComplianceRegion(str, Enum):
    """Compliance regions"""
    INDIA = "india"            # TRAI DND
    US = "us"                  # TCPA
    EU = "eu"                  # GDPR
    UK = "uk"                  # GDPR
    AU = "au"                  # Do Not Call


PHONE_REGEX = re.compile(r"^\+\d{7,15}$")  # Require + prefix, min 7 digits
COUNTRY_CODE_MAP = {
    "+91": (CarrierType.EXOTEL, ComplianceRegion.INDIA),     # India
    "+1": (CarrierType.BANDWIDTH, ComplianceRegion.US),       # US/Canada
    "+44": (CarrierType.VONAGE, ComplianceRegion.UK),         # UK
    "+61": (CarrierType.VONAGE, ComplianceRegion.AU),         # Australia
    "+33": (CarrierType.VONAGE, ComplianceRegion.EU),         # France
    "+49": (CarrierType.VONAGE, ComplianceRegion.EU),         # Germany
}

STOP_KEYWORDS = {"STOP", "UNSUBSCRIBE", "CANCEL", "OPT-OUT"}


# ============================================================================
# Pydantic Models
# ============================================================================

class SMSWebhookPayload(BaseModel):
    """Unified webhook payload from all carriers"""
    message_id: str
    from_number: str
    to_number: str
    content: str
    status: SMSStatus
    direction: SMSDirection
    timestamp: datetime
    carrier_reference: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class SendSMSRequest(BaseModel):
    """Request to send SMS"""
    to_number: str
    content: str
    template_id: Optional[str] = None
    template_variables: Optional[Dict[str, str]] = None
    priority: str = "normal"  # normal, high, urgent
    scheduled_for: Optional[datetime] = None
    tags: Optional[List[str]] = None

    @validator("to_number")
    def validate_to_number(cls, v):
        if not PHONE_REGEX.match(v):
            raise ValueError("Invalid phone number format")
        return v

    @validator("content")
    def validate_content(cls, v):
        if len(v) > 1600:  # Max for concatenated SMS
            raise ValueError("SMS content exceeds maximum length (1600 chars)")
        return v


class SMSTemplate(BaseModel):
    """SMS template definition"""
    id: str
    tenant_id: str
    name: str
    content: str
    variables: List[str]  # List of {{var}} placeholders
    category: str  # marketing, transactional, otp
    created_at: datetime
    updated_at: datetime


class SMSMessage(BaseModel):
    """Detailed SMS message"""
    id: str
    tenant_id: str
    message_id: str
    from_number: str
    to_number: str
    content: str
    status: SMSStatus
    direction: SMSDirection
    carrier: CarrierType
    carrier_reference: Optional[str] = None
    template_id: Optional[str] = None
    dlr_status: Optional[str] = None
    dlr_timestamp: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    opt_out: bool = False
    created_at: datetime
    updated_at: datetime


class OptOutEntry(BaseModel):
    """Customer opt-out record"""
    id: str
    tenant_id: str
    phone_number: str
    reason: str
    opted_out_at: datetime


class SMSAnalytics(BaseModel):
    """SMS analytics for tenant"""
    period_start: datetime
    period_end: datetime
    total_sent: int = 0
    total_delivered: int = 0
    total_failed: int = 0
    delivery_rate: float = 0.0
    total_inbound: int = 0
    total_opt_outs: int = 0
    opt_out_rate: float = 0.0
    avg_response_time_seconds: float = 0.0
    total_cost: float = 0.0
    cost_per_sms: float = 0.0


class TemplateResponse(BaseModel):
    """Response for template operations"""
    id: str
    name: str
    content: str
    variables: List[str]


# ============================================================================
# Carrier Abstraction Layer
# ============================================================================

class CarrierAdapter(ABC):
    """Abstract base for carrier implementations"""

    @abstractmethod
    async def send_sms(
        self,
        from_number: str,
        to_number: str,
        content: str,
        webhook_url: str,
    ) -> str:
        """Send SMS, return message_id"""
        pass

    @abstractmethod
    async def check_dnd(self, phone_number: str) -> bool:
        """Check if number is on Do Not Disturb list. Return True if on DND."""
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify incoming webhook signature"""
        pass


class ExotelSMSAdapter(CarrierAdapter):
    """Exotel.com adapter for India (+91)"""

    def __init__(self):
        self.api_key = os.getenv("EXOTEL_API_KEY", "")
        self.api_secret = os.getenv("EXOTEL_API_SECRET", "")
        self.base_url = "https://api.exotel.in/v1"
        self.account_sid = os.getenv("EXOTEL_ACCOUNT_SID", "")

    async def send_sms(
        self,
        from_number: str,
        to_number: str,
        content: str,
        webhook_url: str,
    ) -> str:
        """Send SMS via Exotel API"""
        message_id = str(uuid4())
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/Accounts/{self.account_sid}/Sms/send",
                    auth=(self.account_sid, self.api_key),
                    json={
                        "From": from_number,
                        "To": to_number,
                        "Body": content,
                        "DltTemplateId": "optional_dlt_id",
                    },
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("SMSMessageData", {}).get("Sid", message_id)
            except httpx.HTTPError as e:
                logger.error("Exotel SMS send error: %s", mask_pii(str(e)))
                raise

    async def check_dnd(self, phone_number: str) -> bool:
        """Check TRAI DND registry (India)"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/Accounts/{self.account_sid}/PhoneNumbers/{phone_number}/Dnd",
                    auth=(self.account_sid, self.api_key),
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("DndStatus", "NotDnd") != "NotDnd"
                return False
            except httpx.HTTPError as e:
                logger.error("DND check error: %s", e)
                return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Exotel webhook signature (HMAC-SHA256)"""
        expected = hmac.new(
            self.api_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


class BandwidthSMSAdapter(CarrierAdapter):
    """Bandwidth.com adapter for US/Canada (+1)"""

    def __init__(self):
        self.api_key = os.getenv("BANDWIDTH_API_KEY", "")
        self.api_secret = os.getenv("BANDWIDTH_API_SECRET", "")
        self.base_url = "https://messaging.bandwidth.com/api/v2"
        self.account_id = os.getenv("BANDWIDTH_ACCOUNT_ID", "")

    async def send_sms(
        self,
        from_number: str,
        to_number: str,
        content: str,
        webhook_url: str,
    ) -> str:
        """Send SMS via Bandwidth API"""
        message_id = str(uuid4())
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/messages",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "to": [to_number],
                        "from": from_number,
                        "text": content,
                        "applicationId": os.getenv("BANDWIDTH_APPLICATION_ID", ""),
                    },
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                result = data.get("result", [{}])[0]
                return result.get("id", message_id)
            except httpx.HTTPError as e:
                logger.error("Bandwidth SMS send error: %s", mask_pii(str(e)))
                raise

    async def check_dnd(self, phone_number: str) -> bool:
        """Check TCPA DNC registry (US)"""
        # Simplified: in production, integrate with FCC DNC API
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"https://api.bandwidth.com/api/v2/accounts/{self.account_id}/phonenumbers/{phone_number}/validate",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("dncStatus") == "OnDnc"
                return False
            except httpx.HTTPError as e:
                logger.error("DNC check error: %s", e)
                return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Bandwidth webhook signature"""
        expected = hmac.new(
            self.api_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


class VonageSMSAdapter(CarrierAdapter):
    """Vonage (Nexmo) adapter for UK/AU/EU (+44, +61, +33, +49)"""

    def __init__(self):
        self.api_key = os.getenv("VONAGE_API_KEY", "")
        self.api_secret = os.getenv("VONAGE_API_SECRET", "")
        self.base_url = "https://rest.nexmo.com"
        self.brand_name = "PriyaAI"

    async def send_sms(
        self,
        from_number: str,
        to_number: str,
        content: str,
        webhook_url: str,
    ) -> str:
        """Send SMS via Vonage API"""
        message_id = str(uuid4())
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/sms/json",
                    json={
                        "api_key": self.api_key,
                        "api_secret": self.api_secret,
                        "to": to_number.lstrip("+"),
                        "from": self.brand_name,
                        "text": content,
                    },
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                messages = data.get("messages", [{}])
                if messages[0].get("status") == "0":
                    return messages[0].get("message-id", message_id)
                raise Exception(f"Vonage error: {messages[0].get('error-text')}")
            except httpx.HTTPError as e:
                logger.error("Vonage SMS send error: %s", mask_pii(str(e)))
                raise

    async def check_dnd(self, phone_number: str) -> bool:
        """Check Do Not Disturb (GDPR for EU, carrier list for UK/AU)"""
        # Simplified: implement per-region DND checking
        return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Vonage webhook signature"""
        expected = hmac.new(
            self.api_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


# ============================================================================
# FastAPI App & Routes
# ============================================================================

app = FastAPI(
    title="SMS Channel Service",
    description="Multi-tenant SMS management with carrier routing",
    version="1.0.0",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="sms")
init_sentry(service_name="sms", service_port=9015)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="sms")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Carrier instances
carriers = {
    CarrierType.EXOTEL: ExotelSMSAdapter(),
    CarrierType.BANDWIDTH: BandwidthSMSAdapter(),
    CarrierType.VONAGE: VonageSMSAdapter(),
}


# CHANNEL-ROUTING-FIX: Tenant resolution by SMS destination number
async def _resolve_tenant_by_number(to_number: str) -> str:
    """
    Resolve tenant_id from SMS destination number using channel_connections lookup.
    Used when inbound SMS webhooks don't include explicit tenant_id.
    """
    try:
        async with db.admin_connection() as conn:
            row = await conn.fetchrow(
                """SELECT tenant_id FROM channel_connections
                   WHERE channel = 'sms' AND channel_identifier = $1 AND is_active = TRUE""",
                to_number
            )
            if row:
                logger.info("Resolved tenant for SMS number %s", mask_pii(to_number))
                return row["tenant_id"]
    except Exception as e:
        logger.error("Error resolving tenant by number %s: %s", mask_pii(to_number), e)

    raise HTTPException(status_code=404, detail="No tenant found for this phone number")


@app.on_event("startup")
async def startup():
    """Initialize database and Redis on service start"""
    global redis_client
    await db.initialize()
    await event_bus.startup()

    try:
        redis_client = aioredis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            max_connections=10,
        )
        logger.info("SMS Redis connected for rate limiting")
    except Exception as e:
        logger.error("SMS Redis connection failed: %s", e)

    logger.info("SMS Service started on port 9015")


@app.on_event("shutdown")
async def shutdown():
    """Close database and Redis on service shutdown"""
    if redis_client:
        await redis_client.close()
    await event_bus.shutdown()
    await db.close()
    shutdown_tracing()


# ─── Security Helpers ───


async def _check_webhook_replay(carrier: str, payload_bytes: bytes) -> bool:
    """
    Prevent webhook replay attacks using payload hash + Redis deduplication.
    Returns True if this is a replay (duplicate), False if fresh.
    """
    if not redis_client:
        return False  # Fail open only for replay check (signature still enforced)
    try:
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()[:32]
        key = f"sms:webhook:nonce:{carrier}:{payload_hash}"
        already_seen = await redis_client.set(key, "1", nx=True, ex=WEBHOOK_REPLAY_WINDOW)
        return already_seen is None  # None means key already existed → replay
    except Exception as e:
        logger.warning("Replay check error: %s", e)
        return False


async def _check_webhook_rate_limit(carrier: str) -> bool:
    """
    Rate limit webhook requests per carrier. Returns True if allowed, False if exceeded.
    """
    if not redis_client:
        return False  # Fail closed — deny when Redis is down
    try:
        import time
        minute_key = f"sms:webhook:rl:{carrier}:{int(time.time()) // 60}"
        count = await redis_client.incr(minute_key)
        if count == 1:
            await redis_client.expire(minute_key, 120)
        return count <= WEBHOOK_RATE_LIMIT
    except Exception as e:
        logger.warning("Webhook rate limit check error: %s", e)
        return False  # Fail closed


async def _check_send_rate_limit(tenant_id: str) -> bool:
    """
    Per-tenant rate limit for outbound SMS. Returns True if allowed, False if exceeded.
    """
    if not redis_client:
        return False  # Fail closed
    try:
        import time
        minute_key = f"sms:send:rl:{tenant_id}:{int(time.time()) // 60}"
        count = await redis_client.incr(minute_key)
        if count == 1:
            await redis_client.expire(minute_key, 120)
        return count <= SEND_RATE_LIMIT_PER_MINUTE
    except Exception as e:
        logger.warning("Send rate limit check error: %s", e)
        return False  # Fail closed


VALID_DLR_STATUSES = {s.value for s in SMSStatus}


# ─── Webhook Endpoints ───


@app.post("/webhook/exotel")
async def webhook_exotel(request: Request):
    """Receive DLR/inbound SMS from Exotel"""
    # Rate limit
    if not await _check_webhook_rate_limit("exotel"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    payload = await request.body()

    # Replay protection
    if await _check_webhook_replay("exotel", payload):
        logger.warning("Exotel webhook replay detected")
        return {"status": "duplicate"}

    signature = request.headers.get("X-Exotel-Signature", "")
    adapter = carriers[CarrierType.EXOTEL]
    if not adapter.verify_webhook_signature(payload, signature):
        logger.warning("Invalid Exotel webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = await request.json()
        await _process_webhook(data, CarrierType.EXOTEL)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Exotel webhook processing error")
        raise HTTPException(status_code=400, detail="Webhook processing failed")


@app.post("/webhook/bandwidth")
async def webhook_bandwidth(request: Request):
    """Receive DLR/inbound SMS from Bandwidth"""
    if not await _check_webhook_rate_limit("bandwidth"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    payload = await request.body()

    if await _check_webhook_replay("bandwidth", payload):
        logger.warning("Bandwidth webhook replay detected")
        return {"status": "duplicate"}

    signature = request.headers.get("X-Bandwidth-Signature", "")
    adapter = carriers[CarrierType.BANDWIDTH]
    if not adapter.verify_webhook_signature(payload, signature):
        logger.warning("Invalid Bandwidth webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = await request.json()
        await _process_webhook(data, CarrierType.BANDWIDTH)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Bandwidth webhook processing error")
        raise HTTPException(status_code=400, detail="Webhook processing failed")


@app.post("/webhook/vonage")
async def webhook_vonage(request: Request):
    """Receive DLR/inbound SMS from Vonage"""
    if not await _check_webhook_rate_limit("vonage"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    payload = await request.body()

    if await _check_webhook_replay("vonage", payload):
        logger.warning("Vonage webhook replay detected")
        return {"status": "duplicate"}

    signature = request.headers.get("X-Vonage-Signature", "")
    adapter = carriers[CarrierType.VONAGE]
    if not adapter.verify_webhook_signature(payload, signature):
        logger.warning("Invalid Vonage webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = await request.json()
        await _process_webhook(data, CarrierType.VONAGE)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Vonage webhook processing error")
        raise HTTPException(status_code=400, detail="Webhook processing failed")


async def _process_webhook(data: Dict[str, Any], carrier: CarrierType):
    """Process inbound SMS or DLR from any carrier"""
    message_type = data.get("type")  # "sms" or "dlr"

    # Validate message type
    if message_type not in ("sms", "dlr"):
        logger.warning("Webhook invalid type: %s", message_type)
        return

    tenant_id = data.get("tenant_id")
    from_number = data.get("from")
    to_number = data.get("to")
    content = data.get("text", "")
    carrier_reference = data.get("carrier_reference")
    timestamp = data.get("timestamp")

    # Validate required fields for inbound SMS
    if message_type == "sms" and (not from_number or not to_number):
        logger.warning("Webhook missing required fields (from/to) for SMS")
        return

    # CHANNEL-ROUTING-FIX: Resolve tenant by phone number if not provided
    if not tenant_id and to_number:
        try:
            tenant_id = await _resolve_tenant_by_number(to_number)
            logger.info("Resolved tenant from SMS destination number: %s", mask_pii(to_number))
        except HTTPException:
            logger.error("Cannot process SMS: no tenant mapping for %s", mask_pii(to_number))
            return

    if not tenant_id:
        logger.warning("Webhook missing tenant_id and cannot resolve from phone number")
        return

    async with db.tenant_connection(tenant_id) as conn:
        if message_type == "sms":
            # Inbound SMS
            message_id = str(uuid4())
            is_opt_out = any(keyword in content.upper() for keyword in STOP_KEYWORDS)

            if is_opt_out:
                # Record opt-out
                await conn.execute(
                    """
                    INSERT INTO sms_opt_outs (id, tenant_id, phone_number, reason, opted_out_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (tenant_id, phone_number) DO UPDATE
                    SET opted_out_at = EXCLUDED.opted_out_at, reason = EXCLUDED.reason
                    """,
                    str(uuid4()), tenant_id, from_number, "Customer stop request", utc_now()
                )
                logger.info("Opt-out recorded: %s", mask_pii(from_number))

            # Store inbound SMS
            await conn.execute(
                """
                INSERT INTO sms_messages (
                    id, tenant_id, message_id, from_number, to_number, content,
                    status, direction, carrier, opt_out, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                str(uuid4()), tenant_id, message_id, from_number, to_number,
                sanitize_input(content), SMSStatus.DELIVERED, SMSDirection.INBOUND,
                carrier.value, is_opt_out, utc_now(), utc_now()
            )

            # Forward to Channel Router
            await _forward_to_channel_router(tenant_id, "sms", {
                "message_id": message_id,
                "from": from_number,
                "to": to_number,
                "content": content,
            })

        elif message_type == "dlr":
            # Delivery Receipt
            raw_status = data.get("status", "failed")
            dlr_timestamp = data.get("dlr_timestamp")

            # Validate DLR status against allowed enum values
            if raw_status not in VALID_DLR_STATUSES:
                logger.warning("Invalid DLR status rejected: %s", raw_status)
                return

            # Validate carrier_reference exists and is reasonable
            if not carrier_reference or not isinstance(carrier_reference, str) or len(carrier_reference) > 200:
                logger.warning("Invalid carrier_reference in DLR: %s", str(carrier_reference)[:50])
                return

            await conn.execute(
                """
                UPDATE sms_messages
                SET status = $1, dlr_status = $2, dlr_timestamp = $3, updated_at = $4
                WHERE carrier_reference = $5 AND tenant_id = $6
                """,
                raw_status, raw_status, dlr_timestamp, utc_now(), carrier_reference, tenant_id
            )

            logger.info("DLR updated: ref=%s → %s", carrier_reference[:20], raw_status)


async def _forward_to_channel_router(tenant_id: str, channel: str, payload: Dict[str, Any]):
    """Forward inbound message to Channel Router service"""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"http://localhost:{config.ports.channel_router}/api/v1/inbound",
                json={
                    "tenant_id": tenant_id,
                    "channel": channel,
                    "payload": payload,
                },
                timeout=10,
            )
        except httpx.HTTPError as e:
            logger.error("Failed to forward to Channel Router: %s", e)


# ─── API Endpoints ───


@app.post("/api/v1/send")
async def send_sms(
    request: SendSMSRequest,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = None,
):
    """Send SMS to recipient"""
    tenant_id = auth.tenant_id

    # Per-tenant rate limiting
    if not await _check_send_rate_limit(str(tenant_id)):
        raise HTTPException(
            status_code=429,
            detail="SMS send rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    to_number = request.to_number
    content = request.content

    # Template substitution if template_id provided
    if request.template_id:
        async with db.tenant_connection(tenant_id) as conn:
            template = await conn.fetchrow(
                "SELECT * FROM sms_templates WHERE id = $1 AND tenant_id = $2",
                request.template_id, tenant_id
            )
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")

            content = template["content"]
            if request.template_variables:
                for var, value in request.template_variables.items():
                    content = content.replace(f"{{{{{var}}}}}", sanitize_input(value))

    # Determine carrier by country code
    country_code = None
    for code, carrier_info in COUNTRY_CODE_MAP.items():
        if to_number.startswith(code):
            country_code = code
            carrier, region = carrier_info
            break

    if not country_code:
        raise HTTPException(status_code=400, detail="Unsupported destination country")

    carrier, region = COUNTRY_CODE_MAP[country_code]

    # Check compliance (DND, TCPA, GDPR, TRAI)
    adapter = carriers[carrier]
    is_on_dnd = await adapter.check_dnd(to_number)
    if is_on_dnd:
        logger.warning("SMS blocked: %s on DND list (%s)", mask_pii(to_number), region.value)
        raise HTTPException(status_code=403, detail="Number on Do Not Disturb list")

    # Check tenant opt-out list
    async with db.tenant_connection(tenant_id) as conn:
        opt_out = await conn.fetchval(
            "SELECT id FROM sms_opt_outs WHERE tenant_id = $1 AND phone_number = $2",
            tenant_id, to_number
        )
        if opt_out:
            logger.warning("SMS blocked: %s opted out", mask_pii(to_number))
            raise HTTPException(status_code=403, detail="Number has opted out")

    # Send SMS
    message_id = str(uuid4())
    try:
        carrier_reference = await adapter.send_sms(
            from_number="PriyaAI",  # Configurable per tenant
            to_number=to_number,
            content=content,
            webhook_url=f"http://localhost:{config.ports.sms}/webhook/{carrier.value}",
        )
    except Exception as e:
        logger.error("SMS send failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to send SMS")

    # Store message record
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO sms_messages (
                id, tenant_id, message_id, from_number, to_number, content,
                status, direction, carrier, carrier_reference, template_id,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            str(uuid4()), tenant_id, message_id, "PriyaAI", to_number,
            sanitize_input(content), SMSStatus.QUEUED, SMSDirection.OUTBOUND,
            carrier.value, carrier_reference, request.template_id,
            utc_now(), utc_now()
        )

    logger.info("SMS sent: %s → %s via %s", message_id, mask_pii(to_number), carrier.value)

    return {
        "message_id": message_id,
        "status": SMSStatus.QUEUED,
        "carrier": carrier.value,
        "to": to_number,
    }


@app.get("/api/v1/messages/{message_id}")
async def get_message(
    message_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get SMS message details"""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        message = await conn.fetchrow(
            "SELECT * FROM sms_messages WHERE id = $1 AND tenant_id = $2",
            message_id, tenant_id
        )

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    return SMSMessage(
        id=message["id"],
        tenant_id=message["tenant_id"],
        message_id=message["message_id"],
        from_number=message["from_number"],
        to_number=message["to_number"],
        content=message["content"],
        status=message["status"],
        direction=message["direction"],
        carrier=message["carrier"],
        carrier_reference=message.get("carrier_reference"),
        template_id=message.get("template_id"),
        dlr_status=message.get("dlr_status"),
        dlr_timestamp=message.get("dlr_timestamp"),
        error_code=message.get("error_code"),
        error_message=message.get("error_message"),
        opt_out=message.get("opt_out", False),
        created_at=message["created_at"],
        updated_at=message["updated_at"],
    ).dict()


# ─── Template Management ───


@app.post("/api/v1/templates")
async def create_template(
    name: str,
    content: str,
    auth: AuthContext = Depends(get_auth),
):
    """Create SMS template with variable placeholders"""
    tenant_id = auth.tenant_id

    # Extract variables from {{var}} placeholders
    import re
    variables = re.findall(r"\{\{(\w+)\}\}", content)

    template_id = str(uuid4())
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO sms_templates (
                id, tenant_id, name, content, variables, category, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            template_id, tenant_id, sanitize_input(name), sanitize_input(content),
            variables, "custom", utc_now(), utc_now()
        )

    logger.info("Template created: %s for tenant %s", template_id, tenant_id)

    return TemplateResponse(
        id=template_id,
        name=name,
        content=content,
        variables=variables,
    ).dict()


@app.get("/api/v1/templates")
async def list_templates(
    auth: AuthContext = Depends(get_auth),
):
    """List all SMS templates for tenant"""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        templates = await conn.fetch(
            "SELECT * FROM sms_templates WHERE tenant_id = $1 ORDER BY created_at DESC",
            tenant_id
        )

    return [
        TemplateResponse(
            id=t["id"],
            name=t["name"],
            content=t["content"],
            variables=t["variables"],
        ).dict()
        for t in templates
    ]


@app.delete("/api/v1/templates/{template_id}")
async def delete_template(
    template_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Delete SMS template"""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "DELETE FROM sms_templates WHERE id = $1 AND tenant_id = $2",
            template_id, tenant_id
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Template not found")

    logger.info("Template deleted: %s", template_id)

    return {"status": "deleted"}


# ─── Opt-Out Management ───


@app.post("/api/v1/opt-outs")
async def add_opt_out(
    phone_number: str,
    reason: str = "User request",
    auth: AuthContext = Depends(get_auth),
):
    """Add phone number to opt-out list"""
    tenant_id = auth.tenant_id

    if not PHONE_REGEX.match(phone_number):
        raise HTTPException(status_code=400, detail="Invalid phone number")

    opt_out_id = str(uuid4())
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO sms_opt_outs (
                id, tenant_id, phone_number, reason, opted_out_at
            ) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (tenant_id, phone_number) DO UPDATE
            SET reason = EXCLUDED.reason, opted_out_at = EXCLUDED.opted_out_at
            """,
            opt_out_id, tenant_id, phone_number, sanitize_input(reason), utc_now()
        )

    logger.info("Opt-out added: %s for tenant %s", mask_pii(phone_number), tenant_id)

    return {"phone_number": phone_number, "status": "opted_out"}


@app.get("/api/v1/opt-outs")
async def list_opt_outs(
    auth: AuthContext = Depends(get_auth),
):
    """List all opt-outs for tenant"""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        opt_outs = await conn.fetch(
            "SELECT * FROM sms_opt_outs WHERE tenant_id = $1 ORDER BY opted_out_at DESC",
            tenant_id
        )

    return [
        OptOutEntry(
            id=o["id"],
            tenant_id=o["tenant_id"],
            phone_number=o["phone_number"],
            reason=o["reason"],
            opted_out_at=o["opted_out_at"],
        ).dict()
        for o in opt_outs
    ]


@app.delete("/api/v1/opt-outs/{phone_number}")
async def remove_opt_out(
    phone_number: str,
    auth: AuthContext = Depends(get_auth),
):
    """Remove phone number from opt-out list"""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        result = await conn.execute(
            "DELETE FROM sms_opt_outs WHERE tenant_id = $1 AND phone_number = $2",
            tenant_id, phone_number
        )

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Opt-out entry not found")

    logger.info("Opt-out removed: %s", mask_pii(phone_number))

    return {"status": "removed"}


# ─── Analytics ───


@app.get("/api/v1/analytics")
async def get_analytics(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    auth: AuthContext = Depends(get_auth),
):
    """Get SMS analytics for tenant"""
    tenant_id = auth.tenant_id

    try:
        period_start = datetime.fromisoformat(start_date)
        period_end = datetime.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (use YYYY-MM-DD)")

    async with db.tenant_connection(tenant_id) as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status != 'failed') as total_sent,
                COUNT(*) FILTER (WHERE status = 'delivered') as total_delivered,
                COUNT(*) FILTER (WHERE status = 'failed') as total_failed,
                COUNT(*) FILTER (WHERE direction = 'inbound') as total_inbound,
                COUNT(*) FILTER (WHERE opt_out = true) as total_opt_outs,
                COALESCE(SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END), 0) as outbound_count
            FROM sms_messages
            WHERE tenant_id = $1 AND created_at >= $2 AND created_at <= $3
            """,
            tenant_id, period_start, period_end
        )

    total_sent = stats["total_sent"] or 0
    total_delivered = stats["total_delivered"] or 0
    total_failed = stats["total_failed"] or 0
    total_inbound = stats["total_inbound"] or 0
    total_opt_outs = stats["total_opt_outs"] or 0

    delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0.0
    opt_out_rate = (total_opt_outs / total_sent * 100) if total_sent > 0 else 0.0

    return SMSAnalytics(
        period_start=period_start,
        period_end=period_end,
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_failed=total_failed,
        delivery_rate=delivery_rate,
        total_inbound=total_inbound,
        total_opt_outs=total_opt_outs,
        opt_out_rate=opt_out_rate,
    ).dict()


@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "sms",
        "port": config.ports.sms,
    }


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=config.ports.sms)
