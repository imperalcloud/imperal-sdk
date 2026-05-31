"""SDL — Entity/EntityList carry an x-sdl schema marker so the platform can
detect an SDL-typed result from its JSON schema alone."""
from __future__ import annotations

from imperal_sdk.sdl.entity import Entity, EntityList


class Project(Entity):
    bucket_count: int = 0


def test_entity_schema_has_marker():
    assert Project.model_json_schema().get("x-sdl") == "entity"
    assert Entity.model_json_schema().get("x-sdl") == "entity"


def test_entity_list_schema_has_marker():
    class PList(EntityList[Project]):
        pass
    assert PList.model_json_schema().get("x-sdl") == "entity-list"
