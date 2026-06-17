"""SDK v5.0.1 — Federal Typed Return Contract.

Tests for the ``data_model=`` kwarg on ``@chat.function`` and the V23/V24
validator rules introduced in 5.0.1.
"""
from __future__ import annotations

import os
import warnings

import pytest
from pydantic import BaseModel

from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension
from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk.validator import validate_extension


# ── Fixtures ──────────────────────────────────────────────────────────


class NoteRecord(BaseModel):
    """Sample data_model — typed return shape for note reads."""
    note_id: str
    title: str
    content: str
    folder_id: str | None = None


class ListNotesParams(BaseModel):
    """Sample input params model."""
    folder_id: str | None = None
    limit: int = 50


class CreateNoteParams(BaseModel):
    title: str
    content: str
    folder_id: str | None = None


def _make_ext():
    """Build a minimal Extension instance that passes V1-V22 unrelated checks."""
    ext = Extension(
        app_id="notes",
        version="1.0.0",
        display_name="Notes",
        description="Personal notes with folders, tags, and full-text search.",
        icon="icon.svg",
    )
    return ext


def _make_chat(ext):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return ChatExtension(ext, tool_name="notes_chat", description="notes")


# ── data_model kwarg propagation ──────────────────────────────────────


def test_data_model_kwarg_populates_return_model():
    """``data_model=NoteRecord`` MUST land in FunctionDef._return_model."""
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="get_note",
        description="Get a single note by ID (read tool returns NoteRecord)",
        action_type="read",
        data_model=NoteRecord,
    )
    async def get_note(ctx, params: ListNotesParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    fn = chat.functions["get_note"]
    assert fn._return_model is NoteRecord


def test_data_model_wins_over_return_annotation():
    """Explicit ``data_model`` kwarg MUST override ``-> ActionResult[T]`` autodetect."""
    ext = _make_ext()
    chat = _make_chat(ext)

    class OtherRecord(BaseModel):
        x: int

    @chat.function(
        name="get_note_two",
        description="Demonstrates data_model precedence over return annotation",
        action_type="read",
        data_model=NoteRecord,
    )
    async def get_note(ctx, params: ListNotesParams) -> ActionResult[OtherRecord]:
        return ActionResult.success(data={}, summary="ok")

    fn = chat.functions["get_note_two"]
    # data_model (NoteRecord) wins, not the annotation (OtherRecord)
    assert fn._return_model is NoteRecord


def test_actionresult_generic_autodetect_when_no_data_model():
    """Without ``data_model=``, ``-> ActionResult[T]`` MUST be detected."""
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="get_note_three",
        description="Demonstrates ActionResult[T] generic autodetection",
        action_type="read",
    )
    async def get_note(ctx, params: ListNotesParams) -> ActionResult[NoteRecord]:
        return ActionResult.success(data={}, summary="ok")

    fn = chat.functions["get_note_three"]
    assert fn._return_model is NoteRecord


def test_data_model_none_means_no_return_model():
    """Read with no data_model and no generic MUST leave _return_model=None."""
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="get_note_four",
        description="Reads without explicit return typing",
        action_type="read",
    )
    async def get_note(ctx, params: ListNotesParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    fn = chat.functions["get_note_four"]
    assert fn._return_model is None


# ── V23 (read) — data_model presence required ─────────────────────────


def test_v23_warn_when_read_missing_data_model(monkeypatch):
    """``IMPERAL_VALIDATOR_V23_SEVERITY=warn`` (explicit opt-out) MUST emit WARN."""
    monkeypatch.setenv("IMPERAL_VALIDATOR_V23_SEVERITY", "warn")
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="list_notes",
        description="List notes — read tool deliberately missing data_model",
        action_type="read",
    )
    async def list_notes(ctx, params: ListNotesParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    v23 = [i for i in report.issues if i.rule == "V23"]
    assert len(v23) == 1
    assert v23[0].level == "WARN"
    assert "data_model" in v23[0].message


def test_v23_error_by_default(monkeypatch):
    """P5-final (2026-06-17): with the env unset, V23 defaults to ERROR."""
    monkeypatch.delenv("IMPERAL_VALIDATOR_V23_SEVERITY", raising=False)
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="list_notes",
        description="List notes — read tool deliberately missing data_model",
        action_type="read",
    )
    async def list_notes(ctx, params: ListNotesParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    v23 = [i for i in report.errors if i.rule == "V23"]
    assert len(v23) == 1
    assert "data_model" in v23[0].message


def test_v23_error_when_severity_env_set(monkeypatch):
    """``IMPERAL_VALIDATOR_V23_SEVERITY=error`` MUST promote to ERROR."""
    monkeypatch.setenv("IMPERAL_VALIDATOR_V23_SEVERITY", "error")
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="list_notes",
        description="List notes — read tool deliberately missing data_model",
        action_type="read",
    )
    async def list_notes(ctx, params: ListNotesParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    v23 = [i for i in report.errors if i.rule == "V23"]
    assert len(v23) == 1
    assert "data_model" in v23[0].message


def test_v23_skips_ui_builder(monkeypatch):
    """``ui_builder=True`` read tools are exempt from V23 even at severity=error."""
    monkeypatch.setenv("IMPERAL_VALIDATOR_V23_SEVERITY", "error")
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="get_panel_data",
        description="Declarative-UI builder — exempt from V23 via ui_builder flag",
        action_type="read",
        ui_builder=True,
    )
    async def get_panel_data(ctx, params: ListNotesParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    assert not [i for i in report.issues if i.rule == "V23"]


def test_v23_passes_when_data_model_declared():
    """Reads with ``data_model=`` MUST NOT trigger V23."""
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="list_notes",
        description="List notes — read tool with explicit data_model declaration",
        action_type="read",
        data_model=NoteRecord,
    )
    async def list_notes(ctx, params: ListNotesParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    assert not [i for i in report.issues if i.rule == "V23"]


def test_v23_passes_with_generic_actionresult():
    """``-> ActionResult[T]`` MUST satisfy V23 without explicit data_model."""
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="list_notes",
        description="List notes — read tool with ActionResult[T] generic",
        action_type="read",
    )
    async def list_notes(ctx, params: ListNotesParams) -> ActionResult[NoteRecord]:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    assert not [i for i in report.issues if i.rule == "V23"]


# ── V24 (write/destructive) — data_model recommended WARN-only ────────


def test_v24_warn_when_write_missing_data_model():
    """Write tool without data_model MUST emit V24 WARN."""
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="create_note",
        description="Create a new note — write tool deliberately missing data_model",
        action_type="write",
        event="notes.created",
    )
    async def create_note(ctx, params: CreateNoteParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    v24 = [i for i in report.warnings if i.rule == "V24"]
    assert len(v24) == 1


def test_v24_warn_when_destructive_missing_data_model():
    """Destructive tool without data_model MUST emit V24 WARN."""
    ext = _make_ext()
    chat = _make_chat(ext)

    class DeleteParams(BaseModel):
        note_id: str

    @chat.function(
        name="delete_note",
        description="Delete a note — destructive tool deliberately missing data_model",
        action_type="destructive",
        event="notes.deleted",
    )
    async def delete_note(ctx, params: DeleteParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    v24 = [i for i in report.warnings if i.rule == "V24"]
    assert len(v24) == 1


def test_v24_passes_when_data_model_declared():
    """Writes with ``data_model=`` MUST NOT trigger V24."""
    ext = _make_ext()
    chat = _make_chat(ext)

    @chat.function(
        name="create_note",
        description="Create a new note — write tool with explicit data_model",
        action_type="write",
        event="notes.created",
        data_model=NoteRecord,
    )
    async def create_note(ctx, params: CreateNoteParams) -> ActionResult:
        return ActionResult.success(data={}, summary="ok")

    report = validate_extension(ext)
    assert not [i for i in report.warnings if i.rule == "V24"]


# ── ActionResult.validate_against ─────────────────────────────────────


def test_validate_against_passes_on_matching_dict():
    """``validate_against`` MUST silently pass on a dict that matches the model."""
    ar = ActionResult.success(
        data={"note_id": "n1", "title": "T", "content": "C"},
        summary="ok",
    )
    result = ar.validate_against(NoteRecord)
    assert result is ar  # no-op return


def test_validate_against_warns_on_mismatched_dict(caplog):
    """``validate_against`` MUST log WARN on mismatched dict and not raise."""
    import logging
    ar = ActionResult.success(
        data={"note_id": "n1", "title": "T"},  # missing required `content`
        summary="ok",
    )
    with caplog.at_level(logging.WARNING, logger="imperal_sdk.action_result"):
        result = ar.validate_against(NoteRecord)
    assert result is ar
    assert any("data_model mismatch" in r.message for r in caplog.records)


def test_validate_against_passes_when_data_is_model_instance():
    """When data is already a model instance, ``validate_against`` MUST no-op."""
    note = NoteRecord(note_id="n1", title="T", content="C")
    ar = ActionResult.success(data=note, summary="ok")
    result = ar.validate_against(NoteRecord)
    assert result is ar
