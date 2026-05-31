# tests/test_sdl_field.py
"""SDL Phase 1 — sdl.field stamps a semantic role into JSON-schema metadata."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from imperal_sdk.sdl.field import field, ROLE_KEY
from imperal_sdk.sdl.roles import RoleError


class Track(BaseModel):
    bpm: int | None = field(role="audio.bpm", describe="beats per minute")
    name: str = "untitled"


def test_role_lands_in_field_schema_extra():
    extra = Track.model_fields["bpm"].json_schema_extra
    assert isinstance(extra, dict)
    assert extra[ROLE_KEY] == "audio.bpm"


def test_describe_becomes_description():
    extra = Track.model_fields["bpm"].json_schema_extra
    assert extra["description"] == "beats per minute"


def test_field_is_optional_by_default():
    # default=None unless overridden, so a model with only defaults validates
    t = Track()
    assert t.bpm is None


def test_field_default_override():
    class M(BaseModel):
        x: int = field(role="x.count", default=5)
    assert M().x == 5


def test_field_rejects_reserved_namespace_eagerly():
    with pytest.raises(RoleError):
        class Bad(BaseModel):
            y: str = field(role="core.title")  # reserved → raises at class definition
