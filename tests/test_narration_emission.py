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


def test_mode_description_scope_clause_present():
    """v4.1.1: mode field description must explicitly scope-restrict audit
    semantics to the prose field only — not to other tools' content fields.
    Without this, BYOLLM LLMs interpret 'audit mode' globally and emit
    placeholders like '<essay 200 words>' in create_note.content_text."""
    mode_desc = EMIT_NARRATION_TOOL["input_schema"]["properties"]["mode"]["description"]
    assert "SCOPE" in mode_desc, "mode description must explicitly mark scope"
    assert "Other tool calls" in mode_desc, "must reference other tool calls explicitly"
    assert "FULL user-requested content" in mode_desc, (
        "must instruct LLM to write full content in non-narration tools"
    )


def test_chat_function_id_projection_kwarg_propagated():
    """v4.1.2 (NEW-5): @chat.function id_projection kwarg flows into FunctionDef
    and through manifest serialization so kernel can wire ext-declared
    target field for chain-step projection (e.g. delete_notes_from_folder
    -> id_projection='folder_id' instead of heuristic's notes_from_folder_id)."""
    from imperal_sdk.chat.extension import ChatExtension, FunctionDef
    from imperal_sdk.extension import Extension

    ext = Extension(app_id="notes_test", display_name="Notes Test", description="x" * 30)
    chat = ChatExtension(ext, tool_name="tool_notes_chat",
                         description="Notes test chat tool — minimal fixture for projection")

    @chat.function(
        "delete_notes_from_folder",
        description="Delete every note inside the given folder by folder_id",
        action_type="destructive",
        id_projection="folder_id",
    )
    async def _h(ctx, params):
        return None

    fn = chat._functions["delete_notes_from_folder"]
    assert isinstance(fn, FunctionDef)
    assert fn.id_projection == "folder_id"


def test_chat_function_id_projection_default_empty():
    """v4.1.2: id_projection defaults to empty string when not provided —
    backward-compat for legacy ext authors who haven't migrated."""
    from imperal_sdk.chat.extension import ChatExtension
    from imperal_sdk.extension import Extension

    ext = Extension(app_id="notes_test2", display_name="Notes Test 2", description="x" * 30)
    chat = ChatExtension(ext, tool_name="tool_notes_chat2",
                         description="Notes test chat tool 2 — minimal fixture for default check")

    @chat.function("delete_note", description="Delete a single note by note_id")
    async def _h(ctx, params):
        return None

    fn = chat._functions["delete_note"]
    assert fn.id_projection == ""


def test_prose_description_warns_against_placeholders():
    """v4.1.1: prose field description must call out placeholder anti-pattern
    (e.g. '<essay 200 words>') so LLM knows brevity rule applies only here."""
    prose_desc = EMIT_NARRATION_TOOL["input_schema"]["properties"]["prose"]["description"]
    assert "CRITICAL" in prose_desc
    assert "placeholders" in prose_desc.lower()
    assert "create_note.content_text" in prose_desc, (
        "concrete example must be present so LLM grounds the rule"
    )


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
