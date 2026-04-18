# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for `imperal_sdk.manifest_schema` — the JSON Schema contract.

Covers:
- Every rule code (M1..M5) fires on the expected input
- Every real production manifest shape validates clean
- `get_schema()` exports a stable Draft 2020-12 JSON Schema
- `generate_manifest()` output round-trips through `validate_manifest_dict`
- Exported static `imperal.schema.json` matches the runtime schema
"""
import json
from pathlib import Path

import pytest

from imperal_sdk import Extension
from imperal_sdk.manifest import generate_manifest
from imperal_sdk.manifest_schema import (
    MANIFEST_SCHEMA,
    Manifest,
    get_schema,
    validate_manifest_dict,
)


# --- Valid baseline -------------------------------------------------

BASE = {
    "app_id": "my-app",
    "version": "1.0.0",
    "capabilities": [],
    "tools": [],
    "signals": [],
    "schedules": [],
    "required_scopes": [],
}


def test_valid_minimal_manifest():
    assert validate_manifest_dict(BASE) == []


def test_valid_full_manifest():
    m = {
        **BASE,
        "tools": [
            {
                "name": "tool_chat",
                "description": "Main chat entry",
                "scopes": ["my-app:*"],
                "parameters": {
                    "message": {"type": "string", "required": False},
                    "kwargs": {"type": "string", "required": True},
                },
            }
        ],
        "signals": [{"name": "on_login"}],
        "schedules": [{"name": "daily", "cron": "0 9 * * *"}],
        "required_scopes": ["my-app:*"],
        "migrations_dir": "./migrations",
        "config_defaults": {"models": {"primary": "claude-opus"}},
        "name": "My App",
        "description": "Marketplace description",
        "author": "Me",
        "license": "AGPL-3.0",
        "category": "productivity",
        "tags": ["a", "b"],
    }
    assert validate_manifest_dict(m) == []


# --- Rule coverage (one test per code) ------------------------------

def test_M1_root_not_dict():
    issues = validate_manifest_dict(["not", "a", "dict"])
    assert len(issues) == 1
    assert issues[0].rule == "M1"


def test_M2_missing_required_app_id():
    bad = {k: v for k, v in BASE.items() if k != "app_id"}
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M2" and "app_id" in i.message for i in issues)


def test_M3_typo_schedule_singular():
    bad = {**BASE, "schedule": []}  # singular typo
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M3" and "schedule" in i.message for i in issues)


def test_M3_typo_tool_singular():
    bad = {**BASE, "tool": []}
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M3" for i in issues)


def test_M4_bad_app_id_uppercase():
    bad = {**BASE, "app_id": "MyApp"}
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M4" and "app_id" in i.message for i in issues)


def test_M4_bad_app_id_underscore():
    bad = {**BASE, "app_id": "my_app"}
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M4" for i in issues)


def test_M4_bad_version_not_semver():
    bad = {**BASE, "version": "v1"}
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M4" and "version" in i.message for i in issues)


def test_M4_bad_required_scope():
    bad = {**BASE, "required_scopes": ["Not A Scope"]}
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M4" for i in issues)


def test_M5_bad_cron():
    bad = {**BASE, "schedules": [{"name": "daily", "cron": "not-cron"}]}
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M5" and "cron" in i.message for i in issues)


def test_M5_bad_tool_scope():
    bad = {
        **BASE,
        "tools": [{"name": "t", "scopes": ["Not Valid"], "parameters": {}}],
    }
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M5" for i in issues)


def test_M5_bad_param_type():
    bad = {
        **BASE,
        "tools": [{
            "name": "t",
            "scopes": [],
            "parameters": {"x": {"type": "unknown_type", "required": True}},
        }],
    }
    issues = validate_manifest_dict(bad)
    assert any(i.rule == "M5" for i in issues)


# --- Cron / scope accepted forms -----------------------------------

@pytest.mark.parametrize("cron", [
    "0 9 * * *",
    "*/5 * * * *",
    "0 0 1 * *",
    "@hourly", "@daily", "@weekly", "@monthly", "@yearly", "@reboot",
])
def test_valid_cron_expressions(cron):
    m = {**BASE, "schedules": [{"name": "s", "cron": cron}]}
    assert validate_manifest_dict(m) == []


@pytest.mark.parametrize("scope", [
    "*",              # umbrella
    "notes:*",        # namespace umbrella
    "notes:read",     # colon form
    "notes.read",     # legacy dot form
    "admin:audit:read",  # multi-segment colon
])
def test_valid_scope_forms(scope):
    m = {
        **BASE,
        "tools": [{"name": "t", "scopes": [scope], "parameters": {}}],
    }
    assert validate_manifest_dict(m) == []


# --- Round-trip: generated manifest validates clean ----------------

def test_generate_manifest_output_validates():
    ext = Extension("round-trip", version="1.0.0")

    @ext.tool("t1", scopes=["round-trip:*"], description="desc")
    async def t1(ctx, x: str):
        pass

    @ext.schedule("daily", cron="0 9 * * *")
    async def daily(ctx):
        pass

    manifest = generate_manifest(ext)
    assert validate_manifest_dict(manifest) == []


# --- Schema export -------------------------------------------------

def test_get_schema_is_json_schema():
    schema = get_schema()
    assert schema["$id"] == "https://imperal.io/schemas/imperal.schema.json"
    assert schema["title"] == "Imperal Extension Manifest"
    # Pydantic v2 emits Draft 2020-12 by default
    assert "$defs" in schema
    assert "properties" in schema
    for required_field in ("app_id", "version"):
        assert required_field in schema["properties"]


def test_manifest_schema_constant_equals_get_schema():
    assert MANIFEST_SCHEMA == get_schema()


def test_static_schema_file_in_sync():
    """The committed JSON Schema file must match the runtime schema.

    Regenerate via:
      python -c 'from imperal_sdk.manifest_schema import get_schema; \
                 import json; print(json.dumps(get_schema(), indent=2))' \
        > src/imperal_sdk/schemas/imperal.schema.json
    """
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "imperal_sdk" / "schemas" / "imperal.schema.json"
    )
    assert schema_path.exists(), f"Missing schema file at {schema_path}"
    on_disk = json.loads(schema_path.read_text())
    assert on_disk == get_schema(), (
        "Static imperal.schema.json is out of sync with runtime schema. "
        "Regenerate it (see docstring)."
    )


# --- Pydantic model smoke ------------------------------------------

def test_manifest_model_validates_baseline():
    # Direct pydantic usage should also work — not just the wrapper.
    Manifest.model_validate(BASE)
