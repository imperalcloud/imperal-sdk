# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""EV6..EV8: event_id, schema_version, source fields on the Event envelope.

Task 1 of the UEB Phase 1 plan — adds three optional backward-compat fields
to the canonical Event Pydantic model in contracts.py and to the JSON Schema
file.
"""
import json
from pathlib import Path
from imperal_sdk.types.contracts import Event


def test_event_accepts_v2_fields():
    """EV6/7/8: event_id, schema_version, source are optional + addable."""
    e = Event(
        type="state_changed",
        scope="email",
        action="received",
        actor="user_123",
        tenant_id="default",
        user_id="user_123",
        timestamp="2026-05-01T10:23:45.123Z",
        data={},
        event_id="01927a3f-a0d1-7b42-9c5e-d8a3e4f2c1b9",
        schema_version=1,
        source="system",
    )
    assert e.event_id == "01927a3f-a0d1-7b42-9c5e-d8a3e4f2c1b9"
    assert e.schema_version == 1
    assert e.source == "system"


def test_event_v1_backward_compat():
    """v1 payloads (without new fields) still validate."""
    e = Event(
        type="state_changed", scope="email", action="received",
        actor="user_123", tenant_id="default", user_id="user_123",
        timestamp="2026-05-01T10:23:45.123Z", data={},
    )
    assert e.event_id is None
    assert e.schema_version is None
    assert e.source is None


def test_event_schema_json_includes_v2_fields():
    """JSON Schema file declares EV6..EV8 properties — and live get_event_schema() matches."""
    schema_path = Path(__file__).parent.parent / "src/imperal_sdk/schemas/event.schema.json"
    schema = json.loads(schema_path.read_text())
    props = schema["properties"]
    assert "event_id" in props
    assert "schema_version" in props
    assert "source" in props
    assert props["source"]["enum"] == ["user", "system", "automation", "rbac", "mcp", "webhook"]

    # Drift check: live generator must produce the same shape
    from imperal_sdk.types.contracts import get_event_schema
    live = get_event_schema()
    live_props = live["properties"]
    assert "event_id" in live_props
    assert "schema_version" in live_props
    assert "source" in live_props
    assert live_props["source"]["enum"] == ["user", "system", "automation", "rbac", "mcp", "webhook"]


def test_event_model_accepts_v2_fields():
    """EventModel (v1 Redis-stream contract) also accepts EV6..EV8 fields backward-compat."""
    from imperal_sdk.types.contracts import EventModel
    e = EventModel(
        event_type="email.state_changed",
        timestamp="2026-05-01T10:23:45.123Z",
        user_id="",
        tenant_id="default",
        data={},
        event_id="01927a3f-a0d1-7b42-9c5e-d8a3e4f2c1b9",
        schema_version=1,
        source="system",
    )
    assert e.event_id == "01927a3f-a0d1-7b42-9c5e-d8a3e4f2c1b9"
