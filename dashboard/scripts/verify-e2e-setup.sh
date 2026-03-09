#!/bin/bash

# E2E Test Suite Setup Verification Script
# This script verifies that all E2E test files are properly set up

set -e

echo "================================"
echo "E2E Test Suite Verification"
echo "================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check function
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1 (MISSING)"
        return 1
    fi
}

check_dir() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✓${NC} $1/"
        return 0
    else
        echo -e "${RED}✗${NC} $1/ (MISSING)"
        return 1
    fi
}

# Count files
count_files() {
    find "$1" -type f -name "*.ts" 2>/dev/null | wc -l
}

# Start verification
ERRORS=0

echo "Checking Configuration Files..."
check_file "playwright.config.ts" || ((ERRORS++))
check_file "package.json" || ((ERRORS++))
check_file ".env.test" || ((ERRORS++))
echo ""

echo "Checking Test Directories..."
check_dir "e2e" || ((ERRORS++))
check_dir "e2e/fixtures" || ((ERRORS++))
echo ""

echo "Checking Test Spec Files..."
check_file "e2e/auth.spec.ts" || ((ERRORS++))
check_file "e2e/onboarding.spec.ts" || ((ERRORS++))
check_file "e2e/dashboard.spec.ts" || ((ERRORS++))
check_file "e2e/conversations.spec.ts" || ((ERRORS++))
check_file "e2e/channels.spec.ts" || ((ERRORS++))
echo ""

echo "Checking Fixture Files..."
check_file "e2e/fixtures/auth.fixture.ts" || ((ERRORS++))
check_file "e2e/fixtures/api-mocks.fixture.ts" || ((ERRORS++))
echo ""

echo "Checking Documentation Files..."
check_file "e2e/README.md" || ((ERRORS++))
check_file "E2E_QUICK_START.md" || ((ERRORS++))
check_file "E2E_TEST_SUITE_SUMMARY.md" || ((ERRORS++))
echo ""

# Check package.json for test scripts
echo "Checking package.json Scripts..."
if grep -q '"test:e2e"' package.json; then
    echo -e "${GREEN}✓${NC} test:e2e script configured"
else
    echo -e "${RED}✗${NC} test:e2e script missing"
    ((ERRORS++))
fi

if grep -q '"test:e2e:ui"' package.json; then
    echo -e "${GREEN}✓${NC} test:e2e:ui script configured"
else
    echo -e "${RED}✗${NC} test:e2e:ui script missing"
    ((ERRORS++))
fi

if grep -q '"test:e2e:headed"' package.json; then
    echo -e "${GREEN}✓${NC} test:e2e:headed script configured"
else
    echo -e "${RED}✗${NC} test:e2e:headed script missing"
    ((ERRORS++))
fi

if grep -q '@playwright/test' package.json; then
    echo -e "${GREEN}✓${NC} @playwright/test dependency added"
else
    echo -e "${RED}✗${NC} @playwright/test dependency missing"
    ((ERRORS++))
fi
echo ""

# Check playwright.config.ts configuration
echo "Checking playwright.config.ts Configuration..."
if grep -q 'testDir: .*e2e' playwright.config.ts; then
    echo -e "${GREEN}✓${NC} Test directory configured"
else
    echo -e "${RED}✗${NC} Test directory not configured"
    ((ERRORS++))
fi

if grep -q 'baseURL:.*localhost:3000' playwright.config.ts; then
    echo -e "${GREEN}✓${NC} Base URL configured"
else
    echo -e "${RED}✗${NC} Base URL not configured"
    ((ERRORS++))
fi

if grep -q "devices\['Desktop Chrome'\]" playwright.config.ts; then
    echo -e "${GREEN}✓${NC} Chromium browser configured"
else
    echo -e "${RED}✗${NC} Chromium browser not configured"
    ((ERRORS++))
fi

if grep -q "devices\['Desktop Firefox'\]" playwright.config.ts; then
    echo -e "${GREEN}✓${NC} Firefox browser configured"
else
    echo -e "${RED}✗${NC} Firefox browser not configured"
    ((ERRORS++))
fi

if grep -q "devices\['Desktop Safari'\]" playwright.config.ts; then
    echo -e "${GREEN}✓${NC} WebKit browser configured"
else
    echo -e "${RED}✗${NC} WebKit browser not configured"
    ((ERRORS++))
fi

if grep -q "devices\['iPhone 12'\]" playwright.config.ts; then
    echo -e "${GREEN}✓${NC} Mobile Safari configured"
else
    echo -e "${RED}✗${NC} Mobile Safari not configured"
    ((ERRORS++))
fi
echo ""

# Statistics
echo "Test Suite Statistics..."
SPEC_COUNT=$(find e2e -name "*.spec.ts" -type f 2>/dev/null | wc -l)
FIXTURE_COUNT=$(find e2e/fixtures -name "*.ts" -type f 2>/dev/null | wc -l)
echo "  Spec files: $SPEC_COUNT"
echo "  Fixture files: $FIXTURE_COUNT"
echo ""

# Lines of code
TOTAL_LINES=$(find e2e -name "*.ts" -type f 2>/dev/null -exec wc -l {} + | tail -1 | awk '{print $1}')
echo "  Total lines of code: $TOTAL_LINES"
echo ""

# Summary
echo "================================"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "E2E test suite is properly configured."
    echo ""
    echo "Next steps:"
    echo "  1. npm install (if not already done)"
    echo "  2. npx playwright install"
    echo "  3. npm run dev (start dashboard)"
    echo "  4. npm run test:e2e (in another terminal)"
    echo ""
    echo "For more info, see E2E_QUICK_START.md"
    exit 0
else
    echo -e "${RED}✗ $ERRORS check(s) failed${NC}"
    echo ""
    echo "Please ensure all required files are in place."
    echo "See E2E_QUICK_START.md for setup instructions."
    exit 1
fi
