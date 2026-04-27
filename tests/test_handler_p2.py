# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""P2 tasks 20 + 27 + 32 — chat/handler.py integrity hardening.

Task 20 — structured error_code in _execute_function
  * Unknown sub-function surfaces UNKNOWN_SUB_FUNCTION in content + result
  * Pydantic validation error surfaces VALIDATION_MISSING_FIELD + missing_fields
  * Any other exception surfaces INTERNAL + error_class; no raw str(e) text leaks
    into _functions_called result dict (the guard surface for Task 21).

Task 27 — emit_narration wire
  * EMIT_NARRATION_TOOL is appended to the tool list passed to create_message
  * A valid emit_narration tool_use terminates the loop and returns ChatResult
    carrying narration_emission
  * Malformed emit_narration input still returns prose with narration_emission
    set to None (parse fallback)

Task 32 — fresh-fetch tool_choice enforcement
  * Single fresh-fetch required → tool_choice={"type":"tool","name":X}
  * Multiple fresh-fetch required → falls back to tool_choice={"type":"any"}
  * Empty fresh-fetch list → standard behaviour unchanged
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from imperal_sdk.types.identity import UserContext
from imperal_sdk.chat.handler import _execute_function, handle_message
from imperal_sdk.chat.narration import EMIT_NARRATION_TOOL
from imperal_sdk.extension import Extension


class SendArgs(BaseModel):
    to: str
    body: str



# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class _NameSpace(SimpleNamespace):
    """SimpleNamespace that tolerates arbitrary attr assignment (default)."""
    pass


def _make_ctx(skeleton=None) -> _NameSpace:
    """Minimal Context stand-in good enough for handler internal paths."""
    from imperal_sdk.runtime.llm_provider import LLMConfig
    u = UserContext(imperal_id="u1", email="u@example.com", tenant_id="default", role="user")
    # Sprint 1.2: inject ctx._llm_configs to mirror kernel context_factory
    # behavior. Without this, handler.py falls back to
    # client._env_default_config_for_purpose() which doesn't exist on
    # the mock _NameSpace client.
    _exec_cfg = LLMConfig(provider="anthropic", model="claude-test", api_key="sk-test")
    ctx = _NameSpace(
        user=u,
        history=[],
        config=None,
        skeleton=skeleton,
        _intent_type="read",
        _llm_configs={"execution": _exec_cfg},
    )
    return ctx


def _make_tu(name: str, inp: dict | None = None, tu_id: str = "tu1"):
    return _NameSpace(name=name, input=inp or {}, id=tu_id, type="tool_use")


def _cfg() -> dict:
    return {
        "max_result_tokens": 3000,
        "list_truncate_items": 5,
        "string_truncate_chars": 500,
        "context_window": 20,
        "keep_recent": 6,
        "quality_ceiling": 50000,
    }


def _fake_text_response(text: str):
    """Build a minimal llm response object matching the attrs handler reads."""
    block = _NameSpace(type="text", text=text)
    return _NameSpace(content=[block])


def _fake_tool_use_response(tool_uses):
    """tool_uses is a list of (name, input, id) tuples."""
    blocks = [_NameSpace(type="tool_use", name=n, input=i, id=tid) for n, i, tid in tool_uses]
    return _NameSpace(content=blocks)


@pytest.fixture
def chat_ext_factory():
    """Factory producing (chat_ext, ext) pairs with per-test function registration."""

    def _factory():
        ext = Extension("test-app")
        from imperal_sdk.chat.extension import ChatExtension
        cx = ChatExtension(ext, tool_name="chat_tool", description="test")
        cx._functions_called = []
        return cx, ext

    return _factory


# ---------------------------------------------------------------------------
# Task 20 — structured errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_sub_function_surfaces_error_code(chat_ext_factory):
    cx, _ext = chat_ext_factory()
    ctx = _make_ctx()
    tu = _make_tu("nonexistent_fn", {"x": 1})

    content = await _execute_function(cx, ctx, tu, action_type="read", cfg=_cfg())
    parsed = json.loads(content)

    assert parsed["RESULT"] == "ERROR"
    assert parsed["error_code"] == "UNKNOWN_SUB_FUNCTION"
    # Available-list detail preserved for the LLM to self-correct
    assert "detail" in parsed
    assert "nonexistent_fn" in parsed["detail"]

    assert len(cx._functions_called) == 1
    last = cx._functions_called[-1]
    assert last["success"] is False
    assert last["result"] == {"error_code": "UNKNOWN_SUB_FUNCTION"}


@pytest.mark.asyncio
async def test_pydantic_validation_error_surfaces_VALIDATION_MISSING_FIELD(chat_ext_factory):
    cx, _ext = chat_ext_factory()
    ctx = _make_ctx()

    @cx.function("send", "Send a thing", action_type="write")
    async def send(ctx, args: SendArgs):  # noqa: ARG001
        return {"ok": True}

    tu = _make_tu("send", {})  # missing `to` and `body`
    content = await _execute_function(cx, ctx, tu, action_type="write", cfg=_cfg())
    parsed = json.loads(content)

    assert parsed["RESULT"] == "ERROR"
    assert parsed["error_code"] == "VALIDATION_MISSING_FIELD"
    assert set(parsed["missing_fields"]) == {"to", "body"}

    # Must be the error surface Task 21 bleed-guard reads
    last = cx._functions_called[-1]
    assert last["success"] is False
    assert last["result"]["error_code"] == "VALIDATION_MISSING_FIELD"
    assert set(last["result"]["missing_fields"]) == {"to", "body"}


@pytest.mark.asyncio
async def test_internal_error_surfaces_INTERNAL(chat_ext_factory):
    cx, _ext = chat_ext_factory()
    ctx = _make_ctx()

    @cx.function("boom", "Boom", action_type="read")
    async def boom(ctx):  # noqa: ARG001
        raise RuntimeError("totally private details: /root/secret/key.pem")

    tu = _make_tu("boom", {})
    content = await _execute_function(cx, ctx, tu, action_type="read", cfg=_cfg())
    parsed = json.loads(content)

    assert parsed["RESULT"] == "ERROR"
    assert parsed["error_code"] == "INTERNAL"
    assert parsed["error_class"] == "RuntimeError"
    # Critical: no str(e) text must leak — guard surface for Task 21
    assert "totally private details" not in content
    assert "secret" not in content.lower()

    last = cx._functions_called[-1]
    assert last["result"]["error_code"] == "INTERNAL"
    assert last["result"]["error_class"] == "RuntimeError"
    # No "error" raw-message key
    assert "error" not in last["result"] or last["result"].get("error") is None


# ---------------------------------------------------------------------------
# Task 27 — emit_narration wire
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emit_narration_tool_in_schema_passed_to_llm(chat_ext_factory):
    cx, _ext = chat_ext_factory()
    ctx = _make_ctx()

    @cx.function("ping", "Ping")
    async def ping(ctx):  # noqa: ARG001
        return {"ok": True}

    # Single round: LLM returns plain text → loop exits with no tool_use.
    spy = AsyncMock(return_value=_fake_text_response("hello"))
    fake_client = _NameSpace(create_message=spy)

    with patch("imperal_sdk.runtime.llm_provider.get_llm_provider", return_value=fake_client):
        await handle_message(cx, ctx, message="hi")

    assert spy.await_count >= 1
    kwargs = spy.await_args_list[0].kwargs
    tools = kwargs["tools"]
    names = [t["name"] for t in tools]
    assert "emit_narration" in names
    # EMIT_NARRATION_TOOL should be the exact shared schema, not a copy
    emit_entry = next(t for t in tools if t["name"] == "emit_narration")
    assert emit_entry["input_schema"] == EMIT_NARRATION_TOOL["input_schema"]


@pytest.mark.asyncio
async def test_emit_narration_tool_use_terminates_loop_returns_emission(chat_ext_factory):
    cx, _ext = chat_ext_factory()
    ctx = _make_ctx()

    @cx.function("ping", "Ping")
    async def ping(ctx):  # noqa: ARG001
        return {"ok": True}

    valid_emission = {
        "mode": "narrative",
        "prose": "All done.",
        "per_call_verdicts": [],
        "task_targets": {"expected": None, "succeeded": 0},
    }
    spy = AsyncMock(return_value=_fake_tool_use_response([("emit_narration", valid_emission, "tu-en")]))
    fake_client = _NameSpace(create_message=spy)

    with patch("imperal_sdk.runtime.llm_provider.get_llm_provider", return_value=fake_client):
        result = await handle_message(cx, ctx, message="hi")

    # Response text comes from the emission prose (with filter pipeline applied)
    assert "All done." in result["response"]
    # narration_emission surfaced on the ChatResult dict
    assert result.get("_narration_emission") is not None
    em = result["_narration_emission"]
    assert em["mode"] == "narrative"
    assert em["prose"] == "All done."
    # Only ONE create_message call — emit_narration is terminal
    assert spy.await_count == 1


@pytest.mark.asyncio
async def test_malformed_emit_narration_still_returns_but_emission_none(chat_ext_factory):
    cx, _ext = chat_ext_factory()
    ctx = _make_ctx()

    @cx.function("ping", "Ping")
    async def ping(ctx):  # noqa: ARG001
        return {"ok": True}

    malformed = {
        # missing "mode" + "task_targets" — Pydantic will reject
        "prose": "fallback prose",
        "per_call_verdicts": [],
    }
    spy = AsyncMock(return_value=_fake_tool_use_response([("emit_narration", malformed, "tu-en")]))
    fake_client = _NameSpace(create_message=spy)

    with patch("imperal_sdk.runtime.llm_provider.get_llm_provider", return_value=fake_client):
        result = await handle_message(cx, ctx, message="hi")

    assert "fallback prose" in result["response"]
    assert result.get("_narration_emission") is None
    assert spy.await_count == 1


# ---------------------------------------------------------------------------
# Task 32 — fresh-fetch tool_choice enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fresh_fetch_single_required_forces_tool_choice_to_that_tool(chat_ext_factory):
    cx, _ext = chat_ext_factory()

    @cx.function("inbox", "List inbox")
    async def inbox(ctx):  # noqa: ARG001
        return {"items": []}

    ctx = _make_ctx(skeleton={"_fresh_fetch_required": ["inbox"]})
    # Plain text response so the loop exits after round 0
    spy = AsyncMock(return_value=_fake_text_response("ok"))
    fake_client = _NameSpace(create_message=spy)

    with patch("imperal_sdk.runtime.llm_provider.get_llm_provider", return_value=fake_client):
        await handle_message(cx, ctx, message="any new mail?")

    assert spy.await_count == 1
    kwargs = spy.await_args_list[0].kwargs
    assert kwargs.get("tool_choice") == {"type": "tool", "name": "inbox"}


@pytest.mark.asyncio
async def test_fresh_fetch_multi_required_falls_back_to_any(chat_ext_factory):
    cx, _ext = chat_ext_factory()

    @cx.function("inbox", "List inbox")
    async def inbox(ctx):  # noqa: ARG001
        return {"items": []}

    @cx.function("unread_count", "Count unread")
    async def unread_count(ctx):  # noqa: ARG001
        return {"count": 0}

    ctx = _make_ctx(skeleton={"_fresh_fetch_required": ["inbox", "unread_count"]})
    spy = AsyncMock(return_value=_fake_text_response("ok"))
    fake_client = _NameSpace(create_message=spy)

    with patch("imperal_sdk.runtime.llm_provider.get_llm_provider", return_value=fake_client):
        await handle_message(cx, ctx, message="status?")

    assert spy.await_count == 1
    kwargs = spy.await_args_list[0].kwargs
    # Falls back to {"type": "any"} — multiple required can't be encoded in one tool_choice
    assert kwargs.get("tool_choice") == {"type": "any"}


@pytest.mark.asyncio
async def test_fresh_fetch_empty_unchanged(chat_ext_factory):
    cx, _ext = chat_ext_factory()

    @cx.function("ping", "Ping")
    async def ping(ctx):  # noqa: ARG001
        return {"ok": True}

    # No skeleton → no _fresh_fetch_required → standard round-0 path
    ctx = _make_ctx(skeleton=None)
    spy = AsyncMock(return_value=_fake_text_response("done"))
    fake_client = _NameSpace(create_message=spy)

    with patch("imperal_sdk.runtime.llm_provider.get_llm_provider", return_value=fake_client):
        await handle_message(cx, ctx, message="hello")

    kwargs = spy.await_args_list[0].kwargs
    # Standard behaviour: tool_choice="any" on round 0 when tools exist (pre-existing rule)
    assert kwargs.get("tool_choice") == {"type": "any"}
