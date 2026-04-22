# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""L1 tests for ctx.as_user — system-context primitive."""
from __future__ import annotations

import pytest

from imperal_sdk.context import Context
from imperal_sdk.auth.user import User


def _make_ctx(user_id: str = "__system__", ext_id: str = "test-ext",
              tenant_id: str = "default") -> Context:
    user = User(id=user_id, email="", tenant_id=tenant_id, role="system",
                scopes=["*"], attributes={})
    return Context(user=user, tenant=tenant_id, _extension_id=ext_id)


def test_as_user_raises_if_not_system():
    """I-AS-USER-1 — scoped copy requires system context."""
    ctx = _make_ctx(user_id="real-user")
    with pytest.raises(RuntimeError, match="system context"):
        ctx.as_user("target-user")


def test_as_user_rejects_empty_or_system():
    ctx = _make_ctx()
    with pytest.raises(ValueError):
        ctx.as_user("")
    with pytest.raises(ValueError):
        ctx.as_user("__system__")


def test_as_user_preserves_extension_tenant_agency():
    """I-AS-USER-2 — preserved fields."""
    ctx = _make_ctx(ext_id="web-tools", tenant_id="tenant_a")
    ctx.agency_id = "agency_x"
    scoped = ctx.as_user("user-42")
    assert scoped._extension_id == "web-tools"
    assert scoped.user.tenant_id == "tenant_a"
    assert scoped.agency_id == "agency_x"


def test_as_user_changes_only_user_id():
    ctx = _make_ctx()
    scoped = ctx.as_user("user-42")
    assert scoped.user.id == "user-42"
    assert scoped.user.role == "system"  # preserved
    assert scoped.user.scopes == ["*"]    # preserved
    assert scoped.user.attributes.get("scoped_from") == "__system__"


def test_as_user_rewires_store_with_new_user_id(mock_store_factory):
    """Verify StoreClient in scoped ctx is a new instance with new user_id."""
    ctx = mock_store_factory.build_system_ctx(ext_id="web-tools")
    assert ctx.store._user_id == "__system__"
    scoped = ctx.as_user("user-42")
    assert scoped.store._user_id == "user-42"
    assert scoped.store._extension_id == "web-tools"
    assert scoped.store._tenant_id == ctx.store._tenant_id
    # New instance — not a shared reference
    assert scoped.store is not ctx.store


def test_as_user_reuses_ai_storage_http_config(mock_store_factory):
    """ai, storage, http, config are NOT user-scoped — same instances preserved."""
    ctx = mock_store_factory.build_system_ctx()
    scoped = ctx.as_user("user-42")
    assert scoped.ai is ctx.ai
    assert scoped.storage is ctx.storage
    assert scoped.http is ctx.http
    assert scoped.config is ctx.config
