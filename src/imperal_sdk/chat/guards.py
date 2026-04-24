# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Security guards for the ChatExtension tool-use loop.

Intent guard, target-scope guard, and 2-step confirmation guard.
All guards return a JSON content string when blocking/intercepting,
or None when the tool_use should proceed to execution.
"""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from imperal_sdk.chat.extension import ChatExtension

# Target scope guard (kernel-only, graceful fallback in SDK-only mode)
try:
    from imperal_sdk.runtime.executor import _check_target_scope
except ImportError:
    import logging as _log_tsc
    _log_tsc.getLogger(__name__).error(
        "CRITICAL: _check_target_scope import failed — all cross-user actions will be BLOCKED"
    )
    def _check_target_scope(**kwargs):
        return {"allowed": False, "cross_user": True, "error": "target_scope_unavailable"}

log = logging.getLogger(__name__)


def _get_connected_emails(ctx) -> list[str]:
    """Retrieve connected-email list from ``ctx._metadata``.

    Kernel populates ``ctx._metadata["connected_emails"]`` at tool-dispatch
    time per the **I-CONNECTED-EMAILS-VIA-METADATA** invariant (see Phase 5
    kernel work). Returns ``[]`` in legacy/dev contexts where metadata is
    not yet populated — this is **fail-SAFE** (empty list narrows
    target-scope authorisation, does not widen; a non-owner caller with
    an empty connected-email set cannot match foreign addresses and so
    cross-user writes stay blocked by the target-scope guard).
    """
    meta = getattr(ctx, "_metadata", None) or {}
    if not isinstance(meta, dict):
        return []
    val = meta.get("connected_emails", [])
    if not isinstance(val, list):
        return []
    # Keep only string entries, filter empties
    return [e for e in val if isinstance(e, str) and e]


def check_guards(
    chat_ext: ChatExtension,
    ctx,
    tu,
    action_type: str,
    confirmation_required: bool,
) -> str | None:
    """Run all security guards for a single tool_use block.

    Returns a JSON content string if the call should be blocked or intercepted,
    or None if the call should proceed to execution.
    """
    # ── Intent guard ──────────────────────────────────────────────
    _ctx_intent = getattr(ctx, "_intent_type", None) or "read"
    if _ctx_intent in ("chain", "automation"):
        pass  # Bypass: function's own action_type is the source of truth
    elif _ctx_intent == "read" and action_type == "write":
        # Escalate: when the extension LLM confidently picks a write tool
        # under a read-classified turn, trust the tool choice (LLM is
        # authoritative over classifier heuristics) and promote _intent_type
        # to "write". The extension then proceeds to execute. Destructive
        # actions do NOT escalate — they still require 2-step confirmation,
        # so the old BLOCK path covers them below.
        log.info(
            f"ChatExtension {chat_ext.tool_name}: ESCALATE {tu.name} "
            f"action=write; classifier said read but extension LLM chose write — trusting LLM"
        )
        ctx._intent_type = "write"
        # Do not append to _functions_called; do not return a verdict — fall
        # through to target_scope + confirmation guards below.
    elif _ctx_intent == "read" and action_type == "destructive":
        log.warning(
            f"ChatExtension {chat_ext.tool_name}: BLOCKED {tu.name} "
            f"(action=destructive) — intent is read, destructive requires explicit user intent"
        )
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input,
            "action_type": action_type, "success": False, "intercepted": False,
            "event": "", "result": None,
        })
        return json.dumps({
            "RESULT": "BLOCKED",
            "error": (
                f"Cannot execute destructive action '{tu.name}' — the user's "
                "request was classified as read-only. Destructive actions require "
                "explicit user intent. Ask the user to confirm if they want to "
                "proceed, then re-run."
            ),
        })

    # ── Target scope guard ────────────────────────────────────────
    blocked = _check_target_scope_guard(chat_ext, ctx, tu, action_type, confirmation_required)
    if blocked is not None:
        return blocked

    # ── 2-step confirmation guard ─────────────────────────────────
    intercepted = _check_confirmation_guard(chat_ext, ctx, tu, action_type, confirmation_required)
    if intercepted is not None:
        return intercepted

    return None


def _check_target_scope_guard(
    chat_ext: ChatExtension,
    ctx,
    tu,
    action_type: str,
    confirmation_required: bool,
) -> str | None:
    """Target scope guard — blocks cross-user actions without proper scopes."""
    _caller_id = str(getattr(ctx.user, 'id', '')) if hasattr(ctx, 'user') and ctx.user else ''
    _caller_email = str(getattr(ctx.user, 'email', '')) if hasattr(ctx, 'user') and ctx.user else ''
    _caller_scopes = getattr(ctx.user, 'scopes', ['*']) if hasattr(ctx, 'user') and ctx.user else ['*']
    # v1.6.0: ``ctx.skeleton_data`` removed. Connected-email enumeration
    # now flows through ``ctx._metadata["connected_emails"]`` populated by
    # the kernel at tool-dispatch time (Phase 5 / I-CONNECTED-EMAILS-VIA-
    # METADATA). Empty list is the fail-SAFE default for legacy/dev
    # contexts — narrows target-scope authorisation, does not widen.
    _connected_emails: list = _get_connected_emails(ctx)

    _tsg = _check_target_scope(
        tool_use_params=tu.input,
        caller_id=_caller_id,
        caller_email=_caller_email,
        caller_scopes=_caller_scopes,
        intent_type=action_type,
        connected_emails=_connected_emails,
    )

    if not _tsg["allowed"]:
        log.warning(
            f"ChatExtension {chat_ext.tool_name}: TARGET_SCOPE BLOCKED "
            f"{tu.name} target={_tsg['target_user_id']}"
        )
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input,
            "action_type": action_type, "success": False, "intercepted": False,
            "event": "", "result": None, "_target_scope": _tsg,
        })
        return json.dumps({
            "RESULT": "BLOCKED",
            "error": (
                f"Cross-user action blocked. Required scope: {_tsg['required_scope']}. "
                f"You are operating on user '{_tsg['target_user_id']}' which is not the current user."
            ),
        })

    if _tsg.get("force_confirmation") and not confirmation_required:
        log.info(
            f"ChatExtension {chat_ext.tool_name}: TARGET_SCOPE forcing "
            f"confirmation for {tu.name}"
        )
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input,
            "action_type": action_type, "success": False, "intercepted": True,
            "event": "", "result": None, "_target_scope": _tsg,
        })
        return json.dumps({
            "RESULT": "INTERCEPTED",
            "message": (
                f"This destructive action targets another user ({_tsg['target_user_id']}). "
                "Confirmation required."
            ),
            "function": tu.name,
            "params": tu.input,
            "action_type": action_type,
        })

    return None


def _check_confirmation_guard(
    chat_ext: ChatExtension,
    ctx,
    tu,
    action_type: str,
    confirmation_required: bool,
) -> str | None:
    """2-step confirmation guard — intercepts write/destructive when confirmation enabled."""
    if not confirmation_required or action_type not in ("write", "destructive"):
        return None

    _conf_acts = getattr(ctx, "_confirmation_actions", {})
    if isinstance(_conf_acts, dict):
        _should_confirm = _conf_acts.get(action_type, False) or _conf_acts.get("all", False)
    else:
        _should_confirm = action_type in _conf_acts or "all" in _conf_acts

    if not _should_confirm:
        return None

    chat_ext._functions_called.append({
        "name": tu.name, "params": tu.input,
        "action_type": action_type, "success": False, "intercepted": True,
        "event": "", "result": None,
    })
    return json.dumps({
        "RESULT": "INTERCEPTED",
        "message": "Action requires user confirmation before execution.",
        "function": tu.name,
        "params": tu.input,
        "action_type": action_type,
    })
