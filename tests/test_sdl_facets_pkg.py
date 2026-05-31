# tests/test_sdl_facets_pkg.py
"""SDL Phase 2 — facets subpackage import surface (grows as families land)."""
from __future__ import annotations


def test_facets_package_importable():
    import imperal_sdk.sdl.facets as facets
    assert facets is not None
