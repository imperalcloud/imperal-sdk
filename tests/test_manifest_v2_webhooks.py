# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
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
