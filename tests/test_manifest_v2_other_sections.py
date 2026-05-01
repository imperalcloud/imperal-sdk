# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Task 5 — M8/M9/M10: exposed/lifecycle/tray sections in generate_manifest()."""
from imperal_sdk import Extension
from imperal_sdk.manifest import generate_manifest


def test_manifest_emits_exposed():
    ext = Extension("billing", version="2.1.0")

    @ext.expose("get_balance", action_type="read")
    async def handler(ctx):
        return {"balance": 0}

    m = generate_manifest(ext)
    assert m["exposed"] == [{"name": "get_balance", "action_type": "read"}]


def test_manifest_emits_lifecycle():
    ext = Extension("billing", version="2.1.0")

    @ext.on_install
    async def install(ctx):
        return None

    @ext.on_upgrade("2.0.0")
    async def upgrade(ctx):
        return None

    @ext.health_check
    async def health(ctx):
        return {"ok": True}

    m = generate_manifest(ext)
    lc = m["lifecycle"]
    assert lc["on_install"] is True
    assert "2.0.0" in lc["on_upgrade"]
    assert lc["health_check"]["interval_sec"] == 60


def test_manifest_emits_tray():
    ext = Extension("mail", version="1.0.0")

    @ext.tray("unread", icon="Mail", tooltip="Unread")
    async def tray_handler(ctx):
        return None

    m = generate_manifest(ext)
    assert m["tray"] == [{"tray_id": "unread", "icon": "Mail", "tooltip": "Unread"}]


def test_manifest_round_trip_validates_with_all_sections():
    """Federal smoke: extension with exposed+lifecycle+tray validates clean."""
    from imperal_sdk.manifest_schema import validate_manifest_dict

    ext = Extension("billing", version="2.1.0")

    @ext.expose("get_balance", action_type="read")
    async def gb(ctx):
        return {}

    @ext.on_install
    async def install(ctx):
        return None

    @ext.tray("unread", icon="Mail", tooltip="Unread")
    async def tu(ctx):
        return None

    manifest = generate_manifest(ext)
    issues = validate_manifest_dict(manifest)
    assert issues == [], f"M8/M9/M10 round-trip failed: {issues}"


def test_manifest_no_optional_sections_when_empty():
    """Empty extension does NOT emit exposed/lifecycle/tray keys."""
    ext = Extension("empty", version="1.0.0")
    m = generate_manifest(ext)
    assert "exposed" not in m
    assert "lifecycle" not in m
    assert "tray" not in m
