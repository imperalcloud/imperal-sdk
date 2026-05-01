"""I-AH-1 L3: SDK rejects empirically observed fabricated message_id shapes.

Empirical evidence: prod 2026-05-01 02:25 UTC chat sent
  GET https://graph.microsoft.com/v1.0/me/messages/webhostmost-outlook-1
  GET https://gmail.googleapis.com/v1/users/me/messages/ivalik-gmail-4
Both IDs were pure LLM hallucination matching pattern
  ^[a-z][a-z0-9]*-[a-z][a-z0-9]*-\\d+$
This test asserts the SDK guard catches that pattern before the tool runs.
"""
import pytest
from imperal_sdk.chat.guards import check_id_shape_fabrication


# --- Rejected (fabricated) ---

def test_rejects_outlook_slug_fabrication():
    rejected = check_id_shape_fabrication({"message_id": "webhostmost-outlook-1"})
    assert rejected is not None
    assert rejected["error_code"] == "FABRICATED_ID_SHAPE"
    assert rejected["field"] == "message_id"


def test_rejects_gmail_slug_fabrication():
    rejected = check_id_shape_fabrication({"message_id": "ivalik-gmail-4"})
    assert rejected is not None
    assert rejected["error_code"] == "FABRICATED_ID_SHAPE"


def test_rejects_arbitrary_slug_fabrication():
    rejected = check_id_shape_fabrication({"message_id": "user-account-99"})
    assert rejected is not None


# --- Accepted (real shapes) ---

def test_accepts_real_outlook_base64_id():
    """Outlook IDs are ~150-char URL-safe base64 with mixed case + dots."""
    real = "AAMkADExMzNkOWZmLTAyMDUtNDY3OS04ZDViLTYwYjY3NjEzNTM4MABGAAAAAACg" * 2
    rejected = check_id_shape_fabrication({"message_id": real})
    assert rejected is None


def test_accepts_real_gmail_hex_id():
    """Gmail message IDs are 16-char hex."""
    rejected = check_id_shape_fabrication({"message_id": "1973fe6c1234abcd"})
    assert rejected is None


def test_accepts_uuid_shape():
    rejected = check_id_shape_fabrication({"message_id": "550e8400-e29b-41d4-a716-446655440000"})
    assert rejected is None


def test_no_message_id_field_passthrough():
    """Tool with no message_id arg is not affected."""
    rejected = check_id_shape_fabrication({"query": "unread", "limit": 10})
    assert rejected is None


def test_rejects_thread_id_slug_fabrication():
    rejected = check_id_shape_fabrication({"thread_id": "fake-gmail-3"})
    assert rejected is not None
    assert rejected["error_code"] == "FABRICATED_ID_SHAPE"
    assert rejected["field"] == "thread_id"


def test_rejects_email_id_slug_fabrication():
    rejected = check_id_shape_fabrication({"email_id": "fake-outlook-2"})
    assert rejected is not None
    assert rejected["field"] == "email_id"


def test_rejects_msg_id_slug_fabrication():
    rejected = check_id_shape_fabrication({"msg_id": "fake-imap-7"})
    assert rejected is not None
    assert rejected["field"] == "msg_id"
