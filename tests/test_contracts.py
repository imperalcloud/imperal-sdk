# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for cross-boundary payload contracts.

Covers `imperal_sdk.types.contracts`:
- `validate_action_result_dict` — rule codes AR1..AR5
- `validate_event_dict`         — rule codes EV1..EV5
- Round-trip: dataclass `ActionResult.to_dict()` output validates clean
- Schema exports (stable; static files match runtime)
"""
import json
from pathlib import Path

import pytest

from imperal_sdk.types import ActionResult, Event
from imperal_sdk.types.contracts import (
    ACTION_RESULT_SCHEMA,
    EVENT_SCHEMA,
    ActionResultModel,
    EventModel,
    get_action_result_schema,
    get_event_schema,
    validate_action_result_dict,
    validate_event_dict,
)


# === ActionResult contract ==========================================

def test_AR_valid_success_minimal():
    assert validate_action_result_dict(
        {"status": "success", "summary": "done", "data": {}}
    ) == []


def test_AR_valid_success_full():
    payload = {
        "status": "success",
        "summary": "done",
        "data": {"id": "abc"},
        "retryable": False,
        "ui": {"type": "Text", "content": "hello"},
        "refresh_panels": ["sidebar", "reports"],
    }
    assert validate_action_result_dict(payload) == []


def test_AR_valid_error():
    assert validate_action_result_dict(
        {"status": "error", "summary": "", "data": {}, "error": "rate limit"}
    ) == []


def test_AR1_root_not_dict():
    issues = validate_action_result_dict("nope")
    assert len(issues) == 1
    assert issues[0].rule == "AR1"


def test_AR2_missing_status():
    issues = validate_action_result_dict({"summary": "x", "data": {}})
    assert any(i.rule == "AR2" and "status" in i.message for i in issues)


def test_AR3_extra_forbidden_typo():
    # "retryble" vs "retryable" — exactly the bug this rule catches
    bad = {"status": "success", "summary": "x", "data": {}, "retryble": True}
    issues = validate_action_result_dict(bad)
    assert any(i.rule == "AR3" for i in issues)


def test_AR4_invalid_status_enum():
    bad = {"status": "pending", "summary": "", "data": {}}
    issues = validate_action_result_dict(bad)
    assert any(i.rule == "AR4" and "status" in i.message for i in issues)


def test_AR4_error_without_error_field():
    # status=error demands a non-empty error= message
    bad = {"status": "error", "summary": "", "data": {}}
    issues = validate_action_result_dict(bad)
    assert any(i.rule == "AR4" for i in issues)


def test_AR4_success_must_not_carry_error():
    bad = {"status": "success", "summary": "x", "data": {}, "error": "huh"}
    issues = validate_action_result_dict(bad)
    assert any(i.rule == "AR4" for i in issues)


# === Round-trip: real ActionResult dataclass → to_dict() ============

def test_AR_roundtrip_success():
    """ActionResult.success().to_dict() must validate clean."""
    ar = ActionResult.success(data={"id": "m1"}, summary="sent")
    assert validate_action_result_dict(ar.to_dict()) == []


def test_AR_roundtrip_error():
    ar = ActionResult.error("rate limited", retryable=True)
    assert validate_action_result_dict(ar.to_dict()) == []


def test_AR_roundtrip_with_refresh_panels():
    ar = ActionResult.success(
        data={}, summary="done", refresh_panels=["sidebar"]
    )
    assert validate_action_result_dict(ar.to_dict()) == []


# === Event contract =================================================

@pytest.mark.parametrize("event_type", [
    "notes.created",
    "notes:created",
    "mail.sent",
    "sharelock.case.created",
    "admin:audit:write",
])
def test_EV_valid_event_types(event_type):
    assert validate_event_dict({"event_type": event_type}) == []


def test_EV_valid_full_envelope():
    payload = {
        "event_type": "mail.sent",
        "timestamp": "2026-04-19T12:00:00Z",
        "user_id": "imp_u_abc123",
        "tenant_id": "imp_t_xyz",
        "data": {"to": "user@x.com", "subject": "hi"},
    }
    assert validate_event_dict(payload) == []


def test_EV_valid_system_event():
    # Schedule-fired events run under synthetic __system__ user
    assert validate_event_dict({
        "event_type": "schedule.fired",
        "user_id": "__system__",
    }) == []


def test_EV_valid_default_tenant():
    assert validate_event_dict({
        "event_type": "notes.created",
        "tenant_id": "default",
    }) == []


def test_EV1_root_not_dict():
    issues = validate_event_dict("nope")
    assert len(issues) == 1
    assert issues[0].rule == "EV1"


def test_EV2_missing_event_type():
    issues = validate_event_dict({"data": {}})
    assert any(i.rule == "EV2" for i in issues)


def test_EV3_unknown_top_level_field():
    issues = validate_event_dict({"event_type": "n.c", "kind": "extra"})
    assert any(i.rule == "EV3" for i in issues)


@pytest.mark.parametrize("bad_event_type", [
    "",                 # empty
    "UPPERCASE",        # uppercase
    "no-separator",     # no . or :
    "has spaces.x",     # whitespace
    "has!.chars",       # bad chars
])
def test_EV4_bad_event_type(bad_event_type):
    issues = validate_event_dict({"event_type": bad_event_type})
    assert any(i.rule in ("EV2", "EV4") for i in issues)


def test_EV4_bad_user_id():
    issues = validate_event_dict({"event_type": "n.c", "user_id": "joe"})
    assert any(i.rule == "EV4" and "user_id" in i.message for i in issues)


def test_EV4_bad_tenant_id():
    issues = validate_event_dict({"event_type": "n.c", "tenant_id": "MyTenant"})
    assert any(i.rule == "EV4" and "tenant_id" in i.message for i in issues)


# === Round-trip: real Event dataclass ==============================

def test_EV_roundtrip():
    from dataclasses import asdict
    ev = Event(event_type="notes.created", user_id="imp_u_a",
               tenant_id="imp_t_b", data={"id": "n1"})
    assert validate_event_dict(asdict(ev)) == []


# === Schema exports ================================================

def test_action_result_schema_is_valid_json_schema():
    s = get_action_result_schema()
    assert s["$id"] == "https://imperal.io/schemas/action_result.schema.json"
    assert s["title"] == "Imperal ActionResult Payload"
    assert "properties" in s
    assert "status" in s["properties"]
    assert "required" in s
    assert "status" in s["required"]


def test_event_schema_is_valid_json_schema():
    s = get_event_schema()
    assert s["$id"] == "https://imperal.io/schemas/event.schema.json"
    assert s["title"] == "Imperal Platform Event Envelope"
    assert "event_type" in s["properties"]
    assert "event_type" in s["required"]


def test_schema_constants_equal_fresh_exports():
    assert ACTION_RESULT_SCHEMA == get_action_result_schema()
    assert EVENT_SCHEMA == get_event_schema()


@pytest.mark.parametrize("name,fn", [
    ("action_result", get_action_result_schema),
    ("event", get_event_schema),
])
def test_static_schema_file_in_sync(name, fn):
    """Committed static schema JSON must match runtime export.

    Regenerate via:
      python -c 'from imperal_sdk.types.contracts import get_{name}_schema; \
                 import json; print(json.dumps(get_{name}_schema(), indent=2))' \
        > src/imperal_sdk/schemas/{name}.schema.json
    """
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "imperal_sdk" / "schemas" / f"{name}.schema.json"
    )
    assert schema_path.exists(), f"Missing {schema_path}"
    assert json.loads(schema_path.read_text()) == fn(), (
        f"src/imperal_sdk/schemas/{name}.schema.json is out of sync"
    )


# === Pydantic model smoke ==========================================

def test_pydantic_models_validate_baselines():
    ActionResultModel.model_validate(
        {"status": "success", "summary": "x", "data": {}}
    )
    EventModel.model_validate({"event_type": "ns.action"})
