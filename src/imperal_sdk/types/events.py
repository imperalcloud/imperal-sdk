"""Event types for the Imperal SDK event system and webhook ingestion."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    """Base event type. All platform events carry this structure."""
    event_type: str
    timestamp: str = ""
    user_id: str = ""
    tenant_id: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class WebhookRequest:
    """Incoming webhook request from external service."""
    method: str
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    query_params: dict = field(default_factory=dict)

    def json(self) -> dict:
        import json
        return json.loads(self.body)

    def text(self) -> str:
        return self.body.decode("utf-8")


@dataclass
class WebhookResponse:
    """Response to return from a webhook handler.

    Returning one of these is equivalent to returning the documented control
    dict — ``{"status_code": ..., "headers": ..., "body": ...}`` — and shapes
    the REAL HTTP reply: the status line and the response headers, not just a
    JSON body. That matters for providers whose handshake lives outside the
    body, such as Asana echoing ``X-Hook-Secret`` in a header.

        return WebhookResponse(status_code=200, body="",
                               headers={"X-Hook-Secret": offered})

    Until 2026-08-15 this class was a trap: it had no ``to_dict``, so the
    runtime's result serializer fell through to its catch-all branch and
    wrapped the whole object as ``{"status": "success", "data": {...}}``. The
    gateway looks for the control keys at the TOP level, found none, and
    answered a plain 200 with the control keys buried in the body — so the
    echo header never reached the wire and the webhook could not be
    established. asana-connector hit exactly this and worked around it by
    returning a bare dict instead.
    """
    status_code: int = 200
    body: dict | str = ""
    headers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Flatten to the control-key dict the webhook route understands.

        Deliberately FLAT — the control keys must stay at the top level. Nest
        them under a "data" key and the gateway silently ignores all three.
        """
        return {
            "status_code": self.status_code,
            "headers": dict(self.headers),
            "body": self.body,
        }

    @staticmethod
    def ok(body: dict | str = "OK") -> WebhookResponse:
        return WebhookResponse(status_code=200, body=body)

    @staticmethod
    def error(message: str, status: int = 400) -> WebhookResponse:
        return WebhookResponse(status_code=status, body={"error": message})
