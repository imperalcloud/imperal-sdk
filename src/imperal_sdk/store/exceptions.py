# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Exceptions raised by imperal_sdk.store."""
from __future__ import annotations


class StoreError(Exception):
    """Base for all store exceptions."""


class StoreUnavailable(StoreError):
    """Auth Gateway unreachable or overloaded.

    SDK-side callers should catch this and skip the tick (for scheduler
    fan-out) or back-off (for user-facing handlers).
    """
    def __init__(self, retry_after: int = 30):
        super().__init__(f"store unavailable (retry in {retry_after}s)")
        self.retry_after = retry_after


class StoreConflict(StoreError):
    """Compare-and-set failed: the document changed under you.

    Raised by ``ctx.store.update(..., if_match=doc.etag)`` (and ``delete``)
    when somebody else wrote to the document between your read and your write.
    This is the honest answer to a lost-update race: the write did NOT happen
    and nothing was overwritten.

    The recovery is always the same shape — re-read, re-apply your change to
    the fresh data, retry::

        for _ in range(3):
            doc = await ctx.store.get("carts", cart_id)
            try:
                return await ctx.store.update(
                    "carts", cart_id,
                    {"items": doc["items"] + [item]},
                    if_match=doc.etag,
                )
            except StoreConflict:
                continue          # somebody beat us; read again and retry

    ``current_etag`` carries the ETag the document has now, so a caller that
    already holds fresh data can retry without a second read.
    """

    def __init__(self, doc_id: str = "", expected_etag: str = "", current_etag: str = ""):
        super().__init__(
            f"document {doc_id or '?'} was modified by someone else "
            f"(expected etag {expected_etag[:12] or '?'}...)"
        )
        self.doc_id = doc_id
        self.expected_etag = expected_etag
        self.current_etag = current_etag


class StoreContractError(StoreError):
    """Auth Gateway returned response violating shared Pydantic contract.

    Indicates SDK/Auth-GW schema drift — should be caught by I-SDK-GW-CONTRACT-1
    CI snapshot test before reaching production.
    """
