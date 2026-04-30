"""Tests for ExtensionsClient.emit federal chokepoint routing (SDK 3.5.0+).

Covers:
1. Happy path: emit routes through imperal_kernel.audit.record_action.
2. Fallback: when imperal_kernel.audit is not importable, falls back to direct
   Redis publish via imperal_kernel.core.redis.get_shared_redis.

Note: Existing mock-context tests use MockExtensionsClient (which has its own
_emitted recording), not the real ExtensionsClient. These tests target the
real client's emit() body directly.
"""
import sys
import types

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_emit_routes_through_record_action():
    """SDK 3.5.0: emit goes through audit.record_action chokepoint."""
    from imperal_sdk.extensions.client import ExtensionsClient

    # Build a minimal ExtensionsClient bypassing __init__
    client = ExtensionsClient.__new__(ExtensionsClient)
    client._current = "notes"
    client._kctx_dict = {
        "user_id": "imp_u_test",
        "tenant_id": "default",
        "email": "test@example.com",
    }

    # Build a fake imperal_kernel.audit module so the import inside emit() works.
    fake_audit = types.ModuleType("imperal_kernel.audit")
    record_action_mock = AsyncMock()
    fake_audit.record_action = record_action_mock

    class _AuditStatus:
        completed = "completed"

    class _AuditSource:
        user = MagicMock()
        user.value = "user"

    fake_audit.AuditStatus = _AuditStatus
    fake_audit.AuditSource = _AuditSource

    # Stub parent package too if missing
    fake_kernel = sys.modules.get("imperal_kernel") or types.ModuleType("imperal_kernel")

    with patch.dict(sys.modules, {
        "imperal_kernel": fake_kernel,
        "imperal_kernel.audit": fake_audit,
    }):
        await client.emit("created", {"note_id": 42})

    record_action_mock.assert_called_once()
    _, kwargs = record_action_mock.call_args
    assert kwargs["action_meta"]["event_type"] == "notes.created"
    assert kwargs["action_meta"]["extension_emit"] is True
    assert kwargs["action_meta"]["action_type"] == "write"
    # plan/kctx/result are synthesized; verify their carried payload.
    assert kwargs["plan"].app_id == "notes"
    assert kwargs["plan"].tool == "<emit>"
    assert kwargs["kctx"].user.imperal_id == "imp_u_test"
    assert kwargs["kctx"].user.tenant_id == "default"
    assert kwargs["result"].event == "created"
    assert kwargs["result"].data == {"note_id": 42}


@pytest.mark.asyncio
async def test_emit_fallback_when_imperal_kernel_unavailable():
    """If imperal_kernel.audit not importable, falls back to direct Redis publish.

    The federal invariant only applies in production kernel context; unit-test
    rigs that do not load imperal_kernel must keep working.
    """
    from imperal_sdk.extensions.client import ExtensionsClient

    client = ExtensionsClient.__new__(ExtensionsClient)
    client._current = "notes"
    client._kctx_dict = {"user_id": "imp_u_test", "tenant_id": "default"}

    redis_mock = MagicMock()
    redis_mock.publish = AsyncMock()

    fake_redis_mod = types.ModuleType("imperal_kernel.core.redis")
    fake_redis_mod.get_shared_redis = MagicMock(return_value=redis_mock)
    fake_core = types.ModuleType("imperal_kernel.core")
    fake_kernel = types.ModuleType("imperal_kernel")

    # Force the audit import to raise ImportError, but allow core.redis to resolve.
    with patch.dict(sys.modules, {
        "imperal_kernel": fake_kernel,
        "imperal_kernel.audit": None,  # sentinel makes import raise ImportError
        "imperal_kernel.core": fake_core,
        "imperal_kernel.core.redis": fake_redis_mod,
    }):
        # Should not raise — emit is fire-and-forget.
        await client.emit("created", {"note_id": 42})

    # Fallback path published to Redis.
    redis_mock.publish.assert_called_once()
    args, _ = redis_mock.publish.call_args
    assert args[0] == "imperal:events:default"
    assert "notes" in args[1]
    assert "created" in args[1]
