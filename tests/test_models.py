"""Tests for SDK data types."""
import pytest
from imperal_sdk.types.models import (
    Document, CompletionResult, LimitsResult, SubscriptionInfo,
    BalanceInfo, FileInfo, HTTPResponse,
)


class TestDocument:
    def test_basic(self):
        doc = Document(id="d1", collection="deals", data={"name": "Big Deal"})
        assert doc.id == "d1"
        assert doc.collection == "deals"
        assert doc.data["name"] == "Big Deal"
        assert doc.tenant_id == "default"

    def test_full(self):
        doc = Document(
            id="d1", collection="deals", data={"x": 1},
            extension_id="crm", tenant_id="t1",
            created_at="2026-01-01", updated_at="2026-01-02",
        )
        assert doc.extension_id == "crm"
        assert doc.created_at == "2026-01-01"


class TestCompletionResult:
    def test_basic(self):
        r = CompletionResult(text="Hello!")
        assert r.text == "Hello!"
        assert r.model == ""
        assert r.usage == {}

    def test_full(self):
        r = CompletionResult(
            text="Answer", model="claude-sonnet",
            usage={"input_tokens": 100, "output_tokens": 50},
            stop_reason="end_turn",
        )
        assert r.model == "claude-sonnet"
        assert r.usage["input_tokens"] == 100


class TestLimitsResult:
    def test_defaults(self):
        r = LimitsResult()
        assert r.allowed is True
        assert r.balance == 0

    def test_blocked(self):
        r = LimitsResult(allowed=False, balance=0, message="Quota exceeded")
        assert r.allowed is False
        assert r.message == "Quota exceeded"


class TestSubscriptionInfo:
    def test_basic(self):
        s = SubscriptionInfo(plan_id="pro", plan_name="Pro", status="active")
        assert s.plan_id == "pro"
        assert s.status == "active"
        assert s.period == "monthly"


class TestBalanceInfo:
    def test_basic(self):
        b = BalanceInfo(balance=50000, plan="pro", cap=250000)
        assert b.balance == 50000
        assert b.cap == 250000


class TestFileInfo:
    def test_basic(self):
        f = FileInfo(path="/uploads/doc.pdf", size=1024, content_type="application/pdf")
        assert f.path == "/uploads/doc.pdf"
        assert f.size == 1024

    def test_with_url(self):
        f = FileInfo(path="/img.png", url="https://cdn.example.com/img.png")
        assert f.url.startswith("https://")


class TestHTTPResponse:
    def test_ok(self):
        r = HTTPResponse(status_code=200, body={"result": "ok"})
        assert r.ok is True
        assert r.json() == {"result": "ok"}

    def test_not_ok(self):
        r = HTTPResponse(status_code=404, body="Not Found")
        assert r.ok is False
        assert r.text() == "Not Found"

    def test_json_from_string(self):
        r = HTTPResponse(status_code=200, body='{"a": 1}')
        assert r.json() == {"a": 1}

    def test_text_from_bytes(self):
        r = HTTPResponse(status_code=200, body=b"hello")
        assert r.text() == "hello"

    def test_text_from_dict(self):
        r = HTTPResponse(status_code=200, body={"k": "v"})
        assert '"k"' in r.text()

    def test_json_from_bytes_raises(self):
        r = HTTPResponse(status_code=200, body=b"hello")
        with pytest.raises(ValueError):
            r.json()

    def test_headers(self):
        r = HTTPResponse(status_code=200, body="", headers={"Content-Type": "text/html"})
        assert r.headers["Content-Type"] == "text/html"
