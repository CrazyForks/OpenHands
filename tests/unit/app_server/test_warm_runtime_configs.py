"""Tests for the shared warm-pool config accessor (Runtime API V2 opt-in)."""

import os
from unittest.mock import patch

from openhands.app_server.sandbox.warm_runtime_configs import (
    get_warm_runtime_configs,
)


class TestGetWarmRuntimeConfigs:
    def test_unset_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_warm_runtime_configs() == {}

    def test_empty_string_returns_empty(self):
        with patch.dict(os.environ, {'SANDBOX_WARM_RUNTIME_CONFIGS': '   '}):
            assert get_warm_runtime_configs() == {}

    def test_parses_object_and_preserves_order(self):
        raw = '{"python-gvisor": "Python (gVisor)", "node-sysbox": "Node.js"}'
        with patch.dict(os.environ, {'SANDBOX_WARM_RUNTIME_CONFIGS': raw}):
            result = get_warm_runtime_configs()
        assert result == {
            'python-gvisor': 'Python (gVisor)',
            'node-sysbox': 'Node.js',
        }
        # JSON object key order drives dropdown order.
        assert list(result.keys()) == ['python-gvisor', 'node-sysbox']

    def test_invalid_json_returns_empty(self):
        with patch.dict(os.environ, {'SANDBOX_WARM_RUNTIME_CONFIGS': 'not json'}):
            assert get_warm_runtime_configs() == {}

    def test_non_object_json_returns_empty(self):
        # A JSON array is valid JSON but the wrong shape.
        with patch.dict(os.environ, {'SANDBOX_WARM_RUNTIME_CONFIGS': '["a", "b"]'}):
            assert get_warm_runtime_configs() == {}

    def test_non_string_values_returns_empty(self):
        with patch.dict(os.environ, {'SANDBOX_WARM_RUNTIME_CONFIGS': '{"a": 1}'}):
            assert get_warm_runtime_configs() == {}
