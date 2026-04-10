# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Hub session state — Redis-backed session management for Hub routing."""
from __future__ import annotations

import json
import logging
import re
import time as _time

from shared_redis import get_shared_redis

log = logging.getLogger(__name__)

_HUB_SESSION_TTL = 3600
_FOLLOWUP_MAX_WORDS = 6
_FOLLOWUP_STALE_SECONDS = 600


async def _get_hub_redis():
    """Thin wrapper — returns shared Redis pool. Kept for call-site compat."""
    return get_shared_redis()


async def _load_session_state(user_id: str) -> dict:
    """Load Hub session state from Redis. Returns {} if none or stale."""
    try:
        r = await _get_hub_redis()
        raw = await r.get(f"imperal:hub_session:{user_id}")
        if not raw:
            return {}
        state = json.loads(raw)
        if _time.time() - state.get("ts", 0) > _FOLLOWUP_STALE_SECONDS:
            return {}
        return state
    except Exception:
        return {}


async def _save_session_state(user_id: str, app_id: str, result: dict):
    """Save Hub session state after extension dispatch. Kernel-level, automatic."""
    try:
        r = await _get_hub_redis()
        response = result.get("response", "") if isinstance(result, dict) else str(result)
        fc_list = result.get("_functions_called", []) if isinstance(result, dict) else []
        last_fn = fc_list[-1].get("name", "") if fc_list else ""
        
        referenced_ids = re.findall(r'(?:ID|id)[:\s]+([a-zA-Z0-9_-]{8,})', response)
        
        # Detect if response asks a question (pending user confirmation)
        _is_question = response.rstrip().endswith("?") if response else False

        state = {
            "last_app": app_id,
            "last_function": last_fn,
            "referenced_ids": referenced_ids[:10],
            "response_preview": response[:300],
            "pending_question": response[:200] if _is_question else "",
            "ts": _time.time(),
        }
        await r.setex(
            f"imperal:hub_session:{user_id}",
            _HUB_SESSION_TTL,
            json.dumps(state, ensure_ascii=False),
        )
    except Exception as e:
        log.debug(f"Session state save failed (non-blocking): {e}")


def _strip_kernel_context(text: str) -> str:
    """Remove [KERNEL CONTEXT: ...] from response text. LLM may echo it back."""
    return re.sub(r'\s*\[KERNEL CONTEXT:[^\]]*\]', '', text).strip()


async def _enrich_if_followup(message: str, user_id: str) -> str:
    """Kernel-level follow-up enrichment. Deterministic, no LLM.
    
    Short messages (<=6 words) + recent session state = follow-up.
    Injects structured context from last extension call into the message.
    """
    words = message.strip().split()
    if len(words) > _FOLLOWUP_MAX_WORDS:
        return message

    state = await _load_session_state(user_id)
    if not state:
        return message

    parts = []
    if state.get("last_app"):
        parts.append(f"last_extension={state['last_app']}")
    if state.get("last_function"):
        parts.append(f"last_function={state['last_function']}")
    if state.get("referenced_ids"):
        parts.append(f"referenced_ids={','.join(state['referenced_ids'][:5])}")
    if state.get("response_preview"):
        parts.append(f"previous_response={state['response_preview'][:200]}")
    
    if not parts:
        return message
    
    context_block = " | ".join(parts)
    enriched = f"{message}\n\n[KERNEL CONTEXT: {context_block}]"
    log.info(f"Hub follow-up enrichment: '{message[:40]}' + {len(parts)} context fields")
    return enriched


async def _update_chain_status(user_id: str, context: dict, status_text: str):
    """Update chat status_text directly from Hub during chain execution.
    Kernel-level: writes to Redis so frontend polling picks it up."""
    assistant_msg_id = context.get("assistant_message_id")
    if not assistant_msg_id:
        return
    try:
        r = await _get_hub_redis()
        history_key = f"imperal:hub:chat:{user_id}"
        existing = await r.get(history_key)
        if not existing:
            return
        messages = json.loads(existing)
        for msg in messages:
            if msg.get("id") == assistant_msg_id and msg.get("status") == "processing":
                msg["status_text"] = status_text
                break
        await r.set(history_key, json.dumps(messages, ensure_ascii=False), ex=86400)
    except Exception:
        pass  # Best effort
