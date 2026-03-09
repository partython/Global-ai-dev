import { test as base, Page } from '@playwright/test';

/**
 * API Mocks Fixture
 * Intercepts all backend API calls and returns mock data
 */

export type APIMocksFixture = {
  mockAPIs: () => Promise<void>;
};

const mockDashboardStats = {
  stats: [
    {
      id: 1,
      label: 'Total Conversations',
      value: '2,543',
      trend: '+12%',
      trendDirection: 'up',
    },
    {
      id: 2,
      label: 'Active Channels',
      value: '5',
      trend: '+1',
      trendDirection: 'up',
    },
    {
      id: 3,
      label: 'Avg Response Time',
      value: '2.3s',
      trend: '-0.5s',
      trendDirection: 'down',
    },
    {
      id: 4,
      label: 'CSAT Score',
      value: '4.8/5',
      trend: '+0.3',
      trendDirection: 'up',
    },
  ],
  charts: {
    conversations: {
      labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      data: [45, 52, 48, 61, 55, 43, 38],
    },
    channelBreakdown: [
      { name: 'WhatsApp', value: 35, fill: '#25D366' },
      { name: 'Telegram', value: 25, fill: '#0088CC' },
      { name: 'Email', value: 20, fill: '#EA4335' },
      { name: 'Chat', value: 15, fill: '#34A853' },
      { name: 'Phone', value: 5, fill: '#FBBC04' },
    ],
  },
};

const mockConversations = {
  conversations: [
    {
      id: 'conv-1',
      customerId: 'cust-1',
      customerName: 'Rajesh Kumar',
      channel: 'whatsapp',
      lastMessage: 'Can you help with order #12345?',
      timestamp: new Date(Date.now() - 5 * 60000).toISOString(),
      status: 'active',
      unread: true,
      avatar: 'https://i.pravatar.cc/150?img=1',
    },
    {
      id: 'conv-2',
      customerId: 'cust-2',
      customerName: 'Priya Singh',
      channel: 'telegram',
      lastMessage: 'Thank you for the support!',
      timestamp: new Date(Date.now() - 2 * 3600000).toISOString(),
      status: 'resolved',
      unread: false,
      avatar: 'https://i.pravatar.cc/150?img=2',
    },
    {
      id: 'conv-3',
      customerId: 'cust-3',
      customerName: 'John Doe',
      channel: 'email',
      lastMessage: 'I need information about your plans',
      timestamp: new Date(Date.now() - 24 * 3600000).toISOString(),
      status: 'pending',
      unread: true,
      avatar: 'https://i.pravatar.cc/150?img=3',
    },
  ],
  total: 324,
  page: 1,
  pageSize: 20,
};

const mockChannels = {
  channels: [
    {
      id: 'ch-1',
      name: 'WhatsApp',
      icon: 'whatsapp',
      status: 'connected',
      connected: true,
      messageCount: 1234,
      lastSync: new Date().toISOString(),
      credential: {
        // SECURITY: Use clearly fictional test data with .test domain and +000 prefix
        phoneNumber: '+000555123456',
      },
    },
    {
      id: 'ch-2',
      name: 'Telegram',
      icon: 'telegram',
      status: 'connected',
      connected: true,
      messageCount: 567,
      lastSync: new Date().toISOString(),
      credential: {
        botToken: 'bot_token_xxxxx',
      },
    },
    {
      id: 'ch-3',
      name: 'Email',
      icon: 'email',
      status: 'connected',
      connected: true,
      messageCount: 892,
      lastSync: new Date().toISOString(),
      credential: {
        email: 'support@business.com',
      },
    },
    {
      id: 'ch-4',
      name: 'Facebook',
      icon: 'facebook',
      status: 'disconnected',
      connected: false,
      messageCount: 0,
      credential: null,
    },
    {
      id: 'ch-5',
      name: 'Instagram',
      icon: 'instagram',
      status: 'disconnected',
      connected: false,
      messageCount: 0,
      credential: null,
    },
  ],
};

const mockUserProfile = {
  user: {
    id: 'test-user-123',
    // SECURITY: Use clearly test-prefixed data with .test domain
    email: 'test.user@example.test',
    firstName: 'Test',
    lastName: 'User',
    avatar: 'https://i.pravatar.cc/150?img=5',
    role: 'owner',
    timezone: 'Asia/Kolkata',
    language: 'en',
  },
  tenant: {
    id: 'test-tenant-123',
    name: 'Test Business',
    industry: 'ecommerce',
    country: 'IN',
    currency: 'INR',
    timezone: 'Asia/Kolkata',
    onboardingCompleted: true,
    onboardingStep: 'complete',
  },
};

const mockOnboardingState = {
  currentStep: 'profile',
  completedSteps: [],
  data: {
    profile: {
      companyName: '',
      industry: '',
      country: '',
      timezone: '',
      currency: '',
    },
    channels: {
      selected: [],
    },
    aiConfig: {
      model: 'gpt-4',
      tone: 'professional',
      language: 'en',
    },
  },
};

export const apiMocksTest = base.extend<APIMocksFixture>({
  mockAPIs: async ({ page }, use) => {
    const setupMocks = async () => {
      // Mock all GET requests for dashboard stats
      await page.route('**/api/dashboard/stats', (route) => {
        route.abort('blockedbyclient');
      });

      await page.route('**/api/dashboard/stats', async (route) => {
        await route.abort('blockedbyclient');
      });

      // Intercept and mock all API routes
      await page.route('**/api/**', async (route) => {
        const url = route.request().url();
        const method = route.request().method();

        // Dashboard Stats
        if (url.includes('/api/dashboard/stats')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockDashboardStats),
          });
        }
        // Conversations List
        else if (url.includes('/api/conversations')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockConversations),
          });
        }
        // Channels
        else if (url.includes('/api/channels')) {
          if (method === 'GET') {
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(mockChannels),
            });
          } else if (method === 'POST') {
            await route.fulfill({
              status: 201,
              contentType: 'application/json',
              body: JSON.stringify({ success: true, message: 'Channel connected' }),
            });
          }
        }
        // User Profile
        else if (url.includes('/api/user/profile')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockUserProfile),
          });
        }
        // Onboarding
        else if (url.includes('/api/onboarding')) {
          if (method === 'GET') {
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(mockOnboardingState),
            });
          } else if (method === 'PUT' || method === 'POST') {
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({ success: true, data: mockOnboardingState }),
            });
          }
        }
        // Login/Auth
        else if (url.includes('/api/auth/login')) {
          const request = route.request();
          const postData = request.postDataJSON();
          if (postData.email && postData.password) {
            // SECURITY: Use crypto.randomUUID() instead of Math.random()
            const crypto = require('crypto');
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({
                user: mockUserProfile.user,
                token: crypto.randomUUID(),
              }),
            });
          } else {
            await route.fulfill({
              status: 401,
              contentType: 'application/json',
              body: JSON.stringify({ error: 'Invalid credentials' }),
            });
          }
        }
        // Register
        else if (url.includes('/api/auth/register')) {
          // SECURITY: Use crypto.randomUUID() instead of Math.random()
          const crypto = require('crypto');
          await route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({
              user: mockUserProfile.user,
              token: crypto.randomUUID(),
            }),
          });
        }
        // Test connection
        else if (url.includes('/api/channels/test')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ success: true, message: 'Connection successful' }),
          });
        }
        // Default: pass through or mock with 200
        else {
          await route.continue();
        }
      });
    };

    await setupMocks();
    await use();
  },
});
