# Priya Global Dashboard - E2E Test Suite

Comprehensive Playwright E2E test suite for the Priya Global Next.js dashboard covering authentication, onboarding, dashboard, conversations, and channels management.

## Overview

This test suite provides end-to-end testing for all major user journeys in the Priya Global dashboard:

- **Authentication** (Login, Register, Forgot Password, Protected Routes)
- **Onboarding Wizard** (5-step setup: Profile, Channels, AI Config, Test, Go Live)
- **Dashboard** (Stats, Charts, Navigation, Dark Mode)
- **Conversations** (List, Search, Filter, Chat Interface, Handoff to Agent)
- **Channels** (Connect, Manage, Analytics, Disconnect)

## Test Statistics

- **Total Test Files**: 5 spec files + 2 fixture files
- **Total Test Cases**: 100+
- **Lines of Code**: 2500+
- **Coverage**: Auth, Onboarding, Dashboard, Conversations, Channels

## Project Structure

```
e2e/
├── fixtures/
│   ├── auth.fixture.ts          # Authentication utilities & test users
│   └── api-mocks.fixture.ts     # API mocking for all backend calls
├── auth.spec.ts                  # Authentication tests (~200 lines)
├── onboarding.spec.ts            # Onboarding wizard tests (~250 lines)
├── dashboard.spec.ts             # Dashboard tests (~200 lines)
├── conversations.spec.ts         # Conversations tests (~200 lines)
├── channels.spec.ts              # Channels tests (~150 lines)
└── README.md                      # This file
```

## Prerequisites

1. Node.js 18+ installed
2. npm or yarn package manager
3. Dashboard app running on http://localhost:3000

## Installation

1. Install Playwright and dependencies:

```bash
npm install
```

This will install:
- `@playwright/test`: ^1.42.0

2. Install Playwright browsers (one-time setup):

```bash
npx playwright install
```

## Configuration

The test suite is configured in `playwright.config.ts` with:

- **Base URL**: http://localhost:3000
- **Browsers**: Chromium, Firefox, WebKit
- **Mobile Viewports**: iPhone 12, Pixel 5, iPad Pro
- **Timeout**: 30 seconds per test
- **Retries**: 2 retries on CI, 0 locally
- **Reporters**: HTML + JUnit for CI integration
- **Screenshots**: On test failure
- **Videos**: On first retry
- **Traces**: On first retry

## Running Tests

### All Tests
```bash
npm run test:e2e
```

### UI Mode (Interactive)
```bash
npm run test:e2e:ui
```
Opens Playwright Test UI for debugging and running tests interactively.

### Headed Mode (See Browser)
```bash
npm run test:e2e:headed
```

### Specific Test File
```bash
npx playwright test e2e/auth.spec.ts
```

### Specific Test Suite
```bash
npx playwright test -g "Login Page"
```

### Specific Browser
```bash
npx playwright test --project=chromium
```
Available projects: `chromium`, `firefox`, `webkit`, `Mobile Safari`, `Mobile Chrome`, `iPad`

### With Debug Mode
```bash
npx playwright test --debug
```

## Test Organization

### Authentication Tests (`auth.spec.ts`)
Covers all auth flows:

- **Login Page**: Rendering, validation, navigation
- **Login Flow**: Valid credentials, invalid credentials, empty fields
- **Remember Me**: Checkbox functionality
- **Registration**: Form validation, password requirements
- **Password Validation**: Min 8 chars, uppercase, number, special char
- **Forgot Password**: Email submission flow
- **Protected Routes**: Redirect unauthenticated users to login
- **Logout**: Session cleanup and redirect
- **Mobile Responsive**: Login/register on mobile viewports

Test Users:
```typescript
valid: {
  email: 'test@priya-global.com',
  password: 'SecurePass123!',
  firstName: 'Test',
  lastName: 'User',
}
```

### Onboarding Tests (`onboarding.spec.ts`)
Complete 5-step wizard validation:

**Step 1: Business Profile**
- Company name (required)
- Industry selection
- Country selection
- Timezone & currency auto-population
- Form validation

**Step 2: Channel Configuration**
- Channel availability display
- Channel selection
- Credential fields per channel type
- Test connection functionality

**Step 3: AI Configuration**
- Model selection
- Tone presets
- Language preferences
- Custom instructions

**Step 4: Test Conversation**
- Message interface
- Send test message
- AI response display
- Typing indicators
- Response quality

**Step 5: Go Live**
- Activation button
- Success messaging
- Dashboard redirect

**Additional Tests**
- Navigation (back/forward)
- Progress persistence on refresh
- Mobile responsive wizard
- Multi-step flow completion

### Dashboard Tests (`dashboard.spec.ts`)
Main dashboard feature validation:

- **Stats Cards**: Display, trends, values, loading states
- **Charts**: Pie chart (channels), line chart (trends), interactivity
- **Getting Started Card**: For new vs. completed tenants
- **Auto-Refresh**: 30-second interval
- **Sidebar Navigation**: Links and routing
- **Dark Mode**: Toggle and persistence
- **User Avatar**: Profile menu and info
- **Breadcrumb Navigation**: Navigation and links
- **Mobile Responsive**: Layout and sidebar toggle
- **Error Handling**: API failure states

### Conversations Tests (`conversations.spec.ts`)
Complete conversation management:

**Conversation List**
- Load and display
- Customer names and avatars
- Last message preview
- Timestamps
- Unread indicators
- Channel icons

**Search & Filter**
- Search by customer name or message
- Filter by channel
- Filter by status
- Real-time filtering
- Empty state

**Chat Interface**
- Two-panel layout (desktop)
- Single panel layout (mobile)
- Message display
- Sender identification (customer vs AI)
- Message input and sending
- Typing indicators
- Close/back navigation

**Handoff to Agent**
- Button visibility
- Transfer dialog
- Confirmation flow

**Mobile Responsive**
- List scrollability
- Back button navigation

### Channels Tests (`channels.spec.ts`)
Channel management and analytics:

**Channel Grid**
- Display all channels
- Channel names and icons
- Status indicators (connected/disconnected)
- Message counts
- Click to details

**Connect Channel**
- Modal opening
- Credential fields per channel type
- Test connection
- Channel confirmation
- Success messaging

**Channel Disconnect**
- Disconnect button visibility
- Confirmation dialog
- Status update

**Channel Analytics**
- Message count
- Sentiment breakdown
- Charts and graphs
- Top messages

**Mobile Responsive**
- Grid responsive layout
- Details drawer
- Back navigation

## API Mocking

The test suite uses **Playwright's `page.route()`** to mock all backend API calls. This allows tests to run without a real backend:

### Mock Endpoints

1. **Dashboard Stats** (`/api/dashboard/stats`)
   - Returns: Stats cards data, chart data

2. **Conversations** (`/api/conversations`)
   - Returns: List of conversations with filtering support
   - Supports: search, channel, status filters

3. **Channels** (`/api/channels`)
   - GET: Returns list of available channels
   - POST: Returns success for channel connection
   - Test: Verifies channel connection

4. **User Profile** (`/api/user/profile`)
   - Returns: User info, tenant config, onboarding status

5. **Onboarding** (`/api/onboarding`)
   - GET: Returns current onboarding state
   - PUT/POST: Updates onboarding progress

6. **Auth** (`/api/auth/*`)
   - Login: Validates credentials
   - Register: Creates new account
   - Logout: Clears session

### Mock Data

Mock data includes:
- Indian + international markets support
- Realistic timestamps and data
- Multiple channels (WhatsApp, Telegram, Email, etc.)
- Customer profiles with avatars
- Message conversations
- Analytics data

## Test Data

### Test Users
```typescript
// Valid user
email: test@priya-global.com
password: SecurePass123!

// Invalid user
email: invalid@test.com
password: wrongpassword
```

### Countries Supported
US, IN (India), GB, CA, AU, DE, FR, JP, BR, AE, SG, MX, KR, ZA, NG, SA, ID, PH, IT, ES, NL, SE, CH, NZ

### Channels
WhatsApp, Telegram, Email, Facebook, Instagram, SMS

### Industries
E-Commerce, Healthcare, Real Estate, Education, Restaurant, Finance, Automotive, Travel, SaaS, Professional Services

## CI/CD Integration

### GitHub Actions

Add to `.github/workflows/e2e.yml`:

```yaml
name: E2E Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'

      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npm run test:e2e

      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 30
```

### Test Reports

After running tests, view reports:

```bash
# HTML Report
npx playwright show-report

# JUnit Report
cat junit-results.xml
```

## Debugging

### Debug Mode
```bash
npx playwright test --debug
```
Opens Playwright Inspector for step-by-step debugging.

### Trace Viewer
```bash
npx playwright show-trace trace.zip
```
View recorded traces of test execution.

### Screenshots & Videos
Failed tests automatically capture:
- Screenshots on failure (saved in test-results/)
- Videos on first retry (saved in test-results/)
- Traces for debugging (saved in test-results/)

### View Failed Test
```bash
npx playwright test --headed e2e/auth.spec.ts
```

### Add Debug Statements
```typescript
await page.pause(); // Pause execution for debugging
```

## Best Practices

### Writing Tests

1. **Use descriptive test names**
   ```typescript
   test('login with valid credentials redirects to dashboard', async () => {
   ```

2. **Group related tests**
   ```typescript
   test.describe('Login Page', () => {
     // Related tests
   });
   ```

3. **Use before/after hooks**
   ```typescript
   test.beforeEach(async ({ page }) => {
     // Setup
   });
   ```

4. **Mock external APIs**
   ```typescript
   await page.route('**/api/**', (route) => {
     // Mock response
   });
   ```

5. **Wait for elements properly**
   ```typescript
   await expect(element).toBeVisible({ timeout: 5000 });
   ```

### Selectors

Prefer in order:
1. Test IDs: `[data-testid="button"]`
2. Accessible role: `button:has-text("Login")`
3. Placeholder: `input[placeholder="Email"]`
4. Type: `input[type="email"]`
5. Last resort: CSS selectors

### Mobile Testing

Always test mobile viewports:
```typescript
test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 }); // iPhone
});
```

## Troubleshooting

### Port Already in Use
```bash
# Find process using port 3000
lsof -i :3000
# Kill process
kill -9 <PID>
```

### Playwright Timeouts
- Increase timeout: `timeout: 60 * 1000` in config
- Add explicit waits: `await page.waitForLoadState('networkidle')`

### API Mocks Not Working
- Ensure route patterns match: `**/api/**`
- Check network tab in headed mode
- Verify mock response format

### Test Flakiness
- Add explicit waits for animations
- Use `waitForLoadState('networkidle')`
- Increase element visibility timeout
- Check for race conditions

### Screenshot Differences (Visual Tests)
- Update baseline: `--update-snapshots` (not yet implemented)
- Check browser versions match
- Verify viewport sizes

## Performance

Current test suite:
- **Total execution time**: ~5-10 minutes (all tests, all browsers)
- **Single test file**: ~1-2 minutes
- **CI execution**: ~15 minutes with retries

Tips for faster tests:
- Run specific test file: `npx playwright test e2e/auth.spec.ts`
- Use single browser: `--project=chromium`
- Disable video: `video: 'off'` in config
- Run in parallel: `fullyParallel: true` (default)

## Maintenance

### Updating Tests

When UI changes:
1. Update selectors in test
2. Update mock data if needed
3. Run tests to verify
4. Commit changes

### Adding New Tests

1. Create new `.spec.ts` file in `e2e/`
2. Import test utilities
3. Add `test.beforeEach` for setup
4. Write test cases
5. Run tests

Example:
```typescript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    // Setup
  });

  test('should do something', async ({ page }) => {
    // Test logic
  });
});
```

## Resources

- [Playwright Documentation](https://playwright.dev)
- [Playwright Test API](https://playwright.dev/docs/api/class-test)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Debugging Guide](https://playwright.dev/docs/debug)
- [CI/CD Integration](https://playwright.dev/docs/ci)

## Contributing

When contributing tests:
1. Follow naming conventions
2. Add proper grouping with `test.describe`
3. Include both positive and negative test cases
4. Test mobile responsive layouts
5. Document any non-obvious test logic
6. Keep tests independent (no dependencies between tests)

## Support

For issues or questions:
1. Check Playwright docs
2. Review existing test patterns
3. Run with `--debug` flag
4. Check network tab in headed mode
5. Review screenshots/videos in test-results/

---

**Last Updated**: March 2026
**Playwright Version**: 1.42.0+
**Node Version**: 18+
