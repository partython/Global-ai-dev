/**
 * K6 Helper Functions and Utilities
 * Priya Global Platform Load Testing
 *
 * Shared utilities for authentication, data generation, response validation,
 * and common test operations
 */

import http from 'k6/http';
import { check, group } from 'k6';
import { CONFIG } from './config.js';

/**
 * Authenticate a user and retrieve JWT token
 * @param {Object} tenant - Tenant configuration object
 * @returns {Object} - { token, tenantId, userId }
 */
export function authenticateUser(tenant) {
  const payload = {
    email: `user-${tenant.id}@priya.local`,
    password: 'TestPassword123!',
  };

  const response = http.post(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.login}`,
    JSON.stringify(payload),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': tenant.id,
        'X-Request-ID': generateRequestId(),
      },
    }
  );

  return {
    token: response.json('access_token') || tenant.token,
    tenantId: tenant.id,
    userId: response.json('user_id') || 'test-user',
    expiresAt: Date.now() + 15 * 60 * 1000, // 15 minute expiry
  };
}

/**
 * Refresh JWT token
 * @param {string} refreshToken - Refresh token from login response
 * @param {string} tenantId - Tenant identifier
 * @returns {Object} - { token, expiresAt }
 */
export function refreshToken(refreshToken, tenantId) {
  const payload = { refresh_token: refreshToken };

  const response = http.post(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.refresh}`,
    JSON.stringify(payload),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Tenant-ID': tenantId,
        'X-Request-ID': generateRequestId(),
      },
    }
  );

  return {
    token: response.json('access_token'),
    expiresAt: Date.now() + 15 * 60 * 1000,
  };
}

/**
 * Get authorization headers with JWT token
 * @param {string} token - JWT token
 * @param {string} tenantId - Tenant ID
 * @returns {Object} - HTTP headers
 */
export function getAuthHeaders(token, tenantId) {
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'X-Tenant-ID': tenantId,
    'X-Request-ID': generateRequestId(),
    'Accept': 'application/json',
  };
}

/**
 * Select random tenant from test pool
 * @returns {Object} - Tenant configuration
 */
export function randomTenant() {
  return CONFIG.TENANTS[Math.floor(Math.random() * CONFIG.TENANTS.length)];
}

/**
 * Select random region based on traffic distribution
 * @returns {string} - Region code (IN, US, EU, ME, AP)
 */
export function randomRegion() {
  const rand = Math.random();
  let cumulative = 0;

  for (const [region, config] of Object.entries(CONFIG.REGIONS)) {
    cumulative += config.weight;
    if (rand <= cumulative) {
      return region;
    }
  }

  return 'IN'; // default fallback
}

/**
 * Generate realistic conversation payload
 * @param {string} channel - Communication channel (whatsapp, email, etc)
 * @param {string} tenantId - Tenant ID
 * @returns {Object} - Conversation payload
 */
export function randomConversation(channel = null, tenantId = null) {
  const selectedChannel = channel || CONFIG.CHANNELS[
    Math.floor(Math.random() * CONFIG.CHANNELS.length)
  ];
  const tenant = tenantId ? { id: tenantId } : randomTenant();

  return {
    channel: selectedChannel,
    customer_name: generateIndianName(),
    customer_phone: generateIndianPhoneNumber(),
    customer_email: generateEmail(),
    metadata: {
      source: 'load-test',
      campaign_id: `campaign-${Math.random().toString(36).substr(2, 9)}`,
      region: randomRegion(),
    },
  };
}

/**
 * Generate realistic message payload
 * @param {string} conversationId - Conversation ID
 * @param {string} channel - Message channel
 * @returns {Object} - Message payload
 */
export function randomMessage(conversationId, channel = 'webchat') {
  const templates = CONFIG.MESSAGE_TEMPLATES;
  const template = templates[Math.floor(Math.random() * templates.length)];

  return {
    conversation_id: conversationId,
    channel: channel,
    text: template,
    sender: 'customer',
    metadata: {
      timestamp: new Date().toISOString(),
      locale: Math.random() > 0.5 ? 'en-IN' : 'hi-IN',
      client_id: `client-${Math.random().toString(36).substr(2, 9)}`,
    },
  };
}

/**
 * Check HTTP response and validate status
 * @param {Object} response - k6 HTTP response
 * @param {number} expectedStatus - Expected HTTP status code
 * @param {Object} expectations - Additional assertions
 * @returns {boolean} - Check result
 */
export function checkResponse(response, expectedStatus = 200, expectations = {}) {
  const checks = {
    [`status is ${expectedStatus}`]: (r) => r.status === expectedStatus,
    'response has body': (r) => r.body.length > 0,
    'response time < 5s': (r) => r.timings.duration < 5000,
    ...expectations,
  };

  return check(response, checks);
}

/**
 * Assert successful response with custom metrics
 * @param {Object} response - k6 HTTP response
 * @param {string} name - Operation name for metrics
 * @returns {boolean} - Check result
 */
export function assertSuccess(response, name = 'operation') {
  return checkResponse(response, 200, {
    'content-type is json': (r) => r.headers['Content-Type']?.includes('application/json'),
  });
}

/**
 * Assert rate limit headers present
 * @param {Object} response - k6 HTTP response
 * @returns {boolean} - Check result
 */
export function assertRateLimitHeaders(response) {
  return check(response, {
    'has x-ratelimit-limit': (r) => 'x-ratelimit-limit' in r.headers,
    'has x-ratelimit-remaining': (r) => 'x-ratelimit-remaining' in r.headers,
    'has x-ratelimit-reset': (r) => 'x-ratelimit-reset' in r.headers,
  });
}

/**
 * Generate Indian phone number (test format - not real)
 * @returns {string} - Phone number for testing (not real numbers)
 */
export function generateIndianPhoneNumber() {
  // SECURITY: Generate non-existent test phone numbers using reserved test range
  // Use +919999XXXXXX format (reserved for testing, never assigned)
  const testPrefix = '+919999';
  const restDigits = Array.from({ length: 6 }, () =>
    Math.floor(Math.random() * 10)
  ).join('');

  return `${testPrefix}${restDigits}`;
}

/**
 * Generate Indian name
 * @returns {string} - Realistic Indian name
 */
export function generateIndianName() {
  const firstNames = [
    'Raj', 'Priya', 'Amit', 'Anjali', 'Arjun', 'Deepa', 'Vikram', 'Neha',
    'Rohan', 'Isha', 'Arun', 'Divya', 'Sanjay', 'Pooja', 'Rahul', 'Kavya',
  ];
  const lastNames = [
    'Sharma', 'Singh', 'Patel', 'Verma', 'Kumar', 'Gupta', 'Iyer', 'Reddy',
    'Nair', 'Rao', 'Yadav', 'Desai', 'Kapoor', 'Chopra', 'Banerjee', 'Das',
  ];

  const firstName = firstNames[Math.floor(Math.random() * firstNames.length)];
  const lastName = lastNames[Math.floor(Math.random() * lastNames.length)];

  return `${firstName} ${lastName}`;
}

/**
 * Generate test email address (not real)
 * @returns {string} - Test email address using .test domain (RFC reserved)
 */
export function generateEmail() {
  // SECURITY: Use .test TLD (RFC 6761 reserved for testing)
  // Prevents accidental enumeration of real email addresses
  const timestamp = Date.now();
  const random = Math.random().toString(36).substr(2, 9);

  return `loadtest-${timestamp}-${random}@priya.test`;
}

/**
 * Generate unique request ID for tracing
 * @returns {string} - Request ID
 */
export function generateRequestId() {
  return `req-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Parse tenant from response headers
 * @param {Object} response - k6 HTTP response
 * @returns {string} - Tenant ID
 */
export function getTenantFromResponse(response) {
  return response.headers['X-Tenant-ID'] || 'unknown';
}

/**
 * Create WebSocket connection headers
 * @param {string} token - JWT token
 * @param {string} tenantId - Tenant ID
 * @returns {Object} - WebSocket connection headers
 */
export function getWebSocketHeaders(token, tenantId) {
  return {
    headers: {
      'Authorization': `Bearer ${token}`,
      'X-Tenant-ID': tenantId,
      'X-Request-ID': generateRequestId(),
    },
  };
}

/**
 * Sleep for specified milliseconds
 * @param {number} ms - Milliseconds to sleep
 */
export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Calculate average of array
 * @param {number[]} arr - Array of numbers
 * @returns {number} - Average value
 */
export function average(arr) {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

/**
 * Calculate percentile of array
 * @param {number[]} arr - Array of numbers
 * @param {number} percentile - Percentile (0-100)
 * @returns {number} - Percentile value
 */
export function calculatePercentile(arr, percentile) {
  if (arr.length === 0) return 0;
  const sorted = arr.sort((a, b) => a - b);
  const index = Math.ceil((percentile / 100) * sorted.length) - 1;
  return sorted[Math.max(0, index)];
}

export default {
  authenticateUser,
  refreshToken,
  getAuthHeaders,
  randomTenant,
  randomRegion,
  randomConversation,
  randomMessage,
  checkResponse,
  assertSuccess,
  assertRateLimitHeaders,
  generateIndianPhoneNumber,
  generateIndianName,
  generateEmail,
  generateRequestId,
  getTenantFromResponse,
  getWebSocketHeaders,
  sleep,
  average,
  calculatePercentile,
};
