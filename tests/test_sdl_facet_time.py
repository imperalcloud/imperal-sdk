# tests/test_sdl_facet_time.py
"""SDL Phase 2 — Time family facets."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.time import Timestamped, Schedulable, Duration, Recurring, Booked


class Doc(Entity, Timestamped, Schedulable, Duration):
    pass


def test_time_facets_compose_and_are_optional():
    d = Doc(id=1, title="x")
    assert d.created_at is None and d.start_at is None and d.duration_s is None


def test_time_facets_accept_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = Doc(id=1, title="x", created_at=now, start_at=now, all_day=True, duration_s=3600)
    assert d.created_at == now and d.all_day is True and d.duration_s == 3600


def test_time_roles_present():
    roles = roles_of(Doc)
    assert roles["created_at"] == "time.created_at"
    assert roles["start_at"] == "time.start_at"
    assert roles["duration_s"] == "time.duration_s"


def test_recurring_and_booked_roles():
    class Ev(Entity, Recurring, Booked):
        pass
    roles = roles_of(Ev)
    assert roles["recurrence_rule"] == "time.recurrence_rule"
    assert roles["check_in_at"] == "time.check_in_at"
