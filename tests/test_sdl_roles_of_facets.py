# tests/test_sdl_roles_of_facets.py
"""SDL Phase 2 — roles_of surfaces facet roles alongside core roles."""
from __future__ import annotations

from pydantic import BaseModel

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.field import _facet_field


class _Timed(BaseModel):
    created_at: str | None = _facet_field(role="time.created_at")


class _Doc(Entity, _Timed):
    pass


def test_roles_of_includes_core_and_facet_roles():
    roles = roles_of(_Doc)
    assert roles["id"] == "core.id"
    assert roles["created_at"] == "time.created_at"
