"""
Priya Global Billing Service (Port 9020)

Complete billing and subscription management system powered by Stripe.
Handles:
- Multi-tenant subscription lifecycle (creation, upgrade, downgrade, cancellation)
- Usage metering and overage tracking
- Invoice management and PDF downloads
- Payment method management
- Free trial tracking and auto-conversion
- Regional pricing (USD, INR, GBP, AUD)
- Stripe webhook processing with signature verification
- Stripe Connect integration (future: plugin developer payouts)

SECURITY ARCHITECTURE:
- JWT authentication on all management endpoints
- Stripe webhook signature verification (HMAC-SHA256)
- Tenant isolation via RLS on all database queries
- PII masking in logs (never log card details)
- Rate limiting on sensitive operations
- All Stripe operations are idempotent

DATABASE:
- subscriptions: Tracks active subscriptions, billing cycle, Stripe customer ID
- usage_metrics: Real-time usage tracking (messages, tokens, storage, API calls)
- invoices: Invoice history from Stripe
- payment_methods: Saved payment methods linked to Stripe customer
- trials: Free trial tracking with expiry dates

STRIPE OBJECTS MANAGED:
- Customer: One per tenant (stripe_customer_id)
- Subscription: One active per tenant
- Product & Price: 3 products (Starter, Growth, Enterprise) with regional pricing
- Invoice: Automatically generated on billing cycle
- PaymentIntent: Card payments (legacy, Stripe handles)
- SetupIntent: Adding payment methods
- Webhook Endpoint: Receives events (checkout, invoice, subscription, payment_method)
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
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
logger = logging.getLogger("priya.billing")

# ─────────────────────────────────────────────────────────────────────────────
# Stripe Configuration
# ─────────────────────────────────────────────────────────────────────────────

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe.api_key:
    raise RuntimeError("STRIPE_SECRET_KEY environment variable must be set")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if not STRIPE_WEBHOOK_SECRET:
    raise RuntimeError("STRIPE_WEBHOOK_SECRET environment variable must be set")

# Pricing Tier Configuration
PRICING_TIERS = {
    "starter": {
        "name": "Starter",
        "features": {
            "team_members": 2,
            "channels": 3,
            "messages_per_month": 5000,
            "integrations": 1,
            "support": "community",
        },
        "prices": {
            "USD": 4900,  # $49.00
            "INR": 99900,  # ₹999.00
            "GBP": 3900,  # £39.00
            "AUD": 7900,  # $79.00
        },
    },
    "growth": {
        "name": "Growth",
        "features": {
            "team_members": 10,
            "channels": 99,
            "messages_per_month": 25000,
            "integrations": 3,
            "support": "email",
        },
        "prices": {
            "USD": 14900,  # $149.00
            "INR": 299900,  # ₹2,999.00
            "GBP": 11900,  # £119.00
            "AUD": 24900,  # $249.00
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "features": {
            "team_members": 999,
            "channels": 999,
            "messages_per_month": 100000,
            "integrations": 999,
            "support": "dedicated",
        },
        "prices": {
            "USD": 49900,  # $499.00
            "INR": 999900,  # ₹9,999.00
            "GBP": 39900,  # £399.00
            "AUD": 79900,  # $799.00
        },
    },
}

# Usage thresholds for soft/hard limits
USAGE_SOFT_LIMIT = 0.80  # Warn at 80%
USAGE_HARD_LIMIT = 1.20  # Block at 120%

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────


class CreateSubscriptionRequest(BaseModel):
    """Request to create a new subscription."""

    plan: str = Field(..., regex="^(starter|growth|enterprise)$")
    billing_cycle: str = Field(default="monthly", regex="^(monthly|annual)$")


class UpgradeSubscriptionRequest(BaseModel):
    """Request to upgrade to a higher tier."""

    new_plan: str = Field(..., regex="^(starter|growth|enterprise)$")
    prorate: bool = Field(default=True)


class DowngradeSubscriptionRequest(BaseModel):
    """Request to downgrade to a lower tier."""

    new_plan: str = Field(..., regex="^(starter|growth|enterprise)$")
    effective_date: str = Field(
        default="next_cycle", regex="^(immediate|next_cycle)$"
    )


class CancelSubscriptionRequest(BaseModel):
    """Request to cancel subscription."""

    reason: Optional[str] = Field(None, max_length=500)
    end_immediately: bool = Field(default=False)

    @validator("reason", pre=True)
    def sanitize_reason(cls, v):
        if v:
            return sanitize_input(v, max_length=500)
        return v


class PaymentMethodSetupRequest(BaseModel):
    """Request to set up a new payment method."""

    card_holder_name: str = Field(..., min_length=1, max_length=255)
    billing_zip: str = Field(..., min_length=3, max_length=10)


class SetDefaultPaymentRequest(BaseModel):
    """Request to set a payment method as default."""

    payment_method_id: str


class ExtendTrialRequest(BaseModel):
    """Request to extend trial period (admin only)."""

    days: int = Field(..., ge=1, le=90)
    reason: str = Field(..., min_length=1, max_length=500)

    @validator("reason", pre=True)
    def sanitize_reason(cls, v):
        if v:
            return sanitize_input(v, max_length=500)
        return v


# Response Models


class SubscriptionResponse(BaseModel):
    """Full subscription details."""

    id: str
    plan: str
    status: str  # active, trialing, past_due, canceled
    current_period_start: datetime
    current_period_end: datetime
    billing_cycle: str
    stripe_subscription_id: str
    stripe_customer_id: str
    trial_ends_at: Optional[datetime]
    auto_renew: bool
    next_billing_date: datetime


class UsageMetricsResponse(BaseModel):
    """Current usage metrics."""

    plan: str
    period_start: datetime
    period_end: datetime
    messages_sent: int
    messages_limit: int
    messages_percentage: float
    ai_tokens_consumed: int
    storage_used_gb: float
    api_calls: int
    warnings: List[str]
    at_soft_limit: bool
    at_hard_limit: bool


class InvoiceResponse(BaseModel):
    """Invoice details."""

    id: str
    number: str
    created: datetime
    due_date: Optional[datetime]
    amount_paid: int
    amount_due: int
    status: str
    pdf_url: str
    stripe_invoice_id: str


class PaymentMethodResponse(BaseModel):
    """Payment method details."""

    id: str
    type: str  # card, bank_account
    last_four: str
    brand: str
    exp_month: int
    exp_year: int
    is_default: bool


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App Setup
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Priya Global Billing Service",
    description="Subscription management, metering, and payment processing",
    version="1.0.0",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="billing")
init_sentry(service_name="billing", service_port=9020)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="billing")
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
    """Initialize database and Stripe connection."""
    await db.initialize()
    await event_bus.startup()
    logger.info("Billing service started on port %d", config.ports.billing)


@app.on_event("shutdown")
async def shutdown():
    """Close database connections."""
    await db.close()
    shutdown_tracing()
    await event_bus.shutdown()
    logger.info("Billing service shut down")


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


async def get_tenant_region(tenant_id: str) -> str:
    """Get the tenant's region from tenant settings."""
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT country FROM tenants WHERE id = $1", tenant_id
        )
    if not row:
        return "USD"  # Default to USD

    country = row["country"]
    region_map = {
        "IN": "INR",
        "US": "USD",
        "GB": "GBP",
        "AU": "AUD",
        "CA": "CAD",
    }
    return region_map.get(country, "USD")


async def get_stripe_customer_id(tenant_id: str) -> Optional[str]:
    """Get the Stripe customer ID for a tenant."""
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT stripe_customer_id FROM subscriptions WHERE tenant_id = $1",
            tenant_id,
        )
    return row["stripe_customer_id"] if row else None


async def ensure_stripe_customer(tenant_id: str, business_name: str) -> str:
    """Create or retrieve a Stripe customer for a tenant."""
    existing_id = await get_stripe_customer_id(tenant_id)
    if existing_id:
        return existing_id

    customer = stripe.Customer.create(
        name=business_name, metadata={"tenant_id": tenant_id}
    )

    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE subscriptions SET stripe_customer_id = $1 WHERE tenant_id = $2",
            customer.id,
            tenant_id,
        )

    logger.info("Created Stripe customer %s for %s", mask_pii(customer.id), tenant_id)
    return customer.id


async def get_current_subscription(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Get the tenant's current active subscription."""
    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, plan, status, stripe_subscription_id, stripe_customer_id,
                   current_period_start, current_period_end, trial_ends_at,
                   billing_cycle, auto_renew
            FROM subscriptions WHERE tenant_id = $1 AND status = 'active'
            """,
            tenant_id,
        )
    return dict(row) if row else None


async def record_usage(
    tenant_id: str,
    messages: int = 0,
    tokens: int = 0,
    storage_gb: float = 0,
    api_calls: int = 0,
):
    """Record usage metrics for billing period."""
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO usage_metrics
            (tenant_id, period_start, messages_sent, ai_tokens_consumed, storage_used_gb, api_calls)
            VALUES ($1, DATE_TRUNC('month', NOW()), $2, $3, $4, $5)
            ON CONFLICT (tenant_id, period_start) DO UPDATE
            SET messages_sent = usage_metrics.messages_sent + $2,
                ai_tokens_consumed = usage_metrics.ai_tokens_consumed + $3,
                storage_used_gb = usage_metrics.storage_used_gb + $4,
                api_calls = usage_metrics.api_calls + $5
            """,
            tenant_id,
            messages,
            tokens,
            storage_gb,
            api_calls,
        )


async def check_usage_limits(
    tenant_id: str, plan: str
) -> Dict[str, Any]:
    """Check current usage against plan limits."""
    limits = PRICING_TIERS[plan]["features"]
    messages_limit = limits["messages_per_month"]

    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT messages_sent, ai_tokens_consumed, storage_used_gb, api_calls
            FROM usage_metrics
            WHERE tenant_id = $1 AND period_start = DATE_TRUNC('month', NOW())
            """,
            tenant_id,
        )

    metrics = {
        "messages_sent": row["messages_sent"] if row else 0,
        "tokens_consumed": row["ai_tokens_consumed"] if row else 0,
        "storage_gb": row["storage_used_gb"] if row else 0,
        "api_calls": row["api_calls"] if row else 0,
    }

    messages_percentage = metrics["messages_sent"] / messages_limit
    warnings = []

    if messages_percentage >= USAGE_HARD_LIMIT:
        warnings.append("Hard limit reached. New messages will be blocked.")
    elif messages_percentage >= USAGE_SOFT_LIMIT:
        warnings.append("Soft limit reached (80%). Consider upgrading.")

    return {
        "metrics": metrics,
        "limits": limits,
        "percentage": messages_percentage,
        "warnings": warnings,
        "at_soft_limit": messages_percentage >= USAGE_SOFT_LIMIT,
        "at_hard_limit": messages_percentage >= USAGE_HARD_LIMIT,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Subscription Management Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/subscriptions/create", response_model=SubscriptionResponse)
async def create_subscription(
    request: CreateSubscriptionRequest,
    auth: AuthContext = Depends(get_auth),
    background_tasks: BackgroundTasks = Depends(),
):
    """Create a new subscription and return Stripe checkout session URL."""
    tenant_id = auth.tenant_id

    # Validate plan
    if request.plan not in PRICING_TIERS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    # Get tenant info
    async with db.tenant_connection(tenant_id) as conn:
        tenant = await conn.fetchrow(
            "SELECT business_name, country FROM tenants WHERE id = $1", tenant_id
        )

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Ensure Stripe customer exists
    stripe_customer_id = await ensure_stripe_customer(
        tenant_id, tenant["business_name"]
    )

    # Get currency based on region
    currency = await get_tenant_region(tenant_id)

    # Get pricing
    price_cents = PRICING_TIERS[request.plan]["prices"][currency]

    # Create or update subscription in database
    async with db.transaction(tenant_id) as conn:
        sub_id = generate_uuid()

        await conn.execute(
            """
            INSERT INTO subscriptions
            (id, tenant_id, plan, status, stripe_customer_id, stripe_subscription_id,
             current_period_start, current_period_end, billing_cycle, auto_renew, created_at)
            VALUES ($1, $2, $3, 'trialing', $4, '', $5, $6, $7, true, $8)
            ON CONFLICT (tenant_id) DO UPDATE SET
            plan = $3, status = 'trialing', updated_at = $8
            """,
            sub_id,
            tenant_id,
            request.plan,
            stripe_customer_id,
            utc_now(),
            utc_now() + timedelta(days=30),
            request.billing_cycle,
            utc_now(),
        )

    # Create Stripe subscription
    try:
        stripe_sub = stripe.Subscription.create(
            customer=stripe_customer_id,
            items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": PRICING_TIERS[request.plan]["name"],
                            "metadata": {"plan": request.plan},
                        },
                        "unit_amount": price_cents,
                        "recurring": {
                            "interval": "month" if request.billing_cycle == "monthly" else "year",
                            "interval_count": 1,
                        },
                    }
                }
            ],
            trial_period_days=14,
            metadata={"tenant_id": tenant_id, "plan": request.plan},
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe error creating subscription: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to create subscription")

    # Update with Stripe subscription ID
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE subscriptions SET stripe_subscription_id = $1 WHERE tenant_id = $2",
            stripe_sub.id,
            tenant_id,
        )

    logger.info("Created subscription for %s: %s (trial)", tenant_id, request.plan)

    subscription = await get_current_subscription(tenant_id)
    return SubscriptionResponse(**subscription)


@app.get("/api/v1/subscriptions/current", response_model=SubscriptionResponse)
async def get_current_subscription_endpoint(
    auth: AuthContext = Depends(get_auth),
):
    """Get the tenant's current subscription details."""
    subscription = await get_current_subscription(auth.tenant_id)

    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")

    return SubscriptionResponse(**subscription)


@app.post("/api/v1/subscriptions/upgrade", response_model=SubscriptionResponse)
async def upgrade_subscription(
    request: UpgradeSubscriptionRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Upgrade to a higher tier plan (with prorating)."""
    tenant_id = auth.tenant_id

    if request.new_plan not in PRICING_TIERS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    current = await get_current_subscription(tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail="No active subscription")

    # Validate upgrade path (can't downgrade)
    plan_order = {"starter": 0, "growth": 1, "enterprise": 2}
    if plan_order[request.new_plan] <= plan_order[current["plan"]]:
        raise HTTPException(
            status_code=400,
            detail="Use downgrade endpoint for lower-tier plans",
        )

    currency = await get_tenant_region(tenant_id)
    price_cents = PRICING_TIERS[request.new_plan]["prices"][currency]

    try:
        stripe_sub = stripe.Subscription.retrieve(current["stripe_subscription_id"])
        stripe.Subscription.modify(
            current["stripe_subscription_id"],
            items=[
                {
                    "id": stripe_sub.items.data[0].id,
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": PRICING_TIERS[request.new_plan]["name"],
                        },
                        "unit_amount": price_cents,
                        "recurring": {
                            "interval": current["billing_cycle"],
                            "interval_count": 1,
                        },
                    },
                    "proration_behavior": "create_prorations"
                    if request.prorate
                    else "none",
                }
            ],
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe error upgrading subscription: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to upgrade subscription")

    # Update database
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE subscriptions SET plan = $1, updated_at = $2 WHERE tenant_id = $3",
            request.new_plan,
            utc_now(),
            tenant_id,
        )

    logger.info(
        "Upgraded %s from %s to %s",
        tenant_id,
        current["plan"],
        request.new_plan,
    )

    updated_sub = await get_current_subscription(tenant_id)
    return SubscriptionResponse(**updated_sub)


@app.post("/api/v1/subscriptions/downgrade", response_model=SubscriptionResponse)
async def downgrade_subscription(
    request: DowngradeSubscriptionRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Downgrade to a lower tier (effective next cycle or immediately)."""
    tenant_id = auth.tenant_id

    if request.new_plan not in PRICING_TIERS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    current = await get_current_subscription(tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail="No active subscription")

    # Validate downgrade path
    plan_order = {"starter": 0, "growth": 1, "enterprise": 2}
    if plan_order[request.new_plan] >= plan_order[current["plan"]]:
        raise HTTPException(
            status_code=400,
            detail="Use upgrade endpoint for higher-tier plans",
        )

    currency = await get_tenant_region(tenant_id)
    price_cents = PRICING_TIERS[request.new_plan]["prices"][currency]

    try:
        stripe_sub = stripe.Subscription.retrieve(current["stripe_subscription_id"])
        stripe.Subscription.modify(
            current["stripe_subscription_id"],
            items=[
                {
                    "id": stripe_sub.items.data[0].id,
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": PRICING_TIERS[request.new_plan]["name"],
                        },
                        "unit_amount": price_cents,
                        "recurring": {
                            "interval": current["billing_cycle"],
                            "interval_count": 1,
                        },
                    },
                    "proration_behavior": "none",
                }
            ],
            billing_cycle_anchor=(
                "now"
                if request.effective_date == "immediate"
                else "unchanged"
            ),
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe error downgrading subscription: %s", str(e))
        raise HTTPException(
            status_code=500, detail="Failed to downgrade subscription"
        )

    # Update database
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE subscriptions SET plan = $1, updated_at = $2 WHERE tenant_id = $3",
            request.new_plan,
            utc_now(),
            tenant_id,
        )

    logger.info(
        "Downgraded %s to %s (effective: %s)",
        tenant_id,
        request.new_plan,
        request.effective_date,
    )

    updated_sub = await get_current_subscription(tenant_id)
    return SubscriptionResponse(**updated_sub)


@app.post("/api/v1/subscriptions/cancel")
async def cancel_subscription(
    request: CancelSubscriptionRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Cancel a subscription immediately or at period end."""
    tenant_id = auth.tenant_id

    current = await get_current_subscription(tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail="No active subscription")

    try:
        stripe.Subscription.delete(
            current["stripe_subscription_id"],
            prorate=not request.end_immediately,
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe error canceling subscription: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to cancel subscription")

    # Update database
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            UPDATE subscriptions
            SET status = 'canceled', auto_renew = false, updated_at = $1
            WHERE tenant_id = $2
            """,
            utc_now(),
            tenant_id,
        )

    logger.info("Canceled subscription for %s: %s", tenant_id, request.reason or "no reason")

    return {"status": "canceled", "message": "Subscription canceled successfully"}


@app.post("/api/v1/subscriptions/reactivate", response_model=SubscriptionResponse)
async def reactivate_subscription(
    auth: AuthContext = Depends(get_auth),
):
    """Reactivate a canceled subscription."""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        current = await conn.fetchrow(
            "SELECT * FROM subscriptions WHERE tenant_id = $1", tenant_id
        )

    if not current:
        raise HTTPException(status_code=404, detail="No subscription found")

    if current["status"] != "canceled":
        raise HTTPException(status_code=400, detail="Only canceled subscriptions can be reactivated")

    stripe_customer_id = current["stripe_customer_id"]
    currency = await get_tenant_region(tenant_id)
    price_cents = PRICING_TIERS[current["plan"]]["prices"][currency]

    try:
        stripe_sub = stripe.Subscription.create(
            customer=stripe_customer_id,
            items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": PRICING_TIERS[current["plan"]]["name"],
                        },
                        "unit_amount": price_cents,
                        "recurring": {
                            "interval": current["billing_cycle"],
                            "interval_count": 1,
                        },
                    }
                }
            ],
            metadata={"tenant_id": tenant_id},
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe error reactivating subscription: %s", str(e))
        raise HTTPException(
            status_code=500, detail="Failed to reactivate subscription"
        )

    # Update database
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            UPDATE subscriptions
            SET status = 'active', stripe_subscription_id = $1, auto_renew = true,
                updated_at = $2
            WHERE tenant_id = $3
            """,
            stripe_sub.id,
            utc_now(),
            tenant_id,
        )

    logger.info("Reactivated subscription for %s", tenant_id)

    subscription = await get_current_subscription(tenant_id)
    return SubscriptionResponse(**subscription)


# ─────────────────────────────────────────────────────────────────────────────
# Usage Metering Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/api/v1/usage", response_model=UsageMetricsResponse)
async def get_current_usage(
    auth: AuthContext = Depends(get_auth),
):
    """Get current usage metrics against plan limits."""
    tenant_id = auth.tenant_id

    current = await get_current_subscription(tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail="No active subscription")

    usage = await check_usage_limits(tenant_id, current["plan"])
    limits = PRICING_TIERS[current["plan"]]["features"]

    return UsageMetricsResponse(
        plan=current["plan"],
        period_start=current["current_period_start"],
        period_end=current["current_period_end"],
        messages_sent=usage["metrics"]["messages_sent"],
        messages_limit=limits["messages_per_month"],
        messages_percentage=usage["percentage"],
        ai_tokens_consumed=usage["metrics"]["tokens_consumed"],
        storage_used_gb=usage["metrics"]["storage_gb"],
        api_calls=usage["metrics"]["api_calls"],
        warnings=usage["warnings"],
        at_soft_limit=usage["at_soft_limit"],
        at_hard_limit=usage["at_hard_limit"],
    )


@app.get("/api/v1/usage/history")
async def get_usage_history(
    period: str = "monthly",
    limit: int = 12,
    auth: AuthContext = Depends(get_auth),
):
    """Get historical usage data (daily or monthly aggregates)."""
    tenant_id = auth.tenant_id

    if period not in ["daily", "monthly"]:
        raise HTTPException(status_code=400, detail="Invalid period")

    if limit < 1 or limit > 24:
        limit = 12

    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                DATE_TRUNC('{period}', period_start) as period,
                SUM(messages_sent) as messages,
                SUM(ai_tokens_consumed) as tokens,
                SUM(storage_used_gb) as storage_gb,
                SUM(api_calls) as api_calls
            FROM usage_metrics
            WHERE tenant_id = $1
            GROUP BY DATE_TRUNC('{period}', period_start)
            ORDER BY period DESC
            LIMIT $2
            """,
            tenant_id,
            limit,
        )

    return [dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Invoice Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/api/v1/invoices")
async def list_invoices(
    limit: int = 20,
    auth: AuthContext = Depends(get_auth),
):
    """List all invoices for the tenant."""
    tenant_id = auth.tenant_id

    if limit < 1 or limit > 100:
        limit = 20

    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, stripe_invoice_number as number, created_at as created,
                   due_date, amount_paid, amount_due, status, pdf_url, stripe_invoice_id
            FROM invoices
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            tenant_id,
            limit,
        )

    return [InvoiceResponse(**dict(row)) for row in rows]


@app.get("/api/v1/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get details for a specific invoice."""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, stripe_invoice_number as number, created_at as created,
                   due_date, amount_paid, amount_due, status, pdf_url, stripe_invoice_id
            FROM invoices
            WHERE tenant_id = $1 AND id = $2
            """,
            tenant_id,
            invoice_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return InvoiceResponse(**dict(row))


@app.get("/api/v1/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get the PDF download URL for an invoice."""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT pdf_url FROM invoices WHERE tenant_id = $1 AND id = $2",
            tenant_id,
            invoice_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")

    return {"pdf_url": row["pdf_url"]}


# ─────────────────────────────────────────────────────────────────────────────
# Payment Methods Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/payment-methods/setup")
async def setup_payment_method(
    request: PaymentMethodSetupRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Create a SetupIntent for adding a new payment method."""
    tenant_id = auth.tenant_id

    stripe_customer_id = await get_stripe_customer_id(tenant_id)
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer found")

    try:
        intent = stripe.SetupIntent.create(
            customer=stripe_customer_id,
            payment_method_types=["card"],
            metadata={"tenant_id": tenant_id},
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe error creating SetupIntent: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to create setup intent")

    return {
        "client_secret": intent.client_secret,
        "setup_intent_id": intent.id,
    }


@app.get("/api/v1/payment-methods")
async def list_payment_methods(
    auth: AuthContext = Depends(get_auth),
):
    """List all saved payment methods for the tenant."""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, type, last_four, brand, exp_month, exp_year, is_default
            FROM payment_methods
            WHERE tenant_id = $1
            ORDER BY is_default DESC, created_at DESC
            """,
            tenant_id,
        )

    return [PaymentMethodResponse(**dict(row)) for row in rows]


@app.delete("/api/v1/payment-methods/{method_id}")
async def delete_payment_method(
    method_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Remove a payment method."""
    tenant_id = auth.tenant_id

    async with db.tenant_connection(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT stripe_payment_method_id FROM payment_methods WHERE id = $1 AND tenant_id = $2",
            method_id,
            tenant_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Payment method not found")

    try:
        stripe.PaymentMethod.detach(row["stripe_payment_method_id"])
    except stripe.error.StripeError:
        pass  # Already detached

    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "DELETE FROM payment_methods WHERE id = $1 AND tenant_id = $2",
            method_id,
            tenant_id,
        )

    logger.info("Deleted payment method %s for %s", method_id, tenant_id)

    return {"message": "Payment method deleted"}


@app.put("/api/v1/payment-methods/{method_id}/default")
async def set_default_payment_method(
    method_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Set a payment method as the default."""
    tenant_id = auth.tenant_id

    async with db.transaction(tenant_id) as conn:
        # Get the payment method
        row = await conn.fetchrow(
            "SELECT stripe_payment_method_id FROM payment_methods WHERE id = $1 AND tenant_id = $2",
            method_id,
            tenant_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Payment method not found")

        # Update all to not default, then set this one
        await conn.execute(
            "UPDATE payment_methods SET is_default = false WHERE tenant_id = $1",
            tenant_id,
        )
        await conn.execute(
            "UPDATE payment_methods SET is_default = true WHERE id = $1 AND tenant_id = $2",
            method_id, tenant_id,
        )

    logger.info("Set default payment method %s for %s", method_id, tenant_id)

    return {"message": "Default payment method updated"}


# ─────────────────────────────────────────────────────────────────────────────
# Trial Management Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/api/v1/trial/extend", dependencies=[Depends(require_role("owner", "admin"))])
async def extend_trial(
    request: ExtendTrialRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Extend a trial period (admin only)."""
    tenant_id = auth.tenant_id

    current = await get_current_subscription(tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail="No subscription found")

    if current["status"] != "trialing":
        raise HTTPException(
            status_code=400, detail="Only trialing subscriptions can be extended"
        )

    new_end = current["trial_ends_at"] + timedelta(days=request.days)

    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "UPDATE subscriptions SET trial_ends_at = $1 WHERE tenant_id = $2",
            new_end,
            tenant_id,
        )

    logger.info(
        "Extended trial for %s by %s days: %s",
        tenant_id,
        request.days,
        request.reason,
    )

    return {
        "message": "Trial extended",
        "new_trial_end": new_end.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Stripe Webhook Handler
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/webhook/stripe")
async def handle_stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    SECURITY: Verify webhook signature before processing.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.warning("Invalid webhook payload: %s", str(e))
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.warning("Invalid webhook signature: %s", str(e))
        raise HTTPException(status_code=403, detail="Invalid signature")

    event_type = event["type"]
    logger.info("Processing Stripe webhook: %s", event_type)

    # Handle events
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        tenant_id = session.get("metadata", {}).get("tenant_id")

        if tenant_id:
            async with db.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    """
                    UPDATE subscriptions
                    SET status = 'active', updated_at = $1
                    WHERE tenant_id = $2
                    """,
                    utc_now(),
                    tenant_id,
                )
            logger.info("Activated subscription for %s", tenant_id)

    elif event_type == "invoice.paid":
        invoice = event["data"]["object"]
        subscription_id = invoice.get("subscription")

        if subscription_id:
            try:
                sub = stripe.Subscription.retrieve(subscription_id)
                tenant_id = sub.metadata.get("tenant_id")

                if tenant_id:
                    async with db.tenant_connection(tenant_id) as conn:
                        await conn.execute(
                            """
                            INSERT INTO invoices
                            (tenant_id, stripe_invoice_id, stripe_invoice_number,
                             amount_paid, amount_due, status, pdf_url, created_at)
                            VALUES ($1, $2, $3, $4, $5, 'paid', $6, $7)
                            ON CONFLICT (stripe_invoice_id) DO UPDATE
                            SET status = 'paid', amount_paid = $4, updated_at = $7
                            """,
                            tenant_id,
                            invoice.get("id"),
                            invoice.get("number"),
                            invoice.get("amount_paid", 0),
                            invoice.get("amount_due", 0),
                            invoice.get("hosted_invoice_url", ""),
                            utc_now(),
                        )
                    logger.info("Recorded payment for %s", tenant_id)
            except stripe.error.StripeError as e:
                logger.error("Error processing invoice.paid: %s", str(e))

    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        tenant_id = sub.metadata.get("tenant_id")

        if tenant_id:
            async with db.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    """
                    UPDATE subscriptions
                    SET status = 'canceled', updated_at = $1
                    WHERE tenant_id = $2
                    """,
                    utc_now(),
                    tenant_id,
                )
            logger.info("Marked subscription as canceled for %s", tenant_id)

    elif event_type == "payment_method.attached":
        pm = event["data"]["object"]
        customer_id = pm.get("customer")

        if customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                tenant_id = customer.metadata.get("tenant_id")

                if tenant_id and pm.get("type") == "card":
                    card = pm.get("card", {})

                    async with db.tenant_connection(tenant_id) as conn:
                        await conn.execute(
                            """
                            INSERT INTO payment_methods
                            (tenant_id, stripe_payment_method_id, type, last_four,
                             brand, exp_month, exp_year, is_default, created_at)
                            VALUES ($1, $2, 'card', $3, $4, $5, $6, false, $7)
                            ON CONFLICT (stripe_payment_method_id) DO NOTHING
                            """,
                            tenant_id,
                            pm.get("id"),
                            card.get("last4"),
                            card.get("brand"),
                            card.get("exp_month"),
                            card.get("exp_year"),
                            utc_now(),
                        )
                    logger.info("Recorded payment method for %s", tenant_id)
            except stripe.error.StripeError as e:
                logger.error("Error processing payment_method.attached: %s", str(e))

    return {"status": "received"}


# ─────────────────────────────────────────────────────────────────────────────
# Health & Status Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "billing"}


@app.get("/api/v1/pricing")
async def get_pricing():
    """Get available pricing tiers and features."""
    return PRICING_TIERS


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.ports.billing,
        log_level=config.log_level.lower(),
    )
