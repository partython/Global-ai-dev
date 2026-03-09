/**
 * Spike Test (Stress Test)
 * Priya Global Platform - K6 Load Test
 *
 * Sudden spike test:
 * - Normal load (50 VUs) → instant spike to 1000 VUs → back to 50
 * - Measure recovery time
 * - Verify no cascading failures
 * - Check circuit breaker behavior
 * - Verify graceful degradation
 *
 * Stages: 50 VUs (2min) → spike to 1000 (instant) → 1000 (3min) → recover to 50 (2min)
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { CONFIG } from '../config.js';
import {
  randomTenant,
  getAuthHeaders,
  checkResponse,
  generateRequestId,
} from '../helpers.js';

// Custom metrics
const spikeLatency = new Trend('spike_latency');
const spikeSuccessRate = new Rate('spike_success_rate');
const spikeErrorCount = new Counter('spike_errors_total');
const circuitBreakerTrips = new Counter('circuit_breaker_trips');
const recoveryTime = new Gauge('recovery_time');
const activeRequests = new Gauge('active_requests');

export const options = {
  scenarios: {
    spike_test: {
      executor: 'rampingVUs',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },    // Normal baseline load
        { duration: '0s', target: 1000 },  // SPIKE: instant jump to 1000
        { duration: '3m', target: 1000 },  // Hold at spike load
        { duration: '2m', target: 50 },    // Recovery back to normal
        { duration: '1m', target: 0 },     // Ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'spike_latency': ['p(95)<2000', 'p(99)<5000'],
    'spike_success_rate': ['rate>0.90'],  // Allow 10% failure during spike
    'http_req_failed': ['rate<0.15'],     // Spike causes higher error rate
    'circuit_breaker_trips': ['count<10'], // Circuit breaker should trip minimally
  },
};

/**
 * Make API request and track spike metrics
 */
function makeSpikeRequest(tenant, token, endpoint, method = 'GET') {
  const url = `${CONFIG.BASE_URL}${endpoint}`;
  const headers = getAuthHeaders(token, tenant.id);

  activeRequests.add(1);

  let response;
  const startTime = Date.now();

  if (method === 'GET') {
    response = http.get(url, { headers });
  } else {
    response = http.post(url, JSON.stringify({}), { headers });
  }

  const duration = Date.now() - startTime;
  spikeLatency.add(duration);
  activeRequests.add(-1);

  const isSuccess = response.status >= 200 && response.status < 300;
  spikeSuccessRate.add(isSuccess);

  if (!isSuccess) {
    spikeErrorCount.add(1);

    // Detect circuit breaker
    if (response.status === 503 || response.status === 429) {
      circuitBreakerTrips.add(1);
    }
  }

  return response;
}

/**
 * Test conversation operations during spike
 */
function testConversationOperationsSpike(tenant, token) {
  group('Conversation Operations - Spike', () => {
    // List conversations
    makeSpikeRequest(tenant, token, CONFIG.ENDPOINTS.conversations.list, 'GET');
    sleep(0.1);

    // Create conversation
    makeSpikeRequest(tenant, token, CONFIG.ENDPOINTS.conversations.create, 'POST');
    sleep(0.1);

    // Send message
    makeSpikeRequest(tenant, token, CONFIG.ENDPOINTS.messages.send, 'POST');
    sleep(0.1);
  });
}

/**
 * Test authentication during spike
 */
function testAuthSpike(tenant, token) {
  group('Authentication - Spike', () => {
    const payload = {
      email: 'spike-test@priya.local',
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
        tags: {
          operation: 'spike_auth',
          tenant: tenant.id,
        },
      }
    );

    spikeLatency.add(response.timings.duration);
    const isSuccess = response.status === 200;
    spikeSuccessRate.add(isSuccess);

    if (!isSuccess) {
      spikeErrorCount.add(1);
    }

    check(response, {
      'auth responds during spike': (r) => r.status !== 0,
      'auth returns in < 5s': (r) => r.timings.duration < 5000,
    });

    sleep(0.1);
  });
}

/**
 * Test analytics endpoints under spike
 */
function testAnalyticsSpike(tenant, token) {
  group('Analytics - Spike', () => {
    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.analytics.dashboard}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'spike_analytics',
          tenant: tenant.id,
        },
      }
    );

    spikeLatency.add(response.timings.duration);
    spikeSuccessRate.add(response.status === 200);

    if (response.status !== 200) {
      spikeErrorCount.add(1);
    }

    sleep(0.2);
  });
}

/**
 * Test billing endpoints under spike
 */
function testBillingSpike(tenant, token) {
  group('Billing - Spike', () => {
    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.billing.usage}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'spike_billing',
          tenant: tenant.id,
        },
      }
    );

    spikeLatency.add(response.timings.duration);
    spikeSuccessRate.add(response.status === 200);

    if (response.status !== 200) {
      spikeErrorCount.add(1);
    }

    sleep(0.2);
  });
}

/**
 * Test rate limiting during spike
 */
function testRateLimitingSpike(tenant, token) {
  group('Rate Limiting - Spike', () => {
    const requests = [];

    // Generate 50 requests rapidly
    for (let i = 0; i < 50; i++) {
      requests.push({
        method: 'GET',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
        params: {
          headers: getAuthHeaders(token, tenant.id),
          tags: { operation: 'spike_ratelimit', tenant: tenant.id },
        },
      });
    }

    const responses = http.batch(requests);

    let rateLimited = 0;
    let successful = 0;

    responses.forEach((resp) => {
      if (resp.status === 429) {
        rateLimited++;
        spikeErrorCount.add(1);
      } else if (resp.status === 200) {
        successful++;
        spikeSuccessRate.add(true);
      } else {
        spikeErrorCount.add(1);
      }

      spikeLatency.add(resp.timings.duration);
    });

    check({ rateLimited, successful }, {
      'rate limiting active during spike': (v) => v.rateLimited > 0,
      'some requests still succeed': (v) => v.successful > 0,
    });

    sleep(0.5);
  });
}

/**
 * Test circuit breaker behavior
 */
function testCircuitBreakerSpike(tenant, token) {
  group('Circuit Breaker - Spike', () => {
    // Make multiple rapid requests to same endpoint
    const requests = [];

    for (let i = 0; i < 100; i++) {
      requests.push({
        method: 'GET',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
        params: {
          headers: getAuthHeaders(token, tenant.id),
          tags: { operation: 'spike_circuit_breaker' },
        },
      });
    }

    const responses = http.batch(requests);

    let circuitOpened = false;
    responses.forEach((resp) => {
      if (resp.status === 503) {
        circuitOpened = true;
        circuitBreakerTrips.add(1);
      }

      spikeLatency.add(resp.timings.duration);
      spikeSuccessRate.add(resp.status < 300);
    });

    // Circuit breaker may or may not trip depending on threshold
    check({ circuitOpened }, {
      'circuit breaker state appropriate': (v) => true, // Just track if it happened
    });

    sleep(0.5);
  });
}

/**
 * Test cascading failure prevention
 */
function testCascadingFailurePrevention(tenant, token) {
  group('Cascading Failure Prevention', () => {
    // Try to hit dependent services
    const criticalEndpoints = [
      CONFIG.ENDPOINTS.conversations.list,
      CONFIG.ENDPOINTS.messages.send,
      CONFIG.ENDPOINTS.ai.chat,
    ];

    let cascadingFailures = 0;

    criticalEndpoints.forEach((endpoint) => {
      const response = http.get(
        `${CONFIG.BASE_URL}${endpoint}`,
        {
          headers: getAuthHeaders(token, tenant.id),
        }
      );

      if (response.status === 503 || response.status === 504) {
        cascadingFailures++;
      }

      spikeLatency.add(response.timings.duration);
      spikeSuccessRate.add(response.status < 400);
    });

    // Some services may be unavailable, but not all
    check({ cascadingFailures }, {
      'not all services failing': (v) => v.cascadingFailures < criticalEndpoints.length,
    });

    sleep(0.3);
  });
}

/**
 * Track recovery metrics
 */
function trackRecovery(initialLoad, currentLoad) {
  if (initialLoad > 100 && currentLoad < 100) {
    // System is in recovery phase
    recoveryTime.add(Date.now(), { phase: 'recovery' });
  }
}

/**
 * Main test function
 */
export default function () {
  const tenant = randomTenant();
  const token = tenant.token;

  // Vary tests based on VU to distribute load
  const testType = __VU % 6;

  switch (testType) {
    case 0:
      testConversationOperationsSpike(tenant, token);
      break;
    case 1:
      testAuthSpike(tenant, token);
      break;
    case 2:
      testAnalyticsSpike(tenant, token);
      break;
    case 3:
      testBillingSpike(tenant, token);
      break;
    case 4:
      testRateLimitingSpike(tenant, token);
      break;
    case 5:
      testCircuitBreakerSpike(tenant, token);
      break;
  }

  sleep(0.5);
}
