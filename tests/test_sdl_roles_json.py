"""SDL Phase 1 — sdl_roles.json is the machine-readable core role catalog."""
from __future__ import annotations

import json
import pathlib

from imperal_sdk.sdl.roles import CORE_ROLES, is_valid_role

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROLES_JSON = ROOT / "sdl_roles.json"


def test_roles_json_exists():
    assert ROLES_JSON.is_file(), "sdl_roles.json must be generated at repo root"


def test_roles_json_contains_all_core_roles():
    data = json.loads(ROLES_JSON.read_text())
    roles = {r["role"] for r in data["roles"]}
    for core_role in CORE_ROLES.values():
        assert core_role in roles


def test_all_roles_valid_grammar():
    data = json.loads(ROLES_JSON.read_text())
    for r in data["roles"]:
        assert is_valid_role(r["role"]), r["role"]


def test_roles_json_in_sync_with_generator():
    # Regenerating must produce identical content (no drift).
    from imperal_sdk.sdl._generate_roles_json import build_catalog
    expected = build_catalog()
    actual = json.loads(ROLES_JSON.read_text())
    assert actual == expected
