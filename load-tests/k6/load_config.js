/**
 * K6 Load Testing Configuration
 * Priya Global - E2E Load Testing Suite
 *
 * Centralized configuration for all load test scenarios with:
 * - Stage definitions (ramp-up, hold, ramp-down)
 * - Threshold definitions
 * - Multi-tenant setup
 * - Performance targets
 *
 * Usage: import { options, BASE_URL, generateToken } from './load_config.js'
 */

import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';

// ─────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────

export const BASE_URL = __ENV.BASE_URL || 'http://localhost:9000';
export const API_GATEWAY = __ENV.API_GATEWAY || 'http://localhost:9000';
export const JWT_SECRET = __ENV.JWT_SECRET || 'test-secret-key-do-not-use-in-production';

// Test execution options
export const defaultOptions = {
  stages: [
    // Ramp up from 0 to 50 virtual users over 2 minutes
    { duration: '2m', target: 50 },
    // Hold 50 VUs for 5 minutes
    { duration: '5m', target: 50 },
    // Ramp down to 0 over 1 minute
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    // Response time thresholds
    'http_req_duration': ['p(95)<500', 'p(99)<1000'],
    'http_req_duration{staticAsset:yes}': ['p(99)<1000'],
    'http_req_duration{staticAsset:no}': ['p(95)<500'],

    // Error rate thresholds
    'http_req_failed': ['rate<0.01'],  // <1% error rate

    // Throughput thresholds
    'http_reqs': ['rate>100'],  // >100 requests per second

    // Custom metrics
    'conversation_response_time': ['p(95)<1000'],
    'ai_inference_latency': ['p(95)<3000'],
    'auth_success_rate': ['rate>0.99'],
  },
  vus: 1,
  duration: '1m',
};

// Spike test options
export const spikeTestOptions = {
  stages: [
    { duration: '2m', target: 10 },    // Warm up
    { duration: '1m', target: 100 },   // Spike to 100 VUs
    { duration: '2m', target: 100 },   // Hold spike
    { duration: '1m', target: 10 },    // Return to baseline
    { duration: '1m', target: 0 },     // Cool down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<800'],
    'http_req_failed': ['rate<0.05'],
  },
};

// Soak test options (long duration)
export const soakTestOptions = {
  stages: [
    { duration: '5m', target: 30 },    // Ramp up
    { duration: '30m', target: 30 },   // Soak at steady load
    { duration: '5m', target: 0 },     // Ramp down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<500'],
    'http_req_failed': ['rate<0.01'],
  },
};

// ─────────────────────────────────────────────────────────
// Test Tenants
// ─────────────────────────────────────────────────────────

export const testTenants = {
  primary: {
    id: `tenant-load-${Date.now()}`,
    name: 'Load Test Tenant - Primary',
    plan: 'enterprise',
    region: 'IN',
  },
  secondary: {
    id: `tenant-load-${Date.now()}-2`,
    name: 'Load Test Tenant - Secondary',
    plan: 'professional',
    region: 'US',
  },
};

// ─────────────────────────────────────────────────────────
// JWT Token Generation
// ─────────────────────────────────────────────────────────

/**
 * Generate a test JWT token
 */
export function generateToken(
  userId = `user-${Date.now()}`,
  tenantId = 'tenant-load-001',
  role = 'admin'
) {
  // Base64 encode (simplified - real JWT needs proper signing)
  // In production, use proper JWT library
  const header = JSON.stringify({ alg: 'HS256', typ: 'JWT' });
  const payload = JSON.stringify({
    sub: userId,
    tenant_id: tenantId,
    role: role,
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 86400,
  });

  const encodedHeader = btoa(header);
  const encodedPayload = btoa(payload);

  // In actual implementation, would compute HMAC signature
  const signature = 'test-signature-not-validated-in-staging';

  return `${encodedHeader}.${encodedPayload}.${signature}`;
}

// ─────────────────────────────────────────────────────────
// Metric Tags
// ─────────────────────────────────────────────────────────

export const metricTags = {
  endpoint: {
    AUTH: 'endpoint:auth',
    CONVERSATION: 'endpoint:conversation',
    MESSAGE: 'endpoint:message',
    KNOWLEDGE_BASE: 'endpoint:knowledge_base',
    BILLING: 'endpoint:billing',
    AI_ENGINE: 'endpoint:ai_engine',
  },
  operation: {
    CREATE: 'operation:create',
    READ: 'operation:read',
    UPDATE: 'operation:update',
    DELETE: 'operation:delete',
  },
  scenario: {
    CONVERSATION_LOAD: 'scenario:conversation',
    API_GATEWAY: 'scenario:gateway',
    AI_ENGINE: 'scenario:ai',
  },
};

// ─────────────────────────────────────────────────────────
// Performance Targets
// ─────────────────────────────────────────────────────────

export const performanceTargets = {
  api: {
    p95: 500,      // 95th percentile <500ms
    p99: 1000,     // 99th percentile <1000ms
    errorRate: 0.01,  // <1% error rate
  },
  ai: {
    p95: 3000,     // AI inference slower
    p99: 5000,
    errorRate: 0.02,  // Allow 2% error for AI
  },
  gateway: {
    p95: 400,      // Gateway should be fast
    p99: 800,
    errorRate: 0.005,
  },
  conversation: {
    p95: 1000,
    p99: 2000,
    errorRate: 0.01,
  },
};

// ─────────────────────────────────────────────────────────
// Test Data
// ─────────────────────────────────────────────────────────

export function generateCustomerPhone() {
  const prefix = '+91';  // India
  const number = Math.floor(Math.random() * 9000000000) + 1000000000;
  return `${prefix}${number}`;
}

export function generateConversationPayload() {
  return {
    channel: 'whatsapp',
    customer_phone: generateCustomerPhone(),
    customer_name: `Customer-${Math.random().toString(36).substr(2, 9)}`,
    initial_message: 'Hello, I need help with my order',
    metadata: {
      source: 'load_test',
      region: 'IN',
    },
  };
}

export function generateMessagePayload() {
  const messages = [
    'What are your business hours?',
    'Can I place an order?',
    'How long is shipping?',
    'Do you have refunds?',
    'What payment methods do you accept?',
  ];
  return {
    content: messages[Math.floor(Math.random() * messages.length)],
    type: 'text',
    sender: 'customer',
  };
}

// ─────────────────────────────────────────────────────────
// Helper Functions
// ─────────────────────────────────────────────────────────

/**
 * Handle response with proper error checking
 */
export function checkResponse(response, expectedStatus = 200) {
  if (response.status !== expectedStatus) {
    console.error(`Unexpected status ${response.status}: ${response.body}`);
  }
  return response.status === expectedStatus;
}

/**
 * Convert milliseconds to seconds for reporting
 */
export function msToSec(ms) {
  return (ms / 1000).toFixed(2);
}

/**
 * Summary handler for JSON output
 */
export function handleSummary(data) {
  return {
    '/tmp/k6-summary.json': JSON.stringify(data),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}
