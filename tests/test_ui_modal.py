"""ui.Modal — the overlay window primitive, and its legacy ui.Dialog alias.

Background (2026-08-15, owner call): the primitive was called ``ui.Dialog``,
which is the wrong word — a "dialog" is the native browser <dialog>/confirm
concept, while this is a MODAL WINDOW. It was renamed to ``ui.Modal``; the old
name stays as a deprecated alias so shipped extensions keep working.

The single most important thing these tests protect is the alias WIRE TYPE:
``ui.Dialog`` must keep emitting ``type="Dialog"``, never "Modal". Four live
extensions still call it (youtube-studio-hub, content-strategy-app,
sharelock-v2, media-studio), and a panel that has not shipped the new renderer
only knows the "dialog" key. Rewiring the alias would blank their overlays.
"""
from __future__ import annotations

import pytest

from imperal_sdk import ui


# --------------------------------------------------------------------------
# The alias contract — the part that must never regress
# --------------------------------------------------------------------------

def test_dialog_alias_still_emits_the_legacy_wire_type():
    """ui.Dialog -> type "Dialog". NOT "Modal". This is load-bearing."""
    assert ui.Dialog(title="Connect").to_dict()["type"] == "Dialog"


def test_modal_emits_the_new_wire_type():
    assert ui.Modal(title="Connect").to_dict()["type"] == "Modal"


def test_alias_and_canonical_agree_on_everything_but_the_type():
    """Same arguments must produce the same props through either name."""
    kwargs = dict(title="Settings", confirm_label="", cancel_label="Close")
    modal = ui.Modal(**kwargs).to_dict()
    dialog = ui.Dialog(**kwargs).to_dict()
    assert modal["props"] == dialog["props"]
    assert modal["type"] != dialog["type"]


def test_alias_accepts_the_new_sizing_knobs_too():
    """Legacy callers can opt into sizing without renaming their code."""
    props = ui.Dialog(title="Wide", size="xl").to_dict()["props"]
    assert props["size"] == "xl"


def test_both_names_are_exported():
    assert "Modal" in ui.__all__
    assert "Dialog" in ui.__all__


# --------------------------------------------------------------------------
# Sizing — bug #9: centre overlays were stuck at one hard-coded width
# --------------------------------------------------------------------------

def test_default_size_is_not_sent_on_the_wire():
    """md is the renderer default; sending it would just be noise."""
    assert "size" not in ui.Modal(title="X").to_dict()["props"]


@pytest.mark.parametrize("size", ["xs", "sm", "md", "lg", "xl", "2xl", "full"])
def test_every_named_size_is_accepted(size):
    node = ui.Modal(title="X", size=size).to_dict()
    if size == "md":
        assert "size" not in node["props"]
    else:
        assert node["props"]["size"] == size


def test_named_sizes_are_published_for_introspection():
    assert ui.MODAL_SIZES == ("xs", "sm", "md", "lg", "xl", "2xl", "full")


def test_unknown_size_is_rejected_loudly():
    """A typo must fail here, not silently render at the wrong width."""
    with pytest.raises(ValueError) as err:
        ui.Modal(title="X", size="huge")
    assert "huge" in str(err.value)


def test_max_width_accepts_any_css_length():
    for value in ("600px", "40rem", "80%", "min(100vw, 50rem)"):
        assert ui.Modal(title="X", max_width=value).to_dict()["props"]["max_width"] == value


def test_max_width_and_size_can_coexist_the_renderer_prefers_max_width():
    props = ui.Modal(title="X", size="sm", max_width="70%").to_dict()["props"]
    assert props["size"] == "sm" and props["max_width"] == "70%"


# --------------------------------------------------------------------------
# Buttons — the empty-blue-button bug
# --------------------------------------------------------------------------

def test_empty_confirm_label_survives_serialization():
    """youtube-studio-hub passes confirm_label="" to mean "no button".

    UINode.to_dict() drops None but MUST keep "" — otherwise the renderer sees
    undefined, applies its own default, and paints a blank primary button.
    """
    props = ui.Modal(title="X", confirm_label="", cancel_label="Close").to_dict()["props"]
    assert props["confirm_label"] == ""
    assert props["cancel_label"] == "Close"


def test_both_labels_blank_is_a_bare_modal():
    props = ui.Modal(title="X", confirm_label="", cancel_label="").to_dict()["props"]
    assert props["confirm_label"] == "" and props["cancel_label"] == ""


# --------------------------------------------------------------------------
# Content and behaviour
# --------------------------------------------------------------------------

def test_content_node_is_serialized_recursively():
    node = ui.Modal(title="X", content=ui.Text("hello")).to_dict()
    assert node["props"]["content"]["type"] == "Text"


def test_subtitle_is_optional_and_omitted_when_blank():
    assert "subtitle" not in ui.Modal(title="X").to_dict()["props"]
    assert ui.Modal(title="X", subtitle="s").to_dict()["props"]["subtitle"] == "s"


def test_dismissible_only_travels_when_disabled():
    """True is the renderer default — only the deviation is worth sending."""
    assert "dismissible" not in ui.Modal(title="X").to_dict()["props"]
    assert ui.Modal(title="X", dismissible=False).to_dict()["props"]["dismissible"] is False


def test_open_only_travels_when_closed():
    assert "open" not in ui.Modal(title="X").to_dict()["props"]
    assert ui.Modal(title="X", open=False).to_dict()["props"]["open"] is False


def test_actions_are_serialized():
    node = ui.Modal(
        title="X",
        on_confirm=ui.Call("save", id="1"),
        on_close=ui.Call("dismiss"),
    ).to_dict()
    # UIAction serializes under the "action" key (see ui/base.py), not "type" —
    # "type" belongs to UINode.
    assert node["props"]["on_confirm"]["action"] == "call"
    assert node["props"]["on_confirm"]["function"] == "save"
    assert node["props"]["on_close"]["action"] == "call"


def test_title_may_be_omitted_for_a_chromeless_modal():
    """Not every overlay wants a header bar."""
    assert "title" not in ui.Modal().to_dict()["props"]
