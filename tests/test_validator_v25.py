# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""V25 — manifest MUST NOT contain tool_*_chat orchestrator-tool entries."""
from imperal_sdk.validator import validate_manifest_dict


def test_v25_rejects_orchestrator_tool_in_manifest():
    legacy_manifest = {
        "app_id": "demo",
        "version": "1.0.0",
        "sdk_version": "5.0.0",
        "tools": [
            {"name": "tool_demo_chat", "description": "legacy orchestrator entry"},
        ],
    }
    issues = validate_manifest_dict(legacy_manifest)
    v25_issues = [i for i in issues if i.get("rule") == "V25"]
    assert len(v25_issues) == 1, f"V25 should fire exactly once; got {v25_issues}"
    assert v25_issues[0].get("severity") == "ERROR"
    assert "tool_demo_chat" in v25_issues[0].get("detail")


def test_v25_passes_when_no_orchestrator_tool():
    clean_manifest = {
        "app_id": "demo",
        "version": "1.0.0",
        "sdk_version": "5.0.0",
        "tools": [
            {"name": "list_items", "description": "list user items"},
        ],
    }
    issues = validate_manifest_dict(clean_manifest)
    v25_issues = [i for i in issues if i.get("rule") == "V25"]
    assert v25_issues == [], f"V25 must not fire on clean manifest; got {v25_issues}"
