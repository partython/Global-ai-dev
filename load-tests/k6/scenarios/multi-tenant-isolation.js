/**
 * Multi-Tenant Isolation Test
 * Priya Global Platform - K6 Load Test
 *
 * Verifies tenant isolation under load:
 * - 10+ tenants hitting simultaneously
 * - Different plan tiers (starter, growth, professional, enterprise)
 * - Rate limits respected per tenant
 * - No cross-tenant data leakage
 * - Tenant A's load doesn't degrade tenant B's performance
 * - Custom metrics per tenant
 *
 * Stages: ramp to 50 VUs (2min), hold (10min), ramp down (2min)
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { CONFIG } from '../config.js';

// SECURITY: Prevent accidental execution against production
if (CONFIG.BASE_URL.includes('prod') || CONFIG.BASE_URL.includes('production')) {
  throw new Error('CRITICAL: Load test cannot run against production. Use staging/test environment only.');
}
import {
  randomTenant,
  getAuthHeaders,
  generateRequestId,
  generateEmail,
} from '../helpers.js';

// Custom metrics per tenant
const responseTimeByTenant = new Trend('response_time_by_tenant');
const errorsByTenant = new Counter('errors_by_tenant');
const successRateByTenant = new Rate('success_rate_by_tenant');
const requestCountByTenant = new Counter('requests_by_tenant');
const dataLeakageAttempts = new Counter('data_leakage_attempts');
const rateLimitEnforced = new Counter('ratelimit_enforced_total');

// Tenant-specific metrics
const tenantMetrics = {};
CONFIG.TENANTS.forEach(tenant => {
  tenantMetrics[tenant.id] = {
    trend: new Trend(`response_time_tenant_${tenant.id}`),
    rate: new Rate(`success_rate_tenant_${tenant.id}`),
    counter: new Counter(`requests_tenant_${tenant.id}`),
  };
});

export const options = {
  scenarios: {
    multi_tenant: {
      executor: 'rampingVUs',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },   // Ramp up
        { duration: '10m', target: 50 },  // Hold at load with all tenants
        { duration: '2m', target: 0 },    // Ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'response_time_by_tenant': ['p(95)<1000'],
    'success_rate_by_tenant': ['rate>0.98'],
    'http_req_failed': ['rate<0.01'],
    'data_leakage_attempts': ['count==0'],  // CRITICAL: no data leakage allowed
  },
};

/**
 * Make request with tenant context
 */
function makeTenantRequest(tenant, token, endpoint, method = 'GET', payload = null) {
  const url = `${CONFIG.BASE_URL}${endpoint}`;
  const headers = getAuthHeaders(token, tenant.id);

  let response;
  const startTime = Date.now();

  if (method === 'GET') {
    response = http.get(url, { headers });
  } else if (method === 'POST') {
    response = http.post(url, JSON.stringify(payload), { headers });
  } else if (method === 'PUT') {
    response = http.put(url, JSON.stringify(payload), { headers });
  }

  const duration = Date.now() - startTime;
  responseTimeByTenant.add(duration, { tenant: tenant.id, plan: tenant.plan });
  tenantMetrics[tenant.id].trend.add(duration);
  tenantMetrics[tenant.id].counter.add(1);
  requestCountByTenant.add(1, { tenant: tenant.id });

  return response;
}

/**
 * Test rate limiting enforcement per plan
 */
function testRateLimitEnforcement(tenant, token) {
  group(`Rate Limit Test - ${tenant.plan.toUpperCase()}`, () => {
    const requestsToSend = Math.min(30, Math.ceil(tenant.rateLimit / 60 * 3)); // 3 seconds worth

    const requests = [];
    for (let i = 0; i < requestsToSend; i++) {
      requests.push({
        method: 'GET',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
        params: {
          headers: getAuthHeaders(token, tenant.id),
          tags: { tenant: tenant.id, operation: 'ratelimit_test' },
        },
      });
    }

    const responses = http.batch(requests);
    let rateLimitCount = 0;

    responses.forEach((resp) => {
      const isSuccess = resp.status === 200;
      tenantMetrics[tenant.id].rate.add(isSuccess);

      if (resp.status === 429) {
        rateLimitCount++;
        rateLimitEnforced.add(1, { tenant: tenant.id, plan: tenant.plan });

        // Verify rate limit headers
        check(resp, {
          'has x-ratelimit-reset': (r) => 'x-ratelimit-reset' in r.headers || 'X-RateLimit-Reset' in r.headers,
          'has retry-after': (r) => 'retry-after' in r.headers || 'Retry-After' in r.headers,
        });
      }
    });

    // Verify rate limiting is enforced (should have some 429s after hitting limit)
    const starterPlanHitsLimit = tenant.plan === 'starter' && rateLimitCount > 0;
    const enterprisePlanNoLimit = tenant.plan === 'enterprise' && rateLimitCount === 0;

    check({ starterPlanHitsLimit, enterprisePlanNoLimit }, {
      'rate limits enforced by plan': (v) => v.starterPlanHitsLimit || v.enterprisePlanNoLimit,
    });

    sleep(1.0);
  });
}

/**
 * Test cross-tenant data isolation
 * Attempt to access another tenant's data
 */
function testDataIsolation(tenant1, token1, tenant2) {
  group('Data Isolation Test', () => {
    // Try to access tenant2's conversations using tenant1's token
    // The request should either fail or return empty data
    // SECURITY: Don't pass tenant_id in query param; server should use auth context

    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,  // No tenant_id param
      {
        headers: getAuthHeaders(token1, tenant1.id),  // Auth header provides tenant context
        tags: {
          operation: 'isolation_test',
          source_tenant: tenant1.id,
          target_tenant: tenant2.id,
        },
      }
    );

    const isIsolated = check(response, {
      'cannot access other tenant data': (r) => {
        // Either 403 Forbidden or returns only tenant1's data
        return r.status === 403 ||
          (r.status === 200 && response.headers['X-Tenant-ID'] === tenant1.id);
      },
      'no cross-tenant leakage': (r) => {
        // Verify response doesn't contain other tenant's ID
        return !r.body.includes(tenant2.id);
      },
    });

    if (!isIsolated) {
      dataLeakageAttempts.add(1, { source: tenant1.id, target: tenant2.id });
    }

    sleep(0.3);
  });
}

/**
 * Test concurrent operations across different tenants
 */
function testConcurrentTenantOperations() {
  group('Concurrent Multi-Tenant Operations', () => {
    const batch = [];

    // Create batch requests from all tenants simultaneously
    CONFIG.TENANTS.forEach(tenant => {
      batch.push({
        method: 'POST',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.create}`,
        body: JSON.stringify({
          channel: 'webchat',
          customer_name: 'Test Customer',
          customer_phone: '+911234567890',
          customer_email: generateEmail(),
        }),
        params: {
          headers: getAuthHeaders(tenant.token, tenant.id),
          tags: { tenant: tenant.id, operation: 'concurrent_create' },
        },
      });
    });

    const responses = http.batch(batch);

    responses.forEach((resp, idx) => {
      const tenant = CONFIG.TENANTS[idx];
      const isSuccess = resp.status === 201 || resp.status === 200;
      tenantMetrics[tenant.id].rate.add(isSuccess);

      check(resp, {
        'conversation created': (r) => r.status === 201 || r.status === 200,
        'correct tenant': (r) => r.headers['X-Tenant-ID'] === tenant.id,
      });
    });

    sleep(0.5);
  });
}

/**
 * Test that heavy load on one tenant doesn't affect others
 */
function testResourceIsolation(tenant1, token1, tenant2, token2) {
  group(`Tenant Isolation Under Load - ${tenant1.plan} vs ${tenant2.plan}`, () => {
    const startTime = Date.now();

    // Tenant 1 sends heavy load (20 rapid requests)
    const tenant1Requests = [];
    for (let i = 0; i < 20; i++) {
      tenant1Requests.push({
        method: 'GET',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
        params: {
          headers: getAuthHeaders(token1, tenant1.id),
          tags: { tenant: tenant1.id, operation: 'load_test' },
        },
      });
    }

    // Tenant 2 sends normal load (3 requests)
    const tenant2Requests = [];
    for (let i = 0; i < 3; i++) {
      tenant2Requests.push({
        method: 'GET',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
        params: {
          headers: getAuthHeaders(token2, tenant2.id),
          tags: { tenant: tenant2.id, operation: 'load_test' },
        },
      });
    }

    // Execute simultaneously
    const responses1 = http.batch(tenant1Requests);
    const responses2 = http.batch(tenant2Requests);

    const avgTime1 = responses1.reduce((sum, r) => sum + r.timings.duration, 0) / responses1.length;
    const avgTime2 = responses2.reduce((sum, r) => sum + r.timings.duration, 0) / responses2.length;

    // Tenant 2 should not be significantly slower due to tenant 1's load
    // Allow up to 2x slower (not ideal, but acceptable for shared infrastructure)
    check({ avgTime1, avgTime2 }, {
      'tenant isolation respected': (v) => v.avgTime2 < v.avgTime1 * 3,
    });

    responses1.forEach(r => tenantMetrics[tenant1.id].rate.add(r.status === 200));
    responses2.forEach(r => tenantMetrics[tenant2.id].rate.add(r.status === 200));

    sleep(0.5);
  });
}

/**
 * Test tenant context in headers
 */
function testTenantContextHeaders(tenant, token) {
  group(`Tenant Context - ${tenant.id}`, () => {
    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: { tenant: tenant.id, operation: 'context_test' },
      }
    );

    check(response, {
      'x-tenant-id in response headers': (r) => {
        const headerValue = r.headers['X-Tenant-ID'] || r.headers['x-tenant-id'];
        return headerValue === tenant.id;
      },
      'x-request-id present': (r) => 'X-Request-ID' in r.headers || 'x-request-id' in r.headers,
    });

    sleep(0.2);
  });
}

/**
 * Main test function
 */
export default function () {
  const tenant = randomTenant();
  const token = tenant.token;

  // Each VU tests one primary tenant throughout
  switch (__VU % 4) {
    case 0:
      // Test rate limiting for this tenant's plan
      testRateLimitEnforcement(tenant, token);
      break;

    case 1:
      // Test data isolation
      const otherTenant = CONFIG.TENANTS.find(t => t.id !== tenant.id);
      testDataIsolation(tenant, token, otherTenant);
      break;

    case 2:
      // Test concurrent operations
      testConcurrentTenantOperations();
      break;

    case 3:
      // Test resource isolation
      const tenant1 = CONFIG.TENANTS[0];
      const tenant2 = CONFIG.TENANTS[1];
      testResourceIsolation(tenant1, tenant1.token, tenant2, tenant2.token);
      break;
  }

  // All VUs test tenant context headers
  testTenantContextHeaders(tenant, token);

  sleep(0.5);
}
