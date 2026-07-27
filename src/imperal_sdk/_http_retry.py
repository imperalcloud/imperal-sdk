# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Bounded retry for TRANSIENT gateway-facing SDK calls (5.9.13).

Why
---
``_shared_http`` (5.9.12) bounded connection churn, but a single transient
blip still killed the whole call: the secrets client raised
``SecretVaultUnavailable`` on the FIRST ``ConnectError``/timeout, and the
extension handler died with it. Production evidence (24h on the platform
worker) — the auth-gw is healthy (healthz p50 ~2ms, 0 5xx) yet extensions
still lost secrets in short bursts that line up with skeleton-refresh
fan-out, not with any gateway outage:

    9  ConnectError   (SYN dropped at an overflowed accept queue)
    8  ReadTimeout    (5s budget exceeded under a burst)

Those are exactly the failures a short retry absorbs.

Contract
--------
- Retries ONLY connection-level / timeout errors, i.e. the request either
  never reached the app or produced no response. HTTP status codes are NOT
  retried here — the caller owns 4xx/5xx semantics (a 503 stays a 503).
- Retries ONLY when the caller declares the operation safe to repeat.
  Reads (GET) and idempotent writes (PUT of a fixed value) are safe;
  DELETE is not routed through here because a retried delete can mask
  the real ``was_set`` answer.
- Bounded and small: 2 extra attempts with jittered exponential backoff
  (~0.1s, ~0.2s + jitter). Worst case adds well under a second — far below
  any user-visible action budget, and it never turns a hard outage into a
  hang: a genuinely down gateway still fails fast after 3 attempts.
- Full jitter (``random.uniform(0, base)``) so a fan-out of extensions that
  all trip at the same instant does not retry in lockstep and re-create the
  very burst that caused the failure.

Usage
-----
    from imperal_sdk._http_retry import retry_transient

    r = await retry_transient(
        lambda: c.get(url, headers=h), op="get(name='x')",
    )
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

import httpx

log = logging.getLogger(__name__)

T = TypeVar("T")

#: Total attempts (1 initial + 2 retries).
MAX_ATTEMPTS = 3

#: Base backoff in seconds; attempt N sleeps a random slice of BASE * 2**(N-1).
BACKOFF_BASE_S = 0.1

#: Errors where the request provably did not get a response. ``ConnectError``
#: and ``ConnectTimeout`` never reached the app; ``ReadTimeout`` /
#: ``PoolTimeout`` / ``WriteTimeout`` may have, which is why only callers that
#: declare the operation idempotent use this helper.
TRANSIENT_EXC = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)


async def retry_transient(
    call: Callable[[], Awaitable[T]],
    *,
    op: str,
    max_attempts: int = MAX_ATTEMPTS,
) -> T:
    """Await ``call()``, retrying only transient transport failures.

    ``call`` must be a zero-arg coroutine factory (a fresh awaitable per
    attempt) — an already-created coroutine cannot be awaited twice.

    Re-raises the LAST transport exception when every attempt fails, so the
    caller's existing ``except`` block and error message stay intact. Any
    non-transient exception propagates immediately, unchanged.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await call()
        except TRANSIENT_EXC as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = random.uniform(0, BACKOFF_BASE_S * (2 ** (attempt - 1)))
            log.warning(
                "http_retry: transient %s on %s (attempt %d/%d), "
                "retrying in %.3fs",
                type(exc).__name__, op, attempt, max_attempts, delay,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None  # only reachable after a transient failure
    log.error(
        "http_retry: %s failed after %d attempts (%s)",
        op, max_attempts, type(last_exc).__name__,
    )
    raise last_exc
