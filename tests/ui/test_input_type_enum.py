"""Ф1 — ui.Input.type is a code-enforced closed enum (single source INPUT_TYPES)."""
from __future__ import annotations

import pytest

from imperal_sdk import ui
from imperal_sdk.ui.input_components import INPUT_TYPES


def test_input_types_is_the_canonical_set() -> None:
    assert INPUT_TYPES == ("text", "password", "email", "number", "url")


def test_input_default_type_is_text_and_omitted_from_props() -> None:
    node = ui.Input(placeholder="Name")
    # default "text" is not serialized into props (matches pre-existing behaviour)
    assert "type" not in node.props


@pytest.mark.parametrize("t", list(INPUT_TYPES))
def test_every_valid_type_is_accepted(t: str) -> None:
    node = ui.Input(placeholder="x", type=t)
    if t == "text":
        assert "type" not in node.props
    else:
        assert node.props["type"] == t


def test_invalid_type_raises_valueerror() -> None:
    with pytest.raises(ValueError) as exc:
        ui.Input(placeholder="x", type="checkbox")
    msg = str(exc.value)
    assert "ui.Input type must be one of" in msg
    assert "'checkbox'" in msg


def test_password_wrapper_still_pins_password_type() -> None:
    node = ui.Password(placeholder="secret")
    assert node.props["type"] == "password"
