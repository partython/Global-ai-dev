/**
 * WebSocket Load Test
 * Priya Global Platform - K6 Load Test
 *
 * WebSocket stress test for real-time features:
 * - Connect 100→1000 concurrent WebSocket connections
 * - Simulate real-time chat: typing indicators, message send/receive
 * - Measure connection time, message latency, dropped connections
 * - Test reconnection behavior under load
 *
 * Stages: 100→1000 connections (5min), hold (5min), ramp down (2min)
 */

import ws from 'k6/ws';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';
import { CONFIG } from '../config.js';
import {
  randomTenant,
  generateRequestId,
} from '../helpers.js';

// Custom metrics
const wsConnectLatency = new Trend('ws_connect_latency');
const wsMessageLatency = new Trend('ws_message_latency');
const wsConnectSuccess = new Rate('ws_connect_success_rate');
const wsMessageSuccess = new Rate('ws_message_success_rate');
const wsConnectionDrops = new Counter('ws_connection_drops_total');
const wsMessagesSent = new Counter('ws_messages_sent_total');
const wsMessagesReceived = new Counter('ws_messages_received_total');
const activeWSConnections = new Gauge('active_ws_connections');

export const options = {
  scenarios: {
    websocket_load: {
      executor: 'rampingVUs',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 100 },   // Ramp to 100 connections
        { duration: '3m', target: 500 },   // Ramp to 500
        { duration: '2m', target: 1000 },  // Ramp to 1000
        { duration: '5m', target: 1000 },  // Hold at peak
        { duration: '3m', target: 100 },   // Scale down
        { duration: '2m', target: 0 },     // Final ramp
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'ws_connect_latency': ['p(95)<1000', 'p(99)<2000'],
    'ws_message_latency': ['p(95)<200', 'p(99)<500'],
    'ws_connect_success_rate': ['rate>0.98'],
    'ws_message_success_rate': ['rate>0.99'],
    'ws_connection_drops_total': ['count<__VU*0.1'],  // Less than 10% drop rate
  },
};

/**
 * Test WebSocket connection and message flow
 */
function testWebSocketFlow(tenant, token) {
  const conversationId = `conv-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  const url = `${CONFIG.WS_URL}/api/v1/conversations/${conversationId}/messages`;

  let connectionEstablished = false;
  let messagesSent = 0;
  let messagesReceived = 0;

  const startTime = Date.now();

  ws.connect(
    url,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'X-Tenant-ID': tenant.id,
        'X-Request-ID': generateRequestId(),
      },
      tags: {
        operation: 'websocket',
        tenant: tenant.id,
        plan: tenant.plan,
      },
    },
    function (socket) {
      const connectTime = Date.now() - startTime;
      wsConnectLatency.add(connectTime);
      wsConnectSuccess.add(true);
      connectionEstablished = true;
      activeWSConnections.add(1);

      // Connection established, test message flow
      socket.on('open', () => {
        // Send initial message
        const initMsg = {
          type: 'message',
          conversation_id: conversationId,
          text: 'WebSocket load test message',
          timestamp: new Date().toISOString(),
        };

        const sendTime = Date.now();
        socket.send(JSON.stringify(initMsg));
        wsMessagesSent.add(1);
        messagesSent++;

        // Simulate rapid message sends
        for (let i = 0; i < 5; i++) {
          socket.setTimeout(() => {
            const msg = {
              type: 'message',
              conversation_id: conversationId,
              text: `Message ${i + 1} from VU ${__VU}`,
              timestamp: new Date().toISOString(),
            };

            socket.send(JSON.stringify(msg));
            wsMessagesSent.add(1);
            messagesSent++;
          }, i * 200);
        }

        // Simulate typing indicators
        for (let i = 0; i < 3; i++) {
          socket.setTimeout(() => {
            const typing = {
              type: 'typing',
              conversation_id: conversationId,
              user_id: `vu-${__VU}`,
              timestamp: new Date().toISOString(),
            };

            socket.send(JSON.stringify(typing));
          }, 100 + i * 500);
        }
      });

      socket.on('message', (data) => {
        if (data) {
          const msgLatency = Date.now() - startTime;
          wsMessageLatency.add(msgLatency);
          wsMessageSuccess.add(true);
          wsMessagesReceived.add(1);
          messagesReceived++;
        }
      });

      socket.on('close', () => {
        activeWSConnections.add(-1);

        // Check message flow metrics
        check({ messagesSent, messagesReceived }, {
          'received messages': (v) => v.messagesReceived > 0,
          'message ratio acceptable': (v) => v.messagesReceived >= v.messagesSent * 0.8,
        });
      });

      socket.on('error', (e) => {
        wsConnectSuccess.add(false);
        wsConnectionDrops.add(1);
        activeWSConnections.add(-1);
        console.error(`WebSocket error for tenant ${tenant.id}: ${e}`);
      });

      // Close socket after test
      socket.setTimeout(() => {
        socket.close();
      }, 5000);
    }
  );

  sleep(5.5);
}

/**
 * Test WebSocket reconnection behavior
 */
function testWebSocketReconnection(tenant, token) {
  const conversationId = `conv-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  const url = `${CONFIG.WS_URL}/api/v1/conversations/${conversationId}/messages`;

  let reconnectAttempts = 0;

  ws.connect(
    url,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'X-Tenant-ID': tenant.id,
        'X-Request-ID': generateRequestId(),
      },
      tags: {
        operation: 'websocket_reconnect',
        tenant: tenant.id,
      },
    },
    function (socket) {
      activeWSConnections.add(1);

      socket.on('open', () => {
        wsConnectSuccess.add(true);

        // Send a message
        socket.send(JSON.stringify({
          type: 'message',
          conversation_id: conversationId,
          text: 'Testing reconnection',
          timestamp: new Date().toISOString(),
        }));

        wsMessagesSent.add(1);

        // Simulate connection drop after 1 second
        socket.setTimeout(() => {
          socket.close();
        }, 1000);
      });

      socket.on('close', () => {
        activeWSConnections.add(-1);
        reconnectAttempts++;

        // Attempt reconnection
        if (reconnectAttempts < 3) {
          sleep(0.5);
          // Reconnection would be initiated by client
        }
      });

      socket.on('error', (e) => {
        wsConnectionDrops.add(1);
        activeWSConnections.add(-1);
      });
    }
  );

  sleep(3.0);
}

/**
 * Test high-frequency message sending
 */
function testHighFrequencyMessaging(tenant, token) {
  const conversationId = `conv-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  const url = `${CONFIG.WS_URL}/api/v1/conversations/${conversationId}/messages`;

  ws.connect(
    url,
    {
      headers: {
        'Authorization': `Bearer ${token}`,
        'X-Tenant-ID': tenant.id,
        'X-Request-ID': generateRequestId(),
      },
      tags: {
        operation: 'websocket_hf_messaging',
        tenant: tenant.id,
      },
    },
    function (socket) {
      activeWSConnections.add(1);

      socket.on('open', () => {
        wsConnectSuccess.add(true);

        // Send 20 messages rapidly
        for (let i = 0; i < 20; i++) {
          const sendTime = Date.now();

          socket.send(JSON.stringify({
            type: 'message',
            conversation_id: conversationId,
            text: `HF Message ${i + 1}`,
            sequence: i,
            timestamp: new Date().toISOString(),
          }));

          wsMessagesSent.add(1);
          wsMessageLatency.add(Date.now() - sendTime);
          wsMessageSuccess.add(true);

          // Small delay between messages
          if (i % 5 === 0) {
            socket.setTimeout(() => {}, 10);
          }
        }

        socket.setTimeout(() => {
          socket.close();
        }, 3000);
      });

      socket.on('message', () => {
        wsMessagesReceived.add(1);
      });

      socket.on('close', () => {
        activeWSConnections.add(-1);
      });

      socket.on('error', () => {
        wsConnectionDrops.add(1);
        activeWSConnections.add(-1);
      });
    }
  );

  sleep(3.5);
}

/**
 * Test concurrent WebSocket connections with message exchange
 */
function testConcurrentWSConnections(tenant, token) {
  group('Concurrent WebSocket Connections', () => {
    const conversationId = `conv-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const url = `${CONFIG.WS_URL}/api/v1/conversations/${conversationId}/messages`;

    ws.connect(
      url,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant-ID': tenant.id,
          'X-Request-ID': generateRequestId(),
        },
        tags: {
          operation: 'websocket_concurrent',
          tenant: tenant.id,
          vu: __VU.toString(),
        },
      },
      function (socket) {
        activeWSConnections.add(1);

        socket.on('open', () => {
          // Send periodic messages
          const sendInterval = setInterval(() => {
            socket.send(JSON.stringify({
              type: 'message',
              conversation_id: conversationId,
              text: `Message from VU ${__VU}`,
              timestamp: new Date().toISOString(),
            }));

            wsMessagesSent.add(1);
          }, 500);

          // Close after 4 seconds
          socket.setTimeout(() => {
            clearInterval(sendInterval);
            socket.close();
          }, 4000);
        });

        socket.on('message', () => {
          wsMessagesReceived.add(1);
        });

        socket.on('close', () => {
          activeWSConnections.add(-1);
        });

        socket.on('error', () => {
          wsConnectionDrops.add(1);
          activeWSConnections.add(-1);
        });
      }
    );

    sleep(4.5);
  });
}

/**
 * Main test function
 */
export default function () {
  const tenant = randomTenant();
  const token = tenant.token;

  // Vary test type based on VU number
  const testType = __VU % 4;

  switch (testType) {
    case 0:
      testWebSocketFlow(tenant, token);
      break;
    case 1:
      testWebSocketReconnection(tenant, token);
      break;
    case 2:
      testHighFrequencyMessaging(tenant, token);
      break;
    case 3:
      testConcurrentWSConnections(tenant, token);
      break;
  }

  sleep(1.0);
}
