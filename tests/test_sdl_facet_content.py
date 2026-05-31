# tests/test_sdl_facet_content.py
"""SDL Phase 2 — Content & Documents family facets (content.*)."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, Ref, roles_of
from imperal_sdk.sdl.facets.content import Bodied, Excerptable, Categorized, Attached, Editorial


class Article(Entity, Bodied, Excerptable, Categorized, Attached, Editorial):
    pass


def test_content_facets_compose_and_are_optional():
    a = Article(id=1, title="x")
    assert a.body is None
    assert a.excerpt is None
    assert a.tags is None
    assert a.attachments is None
    assert a.editorial_state is None


def test_bodied_accepts_values():
    a = Article(id=1, title="x", body="# Hello", body_format="md", raw_body="# Hello")
    assert a.body == "# Hello"
    assert a.body_format == "md"


def test_excerptable_accepts_values():
    a = Article(id=1, title="x", excerpt="Short intro", summary="Summary",
                word_count=500, reading_time_s=120)
    assert a.excerpt == "Short intro"
    assert a.word_count == 500
    assert a.reading_time_s == 120


def test_categorized_accepts_values():
    cat = Ref(id=1, kind="category", title="Tech")
    a = Article(id=1, title="x", tags=["python", "sdk"],
                categories=[cat], topics=["AI"], keywords=["ml"])
    assert a.tags == ["python", "sdk"]
    assert a.categories == [cat]


def test_attached_accepts_values():
    att = Ref(id=5, kind="file", title="doc.pdf")
    a = Article(id=1, title="x", attachments=[att], attachment_count=1,
                has_attachments=True)
    assert a.attachments == [att]
    assert a.attachment_count == 1
    assert a.has_attachments is True


def test_editorial_accepts_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    a = Article(id=1, title="x", editorial_state="published", is_draft=False,
                published_at=now, first_published_at=now)
    assert a.editorial_state == "published"
    assert a.is_draft is False
    assert a.published_at == now


def test_content_roles_present():
    roles = roles_of(Article)
    assert roles["body"] == "content.body"
    assert roles["body_format"] == "content.body_format"
    assert roles["excerpt"] == "content.excerpt"
    assert roles["summary"] == "content.summary"
    assert roles["word_count"] == "content.word_count"
    assert roles["tags"] == "content.tags"
    assert roles["categories"] == "content.categories"
    assert roles["attachments"] == "content.attachments"
    assert roles["attachment_count"] == "content.attachment_count"
    assert roles["editorial_state"] == "content.editorial_state"
    assert roles["published_at"] == "content.published_at"
