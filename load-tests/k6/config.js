/**
 * K6 Load Testing Configuration
 * Priya Global Platform - 36 Microservice SaaS
 *
 * Central configuration for all load test scenarios
 * Environment variables can override defaults
 */

// SECURITY: Validate BASE_URL to prevent running against production
function validateBaseUrl(url) {
  const allowedHosts = ['localhost', '127.0.0.1', '0.0.0.0', 'staging', 'test', 'qa'];
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    const allowed = allowedHosts.some(allowed => host.includes(allowed));

    if (!allowed) {
      throw new Error(`CRITICAL: BASE_URL="${url}" looks like production. Only test/staging URLs allowed.`);
    }
  } catch (e) {
    throw new Error(`Invalid BASE_URL: ${e.message}`);
  }
  return url;
}

export const CONFIG = {
  // Base URLs - override with environment variables
  // SECURITY: Validate URLs to prevent accidental production load test
  BASE_URL: validateBaseUrl(__ENV.BASE_URL || 'http://localhost:9001'),
  WS_URL: __ENV.WS_URL || 'ws://localhost:9001',

  // Load test duration and stages
  DURATION: {
    RAMP_UP: '2m',
    HOLD_LOAD: '5m',
    RAMP_DOWN: '2m',
    SPIKE_DURATION: '3m',
    SOAK_DURATION: '30m',
  },

  // Test tenants for multi-tenant simulation
  // SECURITY: Tokens MUST be provided via environment variables
  // NEVER hardcode test tokens that could leak into VCS
  TENANTS: [
    {
      id: 'tenant-load-001',
      token: __ENV.TENANT_1_TOKEN,  // MUST be set; will error if missing
      plan: 'professional',
      rateLimit: 2000, // requests/minute
      region: 'IN',
    },
    {
      id: 'tenant-load-002',
      token: __ENV.TENANT_2_TOKEN,  // MUST be set
      plan: 'growth',
      rateLimit: 500,
      region: 'US',
    },
    {
      id: 'tenant-load-003',
      token: __ENV.TENANT_3_TOKEN,  // MUST be set
      plan: 'starter',
      rateLimit: 100,
      region: 'EU',
    },
    {
      id: 'tenant-load-004',
      token: __ENV.TENANT_4_TOKEN,  // MUST be set
      plan: 'enterprise',
      rateLimit: 5000,
      region: 'AP',
    },
  ],

// Validate all tenant tokens are provided
CONFIG.TENANTS.forEach((tenant, idx) => {
  if (!tenant.token) {
    throw new Error(`CRITICAL: Tenant ${idx} (${tenant.id}) has no token. Set TENANT_${idx+1}_TOKEN environment variable.`);
  }
});

  // Global SLA thresholds
  THRESHOLDS: {
    // HTTP response time thresholds
    'http_req_duration': [
      'p(50)<200',      // 50th percentile < 200ms
      'p(95)<500',      // 95th percentile < 500ms
      'p(99)<2000',     // 99th percentile < 2s
    ],
    'http_req_failed': [
      'rate<0.01',      // Less than 1% error rate
    ],

    // WebSocket thresholds
    'ws_connecting': [
      'p(95)<1000',     // WebSocket connect < 1s at 95th percentile
    ],
    'ws_message_latency': [
      'p(95)<200',      // Message latency < 200ms
    ],

    // Custom metrics
    'auth_duration': [
      'p(95)<1000',     // Auth < 1s
    ],
    'conversation_create_duration': [
      'p(95)<1500',     // Conversation create < 1.5s
    ],
    'message_send_duration': [
      'p(95)<1000',     // Message send < 1s
    ],
    'ai_response_duration': [
      'p(95)<3000',     // AI response < 3s
    ],
  },

  // Multi-region traffic distribution
  REGIONS: {
    IN: { weight: 0.40, timezone: 'Asia/Kolkata', label: 'India' },
    US: { weight: 0.20, timezone: 'America/New_York', label: 'USA' },
    EU: { weight: 0.15, timezone: 'Europe/London', label: 'Europe' },
    ME: { weight: 0.10, timezone: 'Asia/Dubai', label: 'Middle East' },
    AP: { weight: 0.15, timezone: 'Asia/Singapore', label: 'Asia Pacific' },
  },

  // API endpoints by service
  ENDPOINTS: {
    auth: {
      login: '/api/v1/auth/login',
      refresh: '/api/v1/auth/refresh',
      logout: '/api/v1/auth/logout',
      verify: '/api/v1/auth/verify',
    },
    conversations: {
      create: '/api/v1/conversations',
      list: '/api/v1/conversations',
      getById: '/api/v1/conversations/{id}',
      close: '/api/v1/conversations/{id}/close',
    },
    messages: {
      send: '/api/v1/messages',
      list: '/api/v1/messages',
      getById: '/api/v1/messages/{id}',
    },
    channels: {
      list: '/api/v1/channels',
      getById: '/api/v1/channels/{id}',
      connect: '/api/v1/channels/{id}/connect',
    },
    ai: {
      chat: '/api/v1/ai/chat',
      analyze: '/api/v1/ai/analyze',
      sentiment: '/api/v1/ai/sentiment',
    },
    analytics: {
      dashboard: '/api/v1/analytics/dashboard',
      conversations: '/api/v1/analytics/conversations',
      messages: '/api/v1/analytics/messages',
    },
    billing: {
      usage: '/api/v1/billing/usage',
      invoices: '/api/v1/billing/invoices',
      plans: '/api/v1/billing/plans',
    },
  },

  // Message channels
  CHANNELS: [
    'whatsapp',
    'email',
    'sms',
    'webchat',
    'telegram',
    'facebook',
    'instagram',
  ],

  // Test data generation
  MESSAGE_TEMPLATES: [
    "Hi, I'd like to know more about your services",
    "Can you help me with my order?",
    "What are the pricing plans?",
    "I need technical support",
    "Is your product available in India?",
    "कृपया मुझे अधिक जानकारी दें",
    "Me gustaría saber más",
  ],

  // Concurrent user progression
  LOAD_STAGES: {
    low: 10,
    medium: 50,
    high: 200,
    extreme: 1000,
  },

  // Tags for grouping metrics
  TAGS: {
    TENANT: 'tenant',
    REGION: 'region',
    CHANNEL: 'channel',
    PLAN: 'plan',
    OPERATION: 'operation',
  },
};

export default CONFIG;

// Ensure tenant token validation happens at module load time
if (typeof CONFIG.TENANTS !== 'undefined') {
  CONFIG.TENANTS.forEach((tenant, idx) => {
    if (!tenant.token) {
      throw new Error(`CRITICAL: Tenant ${idx} (${tenant.id}) has no token. Set TENANT_${idx+1}_TOKEN environment variable.`);
    }
  });
}
