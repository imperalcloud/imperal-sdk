# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Kernel extension runner — the core _execute_extension function.

All guards: scopes, target scope, KAV, confirmation, task mgmt, billing hook.
Called by execute_sdk_tool (entry point) AND Hub._dispatch_one (direct dispatch).
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time as _time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from imperal_sdk.runtime.kernel_context import KernelContext as _KernelContext

from imperal_sdk.runtime.task_manager import (
    generate_task_id, create_task, promote_task, complete_task,
    count_active_tasks, update_progress, is_cancelled,
)
from imperal_sdk.runtime.action_writer import generate_trace_id, write_action
from imperal_sdk.runtime.event_publisher import publish_kernel_event
from imperal_sdk.runtime.kernel.scope_guard import _check_tool_scopes
from imperal_sdk.runtime.kernel.system_handlers import (
    _prune_skeleton, _inject_capability_boundary,
)
from imperal_sdk.runtime.kernel.signals import (
    _publish_action_event, _signal_skeleton_after_action,
)
from imperal_sdk.runtime.kernel.task_delivery import _background_task_completion

log = logging.getLogger(__name__)


async def _execute_extension(
    kctx: _KernelContext,
    app_id: str,
    tool_name: str,
    message: str,
    history: list = None,
    skeleton: dict = None,
    context: dict = None,
    chain_mode: bool = False,
    suppress_promotion: bool = False,
    confirmation_bypassed: bool = False,
    chain_id: str = None,
) -> dict:
    """Internal extension execution with all kernel guards.

    Called by execute_sdk_tool (entry point) AND Hub._dispatch_one (direct dispatch).
    Uses factory.create_from_kctx(kctx) — no HTTP calls for identity/config.
    Single billing hook point.

    Guards: scopes, target scope, KAV, confirmation, task mgmt.
    """
    # Lazy import to avoid circular dependency (executor imports us at module level)
    from imperal_sdk.runtime.executor import (
        _loader, _factory, _catalog, _get_redis,
        MAX_TASKS_PER_USER, PROMOTION_THRESHOLD_MS,
    )

    _start_time = _time.time()
    user_id = kctx.user_id
    tenant_id = kctx.tenant_id
    user_scopes = list(kctx.scopes) if kctx.scopes else ["*"]
    ctx_data = context if context is not None else {}

    # ── Scope Enforcement ─────────────────────────────────────────
    required_scopes = ["*"]
    if _catalog and _catalog.loaded:
        for t in _catalog.tools:
            if t["activity_name"] == tool_name:
                required_scopes = t.get("required_scopes", ["*"])
                break

    allowed, missing = _check_tool_scopes(user_scopes, required_scopes)
    if not allowed:
        log.warning(f"KERNEL REJECT: user={user_id} ({kctx.email}) tool={tool_name} missing={missing}")
        try:
            import httpx
            _audit_gw_url = os.getenv("IMPERAL_GATEWAY_URL", "http://104.224.88.155:8085")
            _audit_svc_token = os.getenv("IMPERAL_SERVICE_TOKEN", "")
            async with httpx.AsyncClient(timeout=5.0) as _audit_client:
                await _audit_client.post(
                    f"{_audit_gw_url}/v1/internal/audit",
                    headers={"X-Service-Token": _audit_svc_token},
                    json={
                        "actor_id": user_id, "actor_type": "user",
                        "action": "access.denied", "target_type": "tool",
                        "target_id": tool_name,
                        "metadata": {"tool": tool_name, "app_id": app_id,
                                     "required_scopes": required_scopes,
                                     "user_scopes": user_scopes,
                                     "scope": missing[0] if missing else None},
                        "source": "kernel",
                    }
                )
        except Exception:
            pass
        return {"response": f"Access denied: this action requires {', '.join(missing)} permission. Contact your administrator.", "_handled": False}

    # ── Extension status check (defense-in-depth) ─────────────────
    if _catalog and _catalog.loaded:
        known_apps = {t["app_id"] for t in _catalog.tools}
        if app_id not in known_apps:
            log.warning(f"KERNEL REJECT: app '{app_id}' not in active catalog, tool={tool_name}")
            return {"response": f"Extension '{app_id}' is not available. It may be suspended or removed."}

    # 1. Load extension (mtime cache, auto-reload)
    try:
        ext = _loader.load(app_id)
    except (FileNotFoundError, ImportError) as e:
        log.error(f"Failed to load extension '{app_id}': {e}")
        return {"response": f"Extension '{app_id}' not available"}

    # 2. Check tool exists
    tool_def = ext.tools.get(tool_name)
    if tool_def is None:
        return {"response": f"Unknown tool: {tool_name}"}

    # Guard 4: Skeleton pruning — filter by target extension
    _pruned_skeleton = _prune_skeleton(skeleton or {}, app_id)

    # 3. Create process environment (Context) — no HTTP calls
    ctx = await _factory.create_from_kctx(
        kctx=kctx,
        extension_id=app_id,
        history=history or [],
        skeleton_data=_pruned_skeleton,
    )

    _task_id = None

    try:
        # 4a. Kernel injects capability boundary
        _inject_capability_boundary(ctx, app_id, ext, catalog=_catalog)

        # ── 4a2. Kernel Language Enforcement ──────────────────────────
        ctx._user_language = kctx.language or "en"
        ctx._user_language_name = kctx.language_name or "English"

        # ── 4b. Confirmation + KAV pre-check ─────────────────────────
        _intent_type = kctx.intent_type or ctx_data.get("_intent_type", "read")
        _is_write_intent = _intent_type in ("write", "destructive")
        log.info(f"KAV check: {app_id}/{tool_name} intent={_intent_type} is_write={_is_write_intent} user={user_id}")

        _is_system_task_early = (
            tool_name.startswith("skeleton_")
            or tool_name.startswith("_internal_")
            or ctx_data.get("_is_skeleton_call")
            or ctx_data.get("_is_system_call")
        )
        _is_automation = _intent_type == "automation" or bool(ctx_data.get("automation_rule_id"))

        # Confirmation from KernelContext (pre-resolved, no HTTP)
        _confirmation_settings = None
        if not confirmation_bypassed and not _is_system_task_early and not _is_automation:
            if kctx.confirmation_enabled:
                _conf_actions = kctx.confirmation_actions or {}
                if isinstance(_conf_actions, dict):
                    has_any_confirm = (_conf_actions.get("write", False) or
                                       _conf_actions.get("destructive", False) or
                                       _conf_actions.get("all", False))
                else:
                    has_any_confirm = bool(set(_conf_actions) & {"write", "destructive", "all"})
                log.info(f"KAV confirm check: actions={_conf_actions} has_any_confirm={has_any_confirm}")
                if has_any_confirm:
                    _confirmation_settings = {
                        "confirmation_enabled": True,
                        "confirmation_actions": _conf_actions,
                        "confirmation_ttl": kctx.confirmation_ttl,
                        "kav_max_retries": kctx.kav_max_retries,
                    }
                    ctx._confirmation_required = True
                    ctx._confirmation_settings = _confirmation_settings
                    ctx._confirmation_actions = _conf_actions
                    log.info(f"KAV: confirmation flag set for {app_id}/{tool_name}")

        # Chain mode + intent
        if chain_mode:
            ctx._chain_mode = True
        ctx._intent_type = _intent_type

        # ── 4c. Task creation + limit check ───────────────────────────
        redis = await _get_redis()
        _is_system_task = (
            tool_name.startswith("skeleton_")
            or tool_name.startswith("_internal_")
            or ctx_data.get("_is_skeleton_call")
            or ctx_data.get("_is_system_call")
        )
        # Chain steps skip task creation — Hub manages ONE chain task in tray
        _skip_task = _is_system_task or chain_mode

        if not _skip_task:
            active_count = await count_active_tasks(redis, user_id)
            if active_count >= MAX_TASKS_PER_USER:
                log.warning(f"Task limit reached: user={user_id} active={active_count} max={MAX_TASKS_PER_USER}")
                return {
                    "response": f"You have {active_count} tasks running. Please wait for one to finish before starting another.",
                    "type": "task_limit_reached",
                    "active_tasks": active_count,
                    "max_tasks": MAX_TASKS_PER_USER,
                }

            _task_id = generate_task_id()
            await create_task(redis, _task_id, user_id, tenant_id, app_id, tool_name, message,
                              threshold_ms=PROMOTION_THRESHOLD_MS)
            ctx_data["_task_id"] = _task_id
            await promote_task(redis, _task_id)
            try:
                await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
                    "type": "state_changed", "scope": "task", "action": "promoted",
                    "data": {"task_id": _task_id, "app_id": app_id, "tool_name": tool_name,
                             "message_preview": message[:200] if message else "", "user_id": user_id}
                }))
            except Exception:
                pass

        # ── 4d. Inject progress callback ─────────────────────────────
        _last_progress_time = [0.0]

        async def _progress_callback(percent, msg):
            now = _time.time()
            if now - _last_progress_time[0] >= 2.0:
                _last_progress_time[0] = now
                await update_progress(redis, _task_id, percent, msg)
                try:
                    await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
                        "type": "task.progress", "scope": "task", "action": "progress",
                        "data": {"task_id": _task_id, "percent": percent, "message": msg,
                                 "app_id": app_id, "user_id": user_id}
                    }))
                except Exception:
                    pass
            return await is_cancelled(redis, _task_id)

        ctx_data["_progress_callback"] = _progress_callback

        # ── 4e. Execute extension tool ────────────────────────────────
        log.info(f"Executing {app_id}/{tool_name} for user {user_id} task={_task_id} system={_is_system_task}")

        if _is_system_task:
            result = await ext.call_tool(tool_name, ctx, message=message)
        elif ctx_data.get("_is_async_task"):
            result = await ext.call_tool(tool_name, ctx, message=message)
        elif suppress_promotion or getattr(ctx, '_confirmation_required', False):
            result = await ext.call_tool(tool_name, ctx, message=message)
            if _task_id:
                await complete_task(redis, _task_id, user_id, "completed")
                try:
                    await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
                        "type": "state_changed", "scope": "task", "action": "completed",
                        "data": {"task_id": _task_id, "user_id": user_id}
                    }))
                except Exception:
                    pass
        else:
            # Race extension against threshold timer
            ext_task = asyncio.create_task(ext.call_tool(tool_name, ctx, message=message))
            timer_task = asyncio.create_task(asyncio.sleep(PROMOTION_THRESHOLD_MS / 1000.0))
            done, pending = await asyncio.wait({ext_task, timer_task}, return_when=asyncio.FIRST_COMPLETED)

            if ext_task in done:
                timer_task.cancel()
                result = ext_task.result()
                if _task_id:
                    await complete_task(redis, _task_id, user_id, "completed")
                    try:
                        await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
                            "type": "state_changed", "scope": "task", "action": "completed",
                            "data": {"task_id": _task_id, "user_id": user_id}
                        }))
                    except Exception:
                        pass
            else:
                if _task_id:
                    await promote_task(redis, _task_id)
                    try:
                        await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
                            "type": "task.promoted", "scope": "task", "action": "promoted",
                            "data": {"task_id": _task_id, "message_preview": message[:200],
                                     "app_id": app_id, "tool_name": tool_name, "user_id": user_id}
                        }))
                    except Exception:
                        pass

                _user_info = {
                    "id": kctx.user_id, "email": kctx.email, "role": kctx.role,
                    "scopes": list(kctx.scopes) if kctx.scopes else ["*"],
                    "attributes": kctx.attributes or {}, "tenant_id": kctx.tenant_id,
                }
                asyncio.create_task(_background_task_completion(
                    ext_task, redis, _task_id, user_id, tenant_id,
                    app_id, tool_name, message, _user_info, _user_info, ctx,
                    factory=_factory,
                ))
                ctx._promoted = True
                return {
                    "response": "", "type": "task_promoted",
                    "task_id": _task_id, "app_id": app_id,
                    "tool_name": tool_name, "message_preview": message[:200],
                    "user_message": message[:200],
                }

        # ── 5. Handle intercepted result (2-step confirmation) ────────
        if isinstance(result, dict) and result.get("_intercepted"):
            confirmation_id = f"conf_{uuid.uuid4().hex[:12]}"
            _conf_ttl = kctx.confirmation_ttl if kctx.confirmation_ttl else 300
            intercepted_calls = result.get("intercepted_calls", [])
            from datetime import datetime, timezone
            expires_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            try:
                r = await _get_redis()
                store_data = _json.dumps({
                    "confirmation_id": confirmation_id, "app_id": app_id,
                    "tool_name": tool_name, "user_id": user_id, "tenant_id": tenant_id,
                    "message": message, "intercepted_calls": intercepted_calls,
                    "context": {k: v for k, v in ctx_data.items() if not k.startswith("_")},
                    "created_at": expires_at,
                })
                await r.setex(f"imperal:confirmation:{confirmation_id}", _conf_ttl, store_data)
                user_set_key = f"imperal:confirmations:user:{user_id}"
                await r.sadd(user_set_key, confirmation_id)
                await r.expire(user_set_key, _conf_ttl + 60)
                log.info(f"KAV: stored confirmation {confirmation_id} TTL={_conf_ttl}s calls={len(intercepted_calls)}")
            except Exception as e:
                log.error(f"KAV: failed to store confirmation in Redis: {e}")
            from datetime import timedelta
            _exp = datetime.now(timezone.utc) + timedelta(seconds=_conf_ttl)
            expires_at = _exp.isoformat().replace("+00:00", "Z")
            if _task_id:
                try:
                    await complete_task(redis, _task_id, user_id, "completed")
                except Exception:
                    pass
            return {
                "response": "", "type": "confirmation",
                "confirmation_id": confirmation_id, "app_id": app_id,
                "actions": intercepted_calls, "expires_at": expires_at, "message": message,
            }

        # ── 5b. Normalize result ──────────────────────────────────────
        if isinstance(result, dict):
            normalized = result if "response" in result else {"response": str(result)}
        else:
            normalized = {"response": str(result) if result else "Done."}

        # ── 5c. Kernel response style enforcement ────────────────────
        if isinstance(normalized, dict) and isinstance(normalized.get("response"), str) and normalized["response"]:
            from imperal_sdk.chat.extension import _enforce_response_style
            normalized["response"] = _enforce_response_style(normalized["response"])

        # ── 6. KAV Post-Execution Verification ─────────────────────────
        if _is_write_intent:
            _kav_max = kctx.kav_max_retries if kctx.kav_max_retries else 2
            while True:
                _functions_called = normalized.get("_functions_called", [])
                _any_write_called = any(
                    fc.get("action_type") in ("write", "destructive") for fc in _functions_called
                )
                if _any_write_called:
                    break
                if not _functions_called:
                    _kav_count = ctx_data.get("_kav_retry_count", 0)
                    if _kav_count == 0:
                        log.warning(f"KAV: {app_id}/{tool_name} — NO functions called for write intent, retrying")
                    else:
                        log.info(f"KAV: {app_id}/{tool_name} — still no functions after retry, accepting")
                        break
                elif normalized.get("_handled", True):
                    log.info(f"KAV: {app_id}/{tool_name} called read functions and handled — accepting")
                    break
                else:
                    log.info(f"KAV: {app_id}/{tool_name} — _handled=False, retrying")
                _kav_count = ctx_data.get("_kav_retry_count", 0)
                if _kav_count >= _kav_max:
                    log.error(f"KAV: retries exhausted ({_kav_max}) for {app_id}/{tool_name}")
                    normalized = {
                        "response": f"Could not execute the action after {_kav_max + 1} attempts. Please try again or rephrase your request.",
                        "_kav_failed": True,
                    }
                    break
                ctx_data["_kav_retry_count"] = _kav_count + 1
                _kav_msg = (
                    "KERNEL VERIFICATION FAILED: You were asked to perform a write action but only called read functions. "
                    "You MUST call the appropriate write/send/create/delete function to fulfill the user request. "
                    "Do NOT just describe what you would do — actually call the function. "
                    "If the action is impossible, call a read/list function to verify and explain why."
                )
                ctx_data["_kav_injection"] = _kav_msg
                ctx._kav_injection = _kav_msg
                log.warning(f"KAV: retry {_kav_count + 1}/{_kav_max} for {app_id}/{tool_name}")
                result = await ext.call_tool(tool_name, ctx, message=message)
                if isinstance(result, dict):
                    normalized = result if "response" in result else {"response": str(result)}
                else:
                    normalized = {"response": str(result) if result else "Done."}

        # ── 7. Truth flags ────────────────────────────────────────────
        _fc_list = normalized.get("_functions_called", []) if isinstance(normalized, dict) else []
        _had_function_calls = bool(_fc_list and any(fc.get("name") != "__cancelled__" for fc in _fc_list))
        if not _is_system_task:
            log.debug(f"Action check: {app_id}/{tool_name} _functions_called={len(_fc_list)} _had={_had_function_calls}")
        _had_successful_action = bool(
            isinstance(normalized, dict) and normalized.get("_functions_called")
            and any(
                fc.get("action_type") in ("write", "destructive") and fc.get("success")
                for fc in normalized.get("_functions_called", [])
                if not fc.get("intercepted")
            )
        )
        if isinstance(normalized, dict):
            normalized["_had_function_calls"] = _had_function_calls
            normalized["_had_successful_action"] = _had_successful_action
        for _internal_key in ("_intercepted", "intercepted_calls"):
            if isinstance(normalized, dict):
                normalized.pop(_internal_key, None)

        # ── 9. Pack action metadata ───────────────────────────────────
        _is_navigate = tool_name in ("hub_chat", "system_chat", "discover_tools")
        _was_handled = normalized.get("_handled", False) if isinstance(normalized, dict) else False
        if isinstance(normalized, dict) and not _is_system_task and not _is_navigate and (_had_function_calls or _was_handled):
            normalized["_action_meta"] = {
                "app_id": app_id, "tool_name": tool_name, "intent_type": _intent_type,
                "duration_ms": int((_time.time() - _start_time) * 1000),
                "trace_id": generate_trace_id(),
                "chain_id": chain_id, "task_id": ctx_data.get("_task_id"),
                "message_preview": message[:200] if message else "",
                "user_id": user_id, "tenant_id": tenant_id,
                "kav_failed": bool(normalized.get("_kav_failed")),
                "task_cancelled": bool(normalized.get("_task_cancelled")),
                "user_scopes": user_scopes, "checked_scopes": required_scopes,
            }
            try:
                from imperal_sdk.runtime.llm_provider import get_llm_provider
                _llm_info = getattr(get_llm_provider(), '_last_call_info', None)
                if _llm_info:
                    normalized["_action_meta"]["llm_provider"] = _llm_info.get("provider", "")
                    normalized["_action_meta"]["llm_model"] = _llm_info.get("model", "")
            except Exception:
                pass
            try:
                from imperal_sdk.runtime.llm_provider import get_llm_provider
                _call_log = get_llm_provider().get_call_log()
                if _call_log:
                    normalized["_action_meta"]["llm_steps"] = _call_log
                    normalized["_action_meta"]["llm_total_calls"] = len(_call_log)
                    normalized["_action_meta"]["llm_total_tokens"] = sum(
                        s.get("input_tokens", 0) + s.get("output_tokens", 0) for s in _call_log)
            except Exception:
                pass
            _fc_for_audit = normalized.get("_functions_called", [])
            _tsg_audit = None
            for _fc in _fc_for_audit:
                _fc_tsg = _fc.get("_target_scope")
                if _fc_tsg and _fc_tsg.get("cross_user"):
                    _tsg_audit = _fc_tsg
                    break
            if _tsg_audit:
                normalized["_action_meta"]["target_user_id"] = _tsg_audit.get("target_user_id")
                normalized["_action_meta"]["target_param"] = _tsg_audit.get("target_param")
                normalized["_action_meta"]["cross_user"] = True
                normalized["_action_meta"]["target_scope_required"] = _tsg_audit.get("required_scope")
                normalized["_action_meta"]["target_scope_verdict"] = _tsg_audit.get("verdict")
            else:
                normalized["_action_meta"]["cross_user"] = False

        # ── 10. SSE publish ───────────────────────────────────────────
        if not tool_name.startswith("skeleton_"):
            await _publish_action_event(
                user_id=user_id, tenant_id=tenant_id,
                app_id=app_id, tool_name=tool_name,
                message=message, result=normalized,
            )

        # ── 10b. Event Publishing (ActionResult events for automations) ──
        from imperal_sdk.chat.action_result import ActionResult
        _fc_list_ev = normalized.get("_functions_called", []) if isinstance(normalized, dict) else []
        for _fc_ev in _fc_list_ev:
            _fc_result = _fc_ev.get("result")
            _fc_event = _fc_ev.get("event")
            if (_fc_result is not None
                    and isinstance(_fc_result, ActionResult)
                    and _fc_result.status == "success"
                    and _fc_event
                    and _fc_ev.get("action_type") in ("write", "destructive")):
                try:
                    _ev_redis = await _get_redis()
                    if _ev_redis:
                        from datetime import datetime, timezone as _tz
                        await publish_kernel_event(
                            redis_client=_ev_redis, tenant_id=tenant_id,
                            event_type=f"{app_id}.{_fc_event}", data=_fc_result.data,
                            user_id=user_id, app_id=app_id,
                            function_name=_fc_ev.get("name", ""),
                            action_type=_fc_ev.get("action_type", ""),
                            timestamp=datetime.now(_tz.utc).isoformat(),
                        )
                except Exception as _ev_err:
                    log.error(f"Kernel event publish error: {_ev_err}")

        return normalized

    except Exception as e:
        log.error(f"Extension error {app_id}/{tool_name}: {e}", exc_info=True)
        if _task_id:
            try:
                redis = await _get_redis()
                await complete_task(redis, _task_id, user_id, "failed")
            except Exception:
                pass
        _cascade_effects = []
        try:
            from imperal_sdk.runtime.cascade_map import get_cascade_effects
            _cascade_effects = await get_cascade_effects(app_id)
            if _cascade_effects:
                log.warning(f"CASCADE ALERT: {app_id} failed, affected: {[e['app_id'] for e in _cascade_effects]}")
        except Exception:
            pass
        return {
            "response": "An error occurred while processing your request.",
            "_cascade_effects": _cascade_effects if _cascade_effects else None,
        }

    finally:
        if not getattr(ctx, "_promoted", False):
            await _factory.destroy(ctx)
