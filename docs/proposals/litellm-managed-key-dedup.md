# Proposal: reconcile per-(user,org) LiteLLM managed keys + label them by org

Status: draft / follow-up. Pre-existing bug; Alona explicitly wants it fixed.

## Problem 1 — duplicate managed keys accumulate

OHE provisions a LiteLLM virtual key per `(user, org)` (team_id == org_id). The
provisioning has an **asymmetry**: when an org's default model is set to an
`openhands/*` model, the "openhands" branch
(`enterprise/storage/saas_settings_store.py` ~515-521, `enterprise/storage/org_store.py`
~846-856) mints a fresh `metadata={"type":"openhands"}`, **alias-less** key but —
unlike the non-openhands branch — does **not** delete the pre-existing alias key
first. The old alias key has `metadata={}`, which fails the
`verify_existing_key(openhands_type=True)` match (`lite_llm_manager.py` ~1454-1466),
so it's neither reused nor deleted — it lingers.

Result: switching an org's default to/from an `openhands/*` model leaves an
orphaned managed key. Confirmed live: a user in 2 orgs had 3 keys — one org had a
stale alias key plus the active `type=openhands` key.

**Impact:** nil today (`ENABLE_BILLING=false`, budgets unlimited), but orphaned
keys carry spend and would distort usage/budget the moment billing/budgets are on.

**Fix:** reconcile to exactly one managed key per `(user, org)`. The openhands
branch should delete the prior managed key before minting. Since the openhands
key is alias-less, dedup needs a findable identifier — either give it a
deterministic alias, or match-and-delete by `team_id` + `metadata.type`. Make the
two branches symmetric.

## Problem 2 — keys are unreadable in the dashboard

`key_alias`/`team_alias` use the org UUID and the user's uid, so personal-org vs
default-org keys are indistinguishable in the LiteLLM dashboard (both team_aliases
resolved to the same uid). Set `team_alias`/`key_alias` to the org's **display
name** at provisioning so the dashboard is human-readable.

## Cleanup

Existing orphaned duplicate keys are safe to delete (no auto-cleanup exists).

Part of the LLM-settings state map (P8) — `local-docs/llm-settings-state-map.md`.
