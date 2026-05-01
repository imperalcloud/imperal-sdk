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


# ---------------------------------------------------------------------------
# Task 3+: Integration test scaffolding (mock LLM + ChatExtension setup)
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Any, Sequence

from imperal_sdk.chat.extension import ChatExtension
from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk.extension import Extension
from imperal_sdk.testing.mock_context import MockContext


@dataclass
class _MockToolUseBlock:
    """Mimics Anthropic SDK's tool_use content block."""
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class _MockTextBlock:
    text: str
    type: str = "text"


@dataclass
class _MockUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class _MockResponse:
    content: list = field(default_factory=list)
    usage: _MockUsage = field(default_factory=_MockUsage)


class _MockLLMClient:
    """Replays a queue of canned responses on each create_message call.

    Each queued item is either a list of content blocks (will be wrapped in
    _MockResponse), a _MockResponse, or an Exception to raise.
    """
    def __init__(self, responses: Sequence[Any]):
        self._queue = list(responses)
        self.call_count = 0
        self.calls = []

    async def create_message(self, **kwargs):
        self.call_count += 1
        self.calls.append(kwargs)
        if not self._queue:
            raise AssertionError("MockLLMClient: queue exhausted")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, _MockResponse):
            return item
        return _MockResponse(content=list(item))

    def _env_default_config_for_purpose(self, purpose: str):  # parity with real client
        from types import SimpleNamespace
        return SimpleNamespace(
            provider="anthropic", model="claude-sonnet-4-6",
            max_tokens=2048, is_byollm=False,
            api_kwargs=lambda: {},
        )


class _CreateTaskParams(BaseModel):
    """Mock Pydantic params model for tests."""
    title: str
    project_id: str
    description: str = ""


def _build_test_chat_ext(client) -> ChatExtension:
    """Build minimal ChatExtension with one Pydantic-typed function."""
    ext = Extension("tasks-test", version="1.0.0")
    chat_ext = ChatExtension(ext=ext, tool_name="tasks", description="tasks ext", system_prompt="Test")

    async def _create_task(ctx, params: _CreateTaskParams):
        return ActionResult.ok(
            summary=f"Created '{params.title}' in {params.project_id}",
            data={"task_id": "tsk_42"},
        )

    # Wire @chat.function manually using internal hooks
    chat_ext.function(
        "create_task",
        action_type="write",
        description="Create a task with title and project_id",
    )(_create_task)

    return chat_ext


def _build_test_ctx() -> Any:
    return MockContext(user_id="imp_u_test")


@pytest.mark.asyncio
async def test_retry_succeeds_on_attempt_2():
    """LLM emits invalid args first, valid after prose feedback. fc append happens once with success=True."""
    from imperal_sdk.chat.handler import handle_message

    client = _MockLLMClient([
        # Round 1: emit tool_use missing title and project_id
        [_MockToolUseBlock(id="tu_1", name="create_task", input={"description": "Продлить SSL"})],
        # Retry round (inside _execute_function): emit valid args
        [_MockToolUseBlock(id="tu_2", name="create_task",
            input={"title": "Продление SSL", "project_id": "default", "description": "Продлить SSL"})],
        # Final round: text response after success
        [_MockTextBlock(text="✅ Создал задачу 'Продление SSL'")],
    ])
    ext = _build_test_chat_ext(client)
    ctx = _build_test_ctx()

    # Inject the mock client by monkey-patching get_llm_provider
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        result = await handle_message(ext, ctx, "создай задачу про продление SSL")
    finally:
        _llm_provider_mod.get_llm_provider = original

    # 3 LLM calls: round 1 tool_use + retry + final text
    assert client.call_count == 3, f"expected 3 LLM calls, got {client.call_count}"

    # Exactly one fc entry, success=True
    assert len(ext._functions_called) == 1
    fc = ext._functions_called[0]
    assert fc["name"] == "create_task"
    assert fc["success"] is True
    # The successful fc should record the SECOND attempt's params (retry input)
    assert fc["params"]["title"] == "Продление SSL"
    assert fc["params"]["project_id"] == "default"


@pytest.mark.asyncio
async def test_retry_exhausted_returns_validation_error(caplog):
    """LLM emits invalid args twice. Exit with VALIDATION_MISSING_FIELD. SigNoz outcome=exhausted."""
    from imperal_sdk.chat.handler import handle_message

    client = _MockLLMClient([
        # Round 1: missing fields
        [_MockToolUseBlock(id="tu_1", name="create_task", input={"description": "x"})],
        # Retry: still missing project_id
        [_MockToolUseBlock(id="tu_2", name="create_task", input={"title": "T", "description": "x"})],
        # No third tool_use — kernel sees exhausted, LLM emits final text
        [_MockTextBlock(text="Не смог собрать аргументы")],
    ])
    ext = _build_test_chat_ext(client)
    ctx = _build_test_ctx()

    import imperal_sdk.runtime.llm_provider as _llm_provider_mod
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        with caplog.at_level(logging.WARNING, logger="imperal_sdk.chat.handler"):
            await handle_message(ext, ctx, "создай задачу")
    finally:
        _llm_provider_mod.get_llm_provider = original

    assert len(ext._functions_called) == 1
    fc = ext._functions_called[0]
    assert fc["success"] is False
    assert fc["result"]["error_code"] == "VALIDATION_MISSING_FIELD"

    # SigNoz outcome=exhausted should be logged
    assert any(
        "validation_retry_outcome" in r.message and "outcome=exhausted" in r.message
        for r in caplog.records
    )
