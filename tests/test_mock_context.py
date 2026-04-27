# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for MockContext and all mock clients."""
import pytest
from imperal_sdk.testing import (
    MockAI,
    MockBilling,
    MockConfig,
    MockContext,
    MockExtensions,
    MockHTTP,
    MockNotify,
    MockSkeleton,
    MockStorage,
    MockStore,
)


class TestMockContext:
    def test_creates_context(self):
        ctx = MockContext()
        assert ctx.user.imperal_id == "test_user"
        assert ctx.user.email == "test@test.com"
        assert ctx.user.role == "user"
        assert ctx.store is not None
        assert ctx.ai is not None
        assert ctx._extension_id == "test-ext"

    def test_custom_params(self):
        ctx = MockContext(user_id="u1", role="admin", extension_id="crm")
        assert ctx.user.imperal_id == "u1"
        assert ctx.user.role == "admin"
        assert ctx._extension_id == "crm"

    def test_has_time(self):
        ctx = MockContext()
        assert ctx.time.timezone == "UTC"
        assert ctx.time.now_utc == "2026-01-01T00:00:00Z"

    def test_all_clients_present(self):
        ctx = MockContext()
        assert ctx.store is not None
        assert ctx.ai is not None
        assert ctx.billing is not None
        assert ctx.skeleton is not None
        assert ctx.notify is not None
        assert ctx.storage is not None
        assert ctx.http is not None
        assert ctx.config is not None
        assert ctx.extensions is not None

    def test_default_scopes_allow_all(self):
        ctx = MockContext()
        assert ctx.user.has_scope("any:scope")

    def test_custom_scopes(self):
        ctx = MockContext(scopes=["deals:read"])
        assert ctx.user.has_scope("deals:read")
        assert not ctx.user.has_scope("deals:write")

    def test_tenant_id(self):
        ctx = MockContext(tenant_id="t99")
        assert ctx.user.tenant_id == "t99"


class TestMockStore:
    @pytest.mark.asyncio
    async def test_create_and_get(self):
        ctx = MockContext()
        doc = await ctx.store.create("deals", {"name": "Big Deal", "value": 50000})
        assert doc.id is not None
        assert doc.collection == "deals"
        fetched = await ctx.store.get("deals", doc.id)
        assert fetched is not None
        assert fetched.data["name"] == "Big Deal"

    @pytest.mark.asyncio
    async def test_query_all(self):
        ctx = MockContext()
        await ctx.store.create("deals", {"name": "A", "status": "open"})
        await ctx.store.create("deals", {"name": "B", "status": "closed"})
        page = await ctx.store.query("deals")
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_query_with_where(self):
        ctx = MockContext()
        await ctx.store.create("deals", {"name": "A", "status": "open"})
        await ctx.store.create("deals", {"name": "B", "status": "closed"})
        page = await ctx.store.query("deals", where={"status": "open"})
        assert len(page) == 1
        assert page.data[0].data["name"] == "A"

    @pytest.mark.asyncio
    async def test_update_existing(self):
        ctx = MockContext()
        doc = await ctx.store.create("deals", {"name": "Old"})
        updated = await ctx.store.update("deals", doc.id, {"name": "New"})
        assert updated.data["name"] == "New"

    @pytest.mark.asyncio
    async def test_update_upsert(self):
        ctx = MockContext()
        updated = await ctx.store.update("items", "new_id", {"name": "Fresh"})
        assert updated.id == "new_id"
        assert updated.data["name"] == "Fresh"

    @pytest.mark.asyncio
    async def test_delete_existing(self):
        ctx = MockContext()
        doc = await ctx.store.create("deals", {"name": "X"})
        assert await ctx.store.delete("deals", doc.id) is True
        assert await ctx.store.get("deals", doc.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        ctx = MockContext()
        assert await ctx.store.delete("deals", "ghost") is False

    @pytest.mark.asyncio
    async def test_count_all(self):
        ctx = MockContext()
        await ctx.store.create("deals", {"x": 1})
        await ctx.store.create("deals", {"x": 2})
        assert await ctx.store.count("deals") == 2

    @pytest.mark.asyncio
    async def test_count_with_where(self):
        ctx = MockContext()
        await ctx.store.create("deals", {"status": "open"})
        await ctx.store.create("deals", {"status": "open"})
        await ctx.store.create("deals", {"status": "closed"})
        assert await ctx.store.count("deals", where={"status": "open"}) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        ctx = MockContext()
        assert await ctx.store.get("deals", "nope") is None

    @pytest.mark.asyncio
    async def test_query_empty_collection(self):
        ctx = MockContext()
        page = await ctx.store.query("empty")
        assert len(page) == 0
        assert page.has_more is False

    @pytest.mark.asyncio
    async def test_data_is_tracked_in_store(self):
        ctx = MockContext()
        await ctx.store.create("deals", {"name": "Test"})
        assert "deals" in ctx.store._data
        assert len(ctx.store._data["deals"]) == 1


class TestMockAI:
    @pytest.mark.asyncio
    async def test_default_response(self):
        ctx = MockContext()
        result = await ctx.ai.complete("hello")
        assert result.text == "Mock AI response"
        assert result.model == "mock"

    @pytest.mark.asyncio
    async def test_set_response_pattern_match(self):
        ctx = MockContext()
        ctx.ai.set_response("weather", "It's sunny!")
        result = await ctx.ai.complete("What's the weather?")
        assert result.text == "It's sunny!"

    @pytest.mark.asyncio
    async def test_set_response_no_match_falls_back(self):
        ctx = MockContext()
        ctx.ai.set_response("weather", "It's sunny!")
        result = await ctx.ai.complete("Tell me a joke")
        assert result.text == "Mock AI response"

    @pytest.mark.asyncio
    async def test_custom_model(self):
        ctx = MockContext()
        result = await ctx.ai.complete("hi", model="claude-sonnet")
        assert result.model == "claude-sonnet"


class TestMockBilling:
    @pytest.mark.asyncio
    async def test_check_limits_allowed(self):
        ctx = MockContext()
        result = await ctx.billing.check_limits()
        assert result.allowed is True
        assert result.balance == 50000
        assert result.plan == "pro"

    @pytest.mark.asyncio
    async def test_track_usage_reduces_balance(self):
        ctx = MockContext()
        await ctx.billing.track_usage(100)
        balance = await ctx.billing.get_balance()
        assert balance.balance == 49900

    @pytest.mark.asyncio
    async def test_balance_floor_at_zero(self):
        ctx = MockContext()
        await ctx.billing.track_usage(999999)
        balance = await ctx.billing.get_balance()
        assert balance.balance == 0

    @pytest.mark.asyncio
    async def test_get_subscription(self):
        ctx = MockContext()
        sub = await ctx.billing.get_subscription()
        assert sub.status == "active"
        assert sub.plan_id == "pro"

    @pytest.mark.asyncio
    async def test_custom_billing_params(self):
        ctx = MockContext()
        ctx.billing.balance = 100
        ctx.billing.plan = "starter"
        limits = await ctx.billing.check_limits()
        assert limits.balance == 100
        assert limits.plan == "starter"


class TestMockSkeleton:
    """v1.6.0 contract: ctx.skeleton is read-only; only ``@ext.skeleton`` tools
    (``tool_type="skeleton"``) may read sections. Writes happen kernel-side
    via ``skeleton_save_section`` activity, never through SDK. Tests that need
    to prime sections do so via ``ctx._raw_skeleton`` directly (test-only
    backdoor; not a public API). Invariant: I-SKELETON-LLM-ONLY.
    """

    @pytest.mark.asyncio
    async def test_get_nonexistent_in_skeleton_scope(self):
        ctx = MockContext(tool_type="skeleton")
        assert await ctx.skeleton.get("inbox") is None

    @pytest.mark.asyncio
    async def test_prime_and_get(self):
        """Prime MockSkeleton directly via _raw_skeleton (bypasses guard);
        read via ctx.skeleton.get() under skeleton scope. Tests that the
        mock serves reads correctly, not the removed write contract."""
        ctx = MockContext(tool_type="skeleton")
        ctx._raw_skeleton._sections["inbox"] = {"unread": 5}
        data = await ctx.skeleton.get("inbox")
        assert data is not None
        assert data["unread"] == 5

    @pytest.mark.asyncio
    async def test_prime_overwrites(self):
        ctx = MockContext(tool_type="skeleton")
        ctx._raw_skeleton._sections["stats"] = {"count": 1}
        ctx._raw_skeleton._sections["stats"] = {"count": 2}
        data = await ctx.skeleton.get("stats")
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_get_blocked_outside_skeleton_scope(self):
        """Regression: non-@ext.skeleton contexts raise SkeletonAccessForbidden
        even in tests. Confirms the guard survives the mock plumbing."""
        from imperal_sdk.errors import SkeletonAccessForbidden
        ctx = MockContext(tool_type="tool")  # default, explicit for clarity
        with pytest.raises(SkeletonAccessForbidden):
            await ctx.skeleton.get("inbox")


class TestMockNotify:
    @pytest.mark.asyncio
    async def test_send_records(self):
        ctx = MockContext()
        await ctx.notify.send("Hello!", channel="email")
        assert len(ctx.notify.sent) == 1
        assert ctx.notify.sent[0]["message"] == "Hello!"
        assert ctx.notify.sent[0]["channel"] == "email"

    @pytest.mark.asyncio
    async def test_send_default_channel(self):
        ctx = MockContext()
        await ctx.notify.send("Test")
        assert ctx.notify.sent[0]["channel"] == "in_app"

    @pytest.mark.asyncio
    async def test_send_multiple(self):
        ctx = MockContext()
        await ctx.notify.send("First")
        await ctx.notify.send("Second")
        assert len(ctx.notify.sent) == 2

    @pytest.mark.asyncio
    async def test_send_extra_kwargs(self):
        ctx = MockContext()
        await ctx.notify.send("Alert!", priority="high")
        assert ctx.notify.sent[0]["priority"] == "high"


class TestMockStorage:
    @pytest.mark.asyncio
    async def test_upload_download(self):
        ctx = MockContext()
        info = await ctx.storage.upload("/test.txt", b"hello", "text/plain")
        assert info.path == "/test.txt"
        assert info.size == 5
        assert info.content_type == "text/plain"
        data = await ctx.storage.download("/test.txt")
        assert data == b"hello"

    @pytest.mark.asyncio
    async def test_download_missing_raises(self):
        ctx = MockContext()
        with pytest.raises(FileNotFoundError):
            await ctx.storage.download("/ghost.txt")

    @pytest.mark.asyncio
    async def test_delete_existing(self):
        ctx = MockContext()
        await ctx.storage.upload("/test.txt", b"hello")
        assert await ctx.storage.delete("/test.txt") is True
        assert await ctx.storage.delete("/test.txt") is False

    @pytest.mark.asyncio
    async def test_list_by_prefix(self):
        ctx = MockContext()
        await ctx.storage.upload("/docs/a.txt", b"a")
        await ctx.storage.upload("/docs/b.txt", b"b")
        await ctx.storage.upload("/img/c.png", b"c")
        page = await ctx.storage.list("/docs/")
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_list_all(self):
        ctx = MockContext()
        await ctx.storage.upload("/a.txt", b"a")
        await ctx.storage.upload("/b.txt", b"b")
        page = await ctx.storage.list()
        assert len(page) == 2


class TestMockHTTP:
    @pytest.mark.asyncio
    async def test_mock_get(self):
        ctx = MockContext()
        ctx.http.mock_get("api.example.com", {"status": "ok"})
        resp = await ctx.http.get("https://api.example.com/data")
        assert resp.ok is True
        assert resp.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_mock_post(self):
        ctx = MockContext()
        ctx.http.mock_post("api.example.com/create", {"id": "new1"})
        resp = await ctx.http.post("https://api.example.com/create")
        assert resp.ok is True
        assert resp.json()["id"] == "new1"

    @pytest.mark.asyncio
    async def test_no_mock_returns_404(self):
        ctx = MockContext()
        resp = await ctx.http.get("https://unknown.com")
        assert resp.status_code == 404
        assert resp.ok is False

    @pytest.mark.asyncio
    async def test_mock_custom_status(self):
        ctx = MockContext()
        ctx.http.mock_get("broken.com", {"error": "oops"}, status=500)
        resp = await ctx.http.get("https://broken.com/endpoint")
        assert resp.status_code == 500
        assert resp.ok is False

    @pytest.mark.asyncio
    async def test_put_patch_delete(self):
        ctx = MockContext()
        ctx.http._mocks.append(("PUT", "example.com", {"updated": True}, 200))
        ctx.http._mocks.append(("PATCH", "example.com", {"patched": True}, 200))
        ctx.http._mocks.append(("DELETE", "example.com", {"deleted": True}, 200))
        assert (await ctx.http.put("https://example.com")).ok is True
        assert (await ctx.http.patch("https://example.com")).ok is True
        assert (await ctx.http.delete("https://example.com")).ok is True


class TestMockConfig:
    def test_get_top_level(self):
        ctx = MockContext(config={"api_url": "https://example.com"})
        assert ctx.config.get("api_url") == "https://example.com"

    def test_get_nested_dot_path(self):
        ctx = MockContext(config={"nested": {"key": "val"}})
        assert ctx.config.get("nested.key") == "val"

    def test_get_missing_returns_default(self):
        ctx = MockContext()
        assert ctx.config.get("missing", "default") == "default"

    def test_get_missing_returns_none(self):
        ctx = MockContext()
        assert ctx.config.get("missing") is None

    def test_require_raises_on_missing(self):
        ctx = MockContext()
        from imperal_sdk.errors import ValidationError
        with pytest.raises(ValidationError):
            ctx.config.require("missing_key")

    def test_require_returns_value(self):
        ctx = MockContext(config={"key": "value"})
        assert ctx.config.require("key") == "value"

    def test_get_section(self):
        ctx = MockContext(config={"db": {"host": "localhost", "port": 5432}})
        section = ctx.config.get_section("db")
        assert section["host"] == "localhost"

    def test_get_section_missing(self):
        ctx = MockContext()
        assert ctx.config.get_section("missing") == {}

    def test_all(self):
        ctx = MockContext(config={"a": 1, "b": 2})
        assert ctx.config.all() == {"a": 1, "b": 2}


class TestMockExtensions:
    @pytest.mark.asyncio
    async def test_call_sync_handler(self):
        ctx = MockContext()
        ctx.extensions.register("crm", "get_deal", lambda deal_id: {"id": deal_id, "name": "Test"})
        result = await ctx.extensions.call("crm", "get_deal", deal_id="d1")
        assert result["id"] == "d1"

    @pytest.mark.asyncio
    async def test_call_async_handler(self):
        ctx = MockContext()

        async def async_handler(deal_id):
            return {"id": deal_id, "async": True}

        ctx.extensions.register("crm", "get_deal_async", async_handler)
        result = await ctx.extensions.call("crm", "get_deal_async", deal_id="d2")
        assert result["async"] is True

    @pytest.mark.asyncio
    async def test_call_unknown_raises(self):
        ctx = MockContext()
        from imperal_sdk.errors import ExtensionError
        with pytest.raises(ExtensionError):
            await ctx.extensions.call("unknown", "method")

    @pytest.mark.asyncio
    async def test_call_unknown_method_raises(self):
        ctx = MockContext()
        ctx.extensions.register("crm", "get_deal", lambda: {})
        from imperal_sdk.errors import ExtensionError
        with pytest.raises(ExtensionError):
            await ctx.extensions.call("crm", "unknown_method")

    @pytest.mark.asyncio
    async def test_emit_records(self):
        ctx = MockContext()
        await ctx.extensions.emit("deal.created", {"deal_id": "d1"})
        assert len(ctx.extensions._emitted) == 1
        assert ctx.extensions._emitted[0]["event_type"] == "deal.created"
        assert ctx.extensions._emitted[0]["data"] == {"deal_id": "d1"}

    @pytest.mark.asyncio
    async def test_emit_multiple(self):
        ctx = MockContext()
        await ctx.extensions.emit("a.created", {"id": "1"})
        await ctx.extensions.emit("b.updated", {"id": "2"})
        assert len(ctx.extensions._emitted) == 2
