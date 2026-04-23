# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Test emit_narration wiring in SDK chat handler.

Covers P2 Task 18 — EMIT_NARRATION_TOOL schema + Pydantic parser for the
Federal-Grade Chat Integrity plan (spec §3.2).
"""
import pytest

from imperal_sdk.chat.narration import (
    EMIT_NARRATION_TOOL,
    NarrationEmission,
    PerCallVerdict,
    TaskTargets,
    parse_narration_emission,
)


def test_tool_name_and_shape():
    assert EMIT_NARRATION_TOOL["name"] == "emit_narration"
    s = EMIT_NARRATION_TOOL["input_schema"]
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {"mode", "prose", "per_call_verdicts", "task_targets"}


def test_oai_strict_eligible_at_top_level():
    """No maxLength/minLength/pattern/format/maximum/multipleOf/minItems/maxItems at top level."""
    import json
    blob = json.dumps(EMIT_NARRATION_TOOL["input_schema"])
    banned = ["maxLength", "minLength", "pattern", "format",
              "maximum", "multipleOf", "minItems", "maxItems"]
    for kw in banned:
        assert f'"{kw}"' not in blob, f"Unsupported OAI-strict keyword {kw} present"


def test_verdict_item_has_required_fields():
    item = EMIT_NARRATION_TOOL["input_schema"]["properties"]["per_call_verdicts"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == {"call_index", "name", "status", "user_phrasing"}


def test_mode_enum_exact():
    mode = EMIT_NARRATION_TOOL["input_schema"]["properties"]["mode"]
    assert set(mode["enum"]) == {"audit", "narrative"}


def test_status_enum_exact():
    s = EMIT_NARRATION_TOOL["input_schema"]["properties"]["per_call_verdicts"]["items"]["properties"]["status"]
    assert set(s["enum"]) == {"success", "error", "intercepted"}


def test_parse_minimal_valid():
    em = parse_narration_emission({
        "mode": "audit", "prose": "done.",
        "per_call_verdicts": [],
        "task_targets": {"expected": None, "succeeded": 0},
    })
    assert em.mode == "audit"
    assert em.per_call_verdicts == ()
    assert em.task_targets.expected is None


def test_parse_full_valid():
    em = parse_narration_emission({
        "mode": "audit", "prose": "2 actions.",
        "per_call_verdicts": [
            {"call_index": 0, "name": "send", "status": "success", "user_phrasing": "sent to a@b.c"},
            {"call_index": 1, "name": "send", "status": "error", "user_phrasing": "missing body"},
        ],
        "task_targets": {"expected": 2, "succeeded": 1},
        "identifiers_used": ["a@b.c"],
    })
    assert len(em.per_call_verdicts) == 2
    assert em.per_call_verdicts[0].status == "success"
    assert em.task_targets.succeeded == 1
    assert em.identifiers_used == ("a@b.c",)


def test_parse_rejects_invalid_mode():
    with pytest.raises(Exception):
        parse_narration_emission({"mode": "narrative_foo", "prose": "x",
                                  "per_call_verdicts": [],
                                  "task_targets": {"expected": None, "succeeded": 0}})


def test_parse_rejects_negative_call_index():
    with pytest.raises(Exception):
        parse_narration_emission({
            "mode": "audit", "prose": "x",
            "per_call_verdicts": [{"call_index": -1, "name": "x",
                                    "status": "success", "user_phrasing": "y"}],
            "task_targets": {"expected": None, "succeeded": 0},
        })


def test_parse_rejects_extra_top_level():
    with pytest.raises(Exception):
        parse_narration_emission({
            "mode": "audit", "prose": "x",
            "per_call_verdicts": [], "task_targets": {"expected": None, "succeeded": 0},
            "sneaky_extra_key": "oh no",
        })


def test_emission_frozen():
    em = parse_narration_emission({
        "mode": "audit", "prose": "x",
        "per_call_verdicts": [], "task_targets": {"expected": None, "succeeded": 0},
    })
    with pytest.raises(Exception):
        em.prose = "mutated"
