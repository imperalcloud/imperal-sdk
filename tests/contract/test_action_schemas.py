# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Contract tests: every declarative step verb has a JSON Schema + validate_step."""
from imperal_sdk.ir.actions import ACTION_SCHEMAS, validate_step


def test_every_verb_has_a_schema():
    for verb in (
        "call", "navigate", "send", "open",
        "store.get", "store.list", "store.create", "store.update", "store.delete",
        "ai.complete", "conditional",
    ):
        assert verb in ACTION_SCHEMAS, f"missing schema for verb {verb!r}"


def test_validate_step_rejects_unknown_op():
    errors = validate_step({"id": "s1", "op": "frobnicate", "args": {}})
    assert errors, "expected errors for unknown op"
    assert any("unknown op" in e or "frobnicate" in e for e in errors)


def test_validate_send_step_ok():
    assert validate_step({"id": "s1", "op": "send", "args": {"message": "hi"}}) == []


def test_validate_send_missing_message():
    errors = validate_step({"id": "s1", "op": "send", "args": {}})
    assert errors, "expected error: send requires 'message'"
