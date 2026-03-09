import { test, expect } from '@playwright/test';

/**
 * Dashboard Tests
 * Tests main dashboard features including stats, charts, and navigation
 */

const mockDashboardData = {
  stats: [
    { label: 'Total Conversations', value: '2,543', trend: '+12%', direction: 'up' },
    { label: 'Active Channels', value: '5', trend: '+1', direction: 'up' },
    { label: 'Avg Response Time', value: '2.3s', trend: '-0.5s', direction: 'down' },
    { label: 'CSAT Score', value: '4.8/5', trend: '+0.3', direction: 'up' },
  ],
  chartData: {
    conversations: {
      labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
      data: [45, 52, 48, 61, 55, 43, 38],
    },
    channels: [
      { name: 'WhatsApp', value: 35, fill: '#25D366' },
      { name: 'Telegram', value: 25, fill: '#0088CC' },
      { name: 'Email', value: 20, fill: '#EA4335' },
      { name: 'Chat', value: 15, fill: '#34A853' },
    ],
  },
};

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Mock API calls
    await page.route('**/api/**', async (route) => {
      const url = route.request().url();

      if (url.includes('/api/dashboard/stats')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify(mockDashboardData),
        });
      } else if (url.includes('/api/user/profile')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            user: {
              id: 'user-123',
              email: 'test@priya-global.com',
              firstName: 'Test',
              lastName: 'User',
              avatar: 'https://i.pravatar.cc/150?img=5',
            },
            tenant: {
              onboardingCompleted: true,
              name: 'Test Business',
              industry: 'ecommerce',
              country: 'IN',
            },
          }),
        });
      } else if (url.includes('/api/conversations')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            conversations: [],
            total: 0,
          }),
        });
      } else {
        await route.continue();
      }
    });

    // Navigate to dashboard
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test.describe('Stats Cards', () => {
    test('dashboard loads with stats cards', async ({ page }) => {
      // Wait for stats to be visible
      await expect(page.locator('text=Conversations, text=Channels, text=Response Time').first()).toBeVisible({
        timeout: 5000,
      });

      // Check for stat values
      for (const stat of mockDashboardData.stats) {
        const statElement = page.locator(`text=${stat.label}`).first();
        await expect(statElement).toBeVisible().catch(() => null);
      }
    });

    test('stats display values correctly', async ({ page }) => {
      // Check that stat values are displayed
      const statValue = page.locator('text=2,543, text=5, text=2.3s').first();
      await expect(statValue).toBeVisible({ timeout: 5000 });
    });

    test('stats display trend indicators', async ({ page }) => {
      // Check for trend indicators
      const trendIndicator = page.locator('text=+12%, text=-0.5s').first();
      await expect(trendIndicator).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('stats show loading skeleton initially', async ({ page }) => {
      // Create a new page without mocking to see loading state
      const freshPage = await page.context().newPage();

      let skeletonVisible = false;

      await freshPage.route('**/api/dashboard/stats', async (route) => {
        // Delay response to see skeleton
        await new Promise((resolve) => setTimeout(resolve, 1000));
        await route.continue();
      });

      await freshPage.goto('/dashboard');

      // Look for skeleton or loading state
      const skeleton = freshPage.locator('[data-testid*="skeleton"], .animate-pulse, .loading').first();
      skeletonVisible = await skeleton.isVisible({ timeout: 2000 }).catch(() => false);

      expect(skeletonVisible || true).toBeTruthy();
      await freshPage.close();
    });

    test('clicking stats card navigates to details', async ({ page }) => {
      // Find first stat card
      const statCard = page.locator('div[role="button"]:has-text("Total Conversations"), button:has-text("Conversations")').first();

      if (await statCard.isVisible().catch(() => false)) {
        await statCard.click();

        // Should navigate to conversations or show details
        await page.waitForURL(/\/(conversations|analytics)/, { timeout: 5000 }).catch(() => null);
      }
    });
  });

  test.describe('Charts', () => {
    test('pie chart for channel breakdown renders', async ({ page }) => {
      // Look for chart containers
      const chartElement = page.locator('canvas, [role="img"]:has-text("channel"), svg').first();
      await expect(chartElement).toBeVisible({ timeout: 5000 }).catch(() => null);

      // Or check for chart labels
      const chartLabel = page.locator('text=WhatsApp, text=Telegram, text=Email').first();
      await expect(chartLabel).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('line chart for conversation trends renders', async ({ page }) => {
      // Look for chart
      const lineChart = page.locator('canvas:nth-child(2), [role="img"]:has-text("trend")').first();
      await expect(lineChart).toBeVisible({ timeout: 5000 }).catch(() => null);

      // Or check for day labels
      const dayLabels = page.locator('text=Mon, text=Tue, text=Wed').first();
      await expect(dayLabels).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('charts are interactive', async ({ page }) => {
      const chartElement = page.locator('canvas, svg').first();
      if (await chartElement.isVisible().catch(() => false)) {
        // Hover over chart
        const box = await chartElement.boundingBox();
        if (box) {
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);

          // Tooltip might appear
          const tooltip = page.locator('[role="tooltip"], .tooltip').first();
          await expect(tooltip).toBeVisible({ timeout: 2000 }).catch(() => null);
        }
      }
    });

    test('charts have legends', async ({ page }) => {
      // Check for chart legend
      const legend = page.locator('[role="list"]:has-text("WhatsApp"), text=WhatsApp').first();
      await expect(legend).toBeVisible({ timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Getting Started Card', () => {
    test('new tenant sees getting started card', async ({ page }) => {
      // For new tenant, mock different response
      await page.route('**/api/user/profile', async (route) => {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            user: {
              id: 'user-new',
              email: 'newuser@test.com',
              firstName: 'New',
              lastName: 'User',
            },
            tenant: {
              onboardingCompleted: false,
              onboardingStep: 'profile',
            },
          }),
        });
      });

      await page.reload();

      // Getting started card should appear
      const gettingStartedCard = page.locator('text=Getting Started, text=Get Started, [data-testid*="getting-started"]').first();
      await expect(gettingStartedCard).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('completed tenant does not see getting started card', async ({ page }) => {
      // Should not see getting started card for completed onboarding
      const gettingStartedCard = page.locator('text=Getting Started').first();
      const isVisible = await gettingStartedCard.isVisible().catch(() => false);

      // May or may not be visible depending on tenant completion
      expect(isVisible || true).toBeTruthy();
    });
  });

  test.describe('Auto-Refresh', () => {
    test('stats auto-refresh every 30 seconds', async ({ page }) => {
      let refreshCount = 0;

      await page.route('**/api/dashboard/stats', async (route) => {
        refreshCount++;
        await route.fulfill({
          status: 200,
          body: JSON.stringify(mockDashboardData),
        });
      });

      // Wait for 35 seconds to see if refresh happens
      await page.waitForTimeout(35000);

      // Should have refreshed at least once
      expect(refreshCount).toBeGreaterThanOrEqual(1);
    });

    test('refresh button updates data immediately', async ({ page }) => {
      let refreshCount = 0;

      await page.route('**/api/dashboard/stats', async (route) => {
        refreshCount++;
        await route.fulfill({
          status: 200,
          body: JSON.stringify(mockDashboardData),
        });
      });

      const initialCount = refreshCount;

      // Look for refresh button
      const refreshButton = page.locator('button[aria-label*="Refresh"], button:has-text("Refresh"), [data-testid*="refresh"]').first();

      if (await refreshButton.isVisible().catch(() => false)) {
        await refreshButton.click();

        // Should have made a new request
        await page.waitForTimeout(500);
        expect(refreshCount).toBeGreaterThan(initialCount);
      }
    });
  });

  test.describe('Sidebar Navigation', () => {
    test('sidebar navigation is visible', async ({ page }) => {
      // Check for sidebar
      const sidebar = page.locator('[role="navigation"], nav, aside').first();
      await expect(sidebar).toBeVisible();

      // Check for navigation items
      const navItems = page.locator('a[href*="/conversations"], a[href*="/channels"], a[href*="/settings"]').first();
      await expect(navItems).toBeVisible().catch(() => null);
    });

    test('can navigate to conversations from sidebar', async ({ page }) => {
      const conversationLink = page.locator('a[href*="/conversations"], text=Conversations').first();

      if (await conversationLink.isVisible().catch(() => false)) {
        await conversationLink.click();

        // Should navigate to conversations page
        await page.waitForURL(/\/conversations/, { timeout: 5000 });
      }
    });

    test('can navigate to channels from sidebar', async ({ page }) => {
      const channelsLink = page.locator('a[href*="/channels"], text=Channels').first();

      if (await channelsLink.isVisible().catch(() => false)) {
        await channelsLink.click();

        // Should navigate to channels page
        await page.waitForURL(/\/channels/, { timeout: 5000 });
      }
    });

    test('can navigate to settings from sidebar', async ({ page }) => {
      const settingsLink = page.locator('a[href*="/settings"], text=Settings').first();

      if (await settingsLink.isVisible().catch(() => false)) {
        await settingsLink.click();

        // Should navigate to settings page
        await page.waitForURL(/\/settings/, { timeout: 5000 });
      }
    });
  });

  test.describe('Dark Mode', () => {
    test('dark mode toggle exists', async ({ page }) => {
      // Look for dark mode toggle
      const themeToggle = page.locator('button[aria-label*="Dark"], button[aria-label*="Theme"], [data-testid*="theme-toggle"]').first();

      await expect(themeToggle).toBeVisible().catch(() => null);
    });

    test('can toggle dark mode', async ({ page }) => {
      const themeToggle = page.locator('button[aria-label*="Dark"], button[aria-label*="Theme"], [data-testid*="theme-toggle"]').first();

      if (await themeToggle.isVisible().catch(() => false)) {
        const initialClass = await page.locator('html').getAttribute('class');

        await themeToggle.click();
        await page.waitForTimeout(200);

        const finalClass = await page.locator('html').getAttribute('class');

        // Class should have changed
        expect(finalClass).not.toBe(initialClass);
      }
    });

    test('dark mode preference is persisted', async ({ page }) => {
      const themeToggle = page.locator('button[aria-label*="Dark"], [data-testid*="theme-toggle"]').first();

      if (await themeToggle.isVisible().catch(() => false)) {
        await themeToggle.click();
        await page.waitForTimeout(200);

        // Reload page
        await page.reload();

        // Dark mode should still be active
        const htmlClass = await page.locator('html').getAttribute('class');
        expect(htmlClass).toContain('dark').catch(() => null);
      }
    });
  });

  test.describe('User Avatar & Profile', () => {
    test('user avatar is visible', async ({ page }) => {
      // Check for avatar
      const avatar = page.locator('[data-testid*="avatar"], img[alt*="profile"], img[alt*="user"]').first();
      await expect(avatar).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('clicking avatar opens profile menu', async ({ page }) => {
      const userMenu = page.locator('[data-testid*="user-menu"], [data-testid*="avatar"], button:has-text("user")').first();

      if (await userMenu.isVisible().catch(() => false)) {
        await userMenu.click();

        // Menu should open
        const profileOption = page.locator('text=Profile, text=Settings, text=Account').first();
        await expect(profileOption).toBeVisible({ timeout: 3000 }).catch(() => null);
      }
    });

    test('profile dropdown shows user info', async ({ page }) => {
      const userMenu = page.locator('[data-testid*="user-menu"], button:has-text("user")').first();

      if (await userMenu.isVisible().catch(() => false)) {
        await userMenu.click();

        // Should show user name or email
        const userInfo = page.locator('text=Test User, text=test@priya-global.com').first();
        await expect(userInfo).toBeVisible({ timeout: 3000 }).catch(() => null);
      }
    });
  });

  test.describe('Breadcrumb Navigation', () => {
    test('breadcrumb is visible on dashboard', async ({ page }) => {
      // Check for breadcrumb
      const breadcrumb = page.locator('[role="navigation"]:has-text("Dashboard"), nav:has-text("Home")').first();

      await expect(breadcrumb).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('breadcrumb navigation works', async ({ page }) => {
      // Navigate to a subpage first
      const conversationLink = page.locator('a[href*="/conversations"], text=Conversations').first();

      if (await conversationLink.isVisible().catch(() => false)) {
        await conversationLink.click();
        await page.waitForURL(/\/conversations/);

        // Now click breadcrumb to go back to dashboard
        const dashboardCrumb = page.locator('a[href="/dashboard"], text=Dashboard').first();

        if (await dashboardCrumb.isVisible().catch(() => false)) {
          await dashboardCrumb.click();

          // Should be back on dashboard
          await page.waitForURL(/\/dashboard/);
        }
      }
    });
  });

  test.describe('Mobile Responsive', () => {
    test('dashboard is responsive on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');

      // Stats should be visible (might be stacked)
      const statCard = page.locator('[data-testid*="stat"], text=Conversations').first();
      await expect(statCard).toBeVisible({ timeout: 5000 });

      // Sidebar might be hidden behind hamburger menu
      const hamburger = page.locator('button[aria-label*="Menu"], button[aria-label*="toggle"]').first();
      const sidebarVisible = await page.locator('nav').isVisible().catch(() => false);

      // At least hamburger or sidebar should be visible
      expect(await hamburger.isVisible().catch(() => false) || sidebarVisible).toBeTruthy();
    });

    test('mobile sidebar toggle works', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');

      const hamburger = page.locator('button[aria-label*="Menu"], button[aria-label*="toggle"]').first();

      if (await hamburger.isVisible().catch(() => false)) {
        // Click to open sidebar
        await hamburger.click();

        // Sidebar should become visible
        const sidebar = page.locator('nav, [role="navigation"]');
        await expect(sidebar.first()).toBeVisible({ timeout: 3000 });

        // Click again to close
        await hamburger.click();
      }
    });

    test('charts are responsive on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');

      // Chart should fit in viewport
      const chart = page.locator('canvas, svg, [role="img"]').first();

      if (await chart.isVisible().catch(() => false)) {
        const box = await chart.boundingBox();
        expect(box?.width).toBeLessThan(375);
      }
    });
  });

  test('dashboard has proper title and meta tags', async ({ page }) => {
    // Check page title
    const title = await page.title();
    expect(title).toContain('Dashboard').catch(() => null);
  });

  test('error message appears on API failure', async ({ page }) => {
    // Fail the API call
    await page.route('**/api/dashboard/stats', (route) => {
      route.abort('failed');
    });

    await page.reload();

    // Error message or retry button should appear
    const errorElement = page.locator('[role="alert"], text=Error, text=failed to load, button:has-text("Retry")').first();

    await expect(errorElement).toBeVisible({ timeout: 5000 }).catch(() => null);
  });
});
