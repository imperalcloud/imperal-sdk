# tests/test_context_background_task.py
"""Component B — ctx.background_task() public API surface tests.

Verifies the SDK contract:
- Returns a task_id (str) immediately.
- Spawns coroutine via injected kernel hook.
- Raises RuntimeError if no kernel hook present (e.g. dev mode).
"""
from __future__ import annotations
import pytest

from imperal_sdk import ActionResult
from imperal_sdk.context import Context
from imperal_sdk.types.identity import UserContext


def _make_ctx() -> Context:
    return Context(user=UserContext(
        imperal_id="imp_u_test", email="test@test.com", tenant_id="t", role="user",
    ))


@pytest.mark.asyncio
async def test_background_task_returns_task_id_str():
    captured: dict = {}

    async def _spawn_hook(coro, *, long_running, name):
        captured["coro_present"] = coro is not None
        captured["long_running"] = long_running
        captured["name"] = name
        coro.close()
        return "task_xyz123"

    ctx = _make_ctx()
    ctx._background_task_spawn = _spawn_hook  # type: ignore[attr-defined]

    async def _work():
        return ActionResult.success(data={"ok": True})

    tid = await ctx.background_task(_work(), long_running=True, name="my-task")
    assert tid == "task_xyz123"
    assert captured["long_running"] is True
    assert captured["name"] == "my-task"
    assert captured["coro_present"] is True


@pytest.mark.asyncio
async def test_background_task_raises_without_kernel_hook():
    ctx = _make_ctx()

    async def _work():
        return ActionResult.success(data={"ok": True})

    coro = _work()
    with pytest.raises(RuntimeError, match="ctx.background_task not available"):
        await ctx.background_task(coro)
    coro.close()


@pytest.mark.asyncio
async def test_background_task_default_long_running_false():
    captured: dict = {}

    async def _spawn_hook(coro, *, long_running, name):
        captured["long_running"] = long_running
        coro.close()
        return "task_y"

    ctx = _make_ctx()
    ctx._background_task_spawn = _spawn_hook  # type: ignore[attr-defined]

    async def _work():
        return ActionResult.success(data={"ok": True})

    await ctx.background_task(_work())
    assert captured["long_running"] is False
