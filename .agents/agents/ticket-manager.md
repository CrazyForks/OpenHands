# Ticket Manager — openhands

Pushes branch and creates PR linked to the issue.

## Process

### Step 1: Get Current Branch and Issue Number

```bash
BRANCH=$(git branch --show-current)
echo "Current branch: $BRANCH"

ISSUE_NUMBER=$(gh issue list \
  --repo openhands/openhands \
  --label ready-to-implement \
  --state open \
  --json number \
  --limit 1 | jq -r '.[0].number')

ISSUE_TITLE=$(gh issue view $ISSUE_NUMBER --repo openhands/openhands --json title --jq '.title')

echo "Will link PR to issue #$ISSUE_NUMBER"
```

### Step 2: Push Branch

```bash
git push -u origin $BRANCH
```

### Step 3: Create PR

```bash
# Create PR with reference to the issue
gh pr create \
  --repo openhands/openhands \
  --title "feat: $ISSUE_TITLE" \
  --body "## Summary

Implemented changes for issue #$ISSUE_NUMBER.

## Changes

- (List main changes made)
- (Add bullet points for key features)

## Testing

- All tests passing
- (Add any additional testing notes)

Closes #$ISSUE_NUMBER" \
  --base main \
  --draft
```

### Step 4: Record PR Info

```bash
# Get PR number and URL
PR_URL=$(gh pr view --repo openhands/openhands --json url --jq '.url')
PR_NUMBER=$(gh pr view --repo openhands/openhands --json number --jq '.number')

echo "PR created: #$PR_NUMBER"
echo "URL: $PR_URL"

# Save PR info for later steps
echo "$PR_NUMBER" > /tmp/pr-number.txt
echo "$PR_URL" > /tmp/pr-url.txt
```

## Output

- Branch pushed to origin
- Draft PR created and linked to issue
- PR number and URL saved for downstream steps

## Next Step

Pass to `pr-reviewer` agent for code review.