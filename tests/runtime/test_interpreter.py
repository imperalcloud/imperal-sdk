"""Integration test for run_steps — the multi-step declarative interpreter loop."""
import pytest
from imperal_sdk.runtime.interpreter import run_steps


class Caps:
    def __init__(self): self.docs = {}

    # store
    async def create(self, c, data): self.docs[data["id"]] = data; return data

    async def query(self, c, where=None, order_by=None, limit=100, cursor=None):
        rows = [d for d in self.docs.values() if all(d.get(k) == v for k, v in (where or {}).items())]
        class P: items = rows
        return P()

    async def update(self, c, doc_id, data): self.docs[doc_id].update(data); return self.docs[doc_id]


def _ctx(caps):
    class C: pass
    c = C(); c.store = caps; c.ai = None; c.extensions = None; c.current_app_id = "toy"
    return c


@pytest.mark.asyncio
async def test_archive_ended_flow():
    """Canonical 4-step archive_ended flow from the L0-2 spec."""
    caps = Caps()
    await caps.create("campaign", {"id": "1", "status": "ended"})
    await caps.create("campaign", {"id": "2", "status": "active"})
    steps = [
        {"id": "s1", "op": "store.list",   "args": {"kind": "campaign", "where": {"status": "ended"}}},
        {"id": "s2", "op": "conditional",  "if": {"field": "{{steps.s1.count}}", "gt": 0}, "then": "s3", "else": None},
        {"id": "s3", "op": "store.update", "args": {"kind": "campaign", "ids": "{{steps.s1.ids}}", "set": {"archived": True}}},
        {"id": "s4", "op": "send",         "args": {"message": "Archived {{steps.s1.count}}"}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps))
    assert out["steps"]["s1"]["count"] == 1
    assert caps.docs["1"]["archived"] is True
    assert out["steps"]["s4"] == {"action": "send", "message": "Archived 1"}


@pytest.mark.asyncio
async def test_conditional_else_stops():
    """When conditional resolves to else=None, execution stops — s3 is never run."""
    caps = Caps()
    await caps.create("campaign", {"id": "1", "status": "active"})
    steps = [
        {"id": "s1", "op": "store.list",  "args": {"kind": "campaign", "where": {"status": "ended"}}},
        {"id": "s2", "op": "conditional", "if": {"field": "{{steps.s1.count}}", "gt": 0}, "then": "s3", "else": None},
        {"id": "s3", "op": "send",        "args": {"message": "Should not run"}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps))
    assert out["steps"]["s1"]["count"] == 0
    assert "s3" not in out["steps"]


@pytest.mark.asyncio
async def test_send_directive():
    """send op produces {"action": "send", ...}."""
    caps = Caps()
    steps = [
        {"id": "s1", "op": "send", "args": {"message": "Hello"}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps))
    assert out["steps"]["s1"] == {"action": "send", "message": "Hello"}


@pytest.mark.asyncio
async def test_navigate_directive():
    """navigate op produces {"action": "navigate", ...}."""
    caps = Caps()
    steps = [
        {"id": "s1", "op": "navigate", "args": {"url": "/dashboard"}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps))
    assert out["steps"]["s1"] == {"action": "navigate", "url": "/dashboard"}


@pytest.mark.asyncio
async def test_prev_tracks_last_result():
    """prev is always the last executed step's result."""
    caps = Caps()
    await caps.create("campaign", {"id": "1", "status": "ended"})
    steps = [
        {"id": "s1", "op": "store.list", "args": {"kind": "campaign", "where": {"status": "ended"}}},
        {"id": "s2", "op": "send", "args": {"message": "count={{steps.s1.count}}"}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps))
    assert out["prev"] == {"action": "send", "message": "count=1"}


@pytest.mark.asyncio
async def test_store_create_and_list():
    """store.create followed by store.list sees the created doc."""
    caps = Caps()
    steps = [
        {"id": "s1", "op": "store.create", "args": {"kind": "item", "data": {"id": "x1", "name": "foo"}}},
        {"id": "s2", "op": "store.list",   "args": {"kind": "item"}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps))
    assert out["steps"]["s1"] == {"id": "x1"}
    assert out["steps"]["s2"]["count"] == 1


@pytest.mark.asyncio
async def test_ids_passed_as_list_to_update():
    """{{steps.s1.ids}} resolves to a real list (typed passthrough) for bulk update."""
    caps = Caps()
    await caps.create("item", {"id": "a", "done": False})
    await caps.create("item", {"id": "b", "done": False})
    steps = [
        {"id": "s1", "op": "store.list",   "args": {"kind": "item"}},
        {"id": "s2", "op": "store.update", "args": {"kind": "item", "ids": "{{steps.s1.ids}}", "set": {"done": True}}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps))
    assert caps.docs["a"]["done"] is True
    assert caps.docs["b"]["done"] is True
    assert out["steps"]["s2"]["count"] == 2


@pytest.mark.asyncio
async def test_event_available_in_args():
    """event data is accessible via {{event.*}} in step args."""
    caps = Caps()
    steps = [
        {"id": "s1", "op": "send", "args": {"message": "Hi {{event.user}}"}},
    ]
    out = await run_steps(steps, ctx=_ctx(caps), event={"user": "Alice"})
    assert out["steps"]["s1"] == {"action": "send", "message": "Hi Alice"}


@pytest.mark.asyncio
async def test_backward_conditional_jump_is_bounded():
    """A conditional that always jumps back to an earlier step must be stopped by the budget."""
    caps = Caps()
    steps = [
        {"id": "s1", "op": "send", "args": {"message": "loop"}},
        {"id": "s2", "op": "conditional", "if": {"field": "1", "gt": 0}, "then": "s1", "else": None},
    ]
    with pytest.raises(RuntimeError, match="step budget"):
        await run_steps(steps, ctx=_ctx(caps))


@pytest.mark.asyncio
async def test_conditional_bad_target_raises():
    """A conditional targeting a nonexistent step id raises ValueError."""
    caps = Caps()
    steps = [
        {"id": "s1", "op": "conditional", "if": {"field": "1", "gt": 0}, "then": "nope", "else": None},
    ]
    with pytest.raises(ValueError, match="nope"):
        await run_steps(steps, ctx=_ctx(caps))


@pytest.mark.asyncio
async def test_step_missing_id_raises():
    """A step dict with no 'id' key raises ValueError before execution."""
    caps = Caps()
    steps = [
        {"op": "send", "args": {"message": "no id here"}},
    ]
    with pytest.raises(ValueError, match="missing required 'id'"):
        await run_steps(steps, ctx=_ctx(caps))
