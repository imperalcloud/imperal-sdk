# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Task 7 — M6.3/M7.3/M8.2 validator rules (uniqueness + cross-namespace block)."""
import pytest
from imperal_sdk.manifest_schema import validate_manifest_dict


def _base():
    return {
        "app_id": "billing",
        "version": "1.0.0",
        "manifest_schema_version": 2,
        "tools": [],
        "signals": [],
        "schedules": [],
    }


def test_M6_3_webhook_path_unique():
    m = _base()
    m["webhooks"] = [
        {"path": "/foo", "method": "POST"},
        {"path": "/foo", "method": "GET"},
    ]
    with pytest.raises(ValueError, match="M6.3"):
        validate_manifest_dict(m)


def test_M7_3_emits_prefix_matches_app_id():
    m = _base()
    # app_id = "billing" → emit type "other.bad" must be rejected
    m["events"] = {
        "subscribes": [],
        "emits": [{"type": "other.bad", "schema_ref": "#/x"}],
    }
    with pytest.raises(ValueError, match="M7.3"):
        validate_manifest_dict(m)


def test_M7_3_passes_when_prefix_matches():
    m = _base()
    # app_id = "billing" → "billing.ok" is allowed
    m["events"] = {
        "subscribes": [],
        "emits": [{"type": "billing.ok", "schema_ref": "#/x"}],
    }
    validate_manifest_dict(m)  # must not raise


def test_M8_2_exposed_name_unique():
    m = _base()
    m["exposed"] = [
        {"name": "x", "action_type": "read"},
        {"name": "x", "action_type": "write"},
    ]
    with pytest.raises(ValueError, match="M8.2"):
        validate_manifest_dict(m)


def test_M7_3_empty_emit_type_rejected_by_pydantic():
    """Empty emit type fails Pydantic min_length=1 (federal no-silent-drop)."""
    m = _base()
    m["events"] = {"subscribes": [], "emits": [{"type": "", "schema_ref": "#/x"}]}
    issues = validate_manifest_dict(m)
    assert any("type" in str(i).lower() for i in issues), \
        f"Expected Pydantic to reject empty emit type, got issues: {issues}"


def test_M7_3_empty_subscribe_type_rejected_by_pydantic():
    """Empty subscribe type fails Pydantic min_length=1."""
    m = _base()
    m["events"] = {"subscribes": [{"type": "", "handler": "h"}], "emits": []}
    issues = validate_manifest_dict(m)
    assert any("type" in str(i).lower() for i in issues), \
        f"Expected Pydantic to reject empty subscribe type, got issues: {issues}"
