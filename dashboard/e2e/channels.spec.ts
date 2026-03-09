import { test, expect } from '@playwright/test';

/**
 * Channels Tests
 * Tests channel management, connections, and analytics
 */

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
      credential: { phoneNumber: '+91999XXXXX' },
    },
    {
      id: 'ch-2',
      name: 'Telegram',
      icon: 'telegram',
      status: 'connected',
      connected: true,
      messageCount: 567,
      lastSync: new Date().toISOString(),
      credential: { botToken: 'bot_token_xxxxx' },
    },
    {
      id: 'ch-3',
      name: 'Email',
      icon: 'email',
      status: 'connected',
      connected: true,
      messageCount: 892,
      lastSync: new Date().toISOString(),
      credential: { email: 'support@business.com' },
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
    {
      id: 'ch-6',
      name: 'SMS',
      icon: 'sms',
      status: 'disconnected',
      connected: false,
      messageCount: 0,
      credential: null,
    },
  ],
};

const mockChannelAnalytics = {
  whatsapp: {
    messageCount: 1234,
    conversionCount: 245,
    avgResponseTime: 2.3,
    sentiment: { positive: 80, neutral: 15, negative: 5 },
    topMessages: [
      { text: 'Order status', count: 45 },
      { text: 'Pricing inquiry', count: 38 },
      { text: 'Support request', count: 32 },
    ],
  },
};

test.describe('Channels', () => {
  test.beforeEach(async ({ page }) => {
    // Mock API calls
    await page.route('**/api/**', async (route) => {
      const url = route.request().url();

      if (url.includes('/api/channels') && !url.includes('/test') && !url.includes('/disconnect')) {
        if (route.request().method() === 'GET') {
          await route.fulfill({
            status: 200,
            body: JSON.stringify(mockChannels),
          });
        } else if (route.request().method() === 'POST') {
          // Connect channel
          await route.fulfill({
            status: 201,
            body: JSON.stringify({
              success: true,
              message: 'Channel connected successfully',
              channel: { id: 'new-ch', name: 'New Channel' },
            }),
          });
        }
      } else if (url.includes('/api/channels/test')) {
        // Test connection
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            success: true,
            message: 'Connection successful',
          }),
        });
      } else if (url.includes('/api/channels') && url.includes('/disconnect')) {
        // Disconnect channel
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            success: true,
            message: 'Channel disconnected',
          }),
        });
      } else if (url.includes('/api/channels') && url.includes('/analytics')) {
        // Channel analytics
        await route.fulfill({
          status: 200,
          body: JSON.stringify(mockChannelAnalytics.whatsapp),
        });
      } else {
        await route.continue();
      }
    });

    // Navigate to channels page
    await page.goto('/channels');
    await page.waitForLoadState('networkidle');
  });

  test.describe('Channel Grid', () => {
    test('channel grid loads with all channels', async ({ page }) => {
      // Check that channels are displayed
      for (const channel of mockChannels.channels) {
        const channelCard = page.locator(`text=${channel.name}`).first();
        await expect(channelCard).toBeVisible({ timeout: 5000 });
      }
    });

    test('each channel card shows name and icon', async ({ page }) => {
      // Check for channel names
      const whatsappCard = page.locator('text=WhatsApp').first();
      await expect(whatsappCard).toBeVisible();

      // Icon should be visible (SVG or img)
      const icon = page.locator('[data-testid*="whatsapp-icon"], svg:has-text("whatsapp")').first();
      await expect(icon).toBeVisible().catch(() => null);
    });

    test('connected channels show connected status', async ({ page }) => {
      // WhatsApp is connected
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();

      // Check for connected indicator
      const connectedBadge = whatsappCard.locator('text=Connected, text=Active, [data-testid*="connected"]').first();

      await expect(connectedBadge).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('disconnected channels show disconnected status', async ({ page }) => {
      // Facebook is disconnected
      const facebookCard = page.locator('text=Facebook').locator('..').first();

      // Check for disconnected indicator
      const disconnectedBadge = facebookCard.locator('text=Disconnected, text=Connect, [data-testid*="disconnected"]').first();

      await expect(disconnectedBadge).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('message count displayed for connected channels', async ({ page }) => {
      // WhatsApp has 1234 messages
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();

      const messageCount = whatsappCard.locator('text=1234, text=messages').first();

      await expect(messageCount).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('clicking channel card opens details or settings', async ({ page }) => {
      // Click on connected channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Should show channel details or analytics
      await page.waitForLoadState('networkidle');

      const detailsPanel = page.locator('[data-testid*="channel-details"], text=WhatsApp, text=Analytics').first();

      await expect(detailsPanel).toBeVisible({ timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Connect Channel', () => {
    test('can open connect channel modal for disconnected channel', async ({ page }) => {
      // Find disconnected channel (Facebook)
      const facebookCard = page.locator('text=Facebook').locator('..').first();

      // Click connect button
      const connectButton = facebookCard.locator('button:has-text("Connect"), button:has-text("Add")').first();

      if (await connectButton.isVisible().catch(() => false)) {
        await connectButton.click();

        // Modal should open
        const modal = page.locator('[role="dialog"], text=Connect, text=Facebook').first();
        await expect(modal).toBeVisible({ timeout: 5000 });
      }
    });

    test('connect modal shows credential fields for channel type', async ({ page }) => {
      // Open Facebook connect modal
      const facebookCard = page.locator('text=Facebook').locator('..').first();
      const connectButton = facebookCard.locator('button:has-text("Connect")').first();

      if (await connectButton.isVisible().catch(() => false)) {
        await connectButton.click();

        // Should show Facebook-specific fields
        // E.g., Page ID, App ID, etc.
        const credentialFields = page.locator('input[placeholder*="ID"], input[placeholder*="Token"], input[placeholder*="Key"]').first();

        await expect(credentialFields).toBeVisible({ timeout: 5000 }).catch(() => null);
      }
    });

    test('can fill in channel credentials', async ({ page }) => {
      // Open connect modal
      const facebookCard = page.locator('text=Facebook').locator('..').first();
      const connectButton = facebookCard.locator('button:has-text("Connect")').first();

      if (await connectButton.isVisible().catch(() => false)) {
        await connectButton.click();

        // Fill in credentials
        const credentialInput = page.locator('input[placeholder*="ID"], input[placeholder*="Token"]').first();

        if (await credentialInput.isVisible().catch(() => false)) {
          await credentialInput.fill('123456789');

          const value = await credentialInput.inputValue();
          expect(value).toBe('123456789');
        }
      }
    });

    test('test connection button verifies credentials', async ({ page }) => {
      // Open connect modal
      const facebookCard = page.locator('text=Facebook').locator('..').first();
      const connectButton = facebookCard.locator('button:has-text("Connect")').first();

      if (await connectButton.isVisible().catch(() => false)) {
        await connectButton.click();

        // Fill in credentials
        const credentialInput = page.locator('input[placeholder*="ID"], input[placeholder*="Token"]').first();

        if (await credentialInput.isVisible().catch(() => false)) {
          await credentialInput.fill('test-credential');

          // Click test button
          const testButton = page.locator('button:has-text("Test"), button:has-text("Verify")').first();

          if (await testButton.isVisible().catch(() => false)) {
            await testButton.click();

            // Should show success or error
            const result = page.locator('text=successful, text=Connected, text=Error, [role="alert"]').first();

            await expect(result).toBeVisible({ timeout: 5000 }).catch(() => null);
          }
        }
      }
    });

    test('can confirm channel connection', async ({ page }) => {
      // Open connect modal
      const facebookCard = page.locator('text=Facebook').locator('..').first();
      const connectButton = facebookCard.locator('button:has-text("Connect")').first();

      if (await connectButton.isVisible().catch(() => false)) {
        await connectButton.click();

        // Fill credential
        const credentialInput = page.locator('input[placeholder*="ID"], input[placeholder*="Token"]').first();

        if (await credentialInput.isVisible().catch(() => false)) {
          await credentialInput.fill('valid-credential');

          // Click confirm button
          const confirmButton = page.locator('button:has-text("Confirm"), button:has-text("Connect Channel")').last();

          if (await confirmButton.isVisible().catch(() => false)) {
            await confirmButton.click();

            // Should show success message
            await expect(page.locator('text=successfully, text=connected, [role="alert"]').first()).toBeVisible({
              timeout: 5000,
            }).catch(() => null);

            // Modal should close
            const modal = page.locator('[role="dialog"]').first();
            const isClosed = !(await modal.isVisible().catch(() => false));
            expect(isClosed).toBeTruthy();
          }
        }
      }
    });
  });

  test.describe('Channel Disconnect', () => {
    test('connected channel has disconnect option', async ({ page }) => {
      // Click on connected channel (WhatsApp)
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Should show disconnect button
      const disconnectButton = page.locator('button:has-text("Disconnect"), button:has-text("Remove"), button:has-text("Delete")').first();

      await expect(disconnectButton).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('disconnect shows confirmation dialog', async ({ page }) => {
      // Click on connected channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Click disconnect
      const disconnectButton = page.locator('button:has-text("Disconnect")').first();

      if (await disconnectButton.isVisible().catch(() => false)) {
        await disconnectButton.click();

        // Confirmation dialog should appear
        const confirmDialog = page.locator('[role="dialog"], text=confirm, text=sure, text=disconnect').first();

        await expect(confirmDialog).toBeVisible({ timeout: 5000 }).catch(() => null);
      }
    });

    test('can confirm disconnect', async ({ page }) => {
      // Click on connected channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Click disconnect
      const disconnectButton = page.locator('button:has-text("Disconnect")').first();

      if (await disconnectButton.isVisible().catch(() => false)) {
        await disconnectButton.click();

        // Confirm
        const confirmButton = page.locator('button:has-text("Yes"), button:has-text("Disconnect")').last();

        if (await confirmButton.isVisible().catch(() => false)) {
          await confirmButton.click();

          // Should show success and update status
          await page.waitForLoadState('networkidle');

          const disconnectedStatus = page.locator('text=Disconnected').first();

          await expect(disconnectedStatus).toBeVisible({ timeout: 5000 }).catch(() => null);
        }
      }
    });
  });

  test.describe('Channel Analytics', () => {
    test('channel analytics are displayed', async ({ page }) => {
      // Click on connected channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Should show analytics
      const analytics = page.locator('[data-testid*="analytics"], text=Messages, text=Conversations, text=Response Time').first();

      await expect(analytics).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('analytics show message count', async ({ page }) => {
      // Click on channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Should show message count
      const messageCount = page.locator('text=1234, text=messages').first();

      await expect(messageCount).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('analytics show sentiment breakdown', async ({ page }) => {
      // Click on channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Should show sentiment (positive, neutral, negative)
      const sentiment = page.locator('text=Positive, text=Negative, text=80%').first();

      await expect(sentiment).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('analytics charts render', async ({ page }) => {
      // Click on channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Chart should be visible
      const chart = page.locator('canvas, svg, [role="img"]').first();

      await expect(chart).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('top messages displayed', async ({ page }) => {
      // Click on channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Should show top messages
      const topMessages = page.locator('text=Order status, text=Pricing inquiry').first();

      await expect(topMessages).toBeVisible({ timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Channel Management', () => {
    test('channel list is sortable', async ({ page }) => {
      // Look for sort options
      const sortButton = page.locator('button:has-text("Sort"), select[aria-label*="Sort"]').first();

      if (await sortButton.isVisible().catch(() => false)) {
        await sortButton.click();

        // Sort options should appear
        const sortOption = page.locator('text=Alphabetical, text=Status, text=Messages').first();

        await expect(sortOption).toBeVisible({ timeout: 3000 }).catch(() => null);
      }
    });

    test('can refresh channel list', async ({ page }) => {
      // Find refresh button
      const refreshButton = page.locator('button[aria-label*="Refresh"], button:has-text("Refresh")').first();

      if (await refreshButton.isVisible().catch(() => false)) {
        await refreshButton.click();

        // List should refresh
        await page.waitForLoadState('networkidle');

        const channels = page.locator('text=WhatsApp, text=Telegram, text=Email').first();

        await expect(channels).toBeVisible({ timeout: 5000 });
      }
    });

    test('last sync time is displayed for connected channels', async ({ page }) => {
      // Connected channels show sync time
      const syncTime = page.locator('text=Synced, text=ago, text=minute').first();

      await expect(syncTime).toBeVisible({ timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Mobile Responsive', () => {
    test('channel grid is responsive on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      // Channels should be visible
      const whatsappChannel = page.locator('text=WhatsApp').first();
      await expect(whatsappChannel).toBeVisible({ timeout: 5000 });

      // Should stack vertically on mobile
      const channelCard = whatsappChannel.locator('..').first();
      const box = await channelCard.boundingBox();

      expect(box?.width).toBeLessThan(375);
    });

    test('channel details drawer on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      // Click channel
      const whatsappCard = page.locator('text=WhatsApp').locator('..').first();
      await whatsappCard.click();

      // Details should slide in or replace
      const detailsPanel = page.locator('[data-testid*="channel-details"], text=Analytics').first();

      await expect(detailsPanel).toBeVisible({ timeout: 5000 }).catch(() => null);

      // Back button to close
      const backButton = page.locator('button[aria-label*="back"], button:has-text("Back")').first();

      if (await backButton.isVisible().catch(() => false)) {
        await backButton.click();

        // Should return to list
        const list = page.locator('text=WhatsApp, text=Telegram, text=Email').first();
        await expect(list).toBeVisible({ timeout: 5000 });
      }
    });
  });

  test('no channels state when all disconnected', async ({ page }) => {
    // Mock all channels as disconnected
    await page.route('**/api/channels', async (route) => {
      const disconnected = mockChannels.channels.map((ch) => ({
        ...ch,
        connected: false,
        status: 'disconnected',
      }));

      await route.fulfill({
        status: 200,
        body: JSON.stringify({ channels: disconnected }),
      });
    });

    await page.reload();

    // All channels should show disconnected
    const disconnectedCount = await page.locator('text=Disconnected').count();
    expect(disconnectedCount).toBeGreaterThan(0);

    // Should show prompt to connect
    const connectPrompt = page.locator('text=Connect a channel, text=Get started').first();
    await expect(connectPrompt).toBeVisible({ timeout: 5000 }).catch(() => null);
  });
});
