"""Tests for enhanced ui.Image."""
from imperal_sdk import ui


def test_image_on_click():
    node = ui.Image(src="/img.png", on_click=ui.Open(url="/img.png"))
    d = node.to_dict()
    assert d["props"]["on_click"]["action"] == "open"


def test_image_object_fit():
    node = ui.Image(src="/img.png", object_fit="cover")
    d = node.to_dict()
    assert d["props"]["object_fit"] == "cover"


def test_image_caption():
    node = ui.Image(src="/img.png", caption="Photo 1")
    d = node.to_dict()
    assert d["props"]["caption"] == "Photo 1"


def test_image_backward_compat():
    node = ui.Image(src="/img.png", alt="test", width="200")
    d = node.to_dict()
    assert d["props"]["src"] == "/img.png"
    assert d["props"]["alt"] == "test"
    assert "on_click" not in d["props"]
    assert "object_fit" not in d["props"]
    assert "caption" not in d["props"]
