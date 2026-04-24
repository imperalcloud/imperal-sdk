# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
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
    """PUT body must be {'envelope': {...}, 'ttl_seconds': N} per Auth GW
    CacheSetRequest schema (Phase 3). Assert the absence of the old shapes
    (params={'ttl': ...} and content=<bytes>) so regressions are loud."""
    ext, Model = _make_ext_with_model()
    http = FakeHttp()
    client = _make_client(ext, http)
    url = client._url("inbox_summary", "k")
    http.program("PUT", url, FakeResponse(200, {}))
    await client.set("k", Model(unread=3), ttl_seconds=60)
    method, called_url, kw = http.calls[0]
    assert method == "PUT"
    assert called_url == url
    # New body shape — exact keys + ttl_seconds value
    assert "json" in kw, "set() must send PUT body via json= kwarg"
    body = kw["json"]
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
    # Old-shape absence
    assert "params" not in kw, (
        "set() must NOT send ttl as query param (Phase 3 contract uses body)"
    )
    assert "content" not in kw, (
        "set() must NOT send bytes body (Phase 3 contract uses JSON body)"
    )


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
