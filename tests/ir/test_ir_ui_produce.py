# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""TDD — Task E2: generate_ir populates app.ui.panels.

Runtime panel (no tree=) → render.kind=="code", entry=="__panel__<id>"
Static panel  (tree=UINode) → render.kind=="static", tree non-empty dict.
"""
import pytest

from imperal_sdk import Extension, ui
from imperal_sdk.chat.extension import ChatExtension
from imperal_sdk.ir.produce import generate_ir
from imperal_sdk.ir.validator import validate_ir_dict


def _make_ext_with_panels():
    ext = Extension(app_id="panel_test", version="1.0.0", display_name="Panel Test")
    ChatExtension(ext, description="Panel test chat extension")

    @ext.panel("runtime_dash", slot="center", title="Dashboard")
    async def runtime_panel(ctx, **params):  # pragma: no cover
        return ui.Card(title="Live Dashboard")

    @ext.panel("static_help", slot="right", title="Help", tree=ui.Card(title="Help Panel"))
    async def static_panel(ctx, **params):  # pragma: no cover
        return None

    return ext


@pytest.fixture
def toy_ext_with_panels():
    return _make_ext_with_panels()


def test_runtime_panel_becomes_code_pointer(toy_ext_with_panels):
    ir = generate_ir(toy_ext_with_panels)
    panels = {p["panel_id"]: p for p in ir["app"]["ui"]["panels"]}
    assert panels["runtime_dash"]["render"]["kind"] == "code"
    assert panels["runtime_dash"]["render"]["entry"] == "__panel__runtime_dash"
    assert panels["runtime_dash"]["render"]["module"] == "panels"


def test_static_panel_becomes_static_render(toy_ext_with_panels):
    ir = generate_ir(toy_ext_with_panels)
    panels = {p["panel_id"]: p for p in ir["app"]["ui"]["panels"]}
    assert panels["static_help"]["render"]["kind"] == "static"
    assert isinstance(panels["static_help"]["render"]["tree"], dict)
    assert panels["static_help"]["render"]["tree"]  # non-empty


def test_panels_slot_and_title_preserved(toy_ext_with_panels):
    ir = generate_ir(toy_ext_with_panels)
    panels = {p["panel_id"]: p for p in ir["app"]["ui"]["panels"]}
    assert panels["runtime_dash"]["slot"] == "center"
    assert panels["runtime_dash"]["title"] == "Dashboard"
    assert panels["static_help"]["slot"] == "right"
    assert panels["static_help"]["title"] == "Help"


def test_validate_ir_dict_clean_for_panels_ext(toy_ext_with_panels):
    ir = generate_ir(toy_ext_with_panels)
    issues = validate_ir_dict(ir)
    assert issues == [], f"Unexpected IR validation issues: {issues}"


def test_no_ui_when_no_panels():
    ext = Extension(app_id="no_panels", version="1.0.0", display_name="No Panels")
    chat = ChatExtension(ext, description="No panels ext")

    @chat.function(name="ping", description="Ping")
    async def ping(ctx, params):  # pragma: no cover
        return None

    ir = generate_ir(ext)
    # ui key must be absent (or None) when no panels declared
    assert ir["app"].get("ui") is None
