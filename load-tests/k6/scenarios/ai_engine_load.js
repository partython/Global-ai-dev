/**
 * K6 Load Test: AI Engine Performance
 *
 * Tests AI engine under load:
 * - Intent classification requests
 * - Entity extraction
 * - Response generation
 * - Concurrent request handling
 *
 * Measures AI inference latency separately from HTTP overhead
 *
 * Usage: k6 run ai_engine_load.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import {
  defaultOptions,
  BASE_URL,
  generateToken,
  metricTags,
  performanceTargets,
} from '../load_config.js';

// ─────────────────────────────────────────────────────────
// Custom Metrics - AI Specific
// ─────────────────────────────────────────────────────────

const intentLatency = new Trend('ai_intent_latency', true);
const entityLatency = new Trend('ai_entity_latency', true);
const responseLatency = new Trend('ai_response_latency', true);
const inferenceLatency = new Trend('ai_inference_latency', true);

const intentSuccessRate = new Rate('ai_intent_success_rate', true);
const entitySuccessRate = new Rate('ai_entity_success_rate', true);
const responseSuccessRate = new Rate('ai_response_success_rate', true);

const aiRequests = new Counter('ai_requests', true);
const aiErrors = new Counter('ai_errors', true);
const timeoutErrors = new Counter('ai_timeout_errors', true);

// ─────────────────────────────────────────────────────────
// Test Options
// ─────────────────────────────────────────────────────────

export const options = {
  ...defaultOptions,
  thresholds: {
    ...defaultOptions.thresholds,
    // AI endpoints are slower than regular API
    'ai_intent_latency': [`p(95)<${performanceTargets.ai.p95}`],
    'ai_entity_latency': [`p(95)<${performanceTargets.ai.p95}`],
    'ai_response_latency': [`p(95)<${performanceTargets.ai.p95}`],
    'ai_inference_latency': [`p(95)<${performanceTargets.ai.p95}`],
    'ai_intent_success_rate': [`rate>${1 - performanceTargets.ai.errorRate}`],
    'ai_entity_success_rate': [`rate>${1 - performanceTargets.ai.errorRate}`],
    'ai_response_success_rate': [`rate>${1 - performanceTargets.ai.errorRate}`],
    'http_req_failed': [`rate<0.02`],  // Allow 2% for AI endpoints
  },
};

// ─────────────────────────────────────────────────────────
// Test Payloads
// ─────────────────────────────────────────────────────────

const testMessages = [
  'What are your business hours?',
  'Can I return this product?',
  'How much is shipping?',
  'Do you ship internationally?',
  'What payment methods do you accept?',
  'Is this product in stock?',
  'Can I modify my order?',
  'How long does delivery take?',
  'Do you have customer service?',
  'What is your refund policy?',
  'Can I track my order?',
  'Are there any discounts available?',
  'Is the product available in different colors?',
  'What is the warranty?',
  'Can I cancel my order?',
];

// ─────────────────────────────────────────────────────────
// Test Functions
// ─────────────────────────────────────────────────────────

/**
 * Test intent classification
 */
function testIntentClassification(token, tenantId) {
  group('AI Intent Classification', () => {
    const message = testMessages[Math.floor(Math.random() * testMessages.length)];

    const payload = {
      text: message,
      language: 'en',
      context: {
        channel: 'whatsapp',
        customer_id: `customer-${__VU}`,
      },
    };

    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Tenant-ID': tenantId,
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'IntentClassification',
        ...metricTags.endpoint.AI_ENGINE,
        ...metricTags.operation.READ,
      },
      timeout: '10s',
    };

    const response = http.post(
      `${BASE_URL}/api/v1/ai/classify-intent`,
      JSON.stringify(payload),
      params
    );

    const success = response.status === 200;
    intentSuccessRate.add(success);
    aiRequests.add(1);

    if (success) {
      intentLatency.add(response.timings.duration);

      // Extract inference time from response headers if available
      const inferenceTime = response.headers['X-Inference-Time'];
      if (inferenceTime) {
        inferenceLatency.add(parseInt(inferenceTime));
      } else {
        // Estimate: response time minus network/parsing overhead
        inferenceLatency.add(Math.max(response.timings.duration - 100, 0));
      }
    } else {
      aiErrors.add(1);
      if (response.status === 0) {
        timeoutErrors.add(1);
      }
    }

    check(response, {
      'intent classification succeeds': (r) => r.status === 200,
      'response contains intent': (r) => r.status === 200 && r.body.includes('intent'),
    });
  });
}

/**
 * Test entity extraction
 */
function testEntityExtraction(token, tenantId) {
  group('AI Entity Extraction', () => {
    const message = testMessages[Math.floor(Math.random() * testMessages.length)];

    const payload = {
      text: message,
      language: 'en',
      entity_types: ['PRODUCT', 'ACTION', 'ATTRIBUTE', 'VALUE'],
    };

    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Tenant-ID': tenantId,
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'EntityExtraction',
        ...metricTags.endpoint.AI_ENGINE,
        ...metricTags.operation.READ,
      },
      timeout: '10s',
    };

    const response = http.post(
      `${BASE_URL}/api/v1/ai/extract-entities`,
      JSON.stringify(payload),
      params
    );

    const success = response.status === 200;
    entitySuccessRate.add(success);
    aiRequests.add(1);

    if (success) {
      entityLatency.add(response.timings.duration);
    } else {
      aiErrors.add(1);
      if (response.status === 0) {
        timeoutErrors.add(1);
      }
    }

    check(response, {
      'entity extraction succeeds': (r) => r.status === 200,
      'response contains entities': (r) => r.status === 200 && (r.body.includes('entity') || r.body.includes('entities')),
    });
  });
}

/**
 * Test response generation
 */
function testResponseGeneration(token, tenantId) {
  group('AI Response Generation', () => {
    const message = testMessages[Math.floor(Math.random() * testMessages.length)];

    const payload = {
      message: message,
      conversation_context: {
        channel: 'whatsapp',
        language: 'en',
      },
      knowledge_base_results: [
        {
          document_id: 'doc-' + Math.floor(Math.random() * 100),
          content: 'Sample knowledge base content',
          relevance_score: 0.85,
        },
      ],
    };

    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Tenant-ID': tenantId,
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'ResponseGeneration',
        ...metricTags.endpoint.AI_ENGINE,
        ...metricTags.operation.READ,
      },
      timeout: '15s',  // Generation is slower
    };

    const response = http.post(
      `${BASE_URL}/api/v1/ai/generate-response`,
      JSON.stringify(payload),
      params
    );

    const success = response.status === 200;
    responseSuccessRate.add(success);
    aiRequests.add(1);

    if (success) {
      responseLatency.add(response.timings.duration);

      // Track inference latency
      const inferenceTime = response.headers['X-Inference-Time'];
      if (inferenceTime) {
        inferenceLatency.add(parseInt(inferenceTime));
      } else {
        inferenceLatency.add(Math.max(response.timings.duration - 200, 0));
      }
    } else {
      aiErrors.add(1);
      if (response.status === 0) {
        timeoutErrors.add(1);
      }
    }

    check(response, {
      'response generation succeeds': (r) => r.status === 200,
      'response contains generated text': (r) => r.status === 200 && r.body.length > 0,
    });
  });
}

/**
 * Test batch intent classification
 */
function testBatchIntentClassification(token, tenantId) {
  group('Batch Intent Classification', () => {
    const batch = testMessages.slice(0, 5).map((text, i) => ({
      id: `msg-${i}`,
      text: text,
    }));

    const payload = {
      messages: batch,
      language: 'en',
    };

    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Tenant-ID': tenantId,
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'BatchIntentClassification',
        ...metricTags.endpoint.AI_ENGINE,
      },
      timeout: '15s',
    };

    const response = http.post(
      `${BASE_URL}/api/v1/ai/batch/classify-intent`,
      JSON.stringify(payload),
      params
    );

    const success = response.status === 200;
    intentSuccessRate.add(success);
    aiRequests.add(1);

    if (success) {
      intentLatency.add(response.timings.duration);
    } else {
      aiErrors.add(1);
    }
  });
}

// ─────────────────────────────────────────────────────────
// Main Test
// ─────────────────────────────────────────────────────────

export default function () {
  // Generate token
  const userId = `ai-load-test-${__VU}-${__ITER}`;
  const tenantId = 'tenant-load-001';
  const token = generateToken(userId, tenantId, 'admin');

  // Test different AI capabilities
  const operation = Math.random();

  if (operation < 0.3) {
    testIntentClassification(token, tenantId);
  } else if (operation < 0.6) {
    testEntityExtraction(token, tenantId);
  } else if (operation < 0.9) {
    testResponseGeneration(token, tenantId);
  } else {
    testBatchIntentClassification(token, tenantId);
  }

  // AI operations are resource-intensive, add recovery time
  sleep(Math.random() * 3 + 1);
}

// ─────────────────────────────────────────────────────────
// Summary
// ─────────────────────────────────────────────────────────

export function handleSummary(data) {
  const metrics = data.metrics || {};

  return {
    '/tmp/ai-engine-load-summary.json': JSON.stringify({
      timestamp: new Date().toISOString(),
      testType: 'ai_engine_load',
      metrics: {
        latencies: {
          intentClassification: metrics.ai_intent_latency,
          entityExtraction: metrics.ai_entity_latency,
          responseGeneration: metrics.ai_response_latency,
          avgInference: metrics.ai_inference_latency,
        },
        successRates: {
          intent: metrics.ai_intent_success_rate,
          entity: metrics.ai_entity_success_rate,
          response: metrics.ai_response_success_rate,
        },
        errors: {
          total: metrics.ai_errors,
          timeouts: metrics.ai_timeout_errors,
        },
        totalRequests: metrics.ai_requests,
      },
    }, null, 2),
    stdout: 'standard',
  };
}
