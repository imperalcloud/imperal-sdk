# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for imperal_sdk.chat.narration_guard (v1.5.24).

Covers:
- STRICT_NARRATION_POSTAMBLE is a non-empty format string with the
  ``{functions_called_summary}`` slot.
- ``format_functions_called_summary`` renders SUCCESS / ERROR / empty
  cases correctly.
- ``augment_system_with_narration_rule`` appends the postamble to the
  original prompt and substitutes the summary.

Invariants under test: I-NARRATION-STRICT-1, I-NARRATION-STRICT-2.
"""
from __future__ import annotations

import pytest

from imperal_sdk.chat.narration_guard import (
    STRICT_NARRATION_POSTAMBLE,
    augment_system_with_narration_rule,
    format_functions_called_summary,
)


# --------------------------------------------------------------------------- #
# STRICT_NARRATION_POSTAMBLE — shape                                          #
# --------------------------------------------------------------------------- #


class TestPostambleShape:
    def test_postamble_is_non_empty(self):
        assert isinstance(STRICT_NARRATION_POSTAMBLE, str)
        assert len(STRICT_NARRATION_POSTAMBLE) > 100

    def test_postamble_has_format_slot(self):
        # Must contain the {functions_called_summary} placeholder so the
        # augmenter can substitute at runtime.
        assert "{functions_called_summary}" in STRICT_NARRATION_POSTAMBLE

    def test_postamble_mentions_federal_compliance(self):
        # Invariant I-NARRATION-STRICT-2: the rule language is frozen.
        # Any drift on these anchor phrases must re-pass review.
        assert "federal" in STRICT_NARRATION_POSTAMBLE.lower()
        assert "FUNCTIONS_CALLED" in STRICT_NARRATION_POSTAMBLE


# --------------------------------------------------------------------------- #
# format_functions_called_summary                                             #
# --------------------------------------------------------------------------- #


class TestFormatSummary:
    def test_empty_list_produces_no_operations_sentinel(self):
        assert format_functions_called_summary([]) == "(no operations were performed)"

    def test_none_produces_no_operations_sentinel(self):
        assert format_functions_called_summary(None) == "(no operations were performed)"

    def test_single_success_without_detail(self):
        fc = [{"name": "mail.list", "success": True, "intercepted": False, "result": None}]
        out = format_functions_called_summary(fc)
        assert "- mail.list — SUCCESS" in out
        assert "1 operation total: 1 succeeded, 0 failed" in out

    def test_success_with_summary_field(self):
        class _R:
            summary = "5 unread emails"
            data = None

        fc = [{
            "name": "mail.read_email", "success": True, "intercepted": False, "result": _R(),
        }]
        out = format_functions_called_summary(fc)
        assert "mail.read_email — SUCCESS: 5 unread emails" in out

    def test_error_with_error_field(self):
        class _R:
            error = "Message not found"
            summary = ""
            data = None

        fc = [{
            "name": "mail.read_email", "success": False, "intercepted": False, "result": _R(),
        }]
        out = format_functions_called_summary(fc)
        assert "mail.read_email — ERROR: Message not found" in out
        assert "0 succeeded, 1 failed" in out

    def test_error_without_result_falls_back_to_failed(self):
        fc = [{"name": "notes.delete", "success": False, "intercepted": False, "result": None}]
        out = format_functions_called_summary(fc)
        assert "notes.delete — ERROR: failed" in out

    def test_mixed_success_and_error(self):
        class _OK:
            summary = "id=abc"
            data = None

        class _ERR:
            error = "permission denied"
            summary = ""
            data = None

        fc = [
            {"name": "notes.create", "success": True, "intercepted": False, "result": _OK()},
            {"name": "mail.send",    "success": False, "intercepted": False, "result": _ERR()},
        ]
        out = format_functions_called_summary(fc)
        assert "notes.create — SUCCESS: id=abc" in out
        assert "mail.send — ERROR: permission denied" in out
        assert "2 operations total: 1 succeeded, 1 failed" in out

    def test_intercepted_confirmation_required(self):
        fc = [{"name": "mail.delete", "success": False, "intercepted": True, "result": None}]
        out = format_functions_called_summary(fc)
        assert "mail.delete — CONFIRM_REQUIRED" in out
        assert "awaiting confirmation" in out


# --------------------------------------------------------------------------- #
# augment_system_with_narration_rule                                          #
# --------------------------------------------------------------------------- #


class TestAugment:
    def test_postamble_appended_after_base_prompt(self):
        base = "You are a Notes extension assistant."
        fc = [{"name": "notes.list", "success": True, "intercepted": False, "result": None}]
        out = augment_system_with_narration_rule(base, fc)
        assert out.startswith(base)
        assert "STRICT NARRATION RULE" in out
        assert "FUNCTIONS_CALLED" in out
        assert "notes.list" in out

    def test_empty_fc_shows_no_operations_sentinel(self):
        out = augment_system_with_narration_rule("sys", [])
        assert "(no operations were performed)" in out

    def test_summary_substituted_into_slot(self):
        fc = [
            {"name": "mail.archive", "success": True,  "intercepted": False, "result": None},
            {"name": "mail.delete",  "success": False, "intercepted": False, "result": None},
        ]
        out = augment_system_with_narration_rule("", fc)
        # The raw literal "{functions_called_summary}" MUST be gone
        # (proof that .format() ran), and the summary must be present.
        assert "{functions_called_summary}" not in out
        assert "- mail.archive — SUCCESS" in out
        assert "- mail.delete — ERROR" in out

    def test_works_with_empty_system_prompt(self):
        out = augment_system_with_narration_rule("", [])
        assert "STRICT NARRATION RULE" in out

    def test_works_with_none_functions_called(self):
        out = augment_system_with_narration_rule("sys", None)
        assert "(no operations were performed)" in out

    def test_newline_normalization_preserves_separation(self):
        # Prompt without trailing newline — augmenter adds one.
        out = augment_system_with_narration_rule("base", [])
        # Always at least one blank line between base and postamble so LLMs
        # treat the postamble as a distinct section.
        assert "base\n\n---" in out
