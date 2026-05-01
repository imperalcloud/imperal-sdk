# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Task 4 — M7 events section in generate_manifest()."""
from imperal_sdk import Extension
from imperal_sdk.manifest import generate_manifest


def test_manifest_emits_events_subscribes_and_emits():
    ext = Extension("billing", version="2.1.0")

    @ext.on_event("payment.received")
    async def h1(ctx, **kwargs):
        return None

    @ext.emits("billing.topup_completed", schema_ref="#/schemas/topup")
    async def h2(ctx):
        return None

    m = generate_manifest(ext)
    assert "events" in m
    assert m["events"]["subscribes"] == [
        {"type": "payment.received", "handler": "h1"}
    ]
    assert m["events"]["emits"] == [
        {"type": "billing.topup_completed", "schema_ref": "#/schemas/topup"}
    ]


def test_manifest_no_events_section_when_empty():
    ext = Extension("empty", version="1.0.0")
    m = generate_manifest(ext)
    assert "events" not in m


def test_manifest_events_round_trip_validates():
    """Federal smoke: full round-trip — generate manifest with events, validate, no errors."""
    from imperal_sdk.manifest_schema import validate_manifest_dict

    ext = Extension("billing", version="2.1.0")

    @ext.on_event("payment.received")
    async def h1(ctx, **kwargs):
        return None

    @ext.emits("billing.topup_completed", schema_ref="#/schemas/topup")
    async def h2(ctx):
        return None

    manifest = generate_manifest(ext)
    issues = validate_manifest_dict(manifest)
    assert issues == [], f"Manifest events round-trip failed: {issues}"
