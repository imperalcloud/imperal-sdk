# tests/test_sdl_entity.py
"""SDL Phase 1 — canonical Entity/Ref/EntityList + role introspection."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from imperal_sdk.sdl.entity import Entity, Ref, EntityList, roles_of
from imperal_sdk.sdl.field import field


class Project(Entity):
    bucket_count: int = 0
    velocity: float | None = field(role="app.velocity")


def test_entity_requires_id_and_title():
    with pytest.raises(ValidationError):
        Entity()  # id + title required


def test_entity_minimal():
    e = Entity(id=32, title="WebHostMost Tasks")
    assert e.id == 32
    assert e.title == "WebHostMost Tasks"
    assert e.subtitle is None and e.status is None and e.url is None


def test_kind_defaults_to_subclass_name():
    assert Project(id=1, title="P").kind == "project"


def test_kind_default_for_base_entity():
    assert Entity(id=1, title="X").kind == "entity"


def test_kind_explicit_override():
    assert Project(id=1, title="P", kind="board").kind == "board"


def test_ref_shape():
    r = Ref(id=7, kind="bucket", title="To Do")
    assert r.app_id is None
    assert (r.id, r.kind, r.title) == (7, "bucket", "To Do")


def test_entity_list_generic_iter_len():
    el = EntityList[Project](items=[Project(id=1, title="A"), Project(id=2, title="B")], total=340, has_more=True)
    assert len(el) == 2
    assert [p.title for p in el] == ["A", "B"]
    assert el.total == 340 and el.has_more is True


def test_roles_of_core_and_custom():
    roles = roles_of(Project)
    assert roles["id"] == "core.id"
    assert roles["title"] == "core.title"
    assert roles["kind"] == "core.kind"
    assert roles["velocity"] == "app.velocity"    # custom role read from schema
    assert "bucket_count" not in roles            # plain field → no role
