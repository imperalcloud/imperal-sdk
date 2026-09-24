# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
import io
import json
import pytest
from imperal_sdk.core import (
    CancellationToken,
    StreamEmitter,
    SchemaValidator,
    ICNLIComponent,
)


def test_cancellation_token():
    token = CancellationToken()
    assert token.is_cancelled() is False

    fired = []
    token.on_cancelled(lambda: fired.append(True))
    assert len(fired) == 0

    token.cancel()
    assert token.is_cancelled() is True
    assert len(fired) == 1

    # Callbacks registered after cancel fire immediately
    late = []
    token.on_cancelled(lambda: late.append(True))
    assert len(late) == 1


def test_stream_emitter():
    buf = io.StringIO()
    emitter = StreamEmitter(buf)

    emitter.emit_progress(88.5, "Compiling package")
    emitter.emit_chunk("linking object files...", stream_name="stdout")

    lines = buf.getvalue().strip().split("\n")
    assert len(lines) == 2

    p = json.loads(lines[0])
    assert p["type"] == "progress"
    assert p["payload"]["percent"] == 88.5

    c = json.loads(lines[1])
    assert c["type"] == "stream_chunk"
    assert c["payload"]["chunk"] == "linking object files..."


def test_schema_validator():
    schema = {
        "type": "object",
        "required": ["app_id", "timeout"],
        "properties": {
            "app_id": {"type": "string"},
            "timeout": {"type": "integer"},
            "environment": {"type": "string", "enum": ["prod", "dev"]},
        },
    }

    # Valid
    assert SchemaValidator.validate({"app_id": "test", "timeout": 30, "environment": "prod"}, schema) == []

    # Missing required
    errs = SchemaValidator.validate({"app_id": "test"}, schema)
    assert any("Missing required property 'timeout'" in e for e in errs)

    # Wrong type
    errs = SchemaValidator.validate({"app_id": "test", "timeout": "fast"}, schema)
    assert any("Expected type 'integer'" in e for e in errs)

    # Enum
    errs = SchemaValidator.validate({"app_id": "test", "timeout": 10, "environment": "staging"}, schema)
    assert any("not in enum" in e for e in errs)


def test_icnli_components():
    el = ICNLIComponent.entity_list([{"id": "s1"}], total_count=5, omitted_count=4)
    assert el["component"] == "EntityList"
    assert el["total"] == 5

    cg = ICNLIComponent.confirmation_gate("drop_database", ["db_main"], risk_level="destructive")
    assert cg["component"] == "ConfirmationGate"
    assert cg["risk"] == "destructive"
    assert cg["affected_count"] == 1

    sc = ICNLIComponent.stat_card("Active Nodes", 3, delta="+1", status="good")
    assert sc["component"] == "StatCard"
    assert sc["value"] == 3
    assert sc["delta"] == "+1"
