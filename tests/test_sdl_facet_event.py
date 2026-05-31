# tests/test_sdl_facet_event.py
"""SDL Phase 2 — Events & Tickets family facets."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.event import (
    Eventful,
    Capacity,
    RSVP,
    Ticketed,
    AdmissionPolicy,
    AgendaSlot,
    Cancellation,
    CalendarFeed,
)


class EventDoc(Entity, Eventful, Capacity, RSVP):
    pass


class EventDoc2(Entity, Ticketed, AdmissionPolicy, AgendaSlot):
    pass


class EventDoc3(Entity, Cancellation, CalendarFeed):
    pass


def test_event_facets_compose_and_are_optional():
    d = EventDoc(id=1, title="x")
    assert d.venue is None
    assert d.event_organizer is None
    assert d.capacity_total is None
    assert d.rsvp_state is None


def test_event_facets_accept_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = EventDoc(
        id=1, title="x",
        venue="Main Hall",
        capacity_total=200,
        capacity_remaining=50,
        is_sold_out=False,
        rsvp_state="going",
        checked_in=True,
    )
    assert d.venue == "Main Hall"
    assert d.capacity_total == 200
    assert d.rsvp_state == "going"
    assert d.checked_in is True


def test_event_roles_present():
    roles = roles_of(EventDoc)
    assert roles["venue"] == "event.venue"
    assert roles["event_organizer"] == "event.event_organizer"
    assert roles["event_host"] == "event.event_host"
    assert roles["capacity_total"] == "event.capacity_total"
    assert roles["rsvp_state"] == "event.rsvp_state"


def test_ticketed_admission_agenda_roles():
    roles = roles_of(EventDoc2)
    assert roles["ticket_price"] == "event.ticket_price"
    assert roles["min_age"] == "event.min_age"
    assert roles["session_type"] == "event.session_type"
    assert roles["speakers"] == "event.speakers"


def test_cancellation_calendar_roles():
    d = EventDoc3(id=1, title="x", is_cancelled=True, ical_uid="abc-123")
    assert d.is_cancelled is True
    assert d.ical_uid == "abc-123"
    roles = roles_of(EventDoc3)
    assert roles["is_cancelled"] == "event.is_cancelled"
    assert roles["ical_uid"] == "event.ical_uid"
    assert roles["calendar_color"] == "event.calendar_color"
