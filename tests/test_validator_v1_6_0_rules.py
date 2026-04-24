# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for v1.6.0 validator rules.

Seven new rules: SKEL-GUARD-1, SKEL-GUARD-2, SKEL-GUARD-3, CACHE-MODEL-1,
CACHE-TTL-1, MANIFEST-SKELETON-1, SDK-VERSION-1.

Each rule has a positive (triggers) test and a negative (does NOT trigger)
test — 14 tests in total. Source trees are written to temp dirs; no Extension
instance is required because the rules are static (AST + JSON).
"""
from __future__ import annotations

import pathlib
import pytest

from imperal_sdk.validator_v1_6_0 import (
    validate_source_tree,
    validate_manifest_v1_6_0,
)


def _write(root: pathlib.Path, name: str, body: str) -> None:
    (root / name).write_text(body, encoding="utf-8")


def _rules(issues, rule: str) -> list:
    return [i for i in issues if i.rule == rule]


# ---------------------------------------------------------------------------
# SKEL-GUARD-1 — ctx.skeleton.get() outside @ext.skeleton
# ---------------------------------------------------------------------------


def test_skel_guard_1_triggers_on_panel_reading_skeleton(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.panel("dashboard")
async def dashboard(ctx):
    data = await ctx.skeleton.get("monitors")
    return data
""")
    issues = validate_source_tree(str(tmp_path))
    hits = _rules(issues, "SKEL-GUARD-1")
    assert len(hits) == 1, issues
    assert "dashboard" in hits[0].message


def test_skel_guard_1_allows_skeleton_decorated_tool(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.skeleton("monitors")
async def refresh_monitors(ctx):
    prev = await ctx.skeleton.get("monitors")
    return {"response": {"count": 0, "prev": prev}}
""")
    issues = validate_source_tree(str(tmp_path))
    assert _rules(issues, "SKEL-GUARD-1") == []


# ---------------------------------------------------------------------------
# SKEL-GUARD-2 — ctx.skeleton_data removed
# ---------------------------------------------------------------------------


def test_skel_guard_2_triggers_on_skeleton_data_attribute(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.tool("peek")
async def peek(ctx):
    return ctx.skeleton_data
""")
    issues = validate_source_tree(str(tmp_path))
    assert len(_rules(issues, "SKEL-GUARD-2")) == 1


def test_skel_guard_2_no_false_positive_on_local_var(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.tool("peek")
async def peek(ctx):
    skeleton_data = {"x": 1}  # local var named skeleton_data, NOT ctx attribute
    return skeleton_data
""")
    issues = validate_source_tree(str(tmp_path))
    assert _rules(issues, "SKEL-GUARD-2") == []


# ---------------------------------------------------------------------------
# SKEL-GUARD-3 — ctx.skeleton.update removed
# ---------------------------------------------------------------------------


def test_skel_guard_3_triggers_on_update_call(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.skeleton("monitors")
async def refresh_monitors(ctx):
    await ctx.skeleton.update("monitors", {"count": 0})
    return {"response": {"count": 0}}
""")
    issues = validate_source_tree(str(tmp_path))
    assert len(_rules(issues, "SKEL-GUARD-3")) == 1


def test_skel_guard_3_allows_skeleton_get_only(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.skeleton("monitors")
async def refresh_monitors(ctx):
    prev = await ctx.skeleton.get("monitors")
    return {"response": {"count": len(prev or {})}}
""")
    issues = validate_source_tree(str(tmp_path))
    assert _rules(issues, "SKEL-GUARD-3") == []


# ---------------------------------------------------------------------------
# CACHE-MODEL-1 — ctx.cache.set/get with unregistered model
# ---------------------------------------------------------------------------


def test_cache_model_1_triggers_when_model_not_registered(tmp_path):
    _write(tmp_path, "main.py", """
from pydantic import BaseModel
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

class OtherModel(BaseModel):
    x: int

@ext.cache_model("inbox_summary")
class InboxSummary(BaseModel):
    unread: int

@ext.tool("probe")
async def probe(ctx):
    await ctx.cache.set("k", OtherModel(x=1), ttl_seconds=60)
    return None
""")
    issues = validate_source_tree(str(tmp_path))
    hits = _rules(issues, "CACHE-MODEL-1")
    assert len(hits) == 1, issues
    assert "OtherModel" in hits[0].message


def test_cache_model_1_silent_when_model_is_registered(tmp_path):
    _write(tmp_path, "main.py", """
from pydantic import BaseModel
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.cache_model("inbox_summary")
class InboxSummary(BaseModel):
    unread: int

@ext.tool("probe")
async def probe(ctx):
    await ctx.cache.set("k", InboxSummary(unread=0), ttl_seconds=60)
    val = await ctx.cache.get("k", InboxSummary)
    return val
""")
    issues = validate_source_tree(str(tmp_path))
    assert _rules(issues, "CACHE-MODEL-1") == []


# ---------------------------------------------------------------------------
# CACHE-TTL-1 — literal ttl_seconds outside [5, 300]
# ---------------------------------------------------------------------------


def test_cache_ttl_1_triggers_on_out_of_range_ttl(tmp_path):
    _write(tmp_path, "main.py", """
from pydantic import BaseModel
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.cache_model("inbox_summary")
class InboxSummary(BaseModel):
    unread: int

@ext.tool("probe")
async def probe(ctx):
    # 600 is above the 300s cap — should trigger CACHE-TTL-1
    await ctx.cache.set("k", InboxSummary(unread=0), ttl_seconds=600)
    # 2 is below the 5s floor — second hit
    await ctx.cache.set("k2", InboxSummary(unread=0), ttl_seconds=2)
""")
    issues = validate_source_tree(str(tmp_path))
    hits = _rules(issues, "CACHE-TTL-1")
    assert len(hits) == 2, issues


def test_cache_ttl_1_silent_on_valid_ttl(tmp_path):
    _write(tmp_path, "main.py", """
from pydantic import BaseModel
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.cache_model("inbox_summary")
class InboxSummary(BaseModel):
    unread: int

@ext.tool("probe")
async def probe(ctx):
    await ctx.cache.set("k", InboxSummary(unread=0), ttl_seconds=60)
    await ctx.cache.set("k2", InboxSummary(unread=0), ttl_seconds=300)
    await ctx.cache.set("k3", InboxSummary(unread=0), ttl_seconds=5)
""")
    issues = validate_source_tree(str(tmp_path))
    assert _rules(issues, "CACHE-TTL-1") == []


# ---------------------------------------------------------------------------
# MANIFEST-SKELETON-1 — skeleton_refresh_*/skeleton_alert_* with @ext.tool
# ---------------------------------------------------------------------------


def test_manifest_skeleton_1_triggers_on_wrong_decorator(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.tool("skeleton_refresh_monitors")
async def refresh_monitors(ctx):
    return {"response": {"count": 0}}

@ext.tool("skeleton_alert_monitors")
async def alert_monitors(ctx, prev, curr):
    return {"response": {"changed": False}}
""")
    issues = validate_source_tree(str(tmp_path))
    hits = _rules(issues, "MANIFEST-SKELETON-1")
    assert len(hits) == 2, issues
    names = sorted(h.message for h in hits)
    assert "skeleton_refresh_monitors" in names[0] or "skeleton_refresh_monitors" in names[1]


def test_manifest_skeleton_1_silent_on_ext_skeleton_decorator(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.skeleton("monitors", alert=True)
async def refresh_monitors(ctx):
    return {"response": {"count": 0}}
""")
    issues = validate_source_tree(str(tmp_path))
    assert _rules(issues, "MANIFEST-SKELETON-1") == []


# ---------------------------------------------------------------------------
# SDK-VERSION-1 — manifest sdk_version vs v1.6.0 features
# ---------------------------------------------------------------------------


def test_sdk_version_1_warns_when_using_v1_6_features_without_version(tmp_path):
    _write(tmp_path, "main.py", """
from pydantic import BaseModel
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.cache_model("inbox_summary")
class InboxSummary(BaseModel):
    unread: int

@ext.tool("probe")
async def probe(ctx):
    await ctx.cache.set("k", InboxSummary(unread=0), ttl_seconds=60)
""")
    # manifest missing sdk_version
    manifest = {"app_id": "app", "version": "1.0.0"}
    issues = validate_manifest_v1_6_0(manifest, str(tmp_path))
    hits = _rules(issues, "SDK-VERSION-1")
    assert len(hits) == 1
    assert hits[0].level == "WARN"


def test_sdk_version_1_silent_on_correct_sdk_version(tmp_path):
    _write(tmp_path, "main.py", """
from pydantic import BaseModel
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.cache_model("inbox_summary")
class InboxSummary(BaseModel):
    unread: int

@ext.tool("probe")
async def probe(ctx):
    await ctx.cache.set("k", InboxSummary(unread=0), ttl_seconds=60)
""")
    manifest = {"app_id": "app", "version": "1.0.0", "sdk_version": "1.6.0"}
    issues = validate_manifest_v1_6_0(manifest, str(tmp_path))
    warn_hits = [i for i in _rules(issues, "SDK-VERSION-1") if i.level == "WARN"]
    assert warn_hits == []


def test_sdk_version_1_warns_on_stale_version_with_v1_6_features(tmp_path):
    _write(tmp_path, "main.py", """
from imperal_sdk import Extension

ext = Extension("app", version="1.0.0")

@ext.skeleton("monitors")
async def refresh_monitors(ctx):
    return {"response": {"count": 0}}
""")
    manifest = {"app_id": "app", "version": "1.0.0", "sdk_version": "1.5.22"}
    issues = validate_manifest_v1_6_0(manifest, str(tmp_path))
    hits = _rules(issues, "SDK-VERSION-1")
    assert len(hits) == 1
    assert hits[0].level == "WARN"
    assert "1.5.22" in hits[0].message
