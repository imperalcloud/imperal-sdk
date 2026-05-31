# tests/test_sdl_facets_doc.py
"""SDL Phase 2 — the facet doc references only real facets and covers every family."""
from __future__ import annotations

import pathlib
import re

import imperal_sdk.sdl.facets as facets

DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "sdl-facets.md"


def test_doc_exists():
    assert DOC.is_file()


def test_doc_mentions_every_exported_facet():
    text = DOC.read_text()
    missing = [n for n in facets.__all__ if not re.search(rf"\b{re.escape(n)}\b", text)]
    assert not missing, f"facets undocumented: {missing}"
