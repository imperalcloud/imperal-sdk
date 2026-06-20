"""Tests for IRPanel / IR UI models (Task E1)."""
import pytest
from pydantic import ValidationError

from imperal_sdk.ir.ui import IRPanel


def test_static_panel_roundtrips():
    p = IRPanel.model_validate({
        "panel_id": "dash", "slot": "center", "title": "Dash",
        "render": {"kind": "static", "tree": {"type": "Card", "props": {"title": "Hi"}}},
    })
    assert p.render.kind == "static"
    assert p.render.tree["type"] == "Card"


def test_bad_slot_rejected():
    with pytest.raises(ValidationError):
        IRPanel.model_validate({"panel_id": "x", "slot": "nope",
                                "render": {"kind": "static", "tree": {}}})


def test_all_valid_slots_accepted():
    from imperal_sdk.types.contributions import ALLOWED_PANEL_SLOTS
    for slot in ALLOWED_PANEL_SLOTS:
        p = IRPanel.model_validate({
            "panel_id": "test", "slot": slot,
            "render": {"kind": "static", "tree": {}},
        })
        assert p.slot == slot


def test_render_template_roundtrips():
    p = IRPanel.model_validate({
        "panel_id": "tpl", "slot": "left",
        "render": {"kind": "template", "tree": {"type": "List", "props": {}}},
    })
    assert p.render.kind == "template"


def test_render_code_roundtrips():
    p = IRPanel.model_validate({
        "panel_id": "code_panel", "slot": "right",
        "render": {"kind": "code", "module": "my_ext.panels", "entry": "MyPanel"},
    })
    assert p.render.kind == "code"
    assert p.render.module == "my_ext.panels"
    assert p.render.entry == "MyPanel"


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        IRPanel.model_validate({
            "panel_id": "x", "slot": "center",
            "render": {"kind": "static", "tree": {}},
            "unexpected_field": "boom",
        })


def test_title_and_icon_optional():
    p = IRPanel.model_validate({
        "panel_id": "minimal", "slot": "bottom",
        "render": {"kind": "static", "tree": {}},
    })
    assert p.title == ""
    assert p.icon == ""


def test_invalid_render_kind_rejected():
    with pytest.raises(ValidationError):
        IRPanel.model_validate({
            "panel_id": "x", "slot": "center",
            "render": {"kind": "unknown", "tree": {}},
        })
