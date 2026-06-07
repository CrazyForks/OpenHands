# Ticket Planner — openhands

Reads GitHub Issue → implementation plan mapped to this codebase.

## Inputs

- Issue number: from automation trigger (parsed from `gh issue list`)
- Issue title, body, labels: fetched from GitHub

## Process

### Step 1: Fetch the Issue

```bash
# Get the first open issue labeled 'ready-to-implement'
ISSUE_JSON=$(gh issue list \
  --repo openhands/openhands \
  --label ready-to-implement \
  --state open \
  --json number,title,body,labels \
  --limit 1)

ISSUE_NUMBER=$(echo "$ISSUE_JSON" | jq -r '.[0].number')
ISSUE_TITLE=$(echo "$ISSUE_JSON" | jq -r '.[0].title')
ISSUE_BODY=$(echo "$ISSUE_JSON" | jq -r '.[0].body // empty')

echo "Processing issue #$ISSUE_NUMBER: $ISSUE_TITLE"
```

### Step 2: Explore Codebase Structure

```bash
# List key directories and files
ls -la
find . -maxdepth 2 -type d | head -20
find . -maxdepth 2 -name "*.json" -o -name "*.config.*" | head -10

# Read AGENTS.md if exists
cat AGENTS.md 2>/dev/null || echo "No AGENTS.md found"

# Check for existing patterns
find . -name "*.md" -path "./.agents/*" 2>/dev/null | head -5
```

### Step 3: Identify Affected Files

Based on issue description, identify:
- Which directories contain relevant code
- Which files need modification
- Which test files need updates

```bash
# Search for relevant code patterns
grep -r "TODO\|FIXME\|BUG\|ISSUE" --include="*.py" --include="*.js" --include="*.ts" . 2>/dev/null | head -10

# List source structure
openhands, frontend/src
```

### Step 4: Write Implementation Plan

```bash
cat > /tmp/plan-$ISSUE_NUMBER.md << 'EOF'
# Implementation Plan — Issue #{{ISSUE_NUMBER}}

## Issue
**Title:** {{ISSUE_TITLE}}
**Body:** {{ISSUE_BODY}}

## Analysis

### Affected Directories
- openhands
- frontend/src

### Affected Files
(List files to be created/modified)

### Implementation Steps

1. (Step 1 description)
2. (Step 2 description)
3. (Step 3 description)

### Test Additions
- (Test files to create/update)

### Build Verification
- Command: make build
EOF

cat /tmp/plan-$ISSUE_NUMBER.md
```

## Output

- `/tmp/plan-{ISSUE_NUMBER}.md` - Implementation plan with:
  - Issue summary
  - Affected files and directories
  - Step-by-step implementation instructions
  - Test additions needed
  - Build verification command

## Next Step

Pass `/tmp/plan-{ISSUE_NUMBER}.md` to `code-implementer` agent.