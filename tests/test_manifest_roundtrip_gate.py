# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Federal CI gate: every field emitted by ``generate_manifest`` must be
accepted by the ``Manifest``/``Tool`` schema validators — and vice versa.

Catches the v4.1.4 → v4.1.5 class of bug where ``chat/extension.py``
started emitting ``id_projection`` and ``manifest.py`` started emitting
``sdk_version``, but ``manifest_schema.Tool`` and ``Manifest`` had
``model_config = ConfigDict(extra='forbid')`` without those fields —
production extensions shipped manifests that local CLI ``imperal
validate`` rejected. The drift was invisible until somebody ran the
local CLI on a freshly-built manifest. Recurred at v5.9.4 with panel
metadata and ``secrets[].scope``/``env_fallback`` because the canary
below wasn't maximal — it now exercises EVERY emission site the SDK
offers, plus the reverse direction (schema-known fields hand-added to
``imperal.json`` must survive an ``imperal build`` disk merge).

Federal invariant: ``I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC``.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from imperal_sdk import Extension, ChatExtension, ActionResult
from imperal_sdk.manifest import (
    generate_manifest,
    save_manifest,
    validate_manifest_dict,
)
from imperal_sdk.manifest_schema import Manifest

_ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"></svg>'


class _PingParams(BaseModel):
    """Pydantic params model for the canary @chat.function."""
    label: str = Field(description="Echo target", default="world")


class _PingResult(BaseModel):
    """Typed return contract for the canary @chat.function entries (V23)."""
    label: str = Field(description="Echoed label", default="")


def _build_canary_extension() -> Extension:
    """A small Extension that exercises EVERY manifest emitter code path.

    If the SDK gains a new manifest-emitting feature, this canary MUST
    grow with it — ``test_maximal_canary_covers_every_generator_field``
    fails otherwise. Exercised sites: constructor metadata (incl.
    ``migrations_dir`` + ``config_defaults`` + ``system``), @ext.tool,
    @ext.signal, @ext.schedule, @ext.webhook, ext.oauth, @ext.on_event,
    @ext.emits (with and without schema_ref), @ext.expose, full
    lifecycle (@ext.on_install/on_upgrade/on_uninstall/on_enable/
    on_disable/health_check), @ext.tray, @ext.secret (both scopes, with
    and without env_fallback / rotation_hint_days), @ext.panel (sizing +
    overlay + custom kwargs + static tree), and @chat.function with all
    v4 fields (action_type, event, chain_callable, effects,
    id_projection, data_model).
    """
    ext = Extension(
        "ci-canary",
        version="0.0.1",
        capabilities=["canary:read", "canary:write"],
        migrations_dir="migrations",
        config_defaults={"retention_days": 30},
        display_name="CI Canary",
        description=(
            "Canary extension exercising every manifest emitter code path "
            "for I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC roundtrip validation."
        ),
        icon="canary.svg",
        actions_explicit=True,
        # system=True lets the reverse-direction test exercise the
        # hidden_in_sidebar disk merge legitimately (the flag requires
        # system=True per I-EXT-MANIFEST-HIDDEN-SIDEBAR-SYSTEM-ONLY).
        system=True,
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

    ext.oauth("github", collection="github_accounts", scopes=["repo"])

    @ext.on_event("canary.fired")
    async def _on_event(ctx, event):  # noqa: ARG001
        return None

    @ext.emits("ci-canary.saved", schema_ref="schemas/saved.json")
    async def _emitter_with_ref(ctx):  # noqa: ARG001
        return None

    @ext.emits("ci-canary.purged")
    async def _emitter_bare(ctx):  # noqa: ARG001
        return None

    @ext.expose("lookup", action_type="read")
    async def _exposed(ctx, **kwargs):  # noqa: ARG001
        return {"found": True}

    @ext.on_install
    async def _on_install(ctx):  # noqa: ARG001
        return None

    @ext.on_upgrade("0.0.2")
    async def _on_upgrade(ctx):  # noqa: ARG001
        return None

    @ext.on_uninstall
    async def _on_uninstall(ctx):  # noqa: ARG001
        return None

    @ext.on_enable
    async def _on_enable(ctx):  # noqa: ARG001
        return None

    @ext.on_disable
    async def _on_disable(ctx):  # noqa: ARG001
        return None

    @ext.health_check
    async def _health(ctx):  # noqa: ARG001
        return {"status": "ok"}

    @ext.tray("unread", icon="Mail", tooltip="Unread canaries")
    async def _tray(ctx, **kwargs):  # noqa: ARG001
        return None

    # Secrets — all three declaration shapes (EXT-SECRETS-V1):
    # defaults-only user scope, fully-parameterized user scope, and
    # app scope with env_fallback. `to_manifest_dict` ALWAYS emits
    # `scope`; the v5.9.4 canary missed @ext.secret entirely, so the
    # schema rejecting `scope`/`env_fallback` shipped unseen.
    ext.secret("api_key", "User-pasted API key (defaults roundtrip).")(lambda: None)
    ext.secret(
        "refresh_token",
        "OAuth refresh token written by the extension after authorize.",
        required=True,
        write_mode="extension",
        max_bytes=200,
        rotation_hint_days=30,
    )(lambda: None)
    ext.secret(
        "shared_signing_key",
        "App-scope signing key shared across all users, owner-managed.",
        scope="app",
        env_fallback="IMPERAL_APPSECRET_CI_CANARY_SHARED_SIGNING_KEY",
    )(lambda: None)

    # File Mage L3 — file_sinks[] emission site (references plain_tool above).
    ext.file_sink(
        "plain_tool",
        accepts=["application/pdf", "text/*", "image/*"],
        arg="body",
        arg_kind="text",
        description="Canary file destination exercising every file_sink field.",
    )

    @ext.panel("sidebar", slot="left", title="Canary", icon="Bug",
               refresh="30s", center_overlay=False,
               default_width=300, min_width=200, max_width=500,
               custom_flag=True)
    async def _panel(ctx, **kwargs):  # noqa: ARG001
        return None

    @ext.panel("board", slot="center", title="Canary Board",
               center_overlay=True,
               tree={"type": "Text", "props": {"text": "static tree"}})
    async def _panel_static(ctx, **kwargs):  # noqa: ARG001
        return None

    chat = ChatExtension(
        ext=ext,
        tool_name="canary_chat",
        description="Canary chat tool that exercises all @chat.function fields.",
    )

    @chat.function(
        "ping",
        action_type="read",
        data_model=_PingResult,
        description="Echo back a label — read action with no side effect.",
    )
    async def _fn_ping(ctx, params: _PingParams) -> ActionResult:  # noqa: ARG001
        """Echo the label back (canary read path)."""
        return ActionResult.success(data={"label": params.label}, summary=f"pong {params.label}")

    @chat.function(
        "save",
        action_type="write",
        event="canary_saved",
        chain_callable=True,
        effects=["create:canary"],
        id_projection="label",
        data_model=_PingResult,
        description="Persist a label — exercises write+effects+id_projection.",
    )
    async def _fn_save(ctx, params: _PingParams) -> ActionResult:  # noqa: ARG001
        """Persist the label (canary write path)."""
        return ActionResult.success(data={"saved": params.label}, summary=f"saved {params.label}")

    @chat.function(
        "purge",
        action_type="destructive",
        event="canary_purged",
        chain_callable=True,
        effects=["delete:canary"],
        id_projection="label",
        data_model=_PingResult,
        description="Purge a label — destructive path with effects.",
    )
    async def _fn_purge(ctx, params: _PingParams) -> ActionResult:  # noqa: ARG001
        """Purge the label (canary destructive path)."""
        return ActionResult.success(data={"purged": params.label}, summary=f"purged {params.label}")

    return ext


def _generate_maximal_manifest(tmp_path, monkeypatch) -> tuple[Extension, dict]:
    """Build the canary in a tmp CWD with a resolvable icon file so the
    conditional ``icon_size_bytes`` emission fires too."""
    (tmp_path / "canary.svg").write_text(_ICON_SVG)
    monkeypatch.chdir(tmp_path)
    ext = _build_canary_extension()
    return ext, generate_manifest(ext)


def test_roundtrip_emitter_to_schema(tmp_path, monkeypatch):
    """Every key generate_manifest emits must round-trip through the schema.

    `validate_manifest_dict` returns ValidationIssue list; an empty list
    means the schema accepted every field. A non-empty list (especially
    M3 'Extra inputs are not permitted') is the canonical drift signal.
    """
    _, manifest = _generate_maximal_manifest(tmp_path, monkeypatch)
    issues = validate_manifest_dict(manifest)
    assert issues == [], (
        "I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC violated — generate_manifest "
        "emitted a field that the Manifest/Tool schema rejects. "
        f"Issues: {issues}"
    )


def test_canary_passes_live_extension_v_rules():
    """The canary must clear the V-rules `imperal validate` runs on the
    live Extension object — zero ERROR-level issues (warnings tolerated;
    V8 for example is a runtime-manifest placeholder)."""
    from imperal_sdk.validator import validate_extension

    report = validate_extension(_build_canary_extension())
    errors = [i for i in report.issues if i.level == "ERROR"]
    assert errors == [], (
        f"canary trips ERROR-level V-rules: "
        f"{[(i.rule, i.message) for i in errors]}"
    )


def test_emitted_keys_are_schema_known(tmp_path, monkeypatch):
    """Every emitted top-level key must be a declared Manifest field —
    the explicit form of what extra='forbid' enforces implicitly."""
    _, manifest = _generate_maximal_manifest(tmp_path, monkeypatch)
    unknown = set(manifest) - set(Manifest.model_fields)
    assert not unknown, f"generator emits schema-unknown top-level keys: {unknown}"


def test_maximal_canary_covers_every_generator_field(tmp_path, monkeypatch):
    """Structural exhaustiveness closure — kills this bug class:

    1. The maximal canary must emit EXACTLY the generator-owned fields
       (plus name/description/icon, which the generator emits but the
       disk merge may override). A new emission site therefore forces a
       canary extension; a canary regression is caught immediately.
    2. Every schema-known Manifest field must be either generator-owned
       or disk-preserved. A new schema field that is neither emitted by
       the maximal canary nor preserved by `imperal build`'s disk merge
       cannot exist — the hidden_in_sidebar silent-drop class is dead.
    """
    from imperal_sdk.manifest import GENERATOR_OWNED_FIELDS, disk_preserved_fields

    _, manifest = _generate_maximal_manifest(tmp_path, monkeypatch)

    assert GENERATOR_OWNED_FIELDS <= set(Manifest.model_fields), (
        "GENERATOR_OWNED_FIELDS lists keys the Manifest schema doesn't know: "
        f"{GENERATOR_OWNED_FIELDS - set(Manifest.model_fields)}"
    )
    assert set(manifest) == GENERATOR_OWNED_FIELDS | {"name", "description", "icon"}, (
        "maximal canary manifest keys diverge from the registered "
        "generator-owned field set. Missing from manifest: "
        f"{(GENERATOR_OWNED_FIELDS | {'name', 'description', 'icon'}) - set(manifest)}; "
        f"unregistered emissions: "
        f"{set(manifest) - GENERATOR_OWNED_FIELDS - {'name', 'description', 'icon'}}"
    )
    assert set(Manifest.model_fields) == set(manifest) | disk_preserved_fields(), (
        "schema-known fields exist that are neither emitted by the maximal "
        "canary nor preserved from disk by imperal build: "
        f"{set(Manifest.model_fields) - set(manifest) - disk_preserved_fields()}"
    )


def test_maximal_canary_sections_carry_full_feature_surface(tmp_path, monkeypatch):
    """Deep per-section assertions — the canary cannot silently shrink."""
    _, m = _generate_maximal_manifest(tmp_path, monkeypatch)

    # Icon resolved from CWD → size emitted.
    assert m["icon_size_bytes"] == len(_ICON_SVG)

    # Secrets: scope always present; env_fallback on the app-scope one;
    # rotation_hint_days on the fully-parameterized one.
    secrets = {s["name"]: s for s in m["secrets"]}
    assert set(secrets) == {"api_key", "refresh_token", "shared_signing_key"}
    assert all(s["scope"] in ("user", "app") for s in secrets.values())
    assert secrets["api_key"]["scope"] == "user"
    assert "env_fallback" not in secrets["api_key"]
    assert secrets["refresh_token"]["rotation_hint_days"] == 30
    assert secrets["refresh_token"]["write_mode"] == "extension"
    assert secrets["shared_signing_key"]["scope"] == "app"
    assert (secrets["shared_signing_key"]["env_fallback"]
            == "IMPERAL_APPSECRET_CI_CANARY_SHARED_SIGNING_KEY")

    # Panels: full decorator metadata survives — sizing, overlay,
    # arbitrary kwargs, and a static tree.
    panels = {p["panel_id"]: p for p in m["panels"]}
    sidebar = panels["sidebar"]
    for key, expected in [("slot", "left"), ("icon", "Bug"), ("refresh", "30s"),
                          ("center_overlay", False), ("default_width", 300),
                          ("min_width", 200), ("max_width", 500),
                          ("custom_flag", True)]:
        assert sidebar[key] == expected, f"panels.sidebar.{key} lost"
    assert panels["board"]["center_overlay"] is True
    assert panels["board"]["tree"] == {"type": "Text", "props": {"text": "static tree"}}

    # Lifecycle: every hook kind + health_check; signatures recorded.
    assert m["lifecycle"] == {
        "on_install": True, "on_uninstall": True, "on_enable": True,
        "on_disable": True, "on_upgrade": ["0.0.2"],
        "health_check": {"interval_sec": 60},
    }
    assert set(m["lifecycle_hooks"]) == {
        "on_install", "on_upgrade:0.0.2", "on_uninstall", "on_enable", "on_disable",
    }
    assert all("signature" in h for h in m["lifecycle_hooks"].values())

    # Events: both directions, emit with and without schema_ref.
    assert m["events"]["subscribes"] == [{"type": "canary.fired", "handler": "_on_event"}]
    emits = {e["type"]: e for e in m["events"]["emits"]}
    assert emits["ci-canary.saved"]["schema_ref"] == "schemas/saved.json"
    assert "schema_ref" not in emits["ci-canary.purged"]

    # OAuth / tray / webhooks / exposed — full declared key sets.
    assert m["oauth"] == [{"provider": "github", "collection": "github_accounts",
                           "scopes": ["repo"], "has_hook": False}]
    assert m["tray"] == [{"tray_id": "unread", "icon": "Mail", "tooltip": "Unread canaries"}]
    assert m["webhooks"] == [{"path": "/inbound", "method": "POST",
                              "secret_header": "X-Canary-Sig"}]
    assert m["exposed"] == [{"name": "lookup", "action_type": "read"}]

    # Constructor passthroughs.
    assert m["migrations_dir"] == "migrations"
    assert m["config_defaults"] == {"retention_days": 30}
    assert m["system"] is True


def test_build_merge_preserves_schema_known_disk_fields(tmp_path, monkeypatch):
    """Reverse direction — `imperal build` (save_manifest) must preserve
    EVERY schema-known field hand-maintained in the on-disk imperal.json,
    and the merged result must still validate clean through the exact
    disk-file path `imperal validate` uses.

    This is the hidden_in_sidebar class: accepted by the schema, absent
    from the generator, silently dropped by the old 10-field merge tuple.
    """
    from imperal_sdk.manifest import disk_preserved_fields

    disk_values = {
        "name": "CI Canary (curated)",
        "description": "Marketplace-curated description wins over the generator.",
        "icon": "curated.svg",
        "author": "Imperal, Inc.",
        "license": "Apache-2.0",
        "homepage": "https://imperal.io",
        "category": "productivity",
        "tags": ["canary", "ci"],
        "marketplace": {"featured": True},
        "pricing": {"model": "free"},
        "hidden_in_sidebar": True,
    }
    # The sentinel map itself must stay maximal: one entry per preserved field.
    assert set(disk_values) == disk_preserved_fields(), (
        "disk sentinel map out of sync with disk_preserved_fields(): "
        f"missing {disk_preserved_fields() - set(disk_values)}, "
        f"stale {set(disk_values) - disk_preserved_fields()}"
    )

    (tmp_path / "canary.svg").write_text(_ICON_SVG)
    (tmp_path / "imperal.json").write_text(json.dumps(disk_values))
    monkeypatch.chdir(tmp_path)

    ext = _build_canary_extension()
    out_path = save_manifest(ext, str(tmp_path))
    with open(out_path) as f:
        merged = json.load(f)

    lost = {k: v for k, v in disk_values.items() if merged.get(k) != v}
    assert not lost, f"imperal build dropped hand-maintained schema-known fields: {lost}"

    # Generator-owned sections survive the merge untouched.
    for section in ("secrets", "panels", "oauth", "tray", "webhooks",
                    "events", "exposed", "lifecycle", "tools"):
        assert merged.get(section), f"merge lost generator section {section!r}"

    # And the merged file validates clean through the imperal-validate path.
    issues = validate_manifest_dict(merged)
    assert issues == [], f"merged disk manifest fails validation: {issues}"


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
