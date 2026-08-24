# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""``ctx.rbac`` — roles, scopes, and what a user may actually do.

Admin was the only extension reaching these routes, but it reached them
fourteen distinct ways, including three different spellings of the scope
listing query. Permission plumbing is the last place that should be
improvised per call site.

WHY ROLES AND SCOPES SHARE A NAMESPACE. They are one question asked from two
ends: a scope is a permission, a role is a bundle of them, and the answer
that matters — ``effective_scopes(user)`` — needs both. Splitting them into
``ctx.roles`` and ``ctx.scopes`` would put the interesting call in neither.

CASCADE IS EXPLICIT. Editing a role can rewrite permissions for everyone who
holds it. That is a real blast radius, so it is a named argument the caller
must pass deliberately rather than a default that quietly does the larger
thing.
"""
from __future__ import annotations

from typing import Any

from imperal_sdk._gateway import GatewayClient, require


class RBACClient(GatewayClient):
    """Roles, scopes, and effective permissions."""

    # -- roles -----------------------------------------------------------

    async def list_roles(self) -> dict:
        """Every role defined on the platform."""
        return await self._call("GET", "/v1/roles", resource="roles")

    async def create_role(self, **fields: Any) -> dict:
        """Define a new role."""
        if not fields:
            raise ValueError("create_role() needs at least one field")
        return await self._call("POST", "/v1/roles", json=fields,
                                resource="role")

    async def update_role(self, role_id: str, *, cascade: bool = False,
                          **fields: Any) -> dict:
        """Change a role.

        ``cascade=True`` re-applies the change to every user already holding
        the role. Off by default: the wider action should be the one you
        asked for, not the one you got.
        """
        role_id = require(role_id, "role_id")
        if not fields:
            raise ValueError("update_role() needs at least one field")
        return await self._call(
            "PATCH", f"/v1/roles/{role_id}",
            params={"cascade": cascade}, json=fields, resource="role")

    async def delete_role(self, role_id: str) -> dict:
        """Remove a role definition."""
        role_id = require(role_id, "role_id")
        return await self._call("DELETE", f"/v1/roles/{role_id}",
                                resource="role")

    # -- scopes ----------------------------------------------------------

    async def list_scopes(self, *, resource: str = "") -> dict:
        """Every scope, optionally narrowed to one resource."""
        params = {"resource": resource} if resource else None
        return await self._call("GET", "/v1/scopes", params=params,
                                resource="scopes")

    async def create_scope(self, **fields: Any) -> dict:
        """Define a new scope."""
        if not fields:
            raise ValueError("create_scope() needs at least one field")
        return await self._call("POST", "/v1/scopes", json=fields,
                                resource="scope")

    async def delete_scope(self, scope_id: str) -> dict:
        """Remove a scope definition."""
        scope_id = require(scope_id, "scope_id")
        return await self._call("DELETE", f"/v1/scopes/{scope_id}",
                                resource="scope")

    # -- the question that matters ---------------------------------------

    async def effective_scopes(self, user_id: str) -> dict:
        """What this user may actually do, after roles are resolved.

        The answer to "can they?" — not the role they hold, but the
        permissions that role adds up to. Ask this instead of reading a role
        name and inferring.
        """
        user_id = require(user_id, "user_id")
        return await self._call("GET", f"/v1/scopes/effective/{user_id}",
                                resource="effective scopes")
