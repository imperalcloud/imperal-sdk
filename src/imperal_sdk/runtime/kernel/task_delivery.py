# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Kernel background task completion — delivers results to chat."""
from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import time as _time

from imperal_sdk.runtime.task_manager import complete_task
from imperal_sdk.runtime.action_writer import generate_trace_id, write_action
from imperal_sdk.runtime.kernel.signals import _publish_action_event

log = logging.getLogger(__name__)

_GW_URL = os.getenv("IMPERAL_GATEWAY_URL", "http://104.224.88.155:8085")
_SVC_TOKEN = os.getenv("IMPERAL_SERVICE_TOKEN", "")


async def _deliver_to_chat(redis, user_id: str, content: str, msg_type: str = "response",
                           task_id: str = "", tenant_id: str = "default") -> None:
    """Deliver a background task result to chat history via Redis.

    Strategy: find the existing task_promoted message and UPDATE it with the result.
    This way Panel polling (which watches for status=done on the known message ID)
    picks up the content automatically. Falls back to append if no promoted msg found.
    Also publishes SSE so Panel re-fetches chat if polling already stopped.
    """
    from datetime import datetime
    history_key = f"imperal:hub:chat:{user_id}"
    try:
        existing = await redis.get(history_key)
        messages = _json.loads(existing) if existing else []

        # Strategy 1: Find and update existing task_promoted message for this task
        updated = False
        if task_id:
            for msg in messages:
                if msg.get("type") == "task_promoted" and msg.get("task_id") == task_id:
                    msg["content"] = content
                    msg["status"] = "done"
                    msg["status_text"] = None
                    msg["type"] = msg_type
                    updated = True
                    break

        # Strategy 2: Append as new message if no promoted message found
        if not updated:
            messages.append({
                "id": int(_time.time() * 1000),
                "role": "assistant",
                "content": content,
                "status": "done",
                "status_text": None,
                "type": msg_type,
                "ts": datetime.utcnow().isoformat() + "Z",
            })

        await redis.set(history_key, _json.dumps(messages, ensure_ascii=False), ex=86400)

        # Publish SSE so Panel knows to re-fetch chat history
        try:
            await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
                "type": "state_changed",
                "scope": "hub",
                "action": "background_task_delivered",
                "id": task_id or "unknown",
                "actor": user_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                "data": {"task_id": task_id, "msg_type": msg_type},
            }))
        except Exception:
            pass

    except Exception as e:
        log.warning(f"Failed to deliver background result to chat for {user_id}: {e}")


async def _background_task_completion(
    ext_task: asyncio.Task,
    redis,
    task_id: str,
    user_id: str,
    tenant_id: str,
    app_id: str,
    tool_name: str,
    message: str,
    user_info: dict,
    enriched_user: dict,
    ctx=None,
    factory=None,
) -> None:
    """Handle completion of a promoted background task.

    Waits for ext_task to finish, then marks the task as completed/failed,
    publishes SSE events, and delivers the result to chat history.
    Owns the ctx lifecycle — destroys it when done.
    """
    try:
        result = await ext_task
        await complete_task(redis, task_id, user_id, "completed")

        # Normalize result
        if isinstance(result, dict):
            response_text = result.get("response", str(result))
        else:
            response_text = str(result) if result else "Done."

        # ── Truth Gate (same logic as session_workflow) ───────────
        # Prevents fabricated or integrity-failed responses in background tasks.
        _action_claims = (
            "sent", "deleted", "archived", "created", "forwarded", "replied",
            "moved", "removed", "updated", "saved", "composed",
            "отправлено", "удалено", "заархивировано", "создано", "переслано",
            "перемещено", "сохранено", "обновлено",
        )
        _success_claims = (
            "successfully", "done", "completed", "success",
            "успешно", "готово", "выполнено",
        )
        _bg_verdict = "pass"
        if response_text and isinstance(result, dict):
            _tl = response_text.lower()
            if any(c in _tl for c in _action_claims):
                _bg_had_action = result.get("_had_successful_action", False)
                _bg_had_fn = result.get("_functions_called", False)
                if _bg_had_action:
                    _bg_verdict = "pass"
                elif _bg_had_fn:
                    _fc = result.get("_functions_called", [])
                    _failed = [f for f in _fc if f.get("action_type") in ("write", "destructive") and not f.get("success") and not f.get("intercepted")]
                    if _failed and any(w in _tl for w in _success_claims):
                        _ok = [f.get("name", "?") for f in _fc if f.get("success")]
                        _fl = [f"- {f.get('name','?')}: {f.get('error','')}" for f in _failed]
                        parts = []
                        if _ok: parts.append(f"Completed: {', '.join(_ok)}.")
                        if _fl: parts.append("Could not complete:\n" + "\n".join(_fl))
                        response_text = "Some actions failed.\n\n" + "\n\n".join(parts)
                        _bg_verdict = "integrity_failure"
                else:
                    response_text = "I wasn't able to complete that action. Please try again."
                    _bg_verdict = "fabrication"
        if _bg_verdict != "pass":
            log.warning(f"Background Truth Gate: {_bg_verdict} for {app_id}/{tool_name} task={task_id}")

        # Determine message type from result
        _bg_fc_list = result.get("_functions_called", []) if isinstance(result, dict) else []
        _bg_msg_type = "function_call" if (_bg_fc_list and any(fc.get("name") != "__cancelled__" for fc in _bg_fc_list)) else "response"

        # Store result so Panel Task Monitor can fetch it
        await redis.setex(
            f"imperal:task:{task_id}:result",
            86400,
            _json.dumps({"response": response_text[:2000]}),
        )

        # Deliver result to chat history so user sees it in the conversation
        if response_text and response_text.strip():
            await _deliver_to_chat(redis, user_id, response_text, _bg_msg_type, task_id=task_id, tenant_id=tenant_id)

        # Publish completion SSE
        await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
            "type": "task.completed", "scope": "task", "action": "completed",
            "data": {"task_id": task_id, "app_id": app_id, "tool_name": tool_name,
                     "user_id": user_id, "response_preview": response_text[:200]}
        }))

        # ── Action Writer for promoted tasks ─────────────────────
        # Step 9 is never reached for promoted tasks (main path returns early).
        # Write action here using _had_function_calls from the result.
        _fc_list = result.get("_functions_called", []) if isinstance(result, dict) else []
        _bg_had_function_calls = bool(_fc_list and any(fc.get("name") != "__cancelled__" for fc in _fc_list))
        if _bg_had_function_calls and not tool_name.startswith("skeleton_"):
            _bg_intent = "read"
            if _fc_list:
                for fc in _fc_list:
                    if fc.get("action_type") in ("write", "destructive") and fc.get("success"):
                        _bg_intent = fc["action_type"]
                        break
            try:
                await write_action(
                    gateway_url=_GW_URL,
                    service_token=_SVC_TOKEN,
                    trace_id=generate_trace_id(),
                    user_id=user_id,
                    tenant_id=tenant_id,
                    app_id=app_id,
                    tool_name=tool_name,
                    action_type=_bg_intent,
                    intent_type=_bg_intent,
                    status="completed",
                    message_preview=message[:200] if message else "",
                    result_preview=response_text[:200],
                    duration_ms=0,
                    parent_task_id=task_id,
                )
                log.info(f"Background action written: {app_id}/{tool_name} intent={_bg_intent} task={task_id}")
            except Exception as _aw_err:
                log.warning(f"Background action write failed (non-blocking): {_aw_err}")

        # Publish action event (SSE)
        if not tool_name.startswith("skeleton_"):
            await _publish_action_event(
                user_id=user_info.get("id", ""),
                tenant_id=enriched_user.get("tenant_id", "default"),
                app_id=app_id,
                tool_name=tool_name,
                message=message,
                result={"response": response_text},
            )

        log.info(f"Background task completed: task={task_id} app={app_id}/{tool_name}")

    except asyncio.CancelledError:
        await complete_task(redis, task_id, user_id, "cancelled")
        log.warning(f"Background task cancelled: task={task_id}")

    except Exception as e:
        log.error(f"Background task failed: task={task_id} error={e}", exc_info=True)
        await complete_task(redis, task_id, user_id, "failed")

        # Deliver error to chat so user knows what happened
        await _deliver_to_chat(redis, user_id, f"Task failed: {str(e)[:200]}", "task_failed", task_id=task_id, tenant_id=tenant_id)

        try:
            await redis.publish(f"imperal:events:{tenant_id}", _json.dumps({
                "type": "task.failed", "scope": "task", "action": "failed",
                "data": {"task_id": task_id, "app_id": app_id, "tool_name": tool_name,
                         "user_id": user_id, "error": str(e)[:200]}
            }))
        except Exception:
            pass

    finally:
        # Destroy context after background task completes (we own it)
        if ctx is not None and factory is not None:
            try:
                await factory.destroy(ctx)
            except Exception:
                pass
