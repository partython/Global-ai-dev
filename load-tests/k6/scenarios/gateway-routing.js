/**
 * Gateway Routing Performance Test
 * Priya Global Platform - K6 Load Test
 *
 * Tests gateway proxy performance, request routing latency, and
 * error handling across all major API endpoints
 *
 * Stages: 0→50 VUs (2min), hold 50 (5min), 50→200 (3min), hold 200 (5min), ramp down (2min)
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { CONFIG } from '../config.js';
import {
  randomTenant,
  getAuthHeaders,
  checkResponse,
  generateRequestId,
} from '../helpers.js';

// Custom metrics
const routingLatency = new Trend('routing_latency');
const proxyOverhead = new Trend('proxy_overhead');
const gatewayErrors = new Counter('gateway_errors_total');
const successRate = new Rate('gateway_success_rate');

// Test configuration
export const options = {
  scenarios: {
    gateway_routing: {
      executor: 'rampingVUs',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },    // Ramp up
        { duration: '5m', target: 50 },    // Hold
        { duration: '3m', target: 200 },   // Ramp to high load
        { duration: '5m', target: 200 },   // Hold at high load
        { duration: '2m', target: 0 },     // Ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'routing_latency': CONFIG.THRESHOLDS['http_req_duration'],
    'gateway_success_rate': ['rate>0.99'],
    'http_req_failed': ['rate<0.01'],
  },
};

/**
 * Test gateway routing for authentication endpoints
 */
function testAuthRouting(tenant, token) {
  group('Auth Endpoint Routing', () => {
    // Test login endpoint routing
    const loginPayload = {
      email: 'test@priya.local',
      password: 'TestPassword123!',
    };

    const loginResp = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.login}`,
      JSON.stringify(loginPayload),
      {
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-ID': tenant.id,
          'X-Request-ID': generateRequestId(),
        },
        tags: { endpoint: 'auth-login', service: 'auth' },
      }
    );

    routingLatency.add(loginResp.timings.duration);
    const loginSuccess = checkResponse(loginResp, 200);
    successRate.add(loginSuccess);
    if (!loginSuccess) gatewayErrors.add(1);

    sleep(0.1);

    // Test token refresh endpoint
    const refreshPayload = { refresh_token: 'test-refresh-token' };
    const refreshResp = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.refresh}`,
      JSON.stringify(refreshPayload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'auth-refresh', service: 'auth' },
      }
    );

    routingLatency.add(refreshResp.timings.duration);
    const refreshSuccess = checkResponse(refreshResp, [200, 401]);
    successRate.add(refreshSuccess);
    if (!refreshSuccess) gatewayErrors.add(1);

    sleep(0.1);
  });
}

/**
 * Test gateway routing for conversation endpoints
 */
function testConversationRouting(tenant, token) {
  group('Conversation Endpoint Routing', () => {
    // Test list conversations
    const listResp = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'conversation-list', service: 'conversation' },
      }
    );

    routingLatency.add(listResp.timings.duration);
    const listSuccess = checkResponse(listResp, 200);
    successRate.add(listSuccess);
    if (!listSuccess) gatewayErrors.add(1);

    sleep(0.1);

    // Test create conversation
    const createPayload = {
      channel: 'webchat',
      customer_name: 'Test Customer',
      customer_phone: '+911234567890',
      customer_email: 'test@priya.local',
    };

    const createResp = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.create}`,
      JSON.stringify(createPayload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'conversation-create', service: 'conversation' },
      }
    );

    routingLatency.add(createResp.timings.duration);
    const createSuccess = checkResponse(createResp, [200, 201]);
    successRate.add(createSuccess);
    if (!createSuccess) gatewayErrors.add(1);

    sleep(0.1);
  });
}

/**
 * Test gateway routing for message endpoints
 */
function testMessageRouting(tenant, token) {
  group('Message Endpoint Routing', () => {
    // Test send message
    const messagePayload = {
      conversation_id: 'test-conv-' + Math.random().toString(36).substr(2, 9),
      channel: 'webchat',
      text: 'Test message from load test',
      sender: 'customer',
    };

    const sendResp = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.messages.send}`,
      JSON.stringify(messagePayload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'message-send', service: 'message' },
      }
    );

    routingLatency.add(sendResp.timings.duration);
    const sendSuccess = checkResponse(sendResp, [200, 201]);
    successRate.add(sendSuccess);
    if (!sendSuccess) gatewayErrors.add(1);

    sleep(0.1);

    // Test list messages
    const listResp = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.messages.list}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'message-list', service: 'message' },
      }
    );

    routingLatency.add(listResp.timings.duration);
    const listSuccess = checkResponse(listResp, 200);
    successRate.add(listSuccess);
    if (!listSuccess) gatewayErrors.add(1);

    sleep(0.1);
  });
}

/**
 * Test gateway routing for channel endpoints
 */
function testChannelRouting(tenant, token) {
  group('Channel Endpoint Routing', () => {
    // Test list channels
    const listResp = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.channels.list}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'channel-list', service: 'channel' },
      }
    );

    routingLatency.add(listResp.timings.duration);
    const listSuccess = checkResponse(listResp, 200);
    successRate.add(listSuccess);
    if (!listSuccess) gatewayErrors.add(1);

    sleep(0.1);
  });
}

/**
 * Test gateway routing for AI endpoints
 */
function testAIRouting(tenant, token) {
  group('AI Endpoint Routing', () => {
    // Test AI chat
    const chatPayload = {
      conversation_id: 'test-conv-' + Math.random().toString(36).substr(2, 9),
      message: 'Hello, can you help me?',
    };

    const chatResp = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.ai.chat}`,
      JSON.stringify(chatPayload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'ai-chat', service: 'ai' },
      }
    );

    routingLatency.add(chatResp.timings.duration);
    const chatSuccess = checkResponse(chatResp, [200, 202]);
    successRate.add(chatSuccess);
    if (!chatSuccess) gatewayErrors.add(1);

    sleep(0.1);
  });
}

/**
 * Test gateway routing for analytics endpoints
 */
function testAnalyticsRouting(tenant, token) {
  group('Analytics Endpoint Routing', () => {
    // Test dashboard endpoint
    const dashboardResp = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.analytics.dashboard}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'analytics-dashboard', service: 'analytics' },
      }
    );

    routingLatency.add(dashboardResp.timings.duration);
    const dashboardSuccess = checkResponse(dashboardResp, 200);
    successRate.add(dashboardSuccess);
    if (!dashboardSuccess) gatewayErrors.add(1);

    sleep(0.1);
  });
}

/**
 * Test gateway health and rate limit header propagation
 */
function testGatewayHeaders(tenant, token) {
  group('Gateway Header Propagation', () => {
    const resp = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { endpoint: 'headers-check', service: 'gateway' },
      }
    );

    check(resp, {
      'has request-id header': (r) => 'x-request-id' in r.headers || 'X-Request-ID' in r.headers,
      'has tenant-id header': (r) => 'x-tenant-id' in r.headers || 'X-Tenant-ID' in r.headers,
      'has cache headers': (r) => 'cache-control' in r.headers || 'Cache-Control' in r.headers,
    });

    sleep(0.1);
  });
}

/**
 * Main load test function
 */
export default function () {
  const tenant = randomTenant();
  const token = tenant.token;

  // Execute routing tests in sequence
  testAuthRouting(tenant, token);
  sleep(0.2);

  testConversationRouting(tenant, token);
  sleep(0.2);

  testMessageRouting(tenant, token);
  sleep(0.2);

  testChannelRouting(tenant, token);
  sleep(0.2);

  testAIRouting(tenant, token);
  sleep(0.2);

  testAnalyticsRouting(tenant, token);
  sleep(0.2);

  testGatewayHeaders(tenant, token);
  sleep(0.5);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
  };
}
