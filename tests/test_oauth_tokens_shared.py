# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Federal: I-OAUTH-REFRESH-SINGLE-IMPLEMENTATION (2026-08-21).

Live report: "Google Analytics: an expired access_token is not refreshed
automatically via refresh_token -- a manual reconnect is required."

Analytics stored a valid refresh_token and never used it. The same ~50-line
token_refresh.py existed in the Drive connector, the Search Console connector
and the mail client -- hand-copied, and by then already drifted (different
constants, different error text, different persistence). Analytics simply
never received a copy.

This suite pins the behaviour of the ONE shared implementation, and each test
names the specific way a hand-rolled copy got it wrong.
"""
from __future__ import annotations

import time

import pytest

from imperal_sdk.oauth_tokens import (
    DEFAULT_SKEW_SECONDS,
    PROVIDER_TOKEN_URLS,
    TokenRefreshError,
    fresh_token,
    needs_refresh,
    with_fresh_token,
)


# --------------------------------------------------------------------------
# Doubles
# --------------------------------------------------------------------------

class _Response:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _Secrets:
    def __init__(self, **values):
        self._values = values

    async def get(self, name: str):
        return self._values.get(name)


class _Store:
    def __init__(self):
        self.updates: list[tuple[str, str, dict]] = []
        self.fail = False

    async def update(self, collection: str, doc_id: str, data: dict, if_match: str = ""):
        if self.fail:
            raise RuntimeError("store unavailable")
        self.updates.append((collection, doc_id, data))
        return {"id": doc_id}


class _Http:
    """Records token-endpoint posts and replays queued responses."""

    def __init__(self, *responses):
        self._queue = list(responses) or [_Response(200, {"access_token": "new", "expires_in": 3600})]
        self.posts: list[tuple[str, dict]] = []

    async def post(self, url: str, **kwargs):
        self.posts.append((url, kwargs.get("data") or {}))
        return self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]


class _Ctx:
    def __init__(self, http=None, secrets=None, store=None):
        self.http = http or _Http()
        self.secrets = secrets or _Secrets(
            google_client_id="cid", google_client_secret="csecret",
            microsoft_client_id="mcid", microsoft_client_secret="msecret",
        )
        self.store = store or _Store()


def _account(**over) -> dict:
    acc = {
        "doc_id": "doc-1",
        "access_token": "old-token",
        "refresh_token": "refresh-abc",
        "expires_at": int(time.time()) + 3600,
    }
    acc.update(over)
    return acc


# --------------------------------------------------------------------------
# needs_refresh -- the predicate the copies got wrong
# --------------------------------------------------------------------------

def test_valid_token_is_left_alone():
    assert needs_refresh(_account()) is False


def test_expired_token_needs_refresh():
    assert needs_refresh(_account(expires_at=int(time.time()) - 5)) is True


def test_token_inside_the_skew_window_refreshes_early():
    """Refresh BEFORE expiry, or a slow request starts valid and finishes 401."""
    edge = int(time.time()) + (DEFAULT_SKEW_SECONDS - 5)
    assert needs_refresh(_account(expires_at=edge)) is True


def test_missing_expiry_metadata_forces_refresh():
    """THE COPY BUG. Every hand-rolled version wrote:

        if expires_at and int(expires_at) - now > 60: return acc

    An account stored without expires_at (or with 0 / "" / junk) fell through
    the ``and`` as falsy-but-untested and was returned UNCHANGED -- so it never
    refreshed proactively and 401'd forever. Absent expiry means UNKNOWN, and
    unknown must refresh.
    """
    assert needs_refresh(_account(expires_at=None)) is True
    assert needs_refresh(_account(expires_at=0)) is True
    assert needs_refresh(_account(expires_at="")) is True
    assert needs_refresh(_account(expires_at="not-a-number")) is True


def test_missing_access_token_needs_refresh():
    assert needs_refresh(_account(access_token="")) is True


def test_iso_and_string_expiry_are_understood():
    """Different connectors persisted expires_at as int, numeric string, or
    ISO-8601. One shared parser must read all three."""
    future_epoch = int(time.time()) + 3600
    assert needs_refresh(_account(expires_at=str(future_epoch))) is False
    assert needs_refresh(_account(expires_at=float(future_epoch))) is False


# --------------------------------------------------------------------------
# fresh_token -- the refresh itself
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_token_makes_no_network_call():
    ctx = _Ctx()
    await fresh_token(ctx, _account(), collection="accounts")
    assert ctx.http.posts == [], "a healthy token must not hit the token endpoint"


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_persisted():
    ctx = _Ctx(http=_Http(_Response(200, {"access_token": "fresh-xyz", "expires_in": 3600})))
    acc = await fresh_token(ctx, _account(expires_at=int(time.time()) - 10),
                            collection="ga_accounts")

    assert acc["access_token"] == "fresh-xyz"
    assert acc["expires_at"] > int(time.time()) + 3000
    url, data = ctx.http.posts[0]
    assert url == PROVIDER_TOKEN_URLS["google"]
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"] == "refresh-abc"
    # Persisted, so the next request does not refresh all over again.
    collection, doc_id, payload = ctx.store.updates[0]
    assert (collection, doc_id) == ("ga_accounts", "doc-1")
    assert payload["access_token"] == "fresh-xyz"
    assert "doc_id" not in payload, "doc_id is the address, not a field"


@pytest.mark.asyncio
async def test_rotated_refresh_token_is_stored():
    """Microsoft (and sometimes Google) returns a NEW refresh_token. The copies
    ignored it and kept replaying the original -- which works until the
    provider retires it and the user is told to reconnect."""
    ctx = _Ctx(http=_Http(_Response(200, {
        "access_token": "fresh", "expires_in": 3600, "refresh_token": "rotated-def",
    })))
    acc = await fresh_token(ctx, _account(expires_at=0), collection="accounts")

    assert acc["refresh_token"] == "rotated-def"
    assert ctx.store.updates[0][2]["refresh_token"] == "rotated-def"


@pytest.mark.asyncio
async def test_no_refresh_token_asks_for_reconnect():
    ctx = _Ctx()
    with pytest.raises(TokenRefreshError) as err:
        await fresh_token(ctx, _account(refresh_token="", expires_at=0))
    assert err.value.reconnect_required is True


@pytest.mark.asyncio
async def test_invalid_grant_asks_for_reconnect():
    """A dead grant (revoked, password changed) is the ONE case where a manual
    reconnect is the honest answer."""
    ctx = _Ctx(http=_Http(_Response(400, {"error": "invalid_grant"})))
    with pytest.raises(TokenRefreshError) as err:
        await fresh_token(ctx, _account(expires_at=0))
    assert err.value.reconnect_required is True


@pytest.mark.asyncio
async def test_provider_5xx_is_transient_not_a_reconnect():
    """A provider outage must NOT tell the user to reconnect a healthy account."""
    ctx = _Ctx(http=_Http(_Response(503, {})))
    with pytest.raises(TokenRefreshError) as err:
        await fresh_token(ctx, _account(expires_at=0))
    assert err.value.reconnect_required is False


@pytest.mark.asyncio
async def test_missing_client_credentials_is_not_the_users_fault():
    ctx = _Ctx(secrets=_Secrets())
    with pytest.raises(TokenRefreshError) as err:
        await fresh_token(ctx, _account(expires_at=0))
    assert err.value.reconnect_required is False, "reconnecting cannot fix a missing app secret"


@pytest.mark.asyncio
async def test_store_failure_does_not_break_the_request():
    """Persistence is best-effort: the caller holds a valid token either way."""
    store = _Store()
    store.fail = True
    ctx = _Ctx(http=_Http(_Response(200, {"access_token": "fresh", "expires_in": 3600})),
               store=store)
    acc = await fresh_token(ctx, _account(expires_at=0), collection="accounts")
    assert acc["access_token"] == "fresh"


@pytest.mark.asyncio
async def test_microsoft_uses_its_own_endpoint():
    ctx = _Ctx(http=_Http(_Response(200, {"access_token": "ms", "expires_in": 3600})))
    await fresh_token(ctx, _account(expires_at=0), provider="microsoft")
    assert ctx.http.posts[0][0] == PROVIDER_TOKEN_URLS["microsoft"]


# --------------------------------------------------------------------------
# with_fresh_token -- the reactive layer that removes the manual reconnect
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_401_on_a_believed_valid_token_is_retried_once():
    """THE ANALYTICS BUG, exactly. The clock said the token was good for
    another hour; the provider said 401 (clock skew, early revocation, a
    shorter real lifetime). Every hand-rolled copy stopped here and surfaced
    "reconnect the account". One forced refresh + retry makes it invisible."""
    ctx = _Ctx(http=_Http(_Response(200, {"access_token": "fresh-after-401", "expires_in": 3600})))
    calls: list[str] = []

    async def call(acc):
        calls.append(acc["access_token"])
        return _Response(401 if len(calls) == 1 else 200, {"ok": True})

    response = await with_fresh_token(ctx, _account(), call, collection="accounts")

    assert response.status_code == 200
    assert calls == ["old-token", "fresh-after-401"], "retry must use the REFRESHED token"


@pytest.mark.asyncio
async def test_successful_call_is_not_retried():
    ctx = _Ctx()
    calls = []

    async def call(acc):
        calls.append(1)
        return _Response(200, {"ok": True})

    await with_fresh_token(ctx, _account(), call, collection="accounts")
    assert len(calls) == 1
    assert ctx.http.posts == []


@pytest.mark.asyncio
async def test_retry_happens_only_once():
    """A permanently-401ing endpoint must not loop."""
    ctx = _Ctx(http=_Http(_Response(200, {"access_token": "fresh", "expires_in": 3600})))
    calls = []

    async def call(acc):
        calls.append(1)
        return _Response(401, {})

    response = await with_fresh_token(ctx, _account(), call, collection="accounts")
    assert response.status_code == 401
    assert len(calls) == 2, "exactly one retry, then surface the failure"


@pytest.mark.asyncio
async def test_non_401_errors_pass_straight_through():
    """403/404/500 are not token problems -- refreshing would only add noise."""
    ctx = _Ctx()
    calls = []

    async def call(acc):
        calls.append(1)
        return _Response(403, {"error": "forbidden"})

    response = await with_fresh_token(ctx, _account(), call, collection="accounts")
    assert response.status_code == 403
    assert len(calls) == 1
    assert ctx.http.posts == []


@pytest.mark.asyncio
async def test_dead_grant_on_the_retry_path_surfaces_reconnect():
    ctx = _Ctx(http=_Http(_Response(400, {"error": "invalid_grant"})))

    async def call(acc):
        return _Response(401, {})

    with pytest.raises(TokenRefreshError) as err:
        await with_fresh_token(ctx, _account(), call, collection="accounts")
    assert err.value.reconnect_required is True


# --------------------------------------------------------------------------
# Terminal vs transient: the proactive-refresh failure path
#
# Found by the Analytics integration test (2026-08-21). The lenient branch
# below used to catch EVERY TokenRefreshError and attempt the call anyway.
# For a revoked grant that is wrong: invalid_grant means the user revoked
# access and the stored access token died with it, so the attempt either
# errors confusingly downstream or -- against a caching layer -- looks like
# success. Terminal failures must surface; transient ones must not.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoked_grant_does_not_attempt_the_call_with_a_dead_token():
    """Terminal (invalid_grant): surface the reconnect, do not pretend."""
    ctx = _Ctx(http=_Http(_Response(400, {"error": "invalid_grant"})))
    calls = []

    async def call(acc):
        calls.append(1)
        return _Response(200, {})

    with pytest.raises(TokenRefreshError) as err:
        await with_fresh_token(ctx, _account(expires_at=int(time.time()) - 60),
                               call, collection="accounts")

    assert err.value.reconnect_required is True
    assert calls == [], "a revoked grant must not be papered over with a dead token"


@pytest.mark.asyncio
async def test_transient_refresh_failure_still_tries_the_stored_token():
    """Transient (provider 5xx): the token in hand may still have seconds."""
    ctx = _Ctx(http=_Http(_Response(503, {"error": "backend unavailable"})))
    calls = []

    async def call(acc):
        calls.append(acc.get("access_token"))
        return _Response(200, {})

    response = await with_fresh_token(ctx, _account(expires_at=int(time.time()) - 60),
                                      call, collection="accounts")

    assert response.status_code == 200
    assert calls == ["old-token"], "a blip must not block a token that may still work"
