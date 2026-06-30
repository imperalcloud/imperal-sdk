# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
from imperal_sdk import Extension
from imperal_sdk.manifest import generate_manifest


def test_manifest_emits_webhooks_section():
    ext = Extension("billing", version="2.1.0")

    @ext.webhook("/stripe/checkout", method="POST", secret_header="Stripe-Signature")
    async def handler(ctx, headers, body, query_params):
        return {"ok": True}

    manifest = generate_manifest(ext)
    assert "webhooks" in manifest
    assert manifest["webhooks"] == [
        {"path": "/stripe/checkout", "method": "POST", "secret_header": "Stripe-Signature"}
    ]
    assert manifest["manifest_schema_version"] == 3


def test_manifest_no_webhooks_section_when_empty():
    ext = Extension("empty", version="1.0.0")
    manifest = generate_manifest(ext)
    assert "webhooks" not in manifest


def test_webhook_path_is_slash_normalized():
    """A webhook declared with a leading/trailing slash must register the SAME
    dispatch tool name as one without — slash-free — because the gateway derives
    the name from the URL path (always slash-free). A leading slash here was the
    real production bug: `@ext.webhook("/callback")` registered `__webhook__/callback`
    while the gateway dispatched `__webhook__callback` → "function not found" on the
    OAuth callback. Internal separators (oauth/callback) are preserved."""
    for declared in ("/callback", "callback", "/callback/"):
        ext = Extension("mail", version="1.0.0")

        @ext.webhook(declared, method="GET")
        async def handler(ctx, headers, body, query_params):
            return {"ok": True}

        assert "__webhook__callback" in ext._tools, (
            f"{declared!r} → expected tool '__webhook__callback', "
            f"got {list(ext._tools)}"
        )
        assert "__webhook__/callback" not in ext._tools
        # Manifest path keeps exactly one leading slash (schema rule M4
        # requires `^/[a-z0-9_/-]+$`), regardless of how it was declared.
        assert generate_manifest(ext)["webhooks"][0]["path"] == "/callback"


def test_webhook_preserves_internal_path_separators():
    ext = Extension("billing", version="1.0.0")

    @ext.webhook("/stripe/checkout", method="POST")
    async def handler(ctx, headers, body, query_params):
        return {"ok": True}

    assert "__webhook__stripe/checkout" in ext._tools
    assert generate_manifest(ext)["webhooks"][0]["path"] == "/stripe/checkout"


def test_manifest_excludes_dunder_internal_tools_from_tools_list():
    """Synthetic __webhook__/__panel__/__widget__/__tray__ entries belong to their
    own declarative sections and MUST NOT leak into the user-facing tools list.

    Federal: enables validate_manifest_dict() to pass on extensions with webhooks.
    """
    ext = Extension("billing", version="2.1.0")

    @ext.webhook("/stripe/checkout", method="POST", secret_header="Stripe-Signature")
    async def handler(ctx, headers, body, query_params):
        return {"ok": True}

    manifest = generate_manifest(ext)

    # webhooks section is correct
    assert len(manifest["webhooks"]) == 1

    # tools section MUST NOT contain __webhook__ leak
    tool_names = [t["name"] for t in manifest.get("tools", [])]
    assert not any(
        name.startswith("__") for name in tool_names
    ), f"Synthetic tool names leaked into tools list: {tool_names}"


def test_manifest_validates_with_validate_manifest_dict():
    """Federal smoke: full round-trip — generate manifest, validate it, assert no issues."""
    from imperal_sdk.manifest_schema import validate_manifest_dict

    ext = Extension("billing", version="2.1.0")

    @ext.webhook("/stripe/checkout", method="POST", secret_header="Stripe-Signature")
    async def handler(ctx, headers, body, query_params):
        return {"ok": True}

    manifest = generate_manifest(ext)
    issues = validate_manifest_dict(manifest)
    assert issues == [], f"Manifest round-trip validation failed: {issues}"
