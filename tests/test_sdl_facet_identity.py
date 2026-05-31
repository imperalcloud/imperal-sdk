# tests/test_sdl_facet_identity.py
"""SDL Phase 2 — Identity & Provenance family facets (core.*)."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.identity import Localized, Versioned, Iconified, Lifecycle


class Doc(Entity, Localized, Versioned, Iconified, Lifecycle):
    pass


def test_identity_facets_compose_and_are_optional():
    d = Doc(id=1, title="x")
    assert d.language is None
    assert d.version is None
    assert d.icon is None
    assert d.is_archived is None


def test_localized_accepts_values():
    d = Doc(id=1, title="x", language="en", locale="en_US", text_direction="ltr")
    assert d.language == "en"
    assert d.locale == "en_US"
    assert d.text_direction == "ltr"


def test_versioned_accepts_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = Doc(id=1, title="x", version="1.0.0", semver="1.0.0", revision=3,
            is_latest=True, channel="stable", released_at=now)
    assert d.version == "1.0.0"
    assert d.is_latest is True
    assert d.channel == "stable"
    assert d.released_at == now


def test_iconified_accepts_values():
    d = Doc(id=1, title="x", icon="star", emoji="⭐", color_hex="#ff0000",
            avatar_url="https://example.com/img.png")
    assert d.icon == "star"
    assert d.emoji == "⭐"
    assert d.color_hex == "#ff0000"


def test_lifecycle_accepts_values():
    d = Doc(id=1, title="x", is_archived=True, is_pinned=False,
            is_favorite=True, is_deleted=False, visibility="public")
    assert d.is_archived is True
    assert d.visibility == "public"


def test_identity_roles_present():
    roles = roles_of(Doc)
    assert roles["language"] == "core.language"
    assert roles["version"] == "core.version"
    assert roles["icon"] == "core.icon"
    assert roles["is_archived"] == "core.is_archived"
    assert roles["visibility"] == "core.visibility"
    assert roles["localized_title"] == "core.localized_title"
    assert roles["color_hex"] == "core.color_hex"
    assert roles["channel"] == "core.channel"
