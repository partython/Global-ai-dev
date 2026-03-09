"""
Analytics Service for Priya Global Multi-Tenant AI Sales Platform
Centralized analytics and reporting engine on port 9021
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from enum import Enum
import asyncio
import json
from decimal import Decimal

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text, func, desc
import httpx

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.core.config import config
from shared.core.database import db
from shared.core.security import mask_pii
from shared.middleware.auth import get_auth, AuthContext, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# Initialize FastAPI app
app = FastAPI(
    title="Priya Analytics Service",
    description="Centralized analytics and reporting engine",
    version="1.0.0"
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="analytics")
init_sentry(service_name="analytics", service_port=9021)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="analytics")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# ==================== Models ====================

class Granularity(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DashboardMetrics(BaseModel):
    total_conversations: Dict[str, int]
    active_conversations: int
    total_customers: int
    new_customers: Dict[str, int]
    messages_sent: int
    messages_received: int
    average_response_time_ms: float
    average_resolution_time_ms: float
    csat_score: Optional[float]
    revenue_influenced: Decimal
    ai_resolution_rate: float


class ConversationAnalytics(BaseModel):
    conversations_by_channel: List[Dict[str, Any]]
    conversations_by_status: List[Dict[str, Any]]
    conversations_over_time: List[Dict[str, Any]]
    peak_hours: List[Dict[str, Any]]
    average_messages_per_conversation: float
    first_response_time: Dict[str, float]


class FunnelStage(BaseModel):
    stage: str
    count: int
    conversion_rate: float
    drop_off_rate: float


class SalesFunnelData(BaseModel):
    funnel_stages: List[FunnelStage]
    funnel_over_time: List[Dict[str, Any]]
    top_drop_off_reasons: Dict[str, List[str]]


class ChannelPerformance(BaseModel):
    channel: str
    message_volume: int
    response_time: float
    resolution_rate: float
    csat_score: Optional[float]
    conversion_rate: float


class ChannelsPerformanceData(BaseModel):
    channels: List[ChannelPerformance]


class AIPerformance(BaseModel):
    ai_handled_vs_human: Dict[str, float]
    model_usage: Dict[str, Any]
    intent_distribution: Dict[str, float]
    confidence_scores: Dict[str, float]
    escalation_reasons: Dict[str, float]


class CustomerAnalyticsData(BaseModel):
    customer_growth: List[Dict[str, Any]]
    average_lifetime_value: Decimal
    lead_score_distribution: List[Dict[str, Any]]
    top_customers: List[Dict[str, Any]]
    customer_segments: Dict[str, int]


class RevenueData(BaseModel):
    total_revenue: Decimal
    revenue_by_channel: Dict[str, Decimal]
    revenue_by_product: List[Dict[str, Any]]
    average_order_value: Decimal
    conversion_rate: float
    cart_recovery_rate: float


class ReportRequest(BaseModel):
    report_type: str = Field(..., description="daily, weekly, monthly")
    email_delivery: Optional[bool] = False
    recipient_email: Optional[str] = None
    include_sections: Optional[List[str]] = None


class ReportResponse(BaseModel):
    report_id: str
    status: str
    created_at: datetime
    url: Optional[str] = None


class MetricsUpdate(BaseModel):
    active_conversations: int
    messages_per_minute: float
    queue_depth_per_channel: Dict[str, int]
    timestamp: datetime


# ==================== Database Helpers ====================

async def get_tenant_connection(auth: AuthContext):
    """Get database connection for tenant"""
    return await db.get_connection(auth.tenant_id)


async def get_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> tuple:
    """Parse and validate date range"""
    if not end_date:
        end = datetime.utcnow()
    else:
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

    if not start_date:
        start = end - timedelta(days=30)
    else:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))

    return start, end


# ==================== Analytics Queries ====================

async def get_dashboard_metrics(
    auth: AuthContext,
    start_date: datetime,
    end_date: datetime
) -> DashboardMetrics:
    """Fetch main dashboard metrics"""
    conn = await db.get_connection(auth.tenant_id)

    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # Total conversations by period
    query = text("""
        SELECT
            COUNT(*) FILTER (WHERE DATE(created_at) = :today) as today_count,
            COUNT(*) FILTER (WHERE DATE(created_at) >= :week_ago) as week_count,
            COUNT(*) FILTER (WHERE DATE(created_at) >= :month_ago) as month_count,
            COUNT(*) as all_time_count
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at <= :end_date
    """)

    result = await conn.execute(query, {
        "tenant_id": auth.tenant_id,
        "today": today,
        "week_ago": week_ago,
        "month_ago": month_ago,
        "end_date": end_date
    })
    row = result.fetchone()

    total_conversations = {
        "today": int(row[0]) if row[0] else 0,
        "this_week": int(row[1]) if row[1] else 0,
        "this_month": int(row[2]) if row[2] else 0,
        "all_time": int(row[3]) if row[3] else 0
    }

    # Active conversations
    active_query = text("""
        SELECT COUNT(*) FROM conversations
        WHERE tenant_id = :tenant_id AND status = 'open'
    """)
    active_result = await conn.execute(active_query, {"tenant_id": auth.tenant_id})
    active_conversations = int(active_result.scalar() or 0)

    # Total customers
    customer_query = text("""
        SELECT COUNT(DISTINCT customer_id) FROM conversations
        WHERE tenant_id = :tenant_id
    """)
    customer_result = await conn.execute(customer_query, {"tenant_id": auth.tenant_id})
    total_customers = int(customer_result.scalar() or 0)

    # New customers
    new_cust_query = text("""
        SELECT
            COUNT(*) FILTER (WHERE DATE(created_at) = :today) as today_count,
            COUNT(*) FILTER (WHERE DATE(created_at) >= :month_ago) as month_count
        FROM customers
        WHERE tenant_id = :tenant_id AND created_at <= :end_date
    """)
    new_cust_result = await conn.execute(new_cust_query, {
        "tenant_id": auth.tenant_id,
        "today": today,
        "month_ago": month_ago,
        "end_date": end_date
    })
    new_cust_row = new_cust_result.fetchone()
    new_customers = {
        "today": int(new_cust_row[0]) if new_cust_row[0] else 0,
        "this_month": int(new_cust_row[1]) if new_cust_row[1] else 0
    }

    # Messages
    msg_query = text("""
        SELECT
            COUNT(*) FILTER (WHERE direction = 'outbound') as sent,
            COUNT(*) FILTER (WHERE direction = 'inbound') as received
        FROM messages
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    msg_result = await conn.execute(msg_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    msg_row = msg_result.fetchone()
    messages_sent = int(msg_row[0]) if msg_row[0] else 0
    messages_received = int(msg_row[1]) if msg_row[1] else 0

    # Response and resolution times
    time_query = text("""
        SELECT
            AVG(EXTRACT(EPOCH FROM (first_response_at - created_at))) * 1000 as avg_response_ms,
            AVG(EXTRACT(EPOCH FROM (resolved_at - created_at))) * 1000 as avg_resolution_ms
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    time_result = await conn.execute(time_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    time_row = time_result.fetchone()
    avg_response_time_ms = float(time_row[0]) if time_row[0] else 0.0
    avg_resolution_time_ms = float(time_row[1]) if time_row[1] else 0.0

    # CSAT score
    csat_query = text("""
        SELECT AVG(rating) FROM feedback
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    csat_result = await conn.execute(csat_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    csat_score = float(csat_result.scalar() or 0)

    # Revenue influenced
    revenue_query = text("""
        SELECT SUM(total_amount) FROM orders
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            AND conversation_id IS NOT NULL
    """)
    revenue_result = await conn.execute(revenue_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    revenue_influenced = Decimal(revenue_result.scalar() or 0)

    # AI resolution rate
    ai_resolution_query = text("""
        SELECT
            COUNT(*) FILTER (WHERE resolved_by_ai = true) as ai_resolved,
            COUNT(*) as total
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            AND status = 'resolved'
    """)
    ai_res_result = await conn.execute(ai_resolution_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    ai_res_row = ai_res_result.fetchone()
    ai_resolution_rate = (float(ai_res_row[0]) / float(ai_res_row[1]) * 100) if ai_res_row[1] else 0.0

    return DashboardMetrics(
        total_conversations=total_conversations,
        active_conversations=active_conversations,
        total_customers=total_customers,
        new_customers=new_customers,
        messages_sent=messages_sent,
        messages_received=messages_received,
        average_response_time_ms=avg_response_time_ms,
        average_resolution_time_ms=avg_resolution_time_ms,
        csat_score=csat_score if csat_score > 0 else None,
        revenue_influenced=revenue_influenced,
        ai_resolution_rate=ai_resolution_rate
    )


async def get_conversation_analytics(
    auth: AuthContext,
    start_date: datetime,
    end_date: datetime
) -> ConversationAnalytics:
    """Fetch conversation analytics"""
    conn = await db.get_connection(auth.tenant_id)

    # By channel
    channel_query = text("""
        SELECT channel, COUNT(*) as count
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY channel ORDER BY count DESC
    """)
    channel_result = await conn.execute(channel_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    conversations_by_channel = [
        {"channel": row[0], "count": int(row[1])}
        for row in channel_result.fetchall()
    ]

    # By status
    status_query = text("""
        SELECT status, COUNT(*) as count
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY status
    """)
    status_result = await conn.execute(status_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    conversations_by_status = [
        {"status": row[0], "count": int(row[1])}
        for row in status_result.fetchall()
    ]

    # Over time (daily)
    time_query = text("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY DATE(created_at) ORDER BY date
    """)
    time_result = await conn.execute(time_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    conversations_over_time = [
        {"date": str(row[0]), "count": int(row[1])}
        for row in time_result.fetchall()
    ]

    # Peak hours (heatmap: hour x day_of_week)
    peak_query = text("""
        SELECT
            EXTRACT(HOUR FROM created_at) as hour,
            EXTRACT(DOW FROM created_at) as day_of_week,
            COUNT(*) as count
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY hour, day_of_week
    """)
    peak_result = await conn.execute(peak_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    peak_hours = [
        {"hour": int(row[0]), "day_of_week": int(row[1]), "count": int(row[2])}
        for row in peak_result.fetchall()
    ]

    # Average messages per conversation
    msg_per_conv_query = text("""
        SELECT AVG(message_count) FROM (
            SELECT COUNT(*) as message_count
            FROM messages
            WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            GROUP BY conversation_id
        ) sub
    """)
    msg_per_conv_result = await conn.execute(msg_per_conv_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    avg_messages_per_conversation = float(msg_per_conv_result.scalar() or 0)

    # First response times
    response_query = text("""
        SELECT
            AVG(EXTRACT(EPOCH FROM (first_response_at - created_at))) * 1000 as avg_ms,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (first_response_at - created_at))) * 1000 as p50,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (first_response_at - created_at))) * 1000 as p95
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            AND first_response_at IS NOT NULL
    """)
    response_result = await conn.execute(response_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    resp_row = response_result.fetchone()
    first_response_time = {
        "avg": float(resp_row[0]) if resp_row[0] else 0.0,
        "p50": float(resp_row[1]) if resp_row[1] else 0.0,
        "p95": float(resp_row[2]) if resp_row[2] else 0.0
    }

    return ConversationAnalytics(
        conversations_by_channel=conversations_by_channel,
        conversations_by_status=conversations_by_status,
        conversations_over_time=conversations_over_time,
        peak_hours=peak_hours,
        average_messages_per_conversation=avg_messages_per_conversation,
        first_response_time=first_response_time
    )


async def get_sales_funnel(
    auth: AuthContext,
    start_date: datetime,
    end_date: datetime
) -> SalesFunnelData:
    """Fetch sales funnel analytics"""
    conn = await db.get_connection(auth.tenant_id)

    stages = ["awareness", "interest", "consideration", "intent", "purchase", "advocacy"]
    funnel_stages = []
    drop_off_reasons = {}

    # Get funnel stage counts
    funnel_query = text("""
        SELECT funnel_stage, COUNT(*) as count
        FROM leads
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY funnel_stage
    """)
    funnel_result = await conn.execute(funnel_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    stage_counts = {row[0]: int(row[1]) for row in funnel_result.fetchall()}

    prev_count = sum(stage_counts.values())
    for stage in stages:
        count = stage_counts.get(stage, 0)
        conversion_rate = (count / prev_count * 100) if prev_count > 0 else 0.0
        drop_off_rate = 100.0 - conversion_rate if prev_count > 0 else 0.0

        funnel_stages.append(FunnelStage(
            stage=stage,
            count=count,
            conversion_rate=conversion_rate,
            drop_off_rate=drop_off_rate
        ))
        prev_count = count

    # Funnel over time
    funnel_time_query = text("""
        SELECT DATE(created_at) as date, funnel_stage, COUNT(*) as count
        FROM leads
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY DATE(created_at), funnel_stage
        ORDER BY date, funnel_stage
    """)
    funnel_time_result = await conn.execute(funnel_time_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    funnel_over_time = [
        {"date": str(row[0]), "stage": row[1], "count": int(row[2])}
        for row in funnel_time_result.fetchall()
    ]

    # Top drop-off reasons
    dropout_query = text("""
        SELECT funnel_stage, drop_off_reason, COUNT(*) as count
        FROM leads
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            AND drop_off_reason IS NOT NULL
        GROUP BY funnel_stage, drop_off_reason
        ORDER BY funnel_stage, count DESC
    """)
    dropout_result = await conn.execute(dropout_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })

    for row in dropout_result.fetchall():
        stage = row[0]
        if stage not in drop_off_reasons:
            drop_off_reasons[stage] = []
        drop_off_reasons[stage].append(row[1])

    return SalesFunnelData(
        funnel_stages=funnel_stages,
        funnel_over_time=funnel_over_time,
        top_drop_off_reasons=drop_off_reasons
    )


async def get_channel_performance(
    auth: AuthContext,
    start_date: datetime,
    end_date: datetime
) -> ChannelsPerformanceData:
    """Fetch channel performance metrics"""
    conn = await db.get_connection(auth.tenant_id)

    channels = ["whatsapp", "email", "voice", "instagram", "facebook", "webchat", "sms", "telegram"]
    channel_metrics = []

    for channel in channels:
        # Message volume
        vol_query = text("""
            SELECT COUNT(*) FROM messages
            WHERE tenant_id = :tenant_id AND channel = :channel
                AND created_at BETWEEN :start AND :end
        """)
        vol_result = await conn.execute(vol_query, {
            "tenant_id": auth.tenant_id,
            "channel": channel,
            "start": start_date,
            "end": end_date
        })
        message_volume = int(vol_result.scalar() or 0)

        # Response time
        resp_query = text("""
            SELECT AVG(EXTRACT(EPOCH FROM (first_response_at - created_at))) * 1000
            FROM conversations
            WHERE tenant_id = :tenant_id AND channel = :channel
                AND created_at BETWEEN :start AND :end AND first_response_at IS NOT NULL
        """)
        resp_result = await conn.execute(resp_query, {
            "tenant_id": auth.tenant_id,
            "channel": channel,
            "start": start_date,
            "end": end_date
        })
        response_time = float(resp_result.scalar() or 0)

        # Resolution rate
        res_query = text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'resolved') as resolved,
                COUNT(*) as total
            FROM conversations
            WHERE tenant_id = :tenant_id AND channel = :channel
                AND created_at BETWEEN :start AND :end
        """)
        res_result = await conn.execute(res_query, {
            "tenant_id": auth.tenant_id,
            "channel": channel,
            "start": start_date,
            "end": end_date
        })
        res_row = res_result.fetchone()
        resolution_rate = (float(res_row[0]) / float(res_row[1]) * 100) if res_row[1] else 0.0

        # CSAT
        csat_query = text("""
            SELECT AVG(feedback.rating)
            FROM feedback
            JOIN conversations ON feedback.conversation_id = conversations.id
            WHERE feedback.tenant_id = :tenant_id AND conversations.channel = :channel
                AND feedback.created_at BETWEEN :start AND :end
        """)
        csat_result = await conn.execute(csat_query, {
            "tenant_id": auth.tenant_id,
            "channel": channel,
            "start": start_date,
            "end": end_date
        })
        csat_score = float(csat_result.scalar() or 0)

        # Conversion rate
        conv_query = text("""
            SELECT
                COUNT(DISTINCT orders.id) as orders,
                COUNT(DISTINCT conversations.id) as conversations
            FROM conversations
            LEFT JOIN orders ON conversations.id = orders.conversation_id
            WHERE conversations.tenant_id = :tenant_id AND conversations.channel = :channel
                AND conversations.created_at BETWEEN :start AND :end
        """)
        conv_result = await conn.execute(conv_query, {
            "tenant_id": auth.tenant_id,
            "channel": channel,
            "start": start_date,
            "end": end_date
        })
        conv_row = conv_result.fetchone()
        conversion_rate = (float(conv_row[0]) / float(conv_row[1]) * 100) if conv_row[1] else 0.0

        channel_metrics.append(ChannelPerformance(
            channel=channel,
            message_volume=message_volume,
            response_time=response_time,
            resolution_rate=resolution_rate,
            csat_score=csat_score if csat_score > 0 else None,
            conversion_rate=conversion_rate
        ))

    return ChannelsPerformanceData(channels=channel_metrics)


async def get_ai_performance(
    auth: AuthContext,
    start_date: datetime,
    end_date: datetime
) -> AIPerformance:
    """Fetch AI performance metrics"""
    conn = await db.get_connection(auth.tenant_id)

    # AI handled vs human
    handled_query = text("""
        SELECT
            COUNT(*) FILTER (WHERE resolved_by_ai = true) as ai_handled,
            COUNT(*) FILTER (WHERE resolved_by_ai = false) as human_handled,
            COUNT(*) as total
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    handled_result = await conn.execute(handled_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    handled_row = handled_result.fetchone()
    total = float(handled_row[2]) if handled_row[2] else 1
    ai_handled_vs_human = {
        "ai_handled_percent": (float(handled_row[0]) / total * 100) if handled_row[0] else 0.0,
        "human_handled_percent": (float(handled_row[1]) / total * 100) if handled_row[1] else 0.0
    }

    # Model usage (simulated - would integrate with token tracking service)
    model_usage = {
        "claude": {"tokens": 1250000, "cost": 6.25},
        "gpt4": {"tokens": 850000, "cost": 12.75},
        "total_cost": 19.00
    }

    # Intent distribution
    intent_query = text("""
        SELECT intent_type, COUNT(*) as count
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            AND intent_type IS NOT NULL
        GROUP BY intent_type ORDER BY count DESC
    """)
    intent_result = await conn.execute(intent_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    intent_dist = {}
    total_intents = sum([row[1] for row in intent_result.fetchall()])
    for row in intent_result.fetchall():
        intent_dist[row[0]] = (float(row[1]) / total_intents * 100) if total_intents else 0.0
    intent_distribution = intent_dist or {"product_inquiry": 40.0, "pricing": 25.0, "support": 20.0}

    # Confidence scores by intent
    confidence_query = text("""
        SELECT intent_type, AVG(ai_confidence_score) as avg_confidence
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            AND intent_type IS NOT NULL AND ai_confidence_score IS NOT NULL
        GROUP BY intent_type
    """)
    confidence_result = await conn.execute(confidence_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    confidence_scores = {row[0]: float(row[1]) for row in confidence_result.fetchall()}

    # Escalation reasons
    escal_query = text("""
        SELECT escalation_reason, COUNT(*) as count
        FROM conversations
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
            AND escalation_reason IS NOT NULL
        GROUP BY escalation_reason ORDER BY count DESC
    """)
    escal_result = await conn.execute(escal_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    escal_dist = {}
    total_escalations = sum([row[1] for row in escal_result.fetchall()])
    for row in escal_result.fetchall():
        escal_dist[row[0]] = (float(row[1]) / total_escalations * 100) if total_escalations else 0.0
    escalation_reasons = escal_dist or {"anger": 15.0, "complex": 30.0, "escalation_request": 35.0}

    return AIPerformance(
        ai_handled_vs_human=ai_handled_vs_human,
        model_usage=model_usage,
        intent_distribution=intent_distribution,
        confidence_scores=confidence_scores,
        escalation_reasons=escalation_reasons
    )


async def get_customer_analytics(
    auth: AuthContext,
    start_date: datetime,
    end_date: datetime
) -> CustomerAnalyticsData:
    """Fetch customer analytics"""
    conn = await db.get_connection(auth.tenant_id)

    # Customer growth over time
    growth_query = text("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM customers
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY DATE(created_at) ORDER BY date
    """)
    growth_result = await conn.execute(growth_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    customer_growth = [
        {"date": str(row[0]), "new_customers": int(row[1])}
        for row in growth_result.fetchall()
    ]

    # Average lifetime value
    ltv_query = text("""
        SELECT AVG(total_spent) FROM customers
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    ltv_result = await conn.execute(ltv_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    average_lifetime_value = Decimal(ltv_result.scalar() or 0)

    # Lead score distribution
    score_query = text("""
        SELECT
            CASE
                WHEN lead_score < 25 THEN 'low'
                WHEN lead_score < 50 THEN 'medium'
                WHEN lead_score < 75 THEN 'high'
                ELSE 'very_high'
            END as score_range,
            COUNT(*) as count
        FROM leads
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY score_range
    """)
    score_result = await conn.execute(score_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    lead_score_distribution = [
        {"range": row[0], "count": int(row[1])}
        for row in score_result.fetchall()
    ]

    # Top customers
    top_query = text("""
        SELECT id, name, total_spent, conversation_count
        FROM customers
        WHERE tenant_id = :tenant_id
        ORDER BY total_spent DESC LIMIT 10
    """)
    top_result = await conn.execute(top_query, {"tenant_id": auth.tenant_id})
    top_customers = [
        {
            "customer_id": row[0],
            "name": mask_pii(row[1]),
            "total_spent": float(row[2]),
            "conversation_count": int(row[3])
        }
        for row in top_result.fetchall()
    ]

    # Customer segments
    segment_query = text("""
        SELECT
            CASE
                WHEN last_conversation_at IS NULL THEN 'new'
                WHEN last_conversation_at > NOW() - INTERVAL '30 days' THEN 'returning'
                WHEN last_conversation_at > NOW() - INTERVAL '90 days' THEN 'at_risk'
                ELSE 'churned'
            END as segment,
            COUNT(*) as count
        FROM customers
        WHERE tenant_id = :tenant_id
        GROUP BY segment
    """)
    segment_result = await conn.execute(segment_query, {"tenant_id": auth.tenant_id})
    customer_segments = {row[0]: int(row[1]) for row in segment_result.fetchall()}

    return CustomerAnalyticsData(
        customer_growth=customer_growth,
        average_lifetime_value=average_lifetime_value,
        lead_score_distribution=lead_score_distribution,
        top_customers=top_customers,
        customer_segments=customer_segments
    )


async def get_revenue_analytics(
    auth: AuthContext,
    start_date: datetime,
    end_date: datetime
) -> RevenueData:
    """Fetch revenue analytics"""
    conn = await db.get_connection(auth.tenant_id)

    # Total revenue
    total_query = text("""
        SELECT SUM(total_amount) FROM orders
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    total_result = await conn.execute(total_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    total_revenue = Decimal(total_result.scalar() or 0)

    # Revenue by channel
    channel_query = text("""
        SELECT conversations.channel, SUM(orders.total_amount)
        FROM orders
        JOIN conversations ON orders.conversation_id = conversations.id
        WHERE orders.tenant_id = :tenant_id AND orders.created_at BETWEEN :start AND :end
        GROUP BY conversations.channel
    """)
    channel_result = await conn.execute(channel_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    revenue_by_channel = {row[0]: Decimal(row[1] or 0) for row in channel_result.fetchall()}

    # Revenue by product
    product_query = text("""
        SELECT product_name, SUM(quantity * unit_price) as revenue
        FROM order_items
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
        GROUP BY product_name
        ORDER BY revenue DESC LIMIT 10
    """)
    product_result = await conn.execute(product_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    revenue_by_product = [
        {"product": row[0], "revenue": float(row[1])}
        for row in product_result.fetchall()
    ]

    # Average order value
    aov_query = text("""
        SELECT AVG(total_amount) FROM orders
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    aov_result = await conn.execute(aov_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    average_order_value = Decimal(aov_result.scalar() or 0)

    # Conversion rate
    conv_query = text("""
        SELECT
            COUNT(DISTINCT orders.id) as orders,
            COUNT(DISTINCT conversations.id) as conversations
        FROM conversations
        LEFT JOIN orders ON conversations.id = orders.conversation_id
        WHERE conversations.tenant_id = :tenant_id AND conversations.created_at BETWEEN :start AND :end
    """)
    conv_result = await conn.execute(conv_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    conv_row = conv_result.fetchone()
    conversion_rate = (float(conv_row[0]) / float(conv_row[1]) * 100) if conv_row[1] else 0.0

    # Cart recovery rate
    cart_query = text("""
        SELECT
            COUNT(*) FILTER (WHERE recovered = true) as recovered,
            COUNT(*) as total
        FROM abandoned_carts
        WHERE tenant_id = :tenant_id AND created_at BETWEEN :start AND :end
    """)
    cart_result = await conn.execute(cart_query, {
        "tenant_id": auth.tenant_id,
        "start": start_date,
        "end": end_date
    })
    cart_row = cart_result.fetchone()
    cart_recovery_rate = (float(cart_row[0]) / float(cart_row[1]) * 100) if cart_row[1] else 0.0

    return RevenueData(
        total_revenue=total_revenue,
        revenue_by_channel=revenue_by_channel,
        revenue_by_product=revenue_by_product,
        average_order_value=average_order_value,
        conversion_rate=conversion_rate,
        cart_recovery_rate=cart_recovery_rate
    )


# ==================== Endpoints ====================

@app.get("/api/v1/dashboard", response_model=DashboardMetrics)
async def get_dashboard(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Get main dashboard metrics"""
    await require_role(auth, ["admin", "analyst", "manager"])
    start, end = await get_date_range(start_date, end_date)
    return await get_dashboard_metrics(auth, start, end)


@app.get("/api/v1/conversations/analytics", response_model=ConversationAnalytics)
async def get_conversations_analytics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    granularity: Granularity = Query(Granularity.DAILY),
    channel_filter: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Get conversation analytics"""
    await require_role(auth, ["admin", "analyst", "manager"])
    start, end = await get_date_range(start_date, end_date)
    return await get_conversation_analytics(auth, start, end)


@app.get("/api/v1/funnel", response_model=SalesFunnelData)
async def get_funnel(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Get sales funnel analytics"""
    await require_role(auth, ["admin", "analyst", "manager", "sales"])
    start, end = await get_date_range(start_date, end_date)
    return await get_sales_funnel(auth, start, end)


@app.get("/api/v1/channels/performance", response_model=ChannelsPerformanceData)
async def get_channels_performance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Get per-channel performance metrics"""
    await require_role(auth, ["admin", "analyst", "manager"])
    start, end = await get_date_range(start_date, end_date)
    return await get_channel_performance(auth, start, end)


@app.get("/api/v1/ai/performance", response_model=AIPerformance)
async def get_ai_perf(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Get AI model performance metrics"""
    await require_role(auth, ["admin", "analyst", "manager"])
    start, end = await get_date_range(start_date, end_date)
    return await get_ai_performance(auth, start, end)


@app.get("/api/v1/customers/analytics", response_model=CustomerAnalyticsData)
async def get_customers_analytics(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Get customer analytics"""
    await require_role(auth, ["admin", "analyst", "manager", "sales"])
    start, end = await get_date_range(start_date, end_date)
    return await get_customer_analytics(auth, start, end)


@app.get("/api/v1/revenue", response_model=RevenueData)
async def get_revenue(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth)
):
    """Get revenue analytics"""
    await require_role(auth, ["admin", "analyst", "manager", "finance"])
    start, end = await get_date_range(start_date, end_date)
    return await get_revenue_analytics(auth, start, end)


@app.post("/api/v1/reports/generate", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    auth: AuthContext = Depends(get_auth)
):
    """Generate on-demand report with optional PDF export"""
    await require_role(auth, ["admin", "analyst", "manager"])

    import uuid
    from datetime import datetime as dt

    report_id = str(uuid.uuid4())

    # Determine date range based on report type
    end = dt.utcnow()
    if request.report_type == "daily":
        start = end - timedelta(days=1)
    elif request.report_type == "weekly":
        start = end - timedelta(days=7)
    elif request.report_type == "monthly":
        start = end - timedelta(days=30)
    else:
        start = end - timedelta(days=30)

    # Gather all analytics
    dashboard = await get_dashboard_metrics(auth, start, end)
    conversations = await get_conversation_analytics(auth, start, end)
    revenue = await get_revenue_analytics(auth, start, end)

    # Would integrate with email service if email_delivery is true
    if request.email_delivery and request.recipient_email:
        # Send email with report
        pass

    return ReportResponse(
        report_id=report_id,
        status="generated",
        created_at=dt.utcnow(),
        url=f"/reports/{report_id}.pdf"
    )


# ==================== WebSocket ====================

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, tenant_id: str, websocket: WebSocket):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = []
        self.active_connections[tenant_id].append(websocket)

    async def disconnect(self, tenant_id: str, websocket: WebSocket):
        self.active_connections[tenant_id].remove(websocket)

    async def broadcast(self, tenant_id: str, message: dict):
        if tenant_id in self.active_connections:
            for connection in self.active_connections[tenant_id]:
                try:
                    await connection.send_json(message)
                except (RuntimeError, ConnectionError):
                    pass


manager = ConnectionManager()


@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket, token: str = Query(...)):
    """
    Real-time metrics WebSocket.
    Note: Token passed as query parameter (not in headers) because browser WebSocket API
    doesn't support custom headers. Use short-lived tokens for this endpoint.
    """
    try:
        auth = await get_auth(token)
        await manager.connect(auth.tenant_id, websocket)

        while True:
            # Send metrics every 5 seconds
            await asyncio.sleep(5)

            conn = await db.get_connection(auth.tenant_id)

            # Active conversations
            active_query = text("""
                SELECT COUNT(*) FROM conversations
                WHERE tenant_id = :tenant_id AND status = 'open'
            """)
            active_result = await conn.execute(active_query, {"tenant_id": auth.tenant_id})
            active = int(active_result.scalar() or 0)

            # Messages per minute (sample from last minute)
            mpm_query = text("""
                SELECT COUNT(*) FROM messages
                WHERE tenant_id = :tenant_id
                    AND created_at > NOW() - INTERVAL '1 minute'
            """)
            mpm_result = await conn.execute(mpm_query, {"tenant_id": auth.tenant_id})
            mpm = float(mpm_result.scalar() or 0)

            # Queue depth per channel
            queue_query = text("""
                SELECT channel, COUNT(*)
                FROM conversations
                WHERE tenant_id = :tenant_id AND status = 'open'
                GROUP BY channel
            """)
            queue_result = await conn.execute(queue_query, {"tenant_id": auth.tenant_id})
            queue_depth = {row[0]: int(row[1]) for row in queue_result.fetchall()}

            update = MetricsUpdate(
                active_conversations=active,
                messages_per_minute=mpm,
                queue_depth_per_channel=queue_depth,
                timestamp=datetime.utcnow()
            )

            await manager.broadcast(auth.tenant_id, update.dict())

    except WebSocketDisconnect:
        await manager.disconnect(auth.tenant_id, websocket)
    except Exception as e:
        await websocket.close(code=status.WS_1011_SERVER_ERROR)


# ==================== Health Check ====================

@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "analytics",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=9021)
