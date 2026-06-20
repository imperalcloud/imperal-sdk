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


# ---------------------------------------------------------------------------
# conditional — control-flow verb (if/then/else at step root, NOT args)
# ---------------------------------------------------------------------------

def test_validate_conditional_real_shape_ok():
    """A real interpreter-shaped conditional step must validate clean."""
    step = {
        "id": "s2",
        "op": "conditional",
        "if": {"field": "{{steps.s1.count}}", "gt": 0},
        "then": "s3",
        "else": None,
    }
    assert validate_step(step) == []


def test_validate_conditional_else_string_ok():
    """conditional with else as a step-id string is valid."""
    step = {
        "id": "s2",
        "op": "conditional",
        "if": {"field": "{{steps.s1.count}}", "gt": 10},
        "then": "s3",
        "else": "s9",
    }
    assert validate_step(step) == []


def test_validate_conditional_missing_if():
    """conditional without an 'if' key must produce an error."""
    step = {"id": "s2", "op": "conditional", "then": "s3"}
    errors = validate_step(step)
    assert errors, "expected error: conditional requires 'if'"
    assert any("if" in e for e in errors)


def test_validate_conditional_then_not_string():
    """conditional with 'then' not a string must produce a type error."""
    step = {
        "id": "s2",
        "op": "conditional",
        "if": {"field": "{{steps.s1.count}}", "gt": 0},
        "then": ["s3"],  # should be a string step-id
    }
    errors = validate_step(step)
    assert errors, "expected error: 'then' must be a string step-id"
    assert any("then" in e for e in errors)


def test_validate_conditional_missing_then():
    """conditional without a 'then' key must produce an error."""
    step = {
        "id": "s2",
        "op": "conditional",
        "if": {"field": "{{steps.s1.count}}", "gt": 0},
    }
    errors = validate_step(step)
    assert errors, "expected error: conditional requires 'then'"
    assert any("then" in e for e in errors)
