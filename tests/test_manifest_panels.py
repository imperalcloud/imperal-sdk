# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Ф2 — ui.* surface inside the imperal.json contract.

Task 1 covers the manifest_schema UINode/Panel models (validate Input.type
against the single Ф1 INPUT_TYPES source). Task 2 covers the additive
generate_manifest() 'panels' emission + round-trip through validate_manifest_dict.
"""
import pytest

from imperal_sdk.manifest_schema import Panel, UINode
from imperal_sdk.ui.input_components import INPUT_TYPES


def test_uinode_input_password_type_validates():
    node = UINode.model_validate(
        {"type": "Input", "props": {"type": "password", "param_name": "value"}}
    )
    assert node.type == "Input"
    assert node.props["type"] == "password"


def test_uinode_input_phone_type_raises_clear_error():
    with pytest.raises(ValueError) as exc:
        UINode.model_validate(
            {"type": "Input", "props": {"type": "phone"}}
        )
    msg = str(exc.value)
    assert "phone" in msg
    # Error names the single source set so the author can self-correct.
    assert "password" in msg and "text" in msg


def test_uinode_non_input_type_not_constrained():
    # Only Input nodes carry the closed type enum; a Stack with an
    # arbitrary 'type' prop must pass untouched.
    node = UINode.model_validate(
        {"type": "Stack", "props": {"type": "whatever"}}
    )
    assert node.props["type"] == "whatever"


def test_uinode_input_default_type_absent_is_text_ok():
    # ui.Input(type="text") omits props['type'] (see input_components.py:24);
    # an Input node with no explicit type must validate.
    node = UINode.model_validate({"type": "Input", "props": {"placeholder": "x"}})
    assert node.type == "Input"


def test_uinode_input_all_valid_types_validate():
    # Every value in INPUT_TYPES must validate (they are the single source).
    for t in INPUT_TYPES:
        node = UINode.model_validate(
            {"type": "Input", "props": {"type": t}}
        )
        assert node.props["type"] == t


def test_panel_slot_must_be_allowed():
    p = Panel.model_validate(
        {"slot": "left", "tree": {"type": "Stack", "props": {}}, "panel_id": "nav"}
    )
    assert p.slot == "left"
    with pytest.raises(ValueError) as exc:
        Panel.model_validate(
            {"slot": "nowhere", "tree": {"type": "Stack", "props": {}}}
        )
    assert "nowhere" in str(exc.value)


def test_input_types_is_single_source():
    # Guard: the schema must not re-declare its own copy of the enum.
    assert INPUT_TYPES == ("text", "password", "email", "number", "url")


def test_panel_tree_with_invalid_input_type_raises():
    # A Panel whose tree is an Input with an illegal type must fail validation.
    with pytest.raises(ValueError) as exc:
        Panel.model_validate(
            {
                "slot": "left",
                "tree": {"type": "Input", "props": {"type": "phone"}},
            }
        )
    assert "phone" in str(exc.value)


def test_panel_tree_with_valid_input_type_validates():
    p = Panel.model_validate(
        {
            "slot": "center",
            "tree": {"type": "Input", "props": {"type": "email"}},
            "panel_id": "search",
        }
    )
    assert p.slot == "center"


# --- Task 2: additive generate_manifest() 'panels' emission ---------------

from imperal_sdk import Extension
from imperal_sdk import ui
from imperal_sdk.manifest import generate_manifest
from imperal_sdk.manifest_schema import validate_manifest_dict


def test_manifest_without_panels_is_additive_and_tools_unchanged():
    ext = Extension("no-panel-app", version="2.0.0")

    @ext.tool("hello", scopes=["public"], description="hi")
    async def hello(ctx, name: str = "World"):
        pass

    manifest = generate_manifest(ext)
    # Additive: key present, empty — proves stable shape, no panels declared.
    assert manifest["panels"] == []
    # No regression on the tools surface.
    assert len(manifest["tools"]) == 1
    assert manifest["tools"][0]["name"] == "hello"


def test_manifest_with_static_tree_panel_emits_slot_and_tree():
    ext = Extension("panel-app", version="1.0.0")

    tree = ui.Form(
        children=[ui.Password(param_name="api_key")],
        action="app/save",
    )

    @ext.panel("creds", slot="right", title="Credentials", tree=tree)
    async def creds(ctx):
        return tree

    manifest = generate_manifest(ext)
    panels = manifest["panels"]
    entry = next(p for p in panels if p["panel_id"] == "creds")
    assert entry["slot"] == "right"
    assert entry["title"] == "Credentials"
    # Serialized UINode tree — a real Form wrapping a password Input.
    assert entry["tree"]["type"] == "Form"
    pw = entry["tree"]["props"]["children"][0]
    assert pw["type"] == "Input"
    assert pw["props"]["type"] == "password"


def test_manifest_panel_without_tree_emits_empty_tree():
    ext = Extension("panel-app2", version="1.0.0")

    @ext.panel("nav", slot="left", title="Nav")
    async def nav(ctx):
        return ui.Stack([])

    manifest = generate_manifest(ext)
    entry = next(p for p in manifest["panels"] if p["panel_id"] == "nav")
    assert entry["slot"] == "left"
    assert entry["tree"] == {}


def test_panels_manifest_round_trips_through_validate():
    ext = Extension("panel-app3", version="1.0.0")
    tree = ui.Form(children=[ui.Input(param_name="x", type="password")])

    @ext.panel("creds", slot="right", title="Creds", tree=tree)
    async def creds(ctx):
        return tree

    manifest = generate_manifest(ext)
    issues = validate_manifest_dict(manifest)
    # No M3 extra_forbidden for the new 'panels' key; no other issues.
    assert issues == [], [i.message for i in issues]


def test_panels_manifest_rejects_illegal_input_type():
    manifest = {
        "manifest_schema_version": 3,
        "app_id": "bad-panel-app",
        "version": "1.0.0",
        "panels": [
            {
                "slot": "right",
                "panel_id": "creds",
                "title": "Creds",
                "tree": {"type": "Input", "props": {"type": "phone"}},
            }
        ],
    }
    issues = validate_manifest_dict(manifest)
    assert issues, "expected a validation issue for the illegal Input.type"
    joined = " ".join(i.message for i in issues)
    assert "phone" in joined
