# Sentry Integration - Quick Start Guide

## For Backend Services (FastAPI)

### Already Integrated!

All 35 microservices have automatic Sentry initialization. Just set the environment variable:

```bash
export SENTRY_DSN=https://key@sentry.io/project-id
export ENVIRONMENT=production
```

Services restart → Sentry captures errors automatically.

### Using in Code

**Set Tenant Context (in middleware or before creating response):**

```python
from shared.observability.sentry import set_tenant_context

set_tenant_context(
    tenant_id=request.state.tenant_id,
    user_id=request.state.user_id,
    plan="enterprise"
)
```

**Capture Business Events:**

```python
from shared.observability.sentry import capture_business_event

capture_business_event("order.created", {
    "order_id": "ord_123",
    "amount": 1500,
    "currency": "USD"
})
```

**Manual Error Capture:**

```python
import sentry_sdk

try:
    risky_operation()
except Exception as e:
    sentry_sdk.capture_exception(e)
```

**Add Context to Errors:**

```python
import sentry_sdk

with sentry_sdk.configure_scope() as scope:
    scope.set_tag("payment_provider", "stripe")
    scope.set_context("order", {
        "order_id": "ord_123",
        "status": "pending"
    })
    perform_operation()
```

---

## For Frontend (Next.js Dashboard)

### Setup

In your root layout or `_app.tsx`:

```typescript
import { initSentry, setTenantContext } from "@/lib/sentry";

// On app load
useEffect(() => {
  initSentry();
}, []);

// After auth (in useAuth hook or context provider)
useEffect(() => {
  if (user && tenant) {
    setTenantContext(
      tenant.id,
      user.id,
      tenant.plan
    );
  }
}, [user, tenant]);
```

### Capturing Business Events

```typescript
import { captureBusinessEvent } from "@/lib/sentry";

// In conversation component
const handleMessageSent = async (message) => {
  captureBusinessEvent("message.sent", {
    conversation_id: conversationId,
    channel: "whatsapp",
    length: message.length,
  });
  // ... send message
};
```

### Error Boundaries

```typescript
import * as Sentry from "@sentry/nextjs";

// Wrap a component
const SafeComponent = Sentry.errorBoundaryWithProfiler(MyComponent);

export default function Page() {
  return <SafeComponent />;
}
```

### Tracking User Actions

```typescript
import * as Sentry from "@sentry/nextjs";

const handleButtonClick = () => {
  Sentry.addBreadcrumb({
    category: "ui",
    message: "User clicked important button",
    level: "info",
    data: {
      button_id: "delete_conversation",
      conversation_id: conversationId,
    },
  });
  // ... handle click
};
```

---

## Common Use Cases

### Order Pipeline (Backend)

```python
from shared.observability.sentry import set_tenant_context, capture_business_event
import sentry_sdk

@app.post("/orders")
async def create_order(req: Request, order: OrderCreate):
    # Set context
    set_tenant_context(
        tenant_id=req.state.tenant_id,
        user_id=req.state.user_id
    )
    
    try:
        # Create order
        order_id = await db.orders.insert({
            **order.dict(),
            "tenant_id": req.state.tenant_id,
        })
        
        # Track event
        capture_business_event("order.created", {
            "order_id": order_id,
            "amount": order.amount,
            "customer_id": order.customer_id,
        })
        
        # Process payment
        try:
            await stripe.charge(order.amount)
            capture_business_event("payment.processed", {
                "order_id": order_id,
                "amount": order.amount,
            })
        except StripeError as e:
            # Capture payment error with context
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("payment_status", "failed")
                scope.set_context("order", {"order_id": order_id})
                sentry_sdk.capture_exception(e)
            raise
        
        return {"order_id": order_id, "status": "completed"}
        
    except Exception as e:
        # Broader error handler
        sentry_sdk.capture_exception(e)
        raise
```

### User Authentication (Backend)

```python
from shared.observability.sentry import set_tenant_context
import sentry_sdk

@app.post("/auth/login")
async def login(credentials: LoginRequest):
    user = await db.users.find_by_email(credentials.email)
    
    if not user or not verify_password(credentials.password, user.password_hash):
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("auth_event", "login_failed")
            scope.set_context("attempt", {
                "email": credentials.email,  # Will be scrubbed
                "ip": request.client.host,
            })
            sentry_sdk.capture_message("Failed login attempt")
        raise HTTPException(status_code=401)
    
    # Set context for this user
    set_tenant_context(
        tenant_id=user.tenant_id,
        user_id=user.id,
        plan=user.tenant.plan
    )
    
    token = create_jwt_token(user)
    return {"access_token": token, "token_type": "bearer"}
```

### Conversation Component (Frontend)

```typescript
import { setTenantContext, captureBusinessEvent } from "@/lib/sentry";
import * as Sentry from "@sentry/nextjs";

export function ConversationThread({ conversationId }) {
  const { user, tenant } = useAuth();
  const [messages, setMessages] = useState([]);
  
  useEffect(() => {
    // Set context when component loads
    if (user && tenant) {
      setTenantContext(tenant.id, user.id, tenant.plan);
    }
  }, [user, tenant]);
  
  const handleMessageSend = async (message) => {
    try {
      // Track user action
      Sentry.addBreadcrumb({
        category: "ui.action",
        message: "Message sent",
        data: {
          conversation_id: conversationId,
          channel: "whatsapp",
        },
      });
      
      const response = await sendMessage(conversationId, message);
      
      // Capture business event
      captureBusinessEvent("message.sent", {
        conversation_id: conversationId,
        channel: "whatsapp",
        message_length: message.length,
        response_time: response.timing,
      });
      
      setMessages([...messages, response.message]);
      
    } catch (error) {
      // Will be automatically captured by Sentry error boundary
      captureBusinessEvent("message.send_failed", {
        conversation_id: conversationId,
        error_type: error.type,
      });
      throw error;
    }
  };
  
  return (
    <div className="conversation">
      {messages.map(msg => (
        <Message key={msg.id} message={msg} />
      ))}
      <MessageInput onSend={handleMessageSend} />
    </div>
  );
}
```

---

## What Gets Captured Automatically

### Backend
- Unhandled exceptions in endpoints
- Request/response metadata
- Performance metrics
- Slow requests (>5 seconds)
- Database connection errors

### Frontend
- JavaScript errors
- React component errors
- Failed API calls (5xx)
- Performance metrics
- User interactions leading to errors

---

## Environment Variables Cheat Sheet

**Development:**
```bash
SENTRY_DSN=https://key@sentry.io/project-id
ENVIRONMENT=development
SENTRY_SAMPLE_RATE=1.0  # 100% capture
```

**Production:**
```bash
SENTRY_DSN=https://key@sentry.io/project-id
ENVIRONMENT=production
SENTRY_SAMPLE_RATE=1.0  # 100% errors, 20% transactions
```

**Disable Sentry:**
```bash
SENTRY_ENABLED=false
# or
# SENTRY_DSN not set
```

---

## Debugging Tips

### Check if Sentry is Enabled

```python
import os
dsn = os.getenv("SENTRY_DSN")
enabled = os.getenv("SENTRY_ENABLED", "true").lower() == "true"
print(f"Sentry: DSN={'set' if dsn else 'missing'}, Enabled={enabled}")
```

### Force Send an Event

```python
import sentry_sdk
sentry_sdk.capture_message("Test message", level="info")
```

### Check Tenant Context

```python
import sentry_sdk
with sentry_sdk.configure_scope() as scope:
    print(scope.tags)  # See all current tags
    print(scope._contexts)  # See all contexts
```

### View Breadcrumbs in Sentry UI

In Sentry dashboard, go to an issue and look for the "Breadcrumbs" section.
Each breadcrumb shows the sequence of events leading to the error.

---

## Common Gotchas

### PII Still Appearing?

Sentry automatically scrubs:
- Emails, phones, JWTs, API keys, credit cards

But custom data is scrubbed too. If you see `[EMAIL_REDACTED]`, it's working!

### Tenant Context Not Showing?

Make sure:
1. `set_tenant_context()` is called after JWT validation
2. Middleware runs AFTER auth middleware
3. `request.state.tenant_id` is set by auth middleware

### Too Many Errors?

Adjust sampling:
```bash
SENTRY_SAMPLE_RATE=0.5  # 50% of errors
```

Or add to ignored errors in `shared/observability/sentry.py`:
```python
IGNORED_ERRORS = {
    "YourErrorType",
}
```

---

## Next Steps

1. Set `SENTRY_DSN` in your deployment
2. Deploy a service
3. Go to sentry.io and create an issue to test
4. Configure alerts in Sentry UI
5. Set up Slack integration for notifications

That's it! Errors are now tracked globally.
