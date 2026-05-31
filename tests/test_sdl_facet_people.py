# tests/test_sdl_facet_people.py
"""SDL Phase 2 — People & Identity family facets (people.*)."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, Ref, roles_of
from imperal_sdk.sdl.facets.people import (
    Authorship, Assignable, Participants, Correspondents, ContactPoints, Presence,
)


class Doc(Entity, Authorship, Assignable):
    pass


class Msg(Entity, Participants, Correspondents, ContactPoints, Presence):
    pass


def test_people_facets_compose_and_are_optional():
    d = Doc(id=1, title="x")
    assert d.creator is None
    assert d.assignee is None
    assert d.team is None


def test_authorship_accepts_values():
    ref = Ref(id=42, kind="user", title="Alice")
    d = Doc(id=1, title="x", creator=ref, author=ref, owner=ref)
    assert d.creator == ref
    assert d.author == ref


def test_assignable_accepts_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    ref = Ref(id=7, kind="user", title="Bob")
    d = Doc(id=1, title="x", assignee=ref, assigned_at=now)
    assert d.assignee == ref
    assert d.assigned_at == now


def test_participants_accepts_values():
    ref = Ref(id=1, kind="user", title="User")
    m = Msg(id=1, title="x", host=ref, participant_count=5,
            join_state="member")
    assert m.host == ref
    assert m.participant_count == 5
    assert m.join_state == "member"


def test_correspondents_accepts_values():
    ref = Ref(id=1, kind="user", title="User")
    m = Msg(id=1, title="x", sender=ref, recipient_count=3)
    assert m.sender == ref
    assert m.recipient_count == 3


def test_contact_points_accepts_values():
    m = Msg(id=1, title="x", emails=["a@b.com"], phones=["+1234"],
            website_url="https://example.com", preferred_channel="email")
    assert m.emails == ["a@b.com"]
    assert m.preferred_channel == "email"


def test_presence_accepts_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    m = Msg(id=1, title="x", online_status="online", status_message="Hello",
            last_seen_at=now)
    assert m.online_status == "online"
    assert m.last_seen_at == now


def test_people_roles_present():
    roles = roles_of(Doc)
    assert roles["creator"] == "people.creator"
    assert roles["author"] == "people.author"
    assert roles["owner"] == "people.owner"
    assert roles["assignee"] == "people.assignee"
    assert roles["reviewer"] == "people.reviewer"
    assert roles["assigned_at"] == "people.assigned_at"


def test_msg_roles_present():
    roles = roles_of(Msg)
    assert roles["participant_count"] == "people.participant_count"
    assert roles["sender"] == "people.sender"
    assert roles["emails"] == "people.emails"
    assert roles["online_status"] == "people.online_status"
    assert roles["last_seen_at"] == "people.last_seen_at"
