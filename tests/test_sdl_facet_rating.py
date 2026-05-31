# tests/test_sdl_facet_rating.py
"""SDL Phase 2 — Ratings & Feedback family facets."""
from __future__ import annotations

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.rating import Rated, Reviewed, Sentiment, Voted


class RatingDoc(Entity, Rated, Reviewed):
    pass


class RatingDoc2(Entity, Sentiment, Voted):
    pass


def test_rating_facets_compose_and_are_optional():
    d = RatingDoc(id=1, title="x")
    assert d.rating is None
    assert d.max_score is None
    assert d.review_body is None
    assert d.is_verified is None


def test_rating_facets_accept_values():
    d = RatingDoc(
        id=1, title="x",
        rating=4.5,
        max_score=5.0,
        rating_count=120,
        review_body="Excellent product!",
        is_verified=True,
        would_recommend=True,
    )
    assert d.rating == 4.5
    assert d.rating_count == 120
    assert d.review_body == "Excellent product!"
    assert d.is_verified is True
    assert d.would_recommend is True


def test_rating_roles_present():
    roles = roles_of(RatingDoc)
    assert roles["rating"] == "rating.rating"
    assert roles["max_score"] == "rating.max_score"
    assert roles["rating_count"] == "rating.rating_count"
    assert roles["review_body"] == "rating.review_body"
    assert roles["is_verified"] == "rating.is_verified"


def test_sentiment_voted_roles():
    d = RatingDoc2(id=1, title="x", sentiment="positive", upvotes=42, score=38)
    assert d.sentiment == "positive"
    assert d.upvotes == 42
    assert d.score == 38
    roles = roles_of(RatingDoc2)
    assert roles["sentiment"] == "rating.sentiment"
    assert roles["sentiment_score"] == "rating.sentiment_score"
    assert roles["upvotes"] == "rating.upvotes"
    assert roles["my_vote"] == "rating.my_vote"
