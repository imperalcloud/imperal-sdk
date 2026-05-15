"""Component D — @chat.function(background=True, long_running=True) decorator flag.

Sugar over ctx.background_task(coro) — the kernel auto-wraps the handler call
in ctx.background_task() under the hood; author writes one handler body, no
explicit inner coro wrapper.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from imperal_sdk import ActionResult, Extension
from imperal_sdk.chat import ChatExtension


class _RefineParams(BaseModel):
    text: str


def test_decorator_accepts_background_and_long_running_kwargs():
    ext = Extension("ext-bg-test", display_name="Bg Test",
                    description="Background flag smoke test extension.",
                    actions_explicit=True)
    chat = ChatExtension(ext, tool_name="ext_bg_test_chat",
                         description="bg test")

    @chat.function(
        "refine_output",
        "Refine some text",
        action_type="write",
        event="refined",
        background=True,
        long_running=True,
    )
    async def refine_output(ctx, params: _RefineParams) -> ActionResult:
        return ActionResult.success(data={"out": params.text.upper()})

    fn = chat.functions["refine_output"]
    assert fn.background is True
    assert fn.long_running is True


def test_decorator_defaults_background_false():
    ext = Extension("ext-bg-default", display_name="Bg Default",
                    description="Background flag default-False smoke test.",
                    actions_explicit=True)
    chat = ChatExtension(ext, tool_name="ext_bg_default_chat",
                         description="default")

    @chat.function("plain", "Plain handler", action_type="read")
    async def plain(ctx, params: _RefineParams) -> ActionResult:
        return ActionResult.success(data={"echo": params.text})

    fn = chat.functions["plain"]
    assert fn.background is False
    assert fn.long_running is False


def test_manifest_emits_background_and_long_running():
    """Tool entry in imperal.json carries the new fields."""
    from imperal_sdk.manifest import generate_manifest

    ext = Extension("ext-bg-manifest", display_name="Bg Manifest",
                    description="Background flag manifest emission test.",
                    actions_explicit=True)
    chat = ChatExtension(ext, tool_name="ext_bg_manifest_chat",
                         description="manifest")

    @chat.function(
        "do_long_work",
        "Do long work",
        action_type="write",
        event="work_done",
        background=True,
        long_running=True,
    )
    async def do_long_work(ctx, params: _RefineParams) -> ActionResult:
        return ActionResult.success()

    manifest = generate_manifest(ext)
    tool_entry = next(t for t in manifest["tools"] if t["name"] == "do_long_work")
    assert tool_entry["background"] is True
    assert tool_entry["long_running"] is True


@pytest.mark.asyncio
@pytest.mark.skip(reason="legacy LLM router removed in v5.0.0; _execute_function deleted with handler.py — ported test pending")
async def test_handler_wraps_in_background_task_when_flag_set():
    """When background=True, the SDK handler MUST call ctx.background_task
    instead of running the handler synchronously. The tool result returned
    to the LLM should be an ack with task_id, not the handler's return value.
    """
    from imperal_sdk.chat.handler import _execute_function
    from imperal_sdk.context import Context
    from imperal_sdk.types.identity import UserContext

    # Counter to verify spawn hook was called, not the handler synchronously.
    spawn_calls: list = []

    async def _spawn_hook(coro, *, long_running, name):
        spawn_calls.append({"long_running": long_running, "name": name})
        coro.close()
        return "task_bg_abc"

    ext = Extension("ext-bg-runtime", display_name="Bg Runtime",
                    description="Background runtime wrap smoke test.",
                    actions_explicit=True)
    chat = ChatExtension(ext, tool_name="ext_bg_runtime_chat",
                         description="runtime")

    handler_ran = []

    @chat.function(
        "long_refine",
        "Refine text long-running",
        action_type="write",
        event="refined_long",
        background=True,
        long_running=True,
    )
    async def long_refine(ctx, params: _RefineParams) -> ActionResult:
        handler_ran.append(True)
        return ActionResult.success(data={"result": params.text.upper()})

    ctx = Context(user=UserContext(
        imperal_id="imp_u_t", email="t@t.com", tenant_id="t", role="user",
    ))
    ctx._background_task_spawn = _spawn_hook  # type: ignore[attr-defined]

    # Simulate one tool call from the LLM
    from types import SimpleNamespace
    tu = SimpleNamespace(name="long_refine", input={"text": "hello"})

    cfg = {
        "max_result_tokens": 4096,
        "list_truncate_items": 50,
        "string_truncate_chars": 200,
    }
    chat._functions_called = []
    result_str = await _execute_function(
        chat_ext=chat, ctx=ctx, tu=tu,
        action_type="write", cfg=cfg, retry_ctx=None,
    )

    # Spawn hook was called → handler is detached
    assert len(spawn_calls) == 1
    assert spawn_calls[0]["long_running"] is True
    assert spawn_calls[0]["name"] == "long_refine"
    # Handler body did NOT run synchronously (the coro was closed by spawn hook)
    assert handler_ran == []
    # Tool result returned to LLM is the background-ack envelope
    import json as _j
    res = _j.loads(result_str)
    assert res.get("status") == "success"
    assert "task_id" in (res.get("data") or {})
