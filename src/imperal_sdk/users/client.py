# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""``ctx.users`` — platform user records, settings and surfaces.

The most hand-rolled family in the tree: four extensions were assembling
these calls themselves (admin, billing, automations, notifications), each
with its own spelling of the same routes. Admin alone had nineteen distinct
call sites. One drifting header or a renamed query parameter and they break
in four different ways on four different days.

WHAT BELONGS HERE. Reading and editing a *platform user*: the record, the
per-user settings blob, which surfaces they have connected, which apps they
can reach. Anything about money lives in ``ctx.billing``; anything about
roles and permissions lives in ``ctx.rbac``.

AUTHORITY, NOT CONVENIENCE. Most of these routes are administrative: they
act on *another* user and the gateway enforces that the caller is allowed
to. This client does not soften that — it passes the call through and lets
the gateway's answer stand. A client that guessed at permissions locally
would be both wrong and unsafe.
"""
from __future__ import annotations

from typing import Any

from imperal_sdk._gateway import GatewayClient, require


class UsersClient(GatewayClient):
    """Platform user records, their settings, and their connected surfaces."""

    # -- the record -----------------------------------------------------

    async def list(self, *, search: str = "",
                   include_inactive: bool = False) -> dict:
        """Users on the platform, optionally filtered.

        ``search`` matches email (the gateway decides the exact predicate);
        ``include_inactive`` brings back deactivated accounts, which are
        hidden by default because most callers mean "people who can log in".
        """
        params: dict[str, Any] = {}
        if search:
            params["search"] = search
        if include_inactive:
            params["include_inactive"] = True
        return await self._call("GET", "/v1/users", params=params or None,
                                resource="users")

    async def get(self, user_id: str) -> dict:
        """One user record."""
        user_id = require(user_id, "user_id")
        return await self._call("GET", f"/v1/users/{user_id}",
                                resource="user")

    async def create(self, **fields: Any) -> dict:
        """Create a user. Fields are passed through to the gateway as given."""
        if not fields:
            raise ValueError("create() needs at least one field")
        return await self._call("POST", "/v1/users", json=fields,
                                resource="user")

    async def update(self, user_id: str, **fields: Any) -> dict:
        """Patch a user record — only the fields you pass.

        Omitted fields are left alone rather than reset, so a caller changing
        one thing cannot silently blank another.
        """
        user_id = require(user_id, "user_id")
        if not fields:
            raise ValueError("update() needs at least one field")
        return await self._call("PATCH", f"/v1/users/{user_id}", json=fields,
                                resource="user")

    async def set_active(self, user_id: str, active: bool) -> dict:
        """Deactivate or reactivate an account.

        A named method rather than ``update(is_active=...)`` because this is
        the single most consequential field on the record, and a reader of
        the call site should not have to know that.
        """
        return await self.update(user_id, is_active=active)

    async def delete(self, user_id: str, *, permanent: bool = False) -> dict:
        """Remove a user.

        ``permanent=False`` (the default) is the reversible path the platform
        treats as deactivation-with-cleanup. ``permanent=True`` is not
        recoverable — it is spelled out at the call site on purpose, so a
        permanent delete can never be the accidental default.
        """
        user_id = require(user_id, "user_id")
        params = {"permanent": True} if permanent else None
        return await self._call("DELETE", f"/v1/users/{user_id}",
                                params=params, resource="user")

    # -- what the user has ----------------------------------------------

    async def extensions(self, user_id: str) -> dict:
        """Apps this user can reach, with access and enabled state."""
        user_id = require(user_id, "user_id")
        return await self._call("GET", f"/v1/users/{user_id}/extensions",
                                resource="user extensions")

    async def surfaces(self, user_id: str) -> dict:
        """Surfaces the user has connected — panel, telegram, email, ...

        Worth checking before promising delivery somewhere: routing a
        notification to a surface the user never linked is a silent no-op.
        """
        user_id = require(user_id, "user_id")
        return await self._call("GET", f"/v1/internal/surfaces/{user_id}",
                                resource="user surfaces")

    # -- settings --------------------------------------------------------

    async def get_settings(self, user_id: str, *, tenant_id: str = "") -> dict:
        """The user's settings blob."""
        user_id = require(user_id, "user_id")
        params = {"tenant_id": tenant_id} if tenant_id else None
        return await self._call("GET", f"/v1/internal/users/{user_id}/settings",
                                params=params, resource="user settings")

    async def update_settings(self, user_id: str, patch: dict) -> dict:
        """Merge a patch into the user's settings blob."""
        user_id = require(user_id, "user_id")
        if not isinstance(patch, dict) or not patch:
            raise ValueError("patch must be a non-empty dict")
        return await self._call(
            "PATCH", f"/v1/internal/users/{user_id}/settings", json=patch,
            resource="user settings")

    # -- conversation ----------------------------------------------------

    async def reset_conversation(self, user_id: str) -> dict:
        """Clear the user's live chat record and open a fresh thread.

        Distinct from ``ctx.conversations.delete``: this drops the *running*
        record without erasing archived threads. Used when a conversation is
        wedged rather than unwanted.
        """
        user_id = require(user_id, "user_id")
        return await self._call(
            "POST", f"/v1/users/{user_id}/reset-conversation", json={},
            resource="user conversation")
