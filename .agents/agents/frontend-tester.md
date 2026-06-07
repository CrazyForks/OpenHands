# Frontend Tester — openhands

Writes missing tests for new frontend code.

## Test Framework Detected

- **Framework:** vitest
- **Test Command:** npm run test:coverage
- **Test Directory:** frontend/tests
- **Build Command:** npm run build

## Process

### Step 1: Identify Files Needing Tests

```bash
# Find recently modified source files
git diff --name-only HEAD~1..HEAD

# Look for untested functions/classes in frontend
find frontend/src -name "*.tsx" -o -name "*.ts" 2>/dev/null | head -20
```

### Step 2: Check Existing Test Patterns

```bash
# List test directory structure
ls -la frontend/tests

# Read existing test files to understand patterns
find frontend/tests -name "*.test.tsx" -o -name "*.test.ts" 2>/dev/null | head -5
cat frontend/tests/*.test.tsx 2>/dev/null | head -50
```

### Step 3: Write Missing Tests

Following the project's existing test patterns:

```bash
# Identify untested logic from implementation
# Write tests for:
# - React components
# - Hooks
# - Utilities
# - Edge cases

cat > frontend/tests/test_$(date +%Y%m%d).test.tsx << 'EOF'
import { describe, it, expect } from 'vitest';

describe('Implementation Tests', () => {
  it('should render correctly', () => {
    // Test implementation
  });
  
  it('should handle user interactions', () => {
    // Test interaction
  });
  
  it('should handle edge cases', () => {
    // Test edge cases
  });
});
EOF
```

### Step 4: Run All Test Suites

```bash
npm run test:coverage
```

### Step 5: Fix Any Test Failures

```bash
# If tests fail, analyze and fix
# Ensure tests pass before committing
npm run test:coverage
```

### Step 6: Commit Test Files

```bash
git add frontend/tests/
git commit -m "test: add frontend tests for implementation

- Added test cases for new frontend functionality
- Covered edge cases and error handling
- Ensured compatibility with existing tests
"
```

## Output

- New test files created in `frontend/tests`
- All tests passing
- Test files committed

## Next Step

Pass to `build-check` skill for frontend build verification.