"""Tests for UserContext methods (W1, 2026-04-27).

Canonical types live in `imperal_sdk.types.identity`. UserContext requires
`imperal_id`, `email`, `tenant_id`, `role` (no defaults — explicit identity).
"""
import pytest
from imperal_sdk.types.identity import UserContext


def _make(**overrides):
    """Default UserContext with required fields filled — override per test."""
    base = dict(
        imperal_id="u1",
        email="u@example.com",
        tenant_id="default",
        role="user",
    )
    base.update(overrides)
    return UserContext(**base)


class TestUserBasic:
    def test_required_fields(self):
        u = _make()
        assert u.imperal_id == "u1"
        assert u.email == "u@example.com"
        assert u.role == "user"
        assert u.tenant_id == "default"
        assert u.is_active is True
        assert u.scopes == []
        assert u.attributes == {}

    def test_with_full_attributes(self):
        u = _make(
            email="a@b.com", tenant_id="t1",
            role="admin", scopes=["*"], attributes={"lang": "en"},
        )
        assert u.email == "a@b.com"
        assert u.role == "admin"
        assert u.scopes == ["*"]


class TestHasScope:
    def test_exact_match(self):
        u = _make(scopes=["crm.read", "crm.write"])
        assert u.has_scope("crm.read") is True
        assert u.has_scope("crm.delete") is False

    def test_wildcard(self):
        u = _make(scopes=["*"])
        assert u.has_scope("anything") is True

    def test_prefix_wildcard(self):
        u = _make(scopes=["crm.*"])
        assert u.has_scope("crm.read") is True
        assert u.has_scope("crm.write") is True
        assert u.has_scope("email.read") is False

    def test_empty_scopes(self):
        u = _make(scopes=[])
        assert u.has_scope("anything") is False


class TestHasRole:
    def test_matching_role(self):
        u = _make(role="admin")
        assert u.has_role("admin") is True

    def test_non_matching_role(self):
        u = _make(role="user")
        assert u.has_role("admin") is False
