"""2026-11-13 (imperal-mcp tester): validate_ir and smoke_ir disagreed about one step, and {{args.x}} stored "".
One rule now: a step that validates also runs, a step that does not run says why before anything runs."""
import pytest

from imperal_sdk.ir.actions import validate_step
from imperal_sdk.runtime.interpreter import run_steps


class _Store:
    def __init__(self):
        self.docs = []

    async def create(self, coll, data):
        self.docs.append((coll, data))
        return {"id": f"d{len(self.docs)}"}


class _Ctx:
    def __init__(self):
        self.store = _Store()


SHAPES = [
    ({"op": "store.create", "kind": "link", "data": {"url": "x"}}, False),                   # verb keys at the root, no id
    ({"id": "s", "op": "store.create", "kind": "link", "data": {"url": "x"}}, False),       # verb keys at the root
    ({"op": "store.create", "args": {"kind": "link", "data": {"url": "x"}}}, False),         # no id
    ({"id": "s", "op": "store.create", "args": {"kind": "link", "data": {"url": "x"}}}, True),
]


@pytest.mark.parametrize("step,ok", SHAPES)
@pytest.mark.asyncio
async def test_validate_and_run_agree(step, ok):
    assert (validate_step(step) == []) is ok
    if ok:
        await run_steps([step], _Ctx())
    else:
        with pytest.raises(ValueError):
            await run_steps([step], _Ctx())


def test_a_misplaced_key_is_named_with_where_it_goes():
    errs = validate_step({"id": "s", "op": "store.create", "kind": "link", "data": {"url": "x"}})
    assert any("must go under 'args'" in e and "data" in e for e in errs)


@pytest.mark.asyncio
async def test_args_names_the_functions_parameters():
    ctx = _Ctx()
    await run_steps([{"id": "s", "op": "store.create", "args": {"kind": "link", "data": {"url": "{{args.url}}"}}}],
                    ctx, event={"url": "https://imperal.io"})
    assert ctx.store.docs == [("link", {"url": "https://imperal.io"})]


def test_the_field_tests_exact_step_is_told_its_right_shape():
    # 2026-11-13: {"op":"store.create","collection":"notes","data":{...}} -- three tries, never told the right shape
    errs = validate_step({"op": "store.create", "collection": "notes", "data": {"text": "hello"}})
    text = " ".join(errs)
    assert "needs an 'id'" in text and "'collection' -> args.kind" in text
    assert '{"id": "s1", "op": "store.create", "args": {"kind": ..., "data": ...}}' in text
