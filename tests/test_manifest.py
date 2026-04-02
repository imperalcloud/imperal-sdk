# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from imperal_sdk import Extension
from imperal_sdk.manifest import generate_manifest


def test_manifest_basic():
    ext = Extension("test-app", version="2.0.0")

    @ext.tool("hello", scopes=["public"], description="Say hello")
    async def hello(ctx, name: str = "World"):
        pass

    manifest = generate_manifest(ext)
    assert manifest["app_id"] == "test-app"
    assert manifest["version"] == "2.0.0"
    assert len(manifest["tools"]) == 1
    assert manifest["tools"][0]["name"] == "hello"
    assert manifest["tools"][0]["scopes"] == ["public"]
    assert manifest["required_scopes"] == ["public"]


def test_manifest_parameters():
    ext = Extension("test-app")

    @ext.tool("search")
    async def search(ctx, query: str, limit: int = 10):
        pass

    manifest = generate_manifest(ext)
    params = manifest["tools"][0]["parameters"]
    assert "query" in params
    assert params["query"]["type"] == "string"
    assert params["query"]["required"] is True
    assert "limit" in params
    assert params["limit"]["type"] == "integer"
    assert params["limit"]["required"] is False


def test_manifest_signals_schedules():
    ext = Extension("test-app")

    @ext.signal("on_login")
    async def on_login(ctx, user):
        pass

    @ext.schedule("daily", cron="0 9 * * *")
    async def daily(ctx):
        pass

    manifest = generate_manifest(ext)
    assert len(manifest["signals"]) == 1
    assert manifest["signals"][0]["name"] == "on_login"
    assert len(manifest["schedules"]) == 1
    assert manifest["schedules"][0]["cron"] == "0 9 * * *"


def test_manifest_capabilities():
    ext = Extension("test-app", capabilities=["dedicated_db"], migrations_dir="./migrations")
    manifest = generate_manifest(ext)
    assert "dedicated_db" in manifest["capabilities"]
    assert manifest["migrations_dir"] == "./migrations"


def test_manifest_no_ctx_in_params():
    ext = Extension("test-app")

    @ext.tool("my_tool")
    async def my_tool(ctx, arg1: str):
        pass

    manifest = generate_manifest(ext)
    params = manifest["tools"][0]["parameters"]
    assert "ctx" not in params
    assert "arg1" in params
