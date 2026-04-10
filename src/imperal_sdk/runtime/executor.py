from __future__ import annotations
"""ICNLI OS Kernel — execute_sdk_tool.

The ONLY entry point for extension execution.
System tools (discover_tools, hub_chat) are intercepted before extension dispatch.
Extension execution delegates to kernel/extension_runner.py which enforces all guards.
"""
import json as _json
import logging
import os
from typing import Any

from imperal_sdk.runtime.loader import ExtensionLoader
from imperal_sdk.runtime.context_factory import ContextFactory
from imperal_sdk.runtime.kernel.system_handlers import _handle_discover_tools, _handle_hub_chat
from imperal_sdk.runtime.kernel.signals import _publish_action_event
from imperal_sdk.runtime.kernel.extension_runner import _execute_extension
# Re-export: extension.py imports _check_target_scope from here at runtime
from imperal_sdk.runtime.kernel.scope_guard import _check_target_scope  # noqa: F401

log = logging.getLogger(__name__)

_loader: ExtensionLoader | None = None
_factory: ContextFactory | None = None
_catalog = None
_redis_client = None

MAX_TASKS_PER_USER = int(os.getenv("IMPERAL_MAX_TASKS_PER_USER", "3"))
PROMOTION_THRESHOLD_MS = int(os.getenv("IMPERAL_PROMOTION_THRESHOLD_MS", "5000"))


async def _get_redis() -> Any:
    """Get shared Redis client (lazy init)."""
    global _redis_client
    if _redis_client is None:
        try:
            from shared_redis import get_shared_redis
            _redis_client = get_shared_redis()
        except ImportError:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(os.getenv("REDIS_URL", ""))
    return _redis_client


def init_runtime(gateway_url: str, service_token: str, extensions_dir: str = "/opt/extensions", catalog: Any = None) -> None:
    """Initialize the ICNLI OS runtime. Called once at worker startup."""
    global _loader, _factory, _catalog
    _loader = ExtensionLoader(extensions_dir=extensions_dir)
    _factory = ContextFactory(gateway_url=gateway_url, service_token=service_token)
    _catalog = catalog
    log.info(f"ICNLI OS Runtime initialized: gateway={gateway_url}, extensions={extensions_dir}")


async def publish_event_catalog() -> None:
    """Scan loaded extensions and publish available events to Redis.
    Called at worker startup. Key: imperal:automation:event_catalog (TTL 1h).
    """
    if _loader is None:
        return
    try:
        r = await _get_redis()
        if not r:
            return

        events = []
        extensions_dir = _loader._extensions_dir
        for app_id in os.listdir(extensions_dir):
            main_path = os.path.join(extensions_dir, app_id, "main.py")
            if not os.path.isfile(main_path):
                continue
            try:
                ext = _loader.load(app_id)
                if ext and hasattr(ext, "_chat_extensions"):
                    for tool_name, chat_ext in ext._chat_extensions.items():
                        if hasattr(chat_ext, "_functions"):
                            for func_name, func_def in chat_ext._functions.items():
                                if func_def.event:
                                    events.append({
                                        "event_type": f"{app_id}.{func_def.event}",
                                        "app_id": app_id,
                                        "function": func_name,
                                        "action_type": func_def.action_type,
                                        "description": func_def.description[:150] if func_def.description else "",
                                    })
            except Exception as e:
                log.warning(f"Event catalog: failed to scan {app_id}: {e}")

        events.extend([
            {"event_type": "email.received", "app_id": "gmail", "function": "_kernel_poller", "action_type": "event", "description": "New email received (from kernel event poller)"},
            {"event_type": "system.scheduled", "app_id": "_system", "function": "_kernel_scheduler", "action_type": "event", "description": "Cron schedule triggered"},
        ])

        await r.setex("imperal:automation:event_catalog", 3600, _json.dumps(events))
        log.info(f"Event catalog published to Redis: {len(events)} events from {len(set(e['app_id'] for e in events))} extensions")
    except Exception as e:
        log.error(f"Failed to publish event catalog: {e}")


async def execute_sdk_tool(tool_input: dict) -> dict:
    """ICNLI OS syscall — the ONLY entry point for extension execution.

    Extracts KernelContext, intercepts system tools, delegates extensions
    to _execute_extension.
    """
    if _loader is None or _factory is None:
        return {"response": "ICNLI OS Runtime not initialized"}

    try:
        from imperal_sdk.runtime.llm_provider import get_llm_provider
        get_llm_provider().reset_call_log()
    except Exception:
        pass

    tool_name = tool_input.get("tool_name", "")

    from imperal_sdk.runtime.kernel_context import KernelContext
    kctx_dict = tool_input.get("_kernel_ctx")
    user_info = tool_input.get("user", {})
    if kctx_dict:
        kctx = KernelContext.from_dict(kctx_dict)
    else:
        kctx = KernelContext(
            user_id=str(user_info.get("id", "")),
            email=user_info.get("email", ""),
            role=user_info.get("role", "user"),
            scopes=user_info.get("scopes") or ["*"],
            attributes=user_info.get("attributes") or {},
            tenant_id=user_info.get("tenant_id", "default"),
        )

    # ── System tool interception ──────────────────────────────────
    if tool_name == "discover_tools":
        return await _handle_discover_tools(tool_input, catalog=_catalog)
    if tool_name in ("hub_chat", "system_chat"):
        log.info("Hub chat: executing inline (no promotion)")
        _hub_result = await _handle_hub_chat(tool_input, kctx, catalog=_catalog)
        if isinstance(_hub_result, dict) and _hub_result.get("_had_function_calls"):
            await _publish_action_event(
                user_id=kctx.user_id,
                tenant_id=kctx.tenant_id,
                app_id=_hub_result.get("_action_meta", {}).get("app_id", "__system__"),
                tool_name=_hub_result.get("_action_meta", {}).get("tool_name", "hub_chat"),
                message=tool_input.get("message", ""),
                result=_hub_result,
            )
        return _hub_result

    # ── Extension dispatch ────────────────────────────────────────
    ctx_data = tool_input.get("context", {})
    return await _execute_extension(
        kctx=kctx,
        app_id=tool_input.get("app_id", ""),
        tool_name=tool_name,
        message=tool_input.get("message", ""),
        history=tool_input.get("history", []),
        skeleton=tool_input.get("skeleton", {}),
        context=ctx_data,
        chain_mode=bool(ctx_data.get("_chain_mode")),
        suppress_promotion=bool(ctx_data.get("_suppress_promotion")),
        confirmation_bypassed=bool(ctx_data.get("_confirmation_bypassed")),
        chain_id=ctx_data.get("chain_id"),
    )
