"""Tests for UI contribution types."""
import pytest
from imperal_sdk.types.contributions import (
    Panel, Widget, Command, ContextMenu, Setting, Theme,
)


class TestPanel:
    def test_basic(self):
        p = Panel(id="deals", title="Deal Pipeline")
        assert p.id == "deals"
        assert p.title == "Deal Pipeline"
        assert p.slot == "center"
        assert p.movable is True

    def test_full(self):
        p = Panel(
            id="inbox", title="Inbox", icon="mail", slot="left",
            permissions=["email:read"], context_trigger="email.selected",
            badge="unread_count",
        )
        assert p.slot == "left"
        assert p.permissions == ["email:read"]
        assert p.badge == "unread_count"


class TestWidget:
    def test_basic(self):
        w = Widget(id="deal-stats", slot="dashboard.stats")
        assert w.id == "deal-stats"
        assert w.slot == "dashboard.stats"
        assert w.size == "md"


class TestCommand:
    def test_basic(self):
        c = Command(id="crm.new-deal", title="New Deal", shortcut="Ctrl+Shift+D")
        assert c.id == "crm.new-deal"
        assert c.shortcut == "Ctrl+Shift+D"


class TestContextMenu:
    def test_basic(self):
        m = ContextMenu(slot="chat.message", label="Reply")
        assert m.slot == "chat.message"
        assert m.separator_before is False


class TestSetting:
    def test_string(self):
        s = Setting(id="api_url", type="string", label="API URL", required=True)
        assert s.type == "string"
        assert s.required is True

    def test_select(self):
        s = Setting(
            id="theme", type="select", label="Theme",
            options=[{"value": "dark", "label": "Dark"}, {"value": "light", "label": "Light"}],
            default="dark",
        )
        assert len(s.options) == 2

    def test_number(self):
        s = Setting(id="timeout", type="number", label="Timeout", min=1, max=60, default=30)
        assert s.min == 1
        assert s.max == 60

    def test_admin_only(self):
        s = Setting(id="secret", type="secret", label="API Key", admin_only=True)
        assert s.admin_only is True


class TestTheme:
    def test_defaults(self):
        t = Theme()
        assert t.dark_mode is True
        assert t.border_radius == "md"

    def test_custom(self):
        t = Theme(accent_color="#4F46E5", chat_bubble_style="card")
        assert t.accent_color == "#4F46E5"
