# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for P4 Task 43 — HUB_DISPATCH_TOOL schema.

Invariants covered:
  - I-EXT-TOOL-ISOLATION (shape contribution)
  - I-HUB-DISPATCH-NO-CYCLE (shape-only; runtime guard in handler)
"""
import json

from imperal_sdk.chat.kernel_primitives import (
    HUB_DISPATCH_TOOL,
    is_hub_dispatch_tool_use,
)


def test_tool_name_is_hub_dispatch():
    assert HUB_DISPATCH_TOOL["name"] == "hub_dispatch"


def test_schema_oai_strict_top_level():
    s = HUB_DISPATCH_TOOL["input_schema"]
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {"app_id", "reasoning", "query"}
    for prop in s["properties"]:
        assert prop in s["required"]


def test_schema_no_unsupported_keywords():
    blob = json.dumps(HUB_DISPATCH_TOOL["input_schema"])
    banned = [
        "maxLength",
        "minLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "multipleOf",
        "minItems",
        "maxItems",
    ]
    for kw in banned:
        assert f'"{kw}"' not in blob, f"schema must not contain {kw}"


def test_is_hub_dispatch_tool_use_positive():
    assert is_hub_dispatch_tool_use("hub_dispatch") is True


def test_is_hub_dispatch_tool_use_negative():
    assert is_hub_dispatch_tool_use("emit_narration") is False
    assert is_hub_dispatch_tool_use("send") is False
    assert is_hub_dispatch_tool_use("") is False


def test_description_mentions_depth_limit():
    desc = HUB_DISPATCH_TOOL["description"]
    assert "depth" in desc.lower()
    assert "3" in desc  # numeric depth


def test_required_properties_all_string_type():
    props = HUB_DISPATCH_TOOL["input_schema"]["properties"]
    for name in ("app_id", "reasoning", "query"):
        assert props[name]["type"] == "string"


def test_top_level_object_type():
    assert HUB_DISPATCH_TOOL["input_schema"]["type"] == "object"


def test_schema_is_json_serializable():
    # Federal forensics requires schema to round-trip through JSON.
    blob = json.dumps(HUB_DISPATCH_TOOL)
    roundtrip = json.loads(blob)
    assert roundtrip["name"] == "hub_dispatch"
    assert roundtrip["input_schema"]["additionalProperties"] is False
