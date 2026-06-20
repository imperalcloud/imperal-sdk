import pytest
from pydantic import ValidationError
from imperal_sdk.ir.schema import IRFunction


def test_code_impl_accepted():
    fn = IRFunction.model_validate({
        "name": "pause", "params_schema": {"type": "object"},
        "impl": {"kind": "code", "module": "handlers", "entry": "fn_pause"},
    })
    assert fn.impl.kind == "code"
    assert fn.impl.entry == "fn_pause"


def test_declarative_impl_accepted():
    fn = IRFunction.model_validate({
        "name": "archive", "params_schema": {"type": "object"},
        "impl": {"kind": "declarative", "steps": [{"id": "s1", "op": "send", "args": {"message": "hi"}}]},
    })
    assert fn.impl.kind == "declarative"
    assert fn.impl.steps[0]["op"] == "send"


def test_impl_requires_known_kind():
    with pytest.raises(ValidationError):
        IRFunction.model_validate({
            "name": "bad", "params_schema": {"type": "object"},
            "impl": {"kind": "nope"},
        })


def test_impl_is_required():
    with pytest.raises(ValidationError):
        IRFunction.model_validate({"name": "bad", "params_schema": {"type": "object"}})
