"""SDL Phase 2 — _facet_field allows reserved namespaces; rejects non-reserved + malformed."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from imperal_sdk.sdl.field import _facet_field, ROLE_KEY
from imperal_sdk.sdl.roles import RoleError


class _Sample(BaseModel):
    created_at: str | None = _facet_field(role="time.created_at")


def test_facet_field_allows_reserved_namespace():
    assert _Sample.model_fields["created_at"].json_schema_extra[ROLE_KEY] == "time.created_at"


def test_facet_field_optional_by_default():
    assert _Sample().created_at is None


def test_facet_field_rejects_non_reserved_namespace():
    with pytest.raises(RoleError):
        class Bad(BaseModel):
            x: str | None = _facet_field(role="app.x")  # not reserved → facets must own a reserved ns


def test_facet_field_rejects_malformed():
    with pytest.raises(RoleError):
        class Bad2(BaseModel):
            y: str | None = _facet_field(role="NotARole")
