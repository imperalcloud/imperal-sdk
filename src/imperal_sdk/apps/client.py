# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""``ctx.apps`` — installed apps, their settings, and marketplace moderation.

Two extensions were hand-rolling this family: admin (moderation queue,
approve/reject, per-app user lists) and developer (the app record a
developer owns). They spelled the same routes differently, and the moderation
verbs — the ones with real consequences — were the least consistent of all.

WHAT BELONGS HERE. The app as a platform object: its settings blob, who can
reach it, and the moderation lifecycle that decides whether it is visible at
all. Calling *into* another app is ``ctx.extensions.call``; that is a
different thing and stays where it is.

MODERATION IS NAMED, NOT ENCODED. ``approve()`` and ``reject()`` are separate
methods rather than ``set_status("approved")``, because a reader of the call
site should see which one happened without knowing the status vocabulary —
and because rejecting takes a reason that approving does not.
"""
from __future__ import annotations

from typing import Any

from imperal_sdk._gateway import GatewayClient, require
from imperal_sdk.errors import NotFoundError


class AppsClient(GatewayClient):
    """App settings, app membership, and the moderation lifecycle."""

    # -- settings --------------------------------------------------------

    async def get_settings(self, app_id: str) -> dict:
        """The app's settings, unwrapped.

        App settings live in unified_config under the ``app`` scope, not on a
        route of their own: the gateway serves them from
        ``/v1/internal/config/app/{app_id}``. The response is an envelope
        (scope, scope_id, tenant_id, config, enforced, role_defaults); callers
        want the ``config`` blob, so unwrapping happens once here rather than
        at every call site.

        Returns ``{}`` when the app has no config row yet — a first-run app is
        a normal state, not a failure, and the gateway signals it with 404.
        """
        app_id = require(app_id, "app_id")
        try:
            envelope = await self._call(
                "GET", f"/v1/internal/config/app/{app_id}",
                resource="app settings")
        except NotFoundError:
            return {}
        return (envelope or {}).get("config", {}) if isinstance(envelope, dict) else {}

    async def update_settings(self, app_id: str, patch: dict,
                              *, updated_by: str | None = None,
                              replace_paths: list[str] | None = None) -> dict:
        """Deep-merge a patch into the app's settings.

        The route is an upsert with deep merge, so a patch touching one key
        leaves its siblings alone — which is what "patch" should mean and why
        the raw dict must be wrapped in ``{"config": ...}`` rather than sent
        bare. Sending it bare silently wrote nothing.

        ``replace_paths`` opts specific dotted subtrees out of the merge and
        replaces them wholesale — needed when the writer is authoritative and
        must prune keys it omits (a removed panel slot being the case the
        platform hit).
        """
        app_id = require(app_id, "app_id")
        if not isinstance(patch, dict) or not patch:
            raise ValueError("patch must be a non-empty dict")
        body: dict[str, Any] = {"config": patch}
        if updated_by:
            body["updated_by"] = updated_by
        if replace_paths:
            body["replace_paths"] = replace_paths
        return await self._call("PUT", f"/v1/internal/config/app/{app_id}",
                                json=body, resource="app settings")

    # -- membership ------------------------------------------------------

    async def users(self, app_id: str) -> dict:
        """Users who have access to this app."""
        app_id = require(app_id, "app_id")
        return await self._call("GET", f"/v1/extensions/{app_id}/users",
                                resource="app users")

    # -- moderation ------------------------------------------------------

    async def list_all(self) -> dict:
        """Every app known to the platform (moderation view)."""
        return await self._call("GET", "/v1/admin/apps", resource="apps")

    async def list_pending(self) -> dict:
        """Apps waiting on a moderation decision."""
        return await self._call("GET", "/v1/admin/apps/pending",
                                resource="pending apps")

    async def approve(self, app_id: str) -> dict:
        """Publish an app to the marketplace."""
        app_id = require(app_id, "app_id")
        return await self._call("POST", f"/v1/admin/apps/{app_id}/approve",
                                json={}, resource="app")

    async def reject(self, app_id: str, reason: str) -> dict:
        """Refuse an app, with a reason the developer will read.

        The reason is required on purpose: a rejection without one is a dead
        end for the person on the other side of it.
        """
        app_id = require(app_id, "app_id")
        if not reason or not reason.strip():
            raise ValueError("reject() requires a reason")
        return await self._call("POST", f"/v1/admin/apps/{app_id}/reject",
                                json={"reason": reason}, resource="app")

    async def set_status(self, app_id: str, status: str) -> dict:
        """Set an app's status directly.

        The general form behind ``approve``/``reject``. Prefer the named
        methods; reach for this only for a status they do not cover.
        """
        app_id = require(app_id, "app_id")
        status = require(status, "status")
        return await self._call("POST", f"/v1/admin/apps/{app_id}/status",
                                json={"status": status}, resource="app")

    async def remove(self, app_id: str) -> dict:
        """Delete an app from the platform.

        Named ``remove`` rather than ``delete`` to keep it distinct from the
        soft lifecycle verbs above: this one does not come back.
        """
        app_id = require(app_id, "app_id")
        return await self._call("DELETE", f"/v1/admin/apps/{app_id}",
                                resource="app")
