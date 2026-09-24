# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Test Sync/Async Parity in extension dispatcher."""
import time
import pytest
from imperal_sdk import Extension, ChatExtension, ActionResult
from imperal_sdk.testing.mock_context import MockContext


@pytest.mark.asyncio
async def test_sync_tool_executed_transparently():
    ext = Extension(
        "sync_test_app",
        version="1.0.0",
        display_name="Sync Test App",
        description="A test extension verifying sync/async parity in execution.",
    )
    chat = ChatExtension(ext, tool_name="sync_tool", description="Runs a synchronous task")

    # Registered tool is a purely synchronous function that sleeps
    @ext.tool("sync_ping", description="Ping tool description that is descriptive")
    def sync_ping(ctx, message: str = "pong"):
        time.sleep(0.01)  # synchronous blocking sleep
        return ActionResult.success(data={"echo": message}, summary="Echoed successfully")

    ctx = MockContext()
    # call_tool is async, but seamlessly dispatches sync handler to threadpool
    result = await ext.call_tool("sync_ping", ctx, message="hello_world")
    assert result.status == "success"
    assert result.data["echo"] == "hello_world"
    assert result.summary == "Echoed successfully"
