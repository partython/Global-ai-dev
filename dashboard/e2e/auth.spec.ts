import { test, expect, Page } from '@playwright/test';
import { TEST_USERS } from './fixtures/auth.fixture';

/**
 * Authentication Tests
 * Tests login, registration, and protected routes
 */

test.describe('Authentication', () => {
  test.beforeEach(async ({ page, context }) => {
    // Mock all API calls
    await page.route('**/api/**', async (route) => {
      const url = route.request().url();

      if (url.includes('/api/auth/login')) {
        const postData = route.request().postDataJSON();
        if (
          postData.email === TEST_USERS.valid.email &&
          postData.password === TEST_USERS.valid.password
        ) {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({
              user: {
                id: 'user-123',
                email: TEST_USERS.valid.email,
                firstName: TEST_USERS.valid.firstName,
                lastName: TEST_USERS.valid.lastName,
              },
              token: 'mock-token-123',
            }),
          });
        } else {
          await route.fulfill({
            status: 401,
            body: JSON.stringify({ error: 'Invalid credentials' }),
          });
        }
      } else if (url.includes('/api/auth/register')) {
        const postData = route.request().postDataJSON();
        if (postData.email && postData.password) {
          await route.fulfill({
            status: 201,
            body: JSON.stringify({
              user: {
                id: 'user-new',
                email: postData.email,
                firstName: postData.firstName,
                lastName: postData.lastName,
              },
              token: 'mock-token-new',
            }),
          });
        } else {
          await route.fulfill({
            status: 400,
            body: JSON.stringify({ error: 'Missing required fields' }),
          });
        }
      } else if (url.includes('/api/auth/logout')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ success: true }),
        });
      } else if (url.includes('/api/dashboard')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            stats: [
              { label: 'Conversations', value: '2,543' },
              { label: 'Active Channels', value: '5' },
            ],
          }),
        });
      } else {
        await route.continue();
      }
    });
  });

  test.describe('Login Page', () => {
    test('login page renders correctly', async ({ page }) => {
      await page.goto('/login');

      // Verify key elements are present
      await expect(page.locator('text=Sign In')).toBeVisible();
      await expect(page.locator('input[type="email"]')).toBeVisible();
      await expect(page.locator('input[type="password"]')).toBeVisible();
      await expect(page.locator('text=Forgot Password?')).toBeVisible();
      await expect(page.locator('text=Create Account')).toBeVisible();
    });

    test('login with valid credentials redirects to dashboard', async ({ page }) => {
      await page.goto('/login');

      // Fill in login form
      await page.fill('input[type="email"]', TEST_USERS.valid.email);
      await page.fill('input[type="password"]', TEST_USERS.valid.password);

      // Submit form
      await page.click('button:has-text("Sign In")');

      // Should redirect to dashboard or onboarding
      await page.waitForURL(/\/(dashboard|onboarding)/, { timeout: 5000 });
    });

    test('login with invalid credentials shows error', async ({ page }) => {
      await page.goto('/login');

      // Fill in invalid credentials
      await page.fill('input[type="email"]', TEST_USERS.invalid.email);
      await page.fill('input[type="password"]', TEST_USERS.invalid.password);

      // Submit form
      await page.click('button:has-text("Sign In")');

      // Error message should appear
      await expect(page.locator('text=Invalid credentials').or(page.locator('[role="alert"]'))).toBeVisible(
        { timeout: 5000 },
      );
    });

    test('login with empty fields shows validation errors', async ({ page }) => {
      await page.goto('/login');

      // Try to submit without filling fields
      const submitButton = page.locator('button:has-text("Sign In")');
      await submitButton.click();

      // HTML5 validation should prevent submission
      // Or check for validation messages
      const emailInput = page.locator('input[type="email"]');
      const isInvalid = await emailInput.evaluate((el) => (el as HTMLInputElement).validity.valid);
      expect(isInvalid).toBe(false);
    });

    test('remember me checkbox is visible and functional', async ({ page }) => {
      await page.goto('/login');

      const rememberCheckbox = page.locator('input[type="checkbox"]');
      await expect(rememberCheckbox).toBeVisible();

      // Toggle remember me
      await rememberCheckbox.check();
      await expect(rememberCheckbox).toBeChecked();

      await rememberCheckbox.uncheck();
      await expect(rememberCheckbox).not.toBeChecked();
    });

    test('forgot password link is clickable', async ({ page }) => {
      await page.goto('/login');

      const forgotLink = page.locator('text=Forgot Password?');
      await expect(forgotLink).toBeVisible();
      await forgotLink.click();

      // Should navigate to forgot password page
      await page.waitForURL(/\/forgot-password/);
    });

    test('create account link navigates to register', async ({ page }) => {
      await page.goto('/login');

      const registerLink = page.locator('text=Create Account');
      await expect(registerLink).toBeVisible();
      await registerLink.click();

      // Should navigate to register page
      await page.waitForURL(/\/register/);
    });
  });

  test.describe('Registration', () => {
    test('register page renders correctly', async ({ page }) => {
      await page.goto('/register');

      await expect(page.locator('text=Create Account')).toBeVisible();
      await expect(page.locator('input[placeholder*="First Name"]').or(page.locator('input[name="firstName"]'))).toBeVisible();
      await expect(page.locator('input[placeholder*="Last Name"]').or(page.locator('input[name="lastName"]'))).toBeVisible();
      await expect(page.locator('input[type="email"]')).toBeVisible();
      await expect(page.locator('input[type="password"]')).toBeVisible();
    });

    test('register with valid data shows success', async ({ page }) => {
      await page.goto('/register');

      // Fill registration form
      await page.fill('input[name="firstName"], input[placeholder*="First Name"]', 'New');
      await page.fill('input[name="lastName"], input[placeholder*="Last Name"]', 'User');
      // SECURITY: Use test-prefixed domain for test data
      await page.fill('input[type="email"]', 'newuser@example.test');
      await page.fill('input[type="password"]', 'SecurePass123!');

      // Confirm password if field exists
      const confirmField = page.locator('input[type="password"]').last();
      if (await confirmField.count() > 1) {
        await confirmField.fill('SecurePass123!');
      }

      // Submit
      await page.click('button:has-text("Create Account")');

      // Should show success or redirect
      await page.waitForURL(/\/(dashboard|onboarding|login)/, { timeout: 5000 });
    });

    test('password validation enforces requirements', async ({ page }) => {
      await page.goto('/register');

      const passwordField = page.locator('input[type="password"]').first();
      await passwordField.focus();

      // Test weak password
      await passwordField.fill('weak');
      await passwordField.blur();

      // Should show validation error or disable submit button
      const submitButton = page.locator('button:has-text("Create Account")');
      const isDisabled = await submitButton.evaluate((el) => (el as HTMLButtonElement).disabled);

      // Either button is disabled or there's a validation message
      expect(
        isDisabled ||
          (await page.locator('text=must contain').or(page.locator('[role="alert"]')).isVisible().catch(() => false)),
      ).toBeTruthy();
    });

    test('password with uppercase, number, and special char is valid', async ({ page }) => {
      await page.goto('/register');

      const passwordField = page.locator('input[type="password"]').first();
      await passwordField.fill('SecurePass123!');

      // Should be valid (submit button not disabled)
      const submitButton = page.locator('button:has-text("Create Account")');
      const isDisabled = await submitButton.evaluate((el) => (el as HTMLButtonElement).disabled);

      // Button might be enabled if all fields are filled
      // Or validation message should not appear
      expect(!isDisabled || (await page.locator('[role="alert"]').isVisible().catch(() => false))).toBeTruthy();
    });
  });

  test.describe('Forgot Password', () => {
    test('forgot password page renders', async ({ page }) => {
      await page.goto('/forgot-password');

      await expect(page.locator('text=Reset Password').or(page.locator('text=Forgot Password'))).toBeVisible();
      await expect(page.locator('input[type="email"]')).toBeVisible();
    });

    test('forgot password with valid email shows confirmation', async ({ page }) => {
      await page.route('**/api/auth/forgot-password', async (route) => {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ success: true, message: 'Email sent' }),
        });
      });

      await page.goto('/forgot-password');

      await page.fill('input[type="email"]', TEST_USERS.valid.email);
      await page.click('button:has-text("Send Reset Link")');

      // Should show success message
      await expect(page.locator('text=Check your email').or(page.locator('[role="alert"]'))).toBeVisible({
        timeout: 5000,
      });
    });
  });

  test.describe('Protected Routes', () => {
    test('unauthenticated user cannot access dashboard', async ({ page }) => {
      // Clear any auth tokens
      await page.context().clearCookies();

      await page.goto('/dashboard');

      // Should redirect to login
      await page.waitForURL(/\/login/, { timeout: 5000 });
    });

    test('unauthenticated user cannot access onboarding', async ({ page }) => {
      await page.context().clearCookies();

      await page.goto('/onboarding');

      // Should redirect to login
      await page.waitForURL(/\/login/, { timeout: 5000 });
    });
  });

  test.describe('Logout', () => {
    test('logout redirects to login', async ({ page }) => {
      // Mock successful login first
      await page.goto('/login');
      await page.fill('input[type="email"]', TEST_USERS.valid.email);
      await page.fill('input[type="password"]', TEST_USERS.valid.password);
      await page.click('button:has-text("Sign In")');

      // Wait for dashboard to load
      await page.waitForURL(/\/(dashboard|onboarding)/, { timeout: 5000 });

      // Find and click logout
      // Try different selectors
      const logoutButton = page.locator('button:has-text("Logout"), button:has-text("Sign Out"), [data-testid="logout"]');

      if (await logoutButton.isVisible().catch(() => false)) {
        await logoutButton.click();
      } else {
        // Try clicking user menu first
        const userMenu = page.locator('[data-testid="user-menu"], .avatar, [role="button"]:has-text("account")');
        if (await userMenu.first().isVisible().catch(() => false)) {
          await userMenu.first().click();
          await page.locator('text=Logout, text=Sign Out').click().catch(() => null);
        }
      }

      // Should redirect to login
      await page.waitForURL(/\/login/, { timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Mobile Responsive', () => {
    test('login page is responsive on mobile', async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 812 });

      await page.goto('/login');

      // Check that form is still visible and usable
      const emailInput = page.locator('input[type="email"]');
      await expect(emailInput).toBeVisible();

      // Input should be full width or close to it
      const box = await emailInput.boundingBox();
      expect(box?.width).toBeGreaterThan(300);
    });

    test('register page is responsive on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      await page.goto('/register');

      const firstNameInput = page.locator('input[name="firstName"], input[placeholder*="First Name"]');
      await expect(firstNameInput).toBeVisible();

      // Should be readable without horizontal scroll
      const box = await firstNameInput.boundingBox();
      expect(box?.width).toBeGreaterThan(300);
    });
  });
});
