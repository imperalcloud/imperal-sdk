# tests/test_sdl_facets_catalog.py
"""SDL Phase 2 — every facet role is reserved-namespace, valid, and in sdl_roles.json."""
from __future__ import annotations

import json
import pathlib

import imperal_sdk.sdl.facets as facets
from imperal_sdk.sdl.entity import roles_of
from imperal_sdk.sdl.roles import is_valid_role, namespace_of, RESERVED_NAMESPACES

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _all_facet_roles() -> set[str]:
    roles: set[str] = set()
    for name in facets.__all__:
        model = getattr(facets, name)
        roles.update(roles_of(model).values())
    return roles


def test_every_facet_role_valid_and_reserved():
    for role in _all_facet_roles():
        assert is_valid_role(role), role
        assert namespace_of(role) in RESERVED_NAMESPACES, role


def test_every_facet_role_in_catalog():
    catalog = json.loads((ROOT / "sdl_roles.json").read_text())
    cat_roles = {r["role"] for r in catalog["roles"]}
    missing = _all_facet_roles() - cat_roles
    assert not missing, f"facet roles missing from sdl_roles.json: {sorted(missing)}"


def test_catalog_in_sync_with_generator():
    from imperal_sdk.sdl._generate_roles_json import build_catalog
    actual = json.loads((ROOT / "sdl_roles.json").read_text())
    assert actual == build_catalog()
