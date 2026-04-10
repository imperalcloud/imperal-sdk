"""Tests for Page[T] cursor-based pagination."""
import pytest
from pydantic import BaseModel
from imperal_sdk.types.pagination import Page


class Item(BaseModel):
    id: str
    name: str


class TestPageBasic:
    def test_empty_page(self):
        page = Page(data=[])
        assert len(page) == 0
        assert page.has_more is False
        assert page.cursor is None
        assert page.total is None

    def test_page_with_data(self):
        items = [Item(id="1", name="a"), Item(id="2", name="b")]
        page = Page(data=items, has_more=True, cursor="abc123", total=10)
        assert len(page) == 2
        assert page.has_more is True
        assert page.cursor == "abc123"
        assert page.total == 10

    def test_page_iteration(self):
        items = [Item(id="1", name="a"), Item(id="2", name="b")]
        page = Page(data=items)
        collected = [item for item in page]
        assert len(collected) == 2
        assert collected[0].id == "1"
        assert collected[1].name == "b"

    def test_page_indexing(self):
        items = [Item(id="1", name="a"), Item(id="2", name="b")]
        page = Page(data=items)
        assert page.data[0].id == "1"
        assert page.data[1].name == "b"


class TestPageWithDicts:
    def test_dict_data(self):
        page = Page(data=[{"id": "1"}, {"id": "2"}], has_more=False)
        assert len(page) == 2
        assert page.data[0]["id"] == "1"


class TestPageSerialization:
    def test_model_dump(self):
        items = [Item(id="1", name="a")]
        page = Page(data=items, cursor="next", has_more=True, total=5)
        d = page.model_dump()
        assert d["data"] == [{"id": "1", "name": "a"}]
        assert d["cursor"] == "next"
        assert d["has_more"] is True
        assert d["total"] == 5

    def test_model_validate(self):
        raw = {"data": [{"id": "1", "name": "a"}], "cursor": None, "has_more": False, "total": None}
        page = Page.model_validate(raw)
        assert len(page) == 1


class TestPageEdgeCases:
    def test_single_item(self):
        page = Page(data=[Item(id="1", name="only")])
        assert len(page) == 1
        for item in page:
            assert item.id == "1"

    def test_large_page(self):
        items = [Item(id=str(i), name=f"item_{i}") for i in range(100)]
        page = Page(data=items, has_more=True, cursor="page2", total=500)
        assert len(page) == 100
        assert page.total == 500
