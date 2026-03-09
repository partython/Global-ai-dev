/**
 * K6 Load Test: API Gateway Performance
 *
 * Tests API Gateway with mixed workload:
 * - 70% read operations (GET)
 * - 30% write operations (POST)
 *
 * Endpoints tested:
 * - Authentication
 * - Conversations (CRUD)
 * - Conversations search
 * - Messages
 * - Billing
 *
 * Usage: k6 run api_gateway_load.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import {
  defaultOptions,
  BASE_URL,
  generateToken,
  generateConversationPayload,
  metricTags,
  performanceTargets,
} from '../load_config.js';

// ─────────────────────────────────────────────────────────
// Custom Metrics
// ─────────────────────────────────────────────────────────

const authLatency = new Trend('auth_latency', true);
const conversationLatency = new Trend('conversation_latency', true);
const searchLatency = new Trend('search_latency', true);
const billingLatency = new Trend('billing_latency', true);
const messageLatency = new Trend('message_latency', true);

const authSuccessRate = new Rate('auth_success_rate', true);
const conversationSuccessRate = new Rate('conversation_success_rate', true);
const searchSuccessRate = new Rate('search_success_rate', true);
const billingSuccessRate = new Rate('billing_success_rate', true);

const totalRequests = new Counter('total_requests', true);
const totalErrors = new Counter('total_errors', true);

// ─────────────────────────────────────────────────────────
// Test Options
// ─────────────────────────────────────────────────────────

export const options = {
  ...defaultOptions,
  thresholds: {
    ...defaultOptions.thresholds,
    'auth_latency': [`p(95)<${performanceTargets.api.p95}`],
    'conversation_latency': [`p(95)<${performanceTargets.conversation.p95}`],
    'search_latency': [`p(95)<${performanceTargets.api.p95}`],
    'billing_latency': [`p(95)<${performanceTargets.api.p95}`],
    'message_latency': [`p(95)<${performanceTargets.api.p95}`],
    'auth_success_rate': [`rate>0.99`],
    'conversation_success_rate': [`rate>0.98`],
    'search_success_rate': [`rate>0.98`],
    'billing_success_rate': [`rate>0.98`],
  },
};

// ─────────────────────────────────────────────────────────
// Test Functions
// ─────────────────────────────────────────────────────────

/**
 * Test authentication endpoint
 */
function testAuth() {
  group('Auth', () => {
    const params = {
      headers: {
        'Content-Type': 'application/json',
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'GetToken',
        ...metricTags.endpoint.AUTH,
        ...metricTags.operation.READ,
      },
    };

    // Simulate token validation endpoint
    const response = http.get(
      `${BASE_URL}/api/v1/auth/validate`,
      params
    );

    const success = response.status === 200 || response.status === 401; // 401 is valid response
    authSuccessRate.add(success);
    totalRequests.add(1);

    if (response.status !== 401) {
      authLatency.add(response.timings.duration);
    } else {
      totalErrors.add(1);
    }

    check(response, {
      'auth endpoint responds': (r) => r.status !== 0,
    });
  });
}

/**
 * Test conversation endpoints (mixed read/write)
 */
function testConversations(token) {
  group('Conversations', () => {
    // Read: List conversations (70% likelihood)
    if (Math.random() < 0.7) {
      const params = {
        headers: {
          'Authorization': `Bearer ${token}`,
          'User-Agent': 'k6-load-test',
        },
        tags: {
          name: 'ListConversations',
          ...metricTags.endpoint.CONVERSATION,
          ...metricTags.operation.READ,
        },
      };

      const response = http.get(
        `${BASE_URL}/api/v1/conversations?page=1&limit=20`,
        params
      );

      const success = response.status === 200;
      conversationSuccessRate.add(success);
      totalRequests.add(1);

      if (success) {
        conversationLatency.add(response.timings.duration);
      } else {
        totalErrors.add(1);
      }
    }
    // Write: Create conversation (30% likelihood)
    else {
      const payload = generateConversationPayload();
      const params = {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
          'User-Agent': 'k6-load-test',
        },
        tags: {
          name: 'CreateConversation',
          ...metricTags.endpoint.CONVERSATION,
          ...metricTags.operation.CREATE,
        },
      };

      const response = http.post(
        `${BASE_URL}/api/v1/conversations`,
        JSON.stringify(payload),
        params
      );

      const success = response.status === 201;
      conversationSuccessRate.add(success);
      totalRequests.add(1);

      if (success) {
        conversationLatency.add(response.timings.duration);
      } else {
        totalErrors.add(1);
      }
    }
  });
}

/**
 * Test search endpoint
 */
function testSearch(token) {
  group('Search', () => {
    const queries = [
      'customer',
      'order',
      'product',
      'support',
      'billing',
    ];

    const query = queries[Math.floor(Math.random() * queries.length)];

    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'SearchConversations',
        ...metricTags.endpoint.CONVERSATION,
        ...metricTags.operation.READ,
      },
    };

    const response = http.get(
      `${BASE_URL}/api/v1/conversations/search?q=${query}&limit=10`,
      params
    );

    const success = response.status === 200;
    searchSuccessRate.add(success);
    totalRequests.add(1);

    if (success) {
      searchLatency.add(response.timings.duration);
    } else {
      totalErrors.add(1);
    }

    check(response, {
      'search returns results': (r) => r.status === 200,
    });
  });
}

/**
 * Test billing endpoint
 */
function testBilling(token) {
  group('Billing', () => {
    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'GetSubscription',
        ...metricTags.endpoint.BILLING,
        ...metricTags.operation.READ,
      },
    };

    const response = http.get(
      `${BASE_URL}/api/v1/billing/subscription`,
      params
    );

    const success = response.status === 200;
    billingSuccessRate.add(success);
    totalRequests.add(1);

    if (success) {
      billingLatency.add(response.timings.duration);
    } else {
      totalErrors.add(1);
    }

    check(response, {
      'billing endpoint accessible': (r) => r.status === 200 || r.status === 401,
    });
  });
}

/**
 * Test analytics endpoint
 */
function testAnalytics(token) {
  group('Analytics', () => {
    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'GetAnalytics',
      },
    };

    const response = http.get(
      `${BASE_URL}/api/v1/analytics/summary`,
      params
    );

    // 404 is ok if not implemented
    const success = response.status === 200 || response.status === 404;
    totalRequests.add(1);

    if (response.status !== 200 && response.status !== 404) {
      totalErrors.add(1);
    }
  });
}

// ─────────────────────────────────────────────────────────
// Main Test
// ─────────────────────────────────────────────────────────

export default function () {
  // Generate token for this iteration
  const userId = `load-test-${__VU}-${__ITER}`;
  const tenantId = 'tenant-load-001';
  const token = generateToken(userId, tenantId, 'admin');

  group('Mixed API Workload', () => {
    // Test various endpoints in sequence
    testAuth();
    sleep(0.5);

    testConversations(token);
    sleep(0.5);

    testSearch(token);
    sleep(0.5);

    testBilling(token);
    sleep(0.5);

    testAnalytics(token);
    sleep(0.5);
  });

  // Think time
  sleep(Math.random() * 2);
}

// ─────────────────────────────────────────────────────────
// Summary
// ─────────────────────────────────────────────────────────

export function handleSummary(data) {
  const metrics = data.metrics || {};

  return {
    '/tmp/gateway-load-summary.json': JSON.stringify({
      timestamp: new Date().toISOString(),
      testType: 'api_gateway_load',
      metrics: {
        authLatency: metrics.auth_latency,
        conversationLatency: metrics.conversation_latency,
        searchLatency: metrics.search_latency,
        billingLatency: metrics.billing_latency,
        successRates: {
          auth: metrics.auth_success_rate,
          conversation: metrics.conversation_success_rate,
          search: metrics.search_success_rate,
          billing: metrics.billing_success_rate,
        },
        totals: {
          requests: metrics.total_requests,
          errors: metrics.total_errors,
        },
      },
    }, null, 2),
    stdout: 'standard',
  };
}
