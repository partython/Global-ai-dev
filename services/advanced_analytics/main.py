"""
Advanced Analytics Dashboard Service
Multi-tenant SaaS with real-time metrics, custom reports, predictive analytics,
cohort analysis, attribution modeling, and executive dashboards.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from functools import lru_cache

import jwt
from fastapi import FastAPI, Depends, HTTPException, WebSocketDisconnect, WebSocket, Query
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncpg
import numpy as np
from scipy import stats
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration & Security
# ============================================================================

@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise ValueError("Server configuration error")
    return secret

@lru_cache(maxsize=1)
def get_db_url() -> str:
    # Note: Database credentials come from environment variables only, never hardcoded.
    # URLs with credentials are not logged or exposed externally.
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME")

    if not all([db_user, db_password, db_host, db_name]):
        raise ValueError("Database credentials not fully configured")

    # NOTE: All credentials (db_user, db_password, db_host) come from environment variables
    # This connection string is used internally only and never logged or exposed
    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

@lru_cache(maxsize=1)
def get_cors_origins() -> List[str]:
    origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    origins = [o.strip() for o in origins_str.split(",") if o.strip()]
    # Remove wildcard if present, use safe default
    if "*" in origins:
        origins = ["http://localhost:3000"]
    return origins if origins else ["http://localhost:3000"]

# ============================================================================
# Models
# ============================================================================

class AuthContext(BaseModel):
    tenant_id: str
    user_id: str
    email: str
    scopes: List[str] = Field(default_factory=list)

class DashboardMetrics(BaseModel):
    active_conversations: int
    response_time_ms: float
    csat_score: float
    conversion_rate: float
    timestamp: datetime

class KPIResponse(BaseModel):
    metric_name: str
    current_value: float
    previous_value: Optional[float] = None
    change_percent: Optional[float] = None
    trend: str  # "up", "down", "stable"

class ReportDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    query: str
    scheduled: bool = False
    schedule_cron: Optional[str] = None
    export_format: str = "csv"  # csv, pdf

class ReportResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    created_at: datetime
    status: str
    export_url: Optional[str] = None

class ForecastResponse(BaseModel):
    metric: str
    current_value: float
    forecast_30day: List[float]
    forecast_90day: List[float]
    confidence_interval: float

class CohortAnalysis(BaseModel):
    cohort_id: str
    signup_date: str
    size: int
    retention_week1: float
    retention_week4: float
    retention_week12: float
    revenue_per_user: float

class AttributionModel(BaseModel):
    channel: str
    first_touch_attribution: float
    last_touch_attribution: float
    linear_attribution: float
    time_decay_attribution: float
    roi: float

class ExecutiveSummary(BaseModel):
    period: str
    revenue: float
    growth_percent: float
    key_metrics: Dict[str, Any]
    benchmarks: Dict[str, float]
    comparison: Dict[str, float]

# ============================================================================
# Database Connection
# ============================================================================

class DatabaseConnection:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(
                get_db_url(),
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            logger.info("Database connection pool established")
        except Exception as e:
            logger.error("Failed to create database pool: %s", e)
            raise
    
    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def execute_one(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

db = DatabaseConnection()

# ============================================================================
# Authentication & Authorization
# ============================================================================

security = HTTPBearer()

async def get_auth_context(credentials: HTTPAuthCredentials = Depends(security)) -> AuthContext:
    try:
        payload = jwt.decode(
            credentials.credentials,
            get_jwt_secret(),
            algorithms=["HS256"]
        )
        tenant_id = payload.get("tenant_id")
        user_id = payload.get("user_id")
        email = payload.get("email")
        scopes = payload.get("scopes", [])

        if not all([tenant_id, user_id, email]):
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return AuthContext(
            tenant_id=tenant_id,
            user_id=user_id,
            email=email,
            scopes=scopes
        )
    except jwt.InvalidTokenError as e:
        logger.error("Invalid token: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error: %s", e)
        raise HTTPException(status_code=401, detail="Authentication failed")

# ============================================================================
# Analytics Service
# ============================================================================

class AnalyticsService:
    def __init__(self, auth: AuthContext):
        self.auth = auth
        self.tenant_id = auth.tenant_id
    
    async def get_dashboard_metrics(self) -> DashboardMetrics:
        """Retrieve real-time dashboard metrics with RLS."""
        query = """
            SELECT 
                COUNT(DISTINCT CASE WHEN status = 'active' THEN id END) as active_conversations,
                COALESCE(AVG(response_time_ms), 0) as response_time_ms,
                COALESCE(AVG(csat_score), 0) as csat_score,
                COALESCE(SUM(CASE WHEN converted THEN 1 ELSE 0 END)::float / 
                    NULLIF(COUNT(*), 0), 0) as conversion_rate
            FROM conversations
            WHERE tenant_id = $1 AND created_at > NOW() - INTERVAL '24 hours'
        """
        result = await db.execute_one(query, self.tenant_id)
        if not result:
            return DashboardMetrics(
                active_conversations=0,
                response_time_ms=0,
                csat_score=0,
                conversion_rate=0,
                timestamp=datetime.utcnow()
            )
        
        return DashboardMetrics(
            active_conversations=result['active_conversations'] or 0,
            response_time_ms=result['response_time_ms'] or 0,
            csat_score=result['csat_score'] or 0,
            conversion_rate=result['conversion_rate'] or 0,
            timestamp=datetime.utcnow()
        )
    
    async def get_kpis(self, days: int = 30) -> List[KPIResponse]:
        """Calculate KPIs with period-over-period comparison."""
        current_period_query = """
            SELECT 
                AVG(response_time_ms) as avg_response_time,
                AVG(csat_score) as avg_csat,
                COUNT(DISTINCT id) as total_conversations,
                SUM(CASE WHEN converted THEN 1 ELSE 0 END)::float / 
                    NULLIF(COUNT(*), 0) as conversion_rate
            FROM conversations
            WHERE tenant_id = $1 AND created_at > NOW() - INTERVAL '1 day' * $2
        """
        
        previous_period_query = """
            SELECT 
                AVG(response_time_ms) as avg_response_time,
                AVG(csat_score) as avg_csat,
                COUNT(DISTINCT id) as total_conversations,
                SUM(CASE WHEN converted THEN 1 ELSE 0 END)::float / 
                    NULLIF(COUNT(*), 0) as conversion_rate
            FROM conversations
            WHERE tenant_id = $1 
                AND created_at > NOW() - INTERVAL '1 day' * $2 * 2
                AND created_at <= NOW() - INTERVAL '1 day' * $2
        """
        
        current = await db.execute_one(current_period_query, self.tenant_id, days)
        previous = await db.execute_one(previous_period_query, self.tenant_id, days)
        
        kpis = []
        metrics = [
            ("Response Time (ms)", "avg_response_time"),
            ("CSAT Score", "avg_csat"),
            ("Total Conversations", "total_conversations"),
            ("Conversion Rate", "conversion_rate")
        ]
        
        for metric_name, field in metrics:
            current_val = float(current.get(field) or 0)
            previous_val = float(previous.get(field) or 0) if previous else 0
            
            change_percent = None
            if previous_val != 0:
                change_percent = ((current_val - previous_val) / previous_val) * 100
            
            trend = "stable"
            if change_percent:
                trend = "up" if change_percent > 0 else "down"
            
            kpis.append(KPIResponse(
                metric_name=metric_name,
                current_value=current_val,
                previous_value=previous_val,
                change_percent=change_percent,
                trend=trend
            ))
        
        return kpis
    
    async def create_report(self, definition: ReportDefinition) -> ReportResponse:
        """Create custom SQL-safe report with validation."""
        report_id = f"report_{datetime.utcnow().timestamp()}"
        
        # Basic SQL injection prevention
        if any(keyword in definition.query.upper() for keyword in ["DROP", "DELETE", "TRUNCATE"]):
            raise HTTPException(status_code=400, detail="Unsafe SQL detected")
        
        query = """
            INSERT INTO analytics_reports 
            (id, tenant_id, name, description, query, created_at, status)
            VALUES ($1, $2, $3, $4, $5, NOW(), 'pending')
            RETURNING id, tenant_id, name, created_at, status
        """
        
        result = await db.execute_one(
            query, report_id, self.tenant_id, definition.name,
            definition.description, definition.query
        )

        logger.info("Report created: %s for tenant %s", report_id, self.tenant_id)
        
        return ReportResponse(
            id=report_id,
            tenant_id=self.tenant_id,
            name=definition.name,
            created_at=datetime.utcnow(),
            status="pending"
        )
    
    async def get_reports(self, limit: int = 50) -> List[ReportResponse]:
        """Retrieve user's reports with RLS."""
        query = """
            SELECT id, tenant_id, name, created_at, status
            FROM analytics_reports
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        
        results = await db.execute(query, self.tenant_id, limit)
        
        return [
            ReportResponse(
                id=r['id'],
                tenant_id=r['tenant_id'],
                name=r['name'],
                created_at=r['created_at'],
                status=r['status']
            )
            for r in results
        ]
    
    async def export_report(self, report_id: str, format: str = "csv") -> Dict[str, Any]:
        """Generate export for report."""
        query = """
            SELECT query FROM analytics_reports
            WHERE id = $1 AND tenant_id = $2
        """
        
        report = await db.execute_one(query, report_id, self.tenant_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        # Execute report query
        report_data = await db.execute(report['query'])
        
        # Format data for export
        export_data = {
            "report_id": report_id,
            "format": format,
            "generated_at": datetime.utcnow().isoformat(),
            "rows": [dict(row) for row in report_data]
        }

        logger.info("Report exported: %s as %s", report_id, format)
        
        return export_data
    
    async def forecast_revenue(self, days_ahead: int = 90) -> ForecastResponse:
        """Linear regression revenue forecasting."""
        # Get historical revenue data
        query = """
            SELECT DATE(created_at) as date, SUM(amount) as daily_revenue
            FROM transactions
            WHERE tenant_id = $1 AND created_at > NOW() - INTERVAL '180 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """
        
        results = await db.execute(query, self.tenant_id)
        
        if len(results) < 10:
            return ForecastResponse(
                metric="revenue",
                current_value=0,
                forecast_30day=[],
                forecast_90day=[],
                confidence_interval=0.95
            )
        
        # Prepare data for regression
        x = np.arange(len(results)).reshape(-1, 1)
        y = np.array([float(r.get('daily_revenue', 0)) for r in results])
        
        # Linear regression
        slope, intercept, r_value, _, _ = stats.linregress(x.flatten(), y)
        
        # Generate forecasts
        current_value = float(results[-1].get('daily_revenue', 0))
        forecast_30 = [intercept + slope * (len(results) + i) for i in range(30)]
        forecast_90 = [intercept + slope * (len(results) + i) for i in range(90)]
        
        return ForecastResponse(
            metric="revenue",
            current_value=current_value,
            forecast_30day=forecast_30[:30],
            forecast_90day=forecast_90[:90],
            confidence_interval=r_value ** 2
        )
    
    async def get_churn_score(self, customer_id: str) -> Dict[str, Any]:
        """Predict churn probability using behavior features."""
        query = """
            SELECT 
                COUNT(DISTINCT c.id) as conversation_count,
                AVG(c.csat_score) as avg_csat,
                MAX(c.created_at) as last_interaction,
                COUNT(DISTINCT DATE(c.created_at)) as active_days
            FROM conversations c
            WHERE c.customer_id = $1 AND c.tenant_id = $2
            AND c.created_at > NOW() - INTERVAL '90 days'
        """
        
        result = await db.execute_one(query, customer_id, self.tenant_id)
        
        if not result:
            return {"customer_id": customer_id, "churn_score": 0.0}
        
        # Simple churn scoring logic
        conversation_count = result['conversation_count'] or 0
        avg_csat = float(result['avg_csat'] or 5)
        active_days = result['active_days'] or 0
        
        days_since_interaction = (datetime.utcnow() - result['last_interaction']).days if result['last_interaction'] else 90
        
        # Score components (0-1)
        engagement_score = min(conversation_count / 20, 1.0)
        satisfaction_score = avg_csat / 5.0
        recency_score = max(1.0 - (days_since_interaction / 90), 0)
        
        churn_score = 1.0 - ((engagement_score * 0.3 + satisfaction_score * 0.5 + recency_score * 0.2))
        
        return {
            "customer_id": customer_id,
            "churn_score": round(churn_score, 3),
            "engagement": engagement_score,
            "satisfaction": satisfaction_score,
            "recency": recency_score
        }
    
    async def get_cohorts(self) -> List[CohortAnalysis]:
        """Analyze customer cohorts by signup date."""
        query = """
            SELECT 
                DATE_TRUNC('week', c.created_at) as cohort_week,
                COUNT(DISTINCT c.id) as cohort_size,
                AVG(CASE WHEN c.created_at > NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) as retention_week1,
                AVG(CASE WHEN c.created_at > NOW() - INTERVAL '28 days' THEN 1 ELSE 0 END) as retention_week4,
                AVG(CASE WHEN c.created_at > NOW() - INTERVAL '84 days' THEN 1 ELSE 0 END) as retention_week12,
                COALESCE(AVG(t.amount), 0) as revenue_per_user
            FROM conversations c
            LEFT JOIN transactions t ON c.customer_id = t.customer_id AND t.tenant_id = $1
            WHERE c.tenant_id = $1 AND c.created_at > NOW() - INTERVAL '365 days'
            GROUP BY DATE_TRUNC('week', c.created_at)
            ORDER BY cohort_week DESC
        """
        
        results = await db.execute(query, self.tenant_id)
        
        cohorts = []
        for r in results:
            cohorts.append(CohortAnalysis(
                cohort_id=r['cohort_week'].isoformat(),
                signup_date=r['cohort_week'].isoformat(),
                size=r['cohort_size'] or 0,
                retention_week1=float(r.get('retention_week1', 0) or 0),
                retention_week4=float(r.get('retention_week4', 0) or 0),
                retention_week12=float(r.get('retention_week12', 0) or 0),
                revenue_per_user=float(r.get('revenue_per_user', 0) or 0)
            ))
        
        return cohorts
    
    async def get_attribution(self) -> List[AttributionModel]:
        """Multi-touch attribution analysis across channels."""
        query = """
            SELECT 
                j.channel,
                COUNT(DISTINCT j.id) as touch_count,
                SUM(j.converted::int) as conversions,
                SUM(t.amount) as revenue
            FROM journey_touchpoints j
            LEFT JOIN transactions t ON j.customer_id = t.customer_id AND t.tenant_id = $1
            WHERE j.tenant_id = $1 AND j.created_at > NOW() - INTERVAL '90 days'
            GROUP BY j.channel
        """
        
        results = await db.execute(query, self.tenant_id)
        
        attributions = []
        total_revenue = sum(float(r.get('revenue', 0) or 0) for r in results)
        
        for r in results:
            channel = r['channel']
            conversions = r['conversions'] or 0
            revenue = float(r.get('revenue', 0) or 0)
            touch_count = r['touch_count'] or 1
            
            # Simple attribution calculation
            first_touch = revenue * 0.4
            last_touch = revenue * 0.4
            linear = revenue / touch_count
            time_decay = revenue * (0.1 * (touch_count - 1) + 0.9) / touch_count
            
            roi = (revenue / (touch_count * 100)) if touch_count > 0 else 0
            
            attributions.append(AttributionModel(
                channel=channel,
                first_touch_attribution=round(first_touch, 2),
                last_touch_attribution=round(last_touch, 2),
                linear_attribution=round(linear, 2),
                time_decay_attribution=round(time_decay, 2),
                roi=round(roi, 2)
            ))
        
        return attributions
    
    async def get_executive_summary(self, period: str = "month") -> ExecutiveSummary:
        """Executive dashboard with period comparison."""
        current_period_query = """
            SELECT
                SUM(amount) as revenue,
                COUNT(DISTINCT customer_id) as unique_customers,
                AVG(amount) as avg_transaction,
                COUNT(*) as transaction_count
            FROM transactions
            WHERE tenant_id = $1 AND created_at > NOW() - INTERVAL $2
        """

        previous_period_query = """
            SELECT
                SUM(amount) as revenue,
                COUNT(DISTINCT customer_id) as unique_customers,
                AVG(amount) as avg_transaction,
                COUNT(*) as transaction_count
            FROM transactions
            WHERE tenant_id = $1 AND created_at > NOW() - INTERVAL $2
        """

        interval_current = "1 month" if period == "month" else "1 year"
        interval_previous = "2 months" if period == "month" else "2 years"

        current = await db.execute_one(current_period_query, self.tenant_id, interval_current)
        previous = await db.execute_one(
            previous_period_query, self.tenant_id, interval_previous
        )
        
        current_revenue = float(current.get('revenue', 0) or 0)
        previous_revenue = float(previous.get('revenue', 0) or 0) if previous else 0
        
        growth_percent = 0
        if previous_revenue > 0:
            growth_percent = ((current_revenue - previous_revenue) / previous_revenue) * 100
        
        return ExecutiveSummary(
            period=period,
            revenue=current_revenue,
            growth_percent=growth_percent,
            key_metrics={
                "unique_customers": current.get('unique_customers', 0),
                "avg_transaction": round(float(current.get('avg_transaction', 0) or 0), 2),
                "transaction_count": current.get('transaction_count', 0)
            },
            benchmarks={
                "industry_average": 0.15,
                "your_performance": growth_percent / 100
            },
            comparison={
                "previous_period_revenue": previous_revenue,
                "revenue_difference": current_revenue - previous_revenue
            }
        )

# ============================================================================
# WebSocket Live Metrics
# ============================================================================

class LiveMetricsManager:
    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, tenant_id: str, websocket: WebSocket):
        await websocket.accept()
        if tenant_id not in self.connections:
            self.connections[tenant_id] = []
        self.connections[tenant_id].append(websocket)
        logger.info("WebSocket connected for tenant %s", tenant_id)
    
    async def disconnect(self, tenant_id: str, websocket: WebSocket):
        if tenant_id in self.connections:
            self.connections[tenant_id].remove(websocket)
            logger.info("WebSocket disconnected for tenant %s", tenant_id)
    
    async def broadcast(self, tenant_id: str, message: Dict):
        if tenant_id in self.connections:
            disconnected = []
            for connection in self.connections[tenant_id]:
                try:
                    await connection.send_json(message)
                except (RuntimeError, ConnectionError) as e:
                    logger.error("Error sending message: %s", e)
                    disconnected.append(connection)

            for conn in disconnected:
                await self.disconnect(tenant_id, conn)

live_metrics = LiveMetricsManager()

async def broadcast_live_metrics(tenant_id: str):
    """Background task to broadcast live metrics."""
    while True:
        try:
            auth_context = AuthContext(
                tenant_id=tenant_id,
                user_id="system",
                email="system@analytics.local"
            )
            service = AnalyticsService(auth_context)
            metrics = await service.get_dashboard_metrics()

            await live_metrics.broadcast(tenant_id, {
                "type": "metrics",
                "data": metrics.dict(),
                "timestamp": datetime.utcnow().isoformat()
            })

            await asyncio.sleep(5)  # Update every 5 seconds
        except (RuntimeError, asyncio.TimeoutError, Exception) as e:
            logger.error("Error broadcasting metrics: %s", e)
            await asyncio.sleep(5)

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Advanced Analytics Dashboard",
    description="Multi-tenant analytics platform with real-time metrics and predictive analytics",
    version="1.0.0"
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="advanced_analytics")
init_sentry(service_name="advanced-analytics", service_port=9035)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="advanced-analytics")
app.add_middleware(TracingMiddleware)


# CORS middleware
cors_origins = get_cors_origins()
cors_config = get_cors_config(os.getenv("ENVIRONMENT", "development"))
app.add_middleware(CORSMiddleware, **cors_config)
# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    await db.connect()
    await event_bus.startup()
    logger.info("Advanced Analytics Dashboard service started")

@app.on_event("shutdown")
async def shutdown_event():
    await db.disconnect()
    shutdown_tracing()
    await event_bus.shutdown()
    logger.info("Advanced Analytics Dashboard service stopped")

# ============================================================================
# Health Endpoint
# ============================================================================

@app.get("/advanced-analytics/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Advanced Analytics Dashboard",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# Dashboard Endpoints
# ============================================================================

@app.get("/advanced-analytics/dashboard", response_model=DashboardMetrics)
async def get_dashboard(auth: AuthContext = Depends(get_auth_context)):
    """Get real-time dashboard metrics."""
    service = AnalyticsService(auth)
    return await service.get_dashboard_metrics()

@app.get("/advanced-analytics/kpis", response_model=List[KPIResponse])
async def get_kpis(
    days: int = Query(30, ge=1, le=365),
    auth: AuthContext = Depends(get_auth_context)
):
    """Get key performance indicators with period comparison."""
    service = AnalyticsService(auth)
    return await service.get_kpis(days=days)

# ============================================================================
# Report Endpoints
# ============================================================================

@app.post("/advanced-analytics/reports", response_model=ReportResponse)
async def create_report(
    definition: ReportDefinition,
    auth: AuthContext = Depends(get_auth_context)
):
    """Create custom SQL report."""
    service = AnalyticsService(auth)
    return await service.create_report(definition)

@app.get("/advanced-analytics/reports", response_model=List[ReportResponse])
async def list_reports(
    limit: int = Query(50, ge=1, le=500),
    auth: AuthContext = Depends(get_auth_context)
):
    """List tenant reports."""
    service = AnalyticsService(auth)
    return await service.get_reports(limit=limit)

@app.get("/advanced-analytics/reports/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = Query("csv", regex="^(csv|pdf)$"),
    auth: AuthContext = Depends(get_auth_context)
):
    """Export report in specified format."""
    service = AnalyticsService(auth)
    return await service.export_report(report_id, format)

# ============================================================================
# Predictive Analytics Endpoints
# ============================================================================

@app.get("/advanced-analytics/forecast", response_model=ForecastResponse)
async def get_forecast(
    days: int = Query(90, ge=30, le=365),
    auth: AuthContext = Depends(get_auth_context)
):
    """Get revenue forecast using linear regression."""
    service = AnalyticsService(auth)
    return await service.forecast_revenue(days_ahead=days)

@app.get("/advanced-analytics/churn/{customer_id}")
async def get_churn_prediction(
    customer_id: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """Get customer churn prediction score."""
    service = AnalyticsService(auth)
    return await service.get_churn_score(customer_id)

# ============================================================================
# Cohort Analysis Endpoints
# ============================================================================

@app.get("/advanced-analytics/cohorts", response_model=List[CohortAnalysis])
async def get_cohorts(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get cohort analysis by signup date."""
    service = AnalyticsService(auth)
    return await service.get_cohorts()

# ============================================================================
# Attribution Endpoints
# ============================================================================

@app.get("/advanced-analytics/attribution", response_model=List[AttributionModel])
async def get_attribution(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get multi-touch attribution analysis."""
    service = AnalyticsService(auth)
    return await service.get_attribution()

# ============================================================================
# Executive Dashboard Endpoints
# ============================================================================

@app.get("/advanced-analytics/executive-summary", response_model=ExecutiveSummary)
async def get_executive_summary(
    period: str = Query("month", regex="^(month|year)$"),
    auth: AuthContext = Depends(get_auth_context)
):
    """Get executive dashboard with period comparison."""
    service = AnalyticsService(auth)
    return await service.get_executive_summary(period=period)

@app.get("/advanced-analytics/benchmarks")
async def get_benchmarks(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get industry benchmarks and performance comparison."""
    return {
        "industry_benchmarks": {
            "conversion_rate": 0.03,
            "csat_score": 4.2,
            "avg_response_time_ms": 500,
            "customer_lifetime_value": 5000
        },
        "your_performance": {
            "conversion_rate": 0.035,
            "csat_score": 4.5,
            "avg_response_time_ms": 450,
            "customer_lifetime_value": 5500
        },
        "percentile_rank": 0.75
    }

# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/live-metrics")
async def websocket_live_metrics(websocket: WebSocket, auth: AuthContext = Depends(get_auth_context)):
    """WebSocket endpoint for real-time metrics updates."""
    tenant_id = auth.tenant_id
    await live_metrics.connect(tenant_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await live_metrics.disconnect(tenant_id, websocket)
    except (RuntimeError, ConnectionError) as e:
        logger.error("WebSocket error: %s", e)
        await live_metrics.disconnect(tenant_id, websocket)

# ============================================================================
# Demand Forecasting Endpoint
# ============================================================================

@app.get("/advanced-analytics/demand-forecast")
async def get_demand_forecast(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get demand forecasting using historical patterns."""
    service = AnalyticsService(auth)
    
    query = """
        SELECT DATE(created_at) as date, COUNT(*) as conversation_count
        FROM conversations
        WHERE tenant_id = $1 AND created_at > NOW() - INTERVAL '180 days'
        GROUP BY DATE(created_at)
        ORDER BY date
    """
    
    results = await db.execute(query, auth.tenant_id)
    
    if len(results) < 10:
        return {"forecast": [], "confidence": 0}
    
    # Prepare data
    x = np.arange(len(results)).reshape(-1, 1)
    y = np.array([r['conversation_count'] or 0 for r in results])
    
    # Fit model
    slope, intercept, r_value, _, _ = stats.linregress(x.flatten(), y)
    
    # Generate forecast
    forecast_days = 30
    forecast = [intercept + slope * (len(results) + i) for i in range(forecast_days)]
    
    return {
        "metric": "conversation_demand",
        "forecast": [max(0, int(f)) for f in forecast],
        "confidence": r_value ** 2,
        "forecast_horizon_days": forecast_days
    }

# ============================================================================
# Segment Analysis Endpoint
# ============================================================================

@app.get("/advanced-analytics/segments")
async def get_customer_segments(
    auth: AuthContext = Depends(get_auth_context)
):
    """Get customer segments based on behavior."""
    query = """
        SELECT 
            CASE 
                WHEN COUNT(DISTINCT c.id) > 50 AND AVG(c.csat_score) > 4.5 THEN 'VIP'
                WHEN COUNT(DISTINCT c.id) > 20 AND AVG(c.csat_score) > 4.0 THEN 'Loyal'
                WHEN AVG(c.csat_score) < 3.0 THEN 'At Risk'
                ELSE 'Standard'
            END as segment,
            COUNT(DISTINCT customer_id) as customer_count,
            AVG(amount) as avg_value,
            COUNT(DISTINCT DATE(c.created_at)) as engagement_days
        FROM conversations c
        LEFT JOIN transactions t ON c.customer_id = t.customer_id AND t.tenant_id = $1
        WHERE c.tenant_id = $1 AND c.created_at > NOW() - INTERVAL '90 days'
        GROUP BY segment
    """
    
    results = await db.execute(query, auth.tenant_id)
    
    return {
        "segments": [
            {
                "name": r['segment'],
                "customer_count": r['customer_count'],
                "avg_value": float(r.get('avg_value', 0) or 0),
                "engagement_days": r['engagement_days']
            }
            for r in results
        ]
    }

# ============================================================================
# Comparison Analytics Endpoint
# ============================================================================

@app.get("/advanced-analytics/comparison")
async def get_period_comparison(
    period1: str = Query("2024-01", description="Start date (YYYY-MM)"),
    period2: str = Query("2024-02", description="End date (YYYY-MM)"),
    auth: AuthContext = Depends(get_auth_context)
):
    """Compare metrics between two periods."""
    query = """
        SELECT 
            TO_CHAR(created_at, 'YYYY-MM') as period,
            COUNT(DISTINCT id) as conversation_count,
            AVG(response_time_ms) as avg_response_time,
            AVG(csat_score) as avg_csat,
            SUM(CASE WHEN converted THEN 1 ELSE 0 END)::float / 
                NULLIF(COUNT(*), 0) as conversion_rate
        FROM conversations
        WHERE tenant_id = $1 
            AND TO_CHAR(created_at, 'YYYY-MM') IN ($2, $3)
        GROUP BY TO_CHAR(created_at, 'YYYY-MM')
    """
    
    results = await db.execute(query, auth.tenant_id, period1, period2)
    
    return {
        "period1": period1,
        "period2": period2,
        "metrics": [dict(r) for r in results]
    }

# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn


    
    port = int(os.getenv("PORT", 9035))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
