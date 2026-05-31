# tests/test_sdl_exports.py
"""SDL Phase 1 — top-level import surface."""
from __future__ import annotations


def test_sdl_importable_from_top_level():
    from imperal_sdk import sdl
    assert hasattr(sdl, "Entity")
    assert hasattr(sdl, "Ref")
    assert hasattr(sdl, "EntityList")
    assert hasattr(sdl, "field")
    assert hasattr(sdl, "roles_of")


def test_sdl_in_dunder_all():
    import imperal_sdk
    assert "sdl" in imperal_sdk.__all__


def test_entity_usable_via_top_level():
    from imperal_sdk import sdl

    class Note(sdl.Entity):
        body: str | None = None

    n = Note(id="n1", title="Hello")
    assert n.kind == "note"
