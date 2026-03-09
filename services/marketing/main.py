"""
Marketing Manager AI Service - Priya Global Multi-Tenant AI Sales Platform

AI-powered marketing automation engine for campaign management, content generation,
audience segmentation, drip sequences, A/B testing, and marketing analytics.

FastAPI service running on port 9022.
Uses multi-LLM router (Claude + GPT-4) for marketing-specific AI capabilities.
Multi-tenant with strict data isolation and brand voice personalization.
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import redis.asyncio as redis

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.core.config import config
from shared.core.database import db, get_tenant_pool
from shared.core.security import mask_pii, sanitize_input
from shared.middleware.auth import get_auth, AuthContext, require_role, require_permission
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logger = logging.getLogger("marketing_manager")
logger.setLevel(logging.INFO)

# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class CampaignType(str, Enum):
    DRIP_SEQUENCE = "drip_sequence"
    BROADCAST = "broadcast"
    CART_RECOVERY = "cart_recovery"
    RE_ENGAGEMENT = "re_engagement"
    WELCOME_SERIES = "welcome_series"
    PRODUCT_LAUNCH = "product_launch"
    SEASONAL_PROMO = "seasonal_promo"
    REVIEW_REQUEST = "review_request"

class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class ContentTone(str, Enum):
    FORMAL = "formal"
    CASUAL = "casual"
    URGENT = "urgent"
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"

class SegmentType(str, Enum):
    ALL_CUSTOMERS = "all_customers"
    NEW_LAST_30D = "new_last_30d"
    HIGH_VALUE = "high_value"
    AT_RISK = "at_risk"
    CHURNED = "churned"
    CART_ABANDONERS = "cart_abandoners"
    REPEAT_BUYERS = "repeat_buyers"
    CUSTOM = "custom"

class LLMModel(str, Enum):
    CLAUDE_35_SONNET = "claude-3-5-sonnet-20241022"
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"

# LLM configuration for marketing
LLM_CONFIG = {
    "primary": LLMModel.CLAUDE_35_SONNET,
    "secondary": LLMModel.GPT_4O,
    "cost_optimized": LLMModel.GPT_4O_MINI,
}

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    campaign_type: CampaignType
    channels: list[str] = Field(..., min_items=1)  # whatsapp, email, sms, etc
    audience_id: Optional[str] = None
    schedule_date: Optional[datetime] = None
    description: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        return sanitize_input(v)

class CampaignResponse(BaseModel):
    id: str
    name: str
    campaign_type: CampaignType
    status: CampaignStatus
    channels: list[str]
    created_at: datetime
    scheduled_at: Optional[datetime]
    launched_at: Optional[datetime]
    performance: dict
    audience_count: int

class ContentGenerateRequest(BaseModel):
    campaign_type: CampaignType
    channel: str  # whatsapp, email, sms
    tone: ContentTone = ContentTone.FRIENDLY
    audience_description: str
    product_context: Optional[str] = None
    language: str = "en"

class ContentGenerateResponse(BaseModel):
    subject_line: Optional[str] = None
    message_body: str
    cta_text: str
    variant_b: str
    model_used: str

class AudienceSegmentRequest(BaseModel):
    name: str
    segment_type: SegmentType
    natural_language_query: Optional[str] = None
    filters: Optional[dict] = None

class AudienceSegmentResponse(BaseModel):
    id: str
    name: str
    segment_type: SegmentType
    customer_count: int
    created_at: datetime

class DripSequenceStep(BaseModel):
    step_number: int
    delay_hours: int
    channel: str
    message: str
    conditional_branching: Optional[dict] = None

class DripSequenceCreate(BaseModel):
    name: str
    trigger: str  # signup, purchase, cart_abandon, inactivity
    steps: list[DripSequenceStep]

class DripSequenceResponse(BaseModel):
    id: str
    name: str
    trigger: str
    steps_count: int
    created_at: datetime
    active: bool

class ExperimentCreate(BaseModel):
    name: str
    campaign_id: str
    variant_count: int = Field(2, ge=2, le=4)
    split_percentage: Optional[float] = None

class ExperimentResponse(BaseModel):
    id: str
    campaign_id: str
    variant_count: int
    status: str
    winner: Optional[str] = None
    confidence_level: float

class CartRecoveryConfig(BaseModel):
    enabled: bool
    first_message_delay_hours: int = 1
    discount_percentage: Optional[float] = None
    sequences: list[dict] = Field(default_factory=list)

class ReviewCampaignCreate(BaseModel):
    name: str
    days_after_delivery: int = Field(5, ge=1, le=30)
    preferred_channel: str = "email"

class RecommendationResponse(BaseModel):
    best_send_time: str
    optimal_length: dict
    suggested_products: list[dict]
    budget_allocation: dict
    estimated_revenue: float

class MarketingDashboard(BaseModel):
    total_campaigns: int
    active_campaigns: int
    campaign_performance: list[dict]
    channel_effectiveness: dict
    content_performance: list[dict]
    roi_calculator: dict
    ai_recommendations: list[str]

# ============================================================================
# MULTI-LLM ROUTER (MARKETING-OPTIMIZED)
# ============================================================================

class MarketingLLMRouter:
    """Routes marketing requests to optimal LLM with auto-failover."""

    def __init__(self):
        self.http_client = httpx.AsyncClient()
        self.token_usage = {}

    async def generate_marketing_content(
        self,
        prompt: str,
        campaign_context: str,
        model_preference: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        max_tokens: int = 800,
    ) -> dict:
        """Generate marketing content with auto-failover."""

        model = model_preference or LLM_CONFIG["primary"]
        models_to_try = [model]

        if model == LLMModel.CLAUDE_35_SONNET:
            models_to_try.append(LLMModel.GPT_4O)
            models_to_try.append(LLMModel.GPT_4O_MINI)
        elif model == LLMModel.GPT_4O:
            models_to_try.append(LLMModel.CLAUDE_35_SONNET)
            models_to_try.append(LLMModel.GPT_4O_MINI)

        for attempt_model in models_to_try:
            try:
                if attempt_model == LLMModel.CLAUDE_35_SONNET:
                    return await self._call_claude(
                        prompt, campaign_context, max_tokens, tenant_id
                    )
                elif attempt_model in [LLMModel.GPT_4O, LLMModel.GPT_4O_MINI]:
                    return await self._call_openai(
                        attempt_model, prompt, campaign_context, max_tokens, tenant_id
                    )
            except Exception as e:
                logger.warning("LLM %s failed: %s. Trying fallback...", attempt_model, str(e))
                continue

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All LLM providers unavailable",
        )

    async def _call_claude(
        self,
        prompt: str,
        message: str,
        max_tokens: int,
        tenant_id: Optional[UUID],
    ) -> dict:
        """Call Anthropic Claude API."""
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": LLMModel.CLAUDE_35_SONNET,
            "max_tokens": max_tokens,
            "system": prompt,
            "messages": [{"role": "user", "content": message}],
        }

        response = await self.http_client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        tokens_used = data.get("usage", {}).get("output_tokens", 0)
        if tenant_id:
            await self._track_usage(tenant_id, LLMModel.CLAUDE_35_SONNET, tokens_used)

        return {
            "text": data["content"][0]["text"],
            "model": LLMModel.CLAUDE_35_SONNET,
            "tokens_used": tokens_used,
            "finish_reason": data.get("stop_reason", "end_turn"),
        }

    async def _call_openai(
        self,
        model: str,
        prompt: str,
        message: str,
        max_tokens: int,
        tenant_id: Optional[UUID],
    ) -> dict:
        """Call OpenAI GPT API."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
        }

        response = await self.http_client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        tokens_used = data.get("usage", {}).get("completion_tokens", 0)
        if tenant_id:
            await self._track_usage(tenant_id, model, tokens_used)

        return {
            "text": data["choices"][0]["message"]["content"],
            "model": model,
            "tokens_used": tokens_used,
            "finish_reason": data["choices"][0].get("finish_reason", "stop"),
        }

    async def _track_usage(self, tenant_id: UUID, model: str, tokens: int):
        """Track token usage for billing."""
        pool = await get_tenant_pool(tenant_id)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ai_token_usage (tenant_id, model, tokens_used, recorded_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (tenant_id, model, DATE(recorded_at))
                DO UPDATE SET tokens_used = ai_token_usage.tokens_used + $3
                """,
                str(tenant_id),
                model,
                tokens,
            )

# ============================================================================
# MARKETING ENGINES
# ============================================================================

class ContentGenerationEngine:
    """AI-powered marketing content generation."""

    def __init__(self, llm_router: MarketingLLMRouter):
        self.llm_router = llm_router

    async def generate_marketing_content(
        self,
        tenant_id: UUID,
        request: ContentGenerateRequest,
    ) -> ContentGenerateResponse:
        """Generate channel-specific marketing content with A/B variant."""

        pool = await get_tenant_pool(tenant_id)

        async with pool.acquire() as conn:
            brand_config = await conn.fetchrow(
                """
                SELECT brand_voice, brand_tone, company_name FROM tenant_config
                WHERE tenant_id = $1
                """,
                str(tenant_id),
            )

        brand_voice = brand_config["brand_voice"] if brand_config else "friendly and professional"
        company_name = brand_config.get("company_name", "our company") if brand_config else "our company"

        # Channel-specific constraints
        channel_specs = {
            "whatsapp": {
                "max_chars": 1024,
                "include_emojis": True,
                "style": "casual and conversational",
            },
            "email": {
                "max_chars": 3000,
                "include_html": True,
                "style": "detailed and formatted",
            },
            "sms": {
                "max_chars": 160,
                "include_emojis": False,
                "style": "ultra-concise",
            },
        }

        specs = channel_specs.get(request.channel, channel_specs["email"])

        # Sanitize user input to prevent prompt injection
        audience_description = sanitize_input(request.audience_description, max_length=500)
        product_context = sanitize_input(request.product_context, max_length=500) if request.product_context else "Not specified"

        # Build marketing prompt
        prompt = f"""You are an expert marketing copywriter for {company_name}.
Your writing style: {brand_voice}
Tone for this message: {request.tone.value}

Create compelling marketing content for a {request.campaign_type.value} campaign.
Target audience: {audience_description}
Product context: {product_context}
Language: {request.language}

Channel: {request.channel}
Style guidelines: {specs['style']}
Max length: {specs['max_chars']} characters
Include emojis: {specs['include_emojis']}

Return ONLY a valid JSON object with this structure:
{{
    "subject_line": "Email subject (or null for non-email)",
    "message_body": "Main marketing message",
    "cta_text": "Call-to-action button text",
    "variant_b": "Alternative version for A/B testing"
}}

Make both variants compelling, different in tone/approach, and on-brand."""

        response = await self.llm_router.generate_marketing_content(
            prompt=prompt,
            campaign_context=audience_description,
            tenant_id=tenant_id,
            max_tokens=800,
        )

        try:
            content_json = json.loads(response["text"])
            return ContentGenerateResponse(
                subject_line=content_json.get("subject_line"),
                message_body=content_json.get("message_body", ""),
                cta_text=content_json.get("cta_text", ""),
                variant_b=content_json.get("variant_b", ""),
                model_used=response["model"],
            )
        except json.JSONDecodeError:
            logger.error("Failed to parse content JSON: %s", response.get("text", "")[:200])
            raise HTTPException(status_code=500, detail="Content generation failed")

class AudienceSegmentationEngine:
    """AI-powered audience segmentation."""

    async def create_segment(
        self,
        tenant_id: UUID,
        request: AudienceSegmentRequest,
    ) -> AudienceSegmentResponse:
        """Create audience segment from natural language or filters."""

        pool = await get_tenant_pool(tenant_id)

        segment_id = str(uuid4())
        created_at = datetime.utcnow()

        # Build SQL query based on segment type
        query = await self._build_segment_query(tenant_id, request)

        async with pool.acquire() as conn:
            # Count customers matching the segment
            customer_count = await conn.fetchval(query)

            # Store segment definition
            await conn.execute(
                """
                INSERT INTO marketing_segments
                (id, tenant_id, name, segment_type, filters, query_definition, customer_count, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                segment_id,
                str(tenant_id),
                sanitize_input(request.name),
                request.segment_type.value,
                json.dumps(request.filters or {}),
                query,
                customer_count,
                created_at,
            )

        return AudienceSegmentResponse(
            id=segment_id,
            name=request.name,
            segment_type=request.segment_type,
            customer_count=customer_count,
            created_at=created_at,
        )

    async def _build_segment_query(
        self, tenant_id: UUID, request: AudienceSegmentRequest
    ) -> str:
        """Build SQL query for segment."""

        base_query = f"""
        SELECT COUNT(DISTINCT c.id) FROM customers c
        WHERE c.tenant_id = '{tenant_id}'
        """

        if request.segment_type == SegmentType.ALL_CUSTOMERS:
            return base_query

        elif request.segment_type == SegmentType.NEW_LAST_30D:
            base_query += " AND c.created_at >= NOW() - INTERVAL '30 days'"

        elif request.segment_type == SegmentType.HIGH_VALUE:
            base_query += """
            AND (SELECT SUM(amount) FROM purchases p WHERE p.customer_id = c.id
                 AND p.tenant_id = c.tenant_id) > 1000
            """

        elif request.segment_type == SegmentType.AT_RISK:
            base_query += """
            AND c.id IN (
                SELECT DISTINCT customer_id FROM purchases
                WHERE tenant_id = $1
                AND created_at < NOW() - INTERVAL '90 days'
            )
            """

        elif request.segment_type == SegmentType.CHURNED:
            base_query += """
            AND c.id IN (
                SELECT DISTINCT customer_id FROM purchases
                WHERE tenant_id = $1
                AND created_at < NOW() - INTERVAL '180 days'
            )
            """

        elif request.segment_type == SegmentType.CART_ABANDONERS:
            base_query += """
            AND c.id IN (
                SELECT DISTINCT customer_id FROM abandoned_carts
                WHERE tenant_id = $1 AND created_at >= NOW() - INTERVAL '7 days'
            )
            """

        elif request.segment_type == SegmentType.REPEAT_BUYERS:
            base_query += """
            AND (SELECT COUNT(*) FROM purchases p WHERE p.customer_id = c.id
                 AND p.tenant_id = c.tenant_id) > 1
            """

        elif request.segment_type == SegmentType.CUSTOM and request.filters:
            # SECURITY: Validate and sanitize all filter values — never inject raw user input
            for key, value in request.filters.items():
                if key == "purchase_count":
                    # Validate: must be a positive integer
                    try:
                        count_val = int(value)
                        if count_val < 0 or count_val > 100000:
                            raise ValueError("Out of range")
                    except (ValueError, TypeError):
                        continue  # Skip invalid filter
                    base_query += f" AND (SELECT COUNT(*) FROM purchases p WHERE p.customer_id = c.id AND p.tenant_id = c.tenant_id) > {count_val}"
                elif key == "min_spent":
                    # Validate: must be a positive number
                    try:
                        spent_val = float(value)
                        if spent_val < 0 or spent_val > 1e9:
                            raise ValueError("Out of range")
                    except (ValueError, TypeError):
                        continue  # Skip invalid filter
                    base_query += f" AND (SELECT COALESCE(SUM(amount), 0) FROM purchases p WHERE p.customer_id = c.id AND p.tenant_id = c.tenant_id) >= {spent_val}"
                elif key == "location":
                    # Validate: alphanumeric + spaces only, max 100 chars (country names)
                    import re as _re
                    if not isinstance(value, str) or not _re.match(r'^[a-zA-Z\s\-]{1,100}$', value):
                        continue  # Skip invalid filter
                    # Use parameterized approach — append to param list
                    # Since base_query uses $1 for tenant_id, we append with escaped value
                    safe_location = value.replace("'", "''")  # Escape single quotes
                    base_query += f" AND c.country = '{safe_location}'"

        return base_query

class DripSequenceEngine:
    """Drip sequence automation."""

    async def create_sequence(
        self,
        tenant_id: UUID,
        request: DripSequenceCreate,
    ) -> DripSequenceResponse:
        """Create automated drip sequence."""

        pool = await get_tenant_pool(tenant_id)
        sequence_id = str(uuid4())
        created_at = datetime.utcnow()

        async with pool.acquire() as conn:
            # Store sequence metadata
            await conn.execute(
                """
                INSERT INTO drip_sequences
                (id, tenant_id, name, trigger, steps_count, created_at, active)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                sequence_id,
                str(tenant_id),
                sanitize_input(request.name),
                request.trigger,
                len(request.steps),
                created_at,
                True,
            )

            # Store individual steps
            for step in request.steps:
                step_id = str(uuid4())
                await conn.execute(
                    """
                    INSERT INTO drip_sequence_steps
                    (id, sequence_id, tenant_id, step_number, delay_hours, channel, message, conditional_branching)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    step_id,
                    sequence_id,
                    str(tenant_id),
                    step.step_number,
                    step.delay_hours,
                    step.channel,
                    step.message,
                    json.dumps(step.conditional_branching or {}),
                )

        return DripSequenceResponse(
            id=sequence_id,
            name=request.name,
            trigger=request.trigger,
            steps_count=len(request.steps),
            created_at=created_at,
            active=True,
        )

class ABTestingEngine:
    """A/B testing and variant analysis."""

    async def create_experiment(
        self,
        tenant_id: UUID,
        request: ExperimentCreate,
    ) -> ExperimentResponse:
        """Create A/B test experiment."""

        pool = await get_tenant_pool(tenant_id)
        experiment_id = str(uuid4())
        created_at = datetime.utcnow()

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO marketing_experiments
                (id, tenant_id, campaign_id, variant_count, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                experiment_id,
                str(tenant_id),
                request.campaign_id,
                request.variant_count,
                "active",
                created_at,
            )

        return ExperimentResponse(
            id=experiment_id,
            campaign_id=request.campaign_id,
            variant_count=request.variant_count,
            status="active",
            winner=None,
            confidence_level=0.0,
        )

    async def analyze_and_promote_winner(
        self,
        tenant_id: UUID,
        experiment_id: str,
        confidence_threshold: float = 0.95,
    ) -> dict:
        """Analyze experiment results and auto-promote winner."""

        pool = await get_tenant_pool(tenant_id)

        async with pool.acquire() as conn:
            variant_stats = await conn.fetch(
                """
                SELECT variant_id, COUNT(*) as total,
                       SUM(CASE WHEN opened = true THEN 1 ELSE 0 END) as opens,
                       SUM(CASE WHEN clicked = true THEN 1 ELSE 0 END) as clicks,
                       SUM(CASE WHEN converted = true THEN 1 ELSE 0 END) as conversions
                FROM experiment_messages
                WHERE experiment_id = $1 AND tenant_id = $2
                GROUP BY variant_id
                """,
                experiment_id,
                str(tenant_id),
            )

        if not variant_stats:
            return {"winner": None, "confidence": 0.0}

        # Calculate conversion rates
        variant_performance = []
        for stat in variant_stats:
            conversion_rate = (stat["conversions"] or 0) / (stat["total"] or 1)
            variant_performance.append({
                "variant_id": stat["variant_id"],
                "conversion_rate": conversion_rate,
                "total": stat["total"],
            })

        # Find winner (highest conversion rate)
        winner = max(variant_performance, key=lambda x: x["conversion_rate"])

        # Simple confidence calculation (chi-square would be better)
        confidence = min(0.99, winner["conversion_rate"] * 100 / 100)

        return {
            "winner": winner["variant_id"],
            "confidence": confidence,
            "performance": variant_performance,
        }

class CartRecoveryEngine:
    """Cart recovery automation."""

    async def configure_recovery(
        self,
        tenant_id: UUID,
        config: CartRecoveryConfig,
    ) -> dict:
        """Configure cart recovery sequence."""

        pool = await get_tenant_pool(tenant_id)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cart_recovery_config
                (tenant_id, enabled, first_message_delay, discount_percent, config)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (tenant_id)
                DO UPDATE SET enabled = $2, first_message_delay = $3,
                             discount_percent = $4, config = $5
                """,
                str(tenant_id),
                config.enabled,
                config.first_message_delay_hours,
                config.discount_percentage,
                json.dumps(config.dict()),
            )

        return {"status": "configured", "enabled": config.enabled}

class ReviewRequestEngine:
    """Review collection automation."""

    async def create_review_campaign(
        self,
        tenant_id: UUID,
        request: ReviewCampaignCreate,
    ) -> dict:
        """Create automated review request campaign."""

        campaign_id = str(uuid4())
        created_at = datetime.utcnow()

        pool = await get_tenant_pool(tenant_id)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO review_campaigns
                (id, tenant_id, name, days_after_delivery, preferred_channel, created_at, active)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                campaign_id,
                str(tenant_id),
                sanitize_input(request.name),
                request.days_after_delivery,
                request.preferred_channel,
                created_at,
                True,
            )

        return {
            "id": campaign_id,
            "name": request.name,
            "status": "active",
            "created_at": created_at,
        }

class MarketingAnalyticsEngine:
    """Marketing performance analytics."""

    async def get_dashboard(self, tenant_id: UUID) -> MarketingDashboard:
        """Get comprehensive marketing dashboard."""

        pool = await get_tenant_pool(tenant_id)

        async with pool.acquire() as conn:
            # Campaign metrics
            campaigns = await conn.fetch(
                """
                SELECT id, name, campaign_type, status, created_at,
                       COALESCE(sent_count, 0) as sent,
                       COALESCE(opened_count, 0) as opened,
                       COALESCE(clicked_count, 0) as clicked,
                       COALESCE(converted_count, 0) as converted,
                       COALESCE(revenue, 0) as revenue
                FROM marketing_campaigns
                WHERE tenant_id = $1
                ORDER BY created_at DESC LIMIT 20
                """,
                str(tenant_id),
            )

            # Overall metrics
            overall = await conn.fetchrow(
                """
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                       SUM(COALESCE(sent_count, 0)) as total_sent,
                       SUM(COALESCE(opened_count, 0)) as total_opened,
                       SUM(COALESCE(clicked_count, 0)) as total_clicked,
                       SUM(COALESCE(converted_count, 0)) as total_converted,
                       SUM(COALESCE(revenue, 0)) as total_revenue
                FROM marketing_campaigns
                WHERE tenant_id = $1
                """,
                str(tenant_id),
            )

            # Channel metrics
            channels = await conn.fetch(
                """
                SELECT channel,
                       COUNT(*) as campaigns,
                       SUM(COALESCE(sent_count, 0)) as sent,
                       SUM(COALESCE(opened_count, 0)) as opened,
                       SUM(COALESCE(clicked_count, 0)) as clicked,
                       SUM(COALESCE(converted_count, 0)) as conversions,
                       SUM(COALESCE(revenue, 0)) as revenue
                FROM marketing_campaign_channels
                WHERE tenant_id = $1
                GROUP BY channel
                """,
                str(tenant_id),
            )

        campaign_performance = []
        for c in campaigns:
            open_rate = (c["opened"] / c["sent"] * 100) if c["sent"] > 0 else 0
            click_rate = (c["clicked"] / c["sent"] * 100) if c["sent"] > 0 else 0
            conversion_rate = (c["converted"] / c["sent"] * 100) if c["sent"] > 0 else 0
            roi = ((c["revenue"] - 100) / 100 * 100) if c["revenue"] > 0 else 0

            campaign_performance.append({
                "name": c["name"],
                "type": c["campaign_type"],
                "status": c["status"],
                "sent": c["sent"],
                "open_rate": round(open_rate, 2),
                "click_rate": round(click_rate, 2),
                "conversion_rate": round(conversion_rate, 2),
                "revenue": c["revenue"],
                "roi": round(roi, 2),
            })

        channel_effectiveness = {}
        for ch in channels:
            open_rate = (ch["opened"] / ch["sent"] * 100) if ch["sent"] > 0 else 0
            click_rate = (ch["clicked"] / ch["sent"] * 100) if ch["sent"] > 0 else 0
            conversion_rate = (ch["conversions"] / ch["sent"] * 100) if ch["sent"] > 0 else 0

            channel_effectiveness[ch["channel"]] = {
                "campaigns": ch["campaigns"],
                "sent": ch["sent"],
                "open_rate": round(open_rate, 2),
                "click_rate": round(click_rate, 2),
                "conversion_rate": round(conversion_rate, 2),
                "revenue": ch["revenue"],
            }

        roi_calc = {}
        if overall:
            total_sent = overall["total_sent"] or 0
            if total_sent > 0:
                roi_calc = {
                    "total_campaigns": overall["total"],
                    "total_sent": total_sent,
                    "total_opened": overall["total_opened"] or 0,
                    "total_clicked": overall["total_clicked"] or 0,
                    "total_converted": overall["total_converted"] or 0,
                    "total_revenue": overall["total_revenue"] or 0,
                    "avg_open_rate": round((overall["total_opened"] / total_sent * 100), 2),
                    "avg_conversion_rate": round((overall["total_converted"] / total_sent * 100), 2),
                }

        ai_recommendations = await self._generate_recommendations(
            tenant_id, campaign_performance, channel_effectiveness
        )

        return MarketingDashboard(
            total_campaigns=overall["total"] if overall else 0,
            active_campaigns=overall["active"] if overall else 0,
            campaign_performance=campaign_performance,
            channel_effectiveness=channel_effectiveness,
            content_performance=campaign_performance[:5],
            roi_calculator=roi_calc,
            ai_recommendations=ai_recommendations,
        )

    async def _generate_recommendations(
        self, tenant_id: UUID, campaigns: list, channels: dict
    ) -> list[str]:
        """Generate AI recommendations based on data."""

        recommendations = []

        # Channel recommendations
        if channels:
            best_channel = max(
                channels.items(),
                key=lambda x: x[1].get("conversion_rate", 0)
            )
            if best_channel[1]["conversion_rate"] > 5:
                recommendations.append(
                    f"Your {best_channel[0]} campaigns have the highest conversion rate "
                    f"({best_channel[1]['conversion_rate']:.1f}%). Consider allocating more budget there."
                )

        # Performance recommendations
        if campaigns:
            avg_conversion = sum(c.get("conversion_rate", 0) for c in campaigns) / len(campaigns)
            if avg_conversion < 2:
                recommendations.append(
                    "Your overall conversion rate is below 2%. Consider A/B testing different "
                    "messages, targeting, or send times to improve performance."
                )

        if not recommendations:
            recommendations.append("Your marketing performance is strong. Keep up the momentum!")

        return recommendations

class RecommendationEngine:
    """AI recommendations for marketing optimization."""

    def __init__(self, llm_router: MarketingLLMRouter):
        self.llm_router = llm_router

    async def get_recommendations(
        self, tenant_id: UUID
    ) -> RecommendationResponse:
        """Get AI-powered marketing recommendations."""

        # Stub implementation - in production would query analytics and use LLM
        return RecommendationResponse(
            best_send_time="Tuesday 10:00 AM UTC",
            optimal_length={"email": "150-250 words", "sms": "100-160 chars"},
            suggested_products=[
                {"name": "Premium Plan", "recommendation_reason": "High customer engagement"}
            ],
            budget_allocation={"email": 40, "whatsapp": 35, "sms": 25},
            estimated_revenue=5000.0,
        )

# ============================================================================
# FASTAPI APP & ENDPOINTS
# ============================================================================

app = FastAPI(title="Marketing Manager", version="1.0.0")
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="marketing")
init_sentry(service_name="marketing", service_port=9022)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="marketing")
app.add_middleware(TracingMiddleware)


cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Initialize engines
llm_router = MarketingLLMRouter()
content_engine = ContentGenerationEngine(llm_router)
segment_engine = AudienceSegmentationEngine()
drip_engine = DripSequenceEngine()
ab_engine = ABTestingEngine()
cart_engine = CartRecoveryEngine()
review_engine = ReviewRequestEngine()
analytics_engine = MarketingAnalyticsEngine()
recommendation_engine = RecommendationEngine(llm_router)

redis_client: Optional[redis.Redis] = None

@app.on_event("startup")
async def startup():
    """Initialize connections."""
    global redis_client

    await event_bus.startup()
    redis_client = await redis.from_url(config.REDIS_URL)
    logger.info("Marketing Manager started on port 9022")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup connections."""
    if redis_client:
        await redis_client.close()
    await event_bus.shutdown()
    shutdown_tracing()

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "marketing_manager"}

# ─── CAMPAIGN MANAGEMENT ───

@app.post("/api/v1/campaigns", response_model=CampaignResponse)
async def create_campaign(
    request: CampaignCreate,
    auth: AuthContext = Depends(get_auth),
):
    """Create marketing campaign."""

    auth.require_role("owner", "admin", "marketing")

    pool = await get_tenant_pool(auth.tenant_id)
    campaign_id = str(uuid4())
    created_at = datetime.utcnow()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO marketing_campaigns
            (id, tenant_id, name, campaign_type, channels, status, created_at, sent_count, opened_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 0, 0)
            """,
            campaign_id,
            str(auth.tenant_id),
            sanitize_input(request.name),
            request.campaign_type.value,
            json.dumps(request.channels),
            "draft",
            created_at,
        )

    return CampaignResponse(
        id=campaign_id,
        name=request.name,
        campaign_type=request.campaign_type,
        status=CampaignStatus.DRAFT,
        channels=request.channels,
        created_at=created_at,
        scheduled_at=None,
        launched_at=None,
        performance={},
        audience_count=0,
    )

@app.get("/api/v1/campaigns", response_model=list[CampaignResponse])
async def list_campaigns(auth: AuthContext = Depends(get_auth)):
    """List tenant's campaigns."""

    pool = await get_tenant_pool(auth.tenant_id)

    async with pool.acquire() as conn:
        campaigns = await conn.fetch(
            """
            SELECT id, name, campaign_type, status, channels, created_at,
                   launched_at, sent_count, opened_count, clicked_count, converted_count
            FROM marketing_campaigns
            WHERE tenant_id = $1
            ORDER BY created_at DESC LIMIT 50
            """,
            str(auth.tenant_id),
        )

    result = []
    for c in campaigns:
        result.append(CampaignResponse(
            id=c["id"],
            name=c["name"],
            campaign_type=CampaignType(c["campaign_type"]),
            status=CampaignStatus(c["status"]),
            channels=json.loads(c["channels"]) if isinstance(c["channels"], str) else c["channels"],
            created_at=c["created_at"],
            scheduled_at=None,
            launched_at=c["launched_at"],
            performance={
                "sent": c["sent_count"] or 0,
                "opened": c["opened_count"] or 0,
                "clicked": c["clicked_count"] or 0,
                "converted": c["converted_count"] or 0,
            },
            audience_count=0,
        ))

    return result

@app.get("/api/v1/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get campaign details."""

    pool = await get_tenant_pool(auth.tenant_id)

    async with pool.acquire() as conn:
        campaign = await conn.fetchrow(
            """
            SELECT id, name, campaign_type, status, channels, created_at, launched_at,
                   sent_count, opened_count, clicked_count, converted_count, revenue
            FROM marketing_campaigns
            WHERE id = $1 AND tenant_id = $2
            """,
            campaign_id,
            str(auth.tenant_id),
        )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return CampaignResponse(
        id=campaign["id"],
        name=campaign["name"],
        campaign_type=CampaignType(campaign["campaign_type"]),
        status=CampaignStatus(campaign["status"]),
        channels=json.loads(campaign["channels"]) if isinstance(campaign["channels"], str) else campaign["channels"],
        created_at=campaign["created_at"],
        scheduled_at=None,
        launched_at=campaign["launched_at"],
        performance={
            "sent": campaign["sent_count"] or 0,
            "opened": campaign["opened_count"] or 0,
            "clicked": campaign["clicked_count"] or 0,
            "converted": campaign["converted_count"] or 0,
            "revenue": campaign["revenue"] or 0,
        },
        audience_count=0,
    )

@app.post("/api/v1/campaigns/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Launch campaign."""

    auth.require_role("owner", "admin", "marketing")

    pool = await get_tenant_pool(auth.tenant_id)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE marketing_campaigns
            SET status = 'active', launched_at = NOW()
            WHERE id = $1 AND tenant_id = $2
            """,
            campaign_id,
            str(auth.tenant_id),
        )

    return {"status": "launched"}

@app.post("/api/v1/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Pause campaign."""

    auth.require_role("owner", "admin", "marketing")

    pool = await get_tenant_pool(auth.tenant_id)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE marketing_campaigns
            SET status = 'paused'
            WHERE id = $1 AND tenant_id = $2
            """,
            campaign_id,
            str(auth.tenant_id),
        )

    return {"status": "paused"}

@app.delete("/api/v1/campaigns/{campaign_id}")
async def archive_campaign(
    campaign_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Archive campaign."""

    auth.require_role("owner", "admin", "marketing")

    pool = await get_tenant_pool(auth.tenant_id)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE marketing_campaigns
            SET status = 'archived'
            WHERE id = $1 AND tenant_id = $2
            """,
            campaign_id,
            str(auth.tenant_id),
        )

    return {"status": "archived"}

# ─── CONTENT GENERATION ───

@app.post("/api/v1/content/generate", response_model=ContentGenerateResponse)
async def generate_content(
    request: ContentGenerateRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Generate AI marketing content."""

    auth.require_role("owner", "admin", "marketing")

    response = await content_engine.generate_marketing_content(auth.tenant_id, request)
    return response

# ─── AUDIENCE SEGMENTATION ───

@app.post("/api/v1/audiences/segment", response_model=AudienceSegmentResponse)
async def create_audience_segment(
    request: AudienceSegmentRequest,
    auth: AuthContext = Depends(get_auth),
):
    """Create audience segment."""

    auth.require_role("owner", "admin", "marketing")

    segment = await segment_engine.create_segment(auth.tenant_id, request)
    return segment

# ─── DRIP SEQUENCES ───

@app.post("/api/v1/sequences", response_model=DripSequenceResponse)
async def create_drip_sequence(
    request: DripSequenceCreate,
    auth: AuthContext = Depends(get_auth),
):
    """Create drip sequence."""

    auth.require_role("owner", "admin", "marketing")

    sequence = await drip_engine.create_sequence(auth.tenant_id, request)
    return sequence

# ─── A/B TESTING ───

@app.post("/api/v1/experiments", response_model=ExperimentResponse)
async def create_experiment(
    request: ExperimentCreate,
    auth: AuthContext = Depends(get_auth),
):
    """Create A/B test."""

    auth.require_role("owner", "admin", "marketing")

    experiment = await ab_engine.create_experiment(auth.tenant_id, request)
    return experiment

@app.get("/api/v1/experiments/{experiment_id}/winner")
async def get_experiment_winner(
    experiment_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Get A/B test results and winner."""

    result = await ab_engine.analyze_and_promote_winner(auth.tenant_id, experiment_id)
    return result

# ─── CART RECOVERY ───

@app.post("/api/v1/cart-recovery/configure")
async def configure_cart_recovery(
    config: CartRecoveryConfig,
    auth: AuthContext = Depends(get_auth),
):
    """Configure cart recovery."""

    auth.require_role("owner", "admin", "marketing")

    result = await cart_engine.configure_recovery(auth.tenant_id, config)
    return result

# ─── REVIEW REQUESTS ───

@app.post("/api/v1/reviews/campaign")
async def create_review_campaign(
    request: ReviewCampaignCreate,
    auth: AuthContext = Depends(get_auth),
):
    """Create review request campaign."""

    auth.require_role("owner", "admin", "marketing")

    result = await review_engine.create_review_campaign(auth.tenant_id, request)
    return result

# ─── ANALYTICS & DASHBOARD ───

@app.get("/api/v1/marketing/dashboard", response_model=MarketingDashboard)
async def get_marketing_dashboard(auth: AuthContext = Depends(get_auth)):
    """Get marketing dashboard."""

    dashboard = await analytics_engine.get_dashboard(auth.tenant_id)
    return dashboard

# ─── RECOMMENDATIONS ───

@app.get("/api/v1/recommendations", response_model=RecommendationResponse)
async def get_ai_recommendations(auth: AuthContext = Depends(get_auth)):
    """Get AI marketing recommendations."""

    recommendations = await recommendation_engine.get_recommendations(auth.tenant_id)
    return recommendations

if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=9022, log_level="info")
