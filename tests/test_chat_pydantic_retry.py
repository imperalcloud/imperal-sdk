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


class _MarkReadParams(BaseModel):
    """Mock Pydantic params model with message_id (an _ID_SHAPE_FIELDS member)."""
    message_id: str


class _GenericExceptionParams(BaseModel):
    """Mock Pydantic params model for the generic-exception test."""
    v: str


def _build_test_chat_ext(client) -> ChatExtension:
    """Build minimal ChatExtension with one Pydantic-typed function."""
    ext = Extension("tasks-test", version="1.0.0")
    chat_ext = ChatExtension(ext=ext, tool_name="tasks", description="tasks ext", system_prompt="Test")

    async def _create_task(ctx, params: _CreateTaskParams):
        return ActionResult.success(
            data={"task_id": "tsk_42"},
            summary=f"Created '{params.title}' in {params.project_id}",
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


@pytest.fixture(autouse=False)
def allow_target_scope(monkeypatch):
    """Monkeypatch SDK-standalone _check_target_scope fallback to allow calls.

    Without this, the fallback returns allowed=False (correct production
    semantics when imperal_kernel is absent), blocking the integration test
    from exercising the retry path. Tests that pass this fixture flag the
    guard as a no-op for the duration of the test.
    """
    def _allow(**kwargs):
        return {
            "allowed": True,
            "reason": "test fixture override",
            "target_user_id": kwargs.get("user_id", ""),
            "required_scope": "",
            "force_confirmation": False,
            "cross_user": False,
            "verdict": "test_allow",
        }
    # Patch BOTH the source module AND the import site that chat/guards.py uses
    monkeypatch.setattr("imperal_sdk.runtime.executor._check_target_scope", _allow)
    monkeypatch.setattr("imperal_sdk.chat.guards._check_target_scope", _allow, raising=False)
    yield


@pytest.mark.asyncio
async def test_retry_succeeds_on_attempt_2(allow_target_scope):
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
async def test_retry_exhausted_returns_validation_error(caplog, allow_target_scope):
    """LLM emits invalid args twice. Exit with VALIDATION_MISSING_FIELD. SigNoz outcome=exhausted."""
    from imperal_sdk.chat.handler import handle_message

    client = _MockLLMClient([
        # Round 1: missing fields
        [_MockToolUseBlock(id="tu_1", name="create_task", input={"description": "x"})],
        # Retry attempt 1: still missing project_id
        [_MockToolUseBlock(id="tu_2", name="create_task", input={"title": "T", "description": "x"})],
        # Retry attempt 2: still missing project_id (retry_count reaches _RETRY_BUDGET=2)
        [_MockToolUseBlock(id="tu_3", name="create_task", input={"title": "T", "description": "x"})],
        # After exhausted path returns, kernel emits final text
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


# ---------------------------------------------------------------------------
# Task 5: gave_up + redundant + multi-tool_use cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_llm_gave_up_with_final_text(caplog, allow_target_scope):
    """LLM emits final text in retry round instead of tool_use → exit retry, fail row appended."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    client = _MockLLMClient([
        [_MockToolUseBlock(id="tu_1", name="create_task", input={"description": "x"})],
        # Retry round: only text, no tool_use
        [_MockTextBlock(text="Не смог собрать аргументы")],
        # Final text (caller doesn't reach this — but enqueue defensively)
        [_MockTextBlock(text="...")],
    ])
    ext = _build_test_chat_ext(client)
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        with caplog.at_level(logging.INFO, logger="imperal_sdk.chat.handler"):
            await handle_message(ext, ctx, "create task")
    finally:
        _llm_provider_mod.get_llm_provider = original

    assert len(ext._functions_called) == 1
    assert ext._functions_called[0]["success"] is False
    assert any("outcome=llm_gave_up" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_retry_redundant_args_logged(caplog, allow_target_scope):
    """LLM repeats byte-identical args in retry → log warning + count toward budget."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    client = _MockLLMClient([
        [_MockToolUseBlock(id="tu_1", name="create_task", input={"description": "x"})],
        # Retry: identical args (byte-identical input)
        [_MockToolUseBlock(id="tu_2", name="create_task", input={"description": "x"})],
        # Third attempt also identical to exhaust budget
        [_MockToolUseBlock(id="tu_3", name="create_task", input={"description": "x"})],
        [_MockTextBlock(text="...")],
    ])
    ext = _build_test_chat_ext(client)
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        with caplog.at_level(logging.WARNING, logger="imperal_sdk.chat.handler"):
            await handle_message(ext, ctx, "create task")
    finally:
        _llm_provider_mod.get_llm_provider = original

    assert any("outcome=redundant" in r.message for r in caplog.records)
    assert any("validation_retry_redundant" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_retry_switches_to_different_tool(allow_target_scope):
    """LLM emits tool_use with different name in retry round → exit retry as gave_up."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    client = _MockLLMClient([
        [_MockToolUseBlock(id="tu_1", name="create_task", input={"description": "x"})],
        # Retry round emits a DIFFERENT tool name → treated as gave_up
        [_MockToolUseBlock(id="tu_2", name="read_tasks", input={})],
        [_MockTextBlock(text="...")],
    ])
    ext = _build_test_chat_ext(client)
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        await handle_message(ext, ctx, "create task")
    finally:
        _llm_provider_mod.get_llm_provider = original

    # The create_task fc is appended (failure, gave_up); read_tasks isn't registered so wouldn't execute anyway
    assert len(ext._functions_called) == 1
    assert ext._functions_called[0]["name"] == "create_task"
    assert ext._functions_called[0]["success"] is False


@pytest.mark.asyncio
async def test_retry_multi_tool_use_takes_first_matching(allow_target_scope):
    """LLM emits multiple tool_use blocks in retry response — pick first matching same-name."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    client = _MockLLMClient([
        [_MockToolUseBlock(id="tu_1", name="create_task", input={"description": "x"})],
        # Retry: TWO tool_use blocks; first valid, second junk
        [
            _MockToolUseBlock(id="tu_2a", name="create_task",
                input={"title": "T", "project_id": "p"}),
            _MockToolUseBlock(id="tu_2b", name="something_else", input={}),
        ],
        [_MockTextBlock(text="ok")],
    ])
    ext = _build_test_chat_ext(client)
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        await handle_message(ext, ctx, "create task")
    finally:
        _llm_provider_mod.get_llm_provider = original

    # Retry succeeded with first matching block
    assert len(ext._functions_called) == 1
    assert ext._functions_called[0]["success"] is True
    assert ext._functions_called[0]["params"]["title"] == "T"


# ---------------------------------------------------------------------------
# Task 6: I-PYDANTIC-RETRY-SCOPE — non-Pydantic failures do not retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_kwargs_extension_no_retry(allow_target_scope):
    """Function without _pydantic_model → retry path dormant; PydanticValidationError never raised."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    client = _MockLLMClient([
        [_MockToolUseBlock(id="tu_1", name="legacy_fn", input={"x": 1})],
        [_MockTextBlock(text="done")],
    ])
    base_ext = Extension("legacy-test", version="1.0.0")
    ext = ChatExtension(ext=base_ext, tool_name="legacy", description="legacy ext", system_prompt="t")

    async def _legacy(ctx, **kwargs):
        return ActionResult.success(summary="ok", data=kwargs)
    ext.function("legacy_fn", action_type="read", description="legacy")(_legacy)

    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        await handle_message(ext, ctx, "do x")
    finally:
        _llm_provider_mod.get_llm_provider = original

    # Single fc, no retry. Only 2 LLM calls (tool_use + text), no retry call.
    assert client.call_count == 2
    assert len(ext._functions_called) == 1


@pytest.mark.asyncio
async def test_unknown_sub_function_does_not_retry(allow_target_scope):
    """LLM emits tu for an unregistered function → UNKNOWN_SUB_FUNCTION pre-guard, no retry."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    client = _MockLLMClient([
        [_MockToolUseBlock(id="tu_1", name="not_a_function", input={})],
        [_MockTextBlock(text="done")],
    ])
    ext = _build_test_chat_ext(client)  # registers create_task only
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        await handle_message(ext, ctx, "create task")
    finally:
        _llm_provider_mod.get_llm_provider = original

    # 2 LLM calls — no retry
    assert client.call_count == 2
    assert len(ext._functions_called) == 1
    assert ext._functions_called[0]["result"]["error_code"] == "UNKNOWN_SUB_FUNCTION"


@pytest.mark.asyncio
async def test_fabricated_id_first_attempt_does_not_retry(allow_target_scope):
    """I-AH-1 pre-guard rejects fabricated ID on first attempt — retry layer not entered."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    # Use a tool name that takes message_id (one of _ID_SHAPE_FIELDS)
    base_ext = Extension("mail-test", version="1.0.0")
    ext = ChatExtension(ext=base_ext, tool_name="mail", description="mail ext", system_prompt="t")

    async def _action(ctx, params: _MarkReadParams):
        return ActionResult.success(summary="ok")
    ext.function("mark_read", action_type="write", description="mark read")(_action)

    client = _MockLLMClient([
        # Fabricated slug pattern (matches _FABRICATED_SLUG_RE per check_id_shape_fabrication)
        [_MockToolUseBlock(id="tu_1", name="mark_read",
            input={"message_id": "webhostmost-outlook-1"})],
        [_MockTextBlock(text="done")],
    ])
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        await handle_message(ext, ctx, "mark first read")
    finally:
        _llm_provider_mod.get_llm_provider = original

    # I-AH-1 short-circuited; no retry; outer handler returns immediately on
    # intercepted=True (handler.py:743-744), so call_count==1 (not 2).
    assert client.call_count == 1
    assert len(ext._functions_called) == 1
    assert ext._functions_called[0]["result"]["error_code"] == "FABRICATED_ID_SHAPE"
    assert ext._functions_called[0]["intercepted"] is True


@pytest.mark.asyncio
async def test_fabricated_id_on_retry_input_blocks(caplog, allow_target_scope):
    """LLM fabricates ID in retry input → I-AH-1 re-check fires, retry exits with FABRICATED_ID_SHAPE."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    base_ext = Extension("mail-test", version="1.0.0")
    ext = ChatExtension(ext=base_ext, tool_name="mail", description="mail ext", system_prompt="t")

    async def _action(ctx, params: _MarkReadParams):
        return ActionResult.success(summary="ok")
    ext.function("mark_read", action_type="write", description="mark read")(_action)

    client = _MockLLMClient([
        # First: missing message_id → triggers Pydantic retry
        [_MockToolUseBlock(id="tu_1", name="mark_read", input={})],
        # Retry: fabricated slug
        [_MockToolUseBlock(id="tu_2", name="mark_read",
            input={"message_id": "webhostmost-outlook-1"})],
        [_MockTextBlock(text="done")],
    ])
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        with caplog.at_level(logging.WARNING, logger="imperal_sdk.chat.handler"):
            await handle_message(ext, ctx, "mark first read")
    finally:
        _llm_provider_mod.get_llm_provider = original

    assert len(ext._functions_called) == 1
    assert ext._functions_called[0]["result"]["error_code"] == "FABRICATED_ID_SHAPE"
    assert ext._functions_called[0]["intercepted"] is True
    # SigNoz outcome=fabricated_id_on_retry
    assert any("outcome=fabricated_id_on_retry" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_generic_exception_does_not_retry(allow_target_scope):
    """Function raises generic Exception → INTERNAL fc-append, retry layer not invoked."""
    from imperal_sdk.chat.handler import handle_message
    import imperal_sdk.runtime.llm_provider as _llm_provider_mod

    base_ext = Extension("x-test", version="1.0.0")
    ext = ChatExtension(ext=base_ext, tool_name="x", description="x ext", system_prompt="t")

    async def _action(ctx, params: _GenericExceptionParams):
        raise RuntimeError("boom")
    ext.function("do_x", action_type="read", description="x")(_action)

    client = _MockLLMClient([
        [_MockToolUseBlock(id="tu_1", name="do_x", input={"v": "1"})],
        [_MockTextBlock(text="done")],
    ])
    ctx = _build_test_ctx()
    original = _llm_provider_mod.get_llm_provider
    _llm_provider_mod.get_llm_provider = lambda: client
    try:
        await handle_message(ext, ctx, "do x")
    finally:
        _llm_provider_mod.get_llm_provider = original

    # No retry — exactly 2 LLM calls (tool_use + text response)
    assert client.call_count == 2
    assert len(ext._functions_called) == 1
    assert ext._functions_called[0]["result"]["error_code"] == "INTERNAL"
