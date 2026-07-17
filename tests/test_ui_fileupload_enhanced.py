"""Tests for enhanced ui.FileUpload."""
import pytest

from imperal_sdk import ui


def test_fileupload_presentational_props():
    node = ui.FileUpload(
        title="Upload documents",
        hint="PDF, DOCX or images",
        variant="futuristic",
        show_previews=True,
    )
    d = node.to_dict()
    assert d["props"]["title"] == "Upload documents"
    assert d["props"]["hint"] == "PDF, DOCX or images"
    assert d["props"]["variant"] == "futuristic"
    assert d["props"]["show_previews"] is True


def test_fileupload_default_variant_omitted():
    # Presentational hints stay out of the wire when at their defaults, so old
    # renderers see the same payload they always did (to_dict drops None too).
    node = ui.FileUpload()
    d = node.to_dict()
    assert "variant" not in d["props"]
    assert "title" not in d["props"]
    assert "hint" not in d["props"]
    assert "show_previews" not in d["props"]


def test_fileupload_rejects_unknown_variant():
    with pytest.raises(ValueError):
        ui.FileUpload(variant="hologram")


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
