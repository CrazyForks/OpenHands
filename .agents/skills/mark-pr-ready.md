# Mark PR Ready — openhands

Removes draft status from PR to trigger CI smoke job.

## Process

### Step 1: Get PR Number

```bash
PR_NUMBER=$(cat /tmp/pr-number.txt 2>/dev/null || echo "")

if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(gh pr list \
    --repo openhands/openhands \
    --head "$(git branch --show-current)" \
    --json number \
    --limit 1 | jq -r '.[0].number')
fi

echo "PR to mark ready: #$PR_NUMBER"
```

### Step 2: Remove Draft Status

```bash
# Mark PR as ready for review (removes draft status)
gh pr ready openhands/openhands/$PR_NUMBER

echo "✅ PR #$PR_NUMBER is now ready for review"
```

### Step 3: Verify

```bash
# Verify PR is no longer draft
IS_DRAFT=$(gh pr view $PR_NUMBER --repo openhands/openhands --json isDraft --jq '.isDraft')

if [ "$IS_DRAFT" == "false" ]; then
  echo "✅ PR is no longer a draft"
else
  echo "⚠️ PR may still be draft - check manually"
fi
```

## Why This Step?

Removing draft status triggers:
1. CI smoke job to run
2. Required reviewers to be notified
3. PR to appear in review queues

## Next Step

After marking PR ready, invoke `whatsapp-notifier` to send notification.