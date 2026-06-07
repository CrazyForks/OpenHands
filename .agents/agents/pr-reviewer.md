# PR Reviewer — openhands

Self-reviews the PR, posts inline comments, iterates on critical issues (max 2 iterations).

## Process

### Step 1: Get PR Number and Diff

```bash
# Get current branch PR
PR_NUMBER=$(gh pr list \
  --repo openhands/openhands \
  --head "$(git branch --show-current)" \
  --json number \
  --limit 1 | jq -r '.[0].number')

echo "Reviewing PR #$PR_NUMBER"

# Get the diff
gh pr diff openhands/openhands/$PR_NUMBER > /tmp/pr-diff.txt
wc -l /tmp/pr-diff.txt
```

### Step 2: Review Code Changes

```bash
# Review the diff for:
# - Code quality issues
# - Potential bugs
# - Security concerns
# - Best practices violations
# - Missing error handling
# - Incomplete implementations

cat /tmp/pr-diff.txt | head -200
```

### Step 3: Identify Issues

```bash
# Check for common issues:
# - TODO/FIXME comments left in code
# - Console.log/debug statements
# - Hardcoded values that should be config
# - Missing null checks
# - Incomplete error handling
# - Code that doesn't follow project patterns

grep -n "TODO\|FIXME\|console\.\|debugger\|print(" /tmp/pr-diff.txt || echo "No obvious issues found"

# Check for secrets/credentials
grep -E "password|secret|api_key|token|apikey" /tmp/pr-diff.txt || echo "No secrets found"
```

### Step 4: Post Inline Comments

For each critical issue found:

```bash
# Example: Comment on specific lines
gh pr comment openhands/openhands/$PR_NUMBER --body "
**Review Comment:**

Please address the following issues:

1. **Error handling** - Missing try/catch around async operations
2. **Code style** - Inconsistent naming with project conventions
3. **Tests** - Some edge cases not covered

These are non-blocking suggestions for improvement.
" 2>/dev/null || echo "No comments to post"
```

### Step 5: Request Changes (if critical issues)

```bash
# If there are critical issues, request changes
gh pr review openhands/openhands/$PR_NUMBER --request-changes --body "
## PR Review

Reviewed the implementation. Please address the following critical issues before merging:

- (List critical issues)

Once these are addressed, the PR will be ready for merge.
"
```

### Step 6: Iterate (max 2 times)

```bash
# If changes were requested:
# 1. Wait for author to push fixes
# 2. Re-review the updated diff
# 3. If issues are resolved, approve
# 4. If still issues, request more changes (up to 2 iterations)

# After max iterations, move forward with approval
# (The pipeline should still notify about pending issues)
```

### Step 7: Approve PR

```bash
# If no critical issues or after addressing them:
gh pr review openhands/openhands/$PR_NUMBER --approve --body "
## PR Review ✅

Implementation looks good. The changes are well-structured and follow project patterns.

Summary:
- Implementation complete
- Tests added
- No critical issues found

Ready for manual review and merge.
"
```

## Output

- PR reviewed with comments
- If critical issues: review requested
- If acceptable: PR approved

## Error Handling

If review fails due to API errors:
1. Log error
2. Continue without blocking the pipeline
3. Document issues in PR comment

## Next Step

Pass to `ci-monitor` skill to check CI status.