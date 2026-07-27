# tests/test_http_retry.py
"""Bounded transient retry (5.9.13) — helper contract + secrets wiring.

Covers the production failure this shipped for: a single ConnectError /
ReadTimeout toward the auth gateway used to kill an extension handler
outright (SecretVaultUnavailable on the FIRST blip). One short retry must
absorb it, while a genuinely-down gateway must still fail — fast and with
the original exception type.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from imperal_sdk._http_retry import (
    MAX_ATTEMPTS,
    TRANSIENT_EXC,
    retry_transient,
)
from imperal_sdk.secrets.client import SecretClient
from imperal_sdk.secrets.exceptions import SecretVaultUnavailable
from imperal_sdk.secrets.spec import SecretSpec


# --------------------------------------------------------------------------
# helper contract
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_immediately_when_call_succeeds():
    calls = []

    async def _ok():
        calls.append(1)
        return "value"

    got = await retry_transient(lambda: _ok(), op="probe")
    assert got == "value"
    assert len(calls) == 1, "a successful call must not be repeated"


@pytest.mark.asyncio
async def test_recovers_after_one_transient_failure():
    """The exact production shape: blip, then success."""
    attempts = []

    async def _flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("SYN dropped")
        return "recovered"

    got = await retry_transient(lambda: _flaky(), op="probe")
    assert got == "recovered"
    assert len(attempts) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("exc_type", TRANSIENT_EXC)
async def test_every_declared_transient_error_is_retried(exc_type):
    attempts = []

    async def _flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise exc_type("transient")
        return "ok"

    assert await retry_transient(lambda: _flaky(), op="probe") == "ok"
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts_and_reraises_last():
    attempts = []

    async def _down():
        attempts.append(1)
        raise httpx.ConnectError("gateway down")

    with pytest.raises(httpx.ConnectError):
        await retry_transient(lambda: _down(), op="probe")
    assert len(attempts) == MAX_ATTEMPTS, "must be bounded, not infinite"


@pytest.mark.asyncio
async def test_non_transient_exception_propagates_without_retry():
    """A bug must surface on the first attempt, not be masked by retries."""
    attempts = []

    async def _boom():
        attempts.append(1)
        raise ValueError("programming error")

    with pytest.raises(ValueError):
        await retry_transient(lambda: _boom(), op="probe")
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_http_status_errors_are_not_retried():
    """503 is the caller's semantics (SecretVaultUnavailable), not ours."""
    attempts = []

    async def _resp():
        attempts.append(1)
        return httpx.Response(503, json={"detail": "vault down"})

    r = await retry_transient(lambda: _resp(), op="probe")
    assert r.status_code == 503
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_retry_budget_stays_sub_second():
    """Worst case must stay far below any user-visible action budget."""
    async def _down():
        raise httpx.ConnectError("down")

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(httpx.ConnectError):
        await retry_transient(lambda: _down(), op="probe")
    assert loop.time() - started < 1.0


# --------------------------------------------------------------------------
# secrets client wiring
# --------------------------------------------------------------------------

def _client() -> SecretClient:
    return SecretClient(
        ext_id="my-ext",
        imperal_id="imp_u_abc",
        auth_gw_base="http://auth-gw:8085",
        session_token="tok_x",
        declared={
            "api_key": SecretSpec(
                name="api_key", description="d", write_mode="extension",
            )
        },
    )


class _FlakyOnce:
    """shared_http stand-in: first HTTP verb call blips, then succeeds."""

    def __init__(self, *, response: httpx.Response, exc: Exception):
        self._response = response
        self._exc = exc
        self.calls = 0

    def __call__(self, *a, **kw):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def _maybe(self, *a, **kw):
        self.calls += 1
        if self.calls == 1:
            raise self._exc
        return self._response

    get = put = delete = _maybe


@pytest.mark.asyncio
async def test_secret_get_survives_a_transient_blip(monkeypatch):
    fake = _FlakyOnce(
        response=httpx.Response(200, json={"value": "s3cret"}),
        exc=httpx.ConnectError("SYN dropped"),
    )
    monkeypatch.setattr("imperal_sdk.secrets.client.shared_http", fake)

    assert await _client().get("api_key") == "s3cret"
    assert fake.calls == 2


@pytest.mark.asyncio
async def test_secret_get_still_raises_when_gateway_is_really_down(monkeypatch):
    class _AlwaysDown(_FlakyOnce):
        async def _maybe(self, *a, **kw):
            self.calls += 1
            raise httpx.ConnectError("down")
        get = put = delete = _maybe

    fake = _AlwaysDown(response=httpx.Response(200), exc=httpx.ConnectError("x"))
    monkeypatch.setattr("imperal_sdk.secrets.client.shared_http", fake)

    with pytest.raises(SecretVaultUnavailable):
        await _client().get("api_key")
    assert fake.calls == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_secret_delete_is_never_retried(monkeypatch):
    """A retried DELETE can mask the real was_set answer — must stay single-shot."""
    fake = _FlakyOnce(
        response=httpx.Response(200, json={"was_set": True}),
        exc=httpx.ConnectError("blip"),
    )
    monkeypatch.setattr("imperal_sdk.secrets.client.shared_http", fake)

    with pytest.raises(SecretVaultUnavailable):
        await _client().delete("api_key")
    assert fake.calls == 1
