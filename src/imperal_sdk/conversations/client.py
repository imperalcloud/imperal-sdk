# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""``ctx.conversations`` — the Thoughts Room, from inside an extension.

The room holds every conversation a user has with Webbee, across panel,
Telegram and terminal. It is a first-class platform surface, so reaching it
should not require an extension to know a single URL — before this namespace
existed, the one app that needed it hand-rolled six ``httpx`` calls, and any
second app would have hand-rolled them again, differently.

ISOLATION IS STRUCTURAL. Every route here is owner-scoped by construction:
the gateway resolves the acting user from ``X-Acting-User`` and accepts no
user_id parameter at all. There is no shape of request that could ask for
somebody else's history — the isolation is not a check that could be
forgotten, it is the absence of a way to express the question.

WHY THE ROUTES ARE NOT JUST CRUD. Two stores must stay in step: the LIVE
chat record every surface is reading right now, and the per-thread archive.
``list`` mirrors the live thread before reading so counts are true;
``activate`` archives the current thread before switching; ``delete`` clears
the live record and opens a replacement when the deleted thread was the live
one. That logic lives in the gateway, once. This client asks for it — it
does not reimplement it.
"""
from __future__ import annotations

from typing import Any

from imperal_sdk._gateway import GatewayClient, require

_BASE = "/v1/conversations"


class ConversationsClient(GatewayClient):
    """Read and steer the acting user's own conversation threads."""

    async def list(self, *, limit: int = 50,
                   include_archived: bool = False) -> dict:
        """Threads for the acting user — pinned first, then newest.

        Returns the gateway payload: ``{"conversations": [...],
        "active_id": "..."}``. ``active_id`` is the thread every surface is
        reading at this moment; compare against it rather than guessing which
        row is live.

        The live thread is mirrored into the archive before the listing is
        built, so a conversation the user is typing in right now reports its
        real message count instead of the state it had when they last
        switched away.
        """
        return await self._call(
            "GET", _BASE,
            params={"limit": limit, "include_archived": include_archived},
            resource="conversations",
        )

    async def messages(self, conversation_id: str, *, limit: int = 50) -> dict:
        """Messages inside one thread, oldest-first.

        Each message carries the surface it was said on, so an answer can
        honestly say *where* something was discussed.
        """
        conversation_id = require(conversation_id, "conversation_id")
        return await self._call(
            "GET", f"{_BASE}/{conversation_id}/messages",
            params={"limit": limit}, resource="conversation",
        )

    async def create(self, *, title: str = "") -> dict:
        """Start a fresh thread and make it live.

        The previous thread is archived, not dropped. Leave ``title`` empty
        and the thread names itself from what is said in it.
        """
        return await self._call(
            "POST", _BASE, json={"title": title}, resource="conversation")

    async def activate(self, conversation_id: str) -> dict:
        """Make an existing thread the live one on every surface.

        The thread currently live is archived first, so switching never costs
        a conversation.
        """
        conversation_id = require(conversation_id, "conversation_id")
        return await self._call(
            "POST", f"{_BASE}/{conversation_id}/activate",
            resource="conversation")

    async def update(self, conversation_id: str, *,
                     title: str | None = None,
                     pinned: bool | None = None,
                     archived: bool | None = None) -> dict:
        """Change what a person is allowed to change by hand.

        Passing ``title`` marks the thread as human-named, which stops the
        automatic namer from ever overwriting it. Omitted fields are left
        untouched rather than reset — a partial edit must not silently
        unpin a thread.
        """
        conversation_id = require(conversation_id, "conversation_id")
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
            body["title_generated"] = False
        if pinned is not None:
            body["pinned"] = pinned
        if archived is not None:
            body["archived"] = archived
        if not body:
            raise ValueError(
                "update() needs at least one of title / pinned / archived")
        return await self._call(
            "PATCH", f"{_BASE}/{conversation_id}", json=body,
            resource="conversation")

    async def delete(self, conversation_id: str) -> dict:
        """Erase one thread for good.

        If it was the live thread, the gateway also clears the running chat
        record and opens a replacement — otherwise the user would keep
        talking into a conversation that no longer exists. The response says
        which case it was (``was_active``, ``new_active_id``), so a caller can
        report what actually happened instead of assuming.
        """
        conversation_id = require(conversation_id, "conversation_id")
        return await self._call(
            "DELETE", f"{_BASE}/{conversation_id}", resource="conversation")
