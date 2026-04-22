"""Tests for @ext.skeleton decorator and V13 skeleton-naming validator rule.

Ships in imperal-sdk v1.5.22 alongside the kernel-side skeleton auto-derive
convention (I-SKEL-AUTO-DERIVE-1). The SDK side is pure sugar + validation;
the actual section registration happens in the kernel when it inspects the
extension's tool list.
"""
from __future__ import annotations

import pytest

from imperal_sdk import Extension, validate_extension


def test_skeleton_registers_prefixed_tool():
    ext = Extension(app_id="web-tools", version="1.0.0")

    @ext.skeleton("web_tools")
    async def refresh_web_tools(ctx) -> dict:
        return {"response": {"total": 0}}

    assert "skeleton_refresh_web_tools" in ext.tools
    tool = ext.tools["skeleton_refresh_web_tools"]
    assert tool.name == "skeleton_refresh_web_tools"
    assert tool.description.startswith("Skeleton refresh:")


def test_skeleton_respects_custom_description():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.skeleton("notes", description="Note counts digest")
    async def r(ctx):
        return {"response": {}}

    assert ext.tools["skeleton_refresh_notes"].description == "Note counts digest"


def test_skeleton_metadata_exposed():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.skeleton("monitors", alert=True, ttl=60)
    async def r(ctx):
        return {"response": {}}

    tool = ext.tools["skeleton_refresh_monitors"]
    meta = getattr(tool, "_skeleton", None)
    assert meta is not None
    assert meta["section_name"] == "monitors"
    assert meta["alert_on_change"] is True
    assert meta["ttl"] == 60


def test_skeleton_defaults_ttl_300():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.skeleton("foo")
    async def r(ctx):
        return {"response": {}}

    meta = getattr(ext.tools["skeleton_refresh_foo"], "_skeleton")
    assert meta["ttl"] == 300
    assert meta["alert_on_change"] is False


def test_skeleton_preserves_function():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.skeleton("bar")
    async def refresh_bar(ctx):
        """Docstring stays."""
        return {"response": {"ok": True}}

    assert refresh_bar.__name__ == "refresh_bar"
    assert refresh_bar.__doc__ == "Docstring stays."


def test_skeleton_rejects_empty_section():
    ext = Extension(app_id="x", version="1.0.0")
    with pytest.raises(ValueError):
        @ext.skeleton("")
        async def r(ctx):
            return {}


def test_skeleton_rejects_wildcards_and_separators():
    ext = Extension(app_id="x", version="1.0.0")
    for bad in ("a*b", "a?b", "a[b]", "a:b", "a/b"):
        with pytest.raises(ValueError, match="wildcard/separator"):
            @ext.skeleton(bad)
            async def r(ctx):
                return {}


def test_skeleton_multiple_sections_coexist():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.skeleton("section_a")
    async def ra(ctx):
        return {"response": {}}

    @ext.skeleton("section_b", alert=True)
    async def rb(ctx):
        return {"response": {}}

    assert "skeleton_refresh_section_a" in ext.tools
    assert "skeleton_refresh_section_b" in ext.tools
    assert ext.tools["skeleton_refresh_section_a"]._skeleton["alert_on_change"] is False
    assert ext.tools["skeleton_refresh_section_b"]._skeleton["alert_on_change"] is True


# ---------------------------------------------------------------------
# V13 validator rule — warn on bare "refresh_" without skeleton_ prefix
# ---------------------------------------------------------------------


def test_v13_warns_on_bare_refresh_prefix():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.tool("refresh_stuff", description="badly-named skeleton refresh")
    async def r(ctx):
        return {"response": {}}

    report = validate_extension(ext)
    v13 = [i for i in report.issues if i.rule == "V13"]
    assert len(v13) >= 1
    assert any("skeleton_refresh_stuff" in (i.fix or "") for i in v13)
    assert any("@ext.skeleton" in (i.fix or "") for i in v13)


def test_v13_silent_on_correctly_prefixed():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.skeleton("good_section")
    async def r(ctx):
        return {"response": {}}

    report = validate_extension(ext)
    v13 = [i for i in report.issues if i.rule == "V13"]
    assert v13 == []


def test_v13_also_flags_bare_alert_prefix():
    ext = Extension(app_id="x", version="1.0.0")

    @ext.tool("alert_thing", description="bad alert name")
    async def r(ctx):
        return {"response": {}}

    report = validate_extension(ext)
    v13 = [i for i in report.issues if i.rule == "V13"]
    assert len(v13) >= 1
    assert any("skeleton_alert_thing" in (i.fix or "") for i in v13)
