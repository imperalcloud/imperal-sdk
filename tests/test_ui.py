# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for Declarative UI components — serialization, props, actions."""
import pytest
from imperal_sdk import ui
from imperal_sdk.ui.base import UINode


# ── Layout ────────────────────────────────────────────────────────────


class TestStack:
    def test_default_props(self):
        node = ui.Stack([])
        d = node.to_dict()
        assert d["type"] == "Stack"
        assert d["props"]["direction"] == "v"
        assert d["props"]["gap"] == 3

    def test_horizontal_with_wrap(self):
        node = ui.Stack([], direction="h", gap=2, wrap=True)
        d = node.to_dict()
        assert d["props"]["direction"] == "h"
        assert d["props"]["wrap"] is True

    def test_wrap_default_not_emitted(self):
        # wrap=None (default) must not emit the prop, so Panel can apply its
        # direction-specific default (horizontal auto-wraps since session 33).
        node = ui.Stack([], direction="h")
        d = node.to_dict()
        assert "wrap" not in d["props"]

    def test_wrap_false_explicit_emitted(self):
        # wrap=False MUST be emitted so a horizontal Stack can opt out of the
        # Panel-side auto-wrap default. Regression guard for SDK < 1.5.16 where
        # False was silently dropped and the opt-out was unreachable.
        node = ui.Stack([], direction="h", wrap=False)
        d = node.to_dict()
        assert d["props"]["wrap"] is False

    def test_align_justify(self):
        node = ui.Stack([], align="center", justify="between")
        d = node.to_dict()
        assert d["props"]["align"] == "center"
        assert d["props"]["justify"] == "between"

    def test_children_serialized(self):
        child = ui.Text("hello")
        node = ui.Stack([child])
        d = node.to_dict()
        assert len(d["props"]["children"]) == 1
        assert d["props"]["children"][0]["type"] == "Text"


class TestGrid:
    def test_defaults(self):
        d = ui.Grid([]).to_dict()
        assert d["props"]["columns"] == 2
        assert d["props"]["gap"] == 3


class TestTabs:
    def test_structure(self):
        d = ui.Tabs([{"label": "A", "content": ui.Text("a")}]).to_dict()
        assert d["type"] == "Tabs"
        assert d["props"]["default_tab"] == 0
        assert d["props"]["tabs"][0]["label"] == "A"


class TestSection:
    def test_collapsible(self):
        d = ui.Section([ui.Text("x")], title="Info", collapsible=True).to_dict()
        assert d["props"]["title"] == "Info"
        assert d["props"]["collapsible"] is True


class TestRowColumn:
    def test_row_is_horizontal_stack(self):
        d = ui.Row([]).to_dict()
        assert d["type"] == "Stack"
        assert d["props"]["direction"] == "h"

    def test_column_is_vertical_stack(self):
        d = ui.Column([]).to_dict()
        assert d["type"] == "Stack"
        assert d["props"]["direction"] == "v"


class TestAccordion:
    def test_structure(self):
        d = ui.Accordion([{"id": "a", "title": "A", "children": []}]).to_dict()
        assert d["type"] == "Accordion"
        assert d["props"]["allow_multiple"] is False


class TestPage:
    def test_with_title(self):
        d = ui.Page([ui.Text("body")], title="Home", subtitle="Welcome").to_dict()
        assert d["props"]["title"] == "Home"
        assert d["props"]["subtitle"] == "Welcome"


# ── Display ───────────────────────────────────────────────────────────


class TestText:
    def test_variants(self):
        for v in ("heading", "body", "caption", "code"):
            d = ui.Text("x", variant=v).to_dict()
            assert d["props"]["variant"] == v

    def test_default_body(self):
        d = ui.Text("hello").to_dict()
        assert d["props"]["variant"] == "body"
        assert d["props"]["content"] == "hello"


class TestHeader:
    def test_levels(self):
        d = ui.Header("Title", level=3, subtitle="Sub").to_dict()
        assert d["props"]["text"] == "Title"
        assert d["props"]["level"] == 3
        assert d["props"]["subtitle"] == "Sub"


class TestDivider:
    def test_with_label(self):
        d = ui.Divider(label="OR").to_dict()
        assert d["props"]["label"] == "OR"

    def test_empty(self):
        d = ui.Divider().to_dict()
        assert d["type"] == "Divider"


class TestEmpty:
    def test_with_icon(self):
        d = ui.Empty(message="No data", icon="inbox").to_dict()
        assert d["props"]["message"] == "No data"
        assert d["props"]["icon"] == "inbox"


# ── Interactive ───────────────────────────────────────────────────────


class TestButton:
    def test_variants(self):
        for v in ("primary", "secondary", "ghost", "danger"):
            d = ui.Button("Click", variant=v).to_dict()
            assert d["props"]["variant"] == v

    def test_size(self):
        d = ui.Button("X", size="sm").to_dict()
        assert d["props"]["size"] == "sm"

    def test_on_click_action(self):
        d = ui.Button("Go", on_click=ui.Call("do_thing", id="1")).to_dict()
        assert d["props"]["on_click"]["function"] == "do_thing"
        assert d["props"]["on_click"]["params"]["id"] == "1"


class TestCard:
    def test_with_content(self):
        d = ui.Card(title="Info", content=ui.Text("body")).to_dict()
        assert d["props"]["title"] == "Info"
        assert d["props"]["content"]["type"] == "Text"


class TestSlideOver:
    def test_width(self):
        d = ui.SlideOver("Panel", width="lg").to_dict()
        assert d["props"]["width"] == "lg"
        assert d["props"]["open"] is True


# ── Input ─────────────────────────────────────────────────────────────


class TestInput:
    def test_param_name(self):
        d = ui.Input(placeholder="Name", param_name="username").to_dict()
        assert d["props"]["param_name"] == "username"
        assert d["props"]["placeholder"] == "Name"

    def test_no_label_prop(self):
        """SDK Input does NOT have label parameter."""
        with pytest.raises(TypeError):
            ui.Input(label="Name")


class TestToggle:
    def test_default_false(self):
        d = ui.Toggle(label="Enable").to_dict()
        assert d["props"]["value"] is False
        assert d["props"]["param_name"] == "enabled"

    def test_true_value(self):
        d = ui.Toggle(label="Active", value=True).to_dict()
        assert d["props"]["value"] is True


class TestSelect:
    def test_options(self):
        opts = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]
        d = ui.Select(options=opts, value="a").to_dict()
        assert len(d["props"]["options"]) == 2
        assert d["props"]["value"] == "a"

    def test_no_label_prop(self):
        """SDK Select does NOT have label parameter."""
        with pytest.raises(TypeError):
            ui.Select(options=[], label="Pick")


class TestForm:
    def test_structure(self):
        d = ui.Form(
            children=[ui.Input(placeholder="x")],
            action="save",
            submit_label="Save",
            defaults={"name": "test"},
        ).to_dict()
        assert d["type"] == "Form"
        assert d["props"]["action"] == "save"
        assert d["props"]["submit_label"] == "Save"
        assert d["props"]["defaults"]["name"] == "test"


class TestTagInput:
    def test_grouped_by(self):
        d = ui.TagInput(values=["a:b"], suggestions=["a:c"], grouped_by=":").to_dict()
        assert d["props"]["grouped_by"] == ":"
        assert d["props"]["values"] == ["a:b"]


class TestRichEditor:
    def test_toolbar(self):
        d = ui.RichEditor(content="<p>hi</p>", toolbar=False).to_dict()
        assert d["props"]["toolbar"] is False
        assert d["props"]["content"] == "<p>hi</p>"


# ── Data Display ──────────────────────────────────────────────────────


class TestStat:
    def test_color(self):
        d = ui.Stat(label="Users", value="42", color="green").to_dict()
        assert d["props"]["color"] == "green"
        assert d["props"]["label"] == "Users"

    def test_no_trend_direction_prop(self):
        """SDK Stat does NOT have trend_direction parameter."""
        with pytest.raises(TypeError):
            ui.Stat(label="X", value=0, trend_direction="up")


class TestStats:
    def test_auto_columns(self):
        d = ui.Stats([ui.Stat(label="A", value=1)]).to_dict()
        assert d["type"] == "Stats"
        # columns=0 means auto, prop not set when 0
        assert "columns" not in d["props"] or d["props"]["columns"] == 0


class TestListItem:
    def test_expandable(self):
        d = ui.ListItem(
            id="1", title="Item",
            expandable=True,
            expanded_content=[ui.Text("details")],
        ).to_dict()
        assert d["props"]["expandable"] is True
        assert len(d["props"]["expanded_content"]) == 1

    def test_badge(self):
        d = ui.ListItem(
            id="1", title="X",
            badge=ui.Badge("Active", color="green"),
        ).to_dict()
        assert d["props"]["badge"]["type"] == "Badge"


class TestList:
    def test_searchable(self):
        d = ui.List([], searchable=True, page_size=20).to_dict()
        assert d["props"]["searchable"] is True
        assert d["props"]["page_size"] == 20


class TestKeyValue:
    def test_columns(self):
        d = ui.KeyValue([{"key": "A", "value": "1"}], columns=2).to_dict()
        assert d["props"]["columns"] == 2


class TestDataTable:
    def test_column_helper(self):
        col = ui.DataColumn("name", "Name", editable=True, edit_type="text")
        assert col["key"] == "name"
        assert col["editable"] is True

    def test_table(self):
        d = ui.DataTable(
            columns=[ui.DataColumn("id", "ID")],
            rows=[{"id": "1"}],
        ).to_dict()
        assert d["type"] == "DataTable"


class TestBadge:
    def test_colors(self):
        for c in ("blue", "red", "green", "yellow", "gray"):
            d = ui.Badge("X", color=c).to_dict()
            assert d["props"]["color"] == c


# ── Feedback ──────────────────────────────────────────────────────────


class TestAlert:
    def test_types(self):
        for t in ("info", "success", "warn", "error"):
            d = ui.Alert(message="msg", type=t).to_dict()
            assert d["props"]["type"] == t


class TestChart:
    def test_chart_type_prop(self):
        """Chart Python param is 'type', serialized as 'chart_type' in JSON."""
        d = ui.Chart(data=[], type="bar", x_key="date").to_dict()
        assert d["props"]["chart_type"] == "bar"


class TestLoading:
    def test_variants(self):
        d = ui.Loading(message="Wait...", variant="skeleton").to_dict()
        assert d["props"]["variant"] == "skeleton"


class TestError:
    def test_with_retry(self):
        d = ui.Error(message="Failed", retry=ui.Call("retry")).to_dict()
        assert d["props"]["retry"]["function"] == "retry"


# ── Actions ───────────────────────────────────────────────────────────


class TestActions:
    def test_call(self):
        a = ui.Call("delete", id="123")
        d = a.to_dict()
        assert d["function"] == "delete"
        assert d["params"]["id"] == "123"

    def test_navigate(self):
        a = ui.Navigate("/settings")
        d = a.to_dict()
        assert d["path"] == "/settings"

    def test_send(self):
        a = ui.Send("hello")
        d = a.to_dict()
        assert d["message"] == "hello"


# ── UINode serialization ─────────────────────────────────────────────


class TestUINode:
    def test_to_dict(self):
        node = UINode(type="Custom", props={"foo": "bar"})
        d = node.to_dict()
        assert d == {"type": "Custom", "props": {"foo": "bar"}}

    def test_nested_serialization(self):
        inner = ui.Text("child")
        outer = ui.Stack([inner])
        d = outer.to_dict()
        assert d["props"]["children"][0]["props"]["content"] == "child"
