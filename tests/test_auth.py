# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import pytest
from imperal_sdk.auth.user import User


def test_user_has_scope_exact():
    user = User(id="imp_u_123", scopes=["cases.read", "cases.write"])
    assert user.has_scope("cases.read") is True
    assert user.has_scope("cases.delete") is False


def test_user_has_scope_wildcard():
    user = User(id="imp_u_123", scopes=["cases.*"])
    assert user.has_scope("cases.read") is True
    assert user.has_scope("cases.write") is True
    assert user.has_scope("extensions.read") is False


def test_user_has_scope_star():
    user = User(id="imp_u_123", scopes=["*"])
    assert user.has_scope("anything") is True


def test_user_has_scope_empty():
    user = User(id="imp_u_123", scopes=[])
    assert user.has_scope("cases.read") is False


def test_user_defaults():
    user = User(id="imp_u_abc")
    assert user.tenant_id == "default"
    assert user.role == "user"
    assert user.scopes == []
    assert user.org_id is None
