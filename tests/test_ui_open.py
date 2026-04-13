"""Tests for ui.Open action."""
from imperal_sdk import ui


def test_open_basic():
    action = ui.Open(url="https://accounts.google.com/oauth")
    d = action.to_dict()
    assert d["action"] == "open"
    assert d["url"] == "https://accounts.google.com/oauth"


def test_open_in_button():
    btn = ui.Button("Login", on_click=ui.Open(url="https://example.com"))
    d = btn.to_dict()
    click = d["props"]["on_click"]
    assert click["action"] == "open"
    assert click["url"] == "https://example.com"
