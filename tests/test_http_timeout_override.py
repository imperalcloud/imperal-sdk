# tests/test_http_timeout_override.py
import pytest
import httpx
from imperal_sdk.http.client import HTTPClient


@pytest.mark.asyncio
async def test_post_accepts_per_call_timeout_override(monkeypatch):
    """Component A: timeout= kwarg overrides instance default."""
    captured: dict = {}

    class _MockAsyncClient:
        def __init__(self, *, timeout, follow_redirects, max_redirects):
            captured["timeout"] = timeout
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, **kw):
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("imperal_sdk.http.client.httpx.AsyncClient", _MockAsyncClient)
    c = HTTPClient(timeout=30)
    await c.post("https://example.com", timeout=120)
    assert captured["timeout"] == 120


@pytest.mark.asyncio
async def test_post_default_when_no_override(monkeypatch):
    """No timeout= kwarg → uses instance default."""
    captured: dict = {}

    class _MockAsyncClient:
        def __init__(self, *, timeout, follow_redirects, max_redirects):
            captured["timeout"] = timeout
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, **kw):
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("imperal_sdk.http.client.httpx.AsyncClient", _MockAsyncClient)
    c = HTTPClient(timeout=30)
    await c.post("https://example.com")
    assert captured["timeout"] == 30


@pytest.mark.asyncio
async def test_post_rejects_over_180s_cap():
    """Component A: federal cap 180s — anything more raises ValueError."""
    c = HTTPClient(timeout=30)
    with pytest.raises(ValueError, match="exceeds federal cap"):
        await c.post("https://example.com", timeout=300)


@pytest.mark.asyncio
async def test_post_rejects_zero_or_negative_timeout():
    c = HTTPClient(timeout=30)
    with pytest.raises(ValueError, match="must be > 0"):
        await c.post("https://example.com", timeout=0)
    with pytest.raises(ValueError, match="must be > 0"):
        await c.post("https://example.com", timeout=-5)
