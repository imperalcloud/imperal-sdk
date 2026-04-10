"""Tests for User and Tenant dataclasses."""
import pytest
from imperal_sdk.auth.user import User


class TestUserBasic:
    def test_defaults(self):
        u = User(id="u1")
        assert u.id == "u1"
        assert u.email == ""
        assert u.role == "user"
        assert u.tenant_id == "default"
        assert u.is_active is True
        assert u.scopes == []

    def test_full(self):
        u = User(
            id="u1", email="a@b.com", tenant_id="t1",
            role="admin", scopes=["*"], attributes={"lang": "en"},
        )
        assert u.email == "a@b.com"
        assert u.role == "admin"


class TestHasScope:
    def test_exact_match(self):
        u = User(id="u1", scopes=["crm:read", "crm:write"])
        assert u.has_scope("crm:read") is True
        assert u.has_scope("crm:delete") is False

    def test_wildcard(self):
        u = User(id="u1", scopes=["*"])
        assert u.has_scope("anything") is True

    def test_prefix_wildcard(self):
        u = User(id="u1", scopes=["crm.*"])
        assert u.has_scope("crm.read") is True
        assert u.has_scope("crm.write") is True
        assert u.has_scope("crm") is True
        assert u.has_scope("email.read") is False

    def test_empty_scopes(self):
        u = User(id="u1", scopes=[])
        assert u.has_scope("anything") is False


class TestHasRole:
    def test_matching_role(self):
        u = User(id="u1", role="admin")
        assert u.has_role("admin") is True

    def test_non_matching_role(self):
        u = User(id="u1", role="user")
        assert u.has_role("admin") is False

    def test_default_role(self):
        u = User(id="u1")
        assert u.has_role("user") is True
        assert u.has_role("admin") is False


class TestTenant:
    def test_basic(self):
        from imperal_sdk.auth.user import Tenant
        t = Tenant(id="t1", name="Acme Corp", plan="pro")
        assert t.id == "t1"
        assert t.name == "Acme Corp"
        assert t.plan == "pro"

    def test_defaults(self):
        from imperal_sdk.auth.user import Tenant
        t = Tenant(id="t1")
        assert t.name == ""
        assert t.plan == ""
        assert t.attributes == {}
