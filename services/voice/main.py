"""
Voice Channel Service - Priya Global Multi-Tenant AI Sales Platform

Handles inbound/outbound voice calls with AI-powered conversations.
Direct carrier partnerships: Exotel (India), Bandwidth (US/Canada), Vonage (UK/AU/EU).
Auto-routes by phone number country code. Speech-to-text + AI Engine + Text-to-speech.

FastAPI service running on port 9012 with comprehensive call management,
IVR routing, recording, transcription, and analytics.
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

# ============================================================================
# Constants & Enums
# ============================================================================

class CallState(str, Enum):
    """Call lifecycle states"""
    RINGING = "ringing"
    ANSWERED = "answered"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"


class CallDirection(str, Enum):
    """Call direction"""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CarrierType(str, Enum):
    """Carrier types"""
    EXOTEL = "exotel"      # India +91
    BANDWIDTH = "bandwidth"  # US/Canada +1
    VONAGE = "vonage"      # UK/AU/EU +44, +61


class DTMFKey(str, Enum):
    """DTMF (keypad) tones"""
    KEY_0 = "0"
    KEY_1 = "1"
    KEY_2 = "2"
    KEY_3 = "3"
    KEY_4 = "4"
    KEY_5 = "5"
    KEY_6 = "6"
    KEY_7 = "7"
    KEY_8 = "8"
    KEY_9 = "9"
    STAR = "*"
    HASH = "#"


PHONE_REGEX = re.compile(r"^\+?\d{1,15}$")
COUNTRY_CODE_MAP = {
    "+91": CarrierType.EXOTEL,      # India
    "+1": CarrierType.BANDWIDTH,    # US/Canada
    "+44": CarrierType.VONAGE,      # UK
    "+61": CarrierType.VONAGE,      # Australia
    "+33": CarrierType.VONAGE,      # France
    "+49": CarrierType.VONAGE,      # Germany
}

# ============================================================================
# Pydantic Models
# ============================================================================

class CallWebhookPayload(BaseModel):
    """Unified webhook payload from all carriers"""
    call_id: str
    from_number: str
    to_number: str
    state: CallState
    direction: CallDirection
    timestamp: datetime
    duration_seconds: Optional[int] = None
    recording_url: Optional[str] = None
    dtmf_key: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class InitiateCallRequest(BaseModel):
    """Request to initiate outbound call"""
    to_number: str
    from_number: Optional[str] = None
    ai_prompt: str  # Initial prompt for AI agent
    ivr_menu: Optional[Dict[str, str]] = None  # DTMF routing: "1" -> "sales"
    record: bool = True
    scheduled_for: Optional[datetime] = None
    priority: str = "normal"  # normal, high, urgent

    @validator("to_number")
    def validate_to_number(cls, v):
        if not PHONE_REGEX.match(v):
            raise ValueError("Invalid phone number format")
        return v


class CallDetail(BaseModel):
    """Detailed call information"""
    id: str
    tenant_id: str
    call_id: str
    from_number: str
    to_number: str
    state: CallState
    direction: CallDirection
    carrier: CarrierType
    duration_seconds: Optional[int] = None
    recording_s3_key: Optional[str] = None
    transcription: Optional[str] = None
    ai_agent_prompt: Optional[str] = None
    conversation_messages: int = 0
    started_at: datetime
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class TransferCallRequest(BaseModel):
    """Request to transfer call to agent or number"""
    target: str  # Phone number or agent email
    reason: Optional[str] = None


class HoldCallRequest(BaseModel):
    """Request to hold/unhold call"""
    hold: bool  # true = hold, false = unhold


class CallAnalytics(BaseModel):
    """Call analytics for tenant"""
    period_start: datetime
    period_end: datetime
    total_calls: int = 0
    total_inbound: int = 0
    total_outbound: int = 0
    total_completed: int = 0
    total_failed: int = 0
    avg_duration_seconds: float = 0.0
    total_wait_time_seconds: int = 0
    avg_wait_time_seconds: float = 0.0
    resolution_rate: float = 0.0
    transcription_count: int = 0
    total_cost: float = 0.0
    cost_per_call: float = 0.0


# ============================================================================
# Carrier Abstraction Layer
# ============================================================================

class CarrierAdapter(ABC):
    """Abstract base for carrier implementations"""

    @abstractmethod
    async def initiate_call(
        self,
        from_number: str,
        to_number: str,
        webhook_url: str,
    ) -> str:
        """Initiate outbound call, return call_id"""
        pass

    @abstractmethod
    async def end_call(self, call_id: str) -> bool:
        """Terminate call"""
        pass

    @abstractmethod
    async def transfer_call(self, call_id: str, target_number: str) -> bool:
        """Transfer call to another number"""
        pass

    @abstractmethod
    async def play_audio(self, call_id: str, audio_url: str) -> bool:
        """Play audio during call (IVR menu, TTS response)"""
        pass

    @abstractmethod
    async def record_call(self, call_id: str, enabled: bool = True) -> bool:
        """Enable/disable call recording"""
        pass

    @abstractmethod
    async def send_dtmf(self, call_id: str, digits: str) -> bool:
        """Send DTMF tones"""
        pass

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify incoming webhook signature"""
        pass


class ExotelAdapter(CarrierAdapter):
    """Exotel.com adapter for India (+91)"""

    def __init__(self):
        # CRITICAL FIX: Load from environment variables, not hardcoded placeholders
        self.api_key = os.getenv("EXOTEL_API_KEY", "")
        self.api_secret = os.getenv("EXOTEL_API_SECRET", "")
        if not self.api_key or not self.api_secret:
            logger.warning("Exotel credentials not configured (EXOTEL_API_KEY, EXOTEL_API_SECRET)")
        self.base_url = "https://api.exotel.in/v1"
        self.account_sid = os.getenv("EXOTEL_ACCOUNT_SID", "")

    async def initiate_call(self, from_number: str, to_number: str, webhook_url: str) -> str:
        """Initiate outbound call via Exotel API"""
        call_id = str(uuid4())
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/Accounts/{self.account_sid}/Calls/connect",
                    json={
                        "From": from_number,
                        "To": to_number,
                        "CallerId": from_number,
                        "StatusCallback": webhook_url,
                    },
                    auth=(self.api_key, self.api_secret),
                    timeout=10.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("Call", {}).get("Sid", call_id)
            except Exception as e:
                logger.error("Exotel initiate_call failed: %s", e)
        return call_id

    async def end_call(self, call_id: str) -> bool:
        """Terminate call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/Accounts/{self.account_sid}/Calls/{call_id}",
                    json={"Status": "completed"},
                    auth=(self.api_key, self.api_secret),
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Exotel end_call failed: %s", e)
        return False

    async def transfer_call(self, call_id: str, target_number: str) -> bool:
        """Transfer call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/Accounts/{self.account_sid}/Calls/{call_id}/transfer",
                    json={"TransferTo": target_number},
                    auth=(self.api_key, self.api_secret),
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Exotel transfer_call failed: %s", e)
        return False

    async def play_audio(self, call_id: str, audio_url: str) -> bool:
        """Play audio during call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/Accounts/{self.account_sid}/Calls/{call_id}/play",
                    json={"AudioUrl": audio_url},
                    auth=(self.api_key, self.api_secret),
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Exotel play_audio failed: %s", e)
        return False

    async def record_call(self, call_id: str, enabled: bool = True) -> bool:
        """Enable/disable recording"""
        return True  # Exotel records by default

    async def send_dtmf(self, call_id: str, digits: str) -> bool:
        """Send DTMF tones"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/Accounts/{self.account_sid}/Calls/{call_id}/dtmf",
                    json={"Digits": digits},
                    auth=(self.api_key, self.api_secret),
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Exotel send_dtmf failed: %s", e)
        return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Exotel webhook signature (SHA1 HMAC)"""
        expected = hmac.new(
            self.api_secret.encode(),
            payload,
            hashlib.sha1,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


class BandwidthAdapter(CarrierAdapter):
    """Bandwidth.com adapter for US/Canada (+1)"""

    def __init__(self):
        # CRITICAL FIX: Load from environment variables, not hardcoded placeholders
        self.api_key = os.getenv("BANDWIDTH_API_KEY", "")
        self.api_secret = os.getenv("BANDWIDTH_API_SECRET", "")
        if not self.api_key or not self.api_secret:
            logger.warning("Bandwidth credentials not configured (BANDWIDTH_API_KEY, BANDWIDTH_API_SECRET)")
        self.base_url = "https://api.bandwidth.com/v1"
        self.account_id = os.getenv("BANDWIDTH_ACCOUNT_ID", "")

    async def initiate_call(self, from_number: str, to_number: str, webhook_url: str) -> str:
        """Initiate outbound call via Bandwidth API"""
        call_id = str(uuid4())
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/calls",
                    json={
                        "from": from_number,
                        "to": to_number,
                        "answerUrl": webhook_url,
                        "answerMethod": "POST",
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                if response.status_code == 201:
                    return response.json().get("id", call_id)
            except Exception as e:
                logger.error("Bandwidth initiate_call failed: %s", e)
        return call_id

    async def end_call(self, call_id: str) -> bool:
        """Terminate call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/calls/{call_id}",
                    json={"state": "completed"},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Bandwidth end_call failed: %s", e)
        return False

    async def transfer_call(self, call_id: str, target_number: str) -> bool:
        """Transfer call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/calls/{call_id}/transfer",
                    json={"transferTo": target_number},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Bandwidth transfer_call failed: %s", e)
        return False

    async def play_audio(self, call_id: str, audio_url: str) -> bool:
        """Play audio during call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/calls/{call_id}/bridge",
                    json={"callbackUrl": audio_url},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Bandwidth play_audio failed: %s", e)
        return False

    async def record_call(self, call_id: str, enabled: bool = True) -> bool:
        """Enable/disable recording"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/calls/{call_id}/recording",
                    json={"state": "recording" if enabled else "paused"},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Bandwidth record_call failed: %s", e)
        return False

    async def send_dtmf(self, call_id: str, digits: str) -> bool:
        """Send DTMF tones"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/accounts/{self.account_id}/calls/{call_id}/dtmf",
                    json={"dtmfOut": digits},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                return response.status_code == 200
            except Exception as e:
                logger.error("Bandwidth send_dtmf failed: %s", e)
        return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Bandwidth webhook signature (SHA256 HMAC)"""
        return verify_webhook_signature(payload, signature, self.api_secret)


class VonageAdapter(CarrierAdapter):
    """Vonage (Nexmo) adapter for UK/AU/EU (+44, +61, +33, +49)"""

    def __init__(self):
        # CRITICAL FIX: Load from environment variables, not hardcoded placeholders
        self.api_key = os.getenv("VONAGE_API_KEY", "")
        self.api_secret = os.getenv("VONAGE_API_SECRET", "")
        if not self.api_key or not self.api_secret:
            logger.warning("Vonage credentials not configured (VONAGE_API_KEY, VONAGE_API_SECRET)")
        self.base_url = "https://api.vonage.com/v1/calls"

    async def initiate_call(self, from_number: str, to_number: str, webhook_url: str) -> str:
        """Initiate outbound call via Vonage API"""
        call_id = str(uuid4())
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    json={
                        "to": [{"type": "phone", "number": to_number}],
                        "from": {"type": "phone", "number": from_number},
                        "ncco": [{"action": "connect", "eventUrl": [webhook_url]}],
                    },
                    params={"api_key": self.api_key, "api_secret": self.api_secret},
                    timeout=10.0,
                )
                if response.status_code == 201:
                    return response.json().get("uuid", call_id)
            except Exception as e:
                logger.error("Vonage initiate_call failed: %s", e)
        return call_id

    async def end_call(self, call_id: str) -> bool:
        """Terminate call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.base_url}/{call_id}",
                    json={"action": "hangup"},
                    params={"api_key": self.api_key, "api_secret": self.api_secret},
                    timeout=10.0,
                )
                return response.status_code == 204
            except Exception as e:
                logger.error("Vonage end_call failed: %s", e)
        return False

    async def transfer_call(self, call_id: str, target_number: str) -> bool:
        """Transfer call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.base_url}/{call_id}",
                    json={"action": "transfer", "destination": {"type": "phone", "number": target_number}},
                    params={"api_key": self.api_key, "api_secret": self.api_secret},
                    timeout=10.0,
                )
                return response.status_code == 204
            except Exception as e:
                logger.error("Vonage transfer_call failed: %s", e)
        return False

    async def play_audio(self, call_id: str, audio_url: str) -> bool:
        """Play audio during call"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.base_url}/{call_id}",
                    json={"ncco": [{"action": "talk", "text": "Playing audio"}]},
                    params={"api_key": self.api_key, "api_secret": self.api_secret},
                    timeout=10.0,
                )
                return response.status_code == 204
            except Exception as e:
                logger.error("Vonage play_audio failed: %s", e)
        return False

    async def record_call(self, call_id: str, enabled: bool = True) -> bool:
        """Enable/disable recording"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.base_url}/{call_id}",
                    json={"ncco": [{"action": "record"}] if enabled else []},
                    params={"api_key": self.api_key, "api_secret": self.api_secret},
                    timeout=10.0,
                )
                return response.status_code == 204
            except Exception as e:
                logger.error("Vonage record_call failed: %s", e)
        return False

    async def send_dtmf(self, call_id: str, digits: str) -> bool:
        """Send DTMF tones"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.base_url}/{call_id}",
                    json={"ncco": [{"action": "input", "dtmf": {"maxDigits": len(digits)}}]},
                    params={"api_key": self.api_key, "api_secret": self.api_secret},
                    timeout=10.0,
                )
                return response.status_code == 204
            except Exception as e:
                logger.error("Vonage send_dtmf failed: %s", e)
        return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Vonage webhook signature"""
        return verify_webhook_signature(payload, signature, self.api_secret)


# ============================================================================
# Carrier Router
# ============================================================================

class CarrierRouter:
    """Routes calls to appropriate carrier based on destination country code"""

    def __init__(self):
        self.adapters = {
            CarrierType.EXOTEL: ExotelAdapter(),
            CarrierType.BANDWIDTH: BandwidthAdapter(),
            CarrierType.VONAGE: VonageAdapter(),
        }

    def get_carrier_for_number(self, phone_number: str) -> CarrierType:
        """Determine carrier by country code"""
        phone_number = phone_number.replace(" ", "").replace("-", "")
        if not phone_number.startswith("+"):
            phone_number = "+" + phone_number

        for prefix, carrier in COUNTRY_CODE_MAP.items():
            if phone_number.startswith(prefix):
                return carrier

        # Default to Vonage for unknown regions
        logger.warning("Unknown phone prefix for %s, defaulting to Vonage", phone_number)
        return CarrierType.VONAGE

    def get_adapter(self, carrier: CarrierType) -> CarrierAdapter:
        """Get adapter instance for carrier"""
        return self.adapters.get(carrier, self.adapters[CarrierType.VONAGE])


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Priya Global Voice Service",
    description="AI-powered voice calls with direct carrier partnerships",
    version="1.0.0",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="voice")
init_sentry(service_name="voice", service_port=9012)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="voice")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


carrier_router = CarrierRouter()


# CHANNEL-ROUTING-FIX: Tenant voice number lookup function
async def _get_tenant_voice_number(tenant_id: str) -> str:
    """
    Lookup tenant's configured voice number from channel_connections table.
    Falls back to default if not configured.
    """
    try:
        async with db.admin_connection() as conn:
            row = await conn.fetchrow(
                """SELECT channel_identifier FROM channel_connections
                   WHERE tenant_id = $1 AND channel = 'voice' AND is_active = TRUE LIMIT 1""",
                tenant_id
            )
            if row and row["channel_identifier"]:
                logger.info("Found configured voice number for tenant %s", tenant_id)
                return row["channel_identifier"]
    except Exception as e:
        logger.warning("Error looking up voice number for tenant %s: %s", tenant_id, e)

    # Fallback: raise error to prevent incorrect routing
    raise HTTPException(status_code=400, detail="No voice number configured for this tenant")


@app.on_event("startup")
async def startup():
    """Initialize database connection pool"""
    await db.initialize()
    await event_bus.startup()
    logger.info("Voice Service started on port %d", config.ports.voice)


@app.on_event("shutdown")
async def shutdown():
    """Close database connections"""
    await db.close()
    shutdown_tracing()


# ============================================================================
# Webhook Endpoints (Carrier Callbacks)
# ============================================================================

@app.post("/webhook/exotel")
async def webhook_exotel(request: Request, background_tasks: BackgroundTasks):
    """Handle Exotel call webhooks"""
    body = await request.body()
    signature = request.headers.get("X-Exotel-Signature", "")

    adapter = carrier_router.get_adapter(CarrierType.EXOTEL)
    if not adapter.verify_webhook_signature(body, signature):
        logger.warning("Invalid Exotel webhook signature")
        return JSONResponse({"error": "Invalid signature"}, status_code=401)

    try:
        data = await request.json()
        call_id = data.get("CallSid", "")
        state_str = data.get("CallStatus", "").lower()
        from_number = mask_pii(data.get("From", ""))
        to_number = mask_pii(data.get("To", ""))

        state_map = {
            "ringing": CallState.RINGING,
            "answered": CallState.ANSWERED,
            "completed": CallState.COMPLETED,
            "failed": CallState.FAILED,
        }
        state = state_map.get(state_str, CallState.FAILED)

        logger.info("Exotel webhook: call_id=%s, state=%s", call_id, state)
        background_tasks.add_task(
            process_call_webhook,
            call_id=call_id,
            from_number=data.get("From", ""),
            to_number=data.get("To", ""),
            state=state,
            carrier=CarrierType.EXOTEL,
        )

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error("Exotel webhook error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/webhook/bandwidth")
async def webhook_bandwidth(request: Request, background_tasks: BackgroundTasks):
    """Handle Bandwidth call webhooks"""
    body = await request.body()
    signature = request.headers.get("X-Bandwidth-Signature", "")

    adapter = carrier_router.get_adapter(CarrierType.BANDWIDTH)
    if not adapter.verify_webhook_signature(body, signature):
        logger.warning("Invalid Bandwidth webhook signature")
        return JSONResponse({"error": "Invalid signature"}, status_code=401)

    try:
        data = await request.json()
        call_id = data.get("callId", "")
        state = CallState(data.get("callState", "failed").lower())
        from_number = data.get("from", "")
        to_number = data.get("to", "")

        logger.info("Bandwidth webhook: call_id=%s, state=%s", call_id, state)
        background_tasks.add_task(
            process_call_webhook,
            call_id=call_id,
            from_number=from_number,
            to_number=to_number,
            state=state,
            carrier=CarrierType.BANDWIDTH,
        )

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error("Bandwidth webhook error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/webhook/vonage")
async def webhook_vonage(request: Request, background_tasks: BackgroundTasks):
    """Handle Vonage call webhooks"""
    body = await request.body()
    signature = request.headers.get("X-Vonage-Signature", "")

    adapter = carrier_router.get_adapter(CarrierType.VONAGE)
    if not adapter.verify_webhook_signature(body, signature):
        logger.warning("Invalid Vonage webhook signature")
        return JSONResponse({"error": "Invalid signature"}, status_code=401)

    try:
        data = await request.json()
        call_id = data.get("uuid", "")
        state_str = data.get("status", "failed").lower()
        from_number = data.get("from", "")
        to_number = data.get("to", "")

        state_map = {
            "started": CallState.RINGING,
            "ringing": CallState.RINGING,
            "answered": CallState.ANSWERED,
            "completed": CallState.COMPLETED,
            "failed": CallState.FAILED,
        }
        state = state_map.get(state_str, CallState.FAILED)

        logger.info("Vonage webhook: call_id=%s, state=%s", call_id, state)
        background_tasks.add_task(
            process_call_webhook,
            call_id=call_id,
            from_number=from_number,
            to_number=to_number,
            state=state,
            carrier=CarrierType.VONAGE,
        )

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error("Vonage webhook error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=400)


# ============================================================================
# Background Task: Process Webhook
# ============================================================================

async def process_call_webhook(
    call_id: str,
    from_number: str,
    to_number: str,
    state: CallState,
    carrier: CarrierType,
):
    """Process incoming call webhook and update database"""
    try:
        # Lookup call in database
        query = """
            SELECT id, tenant_id, state, started_at FROM voice_calls
            WHERE call_id = $1
            LIMIT 1
        """

        async with db.admin_connection() as conn:
            call_record = await conn.fetchrow(query, call_id)

            if not call_record:
                logger.warning("Call record not found for call_id=%s", call_id)
                return

            tenant_id = call_record["tenant_id"]
            old_state = call_record["state"]

            # Update call state
            update_query = """
                UPDATE voice_calls
                SET state = $1, updated_at = NOW()
                WHERE id = $2 AND tenant_id = $3
            """
            await conn.execute(update_query, state.value, call_record["id"], tenant_id)

            logger.info("Updated call %s: %s -> %s (tenant=%s)", call_id, old_state, state, tenant_id)

    except Exception as e:
        logger.error("Error processing call webhook: %s", e)


# ============================================================================
# API Endpoints: Call Management
# ============================================================================

@app.post("/api/v1/calls/initiate")
async def initiate_call(
    request: InitiateCallRequest,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = None,
):
    """Initiate an outbound AI-powered call"""
    auth.require_permission("calls.create")

    try:
        call_id = str(uuid4())
        tenant_id = auth.tenant_id
        carrier = carrier_router.get_carrier_for_number(request.to_number)
        adapter = carrier_router.get_adapter(carrier)

        # CHANNEL-ROUTING-FIX: Lookup tenant's configured voice number instead of hardcoding
        if request.from_number:
            from_number = request.from_number
        else:
            from_number = await _get_tenant_voice_number(tenant_id)
        to_number = request.to_number

        # Insert call into database
        query = """
            INSERT INTO voice_calls (
                id, tenant_id, call_id, from_number, to_number, state,
                direction, carrier, ai_agent_prompt, started_at, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW(), NOW())
            RETURNING id
        """

        async with db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                query,
                generate_uuid(),
                tenant_id,
                call_id,
                from_number,
                to_number,
                CallState.RINGING.value,
                CallDirection.OUTBOUND.value,
                carrier.value,
                request.ai_prompt,
            )

        # Webhook URL for carrier to POST status updates
        webhook_url = f"https://voice-api.priyaai.com/webhook/{carrier.value}"

        # Initiate call with carrier
        actual_call_id = await adapter.initiate_call(from_number, to_number, webhook_url)
        logger.info("Initiated %s call: %s", carrier.value, actual_call_id)

        return JSONResponse({
            "call_id": call_id,
            "carrier_call_id": actual_call_id,
            "status": "initiated",
            "to_number": mask_pii(to_number),
        })

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error initiating call: %s", e)
        raise HTTPException(status_code=400, detail="Failed to initiate call")


@app.get("/api/v1/calls")
async def list_calls(
    auth: AuthContext = Depends(get_auth),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List calls for authenticated tenant"""
    auth.require_permission("calls.read")

    query = """
        SELECT id, call_id, from_number, to_number, state, direction,
               carrier, duration_seconds, started_at, ended_at, created_at
        FROM voice_calls
        WHERE tenant_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
    """

    async with db.tenant_connection(auth.tenant_id) as conn:
        rows = await conn.fetch(query, auth.tenant_id, limit, offset)

    calls = [dict(row) for row in rows]
    return JSONResponse({"calls": calls, "count": len(calls)})


@app.get("/api/v1/calls/{call_id}")
async def get_call_detail(
    call_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get detailed call information with transcription"""
    auth.require_permission("calls.read")

    query = """
        SELECT id, call_id, from_number, to_number, state, direction,
               carrier, duration_seconds, recording_s3_key, transcription,
               ai_agent_prompt, started_at, ended_at, created_at, updated_at,
               (SELECT COUNT(*) FROM voice_messages WHERE call_id = voice_calls.id) as msg_count
        FROM voice_calls
        WHERE call_id = $1 AND tenant_id = $2
        LIMIT 1
    """

    async with db.tenant_connection(auth.tenant_id) as conn:
        row = await conn.fetchrow(query, call_id, auth.tenant_id)

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    return JSONResponse({
        "call_id": row["call_id"],
        "from_number": mask_pii(row["from_number"]),
        "to_number": mask_pii(row["to_number"]),
        "state": row["state"],
        "direction": row["direction"],
        "carrier": row["carrier"],
        "duration_seconds": row["duration_seconds"],
        "recording_s3_key": row["recording_s3_key"],
        "transcription": row["transcription"],
        "ai_agent_prompt": row["ai_agent_prompt"],
        "conversation_messages": row["msg_count"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
    })


@app.post("/api/v1/calls/{call_id}/transfer")
async def transfer_call(
    call_id: str,
    request: TransferCallRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Transfer call to agent or another number"""
    auth.require_permission("calls.transfer")

    query = """
        SELECT call_id, carrier FROM voice_calls
        WHERE call_id = $1 AND tenant_id = $2
        LIMIT 1
    """

    async with db.tenant_connection(auth.tenant_id) as conn:
        call_record = await conn.fetchrow(query, call_id, auth.tenant_id)

    if not call_record:
        raise HTTPException(status_code=404, detail="Call not found")

    carrier = CarrierType(call_record["carrier"])
    adapter = carrier_router.get_adapter(carrier)

    success = await adapter.transfer_call(call_record["call_id"], request.target)

    if not success:
        raise HTTPException(status_code=400, detail="Transfer failed")

    # Update call state
    update_query = """
        UPDATE voice_calls
        SET state = $1, updated_at = NOW()
        WHERE call_id = $2 AND tenant_id = $3
    """
    async with db.tenant_connection(auth.tenant_id) as conn:
        await conn.execute(update_query, CallState.TRANSFERRING.value, call_id, auth.tenant_id)

    return JSONResponse({"status": "transferred", "call_id": call_id})


@app.post("/api/v1/calls/{call_id}/hold")
async def hold_call(
    call_id: str,
    request: HoldCallRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Put call on hold or unhold"""
    auth.require_permission("calls.manage")

    new_state = CallState.ON_HOLD if request.hold else CallState.IN_PROGRESS

    update_query = """
        UPDATE voice_calls
        SET state = $1, updated_at = NOW()
        WHERE call_id = $2 AND tenant_id = $3
    """

    async with db.tenant_connection(auth.tenant_id) as conn:
        result = await conn.execute(update_query, new_state.value, call_id, auth.tenant_id)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Call not found")

    return JSONResponse({"status": "held" if request.hold else "unhold", "call_id": call_id})


@app.post("/api/v1/calls/{call_id}/end")
async def end_call(
    call_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """End a call"""
    auth.require_permission("calls.manage")

    query = """
        SELECT id, call_id, carrier FROM voice_calls
        WHERE call_id = $1 AND tenant_id = $2
        LIMIT 1
    """

    async with db.tenant_connection(auth.tenant_id) as conn:
        call_record = await conn.fetchrow(query, call_id, auth.tenant_id)

    if not call_record:
        raise HTTPException(status_code=404, detail="Call not found")

    carrier = CarrierType(call_record["carrier"])
    adapter = carrier_router.get_adapter(carrier)

    await adapter.end_call(call_record["call_id"])

    # Update database
    update_query = """
        UPDATE voice_calls
        SET state = $1, ended_at = NOW(), updated_at = NOW()
        WHERE call_id = $2 AND tenant_id = $3
    """
    async with db.tenant_connection(auth.tenant_id) as conn:
        await conn.execute(update_query, CallState.COMPLETED.value, call_id, auth.tenant_id)

    return JSONResponse({"status": "ended", "call_id": call_id})


# ============================================================================
# API Endpoints: Analytics
# ============================================================================

@app.get("/api/v1/analytics")
async def get_analytics(
    auth: AuthContext = Depends(get_auth),
    days: int = Query(30, ge=1, le=365),
):
    """Get call analytics for tenant"""
    auth.require_permission("analytics.read")

    start_date = utc_now() - timedelta(days=days)

    query = """
        SELECT
            COUNT(*) as total_calls,
            SUM(CASE WHEN direction = $2 THEN 1 ELSE 0 END) as total_inbound,
            SUM(CASE WHEN direction = $3 THEN 1 ELSE 0 END) as total_outbound,
            SUM(CASE WHEN state = $4 THEN 1 ELSE 0 END) as total_completed,
            SUM(CASE WHEN state = $5 THEN 1 ELSE 0 END) as total_failed,
            ROUND(AVG(COALESCE(duration_seconds, 0))::numeric, 2) as avg_duration_seconds,
            COUNT(CASE WHEN transcription IS NOT NULL THEN 1 END) as transcription_count
        FROM voice_calls
        WHERE tenant_id = $1 AND created_at >= $6
    """

    async with db.tenant_connection(auth.tenant_id) as conn:
        row = await conn.fetchrow(
            query,
            auth.tenant_id,
            CallDirection.INBOUND.value,
            CallDirection.OUTBOUND.value,
            CallState.COMPLETED.value,
            CallState.FAILED.value,
            start_date,
        )

    if not row:
        row = {
            "total_calls": 0,
            "total_inbound": 0,
            "total_outbound": 0,
            "total_completed": 0,
            "total_failed": 0,
            "avg_duration_seconds": 0.0,
            "transcription_count": 0,
        }

    total_calls = row["total_calls"] or 0
    total_completed = row["total_completed"] or 0
    resolution_rate = (total_completed / total_calls * 100) if total_calls > 0 else 0.0

    return JSONResponse({
        "period_start": start_date.isoformat(),
        "period_end": utc_now().isoformat(),
        "total_calls": total_calls,
        "total_inbound": row["total_inbound"] or 0,
        "total_outbound": row["total_outbound"] or 0,
        "total_completed": total_completed,
        "total_failed": row["total_failed"] or 0,
        "avg_duration_seconds": float(row["avg_duration_seconds"] or 0),
        "resolution_rate": round(resolution_rate, 2),
        "transcription_count": row["transcription_count"] or 0,
    })


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Service health check"""
    return JSONResponse({"status": "healthy", "service": "voice", "port": config.ports.voice})


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=config.ports.voice)
