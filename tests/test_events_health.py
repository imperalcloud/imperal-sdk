"""Tests for Event, Webhook, and HealthStatus types."""
import json
import pytest
from imperal_sdk.types.events import Event, WebhookRequest, WebhookResponse
from imperal_sdk.types.health import HealthStatus


class TestEvent:
    def test_basic(self):
        e = Event(event_type="deal.created", user_id="u1", data={"deal_id": "d1"})
        assert e.event_type == "deal.created"
        assert e.user_id == "u1"
        assert e.data["deal_id"] == "d1"

    def test_defaults(self):
        e = Event(event_type="test")
        assert e.timestamp == ""
        assert e.tenant_id == ""
        assert e.data == {}


class TestWebhookRequest:
    def test_json(self):
        req = WebhookRequest(method="POST", body=b'{"key": "value"}')
        assert req.json() == {"key": "value"}

    def test_text(self):
        req = WebhookRequest(method="POST", body=b"hello world")
        assert req.text() == "hello world"

    def test_headers_and_query(self):
        req = WebhookRequest(
            method="POST",
            headers={"Content-Type": "application/json"},
            query_params={"token": "abc"},
        )
        assert req.headers["Content-Type"] == "application/json"
        assert req.query_params["token"] == "abc"

    def test_invalid_json_raises(self):
        req = WebhookRequest(method="POST", body=b"not json")
        with pytest.raises(json.JSONDecodeError):
            req.json()


class TestWebhookResponse:
    def test_ok_default(self):
        r = WebhookResponse.ok()
        assert r.status_code == 200
        assert r.body == "OK"

    def test_ok_custom(self):
        r = WebhookResponse.ok({"result": "done"})
        assert r.body == {"result": "done"}

    def test_error(self):
        r = WebhookResponse.error("Bad request", 400)
        assert r.status_code == 400
        assert r.body == {"error": "Bad request"}

    def test_error_default_status(self):
        r = WebhookResponse.error("fail")
        assert r.status_code == 400

    def test_custom_headers(self):
        r = WebhookResponse(status_code=200, body="ok", headers={"X-Custom": "val"})
        assert r.headers["X-Custom"] == "val"


class TestHealthStatus:
    def test_ok(self):
        h = HealthStatus.ok()
        assert h.status == "ok"
        assert h.message == ""
        assert h.details == {}

    def test_ok_with_details(self):
        h = HealthStatus.ok({"connections": 5})
        assert h.details == {"connections": 5}

    def test_degraded(self):
        h = HealthStatus.degraded("High latency")
        assert h.status == "degraded"
        assert h.message == "High latency"

    def test_unhealthy(self):
        h = HealthStatus.unhealthy("Database down")
        assert h.status == "unhealthy"
        assert h.message == "Database down"
