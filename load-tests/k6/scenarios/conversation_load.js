/**
 * K6 Load Test: Conversation Flow
 *
 * Simulates realistic conversation creation and messaging workflow:
 * 1. Create new conversation via WhatsApp
 * 2. Send 5 messages in conversation
 * 3. Measure response times and success rate
 *
 * Usage: k6 run conversation_load.js
 *        BASE_URL=http://staging:9000 k6 run conversation_load.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend, Rate, Counter, Gauge } from 'k6/metrics';
import {
  defaultOptions,
  BASE_URL,
  generateToken,
  generateConversationPayload,
  generateMessagePayload,
  metricTags,
  performanceTargets,
  checkResponse,
} from '../load_config.js';

// ─────────────────────────────────────────────────────────
// Custom Metrics
// ─────────────────────────────────────────────────────────

const conversationCreateTime = new Trend('conversation_create_duration', true);
const messagesSendTime = new Trend('messages_send_duration', true);
const conversationReadTime = new Trend('conversation_read_duration', true);
const successRate = new Rate('conversation_success_rate', true);
const failureCount = new Counter('conversation_failures', true);
const activeConversations = new Gauge('active_conversations', true);

// ─────────────────────────────────────────────────────────
// Test Options
// ─────────────────────────────────────────────────────────

export const options = {
  ...defaultOptions,
  thresholds: {
    ...defaultOptions.thresholds,
    'conversation_create_duration': [`p(95)<${performanceTargets.conversation.p95}`],
    'messages_send_duration': [`p(95)<${performanceTargets.conversation.p95}`],
    'conversation_success_rate': [`rate>${1 - performanceTargets.conversation.errorRate}`],
  },
};

// ─────────────────────────────────────────────────────────
// Test Functions
// ─────────────────────────────────────────────────────────

/**
 * Create a new conversation
 */
function createConversation(token, tenantId) {
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

  const success = checkResponse(response, 201);
  successRate.add(success);

  if (success) {
    const data = response.json();
    conversationCreateTime.add(response.timings.duration);
    return data.id;
  } else {
    failureCount.add(1);
    console.error(`Failed to create conversation: ${response.status}`);
    return null;
  }
}

/**
 * Send messages in conversation
 */
function sendMessages(conversationId, token, messageCount = 5) {
  let successCount = 0;
  const startTime = new Date();

  for (let i = 0; i < messageCount; i++) {
    const payload = generateMessagePayload();
    const params = {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'User-Agent': 'k6-load-test',
      },
      tags: {
        name: 'SendMessage',
        ...metricTags.endpoint.MESSAGE,
        ...metricTags.operation.CREATE,
      },
    };

    const response = http.post(
      `${BASE_URL}/api/v1/conversations/${conversationId}/messages`,
      JSON.stringify(payload),
      params
    );

    const success = checkResponse(response, 201);
    if (success) {
      successCount++;
      messagesSendTime.add(response.timings.duration);
    } else {
      failureCount.add(1);
      console.error(`Failed to send message ${i}: ${response.status}`);
    }

    // Small delay between messages
    sleep(0.2);
  }

  const duration = new Date() - startTime;
  return {
    successCount,
    duration,
    successRate: successCount / messageCount,
  };
}

/**
 * Read conversation
 */
function readConversation(conversationId, token) {
  const params = {
    headers: {
      'Authorization': `Bearer ${token}`,
      'User-Agent': 'k6-load-test',
    },
    tags: {
      name: 'ReadConversation',
      ...metricTags.endpoint.CONVERSATION,
      ...metricTags.operation.READ,
    },
  };

  const response = http.get(
    `${BASE_URL}/api/v1/conversations/${conversationId}`,
    params
  );

  const success = checkResponse(response, 200);
  if (success) {
    conversationReadTime.add(response.timings.duration);
  } else {
    failureCount.add(1);
  }

  return success;
}

/**
 * List conversations
 */
function listConversations(token) {
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

  return checkResponse(response, 200);
}

// ─────────────────────────────────────────────────────────
// Main Test Function
// ─────────────────────────────────────────────────────────

export default function () {
  // Generate test user token
  const userId = `load-test-user-${__VU}-${__ITER}`;
  const tenantId = 'tenant-load-001';
  const token = generateToken(userId, tenantId, 'admin');

  group('Conversation Lifecycle', () => {
    // 1. Create conversation
    const convId = createConversation(token, tenantId);

    if (!convId) {
      console.error('Failed to create conversation, skipping rest of test');
      return;
    }

    activeConversations.add(1);

    // 2. Send messages
    group('Send Messages', () => {
      const messageResult = sendMessages(convId, token, 5);
      check(messageResult, {
        'messages sent successfully': (r) => r.successCount >= 4,  // At least 80% success
      });
    });

    // 3. Read conversation
    group('Read Conversation', () => {
      const success = readConversation(convId, token);
      check(success, {
        'conversation read successfully': (s) => s === true,
      });
    });

    // 4. List conversations
    group('List Conversations', () => {
      const success = listConversations(token);
      check(success, {
        'list conversations successful': (s) => s === true,
      });
    });

    activeConversations.add(-1);
  });

  // Simulate think time between iterations
  sleep(1);
}

// ─────────────────────────────────────────────────────────
// Test Summary
// ─────────────────────────────────────────────────────────

export function handleSummary(data) {
  return {
    '/tmp/conversation-load-summary.json': JSON.stringify({
      timestamp: new Date().toISOString(),
      testType: 'conversation_load',
      metrics: {
        conversationCreate: data.metrics.conversation_create_duration,
        messagesSend: data.metrics.messages_send_duration,
        conversationRead: data.metrics.conversation_read_duration,
        successRate: data.metrics.conversation_success_rate,
        failures: data.metrics.conversation_failures,
      },
    }, null, 2),
    stdout: 'standard',
  };
}
