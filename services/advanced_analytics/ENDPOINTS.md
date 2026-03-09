# Advanced Analytics Dashboard - Complete Endpoint Reference

## Base URL
`http://localhost:9035`

## Authentication
All endpoints (except `/health`) require JWT token in Authorization header:
```
Authorization: Bearer <JWT_TOKEN>
```

## Endpoints

### Health & Status

#### GET /advanced-analytics/health
Get service health status (no auth required)

**Response:**
```json
{
  "status": "healthy",
  "service": "Advanced Analytics Dashboard",
  "timestamp": "2024-03-06T12:00:00"
}
```

---

### Dashboard & KPIs

#### GET /advanced-analytics/dashboard
Get real-time dashboard metrics

**Query Parameters:** None

**Response:**
```json
{
  "active_conversations": 42,
  "response_time_ms": 450.5,
  "csat_score": 4.5,
  "conversion_rate": 0.035,
  "timestamp": "2024-03-06T12:00:00"
}
```

---

#### GET /advanced-analytics/kpis
Get KPIs with period-over-period comparison

**Query Parameters:**
- `days` (int, default: 30, min: 1, max: 365) - Period in days

**Response:**
```json
[
  {
    "metric_name": "Response Time (ms)",
    "current_value": 450.5,
    "previous_value": 500.0,
    "change_percent": -9.9,
    "trend": "down"
  },
  {
    "metric_name": "CSAT Score",
    "current_value": 4.5,
    "previous_value": 4.2,
    "change_percent": 7.1,
    "trend": "up"
  }
]
```

---

### Reports

#### POST /advanced-analytics/reports
Create a custom SQL report

**Request Body:**
```json
{
  "name": "Monthly Revenue Report",
  "description": "Revenue breakdown by channel",
  "query": "SELECT channel, SUM(amount) FROM transactions WHERE tenant_id = ? GROUP BY channel",
  "scheduled": false,
  "schedule_cron": null,
  "export_format": "csv"
}
```

**Response:**
```json
{
  "id": "report_1709721600.0",
  "tenant_id": "tenant_123",
  "name": "Monthly Revenue Report",
  "created_at": "2024-03-06T12:00:00",
  "status": "pending"
}
```

---

#### GET /advanced-analytics/reports
List all reports for tenant

**Query Parameters:**
- `limit` (int, default: 50, min: 1, max: 500) - Number of reports

**Response:**
```json
[
  {
    "id": "report_1709721600.0",
    "tenant_id": "tenant_123",
    "name": "Monthly Revenue Report",
    "created_at": "2024-03-06T12:00:00",
    "status": "completed",
    "export_url": null
  }
]
```

---

#### GET /advanced-analytics/reports/{report_id}/export
Export report in specified format

**Path Parameters:**
- `report_id` (string) - Report identifier

**Query Parameters:**
- `format` (string, default: "csv", options: "csv", "pdf")

**Response:**
```json
{
  "report_id": "report_1709721600.0",
  "format": "csv",
  "generated_at": "2024-03-06T12:00:00",
  "rows": [
    {
      "channel": "web",
      "daily_revenue": 5000
    }
  ]
}
```

---

### Forecasting & Predictions

#### GET /advanced-analytics/forecast
Get revenue forecast using linear regression

**Query Parameters:**
- `days` (int, default: 90, min: 30, max: 365) - Days ahead to forecast

**Response:**
```json
{
  "metric": "revenue",
  "current_value": 50000.0,
  "forecast_30day": [51234.5, 52123.4, 53012.3, ...],
  "forecast_90day": [51234.5, 52123.4, ..., 73456.8],
  "confidence_interval": 0.95
}
```

---

#### GET /advanced-analytics/churn/{customer_id}
Get customer churn prediction score

**Path Parameters:**
- `customer_id` (string) - Customer identifier

**Response:**
```json
{
  "customer_id": "customer_123",
  "churn_score": 0.23,
  "engagement": 0.8,
  "satisfaction": 0.9,
  "recency": 0.7
}
```

---

#### GET /advanced-analytics/demand-forecast
Get demand/conversation volume forecast

**Query Parameters:** None

**Response:**
```json
{
  "metric": "conversation_demand",
  "forecast": [125, 130, 135, 140, ...],
  "confidence": 0.87,
  "forecast_horizon_days": 30
}
```

---

### Analysis

#### GET /advanced-analytics/cohorts
Get cohort analysis by signup date

**Query Parameters:** None

**Response:**
```json
[
  {
    "cohort_id": "2024-03-04T00:00:00",
    "signup_date": "2024-03-04T00:00:00",
    "size": 150,
    "retention_week1": 0.95,
    "retention_week4": 0.85,
    "retention_week12": 0.72,
    "revenue_per_user": 450.50
  }
]
```

---

#### GET /advanced-analytics/attribution
Get multi-touch attribution analysis

**Query Parameters:** None

**Response:**
```json
[
  {
    "channel": "email",
    "first_touch_attribution": 2000.0,
    "last_touch_attribution": 2000.0,
    "linear_attribution": 1800.5,
    "time_decay_attribution": 1950.25,
    "roi": 3.25
  },
  {
    "channel": "social",
    "first_touch_attribution": 1500.0,
    "last_touch_attribution": 1500.0,
    "linear_attribution": 1400.0,
    "time_decay_attribution": 1450.0,
    "roi": 2.80
  }
]
```

---

#### GET /advanced-analytics/segments
Get customer segments based on behavior

**Query Parameters:** None

**Response:**
```json
{
  "segments": [
    {
      "name": "VIP",
      "customer_count": 45,
      "avg_value": 2500.50,
      "engagement_days": 85
    },
    {
      "name": "Loyal",
      "customer_count": 120,
      "avg_value": 1200.75,
      "engagement_days": 65
    },
    {
      "name": "At Risk",
      "customer_count": 23,
      "avg_value": 500.25,
      "engagement_days": 10
    }
  ]
}
```

---

#### GET /advanced-analytics/comparison
Compare metrics between two periods

**Query Parameters:**
- `period1` (string, format: "YYYY-MM", default: "2024-01")
- `period2` (string, format: "YYYY-MM", default: "2024-02")

**Response:**
```json
{
  "period1": "2024-01",
  "period2": "2024-02",
  "metrics": [
    {
      "period": "2024-01",
      "conversation_count": 5000,
      "avg_response_time": 500.0,
      "avg_csat": 4.2,
      "conversion_rate": 0.03
    },
    {
      "period": "2024-02",
      "conversation_count": 5500,
      "avg_response_time": 450.0,
      "avg_csat": 4.5,
      "conversion_rate": 0.035
    }
  ]
}
```

---

### Executive Dashboards

#### GET /advanced-analytics/executive-summary
Get executive dashboard with period comparison

**Query Parameters:**
- `period` (string, default: "month", options: "month", "year")

**Response:**
```json
{
  "period": "month",
  "revenue": 150000.0,
  "growth_percent": 15.5,
  "key_metrics": {
    "unique_customers": 450,
    "avg_transaction": 333.33,
    "transaction_count": 450
  },
  "benchmarks": {
    "industry_average": 0.15,
    "your_performance": 0.155
  },
  "comparison": {
    "previous_period_revenue": 130000.0,
    "revenue_difference": 20000.0
  }
}
```

---

#### GET /advanced-analytics/benchmarks
Get industry benchmarks and performance comparison

**Query Parameters:** None

**Response:**
```json
{
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
```

---

### WebSocket

#### WebSocket /ws/live-metrics
Real-time metrics stream via WebSocket

**Authentication:** JWT token (via query parameter or header)

**Example Connection:**
```javascript
const token = "YOUR_JWT_TOKEN";
const ws = new WebSocket(`ws://localhost:9035/ws/live-metrics?token=${token}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

**Message Format (Sent every 5 seconds):**
```json
{
  "type": "metrics",
  "data": {
    "active_conversations": 42,
    "response_time_ms": 450.5,
    "csat_score": 4.5,
    "conversion_rate": 0.035,
    "timestamp": "2024-03-06T12:00:00"
  },
  "timestamp": "2024-03-06T12:00:00"
}
```

**Keep-Alive:**
```
Client -> "ping"
Server -> "pong"
```

---

## Common Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 401 | Unauthorized (invalid/missing JWT) |
| 404 | Not found (resource doesn't exist) |
| 500 | Internal server error |

---

## Error Response Format

```json
{
  "detail": "Error description here"
}
```

---

## Rate Limiting

Currently unlimited. In production, consider implementing:
- Per-tenant rate limits (e.g., 1000 requests/hour)
- WebSocket connection limits per tenant
- Database query timeouts (60 seconds default)

---

## OpenAPI Documentation

Auto-generated OpenAPI docs available at:
- Swagger UI: `http://localhost:9035/docs`
- ReDoc: `http://localhost:9035/redoc`
- OpenAPI JSON: `http://localhost:9035/openapi.json`
