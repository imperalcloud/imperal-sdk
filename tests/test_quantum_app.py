# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Tests for ICNLI Quantum SDK v6.0 App Engine."""
from __future__ import annotations

import asyncio
from typing import List, Optional
import pytest

from imperal_sdk import App, Context, Extension
from imperal_sdk.auto_ui import project_to_declarative_ir


def test_quantum_app_initialization():
    app = App("pulse-check", name="Pulse Check", category="monitoring")
    assert issubclass(App, Extension)
    assert app.app_id == "pulse-check"
    assert app.display_name == "Pulse Check"
    assert app.category == "monitoring"
    assert len(app.description) >= 40
    assert "<svg" in app.icon


def test_quantum_tool_schema_extraction():
    app = App("schema-test")

    @app.tool(pricing=10, destructive=True)
    def reboot_server(server_id: str, force: bool = False, timeout_sec: int = 30) -> dict:
        """Gracefully reboot a server by server_id."""
        return {"status": "rebooting", "server_id": server_id, "force": force}

    manifest = app.to_manifest()
    assert manifest["app_id"] == "schema-test"
    assert len(manifest["tools"]) == 1

    tool = manifest["tools"][0]
    assert tool["name"] == "reboot_server"
    assert tool["description"] == "Gracefully reboot a server by server_id."
    assert tool["pricing"] == 10
    assert tool["destructive"] is True
    assert tool["action_type"] == "destructive"
    assert tool["scopes"] == ["schema-test:reboot_server"]

    props = tool["parameters"]["properties"]
    assert props["server_id"]["type"] == "string"
    assert props["force"]["type"] == "boolean"
    assert props["force"]["default"] is False
    assert props["timeout_sec"]["type"] == "integer"
    assert props["timeout_sec"]["default"] == 30

    assert tool["parameters"]["required"] == ["server_id"]


def test_ambient_context_hidden_from_schema():
    app = App("ctx-test")

    @app.tool()
    def inspect_cloud(zone: str, ctx: Context = None) -> dict:
        """Inspect cloud zone."""
        return {"zone": zone, "user_role": ctx.user.role if ctx and ctx.user else "none"}

    tool = app.to_manifest()["tools"][0]
    assert "ctx" not in tool["parameters"]["properties"]
    assert "context" not in tool["parameters"]["properties"]
    assert tool["parameters"]["required"] == ["zone"]

    # Invocation with ambient context auto-injection
    res = inspect_cloud(zone="eu-central-1")
    assert res["zone"] == "eu-central-1"
    assert res["user_role"] == "admin"


def test_auto_ir_projection():
    # Metric Card auto-projection
    metric_data = {"status": "healthy", "metric": "99.98%", "nodes": 12}
    ir_card = project_to_declarative_ir(metric_data, title="Cluster Health")
    assert ir_card is not None
    assert ir_card["type"] == "metric_card"
    assert ir_card["title"] == "Cluster Health"
    assert ir_card["badge"] == "healthy"
    assert ir_card["metric"] == "99.98%"
    assert ir_card["details"] == {"nodes": 12}

    # Table auto-projection
    table_data = [
        {"id": 1, "name": "alpha", "ip": "10.0.0.1"},
        {"id": 2, "name": "beta", "ip": "10.0.0.2"},
    ]
    ir_table = project_to_declarative_ir(table_data, title="Nodes")
    assert ir_table is not None
    assert ir_table["type"] == "table"
    assert ir_table["columns"] == ["id", "name", "ip"]
    assert len(ir_table["rows"]) == 2


@pytest.mark.asyncio
async def test_async_quantum_tool():
    app = App("async-test")

    @app.tool()
    async def fetch_telemetry(metric_name: str) -> dict:
        """Async telemetry fetcher."""
        await asyncio.sleep(0.01)
        return {"status": "ok", "value": 42, "metric": metric_name}

    res = await fetch_telemetry(metric_name="cpu_usage")
    assert res["status"] == "ok"
    assert res["value"] == 42
    assert "_ui" in res
    assert res["_ui"]["type"] == "metric_card"
