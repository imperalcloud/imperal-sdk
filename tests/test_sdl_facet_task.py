# tests/test_sdl_facet_task.py
"""SDL Phase 2 — Tasks & Workflow family facets."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, Ref, roles_of
from imperal_sdk.sdl.facets.task import (
    Prioritized,
    Progress,
    Completable,
    Blockable,
    Dependencies,
    Boarded,
    Checklist,
    WorkflowState,
    Approvable,
    Estimable,
)


class Doc(Entity, Prioritized, Progress, Completable):
    pass


def test_task_facets_compose_and_are_optional():
    d = Doc(id=1, title="x")
    assert d.priority is None
    assert d.progress is None
    assert d.is_done is None


def test_task_facets_accept_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    ref = Ref(id="u1", kind="user", title="Alice")
    d = Doc(id=1, title="x", priority="high", progress=0.75, is_done=True, completed_at=now, completed_by=ref)
    assert d.priority == "high"
    assert d.progress == 0.75
    assert d.is_done is True
    assert d.completed_by == ref


def test_task_roles_present():
    roles = roles_of(Doc)
    assert roles["priority"] == "task.priority"
    assert roles["progress"] == "task.progress"
    assert roles["is_done"] == "task.is_done"


def test_blockable_and_dependencies_roles():
    class T(Entity, Blockable, Dependencies):
        pass

    roles = roles_of(T)
    assert roles["is_blocked"] == "task.is_blocked"
    assert roles["blocks"] == "task.blocks"
    assert roles["blocked_by"] == "task.blocked_by"


def test_boarded_and_checklist_roles():
    class T(Entity, Boarded, Checklist):
        pass

    roles = roles_of(T)
    assert roles["board"] == "task.board"
    assert roles["checklist_items"] == "task.checklist_items"
    assert roles["checklist_total"] == "task.checklist_total"


def test_workflow_approvable_estimable_roles():
    class T(Entity, WorkflowState, Approvable, Estimable):
        pass

    roles = roles_of(T)
    assert roles["state"] == "task.state"
    assert roles["approval_status"] == "task.approval_status"
    assert roles["estimate_s"] == "task.estimate_s"
