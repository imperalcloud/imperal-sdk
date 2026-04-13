"""Tests for enhanced ui.FileUpload."""
from imperal_sdk import ui


def test_fileupload_blocked_extensions():
    node = ui.FileUpload(blocked_extensions=["exe", "bat"])
    d = node.to_dict()
    assert d["props"]["blocked_extensions"] == ["exe", "bat"]


def test_fileupload_max_total():
    node = ui.FileUpload(max_total_mb=25, max_files=10)
    d = node.to_dict()
    assert d["props"]["max_total_mb"] == 25
    assert d["props"]["max_files"] == 10


def test_fileupload_backward_compat():
    node = ui.FileUpload(accept="image/*", max_size_mb=5, multiple=True)
    d = node.to_dict()
    assert d["props"]["accept"] == "image/*"
    assert d["props"]["max_size_mb"] == 5
    assert d["props"]["multiple"] is True
    assert "blocked_extensions" not in d["props"]
    assert "max_total_mb" not in d["props"]
