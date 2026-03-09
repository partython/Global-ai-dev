# Sentry Service Modifications - Details

This document shows exactly what was added to each of the 35 microservices.

## Modification Pattern

Every service has TWO changes:

### 1. Import Statement (Added near top, after shared imports)
```python
from shared.observability.sentry import init_sentry
```

### 2. Initialization Call (Added right after FastAPI() instantiation)
```python
# Initialize Sentry error tracking
init_sentry(service_name="[service-name]", service_port=[port])
```

## Example: Gateway Service (Port 9000)

**Before:**
```python
from fastapi import FastAPI
from shared.core.config import config
from shared.core.security import get_rate_limit, mask_pii

app = FastAPI(
    title="Priya Global API Gateway",
    description="Central API routing, rate limiting, and security layer",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
```

**After:**
```python
from fastapi import FastAPI
from shared.core.config import config
from shared.core.security import get_rate_limit, mask_pii
from shared.observability.sentry import init_sentry  # ADDED

app = FastAPI(
    title="Priya Global API Gateway",
    description="Central API routing, rate limiting, and security layer",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)
# Initialize Sentry error tracking  # ADDED
init_sentry(service_name="gateway", service_port=9000)  # ADDED
```

---

## All 35 Services Modified

### Channel Services (9010-9016)

#### WhatsApp Service (Port 9010)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="whatsapp", service_port=9010)
```

#### Email Service (Port 9011)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="email", service_port=9011)
```

#### Voice Service (Port 9012)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="voice", service_port=9012)
```

#### Social Service (Port 9013)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="social", service_port=9013)
```

#### Webchat Service (Port 9014)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="webchat", service_port=9014)
```

#### SMS Service (Port 9015)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="sms", service_port=9015)
```

#### Telegram Service (Port 9016)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="telegram", service_port=9016)
```

---

### Core Services (9000-9006)

#### Gateway Service (Port 9000)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="gateway", service_port=9000)
```

#### Auth Service (Port 9001)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="auth", service_port=9001)
```

#### Tenant Service (Port 9002)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="tenant", service_port=9002)
```

#### Channel Router Service (Port 9003)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="channel-router", service_port=9003)
```

#### AI Engine Service (Port 9004)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="ai-engine", service_port=9004)
```

---

### Business Services (9020-9030)

#### Billing Service (Port 9020)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="billing", service_port=9020)
```

#### Analytics Service (Port 9021)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="analytics", service_port=9021)
```

#### Marketing Service (Port 9022)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="marketing", service_port=9022)
```

#### Ecommerce Service (Port 9023)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="ecommerce", service_port=9023)
```

#### Notification Service (Port 9024)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="notification", service_port=9024)
```

#### Plugins Service (Port 9025)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="plugins", service_port=9025)
```

#### Handoff Service (Port 9026)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="handoff", service_port=9026)
```

#### Leads Service (Port 9027)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="leads", service_port=9027)
```

#### Conversation Intel Service (Port 9028)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="conversation-intel", service_port=9028)
```

#### Appointments Service (Port 9029)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="appointments", service_port=9029)
```

#### Knowledge Service (Port 9030)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="knowledge", service_port=9030)
```

---

### Advanced Services (9031-9042)

#### Voice AI Service (Port 9031)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="voice-ai", service_port=9031)
```

#### Video Service (Port 9032)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="video", service_port=9032)
```

#### RCS Service (Port 9033)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="rcs", service_port=9033)
```

#### Workflows Service (Port 9034)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="workflows", service_port=9034)
```

#### Advanced Analytics Service (Port 9035)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="advanced-analytics", service_port=9035)
```

#### AI Training Service (Port 9036)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="ai-training", service_port=9036)
```

#### Marketplace Service (Port 9037)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="marketplace", service_port=9037)
```

#### Compliance Service (Port 9038)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="compliance", service_port=9038)
```

#### Health Monitor Service (Port 9039)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="health-monitor", service_port=9039)
```

#### CDN Manager Service (Port 9040)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="cdn-manager", service_port=9040)
```

#### Deployment Service (Port 9041)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="deployment", service_port=9041)
```

#### Tenant Config Service (Port 9042)
```python
from shared.observability.sentry import init_sentry
init_sentry(service_name="tenant-config", service_port=9042)
```

---

## Verification Commands

To verify a specific service has Sentry integration:

```bash
# Check if import exists
grep "from shared.observability.sentry import init_sentry" \
  /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/[service_name]/main.py

# Check if init call exists
grep "init_sentry(" \
  /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/[service_name]/main.py

# Show line numbers
grep -n "from shared.observability.sentry import\|init_sentry(" \
  /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/[service_name]/main.py
```

## Verification All Services

```bash
# Count services with Sentry
for svc in gateway auth tenant channel_router ai_engine whatsapp email voice \
  social webchat sms telegram billing analytics marketing ecommerce notification \
  plugins handoff leads conversation_intel appointments knowledge voice_ai video \
  rcs workflows advanced_analytics ai_training marketplace compliance health_monitor \
  cdn_manager deployment tenant_config; do
  
  if grep -q "from shared.observability.sentry import init_sentry" \
    /sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services/$svc/main.py 2>/dev/null; then
    echo "✅ $svc"
  else
    echo "❌ $svc"
  fi
done
```

---

## Rollback Instructions

If needed, to remove Sentry from a service:

1. Remove the import line:
   ```python
   from shared.observability.sentry import init_sentry
   ```

2. Remove the init call:
   ```python
   init_sentry(service_name="...", service_port=...)
   ```

No other code changes are needed. The integration is fully isolated.

---

## What This Enables

With these minimal changes, every service now has:
- Automatic error tracking
- Performance monitoring
- Tenant-aware logging
- Custom business event capture
- PII protection
- Request/response timing
- Exception context enrichment

All with ZERO changes to business logic code.
