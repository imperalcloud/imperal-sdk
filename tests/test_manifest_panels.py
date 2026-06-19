# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
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
