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
    assert manifest["manifest_schema_version"] == 2


def test_manifest_no_webhooks_section_when_empty():
    ext = Extension("empty", version="1.0.0")
    manifest = generate_manifest(ext)
    assert "webhooks" not in manifest
