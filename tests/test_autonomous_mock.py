# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Tests for AutonomousMockContext and offline testing kit."""
import pytest
from imperal_sdk.testing.autonomous_mock import AutonomousMockContext


@pytest.mark.asyncio
async def test_autonomous_mock_offline_flow():
    ctx = AutonomousMockContext(balance=50_000, roles=["admin"], scopes=["admin:write"])

    # Billing offline
    assert await ctx.billing.get_balance() == 50_000
    charged = await ctx.billing.charge(5_000, reason="test action")
    assert charged is True
    assert await ctx.billing.get_balance() == 45_000

    # RBAC offline
    assert await ctx.rbac.has_scope("admin:write") is True
    assert await ctx.rbac.has_scope("random:scope") is True  # admin role has wildcard access

    # Store offline
    await ctx.store.set("session_key", {"foo": "bar"})
    val = await ctx.store.get("session_key")
    assert val == {"foo": "bar"}

    # AI completion offline
    completion = await ctx.ai.complete("Hello assistant")
    assert "Mocked AI reasoning response" in completion
    assert len(ctx.ai.calls) == 1
