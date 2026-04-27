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


@pytest.mark.asyncio
async def test_load_config_store_missing_env(monkeypatch, caplog):
    """When IMPERAL_GATEWAY_URL is missing, return None and WARN once."""
    monkeypatch.delenv("IMPERAL_GATEWAY_URL", raising=False)
    monkeypatch.delenv("IMPERAL_SERVICE_TOKEN", raising=False)

    p = LLMProvider()
    with caplog.at_level("WARNING", logger="imperal_sdk.runtime.llm_provider"):
        result1 = await p._load_config_store()
        result2 = await p._load_config_store()

    assert result1 is None
    assert result2 is None
    # WARN exactly once (not on second call) — per-instance warn-once flag
    warn_records = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "missing" in r.message
    ]
    assert len(warn_records) == 1, f"expected 1 warn, got {len(warn_records)}"


@pytest.mark.asyncio
@respx.mock
async def test_load_config_store_gateway_5xx(monkeypatch, caplog):
    """When gateway returns 5xx, return None + WARN, don't crash."""
    monkeypatch.setenv("IMPERAL_GATEWAY_URL", "http://gw.local")
    monkeypatch.setenv("IMPERAL_SERVICE_TOKEN", "svc-test")
    respx.get("http://gw.local/v1/internal/config/llm").mock(
        return_value=Response(503)
    )

    p = LLMProvider()
    with caplog.at_level("WARNING", logger="imperal_sdk.runtime.llm_provider"):
        result = await p._load_config_store()

    assert result is None
    warn_records = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "503" in r.message
    ]
    assert len(warn_records) == 1


@pytest.mark.asyncio
@respx.mock
async def test_load_config_store_connect_error(monkeypatch, caplog):
    """Network error → None + WARN with exception class name."""
    import httpx as _httpx
    monkeypatch.setenv("IMPERAL_GATEWAY_URL", "http://gw.local")
    monkeypatch.setenv("IMPERAL_SERVICE_TOKEN", "svc-test")
    respx.get("http://gw.local/v1/internal/config/llm").mock(
        side_effect=_httpx.ConnectError("connection refused")
    )

    p = LLMProvider()
    with caplog.at_level("WARNING", logger="imperal_sdk.runtime.llm_provider"):
        result = await p._load_config_store()

    assert result is None
    warn_records = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "ConnectError" in r.message
    ]
    assert len(warn_records) == 1


@pytest.mark.asyncio
@respx.mock
async def test_resolve_execution_uses_admin_config(monkeypatch):
    """End-to-end: with admin config returning openai/gpt-4.1-mini and
    no api_key in payload, _resolve(purpose='execution') returns
    openai/gpt-4.1-mini with api_key falling to OPENAI_API_KEY env.

    This is the regression-guard for the original bug: prior to fix
    this returned anthropic/claude-haiku-4-5-20251001 from
    _PROVIDER_DEFAULTS fallback.
    """
    monkeypatch.setenv("IMPERAL_GATEWAY_URL", "http://gw.local")
    monkeypatch.setenv("IMPERAL_SERVICE_TOKEN", "svc-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    # Production-shape response from auth-gw (verified live 2026-04-28):
    # api_key field is absent, not masked.
    respx.get("http://gw.local/v1/internal/config/llm").mock(
        return_value=Response(200, json={
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "purpose": {},
            "extensions": {},
            "extension_overrides": {},
            "failover_enabled": False,
            "failover_provider": "openai",
        })
    )

    p = LLMProvider()
    cfg = await p._resolve(purpose="execution")

    assert cfg.provider == "openai", f"got provider={cfg.provider}"
    assert cfg.model == "gpt-4.1-mini", f"got model={cfg.model}"
    assert cfg.api_key == "sk-test-openai", "should fall to OPENAI_API_KEY env"
    assert cfg.is_byollm is False
