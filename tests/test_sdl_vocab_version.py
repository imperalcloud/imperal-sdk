"""C3 — sdl_roles.json surfaces sdl_vocab_version (string, sourced from _SCHEMA_VERSION)."""
from __future__ import annotations

import json
import pathlib

ROLES = pathlib.Path(__file__).resolve().parents[1] / "sdl_roles.json"


def test_roles_json_has_vocab_version():
    data = json.loads(ROLES.read_text(encoding="utf-8"))
    assert "sdl_vocab_version" in data
    assert isinstance(data["sdl_vocab_version"], str)
