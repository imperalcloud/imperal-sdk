"""Tests for LLMProvider ctx-injection contract (Sprint 1.2).

Covers:
- LLMConfig field alignment with kernel (failover_config, base_url, etc.)
- api_key repr safety
- ctx._llm_configs consumption + ENV fallback
- create_message backward-compat shim for legacy purpose= callers
- regression-guard for stripped resolution methods
"""
import pytest
from dataclasses import fields

from imperal_sdk.runtime.llm_provider import LLMConfig, LLMProvider


def test_llm_config_has_failover_config_field():
    """LLMConfig MUST have failover_config field for pre-resolved pair."""
    field_names = {f.name for f in fields(LLMConfig)}
    assert "failover_config" in field_names


def test_llm_config_aligned_with_kernel_shape():
    """LLMConfig fields aligned with kernel LLMConfig (8 core fields)."""
    field_names = {f.name for f in fields(LLMConfig)}
    expected = {
        "provider", "model", "api_key", "base_url",
        "is_byollm", "byollm_fallback",
        "thinking_mode", "byollm_tool_choice",
        "failover_config",
    }
    missing = expected - field_names
    assert not missing, f"missing fields: {missing}"


def test_llm_config_api_key_not_in_repr():
    """api_key MUST NOT appear in default __repr__ to prevent log leaks."""
    cfg = LLMConfig(provider="openai", model="gpt-4", api_key="sk-secret-123")
    repr_text = repr(cfg)
    assert "sk-secret-123" not in repr_text, (
        f"api_key leaked in repr: {repr_text}"
    )
    # Provider+model SHOULD appear (used in legitimate logging)
    assert "openai" in repr_text
    assert "gpt-4" in repr_text
