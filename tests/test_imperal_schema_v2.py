# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Task 6 — imperal.schema.json v2 constraint enforcement tests.

Covers: path pattern, method enum, manifest_schema_version enum,
tray_id pattern, health_check minimum interval, action_type enum,
full v2 round-trip, and v1 backward compat.
"""
import json
import jsonschema
import pytest
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "src/imperal_sdk/schemas/imperal.schema.json"


def test_schema_declares_v2_optional_sections():
    schema = json.loads(SCHEMA_PATH.read_text())
    # The static schema may have $defs structure; resolve top-level properties
    props = schema.get("properties", {})
    for sec in ("webhooks", "events", "exposed", "lifecycle", "tray"):
        assert sec in props, f"missing section {sec}"


def test_v2_manifest_validates_against_static_schema():
    """Full v2 manifest must validate against the static schema using jsonschema."""
    schema = json.loads(SCHEMA_PATH.read_text())
    manifest = {
        "name": "billing", "version": "2.1.0",
        "manifest_schema_version": 2,
        "app_id": "billing",
        "tools": [], "signals": [], "schedules": [],
        "webhooks": [{"path": "/stripe", "method": "POST", "secret_header": "Stripe-Signature"}],
        "events": {
            "subscribes": [{"type": "payment.received", "handler": "h"}],
            "emits": [{"type": "billing.topup", "schema_ref": "#/schemas/x"}],
        },
        "exposed": [{"name": "get_balance", "action_type": "read"}],
        "lifecycle": {"on_install": True, "health_check": {"interval_sec": 60}},
        "tray": [{"tray_id": "unread", "icon": "Mail", "tooltip": "x"}],
    }
    jsonschema.validate(manifest, schema)


def test_v1_manifest_still_validates():
    """Backward compat: manifests without v2 sections still pass."""
    schema = json.loads(SCHEMA_PATH.read_text())
    manifest = {
        "app_id": "old-ext",
        "name": "old",
        "version": "1.0.0",
        "tools": [], "signals": [], "schedules": [],
    }
    jsonschema.validate(manifest, schema)


def test_webhook_path_pattern_rejects_invalid():
    """webhooks[].path must match ^/[a-z0-9_/-]+$ — uppercase or special chars rejected."""
    schema = json.loads(SCHEMA_PATH.read_text())
    bad_path = {
        "app_id": "my-ext", "version": "1.0.0", "tools": [], "signals": [], "schedules": [],
        "webhooks": [{"path": "/Stripe", "method": "POST"}],  # uppercase = bad
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_path, schema)


def test_webhook_method_enum_rejects_invalid():
    """webhooks[].method must be POST/GET/PUT/DELETE."""
    schema = json.loads(SCHEMA_PATH.read_text())
    bad_method = {
        "app_id": "my-ext", "version": "1.0.0", "tools": [], "signals": [], "schedules": [],
        "webhooks": [{"path": "/stripe", "method": "PATCH"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_method, schema)


def test_manifest_schema_version_rejects_4():
    """manifest_schema_version enum [1, 2, 3] in v4.0.0 — version 4 rejected.

    v4.0.0 (2026-05-01): Federal Extension Contract added schema_version=3 with
    typed @chat.function emission, ``actions_explicit``, ``icon``, lifecycle
    hook signatures. Future v5.0.0 bumps the enum to include 4.
    """
    schema = json.loads(SCHEMA_PATH.read_text())
    bad_version = {
        "app_id": "my-ext", "version": "1.0.0",
        "manifest_schema_version": 4,
        "tools": [], "signals": [], "schedules": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_version, schema)


def test_tray_id_pattern_rejects_uppercase():
    """tray_id must match ^[a-z][a-z0-9_-]+$ — uppercase rejected."""
    schema = json.loads(SCHEMA_PATH.read_text())
    bad_tray = {
        "app_id": "my-ext", "version": "1.0.0", "tools": [], "signals": [], "schedules": [],
        "tray": [{"tray_id": "Unread"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_tray, schema)


def test_health_check_interval_minimum_30():
    """interval_sec must be >= 30."""
    schema = json.loads(SCHEMA_PATH.read_text())
    bad_interval = {
        "app_id": "my-ext", "version": "1.0.0", "tools": [], "signals": [], "schedules": [],
        "lifecycle": {"health_check": {"interval_sec": 10}},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_interval, schema)


def test_exposed_action_type_rejects_invalid():
    """exposed[].action_type must be 'read' or 'write'."""
    schema = json.loads(SCHEMA_PATH.read_text())
    bad_action = {
        "app_id": "my-ext", "version": "1.0.0", "tools": [], "signals": [], "schedules": [],
        "exposed": [{"name": "get_balance", "action_type": "execute"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_action, schema)
