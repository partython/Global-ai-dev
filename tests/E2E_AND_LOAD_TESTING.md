# End-to-End and Load Testing Guide

Comprehensive E2E and load testing suite for Priya Global platform.

## Table of Contents

- [E2E Tests (pytest + httpx)](#e2e-tests-pytest--httpx)
- [Load Tests (k6)](#load-tests-k6)
- [Running Tests](#running-tests)
- [Test Coverage](#test-coverage)
- [Performance Targets](#performance-targets)
- [Troubleshooting](#troubleshooting)

---

## E2E Tests (pytest + httpx)

End-to-end tests that verify complete workflows using async HTTP client.

### Test Files

#### `tests/e2e/conftest.py`
Shared pytest fixtures providing:
- **API Client**: `async_client` - AsyncClient for making HTTP requests
- **Authentication**: Various auth headers (admin, agent, viewer, expired, tampered)
- **Test Data**: User, tenant, conversation, and message factories
- **Cleanup**: Automatic resource cleanup after tests

**Key Fixtures**:
```python
async_client              # Async HTTP client to API
test_auth_headers         # Valid JWT auth headers
test_agent_headers        # Agent role headers
test_viewer_headers       # Viewer role headers
expired_token_headers     # Expired token headers
tampered_token_headers    # Tampered JWT headers
other_tenant_headers      # Different tenant headers
cleanup_conversations     # Auto-cleanup conversations
cleanup_documents         # Auto-cleanup documents
```

#### `tests/e2e/test_auth_flow.py`
Authentication and authorization tests:

**TestUserRegistration**
- New user registration
- Duplicate email detection
- Missing field validation
- Weak password rejection

**TestLogin**
- Valid credentials login
- Invalid password handling
- Non-existent user handling
- Missing credential handling

**TestTokenRefresh**
- Token refresh with valid refresh token
- Refresh with invalid token
- Refresh with expired token

**TestExpiredTokenAccess**
- Expired token rejection (401)
- Valid token acceptance
- Missing token rejection

**TestMultiTenantIsolation**
- Cross-tenant data access prevention
- Tenant isolation verification
- Missing tenant_id rejection

**TestJWTSecurityValidation**
- Tampered token rejection
- Invalid JWT format handling
- Bearer prefix requirement
- Token claims validation

#### `tests/e2e/test_conversation_flow.py`
Conversation lifecycle tests:

**TestConversationCreation**
- Create WhatsApp conversations
- Create email conversations
- Create Slack conversations
- Missing field validation
- Authentication requirement

**TestSendMessage**
- Send text messages
- Message metadata inclusion
- Non-existent conversation handling
- Authentication requirement

**TestAIAutoResponse**
- AI response generation
- Response field validation

**TestConversationHandoff**
- Handoff to human agent
- Agent access to handed-off conversations

**TestCloseConversation**
- Close active conversations
- Prevent messages on closed conversations
- Handle double-close attempts

**TestConversationSearch**
- Search by customer name
- Search by phone number
- Search by status
- Pagination support
- Authentication requirement

#### `tests/e2e/test_billing_flow.py`
Subscription and billing tests:

**TestSubscriptionManagement**
- Get current subscription
- Subscription details retrieval

**TestPlanUpgrade**
- Upgrade to higher tier
- Immediate billing option
- Plan downgrade
- Invalid plan rejection

**TestUsageTracking**
- Get usage metrics
- Period information
- Usage increment on actions
- Usage forecasting

**TestInvoices**
- List invoices
- Get invoice by ID
- Invoice field validation
- PDF download
- Pagination

**TestPaymentMethods**
- List payment methods
- Set default payment method
- Delete payment method
- Authentication requirement

**TestBillingCycle**
- Get billing cycle information
- Validate cycle dates

#### `tests/e2e/test_knowledge_base.py`
Knowledge base management tests:

**TestDocumentUpload**
- Upload text documents
- Include metadata and tags
- Missing content validation
- Authentication requirement

**TestDocumentProcessing**
- Document processing verification
- Chunk creation
- Indexing

**TestQueryKnowledgeBase**
- Query documents
- Similarity scoring
- Filter by document type
- Filter by tags
- Pagination

**TestDeleteDocument**
- Delete documents
- Verify deletion
- Handle non-existent documents

**TestFileSizeValidation**
- Documents within size limits
- Oversized document rejection

**TestDocumentManagement**
- List documents
- Get document details
- Update document metadata

#### `tests/e2e/test_security.py`
Security-focused tests:

**TestTenantIsolation**
- Cross-tenant access prevention
- Cross-tenant modification prevention
- Tenant ID enforcement
- List scoping to tenant

**TestSQLInjectionPrevention**
- SQL injection in search parameters
- SQL injection in phone search
- SQL injection in message content

**TestXSSPrevention**
- XSS in customer names
- XSS in message content
- XSS in document titles

**TestRateLimiting**
- Rate limit enforcement
- Rate limit headers

**TestJWTTamperingRejection**
- Tampered token rejection
- Signature forgery prevention
- Payload change detection

**TestMissingTenantID**
- Missing tenant_id in token
- Empty tenant_id rejection

**TestFileUploadSecurity**
- MIME type validation
- Executable content blocking
- File content validation

### Running E2E Tests

#### Prerequisites
```bash
pip install pytest httpx pyjwt
```

#### Run All E2E Tests
```bash
pytest tests/e2e/ -v
```

#### Run Specific Test File
```bash
pytest tests/e2e/test_auth_flow.py -v
```

#### Run Specific Test Class
```bash
pytest tests/e2e/test_auth_flow.py::TestUserRegistration -v
```

#### Run Specific Test
```bash
pytest tests/e2e/test_auth_flow.py::TestUserRegistration::test_register_new_user -v
```

#### Run with Coverage
```bash
pytest tests/e2e/ --cov=services --cov-report=html
```

#### Environment Variables
```bash
API_BASE_URL=http://localhost:9000 pytest tests/e2e/ -v
```

#### Async Test Tips
Tests use `@pytest.mark.asyncio` decorator. Ensure pytest-asyncio is installed:
```bash
pip install pytest-asyncio
```

---

## Load Tests (k6)

Performance and load testing using k6 framework.

### Configuration

#### `load-tests/k6/load_config.js`
Central configuration:
- Stage definitions (ramp-up, hold, ramp-down)
- Performance thresholds
- Test tenants
- Metric tags
- Performance targets

**Key Exports**:
```javascript
defaultOptions      // Default test stages and thresholds
spikeTestOptions    // Spike test configuration
soakTestOptions     // Long-duration soak test config
performanceTargets  // p95/p99 targets per service
generateToken()     // Generate test JWT tokens
```

### Test Scenarios

#### `scenarios/conversation_load.js`
Tests conversation creation and messaging:
- Create conversations
- Send 5 messages per conversation
- Read conversation details
- List conversations
- Custom metrics for timing and success rate

**Metrics**:
- `conversation_create_duration` - Time to create conversation
- `messages_send_duration` - Time to send each message
- `conversation_read_duration` - Time to read conversation
- `conversation_success_rate` - Overall success rate

**Load Pattern**: Ramp 2min→50VUs, hold 5min, ramp-down 1min

#### `scenarios/api_gateway_load.js`
Mixed API workload testing:
- 70% read operations (GET)
- 30% write operations (POST)

**Endpoints**:
- Auth validation
- Conversations (CRUD)
- Conversation search
- Billing
- Analytics

**Metrics**:
- Per-endpoint latency trends
- Per-endpoint success rates
- Total request count and error count

#### `scenarios/ai_engine_load.js`
AI engine performance testing:
- Intent classification
- Entity extraction
- Response generation
- Batch operations

**Metrics**:
- `ai_intent_latency` - Intent classification latency
- `ai_entity_latency` - Entity extraction latency
- `ai_response_latency` - Response generation latency
- `ai_inference_latency` - Pure inference time
- Per-operation success rates

**Load Pattern**: Allows 2% error rate (vs 1% for API)

### Running Load Tests

#### Prerequisites
```bash
# Install k6
# macOS with Homebrew
brew install k6

# Or download from https://k6.io/docs/getting-started/installation/
```

#### Run Single Scenario
```bash
k6 run load-tests/k6/scenarios/conversation_load.js
```

#### Run with Custom Load Profile
```bash
k6 run \
  --vus 100 \
  --duration 10m \
  load-tests/k6/scenarios/conversation_load.js
```

#### Run All Scenarios
```bash
cd load-tests/k6
./run_all.sh
```

#### Run All Scenarios Against Staging
```bash
BASE_URL=http://staging:9000 ./run_all.sh
```

#### Dry Run (Test Configuration)
```bash
./run_all.sh --dry-run
```

#### Output to JSON for Analysis
```bash
k6 run -o json=results.json load-tests/k6/scenarios/conversation_load.js
```

#### Monitor with Grafana/Prometheus
```bash
k6 run \
  -o statsd \
  load-tests/k6/scenarios/conversation_load.js
```

---

## Performance Targets

| Component | Metric | Target | Error Rate |
|-----------|--------|--------|------------|
| API | p95 latency | <500ms | <1% |
| API | p99 latency | <1000ms | |
| Gateway | p95 latency | <400ms | <0.5% |
| Conversation | p95 latency | <1000ms | <1% |
| AI Engine | p95 latency | <3000ms | <2% |
| AI Engine | p99 latency | <5000ms | |
| Overall | Throughput | >100 rps | |
| Overall | Error Rate | <1% | |

---

## Test Coverage

### Authentication
- ✓ User registration
- ✓ Login flows
- ✓ Token refresh
- ✓ Token expiration
- ✓ JWT validation and signature verification
- ✓ Multi-tenant isolation

### Conversations
- ✓ Create conversations (WhatsApp, Email, Slack)
- ✓ Send messages
- ✓ Receive messages
- ✓ Handoff to agents
- ✓ Close conversations
- ✓ Search conversations
- ✓ List conversations

### Billing
- ✓ Get subscription
- ✓ Upgrade/downgrade plans
- ✓ Usage tracking
- ✓ Invoice retrieval
- ✓ Payment methods
- ✓ Billing cycle

### Knowledge Base
- ✓ Document upload
- ✓ Document processing
- ✓ Query/search
- ✓ Delete documents
- ✓ File size validation
- ✓ Metadata management

### Security
- ✓ Tenant isolation
- ✓ SQL injection prevention
- ✓ XSS prevention
- ✓ Rate limiting
- ✓ JWT tampering detection
- ✓ Missing tenant_id handling
- ✓ File upload validation

### Load & Performance
- ✓ Conversation creation at scale
- ✓ Message sending throughput
- ✓ Search performance
- ✓ AI inference latency
- ✓ API gateway throughput
- ✓ Spike handling
- ✓ Soak stability

---

## Troubleshooting

### E2E Tests

#### Tests timeout
```bash
# Increase timeout
pytest tests/e2e/ --timeout=60
```

#### Connection refused
```bash
# Check API is running
curl http://localhost:9000/health

# Set correct URL
API_BASE_URL=http://your-api:9000 pytest tests/e2e/ -v
```

#### JWT errors
```bash
# Verify JWT_SECRET matches backend
export JWT_SECRET_KEY="your-secret"
pytest tests/e2e/ -v
```

### Load Tests

#### k6 not found
```bash
# Install k6
brew install k6  # macOS
# Or visit https://k6.io/docs/getting-started/installation/
```

#### Tests fail to connect
```bash
# Check API availability
curl -v http://localhost:9000/health

# Verify BASE_URL
BASE_URL=http://localhost:9000 k6 run scenarios/conversation_load.js
```

#### Out of memory
```bash
# Reduce VUs or duration
k6 run --vus 10 --duration 1m scenarios/conversation_load.js
```

#### High error rates
```bash
# Check logs
tail -f /tmp/k6-*.log

# Reduce load
k6 run --vus 5 scenarios/conversation_load.js
```

#### Results not in JSON format
```bash
# Ensure -o json= flag
k6 run -o json=results.json scenarios/conversation_load.js
```

---

## CI/CD Integration

### GitHub Actions
```yaml
name: E2E and Load Tests
on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install pytest httpx pyjwt pytest-asyncio
      - run: pytest tests/e2e/ -v

  load-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: grafana/setup-k6-action@v1
      - run: cd load-tests/k6 && ./run_all.sh --dry-run
      - uses: actions/upload-artifact@v2
        with:
          name: load-test-results
          path: load-test-results/
```

### GitLab CI
```yaml
e2e-tests:
  image: python:3.10
  script:
    - pip install pytest httpx pyjwt pytest-asyncio
    - pytest tests/e2e/ -v

load-tests:
  image: grafana/k6:latest
  script:
    - cd load-tests/k6
    - ./run_all.sh --dry-run
  artifacts:
    paths:
      - load-test-results/
```

---

## Best Practices

### E2E Tests
1. Use fixtures for setup/teardown
2. Test both happy path and error cases
3. Validate response content, not just status codes
4. Use meaningful assertion messages
5. Clean up resources with cleanup fixtures
6. Test across different roles/tenants

### Load Tests
1. Start with baseline to establish normal behavior
2. Run soak tests for memory leaks
3. Use realistic user behavior patterns
4. Monitor resource utilization
5. Run against staging before production
6. Save results for trend analysis
7. Set thresholds based on SLAs

---

## Additional Resources

- [K6 Documentation](https://k6.io/docs/)
- [Pytest Documentation](https://docs.pytest.org/)
- [HTTPX Documentation](https://www.python-httpx.org/)
- [JWT Documentation](https://jwt.io/)

---

## Support

For issues or questions:
1. Check test logs in `load-test-logs/`
2. Review API error responses
3. Verify environment configuration
4. Check API health at `/health` endpoint
5. Contact the development team
