# Autonomous Dev Pipeline — openhands

End-to-end automation: GitHub Issue labelled `ready-to-implement` → implemented → PR → reviewed → CI green → notification.

## Pipeline

```
Issue labelled "ready-to-implement"
        ↓
  ticket-planner              reads issue, maps to codebase, writes plan
        ↓
  code-implementer            creates branch, writes code
        ↓
  tester                      writes missing tests
        ↓
  build-check (if applicable) frontend build verification
        ↓
  frontend-tester (if applicable) end-to-end frontend tests
        ↓
  ticket-manager              creates PR linked to issue
        ↓
  pr-reviewer                 self-review, inline comments, iterate (max 2)
        ↓
  ci-monitor                  waits for CI to green (max 3 retries)
        ↓
  mark-pr-ready               removes draft status
        ↓
  whatsapp-notifier           sends review request to your phone
```

## Setup: Register the Automation

```bash
# Create the label if it doesn't exist
gh label create "ready-to-implement" \
  --repo openhands/openhands \
  --color "0075ca" \
  --description "Queued for autonomous implementation"

# Register via OpenHands API (requires OPENHANDS_API_KEY)
curl -X POST "https://app.all-hands.dev/api/automation/v1/preset/prompt" \
  -H "Authorization: Bearer ${OPENHANDS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d @/tmp/automation-request.json
```

## Trigger the Pipeline

```bash
# Label an issue to fire the pipeline
gh issue edit <ISSUE_NUMBER> \
  --repo openhands/openhands \
  --add-label "ready-to-implement"
```

## What the Pipeline Will Never Do

- Merge to `main`
- Deploy to production
- Modify production environment variables

## Generated Files

```
.agents/agents/
  - ticket-planner.md
  - code-implementer.md
  - tester.md
  - pr-reviewer.md
  - ticket-manager.md
  - frontend-tester.md (conditional)
.agents/skills/
  - env-setup.md
  - ci-monitor.md
  - whatsapp-notifier.md
  - build-check.md (conditional)
  - playwright-smoke.md (conditional)
  - mark-pr-ready.md
```

## Audit Summary

| Field | Value |
|-------|-------|
| Tech Stack | Python + FastAPI (backend), React Router (frontend) |
| Total Agents | 6 |
| Total Skills | 5 |
| Conditional Added | build-check, playwright-smoke, frontend-tester |
| Package Manager | uv (Python), npm (frontend) |
| Test Framework | pytest, vitest |
| CI System | GitHub Actions |