"""Shared accessor for the Runtime API V2 warm-pool configuration map.

The deployment exposes the available V2 warm pools via the
``SANDBOX_WARM_RUNTIME_CONFIGS`` env var (a JSON object mapping warm-pool /
``sandbox_template`` name -> user-facing display name). Two layers read it:

- the web client config injector, to populate the SaaS Sandbox-tab dropdown, and
- the conversation start flow, to validate a user's saved selection before
  routing their sandbox to V2.

Keeping the parse here gives both a single source of truth without either
subsystem importing the other.
"""

import json
import logging
import os

_logger = logging.getLogger(__name__)

WARM_RUNTIME_CONFIGS_ENV_VAR = 'SANDBOX_WARM_RUNTIME_CONFIGS'


def get_warm_runtime_configs() -> dict[str, str]:
    """Parse the warm-pool map from the environment.

    Returns a dict mapping warm-pool name -> display name. JSON object key order
    is preserved (drives dropdown order). Returns an empty dict when the env var
    is unset, empty, or invalid (the latter logged), which disables the V2
    opt-in feature (the SaaS tab hides itself on an empty map).
    """
    raw = os.getenv(WARM_RUNTIME_CONFIGS_ENV_VAR, '').strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning(
            'Ignoring invalid %s (not valid JSON)', WARM_RUNTIME_CONFIGS_ENV_VAR
        )
        return {}
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
    ):
        _logger.warning(
            'Ignoring %s: expected a JSON object of string->string '
            '(warmPoolName -> displayName)',
            WARM_RUNTIME_CONFIGS_ENV_VAR,
        )
        return {}
    return parsed
