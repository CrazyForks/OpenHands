# Playwright Smoke — openhands

Installs Playwright, runs smoke tests, commits screenshots, posts results to PR.

## Process

### Step 1: Install Playwright

```bash
# Install Playwright
npm install -D @playwright/test

# Install Chromium browser
npx playwright install chromium
```

### Step 2: Configure Test Run

```bash
# Check for playwright.config
cat playwright.config.js 2>/dev/null || cat playwright.config.ts 2>/dev/null || echo "Using default config"

# Create test directory if needed
mkdir -p tests/e2e
```

### Step 3: Run Smoke Tests

```bash
# Run smoke tests with screenshot on failure
npx playwright test tests/e2e \
  --reporter=list \
  --trace=on \
  --screenshot=on \
  --headed=false
```

### Step 4: Commit Screenshots

```bash
# Create results directory
mkdir -p .smoke-results

# Copy test results
cp -r playwright-report/* .smoke-results/ 2>/dev/null || true
cp -r test-results/* .smoke-results/ 2>/dev/null || true

# Find and copy failure screenshots
find . -name "*.png" -path "*failure*" -exec cp {} .smoke-results/ \; 2>/dev/null || true

# Commit
git add .smoke-results/
git commit -m "test: add smoke test screenshots

- Playwright smoke tests completed
- Screenshots saved for review
" 2>/dev/null || echo "Nothing new to commit"
```

### Step 5: Post Results to PR

```bash
PR_NUMBER=$(cat /tmp/pr-number.txt 2>/dev/null || echo "")

gh pr comment openhands/openhands/$PR_NUMBER --body "
## Playwright Smoke Test Results

Tests completed. Screenshots and reports available in \`.smoke-results/\` directory.

View detailed report: [Playwright Report](./.smoke-results)
" 2>/dev/null || echo "Could not post comment"
```

## Next Step

Continue to `ci-monitor`.