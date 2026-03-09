# E2E Testing Quick Start Guide

## 5-Minute Setup

### 1. Install Dependencies
```bash
cd dashboard
npm install
npx playwright install
```

### 2. Start Dashboard
```bash
# In terminal 1
npm run dev
# Dashboard runs on http://localhost:3000
```

### 3. Run Tests
```bash
# In terminal 2
npm run test:e2e
```

## Common Commands

```bash
# Run all tests
npm run test:e2e

# Run with interactive UI
npm run test:e2e:ui

# Run tests with visible browser
npm run test:e2e:headed

# Run specific test file
npx playwright test e2e/auth.spec.ts

# Run specific test
npx playwright test -g "login with valid credentials"

# Run specific browser
npx playwright test --project=chromium

# Debug mode
npx playwright test --debug

# View test report
npx playwright show-report
```

## Test Files Overview

| File | Tests | Focus |
|------|-------|-------|
| `auth.spec.ts` | 12 | Login, Register, Password Reset, Protected Routes |
| `onboarding.spec.ts` | 20 | 5-Step Wizard (Profile, Channels, AI, Test, Go Live) |
| `dashboard.spec.ts` | 15 | Stats, Charts, Navigation, Dark Mode |
| `conversations.spec.ts` | 18 | List, Search, Chat, Handoff |
| `channels.spec.ts` | 16 | Connect, Manage, Analytics |

## What's Mocked

All backend API calls are mocked, so tests run without a real backend:

- `/api/auth/*` - Authentication (login, register)
- `/api/dashboard/*` - Dashboard stats and charts
- `/api/conversations/*` - Conversation list and details
- `/api/channels/*` - Channel management
- `/api/onboarding/*` - Onboarding progress
- `/api/user/*` - User profile

## Test Credentials

```
Email: test@priya-global.com
Password: SecurePass123!
```

## Viewing Results

### After Tests Complete:
```bash
# Open HTML report
npx playwright show-report

# View specific failure
npx playwright show-report playwright-report/
```

### Artifacts Saved:
- Screenshots (failures only)
- Videos (on retry)
- Traces (for debugging)
- HTML report

## Troubleshooting

### Tests Won't Run
```bash
# Ensure Node 18+
node --version

# Ensure dashboard is running on port 3000
curl http://localhost:3000

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
npx playwright install
```

### Playwright Won't Start
```bash
# Install system dependencies (Linux)
npx playwright install-deps

# Or use Docker
docker run --rm -v $(pwd):/tests mcr.microsoft.com/playwright:v1.42.0 npx playwright test
```

### Port 3000 In Use
```bash
# Kill process
lsof -i :3000 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

### Tests Timeout
- Dashboard takes longer to load: increase timeout in `playwright.config.ts`
- Network is slow: tests may need longer waits
- Mock data: ensure API mocks are working in headed mode

## CI/CD Setup

### GitHub Actions
Add this to `.github/workflows/e2e.yml`:

```yaml
name: E2E Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: npm ci && npx playwright install
      - run: npm run test:e2e
      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: playwright-report
          path: playwright-report/
```

### GitLab CI
Add to `.gitlab-ci.yml`:

```yaml
e2e_tests:
  image: mcr.microsoft.com/playwright:v1.42.0
  script:
    - npm ci
    - npm run test:e2e
  artifacts:
    when: always
    paths:
      - playwright-report/
```

## Performance Notes

- Full suite: 5-10 minutes
- Single file: 1-2 minutes
- Parallel execution: Enabled by default
- Mobile tests: Included in full suite

## Mobile Testing

Tests run on multiple devices:
- **iPhone 12** (375x812)
- **Pixel 5** (393x851)
- **iPad Pro** (1024x1366)

Each test validates responsive behavior on all viewports.

## Next Steps

1. Read full documentation: `/e2e/README.md`
2. Review test examples: `/e2e/auth.spec.ts`
3. Add custom tests as needed
4. Integrate with CI/CD pipeline
5. Set up test reports

## Pro Tips

```bash
# Watch mode (re-run on file changes)
npx playwright test --watch

# Record new test
npx playwright codegen http://localhost:3000

# Slow down execution (helpful for debugging)
npx playwright test --headed --slow-mo=1000

# Run tests in order (useful for dependent tests)
fullyParallel: false

# Capture video of all tests
video: 'on'

# Generate test report
npx playwright test --reporter=html
```

## Test Examples

See `/e2e/*.spec.ts` files for complete examples of:
- Form validation
- Navigation flows
- API mocking
- Mobile testing
- Error scenarios
- Accessibility testing

---

**Questions?** Check the full documentation in `/e2e/README.md`
