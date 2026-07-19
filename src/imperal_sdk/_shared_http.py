# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""ONE shared HTTP connection pool per process (2026-07-19).

The SDK runs IN-PROCESS inside the kernel worker: every per-call
``async with httpx.AsyncClient(...)`` in billing/store/secrets/cache/
skeleton/notify opened and tore down a fresh TCP (+TLS) connection toward
the auth gateway — multiplied per entity in bulk turns (live 2026-07-19:
a 149-task bulk delete drove the gateway latency-saturated and the 5s
secrets timeout produced SecretVaultUnavailable failures mid-action).
One keepalive pool per process bounds the churn; it is the SDK twin of
the kernel's ``core/http.py``.

Usage — swap the context-manager line ONLY, bodies untouched:

    from imperal_sdk._shared_http import shared_http

    async with shared_http() as client:            # httpx-default 5s budget
        resp = await client.get(url, timeout=10)   # per-request overrides win

``shared_http`` yields a per-request-timeout view over the ONE process-wide
client; exiting the block never closes the pool. ``ctx.http`` (the
user-facing egress client) deliberately stays per-call: ``max_redirects``
is a client-level httpx option configured per instance there, and its
contract tests pin the constructor kwargs.

Note for tests: monkeypatch the importing module's ``shared_http`` symbol
with any async-context-manager factory (the same shape the old
``httpx.AsyncClient`` fakes had), or call ``reset()`` between loops.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

import httpx

log = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None

# httpx's own default (5s everywhere) — bare ``AsyncClient()`` call sites
# keep byte-identical latency budgets; explicit per-request timeouts at the
# call sites always override (federal cap for ctx-level long-runs is 180s).
_DEFAULT_TIMEOUT = httpx.Timeout(5.0)
_LIMITS = httpx.Limits(
    max_connections=50,
    max_keepalive_connections=10,
    keepalive_expiry=30.0,
)


def get_shared_client() -> httpx.AsyncClient:
    """Lazy per-process singleton ``httpx.AsyncClient`` (keepalive pool).

    Loop-identity guard: pytest-asyncio and one-off ``asyncio.run`` tools
    spin fresh event loops; a loop change transparently rebuilds the client
    (the orphan dies with its loop).
    """
    global _client, _client_loop
    try:
        loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if (
        _client is None
        or _client.is_closed
        or (loop is not None and loop is not _client_loop)
    ):
        _client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, limits=_LIMITS)
        _client_loop = loop
    return _client


class _TimeoutView:
    """Per-request-timeout view over the shared client. Never closes
    anything; only defaults ``timeout=`` per request so migrated call sites
    keep their original latency budgets."""

    __slots__ = ("_c", "_t")

    def __init__(self, c: httpx.AsyncClient, timeout) -> None:
        self._c = c
        self._t = timeout

    def _kw(self, kw: dict) -> dict:
        kw.setdefault("timeout", self._t)
        return kw

    async def get(self, url, **kw):
        return await self._c.get(url, **self._kw(kw))

    async def post(self, url, **kw):
        return await self._c.post(url, **self._kw(kw))

    async def put(self, url, **kw):
        return await self._c.put(url, **self._kw(kw))

    async def patch(self, url, **kw):
        return await self._c.patch(url, **self._kw(kw))

    async def delete(self, url, **kw):
        return await self._c.delete(url, **self._kw(kw))

    async def request(self, method, url, **kw):
        return await self._c.request(method, url, **self._kw(kw))


@asynccontextmanager
async def shared_http(timeout=None) -> AsyncIterator[_TimeoutView]:
    """Drop-in replacement for ``async with httpx.AsyncClient(...)`` that
    reuses the ONE process-wide keepalive pool. Exiting the block is a
    no-op — the pool stays warm."""
    yield _TimeoutView(
        get_shared_client(),
        timeout if timeout is not None else _DEFAULT_TIMEOUT,
    )


async def aclose() -> None:
    """Graceful drain of keepalive sockets. Never raises."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception as exc:  # noqa: BLE001
            log.debug("_shared_http.aclose: %s", exc)
        _client = None


def reset() -> None:
    """Test hook: drop the singleton so the next call rebuilds it."""
    global _client, _client_loop
    _client = None
    _client_loop = None
