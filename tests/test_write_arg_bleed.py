# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""P2 Task 21 — check_write_arg_bleed guard regression.

Invariant: I-WRITE-ARG-NO-BLEED.

Defence-in-depth on top of structured error codes (Task 19) and tool_result
hygiene (Task 20). Even if an LLM paraphrases an error_code into the body
of a subsequent write tool call, the pre-dispatch guard rejects.
"""
from types import SimpleNamespace


def _fc(name, success=True, error_code=None):
    """Helper: construct a _functions_called entry matching the shape
    appended inside handler._execute_function + guards.check_guards."""
    result = None
    if error_code:
        result = {"error_code": error_code, "hint": "x"}
    return {
        "name": name, "params": {}, "action_type": "read",
        "success": success, "intercepted": False,
        "event": "", "result": result,
    }


def _tu(name, inp):
    return SimpleNamespace(name=name, input=inp, id="tu1")


# ── Pass-through cases (allow) ──────────────────────────────────

def test_no_prior_errors_allows():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {"to": "a@b.c", "subject": "hi", "body": "hello"})
    fc = [_fc("inbox", success=True)]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    assert result is None


def test_empty_functions_called_allows():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {"to": "a@b.c", "body": "hi"})
    result = check_write_arg_bleed(tu, [], action_type="write")
    assert result is None


def test_read_action_always_allows():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("read_email", {"message_id": "UNKNOWN_TOOL"})
    fc = [_fc("list_emails", success=False, error_code="UNKNOWN_TOOL")]
    result = check_write_arg_bleed(tu, fc, action_type="read")
    assert result is None, "read actions not gated"


def test_allow_when_no_matching_error_code_substring():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    # Prior error was UNKNOWN_TOOL but body talks about normal mail business
    tu = _tu("send", {"to": "x@y", "body": "meeting tomorrow at 3pm"})
    fc = [_fc("inbox", success=False, error_code="UNKNOWN_TOOL")]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    assert result is None


def test_only_successful_calls_allows():
    """All prior calls succeeded → no error codes to bleed → allow."""
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {"to": "x@y", "body": "whatever"})
    fc = [_fc("fn_a", success=True), _fc("fn_b", success=True)]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    assert result is None


# ── Reject cases (bleed detected) ───────────────────────────────

def test_bleeds_error_code_into_body_rejected():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {
        "to": "support@x.com",
        "subject": "report",
        "body": "There was an UNKNOWN_TOOL situation, see attached",
    })
    fc = [_fc("create_note", success=False, error_code="UNKNOWN_TOOL")]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    assert result is not None, "must reject on error_code substring in body"
    assert "WRITE_ARG_BLEED" in result or "bleed" in result.lower()


def test_bleeds_case_insensitive():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {"to": "x@y", "body": "validation_missing_field for sure"})
    fc = [_fc("insert_row", success=False, error_code="VALIDATION_MISSING_FIELD")]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    assert result is not None, "case-insensitive match required"


def test_bleeds_nested_value():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {
        "to": "x@y",
        "attachments": [{"title": "Error: INTERNAL", "content": "trace"}],
    })
    fc = [_fc("mail", success=False, error_code="INTERNAL")]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    assert result is not None, "nested dict value must be scanned"


def test_destructive_action_gated_same_as_write():
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("delete_table", {"table": "RATE_LIMITED_backup"})
    fc = [_fc("prev_fn", success=False, error_code="RATE_LIMITED")]
    result = check_write_arg_bleed(tu, fc, action_type="destructive")
    assert result is not None


def test_bleeds_multiple_priors_match_first():
    """Two prior errors; any one being present in args triggers reject."""
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {"to": "x@y", "body": "the INTERNAL server problem"})
    fc = [
        _fc("fn_a", success=False, error_code="UNKNOWN_TOOL"),
        _fc("fn_b", success=False, error_code="INTERNAL"),
    ]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    assert result is not None


# ── Defensive / integration ─────────────────────────────────────

def test_malformed_result_does_not_crash():
    """A prior entry with result=<non-dict> must not raise."""
    from imperal_sdk.chat.guards import check_write_arg_bleed
    tu = _tu("send", {"body": "ok"})
    fc = [{
        "name": "x", "params": {}, "action_type": "read",
        "success": False, "intercepted": False,
        "event": "", "result": "some string error",
    }]
    result = check_write_arg_bleed(tu, fc, action_type="write")
    # No structured error_code dict → nothing to match → allow
    assert result is None


def test_guard_exported_from_check_guards_or_directly():
    """Integration: check_write_arg_bleed must be importable from the guards module."""
    from imperal_sdk.chat import guards
    assert hasattr(guards, "check_write_arg_bleed"), \
        "check_write_arg_bleed must be exported from imperal_sdk.chat.guards"
