"""Regression for LLM-FU-1 (2026-04-29).

OpenAI gpt-5 family + o-series reasoning models (o1/o3/o4) reject the legacy
`max_tokens` kwarg. The SDK runtime LLM provider must rename it to
`max_completion_tokens` for that family only — other providers and other
OpenAI models keep `max_tokens`.
"""
from __future__ import annotations

import pytest

from imperal_sdk.runtime.llm_provider import _openai_uses_max_completion_tokens


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
