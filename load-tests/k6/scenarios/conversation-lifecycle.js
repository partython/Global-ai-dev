/**
 * Conversation Lifecycle Load Test
 * Priya Global Platform - K6 Load Test
 *
 * Tests the full conversation flow under load:
 * - Create conversation
 * - Send messages
 * - AI response simulation
 * - Close conversation
 *
 * Multi-channel simulation: WhatsApp, Email, SMS, WebChat
 * Concurrent conversations per tenant
 * Stages: 10→100→500 concurrent conversations
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { CONFIG } from '../config.js';
import {
  randomTenant,
  randomConversation,
  randomMessage,
  getAuthHeaders,
  generateRequestId,
  generateIndianPhoneNumber,
  generateEmail,
} from '../helpers.js';

// Custom metrics
const conversationCreateLatency = new Trend('conversation_create_latency');
const conversationCloseLatency = new Trend('conversation_close_latency');
const messageSendLatency = new Trend('message_send_latency');
const aiResponseLatency = new Trend('ai_response_latency');
const conversationSuccessRate = new Rate('conversation_success_rate');
const messageSuccessRate = new Rate('message_success_rate');
const activeConversations = new Gauge('active_conversations');
const messagesPerConversation = new Counter('messages_sent_total');

export const options = {
  scenarios: {
    conversation_lifecycle: {
      executor: 'rampingVUs',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 10 },    // Ramp up to 10 conversations
        { duration: '3m', target: 100 },   // Ramp to 100
        { duration: '3m', target: 500 },   // Ramp to 500
        { duration: '5m', target: 500 },   // Hold at high load
        { duration: '3m', target: 100 },   // Scale down
        { duration: '2m', target: 0 },     // Final ramp down
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'conversation_create_latency': ['p(95)<1500', 'p(99)<3000'],
    'conversation_close_latency': ['p(95)<500'],
    'message_send_latency': ['p(95)<1000', 'p(99)<2000'],
    'ai_response_latency': ['p(95)<3000', 'p(99)<5000'],
    'conversation_success_rate': ['rate>0.95'],
    'message_success_rate': ['rate>0.98'],
    'http_req_failed': ['rate<0.02'],
  },
};

/**
 * Create a new conversation
 */
function createConversation(tenant, token, channel) {
  const payload = randomConversation(channel, tenant.id);

  const response = http.post(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.create}`,
    JSON.stringify(payload),
    {
      headers: getAuthHeaders(token, tenant.id),
      tags: {
        operation: 'conversation_create',
        tenant: tenant.id,
        channel: channel,
        plan: tenant.plan,
      },
    }
  );

  conversationCreateLatency.add(response.timings.duration);

  const isSuccess = check(response, {
    'conversation created': (r) => r.status === 201 || r.status === 200,
    'has conversation id': (r) => r.json('id') !== undefined,
    'response time < 3s': (r) => r.timings.duration < 3000,
  });

  conversationSuccessRate.add(isSuccess);
  activeConversations.add(1);

  return isSuccess ? response.json('id') : null;
}

/**
 * Send message in conversation
 */
function sendMessage(tenant, token, conversationId, channel) {
  const payload = randomMessage(conversationId, channel);

  const response = http.post(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.messages.send}`,
    JSON.stringify(payload),
    {
      headers: getAuthHeaders(token, tenant.id),
      tags: {
        operation: 'message_send',
        tenant: tenant.id,
        channel: channel,
        conversation: conversationId,
      },
    }
  );

  messageSendLatency.add(response.timings.duration);

  const isSuccess = check(response, {
    'message sent': (r) => r.status === 201 || r.status === 200,
    'has message id': (r) => r.json('id') !== undefined,
    'response time < 2s': (r) => r.timings.duration < 2000,
  });

  messageSuccessRate.add(isSuccess);
  if (isSuccess) {
    messagesPerConversation.add(1);
  }

  return isSuccess;
}

/**
 * Simulate AI response to message
 */
function getAIResponse(tenant, token, conversationId) {
  const payload = {
    conversation_id: conversationId,
    message: 'Can you help me with my order?',
    context: {
      customer_sentiment: 'neutral',
      conversation_stage: 'inquiry',
    },
  };

  const response = http.post(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.ai.chat}`,
    JSON.stringify(payload),
    {
      headers: getAuthHeaders(token, tenant.id),
      tags: {
        operation: 'ai_response',
        tenant: tenant.id,
        conversation: conversationId,
      },
    }
  );

  aiResponseLatency.add(response.timings.duration);

  check(response, {
    'ai responded': (r) => r.status === 200 || r.status === 202,
    'has response content': (r) => r.body.length > 0,
    'response time < 5s': (r) => r.timings.duration < 5000,
  });

  return response.status === 200 || response.status === 202;
}

/**
 * Close conversation
 */
function closeConversation(tenant, token, conversationId) {
  const payload = {
    reason: 'completed',
    notes: 'Load test completion',
  };

  const response = http.post(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.close}`.replace('{id}', conversationId),
    JSON.stringify(payload),
    {
      headers: getAuthHeaders(token, tenant.id),
      tags: {
        operation: 'conversation_close',
        tenant: tenant.id,
        conversation: conversationId,
      },
    }
  );

  conversationCloseLatency.add(response.timings.duration);

  check(response, {
    'conversation closed': (r) => r.status === 200,
    'response time < 1s': (r) => r.timings.duration < 1000,
  });

  activeConversations.add(-1);
}

/**
 * Get conversation details
 */
function getConversationDetails(tenant, token, conversationId) {
  const response = http.get(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.conversations.getById}`.replace('{id}', conversationId),
    {
      headers: getAuthHeaders(token, tenant.id),
      tags: {
        operation: 'conversation_get',
        tenant: tenant.id,
        conversation: conversationId,
      },
    }
  );

  check(response, {
    'conversation retrieved': (r) => r.status === 200,
    'has conversation data': (r) => r.json('id') !== undefined,
  });

  return response.json();
}

/**
 * Simulate sentiment analysis
 */
function analyzeSentiment(tenant, token, conversationId) {
  const payload = {
    conversation_id: conversationId,
    message: 'This is great! I love your product.',
  };

  const response = http.post(
    `${CONFIG.BASE_URL}${CONFIG.ENDPOINTS.ai.sentiment}`,
    JSON.stringify(payload),
    {
      headers: getAuthHeaders(token, tenant.id),
      tags: {
        operation: 'sentiment_analysis',
        tenant: tenant.id,
      },
    }
  );

  check(response, {
    'sentiment analyzed': (r) => r.status === 200 || r.status === 202,
    'has sentiment data': (r) => r.body.length > 0,
  });
}

/**
 * Full conversation lifecycle - WhatsApp
 */
function testWhatsAppConversation(tenant, token) {
  group('WhatsApp Conversation Lifecycle', () => {
    const convId = createConversation(tenant, token, 'whatsapp');
    if (!convId) return;

    sleep(0.3);

    // Send initial message
    sendMessage(tenant, token, convId, 'whatsapp');
    sleep(0.2);

    // Get AI response
    getAIResponse(tenant, token, convId);
    sleep(0.2);

    // Customer sends follow-up
    sendMessage(tenant, token, convId, 'whatsapp');
    sleep(0.2);

    // AI response again
    getAIResponse(tenant, token, convId);
    sleep(0.2);

    // Analyze sentiment
    analyzeSentiment(tenant, token, convId);
    sleep(0.2);

    // Get conversation details
    getConversationDetails(tenant, token, convId);
    sleep(0.2);

    // Close conversation
    closeConversation(tenant, token, convId);
  });
}

/**
 * Full conversation lifecycle - Email
 */
function testEmailConversation(tenant, token) {
  group('Email Conversation Lifecycle', () => {
    const convId = createConversation(tenant, token, 'email');
    if (!convId) return;

    sleep(0.3);

    // Send message
    sendMessage(tenant, token, convId, 'email');
    sleep(0.2);

    // AI response
    getAIResponse(tenant, token, convId);
    sleep(0.2);

    // Another message
    sendMessage(tenant, token, convId, 'email');
    sleep(0.2);

    // Close conversation
    closeConversation(tenant, token, convId);
  });
}

/**
 * Full conversation lifecycle - WebChat
 */
function testWebChatConversation(tenant, token) {
  group('WebChat Conversation Lifecycle', () => {
    const convId = createConversation(tenant, token, 'webchat');
    if (!convId) return;

    sleep(0.3);

    // Send multiple messages quickly (chat-like behavior)
    for (let i = 0; i < 3; i++) {
      sendMessage(tenant, token, convId, 'webchat');
      sleep(0.1);
    }

    // AI response
    getAIResponse(tenant, token, convId);
    sleep(0.2);

    // More messages
    sendMessage(tenant, token, convId, 'webchat');
    sleep(0.1);

    // Close conversation
    closeConversation(tenant, token, convId);
  });
}

/**
 * Full conversation lifecycle - SMS
 */
function testSMSConversation(tenant, token) {
  group('SMS Conversation Lifecycle', () => {
    const convId = createConversation(tenant, token, 'sms');
    if (!convId) return;

    sleep(0.3);

    // Send message
    sendMessage(tenant, token, convId, 'sms');
    sleep(0.2);

    // AI response
    getAIResponse(tenant, token, convId);
    sleep(0.2);

    // Close conversation
    closeConversation(tenant, token, convId);
  });
}

/**
 * Main test function - cycle through different channels
 */
export default function () {
  const tenant = randomTenant();
  const token = tenant.token;

  // Rotate through different conversation types
  const testNumber = Math.floor(__VU / 25) % 4;

  switch (testNumber) {
    case 0:
      testWhatsAppConversation(tenant, token);
      break;
    case 1:
      testEmailConversation(tenant, token);
      break;
    case 2:
      testWebChatConversation(tenant, token);
      break;
    case 3:
      testSMSConversation(tenant, token);
      break;
  }

  sleep(1.0);
}
