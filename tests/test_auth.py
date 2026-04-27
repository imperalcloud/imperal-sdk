# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import pytest
from imperal_sdk.types.identity import UserContext


def test_user_has_scope_exact():
    user = UserContext(imperal_id="imp_u_123", scopes=["cases.read", "cases.write"], email="test@example.com", tenant_id="default", role="user")
    assert user.has_scope("cases.read") is True
    assert user.has_scope("cases.delete") is False


def test_user_has_scope_wildcard():
    user = UserContext(imperal_id="imp_u_123", scopes=["cases.*"], email="test@example.com", tenant_id="default", role="user")
    assert user.has_scope("cases.read") is True
    assert user.has_scope("cases.write") is True
    assert user.has_scope("extensions.read") is False


def test_user_has_scope_star():
    user = UserContext(imperal_id="imp_u_123", scopes=["*"], email="test@example.com", tenant_id="default", role="user")
    assert user.has_scope("anything") is True


def test_user_has_scope_empty():
    user = UserContext(imperal_id="imp_u_123", scopes=[], email="test@example.com", tenant_id="default", role="user")
    assert user.has_scope("cases.read") is False


def test_user_defaults():
    user = UserContext(imperal_id="imp_u_abc", email="test@example.com", tenant_id="default", role="user")
    assert user.tenant_id == "default"
    assert user.role == "user"
    assert user.scopes == []
    assert user.org_id is None
