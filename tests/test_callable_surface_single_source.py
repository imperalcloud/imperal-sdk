# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Federal: I-CALLABLE-SURFACE-SINGLE-SOURCE (2026-08-21).

Live report: deploying WordPress Hub returned "5 of 259 functions synced".

The app was fine. The platform was asking the wrong question. An extension
declares callables through two decorators writing to two registries:

    @ext.tool      -> Extension._tools
    @chat.function -> ChatExtension._functions  (via ext._chat_extensions)

``generate_manifest`` reads BOTH, so the manifest was complete (260 tools).
The Developer Portal's registry sync iterated ``ext.tools`` ONLY, so it saw
1 real tool + 3 ``__panel__*`` + 1 ``__tray__``-shaped synthetic = 5 -- the
exact number in the bug report. The catalog then served 5 callables for an
app with 260.

``callable_functions(ext)`` is now the ONE way to ask. This suite pins the
property that makes the fix permanent: its name set must EQUAL the manifest's
name set. If a future decorator adds a third registry and only teaches the
manifest about it, this test goes red the same day.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from imperal_sdk import ActionResult, ChatExtension, Extension
from imperal_sdk.catalog import callable_function_names, callable_functions
from imperal_sdk.manifest import generate_manifest


class _Params(BaseModel):
    """Params model for the canary chat functions."""
    label: str = Field(description="Echo target", default="world")


class _Result(BaseModel):
    """Typed return contract (V23)."""
    label: str = Field(description="Echoed label", default="")


def _wordpress_hub_shaped(n_functions: int = 12) -> Extension:
    """An extension shaped like the app that exposed the bug: ONE @ext.tool,
    several panels (synthetic entries), and many @chat.function declarations."""
    ext = Extension("shaped-app", version="1.0.0", actions_explicit=True)
    chat = ChatExtension(ext, tool_name="shaped-app", description="Canary chat surface")

    @ext.tool("skeleton_alert_sites", description="Report a site change.")
    async def skeleton_alert_sites(ctx, old: dict | None = None, new: dict | None = None) -> dict:
        return {"response": ""}

    @ext.panel("main")
    async def main_panel(ctx):
        return {}

    @ext.panel("side")
    async def side_panel(ctx):
        return {}

    for i in range(n_functions):
        @chat.function(f"do_thing_{i}",
                       "Does the canary thing number %d for the shaped app." % i,
                       action_type="read", data_model=_Result)
        async def _fn(ctx, params: _Params) -> ActionResult:
            return ActionResult(ok=True)

    return ext


# ───────────────────────── the property that must hold ────────────────────────


@pytest.mark.federal
def test_catalog_equals_what_the_manifest_emits():
    """THE invariant. Two registries, one answer -- forever verifiable."""
    ext = _wordpress_hub_shaped()
    manifest_names = {t["name"] for t in generate_manifest(ext)["tools"]}
    assert callable_function_names(ext) == manifest_names


@pytest.mark.federal
def test_chat_functions_are_not_lost():
    """The reported bug, stated directly: 1 tool + 12 functions must be 13,
    not 1 -- and certainly not the 5 that ext.tools alone reported."""
    ext = _wordpress_hub_shaped(n_functions=12)
    names = callable_function_names(ext)
    assert len(names) == 13
    assert "skeleton_alert_sites" in names
    assert {f"do_thing_{i}" for i in range(12)} <= names


@pytest.mark.federal
def test_synthetic_entries_stay_out():
    """Panels/tray/webhooks are plumbing. They live in ext.tools with a ``__``
    prefix and inflated the old count -- they are not callable surface."""
    ext = _wordpress_hub_shaped()
    assert not [n for n in callable_function_names(ext) if n.startswith("__")]


@pytest.mark.federal
def test_synthetic_entries_are_reachable_when_asked_for():
    """Opt-in, because the panel sync legitimately needs them."""
    ext = _wordpress_hub_shaped()
    everything = {e["name"] for e in callable_functions(ext, include_synthetic=True)}
    assert [n for n in everything if n.startswith("__panel__")]


@pytest.mark.federal
def test_entries_carry_what_a_registry_row_needs():
    """The Developer Portal builds catalog rows straight from these dicts."""
    ext = _wordpress_hub_shaped(n_functions=1)
    by_name = {e["name"]: e for e in callable_functions(ext)}

    fn = by_name["do_thing_0"]
    assert fn["kind"] == "chat_function"
    assert fn["owner_chat_tool"] == "shaped-app"
    assert fn["action_type"] == "read"
    assert len(fn["description"]) >= 20

    tool = by_name["skeleton_alert_sites"]
    assert tool["kind"] == "tool"
    assert tool["action_type"] == "read"


@pytest.mark.federal
def test_action_type_survives_the_trip():
    """A destructive function must not arrive at the catalog looking read-only
    -- action_type drives the kernel's confirmation gate."""
    ext = Extension("act-app", version="1.0.0", actions_explicit=True)
    chat = ChatExtension(ext, tool_name="act-app", description="Action canary")

    @chat.function("delete_everything",
                   "Deletes the canary resource permanently, no recovery.",
                   action_type="destructive", data_model=_Result)
    async def delete_everything(ctx, params: _Params) -> ActionResult:
        return ActionResult(ok=True)

    entry = {e["name"]: e for e in callable_functions(ext)}["delete_everything"]
    assert entry["action_type"] == "destructive"


# ─────────────────────────────── robustness ───────────────────────────────────


@pytest.mark.federal
def test_an_extension_with_no_chat_surface_still_works():
    """Plenty of apps never touch ChatExtension."""
    ext = Extension("plain-app", version="1.0.0")

    @ext.tool("ping", description="Ping the canary app for liveness.")
    async def ping(ctx):
        return {}

    assert callable_function_names(ext) == {"ping"}


@pytest.mark.federal
def test_an_empty_extension_yields_an_empty_surface():
    assert callable_functions(Extension("empty-app", version="1.0.0")) == []


@pytest.mark.federal
def test_a_junk_object_never_raises():
    """This runs inside deploy. A weird object must degrade, never explode."""
    class _Junk:
        tools = None
        _chat_extensions = None

    assert callable_functions(_Junk()) == []
    assert callable_functions(object()) == []


@pytest.mark.federal
def test_order_is_deterministic():
    """Callers diff these lists across deploys; unstable order = false churn."""
    ext = _wordpress_hub_shaped()
    assert [e["name"] for e in callable_functions(ext)] == \
           [e["name"] for e in callable_functions(ext)]


@pytest.mark.federal
def test_a_name_declared_twice_appears_once():
    """The catalog is a set of callables -- a duplicate must not double-count."""
    ext = Extension("dup-app", version="1.0.0", actions_explicit=True)
    chat = ChatExtension(ext, tool_name="dup-app", description="Duplicate canary")

    @ext.tool("overlap", description="A tool that shares its name with a fn.")
    async def overlap_tool(ctx):
        return {}

    @chat.function("overlap", "A chat function sharing the tool's name here.",
                   action_type="read", data_model=_Result)
    async def overlap_fn(ctx, params: _Params) -> ActionResult:
        return ActionResult(ok=True)

    names = [e["name"] for e in callable_functions(ext)]
    assert names.count("overlap") == 1
