# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import pytest
from imperal_sdk.context import Context
from imperal_sdk.auth.user import User


def test_context_creation():
    user = User(id="imp_u_123", email="test@test.com", tenant_id="default")
    ctx = Context(user=user)
    assert ctx.user.id == "imp_u_123"
    assert ctx.store is None
    assert ctx.db is None
    assert ctx.ai is None
    assert ctx.billing is None


def test_context_with_mock_store():
    user = User(id="imp_u_123")

    class MockStore:
        async def create(self, collection, data): return {"id": "1", **data}
        async def get(self, collection, doc_id): return {}
        async def query(self, collection, where=None, order_by=None, limit=100): return []
        async def update(self, collection, doc_id, data): return {}
        async def delete(self, collection, doc_id): return True
        async def count(self, collection, where=None): return 0

    ctx = Context(user=user, store=MockStore())
    assert ctx.store is not None


def test_context_extension_id():
    ctx = Context(user=User(id="imp_u_123"), _extension_id="sharelock-v2")
    assert ctx._extension_id == "sharelock-v2"


def test_context_metadata():
    ctx = Context(user=User(id="imp_u_123"), _metadata={"trace_id": "abc"})
    assert ctx._metadata["trace_id"] == "abc"


class TestContextExtensions:
    def test_extensions_field_exists(self):
        ctx = Context(user=User(id="u1"))
        assert ctx.extensions is None


class TestContextProgress:
    @pytest.mark.asyncio
    async def test_progress_no_callback(self):
        ctx = Context(user=User(id="u1"))
        await ctx.progress(50, "halfway")  # should not raise

    @pytest.mark.asyncio
    async def test_progress_with_callback(self):
        calls = []
        async def cb(pct, msg):
            calls.append((pct, msg))
        ctx = Context(user=User(id="u1"))
        ctx._progress_callback = cb
        await ctx.progress(75, "almost done")
        assert calls == [(75, "almost done")]


class TestContextLog:
    @pytest.mark.asyncio
    async def test_log(self):
        ctx = Context(user=User(id="u1"), _extension_id="test-ext")
        await ctx.log("test message")  # should not raise
