"""Tests for Pydantic feedback loop in chat/handler.py.

Spec: docs/superpowers/specs/2026-05-02-pydantic-feedback-loop-design.md
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import pytest
from pydantic import BaseModel, ValidationError as PydanticValidationError

from imperal_sdk.chat.handler import format_pydantic_for_llm


def _build_validation_error(model_def: type[BaseModel], data: dict) -> PydanticValidationError:
    """Helper: trigger PydanticValidationError by validating bad data against a real model."""
    try:
        model_def.model_validate(data)
    except PydanticValidationError as e:
        return e
    raise AssertionError(f"Expected ValidationError but {model_def.__name__}.model_validate({data!r}) succeeded")


class _MissingFieldModel(BaseModel):
    title: str
    project_id: str


class _StringTypeModel(BaseModel):
    title: str


class _DatetimeModel(BaseModel):
    due_date: datetime


class _ExtraForbiddenModel(BaseModel):
    model_config = {"extra": "forbid"}
    title: str


class _ListTypeModel(BaseModel):
    tags: list[str]


class _IntModel(BaseModel):
    count: int


def test_format_missing_field_produces_required_message():
    e = _build_validation_error(_MissingFieldModel, {"description": "x"})
    out = format_pydantic_for_llm(e)
    assert "'title': required field is missing" in out
    assert "'project_id': required field is missing" in out
    assert out.startswith("Your previous tool call had invalid arguments. Fix these issues:")
    assert "Retry the tool call with corrected arguments." in out


def test_format_string_type_mismatch():
    e = _build_validation_error(_StringTypeModel, {"title": 42})
    out = format_pydantic_for_llm(e)
    assert "'title': expected string" in out


def test_format_datetime_parsing_includes_iso_hint():
    e = _build_validation_error(_DatetimeModel, {"due_date": "tomorrow"})
    out = format_pydantic_for_llm(e)
    assert "'due_date'" in out
    assert "ISO datetime" in out
    assert "'tomorrow'" in out


def test_format_extra_forbidden_says_remove_field():
    e = _build_validation_error(_ExtraForbiddenModel, {"title": "T", "foo": "bar"})
    out = format_pydantic_for_llm(e)
    assert "'foo'" in out
    assert "unknown field — remove it" in out


def test_format_list_type_mismatch():
    e = _build_validation_error(_ListTypeModel, {"tags": "not-a-list"})
    out = format_pydantic_for_llm(e)
    assert "'tags': expected list/array" in out


def test_format_int_type_mismatch():
    e = _build_validation_error(_IntModel, {"count": "many"})
    out = format_pydantic_for_llm(e)
    assert "'count': expected integer" in out


def test_format_multiple_errors_combined():
    e = _build_validation_error(_MissingFieldModel, {})
    out = format_pydantic_for_llm(e)
    assert "'title'" in out
    assert "'project_id'" in out
    assert out.count("required field is missing") == 2


def test_format_unknown_type_falls_back_to_pydantic_msg():
    """Spec T1.6: unknown Pydantic error type routes to fallback `else` branch using Pydantic's msg."""
    from pydantic import field_validator

    class _CustomModel(BaseModel):
        value: str

        @field_validator("value")
        @classmethod
        def check_value(cls, v: str) -> str:
            if v == "bad":
                raise ValueError("custom business rule violated")
            return v

    e = _build_validation_error(_CustomModel, {"value": "bad"})
    out = format_pydantic_for_llm(e)
    # The fallback branch produces "- '<loc>': <msg>" using Pydantic's msg verbatim
    assert "'value'" in out
    assert "custom business rule violated" in out


# ---------------------------------------------------------------------------
# Task 2: SigNoz log emission helper
# ---------------------------------------------------------------------------

from imperal_sdk.chat.handler import _emit_retry_outcome


def test_emit_retry_outcome_logs_structured_line(caplog):
    with caplog.at_level(logging.INFO, logger="imperal_sdk.chat.handler"):
        _emit_retry_outcome(tool="create_task", ext="tasks", outcome="success", retry_count=1)
    assert any(
        "validation_retry_outcome" in r.message
        and "tool=create_task" in r.message
        and "ext=tasks" in r.message
        and "outcome=success" in r.message
        and "retry_count=1" in r.message
        for r in caplog.records
    )


def test_emit_retry_outcome_uses_warning_for_exhausted(caplog):
    with caplog.at_level(logging.WARNING, logger="imperal_sdk.chat.handler"):
        _emit_retry_outcome(tool="create_task", ext="tasks", outcome="exhausted", retry_count=2)
    matching = [r for r in caplog.records if "outcome=exhausted" in r.message]
    assert matching, "expected at least one WARNING-level record"
    assert matching[0].levelname == "WARNING"


def test_emit_retry_outcome_security_outcome_is_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="imperal_sdk.chat.handler"):
        _emit_retry_outcome(tool="send_mail", ext="mail", outcome="fabricated_id_on_retry", retry_count=1)
    matching = [r for r in caplog.records if "fabricated_id_on_retry" in r.message]
    assert matching
    assert matching[0].levelname == "WARNING"
