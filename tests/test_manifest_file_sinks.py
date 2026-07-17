# Copyright (c) 2026 Imperal, Inc.
# Licensed under the Apache-2.0 License.
"""File Mage L3 — file_sinks manifest contract + @ext.file_sink + V35."""
import pytest

from imperal_sdk.extension import Extension
from imperal_sdk.manifest import generate_manifest
from imperal_sdk.manifest_schema import FileSink, validate_manifest_dict
from imperal_sdk.validator import validate_extension


def _errors(issues):
    return [i for i in issues
            if str(getattr(i, "level", getattr(i, "severity", ""))).upper() == "ERROR"]


def _base(**extra):
    d = {"manifest_schema_version": 3, "app_id": "notes", "version": "1.0.0",
         "capabilities": ["store:read"],
         "tools": [{"name": "create_note", "description": "x" * 40}]}
    d.update(extra)
    return d


# ---- Task 1: FileSink model + manifest field ----

def test_valid_file_sink_accepted():
    m = _base(file_sinks=[{"tool": "create_note", "accepts": ["application/pdf", "text/*"],
                           "arg": "body", "arg_kind": "text", "description": "note from a doc"}])
    assert _errors(validate_manifest_dict(m)) == []


def test_bad_arg_kind_rejected():
    m = _base(file_sinks=[{"tool": "create_note", "accepts": ["text/*"],
                           "arg": "body", "arg_kind": "blob"}])
    assert _errors(validate_manifest_dict(m))


def test_empty_accepts_rejected():
    m = _base(file_sinks=[{"tool": "create_note", "accepts": [], "arg": "body"}])
    assert _errors(validate_manifest_dict(m))


def test_file_sink_model_forbids_extra():
    with pytest.raises(Exception):
        FileSink(tool="t", accepts=["text/*"], arg="body", bogus=1)


# ---- Task 2: decorator + serialize + V35 ----

def test_decorator_registers_and_serializes():
    ext = Extension("notes", version="1.0.0")

    @ext.tool("create_note")
    async def create_note(ctx):
        ...
    ext.file_sink("create_note", accepts=["text/*"], arg="body",
                  arg_kind="text", description="d")
    mf = generate_manifest(ext)
    assert mf["file_sinks"] and mf["file_sinks"][0]["tool"] == "create_note"
    assert mf["file_sinks"][0]["arg_kind"] == "text"


def test_file_sinks_property():
    ext = Extension("notes", version="1.0.0")

    @ext.tool("create_note")
    async def create_note(ctx):
        ...
    ext.file_sink("create_note", accepts=["text/*"], arg="body")
    assert len(ext.file_sinks) == 1 and ext.file_sinks[0].tool == "create_note"


def test_duplicate_sink_rejected():
    ext = Extension("notes", version="1.0.0")

    @ext.tool("create_note")
    async def create_note(ctx):
        ...
    ext.file_sink("create_note", accepts=["text/*"], arg="body")
    with pytest.raises(ValueError):
        ext.file_sink("create_note", accepts=["text/*"], arg="title")


def test_v35_rejects_sink_referencing_unknown_tool():
    ext = Extension("notes", version="1.0.0")

    @ext.tool("create_note")
    async def create_note(ctx):
        ...
    ext.file_sink("nonexistent_tool", accepts=["text/*"], arg="body")
    report = validate_extension(ext)
    v35 = [i for i in report.issues if i.rule == "V35"]
    assert v35 and v35[0].level == "ERROR"


def test_v35_passes_for_valid_sink():
    ext = Extension("notes", version="1.0.0")

    @ext.tool("create_note")
    async def create_note(ctx):
        ...
    ext.file_sink("create_note", accepts=["text/*"], arg="body")
    report = validate_extension(ext)
    assert [i for i in report.issues if i.rule == "V35"] == []
