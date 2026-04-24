# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Phase 4 spec-review fixes — ``chat/guards.py`` helpers.

Covers the I-CONNECTED-EMAILS-VIA-METADATA path: the target-scope guard
reads the connected-email list from ``ctx._metadata["connected_emails"]``
(kernel populates at dispatch time). Missing/malformed metadata must
fail SAFE to an empty list.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from imperal_sdk.chat.guards import _get_connected_emails


def test_connected_emails_read_from_metadata():
    ctx = MagicMock()
    ctx._metadata = {"connected_emails": ["a@x.com", "b@x.com"]}
    assert _get_connected_emails(ctx) == ["a@x.com", "b@x.com"]


def test_connected_emails_empty_fallback_when_missing_attr():
    # MagicMock(spec=[]) has no _metadata attr at all
    ctx = MagicMock(spec=[])
    assert _get_connected_emails(ctx) == []


def test_connected_emails_empty_when_metadata_has_no_key():
    ctx = MagicMock()
    ctx._metadata = {}
    assert _get_connected_emails(ctx) == []


def test_connected_emails_empty_when_metadata_is_none():
    ctx = MagicMock()
    ctx._metadata = None
    assert _get_connected_emails(ctx) == []


def test_connected_emails_empty_when_metadata_not_dict():
    """Defensive — if kernel hands us a non-dict for ``_metadata`` (bug),
    fail safe rather than raise at guard-time."""
    ctx = MagicMock()
    ctx._metadata = "definitely not a dict"
    assert _get_connected_emails(ctx) == []


def test_connected_emails_empty_when_value_not_list():
    ctx = MagicMock()
    ctx._metadata = {"connected_emails": "not-a-list@x.com"}
    assert _get_connected_emails(ctx) == []


def test_connected_emails_filters_non_string_entries():
    ctx = MagicMock()
    ctx._metadata = {
        "connected_emails": ["ok@x.com", None, 42, "", "also-ok@y.com"]
    }
    assert _get_connected_emails(ctx) == ["ok@x.com", "also-ok@y.com"]


def test_connected_emails_not_shared_state():
    """Two distinct ctx objects must not share their results. Sanity check
    that the helper returns a fresh list (no mutable default leakage)."""
    ctx1 = MagicMock()
    ctx1._metadata = {"connected_emails": ["a@x.com"]}
    ctx2 = MagicMock()
    ctx2._metadata = {"connected_emails": ["b@x.com"]}
    r1 = _get_connected_emails(ctx1)
    r2 = _get_connected_emails(ctx2)
    assert r1 == ["a@x.com"]
    assert r2 == ["b@x.com"]


# ---------------------------------------------------------------------------
# check_write_arg_bleed — smoke (belongs to separate P2 track but retained
# here because the guard lives in the same module)
# ---------------------------------------------------------------------------


def test_check_write_arg_bleed_skips_read_action():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = MagicMock()
    tu.input = {"error_code": "UNKNOWN_TOOL"}
    # Action is read → bleed guard must allow (return None)
    assert check_write_arg_bleed(tu, [], "read") is None


def test_check_write_arg_bleed_skips_when_no_prior_errors():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = MagicMock()
    tu.input = {"body": "hello"}
    # Prior calls all succeeded — nothing to bleed from
    prior = [{"success": True, "result": {"ok": 1}}]
    assert check_write_arg_bleed(tu, prior, "write") is None


def test_check_write_arg_bleed_blocks_on_taxonomy_match():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = MagicMock()
    tu.input = {"body": "oh no VALIDATION_MISSING_FIELD bubbled up"}
    prior = [
        {"success": False, "result": {"error_code": "VALIDATION_MISSING_FIELD"}}
    ]
    reason = check_write_arg_bleed(tu, prior, "write")
    assert reason is not None
    assert "WRITE_ARG_BLEED" in reason
