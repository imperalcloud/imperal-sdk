"""Regression for LLM-FU-1 + LLM-FU-2 (2026-04-29).

OpenAI gpt-5 family + o-series reasoning models (o1/o3/o4) have two API
quirks that other providers and other OpenAI models do not:

  1. They reject the legacy `max_tokens` kwarg — must use
     `max_completion_tokens`. (LLM-FU-1)
  2. They reject any custom `temperature` value — only the default
     (1.0) is allowed, so callers must omit the kwarg entirely.
     (LLM-FU-2)

The SDK runtime LLM provider gates both behaviours through a pair of
helpers that share the same `_OPENAI_MCT_MODEL_PREFIXES` constant, so
they always agree on which models are "reasoning models".
"""
from __future__ import annotations

import pytest

from imperal_sdk.runtime.llm_provider import (
    _openai_supports_custom_temperature,
    _openai_uses_max_completion_tokens,
)


@pytest.mark.parametrize(
    "provider,model,expected",
    [
        # gpt-5 family — must use max_completion_tokens
        ("openai", "gpt-5", True),
        ("openai", "gpt-5-mini", True),
        ("openai", "gpt-5-nano", True),
        ("openai", "GPT-5-Mini", True),  # case-insensitive
        # o-series reasoning models
        ("openai", "o1", True),
        ("openai", "o1-mini", True),
        ("openai", "o1-preview", True),
        ("openai", "o3", True),
        ("openai", "o3-mini", True),
        ("openai", "o4-mini", True),
        # Legacy OpenAI models — must keep max_tokens
        ("openai", "gpt-4o", False),
        ("openai", "gpt-4o-mini", False),
        ("openai", "gpt-4-turbo", False),
        ("openai", "gpt-3.5-turbo", False),
        ("openai", "gpt-4.1", False),
        ("openai", "gpt-4.1-mini", False),
        # Other providers — never use max_completion_tokens regardless of model name
        ("anthropic", "claude-sonnet-4-6-20251001", False),
        ("anthropic", "gpt-5", False),  # nonsense combo, but provider gates the rename
        ("google", "gemini-2.5-pro", False),
        ("google", "gpt-5", False),
        ("openai_compatible", "gpt-5", False),  # Ollama serving misnamed model
        ("openai_compatible", "qwen3:27b", False),
        # Edge cases
        ("openai", "", False),
        ("", "gpt-5", False),
    ],
)
def test_openai_uses_max_completion_tokens(
    provider: str, model: str, expected: bool
) -> None:
    assert _openai_uses_max_completion_tokens(provider, model) is expected


@pytest.mark.parametrize(
    "provider,model,expected",
    [
        # gpt-5 family — does NOT support custom temperature
        ("openai", "gpt-5", False),
        ("openai", "gpt-5-mini", False),
        ("openai", "gpt-5-nano", False),
        ("openai", "GPT-5-Mini", False),  # case-insensitive
        # o-series reasoning models — does NOT support custom temperature
        ("openai", "o1", False),
        ("openai", "o1-mini", False),
        ("openai", "o1-preview", False),
        ("openai", "o3", False),
        ("openai", "o3-mini", False),
        ("openai", "o4-mini", False),
        # Legacy OpenAI models — DO support custom temperature
        ("openai", "gpt-4o", True),
        ("openai", "gpt-4o-mini", True),
        ("openai", "gpt-4-turbo", True),
        ("openai", "gpt-3.5-turbo", True),
        ("openai", "gpt-4.1", True),
        ("openai", "gpt-4.1-mini", True),
        # Other providers — always support custom temperature regardless of model name
        ("anthropic", "claude-sonnet-4-6-20251001", True),
        ("anthropic", "gpt-5", True),  # nonsense combo, but provider gates
        ("google", "gemini-2.5-pro", True),
        ("google", "gpt-5", True),
        ("openai_compatible", "gpt-5", True),  # Ollama serving misnamed model
        ("openai_compatible", "qwen3:27b", True),
        # Edge cases — empty model means we can't classify, default to "supported"
        ("openai", "", True),
        ("", "gpt-5", True),
    ],
)
def test_openai_supports_custom_temperature(
    provider: str, model: str, expected: bool
) -> None:
    assert _openai_supports_custom_temperature(provider, model) is expected


def test_helpers_agree_on_prefix_list() -> None:
    """The two helpers must always agree on which models are reasoning models.

    Specifically: a model uses `max_completion_tokens` iff it does NOT
    support custom temperature (for OpenAI provider). This prevents drift
    if one helper's prefix list is updated and the other is not.
    """
    reasoning_models = [
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "o1",
        "o1-mini",
        "o3",
        "o3-mini",
        "o4-mini",
    ]
    non_reasoning_models = ["gpt-4o", "gpt-4.1", "gpt-3.5-turbo"]
    for m in reasoning_models:
        assert _openai_uses_max_completion_tokens("openai", m) is True
        assert _openai_supports_custom_temperature("openai", m) is False
    for m in non_reasoning_models:
        assert _openai_uses_max_completion_tokens("openai", m) is False
        assert _openai_supports_custom_temperature("openai", m) is True
