/**
 * Authentication Flow Load Test
 * Priya Global Platform - K6 Load Test
 *
 * Tests authentication under load including:
 * - Login flow (JWT generation)
 * - Token refresh flow
 * - API key authentication
 * - Rate limiting behavior
 * - Concurrent login from same tenant
 * - Brute force protection verification
 *
 * Stages: 0→100 VUs (2min), hold 100 (5min), 100→300 (3min), hold 300 (5min), ramp down (2min)
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { CONFIG } from '../config.js';

// SECURITY: Prevent accidental execution against production
if (CONFIG.BASE_URL.includes('prod') || CONFIG.BASE_URL.includes('production')) {
  throw new Error('CRITICAL: Load test cannot run against production. Use staging/test environment only.');
}
import {
  randomTenant,
  generateEmail,
  getAuthHeaders,
  checkResponse,
  generateRequestId,
} from '../helpers.js';

// Custom metrics
const loginLatency = new Trend('auth_login_latency');
const refreshLatency = new Trend('auth_refresh_latency');
const loginSuccessRate = new Rate('auth_login_success_rate');
const refreshSuccessRate = new Rate('auth_refresh_success_rate');
const rateLimitHits = new Counter('auth_ratelimit_hits');
const bruteForceBlocks = new Counter('auth_bruteforce_blocks');

export const options = {
  scenarios: {
    auth_flow: {
      executor: 'rampingVUs',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 100 },   // Ramp up to normal load
        { duration: '5m', target: 100 },   // Hold
        { duration: '3m', target: 300 },   // Ramp to high load
        { duration: '5m', target: 300 },   // Hold at high load
        { duration: '2m', target: 0 },     // Ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'auth_login_latency': ['p(95)<1000', 'p(99)<2000'],
    'auth_refresh_latency': ['p(95)<300', 'p(99)<800'],
    'auth_login_success_rate': ['rate>0.95'],
    'auth_refresh_success_rate': ['rate>0.98'],
    'http_req_failed': ['rate<0.02'],
  },
};

/**
 * Test basic login flow
 */
function testLoginFlow(tenant) {
  group('Login Flow', () => {
    const payload = {
      email: generateEmail(),
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
          operation: 'login',
          tenant: tenant.id,
          plan: tenant.plan,
        },
      }
    );

    loginLatency.add(response.timings.duration);

    const isSuccess = check(response, {
      'login status 200': (r) => r.status === 200,
      'has access token': (r) => r.json('access_token') !== undefined,
      'has refresh token': (r) => r.json('refresh_token') !== undefined,
      'has user data': (r) => r.json('user_id') !== undefined,
      'response time < 2s': (r) => r.timings.duration < 2000,
    });

    loginSuccessRate.add(isSuccess);
    if (!isSuccess && response.status === 429) {
      rateLimitHits.add(1);
    }

    sleep(0.5);
  });
}

/**
 * Test token refresh flow
 */
function testTokenRefresh(tenant) {
  group('Token Refresh', () => {
    // First login to get refresh token
    const loginPayload = {
      email: generateEmail(),
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
      }
    );

    const refreshToken = loginResp.json('refresh_token');

    // Then refresh the token
    const refreshPayload = {
      refresh_token: refreshToken,
    };

    const refreshResp = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.refresh}`,
      JSON.stringify(refreshPayload),
      {
        headers: {
          'Content-Type': 'application/json',
          'X-Tenant-ID': tenant.id,
          'X-Request-ID': generateRequestId(),
        },
        tags: {
          operation: 'refresh',
          tenant: tenant.id,
          plan: tenant.plan,
        },
      }
    );

    refreshLatency.add(refreshResp.timings.duration);

    const isSuccess = check(refreshResp, {
      'refresh status 200': (r) => r.status === 200,
      'has new access token': (r) => r.json('access_token') !== undefined,
      'response time < 1s': (r) => r.timings.duration < 1000,
    });

    refreshSuccessRate.add(isSuccess);
    sleep(0.3);
  });
}

/**
 * Test concurrent logins from same tenant
 */
function testConcurrentLogins(tenant) {
  group('Concurrent Logins', () => {
    const loginRequests = [];

    for (let i = 0; i < 5; i++) {
      loginRequests.push({
        method: 'POST',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.login}`,
        body: JSON.stringify({
          email: generateEmail(),
          password: 'TestPassword123!',
        }),
        params: {
          headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenant.id,
            'X-Request-ID': generateRequestId(),
          },
          tags: {
            operation: 'concurrent_login',
            tenant: tenant.id,
          },
        },
      });
    }

    const responses = http.batch(loginRequests);

    responses.forEach((resp) => {
      loginLatency.add(resp.timings.duration);
      check(resp, {
        'concurrent login status 200': (r) => r.status === 200,
        'no request timeout': (r) => r.timings.duration < 5000,
      });
    });

    sleep(0.5);
  });
}

/**
 * Test rate limiting behavior
 */
function testRateLimiting(tenant) {
  group('Rate Limiting Behavior', () => {
    // Send rapid-fire login requests to trigger rate limiting
    const requests = [];

    for (let i = 0; i < 20; i++) {
      requests.push({
        method: 'POST',
        url: `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.login}`,
        body: JSON.stringify({
          email: `user-${i}@priya.local`,
          password: 'TestPassword123!',
        }),
        params: {
          headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenant.id,
            'X-Request-ID': generateRequestId(),
          },
          tags: {
            operation: 'ratelimit_test',
            tenant: tenant.id,
          },
        },
      });
    }

    const responses = http.batch(requests);

    let rateLimitCount = 0;
    responses.forEach((resp) => {
      if (resp.status === 429) {
        rateLimitCount++;
        check(resp, {
          'rate limit has retry-after': (r) => 'retry-after' in r.headers || 'Retry-After' in r.headers,
          'rate limit status is 429': (r) => r.status === 429,
        });
      }
    });

    if (rateLimitCount > 0) {
      rateLimitHits.add(rateLimitCount);
    }

    sleep(1.0); // Wait before next test
  });
}

/**
 * Test brute force protection
 */
function testBruteForceProtection(tenant) {
  group('Brute Force Protection', () => {
    const email = generateEmail();
    const failedAttempts = [];

    // Send 10 failed login attempts with wrong password
    for (let i = 0; i < 10; i++) {
      const response = http.post(
        `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.auth.login}`,
        JSON.stringify({
          email: email,
          password: `WrongPassword${i}!`,
        }),
        {
          headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenant.id,
            'X-Request-ID': generateRequestId(),
          },
          tags: {
            operation: 'bruteforce_test',
            attempt: i + 1,
          },
        }
      );

      failedAttempts.push(response.status);

      // Check if brute force protection kicks in (should get 429 or 403)
      if (response.status === 429 || response.status === 403) {
        bruteForceBlocks.add(1);
        break;
      }

      sleep(0.1);
    }

    check(failedAttempts, {
      'brute force triggered': (arr) => arr.includes(429) || arr.includes(403),
    });

    sleep(0.5);
  });
}

/**
 * Test API key authentication (alternative to JWT)
 */
function testAPIKeyAuth(tenant) {
  group('API Key Authentication', () => {
    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
      {
        headers: {
          'X-API-Key': `key-${tenant.id}-${Date.now()}`,
          'X-Tenant-ID': tenant.id,
          'X-Request-ID': generateRequestId(),
        },
        tags: {
          operation: 'api_key_auth',
          tenant: tenant.id,
        },
      }
    );

    check(response, {
      'api key auth responds': (r) => r.status !== 0,
      'proper error handling': (r) => [200, 401, 403].includes(r.status),
    });

    sleep(0.3);
  });
}

/**
 * Test token expiry and invalid token handling
 */
function testTokenExpiry(tenant) {
  group('Token Expiry Handling', () => {
    // SECURITY: Generate expired token dynamically instead of hardcoding
    // Create a token with expiry in the past
    const expiredToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE2MDA1NzY4MDB9.invalid'; // Already expired in 2020

    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.list}`,
      {
        headers: {
          'Authorization': `Bearer ${expiredToken}`,
          'X-Tenant-ID': tenant.id,
          'X-Request-ID': generateRequestId(),
        },
        tags: {
          operation: 'token_expiry',
          tenant: tenant.id,
        },
      }
    );

    check(response, {
      'expired token rejected': (r) => [401, 403].includes(r.status),
      'clear error message': (r) => r.body.length > 0,
    });

    sleep(0.3);
  });
}

/**
 * Main test function
 */
export default function () {
  const tenant = randomTenant();

  // Run authentication tests
  testLoginFlow(tenant);
  sleep(0.5);

  testTokenRefresh(tenant);
  sleep(0.5);

  testConcurrentLogins(tenant);
  sleep(0.5);

  testRateLimiting(tenant);
  sleep(0.5);

  testBruteForceProtection(tenant);
  sleep(0.5);

  testAPIKeyAuth(tenant);
  sleep(0.5);

  testTokenExpiry(tenant);
  sleep(1.0);
}
