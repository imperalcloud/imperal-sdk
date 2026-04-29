# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for @ext.panel() decorator and panel metadata."""
import pytest
from imperal_sdk.extension import Extension


class TestPanelDecorator:
    def test_registers_tool(self):
        ext = Extension("test-app")
        @ext.panel("sidebar", slot="left", title="Nav", icon="Menu")
        async def sidebar(ctx): pass
        assert "__panel__sidebar" in ext.tools
        assert ext.tools["__panel__sidebar"].name == "__panel__sidebar"

    def test_stores_metadata(self):
        ext = Extension("test-app")
        @ext.panel("sidebar", slot="left", title="Nav", icon="Menu",
                   default_width=300, min_width=220, max_width=520,
                   refresh="on_event:scan.completed")
        async def sidebar(ctx): pass
        meta = ext.panels["sidebar"]
        assert meta["slot"] == "left"
        assert meta["title"] == "Nav"
        assert meta["icon"] == "Menu"
        assert meta["default_width"] == 300
        assert meta["min_width"] == 220
        assert meta["max_width"] == 520
        assert meta["refresh"] == "on_event:scan.completed"

    def test_multiple_panels(self):
        ext = Extension("test-app")
        @ext.panel("sidebar", slot="left", title="Left")
        async def left(ctx): pass
        @ext.panel("stats", slot="right", title="Right")
        async def right(ctx): pass
        assert len(ext.panels) == 2
        assert "sidebar" in ext.panels
        assert "stats" in ext.panels

    def test_default_slot(self):
        ext = Extension("test-app")
        @ext.panel("main_view")
        async def view(ctx): pass
        assert ext.panels["main_view"]["slot"] == "main"

    def test_default_refresh(self):
        ext = Extension("test-app")
        @ext.panel("dash", slot="left")
        async def dash(ctx): pass
        assert ext.panels["dash"]["refresh"] == "manual"

    def test_panels_property(self):
        ext = Extension("test-app")
        @ext.panel("sidebar", slot="left", title="Side")
        async def side(ctx): pass
        assert ext.panels == ext._panels

    def test_preserves_original_function(self):
        ext = Extension("test-app")
        @ext.panel("sidebar", slot="left")
        async def my_panel(ctx): pass
        assert my_panel.__name__ == "my_panel"

    def test_kwargs_stored(self):
        """Extra kwargs passed to @ext.panel are stored in metadata."""
        ext = Extension("test-app")
        @ext.panel("sidebar", slot="left", custom_flag=True, priority=5)
        async def sidebar(ctx): pass
        assert ext.panels["sidebar"]["custom_flag"] is True
        assert ext.panels["sidebar"]["priority"] == 5


class TestPanelWrapper:
    @pytest.mark.asyncio
    async def test_wrapper_returns_ui_dict(self):
        from imperal_sdk import ui
        ext = Extension("test-app")
        @ext.panel("sidebar", slot="left")
        async def sidebar(ctx):
            return ui.Stack([ui.Text("hello")])
        # Call the registered tool wrapper (not the original function)
        wrapper = ext.tools["__panel__sidebar"].func
        result = await wrapper(None)
        assert result["panel_id"] == "sidebar"
        assert result["ui"]["type"] == "Stack"

    @pytest.mark.asyncio
    async def test_wrapper_passes_params(self):
        ext = Extension("test-app")
        received = {}
        @ext.panel("sidebar", slot="left")
        async def sidebar(ctx, section="default", **kwargs):
            received["section"] = section
            received["kwargs"] = kwargs
            return {"test": True}
        wrapper = ext.tools["__panel__sidebar"].func
        await wrapper(None, section="users", extra="val")
        assert received["section"] == "users"
        assert received["kwargs"]["extra"] == "val"


# --- LLM-FU follow-up: slot whitelist validation (3.4.0) ---

from imperal_sdk.types.contributions import Panel, ALLOWED_PANEL_SLOTS


class TestPanelDataclassSlotValidation:
    def test_default_slot_is_center(self):
        p = Panel(id="p1", title="P")
        assert p.slot == "center"

    def test_known_slots_accepted(self):
        for s in ("center", "left", "right", "overlay", "bottom", "chat-sidebar"):
            Panel(id="p", title="P", slot=s)  # must not raise

    def test_main_rejected(self):
        with pytest.raises(ValueError) as exc:
            Panel(id="inbox", title="Inbox", slot="main")
        msg = str(exc.value)
        assert "main" in msg
        assert "center" in msg
        assert "3.4.0" in msg

    def test_garbage_rejected(self):
        with pytest.raises(ValueError) as exc:
            Panel(id="p", title="P", slot="middle")
        assert "middle" in str(exc.value)

    def test_allowed_panel_slots_is_frozenset(self):
        assert isinstance(ALLOWED_PANEL_SLOTS, frozenset)
        assert "center" in ALLOWED_PANEL_SLOTS
        assert "main" not in ALLOWED_PANEL_SLOTS
