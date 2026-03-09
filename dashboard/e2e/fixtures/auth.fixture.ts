import { test as base, expect } from '@playwright/test';

/**
 * Auth Fixture
 * Provides authentication utilities and test credentials
 */

export const TEST_USERS = {
  valid: {
    email: 'test.user@example.test',
    password: process.env.TEST_USER_PASSWORD || 'SecurePass123!',
    firstName: 'Test',
    lastName: 'User',
  },
  admin: {
    email: 'admin.user@example.test',
    password: process.env.TEST_ADMIN_PASSWORD || 'AdminPass123!',
    firstName: 'Admin',
    lastName: 'User',
  },
  invalid: {
    email: 'invalid@test.test',
    password: 'wrongpassword',
  },
};
// SECURITY NOTE: Test credentials should be loaded from .env.test file in production.
// Use `npx dotenv -e .env.test -- playwright test` to load test environment variables.
// Never commit actual passwords to version control.

export type AuthFixture = {
  authToken: string;
  userId: string;
  storageState: string;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  getAuthToken: () => string;
};

export const authTest = base.extend<AuthFixture>({
  authToken: '',
  userId: 'test-user-123',
  storageState: 'auth-state.json',

  login: async ({ page }, use) => {
    const loginFunc = async (email: string, password: string) => {
      await page.goto('/login');
      await page.fill('input[type="email"]', email);
      await page.fill('input[type="password"]', password);
      await page.click('button:has-text("Sign In")');

      // Wait for navigation to dashboard
      await page.waitForURL(/\/dashboard/, { timeout: 5000 }).catch(() => null);
    };

    await use(loginFunc);
  },

  logout: async ({ page }, use) => {
    const logoutFunc = async () => {
      // Click on user avatar/menu
      await page.click('[data-testid="user-menu"]').catch(() => null);
      // Click logout
      await page.click('button:has-text("Logout")').catch(() => null);
      // Wait for redirect to login
      await page.waitForURL('/login', { timeout: 5000 }).catch(() => null);
    };

    await use(logoutFunc);
  },

  getAuthToken: async ({}, use) => {
    const getTokenFunc = () => {
      // Generate a realistic token for testing
      const crypto = require('crypto');
      return crypto.randomUUID();
    };

    await use(getTokenFunc);
  },

  // Fixture initialization
  async authToken({}, use) {
    // SECURITY: Use cryptographically secure token generation
    const crypto = require('crypto');
    const token = crypto.randomUUID();
    await use(token);
  },
});

export { expect };
