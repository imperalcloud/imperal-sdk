import pytest
from pydantic import ValidationError
from imperal_sdk.types.metered_event import MeteredEvent


def _valid():
    return {"v": 1, "event_id": "m_abc", "ts": 1,
            "identity": {"imperal_id": "u1", "tenant_id": "t1", "agency_id": None},
            "meter": {"unit_type": "invocation", "meter_version": 1},
            "attribution": {"app_id": "notes", "tool_name": "create_note", "action_type": "write"},
            "dimensions": {"count": 1, "model": "claude-haiku-4-5"}}


def test_valid_invocation_event():
    e = MeteredEvent.model_validate(_valid())
    assert e.meter.unit_type == "invocation"
    assert e.identity.imperal_id == "u1"
    assert e.dimensions["count"] == 1


def test_price_keys_forbidden_anywhere():
    for bad in ("base_price", "platform_fee", "cost", "model_tier", "price"):
        d = _valid(); d["dimensions"][bad] = 100
        with pytest.raises(ValidationError):
            MeteredEvent.model_validate(d)


def test_two_version_axes_present():
    e = MeteredEvent.model_validate(_valid())
    assert e.v == 1 and e.meter.meter_version == 1   # envelope vs vocabulary, decoupled


def test_identity_imperal_id_required_nonempty():
    d = _valid(); d["identity"]["imperal_id"] = ""
    with pytest.raises(ValidationError):
        MeteredEvent.model_validate(d)
