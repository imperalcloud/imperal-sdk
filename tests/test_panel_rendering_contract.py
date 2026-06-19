# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Federal CI gate: PANEL_SLOT_RENDERING_STATUS keys must equal
ALLOWED_PANEL_SLOTS exactly.

Federal invariant ``I-PANEL-RENDERING-CONTRACT`` — when a contributor
adds a new slot to ``ALLOWED_PANEL_SLOTS`` they MUST also declare what
the frontend host does with it (``permanent`` / ``center-overlay`` /
``reserved``). Without this gate the v4.1.x class of bug recurs:
extensions decorate with the new slot, the SDK accepts it, but the
frontend silently drops it because no render path exists.
"""
from __future__ import annotations

from imperal_sdk.types.contributions import (
    ALLOWED_PANEL_SLOTS,
    PANEL_SLOT_RENDERING_STATUS,
)

VALID_RENDERING_VALUES = frozenset({"permanent", "center-overlay", "reserved"})


def test_rendering_status_keys_match_allowed_slots():
    """Every allowed slot has a declared rendering status — and vice versa."""
    status_keys = set(PANEL_SLOT_RENDERING_STATUS.keys())
    allowed = set(ALLOWED_PANEL_SLOTS)
    missing = allowed - status_keys
    extra = status_keys - allowed
    assert not missing, (
        f"I-PANEL-RENDERING-CONTRACT violated — slots in ALLOWED_PANEL_SLOTS "
        f"missing rendering status: {missing}"
    )
    assert not extra, (
        f"I-PANEL-RENDERING-CONTRACT violated — slots declared in "
        f"PANEL_SLOT_RENDERING_STATUS that are NOT in ALLOWED_PANEL_SLOTS: "
        f"{extra}"
    )


def test_rendering_status_values_are_valid():
    """Each value must be one of the three federal categories."""
    for slot, status in PANEL_SLOT_RENDERING_STATUS.items():
        assert status in VALID_RENDERING_VALUES, (
            f"slot {slot!r} has invalid rendering status {status!r}; "
            f"must be one of {sorted(VALID_RENDERING_VALUES)}"
        )


def test_at_least_one_permanent_slot_exists():
    """Sanity floor — without permanent slots, no extension can render."""
    permanent = [s for s, v in PANEL_SLOT_RENDERING_STATUS.items() if v == "permanent"]
    assert "left" in permanent, "left slot must be permanent"
    assert "right" in permanent, "right slot must be permanent"
