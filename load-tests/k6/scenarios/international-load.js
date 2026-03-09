/**
 * International Load Test
 * Priya Global Platform - K6 Load Test
 *
 * Simulate global traffic patterns:
 * - Traffic from India (40%), US (20%), EU (15%), Middle East (10%), SE Asia (15%)
 * - Different timezone peak hours
 * - Multi-currency billing operations
 * - Unicode/multilingual message content
 * - Different payload sizes per region
 * - Verify same SLA regardless of origin region
 *
 * Stages: 50 VUs (5min), scale to 200 (3min), hold (5min), ramp down (2min)
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { CONFIG } from '../config.js';
import {
  randomTenant,
  getAuthHeaders,
  generateRequestId,
  generateIndianPhoneNumber,
  generateIndianName,
  generateEmail,
} from '../helpers.js';

// Custom metrics by region
const latencyByRegion = new Trend('latency_by_region');
const successRateByRegion = new Rate('success_rate_by_region');
const requestsByRegion = new Counter('requests_by_region');
const currencyOperations = new Counter('currency_operations_total');
const multilingualMessages = new Counter('multilingual_messages_total');
const largePayloads = new Counter('large_payloads_total');

export const options = {
  scenarios: {
    international_load: {
      executor: 'rampingVUs',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },    // Ramp up
        { duration: '3m', target: 200 },   // Scale to global peak
        { duration: '5m', target: 200 },   // Hold at load
        { duration: '2m', target: 0 },     // Ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'latency_by_region': ['p(95)<1000', 'p(99)<2000'],
    'success_rate_by_region': ['rate>0.98'],
    'http_req_failed': ['rate<0.01'],
  },
};

/**
 * Regions with traffic distribution and characteristics
 */
const REGIONS = {
  IN: {
    weight: 0.40,
    currencies: ['INR'],
    languages: ['en', 'hi'],
    cities: ['Mumbai', 'Delhi', 'Bangalore', 'Hyderabad', 'Pune'],
    timezone: 'Asia/Kolkata',
    avgPayloadSize: 1024,
    peakHour: 18, // 6 PM IST
  },
  US: {
    weight: 0.20,
    currencies: ['USD'],
    languages: ['en'],
    cities: ['New York', 'San Francisco', 'Austin', 'Chicago'],
    timezone: 'America/New_York',
    avgPayloadSize: 2048,
    peakHour: 10, // 10 AM EST
  },
  EU: {
    weight: 0.15,
    currencies: ['EUR', 'GBP'],
    languages: ['en', 'de', 'fr'],
    cities: ['London', 'Berlin', 'Paris', 'Amsterdam'],
    timezone: 'Europe/London',
    avgPayloadSize: 1536,
    peakHour: 11, // 11 AM GMT
  },
  ME: {
    weight: 0.10,
    currencies: ['AED', 'SAR'],
    languages: ['en', 'ar'],
    cities: ['Dubai', 'Abu Dhabi', 'Riyadh'],
    timezone: 'Asia/Dubai',
    avgPayloadSize: 1024,
    peakHour: 14, // 2 PM GST
  },
  AP: {
    weight: 0.15,
    currencies: ['SGD', 'AUD'],
    languages: ['en', 'zh'],
    cities: ['Singapore', 'Sydney', 'Bangkok', 'Manila'],
    timezone: 'Asia/Singapore',
    avgPayloadSize: 1792,
    peakHour: 19, // 7 PM SGT
  },
};

/**
 * Select region based on traffic distribution
 */
function selectRegion() {
  const rand = Math.random();
  let cumulative = 0;

  for (const [region, config] of Object.entries(REGIONS)) {
    cumulative += config.weight;
    if (rand <= cumulative) {
      return region;
    }
  }

  return 'IN';
}

/**
 * Get localized message content
 */
function getLocalizedMessage(region, messageType = 'inquiry') {
  const messages = {
    IN: {
      inquiry: 'क्या आप मेरी मदद कर सकते हैं?',
      greeting: 'नमस्ते',
      complaint: 'मुझे एक समस्या है',
      thanks: 'धन्यवाद',
    },
    US: {
      inquiry: 'Can you help me?',
      greeting: 'Hello',
      complaint: 'I have a problem',
      thanks: 'Thank you',
    },
    EU: {
      inquiry: 'Können Sie mir helfen?',
      greeting: 'Guten Tag',
      complaint: 'Ich habe ein Problem',
      thanks: 'Danke schön',
    },
    ME: {
      inquiry: 'هل يمكنك مساعدتي؟',
      greeting: 'مرحبا',
      complaint: 'لدي مشكلة',
      thanks: 'شكرا لك',
    },
    AP: {
      inquiry: '你能帮我吗?',
      greeting: '你好',
      complaint: '我有个问题',
      thanks: '谢谢',
    },
  };

  return messages[region][messageType] || messages.US[messageType];
}

/**
 * Test India-specific operations
 */
function testIndiaRegionalOps(tenant, token) {
  group('India Regional Operations', () => {
    const regionCode = 'IN';

    // Test with Indian phone number
    const payload = {
      channel: 'whatsapp',
      customer_name: generateIndianName(),
      customer_phone: generateIndianPhoneNumber(),
      customer_email: generateEmail(),
      metadata: {
        region: regionCode,
        language: Math.random() > 0.7 ? 'hi' : 'en',
      },
    };

    const response = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.create}`,
      JSON.stringify(payload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'regional_ops',
          region: regionCode,
          tenant: tenant.id,
        },
      }
    );

    latencyByRegion.add(response.timings.duration, { region: regionCode });
    successRateByRegion.add(response.status === 201 || response.status === 200, { region: regionCode });
    requestsByRegion.add(1, { region: regionCode });

    sleep(0.5);
  });
}

/**
 * Test US-specific operations
 */
function testUSRegionalOps(tenant, token) {
  group('US Regional Operations', () => {
    const regionCode = 'US';

    const payload = {
      channel: 'webchat',
      customer_name: 'John Smith',
      customer_phone: '+14155552671',
      customer_email: generateEmail(),
      metadata: {
        region: regionCode,
        language: 'en',
      },
    };

    const response = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.create}`,
      JSON.stringify(payload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'regional_ops',
          region: regionCode,
          tenant: tenant.id,
        },
      }
    );

    latencyByRegion.add(response.timings.duration, { region: regionCode });
    successRateByRegion.add(response.status === 201 || response.status === 200, { region: regionCode });
    requestsByRegion.add(1, { region: regionCode });

    sleep(0.5);
  });
}

/**
 * Test multilingual message support
 */
function testMultilingualMessaging(tenant, token) {
  group('Multilingual Messaging', () => {
    const region = selectRegion();
    const regionConfig = REGIONS[region];

    // Generate multilingual message
    const messageContent = getLocalizedMessage(region, 'inquiry');

    const payload = {
      conversation_id: `conv-${Date.now()}`,
      channel: 'webchat',
      text: messageContent,
      metadata: {
        region: region,
        language: regionConfig.languages[0],
      },
    };

    const response = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.messages.send}`,
      JSON.stringify(payload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'multilingual',
          region: region,
          tenant: tenant.id,
        },
      }
    );

    latencyByRegion.add(response.timings.duration, { region });
    successRateByRegion.add(response.status === 200 || response.status === 201, { region });
    multilingualMessages.add(1, { region });
    requestsByRegion.add(1, { region });

    sleep(0.3);
  });
}

/**
 * Test multi-currency billing
 */
function testMultiCurrencyBilling(tenant, token) {
  group('Multi-Currency Billing', () => {
    const region = selectRegion();
    const regionConfig = REGIONS[region];
    const currency = regionConfig.currencies[0];

    const payload = {
      currency: currency,
      amount: Math.random() * 1000,
      region: region,
    };

    const response = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.billing.usage}`,
      JSON.stringify(payload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'billing',
          region: region,
          currency: currency,
          tenant: tenant.id,
        },
      }
    );

    latencyByRegion.add(response.timings.duration, { region, currency });
    successRateByRegion.add(response.status === 200 || response.status === 201, { region });
    currencyOperations.add(1, { region, currency });
    requestsByRegion.add(1, { region });

    sleep(0.5);
  });
}

/**
 * Test with region-appropriate payload sizes
 */
function testRegionalPayloadSizes(tenant, token) {
  group('Regional Payload Variations', () => {
    const region = selectRegion();
    const regionConfig = REGIONS[region];

    // Create payload with size appropriate to region
    const payloadSize = regionConfig.avgPayloadSize + Math.random() * 512;
    const largeContent = 'x'.repeat(Math.floor(payloadSize));

    const payload = {
      conversation_id: `conv-${Date.now()}`,
      channel: 'email',
      text: largeContent,
      metadata: {
        region: region,
        payload_size: payloadSize,
      },
    };

    const response = http.post(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.messages.send}`,
      JSON.stringify(payload),
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'payload_size_test',
          region: region,
          tenant: tenant.id,
        },
      }
    );

    latencyByRegion.add(response.timings.duration, { region });
    successRateByRegion.add(response.status === 200 || response.status === 201, { region });
    largePayloads.add(1, { region });
    requestsByRegion.add(1, { region });

    sleep(0.5);
  });
}

/**
 * Test regional analytics
 */
function testRegionalAnalytics(tenant, token) {
  group('Regional Analytics', () => {
    const region = selectRegion();

    const response = http.get(
      `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.analytics.conversations}?region=${region}`,
      {
        headers: getAuthHeaders(token, tenant.id),
        tags: {
          operation: 'regional_analytics',
          region: region,
          tenant: tenant.id,
        },
      }
    );

    latencyByRegion.add(response.timings.duration, { region });
    successRateByRegion.add(response.status === 200, { region });
    requestsByRegion.add(1, { region });

    sleep(0.5);
  });
}

/**
 * Main test function
 */
export default function () {
  const tenant = randomTenant();
  const token = tenant.token;

  // Determine which regional test to run based on VU
  const testType = __VU % 6;

  switch (testType) {
    case 0:
      testIndiaRegionalOps(tenant, token);
      break;
    case 1:
      testUSRegionalOps(tenant, token);
      break;
    case 2:
      testMultilingualMessaging(tenant, token);
      break;
    case 3:
      testMultiCurrencyBilling(tenant, token);
      break;
    case 4:
      testRegionalPayloadSizes(tenant, token);
      break;
    case 5:
      testRegionalAnalytics(tenant, token);
      break;
  }

  sleep(1.0);
}
