# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
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

    # ── direction spelling ────────────────────────────────────────────
    # The long forms are not invented sugar: 20 call sites across the shipped
    # extensions already write direction="horizontal"/"vertical". They used to
    # travel unnormalised and silently lay out the wrong way round.

    @pytest.mark.parametrize("spelling", ["horizontal", "HORIZONTAL", " row ", "row"])
    def test_horizontal_synonyms_normalise(self, spelling):
        assert ui.Stack([], direction=spelling).to_dict()["props"]["direction"] == "h"

    @pytest.mark.parametrize("spelling", ["vertical", "column", "col", "V"])
    def test_vertical_synonyms_normalise(self, spelling):
        assert ui.Stack([], direction=spelling).to_dict()["props"]["direction"] == "v"

    def test_canonical_spellings_untouched(self):
        assert ui.Stack([], direction="h").to_dict()["props"]["direction"] == "h"
        assert ui.Stack([], direction="v").to_dict()["props"]["direction"] == "v"

    def test_unknown_direction_raises_instead_of_laying_out_wrong(self):
        # A typo must fail here, loudly, rather than reach the renderer and
        # quietly stack the wrong way with no clue why.
        with pytest.raises(ValueError) as err:
            ui.Stack([], direction="verticl")
        assert "verticl" in str(err.value)

    def test_row_and_column_helpers_still_agree(self):
        # Row/Column are thin wrappers; normalisation must not shift them.
        assert ui.Row([]).to_dict()["props"]["direction"] == "h"
        assert ui.Column([]).to_dict()["props"]["direction"] == "v"


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

    def test_labeled_variant(self):
        """SDK Input supports the LABELED variant (system requirement).

        Was previously asserted as *absent*; the renderer had read `label`,
        `description`, `error`, `required` for a long time, so extensions
        simply could not reach a labeled field. Now they can — and the
        label-less shape must keep serializing exactly as before.
        """
        props = ui.Input(
            label="Contract amount",
            placeholder="e.g. 500.00",
            description="Empty = use the plan price.",
            required=True,
        ).to_dict()["props"]
        assert props["label"] == "Contract amount"
        assert props["description"] == "Empty = use the plan price."
        assert props["required"] is True
        # A placeholder never replaces a label — both travel together.
        assert props["placeholder"] == "e.g. 500.00"

    def test_unlabeled_variant_is_byte_identical(self):
        """The label-less input is untouched: no new keys on the wire."""
        assert ui.Input(placeholder="Name").to_dict()["props"] == {
            "placeholder": "Name", "value": "", "param_name": "value",
        }

    def test_variant_is_validated(self):
        with pytest.raises(ValueError):
            ui.Input(variant="fancy")


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

    def test_labeled_variant(self):
        """SDK Select supports the LABELED variant (system requirement)."""
        props = ui.Select(
            options=[{"value": "card", "label": "Card"}],
            label="How they pay",
            description="Enterprise may settle by invoice.",
            required=True,
        ).to_dict()["props"]
        assert props["label"] == "How they pay"
        assert props["required"] is True

    def test_unlabeled_variant_is_byte_identical(self):
        assert ui.Select(options=[]).to_dict()["props"] == {
            "options": [], "value": "", "param_name": "value",
        }


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

    def test_trend_direction_and_description(self):
        """Stat can say WHICH WAY a trend points — up is not always good.

        Rising spend is bad, rising revenue is good, so direction is explicit
        rather than inferred from the trend string.
        """
        props = ui.Stat(
            label="Spent", value="34,287,494", trend="+12%",
            trend_direction="up", description="net of refunds", color="red",
        ).to_dict()["props"]
        assert props["trend_direction"] == "up"
        assert props["description"] == "net of refunds"
        assert props["color"] == "red"

    def test_direction_is_validated(self):
        with pytest.raises(ValueError):
            ui.Stat(label="X", value=0, trend_direction="sideways")


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
    def test_severity_reaches_the_renderer(self):
        """Severity must land on `variant` — the prop the renderer reads.

        `Alert(type="error")` used to serialize a prop nothing consumed, so a
        red warning silently rendered as a blue "info" notice. The legacy
        spelling still works and is now translated instead of dropped.
        """
        for severity in ("info", "success", "warn", "error"):
            legacy = ui.Alert(message="msg", type=severity).to_dict()["props"]
            modern = ui.Alert(message="msg", variant=severity).to_dict()["props"]
            assert legacy["variant"] == severity
            assert modern["variant"] == severity
            assert "type" not in legacy  # the dead prop is gone from the wire

    def test_unambiguous_synonyms_are_normalised(self):
        """`warning`/`danger` are normalised, not rejected.

        Found live: ext-admin shipped `Alert(type="warning")` in four places.
        The renderer only ever knew "warn", so those warnings had been
        rendering as blue "info" banners the whole time. Rejecting the synonym
        would break working panels over a spelling everyone reasonably expects
        to work; normalising it makes the banner finally turn yellow.
        """
        for given, expected in (("warning", "warn"), ("danger", "error"),
                                ("err", "error"), ("ok", "success")):
            assert ui.Alert("m", type=given).to_dict()["props"]["variant"] == expected
            assert ui.Alert("m", variant=given).to_dict()["props"]["variant"] == expected

    def test_a_real_typo_still_raises(self):
        """Only unambiguous aliases are accepted. Guessing what a developer
        meant is how a red alert quietly becomes a green one."""
        for bad in ("critical", "warnign", "fatal"):
            with pytest.raises(ValueError):
                ui.Alert("m", variant=bad)

    def test_unknown_severity_is_caught(self):
        with pytest.raises(ValueError):
            ui.Alert(message="msg", variant="critical")


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
