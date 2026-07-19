# tests/test_context_deliver_chat_message.py
"""Component C — ctx.deliver_chat_message() public API surface tests.

Verifies the SDK contract:
- POSTs to auth-gw /v1/internal/chat/inject with correct payload + headers.
- Truncates text > 64KB with appended marker.
- Respects msg_type literal values.
- Forwards optional refresh_panels list.
"""
from __future__ import annotations
import pytest
import httpx

from imperal_sdk.context import Context
from imperal_sdk.types.identity import UserContext


def _make_ctx(*, ext_id="my-ext", user_id="imp_u_abc",
              gw="http://auth-gw:8085", svc="tok_xxx") -> Context:
    ctx = Context(user=UserContext(
        imperal_id=user_id, email="u@t.com", tenant_id="t", role="user",
    ))
    ctx._extension_id = ext_id
    ctx._user_id = user_id            # type: ignore[attr-defined]
    ctx._gateway_url = gw
    ctx._service_token = svc
    return ctx


@pytest.mark.asyncio
async def test_deliver_chat_message_posts_to_auth_gw(monkeypatch):
    captured: dict = {}

    class _MockAsyncClient:
        def __init__(self, *, timeout, **kw):
            captured["timeout"] = timeout
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("imperal_sdk.context.shared_http", _MockAsyncClient)
    ctx = _make_ctx()

    await ctx.deliver_chat_message("Hello!")
    assert captured["url"].endswith("/v1/internal/chat/inject")
    assert captured["json"]["text"] == "Hello!"
    assert captured["json"]["msg_type"] == "response"
    assert captured["json"]["ext_id"] == "my-ext"
    assert captured["json"]["user_id"] == "imp_u_abc"
    assert captured["headers"]["X-Service-Token"] == "tok_xxx"
    assert captured["headers"]["X-Acting-User"] == "imp_u_abc"


@pytest.mark.asyncio
async def test_deliver_chat_message_truncates_oversized_text(monkeypatch):
    captured: dict = {}

    class _MockAsyncClient:
        def __init__(self, *, timeout, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None, headers=None):
            captured["text"] = json["text"]
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("imperal_sdk.context.shared_http", _MockAsyncClient)
    ctx = _make_ctx()

    big = "x" * 70000
    await ctx.deliver_chat_message(big)
    assert len(captured["text"]) <= 64 * 1024 + len("...(truncated)")
    assert captured["text"].endswith("...(truncated)")


@pytest.mark.asyncio
async def test_deliver_chat_message_with_refresh_panels(monkeypatch):
    captured: dict = {}

    class _MockAsyncClient:
        def __init__(self, *, timeout, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None, headers=None):
            captured["json"] = json
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("imperal_sdk.context.shared_http", _MockAsyncClient)
    ctx = _make_ctx()

    await ctx.deliver_chat_message("Done!", msg_type="tool_result", refresh_panels=["editor"])
    assert captured["json"]["msg_type"] == "tool_result"
    assert captured["json"]["refresh_panels"] == ["editor"]
