# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Federal CI gate: every field emitted by ``generate_manifest`` must be
accepted by the ``Manifest``/``Tool`` schema validators.

Catches the v4.1.4 → v4.1.5 class of bug where ``chat/extension.py``
started emitting ``id_projection`` and ``manifest.py`` started emitting
``sdk_version``, but ``manifest_schema.Tool`` and ``Manifest`` had
``model_config = ConfigDict(extra='forbid')`` without those fields —
production extensions shipped manifests that local CLI ``imperal
validate`` rejected. The drift was invisible until somebody ran the
local CLI on a freshly-built manifest.

Federal invariant: ``I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC``.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from imperal_sdk import Extension, ChatExtension, ActionResult
from imperal_sdk.manifest import generate_manifest, validate_manifest_dict


class _PingParams(BaseModel):
    """Pydantic params model for the canary @chat.function."""
    label: str = Field(description="Echo target", default="world")


def _build_canary_extension() -> Extension:
    """A small Extension that exercises every emitter code path:
    @ext.tool, @ext.signal, @ext.schedule, @ext.webhook, @ext.on_event,
    @ext.on_install, @ext.health_check, @chat.function with all v4
    fields (action_type, event, chain_callable, effects, id_projection),
    and panel/tray declarations through @ext.panel.
    """
    ext = Extension(
        "ci-canary",
        version="0.0.1",
        capabilities=["canary:read", "canary:write"],
        display_name="CI Canary",
        description=(
            "Canary extension exercising every manifest emitter code path "
            "for I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC roundtrip validation."
        ),
        icon="canary.svg",
        actions_explicit=True,
    )

    @ext.tool("plain_tool", scopes=["canary:read"], description="Plain tool entry.")
    async def _plain_tool(ctx, **kwargs):  # noqa: ARG001
        return {"ok": True}

    @ext.signal("on_canary_signal")
    async def _signal(ctx, payload):  # noqa: ARG001
        return None

    @ext.schedule("nightly", cron="0 0 * * *")
    async def _scheduled(ctx):  # noqa: ARG001
        return None

    @ext.webhook("/inbound", method="POST", secret_header="X-Canary-Sig")
    async def _webhook(ctx, headers, body, query_params):  # noqa: ARG001
        return {"ack": True}

    @ext.on_event("canary.fired")
    async def _on_event(ctx, event):  # noqa: ARG001
        return None

    @ext.on_install
    async def _on_install(ctx):  # noqa: ARG001
        return None

    @ext.health_check
    async def _health(ctx):  # noqa: ARG001
        return {"status": "ok"}

    @ext.panel("sidebar", slot="left", title="Canary", icon="Bug",
               default_width=300, min_width=200, max_width=500)
    async def _panel(ctx, **kwargs):  # noqa: ARG001
        return None

    chat = ChatExtension(
        ext=ext,
        tool_name="canary_chat",
        description="Canary chat tool that exercises all @chat.function fields.",
    )

    @chat.function(
        "ping",
        action_type="read",
        description="Echo back a label — read action with no side effect.",
    )
    async def _fn_ping(ctx, params: _PingParams) -> ActionResult:  # noqa: ARG001
        return ActionResult.success(data={"label": params.label}, summary=f"pong {params.label}")

    @chat.function(
        "save",
        action_type="write",
        event="canary_saved",
        chain_callable=True,
        effects=["create:canary"],
        id_projection="label",
        description="Persist a label — exercises write+effects+id_projection.",
    )
    async def _fn_save(ctx, params: _PingParams) -> ActionResult:  # noqa: ARG001
        return ActionResult.success(data={"saved": params.label}, summary=f"saved {params.label}")

    @chat.function(
        "purge",
        action_type="destructive",
        event="canary_purged",
        chain_callable=True,
        effects=["delete:canary"],
        id_projection="label",
        description="Purge a label — destructive path with effects.",
    )
    async def _fn_purge(ctx, params: _PingParams) -> ActionResult:  # noqa: ARG001
        return ActionResult.success(data={"purged": params.label}, summary=f"purged {params.label}")

    return ext


def test_roundtrip_emitter_to_schema():
    """Every key generate_manifest emits must round-trip through the schema.

    `validate_manifest_dict` returns ValidationIssue list; an empty list
    means the schema accepted every field. A non-empty list (especially
    M3 'Extra inputs are not permitted') is the canonical drift signal.
    """
    ext = _build_canary_extension()
    manifest = generate_manifest(ext)
    issues = validate_manifest_dict(manifest)
    assert issues == [], (
        "I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC violated — generate_manifest "
        "emitted a field that the Manifest/Tool schema rejects. "
        f"Issues: {issues}"
    )


def test_emitter_writes_v4_required_fields():
    """Sanity floor — these top-level fields MUST always be present."""
    ext = _build_canary_extension()
    manifest = generate_manifest(ext)
    required = {
        "manifest_schema_version",
        "sdk_version",       # v4.1.5 — auto-emitted from imperal_sdk.__version__
        "app_id",
        "version",
        "name",
        "description",
        "icon",
        "actions_explicit",
        "capabilities",
        "tools",
    }
    missing = required - manifest.keys()
    assert not missing, f"emitter missing required top-level keys: {missing}"


def test_emitter_writes_v4_chat_function_fields_per_tool():
    """Every @chat.function tool entry must carry the v4 contract fields."""
    ext = _build_canary_extension()
    manifest = generate_manifest(ext)
    chat_tool_names = {"ping", "save", "purge"}
    chat_tools = [t for t in manifest["tools"] if t["name"] in chat_tool_names]
    assert len(chat_tools) == len(chat_tool_names), (
        f"emitter dropped chat tools — got {[t['name'] for t in chat_tools]}"
    )
    required_per_tool = {
        "name", "description", "action_type", "chain_callable",
        "effects", "params_schema", "event", "id_projection",
    }
    for tool in chat_tools:
        missing = required_per_tool - tool.keys()
        assert not missing, (
            f"chat tool {tool['name']!r} missing v4 fields: {missing}"
        )
