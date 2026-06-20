import pytest
from pydantic import ValidationError
from imperal_sdk.ir.schema import IREnvelope


def test_minimal_envelope_accepted():
    env = IREnvelope.model_validate({
        "ir_version": "1.0",
        "app": {"id": "hello", "version": "1.0.0", "title": "Hello"},
    })
    assert env.app.id == "hello"
    assert env.ir_version == "1.0"
    assert env.sdl_vocab_version == "1"      # default
    assert env.contract_version == "1.0"     # default


def test_unknown_top_level_key_rejected():
    with pytest.raises(ValidationError):
        IREnvelope.model_validate({
            "ir_version": "1.0",
            "app": {"id": "x", "version": "1", "title": "X"},
            "bogus": True,
        })
