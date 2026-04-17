"""Regression tests for PEP 563 / forward-reference handling in validator.

Ensures V5 (return ActionResult) and V6 (params = Pydantic BaseModel)
correctly resolve string annotations to classes under
``from __future__ import annotations``.

Task #73 (session 26 continuation).
"""
from __future__ import annotations

import importlib
import textwrap
import tempfile
import sys
import os
import pytest


def _mk_module(body: str):
    """Compile + import a temporary module with the given source body."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir="/tmp",
    ) as f:
        f.write(textwrap.dedent(body))
        path = f.name
    modname = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod, path


def _cleanup(path):
    try:
        os.unlink(path)
    except Exception:
        pass


class FakeChatExt:
    def __init__(self, functions):
        self._functions = functions


class FakeFunc:
    def __init__(self, fn, action_type="read", event=""):
        self.func = fn
        self.action_type = action_type
        self.event = event


class FakeExt:
    def __init__(self, app_id="test-app", version="1.0.0", chat_functions=None):
        self.app_id = app_id
        self.version = version
        self._tools = {}
        self._chat_extensions = {
            "main": FakeChatExt(chat_functions or {}),
        }
        self._health_check = None
        self._event_handlers = []
        self._lifecycle = {}


# ── V6 regression: PEP 563 Pydantic param ─────────────────────────────────── #


def test_v6_pydantic_param_under_pep_563_passes():
    """The exact bug from the incident: BaseModel param + future annotations."""
    mod, path = _mk_module('''
    from __future__ import annotations
    from pydantic import BaseModel
    from imperal_sdk.chat.action_result import ActionResult

    class MyParams(BaseModel):
        name: str

    async def fn_my_func(ctx, params: MyParams) -> ActionResult:
        """docstring."""
        return ActionResult.success(data={}, summary="ok")
    ''')
    try:
        from imperal_sdk.validator import validate_extension
        ext = FakeExt(chat_functions={"my_func": FakeFunc(mod.fn_my_func)})
        report = validate_extension(ext)
        v6 = [i for i in report.issues if i.rule == "V6"]
        assert not v6, f"V6 false-positive on PEP 563 code: {[i.message for i in v6]}"
    finally:
        _cleanup(path)


def test_v6_non_basemodel_param_still_warns():
    """Extension WITHOUT a Pydantic model must still trip V6 (true positive)."""
    mod, path = _mk_module('''
    from __future__ import annotations
    from imperal_sdk.chat.action_result import ActionResult

    async def fn_my_func(ctx, name: str, count: int) -> ActionResult:
        """docstring."""
        return ActionResult.success(data={}, summary="ok")
    ''')
    try:
        from imperal_sdk.validator import validate_extension
        ext = FakeExt(chat_functions={"my_func": FakeFunc(mod.fn_my_func)})
        report = validate_extension(ext)
        v6 = [i for i in report.issues if i.rule == "V6"]
        assert v6, "V6 should warn when no BaseModel param is present"
    finally:
        _cleanup(path)


def test_v6_without_future_annotations_still_passes():
    """Sanity: pre-PEP-563 style still validates correctly."""
    mod, path = _mk_module('''
    from pydantic import BaseModel
    from imperal_sdk.chat.action_result import ActionResult

    class MyParams(BaseModel):
        name: str

    async def fn_my_func(ctx, params: MyParams) -> ActionResult:
        """docstring."""
        return ActionResult.success(data={}, summary="ok")
    ''')
    try:
        from imperal_sdk.validator import validate_extension
        ext = FakeExt(chat_functions={"my_func": FakeFunc(mod.fn_my_func)})
        report = validate_extension(ext)
        v6 = [i for i in report.issues if i.rule == "V6"]
        assert not v6, f"V6 false-positive on pre-PEP-563 code: {[i.message for i in v6]}"
    finally:
        _cleanup(path)


# ── V5 regression: PEP 563 ActionResult return ───────────────────────────── #


def test_v5_action_result_return_under_pep_563_passes():
    mod, path = _mk_module('''
    from __future__ import annotations
    from pydantic import BaseModel
    from imperal_sdk.chat.action_result import ActionResult

    class P(BaseModel):
        x: int

    async def fn_ok(ctx, params: P) -> ActionResult:
        """doc."""
        return ActionResult.success(data={}, summary="ok")
    ''')
    try:
        from imperal_sdk.validator import validate_extension
        ext = FakeExt(chat_functions={"ok": FakeFunc(mod.fn_ok)})
        report = validate_extension(ext)
        v5 = [i for i in report.issues if i.rule == "V5"]
        assert not v5, f"V5 false-positive on PEP 563 ActionResult: {[i.message for i in v5]}"
    finally:
        _cleanup(path)


def test_v5_missing_return_annotation_errors():
    mod, path = _mk_module('''
    from __future__ import annotations
    from pydantic import BaseModel

    class P(BaseModel):
        x: int

    async def fn_bad(ctx, params: P):
        """no return annotation."""
        return None
    ''')
    try:
        from imperal_sdk.validator import validate_extension
        ext = FakeExt(chat_functions={"bad": FakeFunc(mod.fn_bad)})
        report = validate_extension(ext)
        v5 = [i for i in report.issues if i.rule == "V5"]
        assert v5, "V5 must error when ActionResult return annotation is missing"
    finally:
        _cleanup(path)


def test_v5_subclass_of_action_result_also_passes():
    """Return type annotated as ActionResult subclass should still pass V5."""
    mod, path = _mk_module('''
    from __future__ import annotations
    from pydantic import BaseModel
    from imperal_sdk.chat.action_result import ActionResult

    class MyActionResult(ActionResult):
        pass

    class P(BaseModel):
        x: int

    async def fn_sub(ctx, params: P) -> MyActionResult:
        """doc."""
        return MyActionResult.success(data={}, summary="ok")
    ''')
    try:
        from imperal_sdk.validator import validate_extension
        ext = FakeExt(chat_functions={"sub": FakeFunc(mod.fn_sub)})
        report = validate_extension(ext)
        v5 = [i for i in report.issues if i.rule == "V5"]
        assert not v5, f"V5 false-positive on ActionResult subclass: {[i.message for i in v5]}"
    finally:
        _cleanup(path)


# ── Helper unit tests ─────────────────────────────────────────────────────── #


def test_resolve_hints_returns_empty_on_unresolvable():
    """_resolve_hints must degrade gracefully, never raise."""
    from imperal_sdk.validator import _resolve_hints

    async def fn_broken(ctx, params: "NonExistentClass") -> "MysteryReturn":
        return None
    # Should NOT raise -- fallback to {}
    result = _resolve_hints(fn_broken)
    assert isinstance(result, dict)


def test_is_basemodel_subclass_edge_cases():
    from imperal_sdk.validator import _is_basemodel_subclass
    from pydantic import BaseModel

    class Real(BaseModel):
        x: int

    class NotPydantic:
        pass

    assert _is_basemodel_subclass(Real) is True
    assert _is_basemodel_subclass(NotPydantic) is False
    assert _is_basemodel_subclass(None) is False
    assert _is_basemodel_subclass("Real") is False      # string isn't a class
    assert _is_basemodel_subclass(42) is False


def test_looks_like_action_result_lenient_fallback():
    """String annotation fallback still works (lenient substring)."""
    from imperal_sdk.validator import _looks_like_action_result
    from imperal_sdk.chat.action_result import ActionResult

    assert _looks_like_action_result(ActionResult) is True
    # Subclass
    class Sub(ActionResult):
        pass
    assert _looks_like_action_result(Sub) is True
    # String (raw annotation, unresolved forward ref)
    assert _looks_like_action_result("ActionResult") is True
    assert _looks_like_action_result("Optional[ActionResult]") is True
    # Not matching
    assert _looks_like_action_result("int") is False
    assert _looks_like_action_result(None) is False
