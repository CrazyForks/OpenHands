"""Tests for DeepSeek BYOK (Bring Your Own Key) provider resolution.

Reproduces the issue reported in https://github.com/OpenHands/OpenHands/issues/14323
where using DeepSeek with a custom provider returns a 500 error because litellm
cannot resolve the provider from a bare ``deepseek-chat`` model name.

Root cause: litellm's ``get_llm_provider("deepseek-chat")`` raises
``BadRequestError`` when no provider prefix is supplied, and the
``_assign_provider`` helper in the model-list builder has no
``_BARE_DEEPSEEK_MODELS`` set to catch this.
"""

import warnings

import pytest

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from litellm import BadRequestError, get_llm_provider

from openhands.app_server.utils.llm import (
    _assign_provider,
    get_provider_api_base,
    resolve_llm_base_url,
)
from openhands.sdk.llm.utils.litellm_provider import infer_litellm_provider

MANAGED_PROXY = 'https://llm-proxy.app.all-hands.dev'


class TestDeepSeekBareNameProviderResolution:
    """litellm cannot infer the provider from bare ``deepseek-*`` names.

    This is the core bug: a user who types ``deepseek-chat`` in the model
    field (a reasonable thing to do — it appears in the verified list)
    will hit a 500 because ``litellm.get_llm_provider`` raises instead
    of returning ``"deepseek"``.
    """

    def test_bare_deepseek_chat_raises_in_litellm(self):
        """Bare ``deepseek-chat`` fails litellm's provider lookup."""
        with pytest.raises(BadRequestError, match='LLM Provider NOT provided'):
            get_llm_provider('deepseek-chat')

    def test_bare_deepseek_reasoner_raises_in_litellm(self):
        """Bare ``deepseek-reasoner`` also fails."""
        with pytest.raises(BadRequestError, match='LLM Provider NOT provided'):
            get_llm_provider('deepseek-reasoner')

    def test_prefixed_deepseek_chat_resolves(self):
        """``deepseek/deepseek-chat`` resolves correctly."""
        _model, provider, _dynamic, _name = get_llm_provider('deepseek/deepseek-chat')
        assert provider == 'deepseek'

    def test_openai_prefixed_deepseek_resolves(self):
        """``openai/deepseek-chat`` resolves to the openai provider."""
        _model, provider, _dynamic, _name = get_llm_provider('openai/deepseek-chat')
        assert provider == 'openai'


class TestAssignProviderDeepSeek:
    """``_assign_provider`` should prefix bare DeepSeek models.

    Currently it doesn't — the bare name falls through to the litellm
    fallback which raises, and the exception handler returns the bare name
    unprefixed.  This means the frontend model selector shows
    ``deepseek-chat`` without a provider, and a BYOK user who selects it
    gets a broken configuration.
    """

    def test_bare_deepseek_chat_gets_no_provider_prefix(self):
        """BUG: bare ``deepseek-chat`` is returned without a provider prefix.

        Expected (after fix): ``deepseek/deepseek-chat``
        Actual (current):     ``deepseek-chat``
        """
        result = _assign_provider('deepseek-chat')
        # This assertion documents the CURRENT (broken) behaviour.
        # After the fix it should be: assert result == 'deepseek/deepseek-chat'
        assert result == 'deepseek-chat', (
            'If this starts passing as deepseek/deepseek-chat, the fix landed!'
        )

    def test_prefixed_deepseek_chat_unchanged(self):
        """Already-prefixed ``deepseek/deepseek-chat`` is returned as-is."""
        assert _assign_provider('deepseek/deepseek-chat') == 'deepseek/deepseek-chat'


class TestInferLitellmProviderDeepSeek:
    """SDK's ``infer_litellm_provider`` returns ``None`` for common BYOK configs.

    When the provider is ``None``, ``litellm.completion()`` cannot route
    the request, producing a 500 error in the agent runtime.
    """

    def test_bare_deepseek_with_api_deepseek_com_returns_none(self):
        """BUG: provider inference fails for the most natural BYOK URL."""
        provider = infer_litellm_provider(
            model='deepseek-chat', api_base='https://api.deepseek.com'
        )
        # This documents the CURRENT (broken) behaviour.
        assert provider is None

    def test_bare_deepseek_with_no_base_url_returns_none(self):
        """BUG: provider inference fails without a base URL."""
        provider = infer_litellm_provider(model='deepseek-chat', api_base=None)
        assert provider is None

    def test_bare_deepseek_with_v1_suffix_works(self):
        """Workaround: appending ``/v1`` to the base URL lets litellm resolve."""
        provider = infer_litellm_provider(
            model='deepseek-chat', api_base='https://api.deepseek.com/v1'
        )
        assert provider == 'deepseek'

    def test_prefixed_deepseek_works_without_base_url(self):
        """``deepseek/deepseek-chat`` resolves even without a base URL."""
        provider = infer_litellm_provider(model='deepseek/deepseek-chat', api_base=None)
        assert provider == 'deepseek'

    def test_openai_prefix_works_with_deepseek_base_url(self):
        """``openai/deepseek-chat`` + DeepSeek URL resolves via OpenAI provider."""
        provider = infer_litellm_provider(
            model='openai/deepseek-chat', api_base='https://api.deepseek.com'
        )
        assert provider == 'openai'


class TestGetProviderApiBaseDeepSeek:
    """``get_provider_api_base`` returns ``None`` for bare ``deepseek-chat``.

    This means ``resolve_llm_base_url`` cannot auto-fill the base URL
    when the user omits it, leaving ``base_url=None`` in the saved
    settings.
    """

    def test_bare_deepseek_chat_returns_none(self):
        """BUG: no api_base resolved for bare ``deepseek-chat``."""
        result = get_provider_api_base('deepseek-chat')
        assert result is None

    def test_prefixed_deepseek_chat_returns_deepseek_url(self):
        """``deepseek/deepseek-chat`` correctly returns the DeepSeek API URL."""
        result = get_provider_api_base('deepseek/deepseek-chat')
        assert result is not None
        assert 'deepseek' in result


class TestResolveLlmBaseUrlDeepSeek:
    """``resolve_llm_base_url`` cannot auto-fill for bare DeepSeek models."""

    def test_bare_deepseek_no_base_url_returns_none(self):
        """BUG: ``base_url`` stays ``None`` for bare ``deepseek-chat``."""
        result = resolve_llm_base_url(
            model='deepseek-chat',
            base_url=None,
            managed_proxy_url=MANAGED_PROXY,
        )
        # Because get_provider_api_base('deepseek-chat') returns None,
        # resolve_llm_base_url returns None too. The user then gets no
        # base_url at all.
        assert result is None

    def test_prefixed_deepseek_no_base_url_auto_fills(self):
        """``deepseek/deepseek-chat`` correctly auto-fills the base URL."""
        result = resolve_llm_base_url(
            model='deepseek/deepseek-chat',
            base_url=None,
            managed_proxy_url=MANAGED_PROXY,
        )
        assert result is not None
        assert 'deepseek' in result

    def test_explicit_base_url_preserved(self):
        """A user-supplied ``base_url`` is always preserved regardless of model."""
        custom_url = 'https://api.deepseek.com/v1'
        result = resolve_llm_base_url(
            model='deepseek-chat',
            base_url=custom_url,
            managed_proxy_url=MANAGED_PROXY,
        )
        assert result == custom_url


class TestEndToEndDeepSeekBYOK:
    """End-to-end scenario: a user configures DeepSeek BYOK.

    Documents the full chain of failures that lead to the 500 error.
    """

    def test_byok_scenario_bare_model_no_base_url(self):
        """Scenario: user enters ``deepseek-chat`` + API key, no base URL.

        1. Settings save: resolve_llm_base_url returns None (can't auto-detect)
        2. LLM init: infer_litellm_provider returns None
        3. litellm.completion: raises BadRequestError → 500 to the user
        """
        # Step 1: Settings save doesn't auto-fill base_url
        base_url = resolve_llm_base_url(
            model='deepseek-chat',
            base_url=None,
            managed_proxy_url=MANAGED_PROXY,
        )
        assert base_url is None, 'base_url should be None (not auto-filled)'

        # Step 2: Provider inference fails
        provider = infer_litellm_provider(model='deepseek-chat', api_base=base_url)
        assert provider is None, 'provider should be None (not inferred)'

    def test_byok_scenario_bare_model_with_deepseek_url(self):
        """Scenario: user enters ``deepseek-chat`` + API key + ``https://api.deepseek.com``.

        Even with a correct-looking base URL, provider inference still fails
        because litellm requires ``/v1`` suffix for URL-based provider detection.
        """
        provider = infer_litellm_provider(
            model='deepseek-chat', api_base='https://api.deepseek.com'
        )
        assert provider is None, (
            'Provider inference fails even with the correct DeepSeek URL'
        )

    def test_byok_scenario_prefixed_model_works(self):
        """Scenario: user enters ``deepseek/deepseek-chat`` + API key.

        With the provider prefix, everything works correctly even without
        a base URL.
        """
        # Step 1: Settings save auto-fills base_url
        base_url = resolve_llm_base_url(
            model='deepseek/deepseek-chat',
            base_url=None,
            managed_proxy_url=MANAGED_PROXY,
        )
        assert base_url is not None

        # Step 2: Provider inference succeeds
        provider = infer_litellm_provider(
            model='deepseek/deepseek-chat', api_base=base_url
        )
        assert provider == 'deepseek'

    def test_byok_workaround_openai_prefix(self):
        """Workaround: using ``openai/deepseek-chat`` with custom base URL.

        This is the documented workaround from the OpenHands LLM settings page.
        """
        provider = infer_litellm_provider(
            model='openai/deepseek-chat', api_base='https://api.deepseek.com'
        )
        assert provider == 'openai'
