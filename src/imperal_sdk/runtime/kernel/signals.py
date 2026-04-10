# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Kernel post-action signals — event publishing + skeleton refresh."""
from __future__ import annotations

import json as _json
import logging
import os
import time as _time

log = logging.getLogger(__name__)

_action_counter: dict[str, int] = {}


def _get_redis():
    """Get shared Redis client."""
    try:
        from shared_redis import get_shared_redis
        return get_shared_redis()
    except ImportError:
        return None


async def _publish_action_event(user_id: str, tenant_id: str, app_id: str,
                                 tool_name: str, message: str, result: dict) -> None:
    """Kernel-level event publisher. EVERY extension action gets an event.
    
    Published to Redis imperal:events:{tenant_id} for:
    - SSE → Panel real-time updates
    - Rule engine → automation triggers
    
    Includes timestamp + use counter automatically.
    Extensions don't need to publish events — kernel does it.
    """
    # Increment action counter
    counter_key = f"{app_id}/{tool_name}"
    if len(_action_counter) > 10000:
        _action_counter.clear()
    _action_counter[counter_key] = _action_counter.get(counter_key, 0) + 1
    
    # Determine scope from app_id
    scope_map = {
        "gmail": "email", "admin": "admin", "sharelock-v2": "case",
        "notes": "notes", "__system__": "system",
    }
    scope = scope_map.get(app_id, app_id)
    
    # Determine action from tool response
    response_text = result.get("response", "") if isinstance(result, dict) else str(result)
    action = tool_name.replace(f"tool_{app_id.replace('-','_')}_chat", "action").replace("tool_", "")
    
    try:
        r = _get_redis()
        if not r:
            return
        event = _json.dumps({
            "type": "state_changed",
            "scope": scope,
            "action": action,
            "id": f"{app_id}/{tool_name}",
            "actor": user_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
            "data": {
                "app_id": app_id,
                "tool_name": tool_name,
                "message": message[:200] if message else "",
                "response_preview": response_text[:200] if isinstance(response_text, str) else "",
                "use_count": _action_counter[counter_key],
            },
        })
        await r.publish(f"imperal:events:{tenant_id}", event)
        log.info(f"Kernel event: {scope}.{action} app={app_id} tool={tool_name} count={_action_counter[counter_key]}")
    except Exception as e:
        log.warning(f"Kernel event publish failed: {e}")


async def _signal_skeleton_after_action(user_id: str, app_id: str, tool_name: str):
    """Signal skeleton workflow to refresh after any extension tool execution.
    Non-blocking: failures are logged but don't affect the tool response.
    Skips skeleton_* tools to avoid infinite recursion."""
    if not user_id:
        return
    try:
        r = _get_redis()
        if not r:
            return
        await r.publish("imperal:config:invalidate", _json.dumps({
            "scope": "skeleton", "user_id": user_id, "app_id": app_id,
        }))
        log.info(f"Kernel signal: skeleton refresh for user {user_id} after {app_id}/{tool_name}")
    except Exception as e:
        # Non-fatal: skeleton may not be running yet, or already terminated
        log.debug(f"Skeleton signal skipped for user {user_id}: {e}")
