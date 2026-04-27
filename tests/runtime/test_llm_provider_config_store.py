"""Tests for LLMProvider._load_config_store HTTP fetch path.

Covers Sprint 1.1 hotfix: replaced broken `from shared_redis import ...`
with httpx call to auth-gw `/v1/internal/config/llm`.
"""
import pytest
import respx
from httpx import Response

from imperal_sdk.runtime.llm_provider import LLMProvider


@pytest.mark.asyncio
@respx.mock
async def test_load_config_store_success(monkeypatch):
    """Happy path: gateway returns config JSON, SDK caches and returns it."""
    monkeypatch.setenv("IMPERAL_GATEWAY_URL", "http://gw.local")
    monkeypatch.setenv("IMPERAL_SERVICE_TOKEN", "svc-test")
    expected = {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "purpose": {},
        "extensions": {},
        "extension_overrides": {},
        "failover_enabled": False,
    }
    route = respx.get("http://gw.local/v1/internal/config/llm").mock(
        return_value=Response(200, json=expected)
    )

    p = LLMProvider()
    result = await p._load_config_store()

    assert result == expected
    assert route.called
    # Cache hit on second call — must NOT re-fetch
    result2 = await p._load_config_store()
    assert result2 == expected
    assert route.call_count == 1
