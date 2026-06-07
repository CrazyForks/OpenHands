# CI Monitor — openhands

Polls PR checks, surfaces failure logs, retries on failure (max 3 retries).

## CI System Detected

- **Type:** github-actions (GitHub Actions, CircleCI, Jenkins)
- **Config:** .github/workflows/

## Process

### Step 1: Get PR Number

```bash
PR_NUMBER=$(cat /tmp/pr-number.txt 2>/dev/null || \
  gh pr list \
    --repo openhands/openhands \
    --head "$(git branch --show-current)" \
    --json number \
    --limit 1 | jq -r '.[0].number')

echo "Monitoring CI for PR #$PR_NUMBER"
```

### Step 2: Poll CI Status

```bash
# Check CI status using gh cli
gh pr checks $PR_NUMBER --repo openhands/openhands --watch --interval 30 2>/dev/null || \
gh run list --repo openhands/openhands --limit 5
```

### Step 3: Wait for CI Completion

```bash
# Poll until all checks complete or timeout
MAX_WAIT=600  # 10 minutes
START_TIME=$(date +%s)
RETRIES=0
MAX_RETRIES=3

while [ $RETRIES -lt $MAX_RETRIES ]; do
  # Check current status
  STATUS=$(gh pr view $PR_NUMBER --repo openhands/openhands --json statusCheckRollup --jq '.[0].statusCheckRollup[] | select(.state != "SUCCESS") | .state' 2>/dev/null | head -1)
  
  if [ -z "$STATUS" ]; then
    echo "All checks passed!"
    break
  fi
  
  CURRENT_TIME=$(date +%s)
  ELAPSED=$((CURRENT_TIME - START_TIME))
  
  if [ $ELAPSED -gt $MAX_WAIT ]; then
    echo "Timeout reached after ${ELAPSED}s"
    break
  fi
  
  echo "Waiting for checks... (${ELAPSED}s elapsed)"
  sleep 30
done
```

### Step 4: Handle Failures

```bash
# If CI failed, fetch logs and attempt fix
FAILURES=$(gh pr view $PR_NUMBER --repo openhands/openhands --json statusCheckRollup --jq '.[0].statusCheckRollup[] | select(.state == "FAILURE") | .name' 2>/dev/null)

if [ -n "$FAILURES" ]; then
  echo "Failed checks: $FAILURES"
  
  # Fetch logs for failed checks
  gh run list --repo openhands/openhands --limit 5 --json name,status,conclusion | jq .
  
  # Attempt to fix common issues
  # 1. Re-run failed jobs
  FAILED_RUN_ID=$(gh run list --repo openhands/openhands --limit 5 --json id,conclusion --jq '.[] | select(.conclusion == "failure") | .id' | head -1)
  
  if [ -n "$FAILED_RUN_ID" ]; then
    echo "Re-running failed job: $FAILED_RUN_ID"
    gh run rerun $FAILED_RUN_ID --repo openhands/openhands
    
    # Increment retry counter
    RETRIES=$((RETRIES + 1))
    
    if [ $RETRIES -lt $MAX_RETRIES ]; then
      echo "Retry $RETRIES/$MAX_RETRIES - waiting for re-run..."
      sleep 60
      continue
    fi
  fi
  
  echo "Max retries reached. CI still failing."
fi
```

### Step 5: Report Final Status

```bash
# Get final status
FINAL_STATUS=$(gh pr view $PR_NUMBER --repo openhands/openhands --json mergeable --jq '.mergeable')

if [ "$FINAL_STATUS" == "true" ]; then
  echo "✅ CI passed - PR is mergeable"
else
  echo "❌ CI failed - manual intervention required"
fi
```

## GitHub Actions Specific

```bash
# For GitHub Actions, you can also use:
gh run watch  # Watch current run
gh run list --limit 5  # List recent runs

# Get logs for specific run
gh run view <run-id> --repo openhands/openhands --log | head -100
```

## Error Handling

If polling fails:
1. Log error to `/tmp/ci-monitor-error.log`
2. Continue to notification step with "unknown" status
3. Manual review will be needed

## Next Step

After CI monitoring, pass to `mark-pr-ready` skill (if CI passed) and then `whatsapp-notifier`.