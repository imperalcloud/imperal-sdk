# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Phase 4 Task 4.2 — Context skeleton access guard + skeleton_data removal.

These tests import from the package (``imperal_sdk.context`` /
``imperal_sdk.errors``) and therefore require Python >= 3.11 due to PEP 604
unions elsewhere in the package. On laptop-level Python 3.9 smoke runs they
will fail at import time; CI (3.11) and the prod venvs run them green.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Skeleton access guard — behaviour
# ---------------------------------------------------------------------------


def _make_guard(tool_type: str, client=None):
    from imperal_sdk.context import _SkeletonAccessGuard
    return _SkeletonAccessGuard(client or MagicMock(), tool_type)


@pytest.mark.asyncio
async def test_skeleton_guard_allows_skeleton_context():
    client = MagicMock()

    async def _fake_get(section):
        return {"section": section, "fresh": True}

    client.get = _fake_get
    guard = _make_guard("skeleton", client)
    result = await guard.get("mail_inbox_summary")
    assert result["fresh"] is True
    assert result["section"] == "mail_inbox_summary"


@pytest.mark.asyncio
async def test_skeleton_guard_blocks_panel():
    from imperal_sdk.errors import SkeletonAccessForbidden
    guard = _make_guard("panel")
    with pytest.raises(SkeletonAccessForbidden):
        await guard.get("mail_inbox_summary")


@pytest.mark.asyncio
async def test_skeleton_guard_blocks_tool():
    from imperal_sdk.errors import SkeletonAccessForbidden
    guard = _make_guard("tool")
    with pytest.raises(SkeletonAccessForbidden):
        await guard.get("anything")


@pytest.mark.asyncio
async def test_skeleton_guard_blocks_chat_fn():
    from imperal_sdk.errors import SkeletonAccessForbidden
    guard = _make_guard("chat_fn")
    with pytest.raises(SkeletonAccessForbidden):
        await guard.get("anything")


def test_skeleton_guard_has_no_update_method():
    guard = _make_guard("skeleton")
    assert not hasattr(guard, "update"), (
        "SkeletonAccessGuard must not expose update() — "
        "I-NO-SKELETON-PUT requires the write path be unreachable from the SDK."
    )


def test_skeleton_client_has_no_update_method():
    from imperal_sdk.skeleton.client import SkeletonClient
    assert not hasattr(SkeletonClient, "update"), (
        "SkeletonClient.update() must not exist in v1.6.0 — "
        "kernel skeleton_save_section activity is sole writer."
    )


def test_skeleton_access_forbidden_is_permission_error():
    from imperal_sdk.errors import SkeletonAccessForbidden
    assert issubclass(SkeletonAccessForbidden, PermissionError)


def test_skeleton_access_forbidden_reexported():
    import imperal_sdk
    assert hasattr(imperal_sdk, "SkeletonAccessForbidden")
    from imperal_sdk.errors import SkeletonAccessForbidden as _direct
    assert imperal_sdk.SkeletonAccessForbidden is _direct


# ---------------------------------------------------------------------------
# Context wiring — skeleton_data gone, guard wrapping active
# ---------------------------------------------------------------------------


def test_context_class_has_no_skeleton_data_attr_assignment():
    """AST-level check: no ``self.skeleton_data = ...`` anywhere in Context."""
    source = Path("src/imperal_sdk/context.py").read_text()
    tree = ast.parse(source)
    ctx_node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "Context"
    )
    for node in ast.walk(ctx_node):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "skeleton_data"
            ):
                pytest.fail(
                    f"Context still assigns self.skeleton_data at line {target.lineno}"
                )


def test_context_constructs_with_tool_type_and_call_token():
    """_tool_type + _call_token must be accepted kwargs and round-trip."""
    from imperal_sdk.auth.user import User
    from imperal_sdk.context import Context

    user = User(id="u-1", email="u@example.com", tenant_id="t-1",
                role="user", scopes=["*"], attributes={})
    ctx = Context(user=user, _tool_type="panel", _call_token="tok-abc")
    assert ctx._tool_type == "panel"
    assert ctx._call_token == "tok-abc"


def test_context_wraps_skeleton_in_guard_for_non_skeleton_tool_type():
    """When a raw skeleton client is provided, ctx.skeleton must be a guard."""
    from imperal_sdk.auth.user import User
    from imperal_sdk.context import Context, _SkeletonAccessGuard

    user = User(id="u-1", email="u@example.com", tenant_id="t-1",
                role="user", scopes=["*"], attributes={})
    raw = MagicMock()
    ctx = Context(user=user, skeleton=raw, _tool_type="panel", _call_token="tok")
    assert isinstance(ctx.skeleton, _SkeletonAccessGuard)
    assert ctx._raw_skeleton is raw


@pytest.mark.asyncio
async def test_context_skeleton_blocks_panel_end_to_end():
    from imperal_sdk.auth.user import User
    from imperal_sdk.context import Context
    from imperal_sdk.errors import SkeletonAccessForbidden

    raw = MagicMock()

    async def _get(section):
        return {"ok": True}
    raw.get = _get

    user = User(id="u-1", email="u@example.com", tenant_id="t-1",
                role="user", scopes=["*"], attributes={})
    ctx = Context(user=user, skeleton=raw, _tool_type="panel")
    with pytest.raises(SkeletonAccessForbidden):
        await ctx.skeleton.get("mail_inbox_summary")


@pytest.mark.asyncio
async def test_context_skeleton_allows_skeleton_tool_type():
    from imperal_sdk.auth.user import User
    from imperal_sdk.context import Context

    raw = MagicMock()

    async def _get(section):
        return {"fresh": True, "section": section}
    raw.get = _get

    user = User(id="u-1", email="u@example.com", tenant_id="t-1",
                role="user", scopes=["*"], attributes={})
    ctx = Context(user=user, skeleton=raw, _tool_type="skeleton")
    result = await ctx.skeleton.get("monitors")
    assert result == {"fresh": True, "section": "monitors"}


# ---------------------------------------------------------------------------
# Task 4.5 — ctx.cache wiring
# ---------------------------------------------------------------------------


def test_context_has_cache_property_attribute():
    """The cache descriptor exists on the class even when no Extension was
    supplied (attribute access returns a working property that raises on
    first use if unconfigured)."""
    from imperal_sdk.context import Context
    assert "cache" in dir(Context)


def test_context_cache_raises_without_extension():
    """Without an Extension reference the cache property must surface a
    clear RuntimeError rather than silently returning None."""
    from imperal_sdk.auth.user import User
    from imperal_sdk.context import Context

    user = User(id="u-1", email="u@example.com", tenant_id="t-1",
                role="user", scopes=["*"], attributes={})
    ctx = Context(user=user)
    with pytest.raises(RuntimeError, match="not available"):
        _ = ctx.cache


def test_context_cache_constructs_with_extension_and_gw():
    """When _extension + a derivable gateway URL are both present, the
    Context builds a CacheClient and exposes it on ctx.cache."""
    from imperal_sdk.auth.user import User
    from imperal_sdk.cache.client import CacheClient
    from imperal_sdk.context import Context
    from imperal_sdk.extension import Extension

    ext = Extension(app_id="mail")
    user = User(id="u-1", email="u@example.com", tenant_id="t-1",
                role="user", scopes=["*"], attributes={})
    ctx = Context(
        user=user,
        _extension=ext,
        _gateway_url="http://gw.example.com",
        _service_token="svc",
        _call_token="tok",
        _tool_type="panel",
    )
    assert isinstance(ctx.cache, CacheClient)
    assert ctx.cache._app_id == "mail"
    assert ctx.cache._user_id == "u-1"
    assert ctx.cache._call_token == "tok"
    assert ctx.cache._service_token == "svc"


def test_context_cache_gateway_url_derived_from_skeleton_client():
    """When ``_gateway_url`` is not passed explicitly, it should be derived
    from the raw skeleton client's ``_gateway_url``."""
    from imperal_sdk.auth.user import User
    from imperal_sdk.context import Context
    from imperal_sdk.extension import Extension
    from imperal_sdk.skeleton.client import SkeletonClient

    ext = Extension(app_id="mail")
    raw_sk = SkeletonClient(
        gateway_url="http://derived.example.com",
        service_token="svc",
        extension_id="mail",
        user_id="u-1",
    )
    user = User(id="u-1", email="u@example.com", tenant_id="t-1",
                role="user", scopes=["*"], attributes={})
    ctx = Context(user=user, skeleton=raw_sk, _extension=ext, _tool_type="tool")
    assert ctx.cache._gw_url == "http://derived.example.com"
    assert ctx.cache._service_token == "svc"
