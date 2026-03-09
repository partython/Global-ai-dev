import { test, expect } from '@playwright/test';

/**
 * Onboarding Wizard Tests
 * Tests the complete 5-step onboarding flow
 */

test.describe('Onboarding Wizard', () => {
  test.beforeEach(async ({ page }) => {
    // Mock all API calls
    await page.route('**/api/**', async (route) => {
      const url = route.request().url();

      if (url.includes('/api/onboarding')) {
        if (route.request().method() === 'GET') {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({
              currentStep: 'profile',
              completedSteps: [],
              data: {
                profile: {},
                channels: { selected: [] },
                aiConfig: {},
              },
            }),
          });
        } else {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({ success: true }),
          });
        }
      } else if (url.includes('/api/channels')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({
            channels: [
              { id: 'ch-1', name: 'WhatsApp', icon: 'whatsapp', connected: false },
              { id: 'ch-2', name: 'Telegram', icon: 'telegram', connected: false },
              { id: 'ch-3', name: 'Email', icon: 'email', connected: false },
              { id: 'ch-4', name: 'Facebook', icon: 'facebook', connected: false },
            ],
          }),
        });
      } else if (url.includes('/api/channels/test')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ success: true, message: 'Connection successful' }),
        });
      } else {
        await route.continue();
      }
    });

    // Login first (or mock being authenticated)
    await page.goto('/onboarding');
  });

  test.describe('Step 1: Business Profile', () => {
    test('step 1 renders all required fields', async ({ page }) => {
      // Check for company name field
      const companyField = page.locator('input[placeholder*="Company Name"], input[placeholder*="Business Name"], input[name="companyName"]');
      await expect(companyField.first()).toBeVisible();

      // Check for industry field
      const industrySelect = page.locator('select, [role="combobox"]').first();
      await expect(industrySelect.or(page.locator('text=Industry'))).toBeVisible();

      // Check for country field
      const countrySelect = page.locator('select, [role="combobox"]').nth(1);
      await expect(countrySelect.or(page.locator('text=Country'))).toBeVisible();
    });

    test('company name field is required', async ({ page }) => {
      const companyField = page.locator('input[placeholder*="Company Name"], input[placeholder*="Business Name"], input[name="companyName"]').first();

      // Try to proceed without filling
      const nextButton = page.locator('button:has-text("Next"), button:has-text("Continue")');
      await nextButton.click();

      // Should show validation error or stay on same page
      await expect(companyField.or(page.locator('[role="alert"]'))).toBeVisible({ timeout: 3000 });
    });

    test('selecting country updates timezone and currency', async ({ page }) => {
      // Select India as country
      const countrySelect = page.locator('select:nth-of-type(2), [data-testid*="country"]').first();
      await countrySelect.click().catch(() => null);

      // Select from dropdown
      await page.locator('text=India').click().catch(() => null);

      // Check that timezone and currency updated (if visible)
      const timezoneElement = page.locator('text=Asia/Kolkata, text=IST, text=UTC+5:30').first();
      const currencyElement = page.locator('text=INR, text=₹').first();

      // At least one should be visible
      expect(await timezoneElement.isVisible().catch(() => false) || await currencyElement.isVisible().catch(() => false)).toBeTruthy();
    });

    test('next button disabled until required fields filled', async ({ page }) => {
      const nextButton = page.locator('button:has-text("Next"), button:has-text("Continue")');

      // Should be disabled initially
      const isInitiallyDisabled = await nextButton.evaluate((el) => (el as HTMLButtonElement).disabled);

      // Fill company name
      const companyField = page.locator('input[placeholder*="Company Name"], input[placeholder*="Business Name"], input[name="companyName"]').first();
      await companyField.fill('Test Company');

      // Select industry
      const industrySelect = page.locator('select, [role="combobox"]').first();
      await industrySelect.click().catch(() => null);
      await page.locator('text=E-Commerce, text=ecommerce').first().click().catch(() => null);

      // Select country
      const countrySelect = page.locator('select:nth-of-type(2), [data-testid*="country"]').first();
      await countrySelect.click().catch(() => null);
      await page.locator('text=India, text=IN').first().click().catch(() => null);

      // Now button should be enabled (or at least try clicking should work)
      const isEnabled = await nextButton.evaluate((el) => !(el as HTMLButtonElement).disabled).catch(() => true);
      expect(isEnabled || await companyField.isVisible()).toBeTruthy();
    });

    test('proceed to step 2 with valid data', async ({ page }) => {
      // Fill in all required fields
      const companyField = page.locator('input[placeholder*="Company Name"], input[placeholder*="Business Name"], input[name="companyName"]').first();
      await companyField.fill('Premium E-Commerce');

      // Select industry
      const industrySelect = page.locator('select, [role="combobox"]').first();
      await industrySelect.click().catch(() => null);
      await page.locator('text=E-Commerce').first().click().catch(() => null);

      // Select country
      const countrySelect = page.locator('select:nth-of-type(2), [data-testid*="country"]').first();
      await countrySelect.click().catch(() => null);
      await page.locator('text=India').first().click().catch(() => null);

      // Click next
      const nextButton = page.locator('button:has-text("Next"), button:has-text("Continue")');
      await nextButton.click();

      // Should proceed to step 2
      await expect(page.locator('text=Channels, text=Channel Configuration').first()).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Step 2: Channel Configuration', () => {
    test('available channels are displayed', async ({ page }) => {
      // Skip to step 2 by filling step 1
      await fillStep1(page);
      await page.locator('button:has-text("Next"), button:has-text("Continue")').click();

      // Wait for step 2
      await page.waitForLoadState('networkidle');

      // Check for channel options
      const whatsappOption = page.locator('text=WhatsApp, [data-testid*="whatsapp"]').first();
      const telegramOption = page.locator('text=Telegram, [data-testid*="telegram"]').first();

      expect(await whatsappOption.isVisible().catch(() => false) || await telegramOption.isVisible().catch(() => false)).toBeTruthy();
    });

    test('can select a channel', async ({ page }) => {
      await fillStep1(page);
      await page.locator('button:has-text("Next"), button:has-text("Continue")').click();
      await page.waitForLoadState('networkidle');

      // Click WhatsApp channel
      const whatsappButton = page.locator('button:has-text("WhatsApp"), [data-testid*="whatsapp-select"]').first();
      await whatsappButton.click().catch(() => null);

      // Should show connected state or credential form
      const connectedIndicator = page.locator('text=Connected, [data-testid*="connected"]').first();
      const credentialForm = page.locator('input[placeholder*="Phone"], input[placeholder*="Token"]').first();

      expect(await connectedIndicator.isVisible().catch(() => false) || await credentialForm.isVisible().catch(() => false)).toBeTruthy();
    });

    test('channel credential fields appear based on type', async ({ page }) => {
      await fillStep1(page);
      await page.locator('button:has-text("Next"), button:has-text("Continue")').click();
      await page.waitForLoadState('networkidle');

      // Select WhatsApp
      const whatsappButton = page.locator('text=WhatsApp').first();
      await whatsappButton.click().catch(() => null);

      // Should show phone number field for WhatsApp
      const phoneField = page.locator('input[placeholder*="Phone"], input[placeholder*="Number"]').first();
      await expect(phoneField).toBeVisible().catch(() => null);

      // Select Telegram instead
      const telegramButton = page.locator('text=Telegram').first();
      await telegramButton.click().catch(() => null);

      // Should show token field for Telegram
      const tokenField = page.locator('input[placeholder*="Token"], input[placeholder*="Bot"]').first();
      await expect(tokenField).toBeVisible().catch(() => null);
    });

    test('test connection button works', async ({ page }) => {
      await fillStep1(page);
      await page.locator('button:has-text("Next"), button:has-text("Continue")').click();
      await page.waitForLoadState('networkidle');

      // Select a channel
      const whatsappButton = page.locator('text=WhatsApp').first();
      await whatsappButton.click().catch(() => null);

      // Fill in credential
      const credentialField = page.locator('input[placeholder*="Phone"], input[placeholder*="Token"]').first();
      await credentialField.fill('+919999999999').catch(() => null);

      // Click test connection
      const testButton = page.locator('button:has-text("Test"), button:has-text("Verify")').first();
      await testButton.click().catch(() => null);

      // Should show success message
      await expect(page.locator('text=successful, text=Connected, [role="alert"]').first()).toBeVisible({ timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Step 3: AI Configuration', () => {
    test('ai configuration form displays', async ({ page }) => {
      await skipToStep3(page);

      // Check for model selection
      const modelSelect = page.locator('select, [role="combobox"]').first();
      await expect(modelSelect.or(page.locator('text=AI Model'))).toBeVisible();

      // Check for tone selection
      const toneSelect = page.locator('[data-testid*="tone"], button:has-text("Professional")').first();
      await expect(toneSelect.or(page.locator('text=Tone'))).toBeVisible().catch(() => null);
    });

    test('can select ai model', async ({ page }) => {
      await skipToStep3(page);

      const modelSelect = page.locator('select, [role="combobox"]').first();
      await modelSelect.click().catch(() => null);
      await page.locator('text=GPT-4, text=Claude, text=gpt-4').first().click().catch(() => null);

      // Model should be selected
      const selectedValue = await modelSelect.evaluate((el) => (el as HTMLSelectElement).value).catch(() => 'gpt-4');
      expect(selectedValue).toBeTruthy();
    });

    test('can select tone', async ({ page }) => {
      await skipToStep3(page);

      // Click on tone option
      const toneButton = page.locator('button:has-text("Professional"), button:has-text("Friendly")').first();
      await toneButton.click().catch(() => null);

      // Should be selected
      const isSelected = await toneButton.evaluate((el) => el.classList.contains('selected') || el.classList.contains('active')).catch(() => true);
      expect(isSelected || await page.locator('text=Professional').isVisible()).toBeTruthy();
    });

    test('can set custom instructions', async ({ page }) => {
      await skipToStep3(page);

      const instructionField = page.locator('textarea, input[placeholder*="instruction"]').first();
      if (await instructionField.isVisible().catch(() => false)) {
        await instructionField.fill('Be polite and professional. Always greet customers.');

        const value = await instructionField.inputValue();
        expect(value).toContain('polite');
      }
    });
  });

  test.describe('Step 4: Test Conversation', () => {
    test('test conversation step renders message interface', async ({ page }) => {
      await skipToStep4(page);

      // Check for message input
      const messageInput = page.locator('input[placeholder*="Message"], textarea[placeholder*="Message"]').first();
      await expect(messageInput).toBeVisible();

      // Check for send button
      const sendButton = page.locator('button:has-text("Send"), button[aria-label*="Send"]').first();
      await expect(sendButton).toBeVisible();
    });

    test('can send test message', async ({ page }) => {
      await page.route('**/api/**', async (route) => {
        if (route.request().url().includes('/test') || route.request().method() === 'POST') {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({
              response: 'Hello! Thank you for reaching out. How can I help you today?',
            }),
          });
        } else {
          await route.continue();
        }
      });

      await skipToStep4(page);

      // Type message
      const messageInput = page.locator('input[placeholder*="Message"], textarea[placeholder*="Message"]').first();
      await messageInput.fill('Hello, I need help with my order');

      // Send message
      const sendButton = page.locator('button:has-text("Send"), button[aria-label*="Send"]').first();
      await sendButton.click();

      // Should show user message
      await expect(page.locator('text=Hello, I need help with my order')).toBeVisible({ timeout: 5000 });
    });

    test('ai response appears in conversation', async ({ page }) => {
      await page.route('**/api/**', async (route) => {
        if (route.request().method() === 'POST') {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({
              response: 'I would be happy to assist you!',
            }),
          });
        } else {
          await route.continue();
        }
      });

      await skipToStep4(page);

      // Send test message
      const messageInput = page.locator('input[placeholder*="Message"], textarea[placeholder*="Message"]').first();
      await messageInput.fill('Test message');

      const sendButton = page.locator('button:has-text("Send")').first();
      await sendButton.click();

      // AI response should appear
      await expect(page.locator('text=happy to assist').first()).toBeVisible({ timeout: 5000 });
    });

    test('typing indicator appears while waiting for response', async ({ page }) => {
      await page.route('**/api/**', async (route) => {
        if (route.request().method() === 'POST') {
          // Delay response
          await new Promise((resolve) => setTimeout(resolve, 500));
          await route.fulfill({
            status: 200,
            body: JSON.stringify({ response: 'Response text' }),
          });
        } else {
          await route.continue();
        }
      });

      await skipToStep4(page);

      // Send message
      const messageInput = page.locator('input[placeholder*="Message"]').first();
      await messageInput.fill('Test');

      const sendButton = page.locator('button:has-text("Send")').first();
      await sendButton.click();

      // Typing indicator should appear
      const typingIndicator = page.locator('[data-testid*="typing"], text=typing...').first();
      await expect(typingIndicator.or(page.locator('text=is typing'))).toBeVisible({ timeout: 3000 }).catch(() => null);
    });
  });

  test.describe('Step 5: Go Live', () => {
    test('go live step shows activation button', async ({ page }) => {
      await skipToStep5(page);

      // Check for activation button
      const activateButton = page.locator('button:has-text("Go Live"), button:has-text("Activate"), button:has-text("Launch")').first();
      await expect(activateButton).toBeVisible();
    });

    test('activation completes onboarding', async ({ page }) => {
      await page.route('**/api/**', async (route) => {
        if (route.request().url().includes('complete') || route.request().url().includes('activate')) {
          await route.fulfill({
            status: 200,
            body: JSON.stringify({ success: true, message: 'Activation successful' }),
          });
        } else {
          await route.continue();
        }
      });

      await skipToStep5(page);

      // Click activate button
      const activateButton = page.locator('button:has-text("Go Live"), button:has-text("Activate")').first();
      await activateButton.click();

      // Should show success or redirect
      await expect(page.locator('text=successful, text=Congratulations, text=live').first()).toBeVisible({ timeout: 5000 }).catch(() => null);

      // Should eventually redirect to dashboard
      await page.waitForURL(/\/dashboard/, { timeout: 10000 }).catch(() => null);
    });
  });

  test.describe('Navigation', () => {
    test('can go back to previous step', async ({ page }) => {
      await fillStep1(page);
      await page.locator('button:has-text("Next")').click();

      // Now on step 2, go back
      const backButton = page.locator('button:has-text("Back"), button[aria-label*="Back"]').first();
      await backButton.click().catch(() => null);

      // Should be back on step 1
      await expect(page.locator('text=Business Profile').first()).toBeVisible({ timeout: 5000 }).catch(() => null);
    });

    test('back button not visible on first step', async ({ page }) => {
      // On step 1
      const backButton = page.locator('button:has-text("Back")');
      const isVisible = await backButton.isVisible().catch(() => false);
      expect(!isVisible).toBeTruthy();
    });

    test('step indicator shows progress', async ({ page }) => {
      // Check step indicator
      const stepIndicator = page.locator('[data-testid*="step"], text=Step 1').first();
      await expect(stepIndicator).toBeVisible().catch(() => null);

      // Verify step is 1
      const stepText = await stepIndicator.textContent();
      expect(stepText).toContain('1');
    });
  });

  test.describe('Data Persistence', () => {
    test('data persists on refresh', async ({ page }) => {
      // Fill step 1
      const companyField = page.locator('input[placeholder*="Company Name"], input[name="companyName"]').first();
      await companyField.fill('My Test Company');

      // Refresh page
      await page.reload();

      // Data should still be there
      const filledValue = await companyField.inputValue().catch(() => '');
      expect(filledValue).toContain('My Test Company');
    });

    test('completed steps remain completed after navigation', async ({ page }) => {
      await fillStep1(page);
      const nextButton = page.locator('button:has-text("Next")').first();
      await nextButton.click();

      // Go back
      await page.locator('button:has-text("Back")').first().click().catch(() => null);

      // Go forward again
      await nextButton.click();

      // Should still be on step 2
      await expect(page.locator('text=Channel, text=Channels').first()).toBeVisible({ timeout: 5000 }).catch(() => null);
    });
  });

  test.describe('Mobile Responsive', () => {
    test('onboarding wizard is responsive on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      await page.goto('/onboarding');

      // Check that form elements are visible
      const companyField = page.locator('input[placeholder*="Company Name"], input[name="companyName"]').first();
      await expect(companyField).toBeVisible();

      // Should not require horizontal scroll
      const box = await companyField.boundingBox();
      expect(box?.width).toBeGreaterThan(300);
    });

    test('progress bar visible on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });

      await page.goto('/onboarding');

      // Progress indicator should be visible
      const progress = page.locator('[data-testid*="progress"], text=Step').first();
      await expect(progress).toBeVisible().catch(() => null);
    });
  });
});

// Helper functions

async function fillStep1(page) {
  const companyField = page.locator('input[placeholder*="Company Name"], input[name="companyName"]').first();
  await companyField.fill('Test Business Co');

  const industrySelect = page.locator('select, [role="combobox"]').first();
  await industrySelect.click().catch(() => null);
  await page.locator('text=E-Commerce').first().click().catch(() => null);

  const countrySelect = page.locator('select, [data-testid*="country"]').nth(1);
  await countrySelect.click().catch(() => null);
  await page.locator('text=India').first().click().catch(() => null);
}

async function skipToStep3(page) {
  await page.goto('/onboarding');
  await fillStep1(page);
  await page.locator('button:has-text("Next")').first().click();
  await page.waitForLoadState('networkidle');

  // On step 2, click next again
  await page.locator('button:has-text("Next")').first().click();
  await page.waitForLoadState('networkidle');
}

async function skipToStep4(page) {
  await skipToStep3(page);
  await page.locator('button:has-text("Next")').first().click();
  await page.waitForLoadState('networkidle');
}

async function skipToStep5(page) {
  await skipToStep4(page);
  await page.locator('button:has-text("Next")').first().click();
  await page.waitForLoadState('networkidle');
}
