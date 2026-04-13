"""Tests for ui.Html component."""
from imperal_sdk import ui


def test_html_basic():
    node = ui.Html(content="<p>Hello</p>")
    d = node.to_dict()
    assert d["type"] == "Html"
    assert d["props"]["content"] == "<p>Hello</p>"
    assert d["props"]["sandbox"] is True


def test_html_no_sandbox():
    node = ui.Html(content="<b>Bold</b>", sandbox=False)
    d = node.to_dict()
    assert d["props"]["sandbox"] is False


def test_html_max_height():
    node = ui.Html(content="<p>Hi</p>", max_height=500)
    d = node.to_dict()
    assert d["props"]["max_height"] == 500


def test_html_max_height_zero_omitted():
    node = ui.Html(content="<p>Hi</p>", max_height=0)
    d = node.to_dict()
    assert "max_height" not in d["props"]
