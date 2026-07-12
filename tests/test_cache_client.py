# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Phase 4 Task 4.4 — ``ctx.cache`` CacheClient.

Uses a lightweight mock httpx surface so tests do not need a live Auth GW.
Imports from ``imperal_sdk.*`` — requires Python >= 3.11 (PEP 604 unions
elsewhere in the package). Smoke-run on 3.9 will fail at import.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from imperal_sdk.cache.client import CacheClient
from imperal_sdk.extension import Extension


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = (
            json.dumps(self._payload).encode()
            if isinstance(self._payload, (dict, list))
            else b""
        )

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if 400 <= self.status_code < 600:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("GET", "http://fake"),
                response=self,  # type: ignore[arg-type]
            )


class FakeHttp:
    """Minimal httpx.AsyncClient stand-in that records calls + returns
    pre-configured responses."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.responses: dict[tuple[str, str], FakeResponse] = {}
        self.default = FakeResponse(404)

    def program(self, method: str, url: str, response: FakeResponse) -> None:
        self.responses[(method, url)] = response

    async def request(self, method: str, url: str, **kw):
        self.calls.append((method, url, kw))
        return self.responses.get((method, url), self.default)


def _make_ext_with_model() -> tuple[Extension, type]:
    ext = Extension(app_id="mail")

    @ext.cache_model("inbox_summary")
    class InboxSummary(BaseModel):
        unread: int = 0
        latest_subject: str = ""

    return ext, InboxSummary


def _make_client(ext: Extension, http: FakeHttp | None = None) -> CacheClient:
    return CacheClient(
        app_id=ext.app_id,
        user_id="u-123",
        gw_url="http://gw.example.com",
        service_token="svc",
        call_token="tok",
        extension=ext,
        http_client=http,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Key validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_validates_key_length():
    ext, Model = _make_ext_with_model()
    client = _make_client(ext, FakeHttp())
    with pytest.raises(ValueError, match="too long"):
        await client.get("k" * 129, Model)


@pytest.mark.asyncio
async def test_get_validates_key_chars_slash():
    ext, Model = _make_ext_with_model()
    client = _make_client(ext, FakeHttp())
    with pytest.raises(ValueError, match="forbidden characters"):
        await client.get("foo/bar", Model)


@pytest.mark.asyncio
async def test_get_validates_key_chars_wildcard():
    ext, Model = _make_ext_with_model()
    client = _make_client(ext, FakeHttp())
    with pytest.raises(ValueError, match="forbidden"):
        await client.get("foo*", Model)


@pytest.mark.asyncio
async def test_get_validates_key_empty():
    ext, Model = _make_ext_with_model()
    client = _make_client(ext, FakeHttp())
    with pytest.raises(ValueError, match="non-empty"):
        await client.get("", Model)


# ---------------------------------------------------------------------------
# TTL bounds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_ttl_too_low():
    ext, Model = _make_ext_with_model()
    client = _make_client(ext, FakeHttp())
    with pytest.raises(ValueError, match=r"\[5, 300\]"):
        await client.set("k", Model(unread=1), ttl_seconds=4)


@pytest.mark.asyncio
async def test_set_ttl_too_high():
    ext, Model = _make_ext_with_model()
    client = _make_client(ext, FakeHttp())
    with pytest.raises(ValueError, match=r"\[5, 300\]"):
        await client.set("k", Model(unread=1), ttl_seconds=301)


@pytest.mark.asyncio
async def test_set_ttl_boundaries_ok():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    # Program both calls to return 200
    client = _make_client(ext, http)
    http.program(
        "PUT",
        client._url("inbox_summary", "k"),
        FakeResponse(200, {}),
    )
    await client.set("k", Model(unread=1), ttl_seconds=5)
    await client.set("k", Model(unread=1), ttl_seconds=300)


# ---------------------------------------------------------------------------
# Model / type constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_non_pydantic_raises():
    ext, _ = _make_ext_with_model()
    client = _make_client(ext, FakeHttp())
    with pytest.raises(TypeError, match="BaseModel"):
        await client.set("k", {"unread": 1}, ttl_seconds=60)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_set_unregistered_model_raises():
    ext, _ = _make_ext_with_model()

    class Unregistered(BaseModel):
        x: int = 1

    client = _make_client(ext, FakeHttp())
    with pytest.raises(ValueError, match="not registered"):
        await client.set("k", Unregistered(), ttl_seconds=60)


@pytest.mark.asyncio
async def test_get_non_pydantic_model_raises():
    ext, _ = _make_ext_with_model()

    class NotAModel:
        pass

    client = _make_client(ext, FakeHttp())
    with pytest.raises(TypeError, match="BaseModel"):
        await client.get("k", NotAModel)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_set_value_over_64kb_raises():
    ext = Extension(app_id="mail")

    @ext.cache_model("blob")
    class Blob(BaseModel):
        data: str = ""

    client = _make_client(ext, FakeHttp())
    huge = Blob(data="x" * (70 * 1024))
    with pytest.raises(ValueError, match="too large"):
        await client.set("k", huge, ttl_seconds=60)


# ---------------------------------------------------------------------------
# Happy-path + GET cache hit / miss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_none_on_404():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    http.default = FakeResponse(404)
    assert await client.get("missing", Model) is None


@pytest.mark.asyncio
async def test_get_returns_model_on_hit():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    envelope = {
        "model": "inbox_summary",
        "version": 1,
        "data": {"unread": 7, "latest_subject": "hello"},
        "cached_at": "2026-04-24T00:00:00+00:00",
    }
    http.program("GET", url, FakeResponse(200, envelope))
    got = await client.get("k", Model)
    assert got is not None
    assert got.unread == 7
    assert got.latest_subject == "hello"


@pytest.mark.asyncio
async def test_get_returns_none_on_model_mismatch():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    envelope = {
        "model": "wrong_name",
        "version": 1,
        "data": {"unread": 7},
        "cached_at": "2026-04-24T00:00:00+00:00",
    }
    http.program("GET", url, FakeResponse(200, envelope))
    assert await client.get("k", Model) is None


@pytest.mark.asyncio
async def test_set_sends_auth_headers():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    http.program("PUT", url, FakeResponse(200, {}))
    await client.set("k", Model(unread=3), ttl_seconds=60)
    method, called_url, kw = http.calls[0]
    assert method == "PUT"
    assert called_url == url
    h = kw["headers"]
    assert h["X-Service-Token"] == "svc"
    assert h["Authorization"] == "ImperalCallToken tok"


@pytest.mark.asyncio
async def test_set_sends_envelope_and_ttl_seconds_body_shape():
    """PUT body must decode to {'envelope': {...}, 'ttl_seconds': N} per Auth GW
    CacheSetRequest schema (Phase 3). The body is sent as pre-serialized COMPACT
    bytes via ``content=`` (not httpx ``json=``) so the exact bytes we size-check
    are the exact bytes on the wire (see the size-guard fix). Assert the absence
    of the old shapes (params={'ttl': ...} and json=<dict>) so regressions are
    loud."""
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    http.program("PUT", url, FakeResponse(200, {}))
    await client.set("k", Model(unread=3), ttl_seconds=60)
    method, called_url, kw = http.calls[0]
    assert method == "PUT"
    assert called_url == url
    # New transport — pre-serialized compact bytes via content=
    assert "content" in kw, "set() must send PUT body via content= (exact bytes)"
    body = json.loads(kw["content"])
    assert set(body.keys()) == {"envelope", "ttl_seconds"}, (
        f"PUT body keys must be exactly {{'envelope','ttl_seconds'}}, "
        f"got {set(body.keys())}"
    )
    assert body["ttl_seconds"] == 60
    env = body["envelope"]
    assert env["model"] == "inbox_summary"
    assert env["version"] == 1
    assert env["data"] == {"unread": 3, "latest_subject": ""}
    assert "cached_at" in env
    # Content-Type must be explicit since content= does not set it
    assert kw["headers"].get("Content-Type") == "application/json"
    # Old-shape absence
    assert "params" not in kw, (
        "set() must NOT send ttl as query param (Phase 3 contract uses body)"
    )
    assert "json" not in kw, (
        "set() must NOT use httpx json= (default separators re-inflate the "
        "body past what the size guard measured — the 413 bug)"
    )


@pytest.mark.asyncio
async def test_set_guard_measures_exact_wire_bytes_compact():
    """Regression for the guard-vs-wire size mismatch that caused live 413s.

    OLD behaviour: the guard measured ``json.dumps(envelope, compact)`` (inner
    envelope only) but httpx ``json={"envelope":..,"ttl_seconds":..}`` put a
    strictly LARGER body on the wire (default separators + wrapper dict). A
    payload could pass the guard yet exceed the server cap → 413.

    NEW behaviour: exactly ONE compact serialization of the full
    ``{envelope, ttl_seconds}`` body is both size-checked and sent. This test
    pins that the bytes on the wire are compact (no ``", "`` / ``": "`` spacing)
    and are byte-identical to a compact re-serialization of the decoded body."""
    ext = Extension(app_id="mail")

    @ext.cache_model("blob")
    class Blob(BaseModel):
        data: str = ""

    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("blob", "k")
    http.program("PUT", url, FakeResponse(200, {}))

    # A payload that is comfortably under 64 KB either way, so it must SEND
    # (not raise) — the point is to inspect the exact wire bytes.
    await client.set("k", Blob(data="z" * 4096), ttl_seconds=120)
    _method, _url, kw = http.calls[0]
    wire = kw["content"]
    assert isinstance(wire, (bytes, bytearray)), "wire body must be raw bytes"
    # Compact: no whitespace after JSON separators anywhere in the body.
    assert b", " not in wire and b": " not in wire, (
        "wire body must be COMPACT (separators=(',',':')) — spaced separators "
        "are the ~7% bloat that re-inflated the body past the guard"
    )
    # Byte-identical to a compact re-dump of what the server will parse.
    decoded = json.loads(wire)
    assert wire == json.dumps(decoded, separators=(",", ":")).encode("utf-8")
    assert decoded["ttl_seconds"] == 120
    assert decoded["envelope"]["data"] == {"data": "z" * 4096}


@pytest.mark.asyncio
async def test_delete_ok_on_404():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    # default 404 — should NOT raise
    await client.delete("k")


@pytest.mark.asyncio
async def test_delete_iterates_all_registered_models():
    """delete() must issue DELETE per registered model since key can live
    under any. Literal ``*`` in URL path is a no-op against Phase 3 Auth GW."""
    ext = Extension(app_id="mail")

    @ext.cache_model("inbox_summary")
    class InboxSummary(BaseModel):
        unread: int = 0

    @ext.cache_model("thread_snapshot")
    class ThreadSnapshot(BaseModel):
        subject: str = ""

    @ext.cache_model("draft_cache")
    class Draft(BaseModel):
        body: str = ""

    http = FakeHttp()
    # Program every model-scoped URL to return 404 (idempotent delete)
    client = _make_client(ext, http)
    for model_name in ("inbox_summary", "thread_snapshot", "draft_cache"):
        http.program(
            "DELETE",
            client._url(model_name, "some-key"),
            FakeResponse(404),
        )

    await client.delete("some-key")

    methods = [c[0] for c in http.calls]
    urls = [c[1] for c in http.calls]

    assert methods.count("DELETE") == 3, (
        f"Expected 3 DELETE calls (one per registered model), got {methods}"
    )
    # Each call must hit a distinct model path segment — no literal "*"
    model_segs = []
    for u in urls:
        # URL form: .../extcache/{app}/{user}/{model}/{hash}
        parts = u.split("/")
        # model is 2nd from the end
        model_segs.append(parts[-2])
    assert set(model_segs) == {"inbox_summary", "thread_snapshot", "draft_cache"}
    assert "*" not in model_segs, (
        "delete() must NOT use literal '*' in URL path — Phase 3 Auth GW does "
        "not support wildcard and would silently no-op"
    )


@pytest.mark.asyncio
async def test_delete_no_models_registered_is_noop():
    """When the extension has zero cache_model registrations, delete() must
    be a well-defined no-op (no DELETE issued)."""
    ext = Extension(app_id="mail")
    http = FakeHttp()
    client = _make_client(ext, http)
    await client.delete("some-key")
    assert [c[0] for c in http.calls] == []


# ---------------------------------------------------------------------------
# get_or_fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_fetch_uses_cache_when_present():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    envelope = {
        "model": "inbox_summary",
        "version": 1,
        "data": {"unread": 4},
        "cached_at": "2026-04-24T00:00:00+00:00",
    }
    http.program("GET", url, FakeResponse(200, envelope))

    calls = {"n": 0}

    async def fetcher():
        calls["n"] += 1
        return Model(unread=99)

    got = await client.get_or_fetch("k", Model, fetcher, ttl_seconds=60)
    assert got.unread == 4
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_get_or_fetch_invokes_fetcher_on_miss():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    http.program("GET", url, FakeResponse(404))
    http.program("PUT", url, FakeResponse(200, {}))

    async def fetcher():
        return Model(unread=42)

    got = await client.get_or_fetch("k", Model, fetcher, ttl_seconds=60)
    assert got.unread == 42
    # Verify both GET + PUT happened
    methods = [c[0] for c in http.calls]
    assert methods == ["GET", "PUT"]


@pytest.mark.asyncio
async def test_get_or_fetch_wrong_type_raises():
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    http.program("GET", url, FakeResponse(404))

    class Other(BaseModel):
        y: int = 1

    async def fetcher():
        return Other()  # type: ignore[return-value]

    with pytest.raises(TypeError, match="expected InboxSummary"):
        await client.get_or_fetch("k", Model, fetcher, ttl_seconds=60)


@pytest.mark.asyncio
async def test_get_or_fetch_oversized_write_serves_fresh_value():
    # Live 2026-07-12: an 83KB capability catalog tripped the 64KB size cap on
    # the WRITE inside get_or_fetch and the raised ValueError blanked the
    # caller's whole catalog — with the fetched value already in hand. The
    # write is an optimization: on ANY set failure the fresh value is served.
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    http.program("GET", url, FakeResponse(404))
    # No PUT programmed — but we don't even reach it: monkeypatch set to raise
    # the exact size-cap error.

    async def _boom(key, value, ttl_seconds=60):
        raise ValueError("cache value too large: 83460 > 65536 bytes "
                         "(I-CACHE-VALUE-SIZE-CAP-64KB)")

    client.set = _boom  # type: ignore[method-assign]

    async def fetcher():
        return Model(unread=7)

    got = await client.get_or_fetch("k", Model, fetcher, ttl_seconds=60)
    assert got.unread == 7            # fresh value served, no exception
