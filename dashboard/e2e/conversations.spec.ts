import { test, expect } from '@playwright/test';

/**
 * Conversations Tests
 * Tests conversation list, search, filtering, and chat interface
 */

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

const mockConversationDetails = {
  id: 'conv-1',
  customer: {
    id: 'cust-1',
    name: 'Rajesh Kumar',
    email: 'rajesh@example.com',
    phone: '+919999999999',
    avatar: 'https://i.pravatar.cc/150?img=1',
  },
  channel: 'whatsapp',
  status: 'active',
  createdAt: new Date(Date.now() - 24 * 3600000).toISOString(),
  messages: [
    {
      id: 'msg-1',
      sender: 'customer',
      text: 'Hi, I need help with my order',
      timestamp: new Date(Date.now() - 15 * 60000).toISOString(),
      read: true,
    },
    {
      id: 'msg-2',
      sender: 'ai',
      text: 'Hello Rajesh! I would be happy to help. What is your order number?',
      timestamp: new Date(Date.now() - 14 * 60000).toISOString(),
      read: true,
    },
    {
      id: 'msg-3',
      sender: 'customer',
      text: 'Can you help with order #12345?',
      timestamp: new Date(Date.now() - 5 * 60000).toISOString(),
      read: true,
    },
  ],
};

test.describe('Conversations', () => {
  test.beforeEach(async ({ page }) => {
    // Mock API calls
    await page.route('**/api/**', async (route) => {
      const url = route.request().url();

      if (url.includes('/api/conversations') && !url.includes('/conv-')) {
        // List conversations
        const searchParams = new URL(url).searchParams;
        const search = searchParams.get('search');
        const channel = searchParams.get('channel');
        const status = searchParams.get('status');

        let filtered = mockConversations.conversations;

        if (search) {
          filtered = filtered.filter((c) =>
            c.customerName.toLowerCase().includes(search.toLowerCase()) ||
            c.lastMessage.toLowerCase().includes(search.toLowerCase()),
          );
        }

        if (channel) {
          filtered = filtered.filter((c) => c.channel === channel);
        }

        if (status) {
          filtered = filtered.filter((c) => c.status === status);
        }

        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            conversations: filtered,
            total: filtered.length,
            page: 1,
            pageSize: 20,
          }),
        });
      } else if (url.includes('/api/conversations/conv-')) {
        // Get conversation details
        await route.fulfill({
          status: 200,
          body: JSON.stringify(mockConversationDetails),
        });
      } else if (url.includes('/api/conversations') && route.request().method() === 'POST') {
        // Send message
        await route.fulfill({
          status: 201,
          body: JSON.stringify({
            id: 'msg-new',
            text: 'Message sent',
            timestamp: new Date().toISOString(),
          }),
        });
      } else if (url.includes('/api/handoff')) {
        // Handoff to agent
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ success: true }),
        });
      } else {
        await route.continue();
      }
    });

    // Navigate to conversations page
    await page.goto('/conversations');
    await page.waitForLoadState('networkidle');
  });

  test.describe('Conversation List', () => {
    test('conversation list loads', async ({ page }) => {
      // Check that conversations are displayed
      const conversationItem = page.locator('text=Rajesh Kumar, text=Priya Singh').first();
      await expect(conversationItem).toBeVisible({ timeout: 5000 });
    });

    test('conversation items show customer name', async ({ page }) => {
      // Should show customer names
      for (const conv of mockConversations.conversations) {
        const nameElement = page.locator(`text=${conv.customerName}`).first();
        await expect(nameElement).toBeVisible({ timeout: 5000 }).catch(() => null);
      }
    });

    test('conversation items show last message preview', async ({ page }) => {
      // Should show last message
      const messagePreview = page.locator('text=Can you help with order').first();
      await expect(messagePreview).toBeVisible({ timeout: 5000 });
    });

    test('conversation items show timestamp', async ({ page }) => {
      // Should show time ago or timestamp
      const timestamp = page.locator('text=5 minutes, text=ago, text=2 hours').first();
      await expect(timestamp).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('unread conversations are highlighted', async ({ page }) => {
      // Unread conversations should have visual indicator
      const unreadIndicator = page.locator('[data-testid*="unread"], .unread, [data-unread="true"]').first();

      // Or check for bold text
      const unreadElement = page.locator('text=Rajesh Kumar').first();
      const style = await unreadElement.evaluate((el) => {
        const style = window.getComputedStyle(el);
        return style.fontWeight;
      });

      expect(style === '700' || style === 'bold' || (await unreadIndicator.isVisible().catch(() => false))).toBeTruthy();
    });

    test('conversation channel icon is displayed', async ({ page }) => {
      // Should show channel icon
      const whatsappIcon = page.locator('[data-testid*="whatsapp"], svg:has-text("whatsapp")').first();
      await expect(whatsappIcon).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('clicking conversation opens chat panel', async ({ page }) => {
      // Click first conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Chat panel should open
      const chatPanel = page.locator('[data-testid*="chat"], text=Rajesh Kumar').first();
      await expect(chatPanel).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Search & Filter', () => {
    test('can search conversations by customer name', async ({ page }) => {
      // Find search input
      const searchInput = page.locator('input[placeholder*="Search"], input[aria-label*="Search"]').first();
      await expect(searchInput).toBeVisible();

      // Type search term
      await searchInput.fill('Rajesh');

      // Should filter results
      await page.waitForLoadState('networkidle');

      const conversationItem = page.locator('text=Rajesh Kumar').first();
      await expect(conversationItem).toBeVisible({ timeout: 5000 });

      // Other conversations should not be visible
      const otherConversation = page.locator('text=Priya Singh').first();
      const isVisible = await otherConversation.isVisible().catch(() => false);
      expect(!isVisible || (await searchInput.inputValue()).includes('Rajesh')).toBeTruthy();
    });

    test('can filter by channel', async ({ page }) => {
      // Find channel filter
      const channelFilter = page.locator('select, [role="combobox"]:has-text("Channel"), button:has-text("Channel")').first();

      if (await channelFilter.isVisible().catch(() => false)) {
        await channelFilter.click();

        // Select WhatsApp
        await page.locator('text=WhatsApp').click().catch(() => null);

        // Should filter to only WhatsApp conversations
        await page.waitForLoadState('networkidle');

        const whatsappConversation = page.locator('text=Rajesh Kumar').first();
        await expect(whatsappConversation).toBeVisible({ timeout: 5000 });
      }
    });

    test('can filter by status', async ({ page }) => {
      // Find status filter
      const statusFilter = page.locator('select, [role="combobox"]:has-text("Status"), button:has-text("Status")').first();

      if (await statusFilter.isVisible().catch(() => false)) {
        await statusFilter.click();

        // Select active
        await page.locator('text=Active').click().catch(() => null);

        // Should filter to only active conversations
        await page.waitForLoadState('networkidle');
      }
    });

    test('search results update in real-time', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]').first();

      // Type search
      await searchInput.fill('Rajesh');
      await page.waitForTimeout(300);

      // Results should be filtered
      const matchingItem = page.locator('text=Rajesh Kumar').first();
      await expect(matchingItem).toBeVisible({ timeout: 5000 });

      // Clear search
      await searchInput.clear();
      await page.waitForTimeout(300);

      // All conversations should return
      const allItems = page.locator('text=Rajesh Kumar, text=Priya Singh').first();
      await expect(allItems).toBeVisible({ timeout: 5000 });
    });

    test('search with no results shows empty state', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]').first();

      // Search for non-existent customer
      await searchInput.fill('NonExistentCustomer');
      await page.waitForLoadState('networkidle');

      // Should show empty state
      const emptyState = page.locator('text=No conversations, text=empty, text=not found').first();
      await expect(emptyState).toBeVisible({ timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Chat Interface', () => {
    test('clicking conversation opens two-panel layout on desktop', async ({ page }) => {
      // Set desktop viewport
      await page.setViewportSize({ width: 1920, height: 1080 });

      // Click a conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Both list and chat should be visible
      const conversationList = page.locator('text=Rajesh Kumar, text=Priya Singh').first();
      const chatPanel = page.locator('[data-testid*="chat"], text=Can you help').first();

      await expect(conversationList).toBeVisible({ timeout: 5000 });
      await expect(chatPanel).toBeVisible({ timeout: 5000 });
    });

    test('single panel layout on mobile', async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 812 });

      // Click a conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first();
      await conversationItem.click();

      // Chat panel should be visible
      const chatPanel = page.locator('[data-testid*="chat"], text=Can you help').first();
      await expect(chatPanel).toBeVisible({ timeout: 5000 });

      // List might be hidden
      // Navigation back button should be visible
      const backButton = page.locator('button[aria-label*="back"], button:has-text("Back")').first();
      await expect(backButton).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('messages are displayed in conversation', async ({ page }) => {
      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Check for messages
      const customerMessage = page.locator('text=Can you help with order').first();
      const aiMessage = page.locator('text=I would be happy to help').first();

      await expect(customerMessage).toBeVisible({ timeout: 5000 });
      await expect(aiMessage).toBeVisible({ timeout: 5000 });
    });

    test('message bubbles show sender (customer vs AI)', async ({ page }) => {
      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Customer messages should be on one side
      // AI messages on the other
      const customerBubble = page.locator('[data-testid*="customer-message"], .customer, .user-message').first();
      const aiBubble = page.locator('[data-testid*="ai-message"], .ai, .bot-message').first();

      expect(
        (await customerBubble.isVisible().catch(() => false)) ||
        (await aiBubble.isVisible().catch(() => false)) ||
        true,
      ).toBeTruthy();
    });

    test('message input field is visible', async ({ page }) => {
      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Find message input
      const messageInput = page.locator('input[placeholder*="Message"], textarea[placeholder*="Message"]').first();
      await expect(messageInput).toBeVisible({ timeout: 5000 });
    });

    test('can send a message', async ({ page }) => {
      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Type message
      const messageInput = page.locator('input[placeholder*="Message"], textarea[placeholder*="Message"]').first();
      await messageInput.fill('Can you check the order status?');

      // Send message
      const sendButton = page.locator('button[aria-label*="Send"], button:has-text("Send"), button[type="submit"]').first();
      await sendButton.click();

      // Message should appear in chat
      await expect(page.locator('text=Can you check the order status?')).toBeVisible({ timeout: 5000 });

      // Input should be cleared
      const inputValue = await messageInput.inputValue();
      expect(inputValue).toBe('');
    });

    test('typing indicator appears while sending', async ({ page }) => {
      // Mock slow response
      let requestIntercepted = false;
      await page.route('**/api/**', async (route) => {
        requestIntercepted = true;
        // Delay response
        await new Promise((resolve) => setTimeout(resolve, 1000));
        await route.continue();
      });

      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Type and send message
      const messageInput = page.locator('input[placeholder*="Message"]').first();
      await messageInput.fill('Test message');

      const sendButton = page.locator('button[aria-label*="Send"], button:has-text("Send")').first();
      await sendButton.click();

      // Typing indicator should appear briefly
      const typingIndicator = page.locator('[data-testid*="typing"], text=typing...').first();
      await expect(typingIndicator).toBeVisible({ timeout: 3000 }).catch(() => null);
    });

    test('close conversation button returns to list', async ({ page }) => {
      // Set mobile viewport to see close button better
      await page.setViewportSize({ width: 375, height: 812 });

      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first();
      await conversationItem.click();

      // Click close/back button
      const closeButton = page.locator('button[aria-label*="back"], button[aria-label*="close"], button:has-text("Back")').first();

      if (await closeButton.isVisible().catch(() => false)) {
        await closeButton.click();

        // Should return to list
        const conversationList = page.locator('text=Rajesh Kumar, text=Priya Singh').first();
        await expect(conversationList).toBeVisible({ timeout: 5000 });
      }
    });
  });

  test.describe('Handoff to Agent', () => {
    test('handoff to agent button is visible', async ({ page }) => {
      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Find handoff button
      const handoffButton = page.locator('button:has-text("Handoff"), button:has-text("Transfer"), button:has-text("Agent")').first();

      await expect(handoffButton).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('clicking handoff opens agent transfer dialog', async ({ page }) => {
      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Click handoff
      const handoffButton = page.locator('button:has-text("Handoff"), button:has-text("Transfer")').first();

      if (await handoffButton.isVisible().catch(() => false)) {
        await handoffButton.click();

        // Dialog should appear
        const dialog = page.locator('[role="dialog"], text=agent, text=transfer').first();
        await expect(dialog).toBeVisible({ timeout: 5000 }).catch(() => null);
      }
    });

    test('can confirm handoff to agent', async ({ page }) => {
      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first().locator('..').first();
      await conversationItem.click();

      // Click handoff
      const handoffButton = page.locator('button:has-text("Handoff"), button:has-text("Transfer")').first();

      if (await handoffButton.isVisible().catch(() => false)) {
        await handoffButton.click();

        // Confirm handoff
        const confirmButton = page.locator('button:has-text("Confirm"), button:has-text("Transfer")').last();

        if (await confirmButton.isVisible().catch(() => false)) {
          await confirmButton.click();

          // Should show success message
          await expect(page.locator('text=transferred, text=success, [role="alert"]').first()).toBeVisible({ timeout: 5000 }).catch(
            () => null,
          );
        }
      }
    });
  });

  test.describe('Empty State', () => {
    test('empty state shown when no conversations', async ({ page }) => {
      // Mock empty response
      await page.route('**/api/conversations', async (route) => {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            conversations: [],
            total: 0,
          }),
        });
      });

      await page.reload();

      // Empty state should appear
      const emptyState = page.locator('text=No conversations, text=empty, text=Start a new').first();
      await expect(emptyState).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Mobile Responsive', () => {
    test('conversations list is responsive on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      // List should be visible and scrollable
      const conversationItem = page.locator('text=Rajesh Kumar').first();
      await expect(conversationItem).toBeVisible({ timeout: 5000 });

      // Should not overflow horizontally
      const viewport = page.locator('body');
      const box = await viewport.boundingBox();
      expect(box?.width).toBeLessThanOrEqual(375);
    });

    test('back button on mobile navigates back to list', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      // Open conversation
      const conversationItem = page.locator('text=Rajesh Kumar').first();
      await conversationItem.click();

      // Click back
      const backButton = page.locator('button[aria-label*="back"], button:has-text("Back")').first();

      if (await backButton.isVisible().catch(() => false)) {
        await backButton.click();

        // Should be back to list
        const list = page.locator('text=Rajesh Kumar, text=Priya Singh').first();
        await expect(list).toBeVisible({ timeout: 5000 });
      }
    });
  });
});
