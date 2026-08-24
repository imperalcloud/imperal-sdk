# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""The gateway-backed namespaces added in 5.12.0.

WHAT IS WORTH TESTING HERE. These clients hold almost no logic — the value
they add is that every extension now reaches a route the SAME way. So the
tests assert the things that would silently rot: the exact route, the exact
headers (isolation depends on one of them), and that a failing gateway turns
into a typed error instead of a raw httpx exception leaking upward.

WHY IT PATCHES ``_gateway.shared_http`` AND NOT ``httpx.AsyncClient``. The
SDK's own pool docstring says so, and it matters: ``shared_http`` yields a
view over ONE process-wide client, so patching the httpx constructor
intercepts nothing and the suite goes green while testing air. That exact
mistake shipped two real defects in an extension earlier today.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from imperal_sdk import _gateway
from imperal_sdk.apps.client import AppsClient
from imperal_sdk.conversations.client import ConversationsClient
from imperal_sdk.errors import APIError, AuthError, NotFoundError
from imperal_sdk.rbac.client import RBACClient
from imperal_sdk.users.client import UsersClient

GW = "http://auth-gw.internal:8085"
TOKEN = "svc-token"
UID = "imp_u_TEST"


class _Recorder:
    """Records every outgoing request and replays programmed responses."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.responses: dict[tuple[str, str], Any] = {}
        self.default = httpx.Response(200, json={"ok": True})

    def program(self, method: str, path: str, *, json_body=None,
                status: int = 200):
        self.responses[(method, path)] = httpx.Response(status, json=json_body)

    def raises(self, exc: BaseException):
        self.default = exc

    async def _request(self, method, url, **kw):
        req = httpx.Request(method, url, headers=kw.get("headers") or {},
                            json=kw.get("json"), params=kw.get("params"))
        self.requests.append(req)
        programmed = self.responses.get((method, req.url.path))
        if programmed is not None:
            return programmed
        if isinstance(self.default, BaseException):
            raise self.default
        return self.default

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "no request was made"
        return self.requests[-1]


@pytest.fixture
def gw(monkeypatch) -> _Recorder:
    rec = _Recorder()

    class _Client:
        async def request(self, method, url, **kw):
            return await rec._request(method, url, **kw)

    @asynccontextmanager
    async def _fake_pool(*a, **kw):
        yield _Client()

    monkeypatch.setattr(_gateway, "shared_http", _fake_pool)
    return rec


def _client(cls, user_id: str = UID):
    return cls(gateway_url=GW, service_token=TOKEN, user_id=user_id,
               extension_id="test-ext", tenant_id="t1")


# ── the shared base ─────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_every_call_carries_the_acting_user(gw):
    """Per-user isolation rests entirely on this header being present."""
    await _client(ConversationsClient).list()

    assert gw.last.headers["X-Acting-User"] == UID
    assert gw.last.headers["X-Service-Token"] == TOKEN


@pytest.mark.asyncio
async def test_an_unknown_user_sends_no_empty_header(gw):
    """An empty X-Acting-User looks like an answered question. Omit it."""
    await _client(ConversationsClient, user_id="").list()

    assert "X-Acting-User" not in gw.last.headers


@pytest.mark.asyncio
async def test_for_user_rebinds_without_mutating_the_original(gw):
    original = _client(UsersClient)
    scoped = original.for_user("imp_u_OTHER")

    assert original.user_id == UID
    assert scoped.user_id == "imp_u_OTHER"
    assert type(scoped) is type(original)


@pytest.mark.asyncio
async def test_a_404_becomes_NotFoundError_not_a_raw_httpx_error(gw):
    gw.program("GET", "/v1/conversations/c_gone/messages",
               json_body={"detail": "no such thread"}, status=404)

    with pytest.raises(NotFoundError):
        await _client(ConversationsClient).messages("c_gone")


@pytest.mark.asyncio
async def test_a_403_becomes_AuthError(gw):
    gw.program("GET", "/v1/users/imp_u_X", json_body={"detail": "nope"},
               status=403)

    with pytest.raises(AuthError):
        await _client(UsersClient).get("imp_u_X")


@pytest.mark.asyncio
async def test_a_500_becomes_APIError_carrying_the_status(gw):
    gw.program("GET", "/v1/roles", json_body={"detail": "boom"}, status=500)

    with pytest.raises(APIError) as exc:
        await _client(RBACClient).list_roles()
    assert exc.value.status_code == 500


# ── routes: the thing that silently rots ────────────────────────────────── #

@pytest.mark.asyncio
async def test_conversation_routes(gw):
    c = _client(ConversationsClient)

    await c.list()
    assert gw.last.url.path == "/v1/conversations"

    await c.messages("c1")
    assert gw.last.url.path == "/v1/conversations/c1/messages"

    await c.activate("c1")
    assert (gw.last.method, gw.last.url.path) == (
        "POST", "/v1/conversations/c1/activate")

    await c.delete("c1")
    assert (gw.last.method, gw.last.url.path) == (
        "DELETE", "/v1/conversations/c1")


@pytest.mark.asyncio
async def test_user_routes(gw):
    u = _client(UsersClient)

    await u.get(UID)
    assert gw.last.url.path == f"/v1/users/{UID}"

    await u.get_settings(UID)
    assert gw.last.url.path == f"/v1/internal/users/{UID}/settings"

    await u.surfaces(UID)
    assert gw.last.url.path == f"/v1/internal/surfaces/{UID}"

    await u.reset_conversation(UID)
    assert (gw.last.method, gw.last.url.path) == (
        "POST", f"/v1/users/{UID}/reset-conversation")


@pytest.mark.asyncio
async def test_app_and_rbac_routes(gw):
    a = _client(AppsClient)
    await a.list_pending()
    assert gw.last.url.path == "/v1/admin/apps/pending"

    await a.approve("some-app")
    assert (gw.last.method, gw.last.url.path) == (
        "POST", "/v1/admin/apps/some-app/approve")

    r = _client(RBACClient)
    await r.effective_scopes(UID)
    assert gw.last.url.path == f"/v1/scopes/effective/{UID}"


# ── app settings: the family that shipped wrong in 5.12.0 ───────────────── #
#
# These four exist because 5.12.0 shipped get_settings/update_settings
# pointing at /v1/apps/{id}/settings — a route the gateway does not serve.
# The suite was green: it asserted the USER settings route and never the app
# one, so a plausible-looking invention sailed into a public release. The
# lesson is not "add a test", it is that a route nobody asserts is a route
# nobody has checked exists.

@pytest.mark.asyncio
async def test_app_settings_read_hits_unified_config_and_unwraps(gw):
    """App settings live in unified_config's `app` scope, not a route of
    their own, and arrive wrapped in an envelope."""
    gw.program("GET", "/v1/internal/config/app/some-app",
               json_body={"scope": "app", "scope_id": "some-app",
                          "config": {"theme": "dark"},
                          "enforced": {}, "role_defaults": {}})

    got = await _client(AppsClient).get_settings("some-app")

    assert gw.last.url.path == "/v1/internal/config/app/some-app"
    assert got == {"theme": "dark"}, "caller wants config, not the envelope"


@pytest.mark.asyncio
async def test_app_settings_read_treats_a_missing_row_as_empty(gw):
    """A first-run app has no config row. That is a normal state, and the
    gateway says so with 404 — callers should not have to catch it."""
    gw.program("GET", "/v1/internal/config/app/fresh-app",
               json_body={"detail": "Config not found"}, status=404)

    assert await _client(AppsClient).get_settings("fresh-app") == {}


@pytest.mark.asyncio
async def test_app_settings_write_is_a_put_wrapped_in_config(gw):
    """The route upserts with a deep merge and reads the patch from a
    `config` key. Sent bare, the write silently stored nothing."""
    await _client(AppsClient).update_settings("some-app", {"theme": "dark"})

    assert (gw.last.method, gw.last.url.path) == (
        "PUT", "/v1/internal/config/app/some-app")
    assert json.loads(gw.last.content) == {"config": {"theme": "dark"}}


@pytest.mark.asyncio
async def test_app_settings_write_can_prune_a_subtree(gw):
    """An authoritative writer must be able to remove keys it omits —
    deep merge alone can only ever add."""
    await _client(AppsClient).update_settings(
        "some-app", {"ui": {"slots": []}},
        updated_by="imp_u_ADMIN", replace_paths=["ui.slots"])

    body = json.loads(gw.last.content)
    assert body["replace_paths"] == ["ui.slots"]
    assert body["updated_by"] == "imp_u_ADMIN"


# ── guards: refusing to send a meaningless call ─────────────────────────── #

@pytest.mark.parametrize("call", [
    lambda c: c.messages(""),
    lambda c: c.activate("   "),
    lambda c: c.delete(""),
])
@pytest.mark.asyncio
async def test_conversations_refuse_a_blank_id_without_calling_out(gw, call):
    with pytest.raises(ValueError):
        await call(_client(ConversationsClient))
    assert gw.requests == []


@pytest.mark.asyncio
async def test_update_settings_refuses_an_empty_patch(gw):
    """An empty PATCH is a no-op that still costs a round trip."""
    with pytest.raises(ValueError):
        await _client(UsersClient).update_settings(UID, {})
    assert gw.requests == []
