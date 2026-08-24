# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""One way to call the Auth Gateway from an SDK client.

WHY THIS EXISTS. Before 5.12.0 every namespace that needed a gateway route
re-implemented the same four steps: build the header set, open a client from
the shared pool, decide which failures are worth retrying, and turn a non-2xx
body into something a caller can act on. Store, notify, secrets and billing
each carry their own copy — and extensions that needed a route no namespace
covered wrote a fifth copy by hand, inside the extension.

That hand-rolled fifth copy is the actual problem: ten extensions in this
tree were assembling ``httpx`` calls against ``/v1/...`` because the SDK had
no client for the route. Every one of them re-invented header names, error
messages and retry behaviour, and every one of them drifts on the day the
gateway changes. The fix is not another copy — it is a base thin enough that
adding a namespace costs a few lines, so there is never a reason to reach
past the SDK again.

WHAT IT DELIBERATELY DOES NOT DO. No caching, no response models, no
per-route knowledge. Those belong to the namespace on top. This layer knows
exactly one thing: how to make one authenticated call and report the outcome
honestly.
"""
from __future__ import annotations

import logging
from typing import Any

from imperal_sdk._http_retry import retry_transient
from imperal_sdk._shared_http import shared_http
from imperal_sdk.errors import APIError, AuthError, NotFoundError

log = logging.getLogger("imperal_sdk.gateway")

# Long enough for the slowest legitimate gateway read (a full user listing),
# short enough that a wedged call surfaces inside one chat turn rather than
# hanging the whole workflow.
DEFAULT_TIMEOUT = 15.0


class GatewayClient:
    """Base for SDK namespaces that call Auth Gateway routes.

    Subclasses declare methods; they never touch httpx, headers or retries.

    The acting user matters as much as the token. A service token alone says
    *which app* is calling; ``X-Acting-User`` says *on whose behalf*. Routes
    that own per-user data refuse the first without the second rather than
    defaulting to somebody — which is exactly the behaviour to inherit, not
    to work around.
    """

    __slots__ = ("_gateway_url", "_service_token", "_user_id",
                 "_extension_id", "_tenant_id")

    def __init__(self, gateway_url: str, service_token: str = "",
                 user_id: str = "", extension_id: str = "",
                 tenant_id: str = "") -> None:
        self._gateway_url = (gateway_url or "").rstrip("/")
        self._service_token = service_token or ""
        self._user_id = user_id or ""
        self._extension_id = extension_id or ""
        self._tenant_id = tenant_id or ""

    # -- re-scoping -----------------------------------------------------

    def for_user(self, user_id: str):
        """A copy of this client acting for a different user.

        Mirrors ``StoreClient.for_user`` / ``NotifyClient.for_user`` so every
        per-user namespace re-scopes the same way. Returns the concrete
        subclass, not the base, so chained calls keep their real type.
        """
        if not user_id:
            raise ValueError("for_user() needs a non-empty user_id")
        clone = self.__class__.__new__(self.__class__)
        GatewayClient.__init__(
            clone, self._gateway_url, self._service_token, user_id,
            self._extension_id, self._tenant_id,
        )
        return clone

    @property
    def user_id(self) -> str:
        """The user this client is acting for."""
        return self._user_id

    # -- the one call ---------------------------------------------------

    def _headers(self) -> dict:
        h = {"X-Service-Token": self._service_token}
        # Only send what we actually know. An empty X-Acting-User is worse
        # than none: it looks like an answered question.
        if self._user_id:
            h["X-Acting-User"] = self._user_id
        if self._extension_id:
            h["X-Extension-ID"] = self._extension_id
        if self._tenant_id:
            h["X-Tenant-ID"] = self._tenant_id
        return h

    async def _call(self, method: str, path: str, *,
                    params: dict | None = None,
                    json: dict | list | None = None,
                    timeout: float = DEFAULT_TIMEOUT,
                    resource: str = "") -> Any:
        """One authenticated gateway call. Returns parsed JSON.

        Raises :class:`NotFoundError` on 404, :class:`AuthError` on 401/403,
        :class:`APIError` on any other non-2xx. Transient transport failures
        are retried by the shared policy before any of that.
        """
        if not self._gateway_url:
            raise APIError(
                "No gateway URL available in this context — the SDK client "
                "was built without one (typically a mock context).", 0,
                "no_gateway")

        url = f"{self._gateway_url}{path}"
        op = f"{method} {path}"

        async def _once():
            async with shared_http(timeout=timeout) as client:
                return await client.request(
                    method, url, params=params, json=json,
                    headers=self._headers(),
                )

        resp = await retry_transient(_once, op=op)

        if resp.status_code == 404:
            raise NotFoundError(resource or path, str(params or json or ""))
        if resp.status_code in (401, 403):
            raise AuthError(_detail(resp) or f"Not permitted: {op}")
        if resp.status_code >= 400:
            raise APIError(_detail(resp) or f"{op} failed", resp.status_code)

        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}


def require(value: str, name: str) -> str:
    """Return ``value`` stripped, or raise if it is blank.

    WHY THIS IS NOT ``if not value``. A whitespace-only id is falsy to a
    human and truthy to Python: ``"   "`` sailed through the obvious guard
    and became ``/v1/conversations/   /messages``, a request the gateway can
    only reject in a confusing way. Every namespace validates the same way
    through here, and gets the stripped value back so the caller cannot
    accidentally interpolate the padded original.
    """
    text = (value or "").strip() if isinstance(value, str) else ""
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _detail(resp) -> str:
    """The gateway's own explanation, when it gave one."""
    try:
        body = resp.json()
    except Exception:
        return (resp.text or "")[:300]
    if isinstance(body, dict):
        d = body.get("detail") or body.get("message") or body.get("error")
        if d:
            return str(d)[:300]
    return str(body)[:300]
