# tests/test_sdl_facet_comm.py
"""SDL Phase 2 — Communication family facets (comm.*)."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, Ref, roles_of
from imperal_sdk.sdl.facets.comm import (
    Conversational, Threaded, MessageState, Reactable, Callable, Draftable,
)


class ChatMsg(Entity, Conversational, Threaded, MessageState, Reactable):
    pass


class CallRecord(Entity, Callable, Draftable):
    pass


def test_comm_facets_compose_and_are_optional():
    m = ChatMsg(id=1, title="x")
    assert m.conversation_ref is None
    assert m.thread_ref is None
    assert m.is_read is None
    assert m.reactions is None


def test_conversational_accepts_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    conv = Ref(id=10, kind="conversation", title="General")
    m = ChatMsg(id=1, title="x", conversation_ref=conv,
                conversation_type="group", channel_name="general",
                is_group=True, conversation_participant_count=5,
                last_message_at=now, last_preview="Hi there")
    assert m.conversation_ref == conv
    assert m.conversation_type == "group"
    assert m.conversation_participant_count == 5
    assert m.last_message_at == now


def test_threaded_accepts_values():
    root = Ref(id=1, kind="message", title="Root")
    m = ChatMsg(id=5, title="x", thread_ref=root, root=root, depth=2)
    assert m.thread_ref == root
    assert m.depth == 2


def test_message_state_accepts_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    m = ChatMsg(id=1, title="x", direction="incoming", is_read=True,
                delivery_state="delivered", sent_at=now, is_from_me=False)
    assert m.direction == "incoming"
    assert m.is_read is True
    assert m.delivery_state == "delivered"


def test_reactable_accepts_values():
    m = ChatMsg(id=1, title="x", reactions={"👍": 3, "❤️": 1},
                reaction_count=4, my_reactions=["👍"])
    assert m.reactions == {"👍": 3, "❤️": 1}
    assert m.reaction_count == 4


def test_callable_accepts_values():
    c = CallRecord(id=1, title="x", call_direction="outgoing",
                   call_type="voice", call_state="ended",
                   answered=True, end_reason="hangup", ring_duration_s=5)
    assert c.call_direction == "outgoing"
    assert c.call_type == "voice"
    assert c.answered is True
    assert c.end_reason == "hangup"


def test_draftable_accepts_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    c = CallRecord(id=1, title="x", is_draft=True, scheduled_send_at=now,
                   last_saved_at=now, is_auto_generated=False)
    assert c.is_draft is True
    assert c.scheduled_send_at == now


def test_comm_roles_present():
    roles = roles_of(ChatMsg)
    # Conversational — note special role for participant count
    assert roles["conversation_ref"] == "comm.conversation_ref"
    assert roles["conversation_type"] == "comm.conversation_type"
    assert roles["conversation_participant_count"] == "comm.participant_count"
    assert roles["last_message_at"] == "comm.last_message_at"
    # Threaded
    assert roles["thread_ref"] == "comm.thread_ref"
    assert roles["depth"] == "comm.depth"
    # MessageState
    assert roles["direction"] == "comm.direction"
    assert roles["is_read"] == "comm.is_read"
    assert roles["delivery_state"] == "comm.delivery_state"
    # Reactable
    assert roles["reactions"] == "comm.reactions"
    assert roles["reaction_count"] == "comm.reaction_count"


def test_callable_draftable_roles():
    roles = roles_of(CallRecord)
    assert roles["call_direction"] == "comm.call_direction"
    assert roles["call_type"] == "comm.call_type"
    assert roles["call_state"] == "comm.call_state"
    assert roles["is_draft"] == "comm.is_draft"
    assert roles["scheduled_send_at"] == "comm.scheduled_send_at"
