import pytest
from imperal_sdk.runtime.verbs import run_store
from imperal_sdk.types.pagination import Page


class FakeStore:
    def __init__(self): self.docs = {}
    async def create(self, collection, data): self.docs[data["id"]] = data; return data
    async def query(self, collection, where=None, order_by=None, limit=100, cursor=None):
        rows = [d for d in self.docs.values() if all(d.get(k) == v for k, v in (where or {}).items())]
        return Page(data=rows)  # the REAL Page contract (.data), not a fake .items
    async def update(self, collection, doc_id, data): self.docs[doc_id].update(data); return self.docs[doc_id]
    async def delete(self, collection, doc_id): return self.docs.pop(doc_id, None) is not None
    async def count(self, collection, where=None): return len(self.docs)
    async def get(self, collection, doc_id): return self.docs.get(doc_id)


@pytest.mark.asyncio
async def test_store_create_then_list():
    s = FakeStore()
    await run_store("create", {"kind": "c", "data": {"id": "1", "status": "ended"}}, s)
    out = await run_store("list", {"kind": "c", "where": {"status": "ended"}}, s)
    assert out["ids"] == ["1"]
    assert out["count"] == 1


@pytest.mark.asyncio
async def test_store_update_by_ids_loops():
    s = FakeStore()
    await run_store("create", {"kind": "c", "data": {"id": "1"}}, s)
    await run_store("create", {"kind": "c", "data": {"id": "2"}}, s)
    out = await run_store("update", {"kind": "c", "ids": ["1", "2"], "set": {"archived": True}}, s)
    assert out["count"] == 2
    assert s.docs["1"]["archived"] is True


@pytest.mark.asyncio
async def test_store_create_returns_id():
    s = FakeStore()
    out = await run_store("create", {"kind": "items", "data": {"id": "abc", "name": "x"}}, s)
    assert out["id"] == "abc"


@pytest.mark.asyncio
async def test_store_get():
    s = FakeStore()
    await run_store("create", {"kind": "c", "data": {"id": "42", "val": 99}}, s)
    out = await run_store("get", {"kind": "c", "id": "42"}, s)
    assert out["doc"]["val"] == 99


@pytest.mark.asyncio
async def test_store_delete_by_ids():
    s = FakeStore()
    await run_store("create", {"kind": "c", "data": {"id": "1"}}, s)
    await run_store("create", {"kind": "c", "data": {"id": "2"}}, s)
    out = await run_store("delete", {"kind": "c", "ids": ["1", "2"]}, s)
    assert out["count"] == 2
    assert "1" not in s.docs
    assert "2" not in s.docs


@pytest.mark.asyncio
async def test_store_delete_by_single_id():
    s = FakeStore()
    await run_store("create", {"kind": "c", "data": {"id": "7"}}, s)
    out = await run_store("delete", {"kind": "c", "id": "7"}, s)
    assert out["count"] == 1
    assert "7" not in s.docs


@pytest.mark.asyncio
async def test_store_unknown_op_raises():
    s = FakeStore()
    with pytest.raises(ValueError, match="Unknown store op"):
        await run_store("explode", {"kind": "c"}, s)


@pytest.mark.asyncio
async def test_store_list_against_real_mock_store_counts():
    """Regression: run_store('list') must read Page.data. The prior code read a
    non-existent Page.items, so store.list returned count=0 against the REAL store
    (MockStore/Page) while the old fake (.items) masked it. Exercise the real store."""
    from imperal_sdk.testing import MockContext
    ctx = MockContext(tenant_id="store_list_real")
    await ctx.store.create("c", {"status": "ended"})
    await ctx.store.create("c", {"status": "ended"})
    await ctx.store.create("c", {"status": "running"})
    out = await run_store("list", {"kind": "c", "where": {"status": "ended"}}, ctx.store)
    assert out["count"] == 2
    assert len(out["ids"]) == 2 and all(out["ids"])
