# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""P2 Task 19/20 federal-chat-integrity — ``check_write_arg_bleed``.

Defence-in-depth belt-and-suspenders: reject write/destructive calls whose
args echo an ERROR_TAXONOMY code after a prior tool call recorded an
error_code. Belongs to the P2 federal-chat-integrity track, not Phase 4.

Spec: docs/superpowers/specs/2026-04-23-federal-grade-chat-integrity-design.md
Invariant: I-WRITE-ARG-NO-BLEED
"""
from __future__ import annotations

from unittest.mock import MagicMock

from imperal_sdk.chat.guards import check_write_arg_bleed


# ---------------------------------------------------------------------------
# Action-type gating — read args can echo error codes freely
# ---------------------------------------------------------------------------


def test_bleed_skips_read_action():
    tu = MagicMock()
    tu.input = {"error_code": "UNKNOWN_TOOL"}
    assert check_write_arg_bleed(tu, [], "read") is None


def test_bleed_skips_when_no_prior_errors():
    tu = MagicMock()
    tu.input = {"body": "hello"}
    prior = [{"success": True, "result": {"ok": 1}}]
    assert check_write_arg_bleed(tu, prior, "write") is None


# ---------------------------------------------------------------------------
# Block cases
# ---------------------------------------------------------------------------


def test_bleed_blocks_on_taxonomy_match_exact_case():
    tu = MagicMock()
    tu.input = {"body": "VALIDATION_MISSING_FIELD happened"}
    prior = [
        {"success": False, "result": {"error_code": "VALIDATION_MISSING_FIELD"}}
    ]
    reason = check_write_arg_bleed(tu, prior, "write")
    assert reason is not None
    assert "WRITE_ARG_BLEED" in reason


def test_bleed_blocks_case_insensitive():
    """LLMs rephrase casing but preserve letter order."""
    tu = MagicMock()
    tu.input = {"body": "oh no validation_missing_field happened"}
    prior = [
        {"success": False, "result": {"error_code": "VALIDATION_MISSING_FIELD"}}
    ]
    assert check_write_arg_bleed(tu, prior, "write") is not None


def test_bleed_blocks_on_destructive_action():
    tu = MagicMock()
    tu.input = {"body": "PERMISSION_DENIED leaked"}
    prior = [{"success": False, "result": {"error_code": "UNKNOWN_TOOL"}}]
    assert check_write_arg_bleed(tu, prior, "destructive") is not None


def test_bleed_scans_nested_structures():
    """JSON serialisation must flatten dict/list values."""
    tu = MagicMock()
    tu.input = {
        "payload": {
            "nested": ["one", {"deeper": "BACKEND_TIMEOUT string"}],
        }
    }
    prior = [{"success": False, "result": {"error_code": "UNKNOWN_TOOL"}}]
    assert check_write_arg_bleed(tu, prior, "write") is not None


# ---------------------------------------------------------------------------
# Defensive fallback — un-serialisable args must not raise
# ---------------------------------------------------------------------------


class _Unserialisable:
    def __repr__(self):
        return "plain-safe-repr"


def test_bleed_handles_unserialisable_safely():
    """We allow (return None) rather than crash on exotic payloads — better
    UX than a DoS on legitimate calls from buggy extensions."""
    tu = MagicMock()
    # default=str in the json.dumps call should make this serialise fine,
    # so no bleed-match and no raise — test ensures no exception.
    tu.input = {"x": _Unserialisable()}
    prior = [{"success": False, "result": {"error_code": "UNKNOWN_TOOL"}}]
    assert check_write_arg_bleed(tu, prior, "write") is None


def test_bleed_skips_when_prior_error_has_no_error_code():
    """A failed prior call without an ``error_code`` field is treated as
    'no prior error' — nothing to bleed."""
    tu = MagicMock()
    tu.input = {"body": "VALIDATION_MISSING_FIELD"}
    prior = [{"success": False, "result": {"detail": "oops"}}]
    assert check_write_arg_bleed(tu, prior, "write") is None
