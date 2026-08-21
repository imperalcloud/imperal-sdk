# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Shared OAuth token refresh -- the ONE implementation every connector uses.

Why this module exists (2026-08-21, Google Analytics reconnect report)
----------------------------------------------------------------------
"Google Analytics: an expired access_token is not refreshed automatically via
refresh_token -- a manual reconnect is required."

The Analytics extension stored a perfectly good ``refresh_token`` and never
used it: its request path read ``account["access_token"]`` and mapped HTTP 401
straight to "reconnect the account". It was not alone in the pattern -- it was
alone in *missing* it. The same ~50-line ``token_refresh.py`` had been
hand-copied into the Drive connector, the Search Console connector and the
mail client, and those copies had ALREADY drifted apart (different constants,
different error text, different persistence). Analytics simply never got a
copy, and nothing in the platform noticed.

Copying it a fourth time would fix Analytics for a week and guarantee a fifth
divergence. So the behaviour lives here, once::

    from imperal_sdk.oauth_tokens import fresh_token, with_fresh_token

Two layers, because expiry metadata cannot be trusted on its own:

1. **Proactive** -- refresh when ``expires_at`` is within ``skew`` seconds, or
   is absent/unparseable (exactly the state in which a stale token hides).
2. **Reactive** -- :func:`with_fresh_token` retries ONCE on a 401. Clock skew,
   a token revoked early, a provider expiring sooner than advertised: every
   hand-rolled copy failed this case because it only ever looked at the clock.
   This layer is what removes the manual reconnect.

Refresh-token ROTATION is handled: Microsoft (and Google, when it chooses to)
returns a NEW ``refresh_token`` on refresh. The copies ignored it and kept
replaying the original -- which works until the provider retires it, and then
the user is told to reconnect. Here a rotated token is persisted.

Federal invariant: ``I-OAUTH-REFRESH-SINGLE-IMPLEMENTATION``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Optional

__all__ = [
    "TokenRefreshError",
    "PROVIDER_TOKEN_URLS",
    "needs_refresh",
    "fresh_token",
    "with_fresh_token",
]

log = logging.getLogger("imperal_sdk.oauth_tokens")

#: Token endpoints per provider, matching the ``ctx.oauth_authorize_url``
#: provider names so a connector never has to name a URL itself.
PROVIDER_TOKEN_URLS: dict[str, str] = {
    "google": "https://oauth2.googleapis.com/token",
    "microsoft": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "yahoo": "https://api.login.yahoo.com/oauth2/get_token",
}

#: Refresh this many seconds BEFORE the provider's stated expiry. Sixty seconds
#: is the value the hand-rolled copies converged on and it is enough to cover a
#: slow request that starts just under the wire.
DEFAULT_SKEW_SECONDS = 60


class TokenRefreshError(RuntimeError):
    """A refresh could not be performed or was rejected by the provider.

    Carries ``reconnect_required`` so a caller can tell an unrecoverable state
    (no refresh_token on the account, provider says ``invalid_grant`` -- the
    user really must reconnect) from a transient one (network blip, provider
    5xx) that is worth retrying later.
    """

    def __init__(self, message: str, *, reconnect_required: bool = False,
                 status_code: int = 0) -> None:
        super().__init__(message)
        self.reconnect_required = reconnect_required
        self.status_code = status_code


def _parse_expires_at(value: Any) -> Optional[int]:
    """Best-effort epoch seconds from whatever the account doc happens to hold.

    Accounts have been written by several different callbacks over time:
    ``expires_at`` shows up as an int, as a numeric string, and as an ISO-8601
    timestamp. An unparseable value returns None, which callers treat as
    "unknown -> refresh now" rather than "still valid" -- guessing valid is how
    a stale token survives to become a 401.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime

        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None


def needs_refresh(account: dict, *, skew: int = DEFAULT_SKEW_SECONDS) -> bool:
    """True when the stored access token is missing, expiring, or unknowable."""
    if not (account or {}).get("access_token"):
        return True
    expires_at = _parse_expires_at((account or {}).get("expires_at"))
    if expires_at is None:
        # No usable expiry metadata. The copies returned the token unchanged
        # here (``if expires_at and ...``), so an account written without an
        # expiry NEVER refreshed proactively -- it just 401'd forever.
        return True
    return expires_at - int(time.time()) <= skew


def _doc_id(account: dict) -> str:
    return str((account or {}).get("doc_id") or (account or {}).get("id") or "")


async def _persist(ctx, collection: str, account: dict) -> None:
    """Write refreshed fields back. Best-effort: a store failure must not fail
    the user's actual request -- the token in hand is already valid, and the
    next call simply refreshes again."""
    doc_id = _doc_id(account)
    if not (collection and doc_id):
        return
    payload = {k: v for k, v in account.items() if k not in ("doc_id", "id")}
    try:
        await ctx.store.update(collection, doc_id, payload)
    except Exception as exc:  # noqa: BLE001 - deliberately non-fatal
        log.warning("oauth token persisted refresh failed (non-fatal): %s", exc)


async def fresh_token(
    ctx,
    account: dict,
    *,
    provider: str = "google",
    collection: str = "",
    skew: int = DEFAULT_SKEW_SECONDS,
    force: bool = False,
) -> dict:
    """Return ``account`` with a valid ``access_token``, refreshing if needed.

    Args:
        ctx: The extension context (uses ``ctx.secrets``, ``ctx.http``,
            ``ctx.store``).
        account: The stored account dict. Must carry ``refresh_token``; should
            carry ``doc_id`` so the new token can be persisted.
        provider: Key into :data:`PROVIDER_TOKEN_URLS`.
        collection: Store collection holding the account doc. Omit to skip
            persistence (the refreshed token still comes back in the return).
        skew: Refresh this many seconds before stated expiry.
        force: Refresh even if the token still looks valid (used by the 401
            retry path, where the clock clearly lied).

    Returns:
        The same dict, updated in place and returned for convenience.

    Raises:
        TokenRefreshError: with ``reconnect_required=True`` when only a real
            reconnect can fix it.
    """
    account = account or {}
    if not force and not needs_refresh(account, skew=skew):
        return account

    token_url = PROVIDER_TOKEN_URLS.get(provider)
    if not token_url:
        raise TokenRefreshError(f"unknown oauth provider {provider!r}")

    refresh_token = account.get("refresh_token")
    if not refresh_token:
        raise TokenRefreshError(
            "This account has no refresh token stored, so its access cannot be "
            "renewed automatically -- reconnect the account once to grant "
            "offline access.",
            reconnect_required=True,
        )

    client_id = await ctx.secrets.get(f"{provider}_client_id")
    client_secret = await ctx.secrets.get(f"{provider}_client_secret")
    if not client_id or not client_secret:
        raise TokenRefreshError(
            f"{provider} OAuth credentials are not configured for this "
            f"extension ({provider}_client_id / {provider}_client_secret app "
            f"secrets are missing), so no token can be refreshed.",
        )

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        response = await ctx.http.post(token_url, data=data)
    except Exception as exc:  # noqa: BLE001 - network faults are transient
        raise TokenRefreshError(f"could not reach the {provider} token endpoint: {exc}") from exc

    status = int(getattr(response, "status_code", 0) or 0)
    body: Any = {}
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 - non-JSON error bodies exist
        body = {}

    if status != 200:
        error = ""
        if isinstance(body, dict):
            error = str(body.get("error") or "")
        # invalid_grant is the provider saying the grant is dead: revoked,
        # password changed, or expired through disuse. No retry will help.
        raise TokenRefreshError(
            f"{provider} refused to refresh this account's access "
            f"(HTTP {status}{': ' + error if error else ''}).",
            reconnect_required=(error == "invalid_grant" or status in (400, 401)),
            status_code=status,
        )

    if not isinstance(body, dict) or not body.get("access_token"):
        raise TokenRefreshError(f"{provider} returned no access token on refresh.")

    account["access_token"] = body["access_token"]
    try:
        lifetime = int(body.get("expires_in") or 3600)
    except (TypeError, ValueError):
        lifetime = 3600
    account["expires_at"] = int(time.time()) + lifetime
    # Rotation: providers may hand back a NEW refresh token and retire the old
    # one. Replaying a retired token is a slow-motion forced reconnect.
    rotated = body.get("refresh_token")
    if rotated and rotated != refresh_token:
        account["refresh_token"] = rotated

    await _persist(ctx, collection, account)
    return account


async def with_fresh_token(
    ctx,
    account: dict,
    call: Callable[[dict], Awaitable[Any]],
    *,
    provider: str = "google",
    collection: str = "",
    skew: int = DEFAULT_SKEW_SECONDS,
) -> Any:
    """Run ``call(account)`` with a valid token, retrying ONCE on a 401.

    ``call`` receives the (possibly refreshed) account dict and must return an
    HTTP response exposing ``status_code``. The proactive refresh handles the
    ordinary case; the single retry handles every case where the stored expiry
    was wrong -- clock skew, early revocation, a provider expiring a token
    sooner than it advertised. That retry is the difference between "it just
    works" and "please reconnect your account".

    A refresh that raises with ``reconnect_required`` propagates: the caller
    should surface it as a genuine reconnect prompt, which by then it truly is.
    """
    try:
        account = await fresh_token(ctx, account, provider=provider,
                                    collection=collection, skew=skew)
    except TokenRefreshError as exc:
        # A TERMINAL failure kills the stored token too: when Google says
        # ``invalid_grant`` the user revoked the grant, and the access token
        # died with it. Attempting the call anyway would trade an honest
        # "reconnect" for a confusing downstream error -- or, worse, look like
        # success against a stale cache. Surface it.
        if exc.reconnect_required:
            raise
        # A TRANSIENT failure (network blip, provider 5xx) is different: the
        # token in hand is merely near expiry and usually has seconds left, and
        # a working answer now beats an error the user cannot act on.
        if not account.get("access_token"):
            raise

    response = await call(account)
    if int(getattr(response, "status_code", 0) or 0) != 401:
        return response

    # The clock said fine, the provider said no. Force a refresh and retry once.
    log.info("oauth: 401 despite a token believed valid -- forcing refresh (%s)", provider)
    account = await fresh_token(ctx, account, provider=provider,
                                collection=collection, skew=skew, force=True)
    return await call(account)
