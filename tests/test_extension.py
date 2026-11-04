# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import pytest
from imperal_sdk import Extension


def test_create_extension():
    ext = Extension("test-app", version="1.0.0")
    assert ext.app_id == "test-app"
    assert ext.version == "1.0.0"


def test_register_tool():
    ext = Extension("test-app")

    @ext.tool("my_tool", scopes=["read"])
    async def my_tool(ctx, text: str):
        return {"text": text}

    assert "my_tool" in ext.tools
    assert ext.tools["my_tool"].name == "my_tool"
    assert ext.tools["my_tool"].scopes == ["read"]


def test_register_signal():
    ext = Extension("test-app")

    @ext.signal("on_login")
    async def on_login(ctx, user):
        pass

    assert "on_login" in ext.signals


def test_register_schedule():
    ext = Extension("test-app")

    @ext.schedule("daily", cron="0 9 * * *")
    async def daily(ctx):
        pass

    assert "daily" in ext.schedules
    assert ext.schedules["daily"].cron == "0 9 * * *"


@pytest.mark.asyncio
async def test_call_tool():
    ext = Extension("test-app")

    @ext.tool("echo")
    async def echo(ctx, message: str):
        return {"message": message}

    result = await ext.call_tool("echo", ctx=None, message="hello")
    assert result == {"message": "hello"}


@pytest.mark.asyncio
async def test_call_unknown_tool_raises():
    ext = Extension("test-app")
    with pytest.raises(ValueError, match="Unknown tool"):
        await ext.call_tool("nonexistent", ctx=None)


def test_capabilities():
    ext = Extension("test-app", capabilities=["dedicated_db"])
    assert "dedicated_db" in ext.capabilities


def test_tool_preserves_function():
    ext = Extension("test-app")

    @ext.tool("my_tool")
    async def my_tool(ctx):
        """My docstring."""
        pass

    assert my_tool.__doc__ == "My docstring."
    assert ext.tools["my_tool"].description == "My docstring."
