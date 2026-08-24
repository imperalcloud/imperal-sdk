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


class AppsClient(GatewayClient):
    """App settings, app membership, and the moderation lifecycle."""

    # -- settings --------------------------------------------------------

    async def get_settings(self, app_id: str) -> dict:
        """The app's settings blob."""
        app_id = require(app_id, "app_id")
        return await self._call("GET", f"/v1/apps/{app_id}/settings",
                                resource="app settings")

    async def update_settings(self, app_id: str, patch: dict) -> dict:
        """Merge a patch into the app's settings blob."""
        app_id = require(app_id, "app_id")
        if not isinstance(patch, dict) or not patch:
            raise ValueError("patch must be a non-empty dict")
        return await self._call("PATCH", f"/v1/apps/{app_id}/settings",
                                json=patch, resource="app settings")

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
