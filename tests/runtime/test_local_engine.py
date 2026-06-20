"""Tests for LocalDevEngine — in-process declarative + code execution."""
import pytest
from imperal_sdk.runtime.local_engine import LocalDevEngine


class Caps:
    def __init__(self): self.sent = None
    # no store needed for this flow


@pytest.mark.asyncio
async def test_declarative_function_runs_in_process():
    eng = LocalDevEngine()
    ir_fn = {"name": "greet", "impl": {"kind": "declarative",
             "steps": [{"id": "s1", "op": "send", "args": {"message": "hi {{event.who}}"}}]}}
    class C: store=None; ai=None; extensions=None; current_app_id="toy"
    out = await eng.run_function(ir_fn, {"who": "Val"}, C())
    assert out["steps"]["s1"] == {"action": "send", "message": "hi Val"}


@pytest.mark.asyncio
async def test_code_function_dict_result():
    """Code impl that returns a dict passes through as-is."""
    import types, sys
    mod = types.ModuleType("_test_code_fn_dict")
    async def greet(ctx, params):
        return {"status": "ok", "name": params["who"]}
    mod.greet = greet
    sys.modules["_test_code_fn_dict"] = mod

    eng = LocalDevEngine()
    ir_fn = {"name": "greet", "impl": {"kind": "code", "module": "_test_code_fn_dict", "entry": "greet"}}
    class C: pass
    out = await eng.run_function(ir_fn, {"who": "World"}, C())
    assert out == {"status": "ok", "name": "World"}


@pytest.mark.asyncio
async def test_code_function_non_dict_result_normalized():
    """Code impl that returns a non-dict is wrapped in the success envelope."""
    import types, sys
    mod = types.ModuleType("_test_code_fn_str")
    async def shout(ctx, params):
        return "HELLO"
    mod.shout = shout
    sys.modules["_test_code_fn_str"] = mod

    eng = LocalDevEngine()
    ir_fn = {"name": "shout", "impl": {"kind": "code", "module": "_test_code_fn_str", "entry": "shout"}}
    class C: pass
    out = await eng.run_function(ir_fn, {}, C())
    assert out == {"status": "success", "data": "HELLO"}
