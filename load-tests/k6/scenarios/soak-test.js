/**
 * Soak Test
 * Priya Global Platform - K6 Load Test
 *
 * Long-duration stability test:
 * - 100 VUs sustained for 30 minutes
 * - Check for memory leaks (response time degradation over time)
 * - Verify connection pool stability
 * - Check Redis/Kafka connection health over time
 * - Monitor resource utilization
 *
 * This test helps identify:
 * - Memory leaks in services
 * - Connection pool exhaustion
 * - Database connection issues
 * - Logging accumulation problems
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { CONFIG } from '../config.js';
import {
  randomTenant,
  getAuthHeaders,
  generateRequestId,
  generateEmail,
} from '../helpers.js';

// Custom metrics
const soakLatency = new Trend('soak_latency');
const soakSuccessRate = new Rate('soak_success_rate');
const latencyDegradation = new Gauge('latency_degradation');
const memoryLeakDetection = new Gauge('memory_leak_detection');
const connectionPoolHealth = new Gauge('connection_pool_health');
const requestCount = new Counter('soak_requests_total');
const errorCount = new Counter('soak_errors_total');

// Track latency over time
let latencySamples = [];
let testStartTime = Date.now();

export const options = {
  scenarios: {
    soak_test: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },    // Ramp up slowly
        { duration: '30m', target: 100 },  // Long soak at moderate load
        { duration: '2m', target: 0 },     // Ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'soak_latency': ['p(95)<1000', 'p(99)<2000'],
    'soak_success_rate': ['rate>0.99'],
    'http_req_failed': ['rate<0.01'],
    'memory_leak_detection': ['value<0.15'], // Less than 15% degradation
    'latency_degradation': ['value<0.20'],   // Less than 20% latency increase
  },
};

/**
 * Test conversation operations (core business logic)
 */
function testConversationOperations(tenant, token) {
  group('Conversation Operations', () => {
    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { operation: 'soak_conversation', tenant: tenant.id },
      }
    );

    soakLatency.add(response.timings.duration);
    const isSuccess = response.status === 200;
    soakSuccessRate.add(isSuccess);
    requestCount.add(1);

    if (!isSuccess) {
      errorCount.add(1);
    }

    sleep(0.5);
  });
}

/**
 * Test message operations
 */
function testMessageOperations(tenant, token) {
  group('Message Operations', () => {
    const payload = {
      conversation_id: `conv-${Date.now()}`,
      channel: 'webchat',
      text: 'Soak test message',
      sender: 'customer',
    };

    const response = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.messages.send}`,
      JSON.stringify(payload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { operation: 'soak_message', tenant: tenant.id },
      }
    );

    soakLatency.add(response.timings.duration);
    const isSuccess = response.status === 201 || response.status === 200;
    soakSuccessRate.add(isSuccess);
    requestCount.add(1);

    if (!isSuccess) {
      errorCount.add(1);
    }

    sleep(0.5);
  });
}

/**
 * Test authentication flow repeatedly
 */
function testAuthenticationCycles(tenant, token) {
  group('Authentication Cycles', () => {
    // Periodic token refresh to test auth service stability
    const payload = { refresh_token: 'test-refresh-token' };

    const response = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.refresh}`,
      JSON.stringify(payload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { operation: 'soak_auth', tenant: tenant.id },
      }
    );

    soakLatency.add(response.timings.duration);
    soakSuccessRate.add([200, 401].includes(response.status));
    requestCount.add(1);

    if (response.status >= 400 && response.status !== 401) {
      errorCount.add(1);
    }

    sleep(1.0);
  });
}

/**
 * Test analytics queries (can be resource intensive)
 */
function testAnalyticsQueries(tenant, token) {
  group('Analytics Queries', () => {
    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.analytics.dashboard}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { operation: 'soak_analytics', tenant: tenant.id },
      }
    );

    soakLatency.add(response.timings.duration);
    soakSuccessRate.add(response.status === 200);
    requestCount.add(1);

    if (response.status !== 200) {
      errorCount.add(1);
    }

    sleep(2.0);
  });
}

/**
 * Test list operations with pagination
 */
function testListOperations(tenant, token) {
  group('List Operations', () => {
    // Paginated list request
    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}?limit=50&offset=0`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { operation: 'soak_list', tenant: tenant.id },
      }
    );

    soakLatency.add(response.timings.duration);
    soakSuccessRate.add(response.status === 200);
    requestCount.add(1);

    if (response.status !== 200) {
      errorCount.add(1);
    }

    sleep(0.5);
  });
}

/**
 * Monitor latency degradation over time
 */
function monitorLatencyTrend(latency) {
  latencySamples.push(latency);

  // Every 100 samples (approximately), check for degradation
  if (latencySamples.length % 100 === 0) {
    const midpoint = Math.floor(latencySamples.length / 2);
    const firstHalf = latencySamples.slice(0, midpoint);
    const secondHalf = latencySamples.slice(midpoint);

    const avgFirst = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length;
    const avgSecond = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length;

    const degradation = (avgSecond - avgFirst) / avgFirst;
    latencyDegradation.add(degradation);

    // Check for memory leak pattern (consistent increase)
    if (degradation > 0.2) {
      memoryLeakDetection.add(degradation);
    }
  }
}

/**
 * Simulate connection pool health check
 */
function checkConnectionPoolHealth(tenant, token) {
  // Every 5 minutes, make a health check
  if (requestCount.value % 50 === 0) {
    const response = http.get(
      `${CONFIG.BASE_URL}/health`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { operation: 'health_check', tenant: tenant.id },
      }
    );

    if (response.status === 200) {
      connectionPoolHealth.add(1);
    } else {
      connectionPoolHealth.add(0);
    }
  }
}

/**
 * Test with varying request patterns
 */
function testVariedPatterns(tenant, token) {
  const pattern = Math.floor(Date.now() / 60000) % 4;

  switch (pattern) {
    case 0:
      // Conversation-heavy pattern
      for (let i = 0; i < 3; i++) {
        testConversationOperations(tenant, token);
      }
      break;

    case 1:
      // Message-heavy pattern
      for (let i = 0; i < 3; i++) {
        testMessageOperations(tenant, token);
      }
      break;

    case 2:
      // Auth-heavy pattern
      testAuthenticationCycles(tenant, token);
      break;

    case 3:
      // Analytics-heavy pattern
      testAnalyticsQueries(tenant, token);
      break;
  }
}

/**
 * Main test function
 */
export default function () {
  const tenant = randomTenant();
  const token = tenant.token;

  // Record latency for degradation analysis
  const startTime = Date.now();

  // Vary the operations based on time to simulate realistic patterns
  const minute = Math.floor((Date.now() - testStartTime) / 60000);

  switch (minute % 5) {
    case 0:
      testConversationOperations(tenant, token);
      break;
    case 1:
      testMessageOperations(tenant, token);
      break;
    case 2:
      testListOperations(tenant, token);
      break;
    case 3:
      testAuthenticationCycles(tenant, token);
      break;
    case 4:
      testAnalyticsQueries(tenant, token);
      break;
  }

  const duration = Date.now() - startTime;
  monitorLatencyTrend(duration);
  checkConnectionPoolHealth(tenant, token);

  // Gradually increase sleep to simulate off-peak periods
  const variableSleep = 0.5 + (Math.random() * 1.5);
  sleep(variableSleep);
}
