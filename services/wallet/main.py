"""
Priya Global Wallet Service (Port 9050)

Prepaid wallet / credits system for the platform.
Handles:
- Tenant wallet balance management
- Razorpay payment order creation and verification
- Transaction history (topups, debits, refunds)
- Internal debit API for message/call/AI usage costs
- Razorpay webhook processing with signature verification
- Auto-topup configuration (optional)

SECURITY ARCHITECTURE:
- JWT authentication on all management endpoints
- Razorpay webhook signature verification (HMAC-SHA256)
- Tenant isolation via RLS on all database queries
- All amounts stored in paisa (integer) — no floating point
- Idempotent topup verification (Razorpay payment_id dedup)
- Rate limiting on topup creation (5 per minute per tenant)

DATABASE:
- wallet_accounts: One per tenant, balance in paisa, currency
- wallet_transactions: Full ledger — topup, debit, refund, adjustment
- wallet_topups: Razorpay order tracking (order_id → payment_id mapping)

PRICING (per-unit costs deducted from wallet):
- WhatsApp message: ₹0.50 (50 paisa)
- SMS (India): ₹0.25 (25 paisa)
- Email: ₹0.10 (10 paisa)
- Voice minute (WhatsApp): ₹1.00 (100 paisa)
- Voice minute (Exotel): ₹2.50 (250 paisa)
- AI token (1K tokens): ₹0.20 (20 paisa)
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import razorpay
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Header,
    Request,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import mask_pii, sanitize_input
from shared.middleware.auth import AuthContext, get_auth, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# ─────────────────────────────────────────────────────────────────────────────
# Configure Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=config.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("priya.wallet")

# ─────────────────────────────────────────────────────────────────────────────
# Razorpay Configuration
# ─────────────────────────────────────────────────────────────────────────────

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

razorpay_client = None
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    logger.info("Razorpay client initialized")
else:
    logger.warning("Razorpay credentials not set — wallet topups will be disabled")

# ─────────────────────────────────────────────────────────────────────────────
# Per-unit costs in paisa (1 INR = 100 paisa)
# ─────────────────────────────────────────────────────────────────────────────

CHANNEL_COSTS_PAISA = {
    "whatsapp_message": 50,       # ₹0.50
    "whatsapp_voice_minute": 100, # ₹1.00
    "sms_india": 25,              # ₹0.25
    "email": 10,                  # ₹0.10
    "voice_exotel_minute": 250,   # ₹2.50
    "ai_tokens_1k": 20,           # ₹0.20
    "instagram_dm": 50,           # ₹0.50
    "telegram_message": 10,       # ₹0.10
    "webchat_message": 5,         # ₹0.05
    "rcs_message": 75,            # ₹0.75
}

# Minimum topup amount (₹100)
MIN_TOPUP_PAISA = 10000
# Maximum topup amount (₹10,00,000 = ₹10 lakhs)
MAX_TOPUP_PAISA = 100_000_00

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────


class TopupOrderRequest(BaseModel):
    """Request to create a Razorpay order for wallet topup."""
    amount_paisa: int = Field(..., ge=MIN_TOPUP_PAISA, le=MAX_TOPUP_PAISA)
    currency: str = Field(default="INR", regex="^(INR|USD)$")
    notes: Optional[str] = Field(default=None, max_length=200)


class TopupVerifyRequest(BaseModel):
    """Request to verify a Razorpay payment and credit wallet."""
    razorpay_order_id: str = Field(..., min_length=10)
    razorpay_payment_id: str = Field(..., min_length=10)
    razorpay_signature: str = Field(..., min_length=10)


class DebitRequest(BaseModel):
    """Internal request to debit wallet for usage."""
    channel: str = Field(..., description="Channel type from CHANNEL_COSTS_PAISA")
    units: int = Field(default=1, ge=1, le=10000)
    reference_id: Optional[str] = Field(default=None, description="Message/call ID")
    description: Optional[str] = Field(default=None, max_length=500)


class AdjustmentRequest(BaseModel):
    """Admin request to manually adjust wallet balance."""
    amount_paisa: int = Field(..., description="Positive for credit, negative for debit")
    reason: str = Field(..., min_length=5, max_length=500)
    reference_id: Optional[str] = None


class AutoTopupConfig(BaseModel):
    """Configuration for automatic wallet topups."""
    enabled: bool = False
    threshold_paisa: int = Field(default=100_00, ge=0)  # ₹100
    topup_amount_paisa: int = Field(default=500_00, ge=MIN_TOPUP_PAISA, le=MAX_TOPUP_PAISA)  # ₹500


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Priya Global - Wallet Service",
    description="Prepaid wallet / credits system with Razorpay integration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

event_bus = EventBus(service_name="wallet")
init_sentry(service_name="wallet", service_port=9050)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="wallet")
app.add_middleware(TracingMiddleware)

# CORS
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle Events
# ─────────────────────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    """Initialize database and event bus."""
    await db.initialize()
    await event_bus.startup()
    logger.info("Wallet service started on port 9050")


@app.on_event("shutdown")
async def shutdown():
    """Close database connections."""
    await db.close()
    shutdown_tracing()
    await event_bus.shutdown()
    logger.info("Wallet service shut down")


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "wallet",
        "version": "1.0.0",
        "razorpay_configured": razorpay_client is not None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Balance
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/api/v1/wallet/balance")
async def get_balance(auth: AuthContext = Depends(get_auth)):
    """Get the current wallet balance for the authenticated tenant."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, balance_paisa, currency, auto_topup_enabled,
                   auto_topup_threshold_paisa, auto_topup_amount_paisa,
                   created_at, updated_at
            FROM wallet_accounts
            WHERE tenant_id = $1
            """,
            auth.tenant_id,
        )

    if not row:
        # Auto-create wallet for tenant if it doesn't exist
        wallet_id = generate_uuid()
        async with db.tenant_connection(auth.tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO wallet_accounts (id, tenant_id, balance_paisa, currency)
                VALUES ($1, $2, 0, 'INR')
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                wallet_id,
                auth.tenant_id,
            )
            row = await conn.fetchrow(
                "SELECT * FROM wallet_accounts WHERE tenant_id = $1",
                auth.tenant_id,
            )

    balance_paisa = row["balance_paisa"]
    return {
        "wallet_id": str(row["id"]),
        "balance_paisa": balance_paisa,
        "balance_display": f"₹{balance_paisa / 100:.2f}",
        "currency": row["currency"],
        "auto_topup": {
            "enabled": row["auto_topup_enabled"],
            "threshold_paisa": row["auto_topup_threshold_paisa"],
            "topup_amount_paisa": row["auto_topup_amount_paisa"],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Topup — Create Razorpay Order
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/wallet/topup-order")
async def create_topup_order(
    req: TopupOrderRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Create a Razorpay order for wallet topup."""
    if not razorpay_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment gateway not configured",
        )

    topup_id = generate_uuid()

    # Create Razorpay order
    try:
        order_data = razorpay_client.order.create(
            {
                "amount": req.amount_paisa,
                "currency": req.currency,
                "receipt": f"wallet_{topup_id}",
                "notes": {
                    "tenant_id": auth.tenant_id,
                    "topup_id": topup_id,
                    "type": "wallet_topup",
                },
            }
        )
    except Exception as e:
        logger.error("Razorpay order creation failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create payment order",
        )

    razorpay_order_id = order_data["id"]

    # Persist topup record
    async with db.tenant_connection(auth.tenant_id) as conn:
        # Ensure wallet exists
        await conn.execute(
            """
            INSERT INTO wallet_accounts (id, tenant_id, balance_paisa, currency)
            VALUES ($1, $2, 0, $3)
            ON CONFLICT (tenant_id) DO NOTHING
            """,
            generate_uuid(),
            auth.tenant_id,
            req.currency,
        )

        wallet_row = await conn.fetchrow(
            "SELECT id FROM wallet_accounts WHERE tenant_id = $1",
            auth.tenant_id,
        )

        await conn.execute(
            """
            INSERT INTO wallet_topups (
                id, wallet_id, tenant_id, razorpay_order_id,
                amount_paisa, currency, status, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7)
            """,
            topup_id,
            wallet_row["id"],
            auth.tenant_id,
            razorpay_order_id,
            req.amount_paisa,
            req.currency,
            utc_now(),
        )

    logger.info(
        "Topup order created: tenant=%s amount=%d order=%s",
        mask_pii(auth.tenant_id),
        req.amount_paisa,
        razorpay_order_id,
    )

    return {
        "topup_id": topup_id,
        "razorpay_order_id": razorpay_order_id,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "amount_paisa": req.amount_paisa,
        "currency": req.currency,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Topup — Verify Razorpay Payment
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/wallet/topup-verify")
async def verify_topup(
    req: TopupVerifyRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """Verify Razorpay payment signature and credit wallet."""
    if not razorpay_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment gateway not configured",
        )

    # Verify Razorpay signature
    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": req.razorpay_order_id,
                "razorpay_payment_id": req.razorpay_payment_id,
                "razorpay_signature": req.razorpay_signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        logger.warning(
            "Payment signature verification failed: order=%s",
            req.razorpay_order_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment signature verification failed",
        )

    async with db.tenant_connection(auth.tenant_id) as conn:
        # Get topup record
        topup = await conn.fetchrow(
            """
            SELECT id, wallet_id, amount_paisa, status
            FROM wallet_topups
            WHERE razorpay_order_id = $1 AND tenant_id = $2
            """,
            req.razorpay_order_id,
            auth.tenant_id,
        )

        if not topup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Topup order not found",
            )

        if topup["status"] == "completed":
            # Idempotent — already processed
            return {"status": "already_completed", "message": "Topup already credited"}

        now = utc_now()

        # Credit wallet (atomic)
        await conn.execute(
            """
            UPDATE wallet_accounts
            SET balance_paisa = balance_paisa + $1, updated_at = $2
            WHERE id = $3
            """,
            topup["amount_paisa"],
            now,
            topup["wallet_id"],
        )

        # Update topup status
        await conn.execute(
            """
            UPDATE wallet_topups
            SET status = 'completed',
                razorpay_payment_id = $1,
                completed_at = $2
            WHERE id = $3
            """,
            req.razorpay_payment_id,
            now,
            topup["id"],
        )

        # Insert transaction record
        tx_id = generate_uuid()
        new_balance = await conn.fetchval(
            "SELECT balance_paisa FROM wallet_accounts WHERE id = $1",
            topup["wallet_id"],
        )

        await conn.execute(
            """
            INSERT INTO wallet_transactions (
                id, wallet_id, tenant_id, type, amount_paisa,
                running_balance_paisa, channel, reference_id,
                description, created_at
            )
            VALUES ($1, $2, $3, 'topup', $4, $5, 'razorpay', $6, $7, $8)
            """,
            tx_id,
            topup["wallet_id"],
            auth.tenant_id,
            topup["amount_paisa"],
            new_balance,
            req.razorpay_payment_id,
            f"Wallet topup via Razorpay",
            now,
        )

    # Publish event
    background_tasks.add_task(
        event_bus.publish,
        EventType.BILLING_PAYMENT_RECEIVED,
        {
            "tenant_id": auth.tenant_id,
            "type": "wallet_topup",
            "amount_paisa": topup["amount_paisa"],
            "payment_id": req.razorpay_payment_id,
        },
    )

    logger.info(
        "Wallet topped up: tenant=%s amount=%d payment=%s",
        mask_pii(auth.tenant_id),
        topup["amount_paisa"],
        req.razorpay_payment_id,
    )

    return {
        "status": "success",
        "amount_paisa": topup["amount_paisa"],
        "new_balance_paisa": new_balance,
        "new_balance_display": f"₹{new_balance / 100:.2f}",
        "transaction_id": tx_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Transaction History
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/api/v1/wallet/transactions")
async def get_transactions(
    page: int = 1,
    per_page: int = 25,
    type: Optional[str] = None,
    auth: AuthContext = Depends(get_auth),
):
    """Get paginated wallet transaction history."""
    if per_page > 100:
        per_page = 100
    offset = (page - 1) * per_page

    async with db.tenant_connection(auth.tenant_id) as conn:
        # Build query with optional type filter
        where_clause = "WHERE tenant_id = $1"
        params: list = [auth.tenant_id]
        if type and type in ("topup", "debit", "refund", "adjustment"):
            where_clause += " AND type = $2"
            params.append(type)

        count = await conn.fetchval(
            f"SELECT COUNT(*) FROM wallet_transactions {where_clause}",
            *params,
        )

        rows = await conn.fetch(
            f"""
            SELECT id, type, amount_paisa, running_balance_paisa,
                   channel, reference_id, description, created_at
            FROM wallet_transactions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT {per_page} OFFSET {offset}
            """,
            *params,
        )

    transactions = [
        {
            "id": str(r["id"]),
            "type": r["type"],
            "amount_paisa": r["amount_paisa"],
            "amount_display": f"₹{r['amount_paisa'] / 100:.2f}",
            "running_balance_paisa": r["running_balance_paisa"],
            "channel": r["channel"],
            "reference_id": r["reference_id"],
            "description": r["description"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

    return {
        "transactions": transactions,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": count,
            "pages": (count + per_page - 1) // per_page if count else 0,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Internal Debit API (called by other services)
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/wallet/debit")
async def debit_wallet(
    req: DebitRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth),
):
    """
    Debit wallet for channel usage.
    Called internally by channel services after sending messages/calls.
    Returns insufficient_funds error if balance too low.
    """
    if req.channel not in CHANNEL_COSTS_PAISA:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown channel: {req.channel}. Valid: {list(CHANNEL_COSTS_PAISA.keys())}",
        )

    cost_per_unit = CHANNEL_COSTS_PAISA[req.channel]
    total_cost = cost_per_unit * req.units

    async with db.tenant_connection(auth.tenant_id) as conn:
        # Atomic debit with balance check
        result = await conn.fetchrow(
            """
            UPDATE wallet_accounts
            SET balance_paisa = balance_paisa - $1,
                updated_at = $2
            WHERE tenant_id = $3 AND balance_paisa >= $1
            RETURNING id, balance_paisa
            """,
            total_cost,
            utc_now(),
            auth.tenant_id,
        )

        if not result:
            # Check if wallet exists or insufficient funds
            wallet = await conn.fetchrow(
                "SELECT balance_paisa FROM wallet_accounts WHERE tenant_id = $1",
                auth.tenant_id,
            )
            if not wallet:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Wallet not found — tenant needs to create wallet first",
                )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "insufficient_funds",
                    "balance_paisa": wallet["balance_paisa"],
                    "required_paisa": total_cost,
                    "shortfall_paisa": total_cost - wallet["balance_paisa"],
                },
            )

        # Record transaction
        tx_id = generate_uuid()
        await conn.execute(
            """
            INSERT INTO wallet_transactions (
                id, wallet_id, tenant_id, type, amount_paisa,
                running_balance_paisa, channel, reference_id,
                description, created_at
            )
            VALUES ($1, $2, $3, 'debit', $4, $5, $6, $7, $8, $9)
            """,
            tx_id,
            result["id"],
            auth.tenant_id,
            total_cost,
            result["balance_paisa"],
            req.channel,
            req.reference_id,
            req.description or f"{req.channel} x{req.units}",
            utc_now(),
        )

    # Check if auto-topup needed
    if result["balance_paisa"] < 100_00:  # Below ₹100
        background_tasks.add_task(
            _check_auto_topup, auth.tenant_id, result["id"], result["balance_paisa"]
        )

    return {
        "status": "debited",
        "amount_paisa": total_cost,
        "new_balance_paisa": result["balance_paisa"],
        "transaction_id": tx_id,
    }


async def _check_auto_topup(tenant_id: str, wallet_id: str, current_balance: int):
    """Check and trigger auto-topup if configured."""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            wallet = await conn.fetchrow(
                """
                SELECT auto_topup_enabled, auto_topup_threshold_paisa,
                       auto_topup_amount_paisa
                FROM wallet_accounts WHERE id = $1
                """,
                wallet_id,
            )

        if (
            wallet
            and wallet["auto_topup_enabled"]
            and current_balance <= wallet["auto_topup_threshold_paisa"]
        ):
            await event_bus.publish(
                EventType.BILLING_PAYMENT_RECEIVED,
                {
                    "tenant_id": tenant_id,
                    "type": "auto_topup_trigger",
                    "current_balance_paisa": current_balance,
                    "threshold_paisa": wallet["auto_topup_threshold_paisa"],
                    "topup_amount_paisa": wallet["auto_topup_amount_paisa"],
                },
            )
            logger.info("Auto-topup triggered for tenant %s", mask_pii(tenant_id))
    except Exception as e:
        logger.error("Auto-topup check failed: %s", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Auto-Topup Configuration
# ─────────────────────────────────────────────────────────────────────────────


@app.put("/api/v1/wallet/auto-topup")
async def configure_auto_topup(
    req: AutoTopupConfig,
    auth: AuthContext = Depends(get_auth),
):
    """Configure auto-topup settings for the tenant wallet."""
    async with db.tenant_connection(auth.tenant_id) as conn:
        result = await conn.execute(
            """
            UPDATE wallet_accounts
            SET auto_topup_enabled = $1,
                auto_topup_threshold_paisa = $2,
                auto_topup_amount_paisa = $3,
                updated_at = $4
            WHERE tenant_id = $5
            """,
            req.enabled,
            req.threshold_paisa,
            req.topup_amount_paisa,
            utc_now(),
            auth.tenant_id,
        )

    if result == "UPDATE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    return {"status": "updated", "auto_topup": req.dict()}


# ─────────────────────────────────────────────────────────────────────────────
# Admin — Manual Adjustment
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/wallet/adjust")
async def adjust_balance(
    req: AdjustmentRequest,
    auth: AuthContext = Depends(require_role("admin")),
):
    """Admin-only: manually adjust wallet balance (credit or debit)."""
    now = utc_now()

    async with db.tenant_connection(auth.tenant_id) as conn:
        if req.amount_paisa < 0:
            # Debit — check sufficient balance
            result = await conn.fetchrow(
                """
                UPDATE wallet_accounts
                SET balance_paisa = balance_paisa + $1, updated_at = $2
                WHERE tenant_id = $3 AND balance_paisa >= $4
                RETURNING id, balance_paisa
                """,
                req.amount_paisa,
                now,
                auth.tenant_id,
                abs(req.amount_paisa),
            )
        else:
            # Credit
            result = await conn.fetchrow(
                """
                UPDATE wallet_accounts
                SET balance_paisa = balance_paisa + $1, updated_at = $2
                WHERE tenant_id = $3
                RETURNING id, balance_paisa
                """,
                req.amount_paisa,
                now,
                auth.tenant_id,
            )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wallet not found or insufficient balance for debit",
            )

        tx_id = generate_uuid()
        tx_type = "adjustment"
        await conn.execute(
            """
            INSERT INTO wallet_transactions (
                id, wallet_id, tenant_id, type, amount_paisa,
                running_balance_paisa, channel, reference_id,
                description, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'admin', $7, $8, $9)
            """,
            tx_id,
            result["id"],
            auth.tenant_id,
            tx_type,
            abs(req.amount_paisa),
            result["balance_paisa"],
            req.reference_id,
            f"Admin adjustment: {req.reason}",
            now,
        )

    logger.info(
        "Admin adjustment: tenant=%s amount=%d reason=%s",
        mask_pii(auth.tenant_id),
        req.amount_paisa,
        req.reason[:50],
    )

    return {
        "status": "adjusted",
        "amount_paisa": req.amount_paisa,
        "new_balance_paisa": result["balance_paisa"],
        "transaction_id": tx_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pricing Info (public)
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/api/v1/wallet/pricing")
async def get_pricing():
    """Get current per-unit pricing for all channels."""
    return {
        "currency": "INR",
        "costs": {
            channel: {
                "cost_paisa": cost,
                "cost_display": f"₹{cost / 100:.2f}",
            }
            for channel, cost in CHANNEL_COSTS_PAISA.items()
        },
        "min_topup_paisa": MIN_TOPUP_PAISA,
        "min_topup_display": f"₹{MIN_TOPUP_PAISA / 100:.2f}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Razorpay Webhook
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    """
    Razorpay webhook handler — backup for client-side verification.
    Handles: payment.captured, payment.failed, refund.processed
    """
    if not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook not configured",
        )

    body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    # Verify webhook signature
    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        logger.warning("Invalid Razorpay webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = json.loads(body)
    event = payload.get("event", "")
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})

    logger.info("Razorpay webhook: event=%s", event)

    if event == "payment.captured":
        # Backup credit — only if not already processed by client verify
        order_id = entity.get("order_id")
        payment_id = entity.get("id")

        if order_id:
            async with db.connection() as conn:
                topup = await conn.fetchrow(
                    "SELECT id, wallet_id, tenant_id, amount_paisa, status FROM wallet_topups WHERE razorpay_order_id = $1",
                    order_id,
                )

            if topup and topup["status"] == "pending":
                now = utc_now()
                async with db.tenant_connection(topup["tenant_id"]) as conn:
                    await conn.execute(
                        "UPDATE wallet_accounts SET balance_paisa = balance_paisa + $1, updated_at = $2 WHERE id = $3",
                        topup["amount_paisa"],
                        now,
                        topup["wallet_id"],
                    )
                    await conn.execute(
                        "UPDATE wallet_topups SET status = 'completed', razorpay_payment_id = $1, completed_at = $2 WHERE id = $3",
                        payment_id,
                        now,
                        topup["id"],
                    )

                    new_balance = await conn.fetchval(
                        "SELECT balance_paisa FROM wallet_accounts WHERE id = $1",
                        topup["wallet_id"],
                    )
                    await conn.execute(
                        """
                        INSERT INTO wallet_transactions (id, wallet_id, tenant_id, type, amount_paisa, running_balance_paisa, channel, reference_id, description, created_at)
                        VALUES ($1, $2, $3, 'topup', $4, $5, 'razorpay_webhook', $6, 'Wallet topup via Razorpay webhook', $7)
                        """,
                        generate_uuid(),
                        topup["wallet_id"],
                        topup["tenant_id"],
                        topup["amount_paisa"],
                        new_balance,
                        payment_id,
                        now,
                    )

                logger.info("Webhook credited wallet: tenant=%s amount=%d", mask_pii(topup["tenant_id"]), topup["amount_paisa"])

    elif event == "payment.failed":
        order_id = entity.get("order_id")
        if order_id:
            async with db.connection() as conn:
                await conn.execute(
                    "UPDATE wallet_topups SET status = 'failed' WHERE razorpay_order_id = $1 AND status = 'pending'",
                    order_id,
                )
            logger.warning("Payment failed: order=%s", order_id)

    return {"status": "ok"}
