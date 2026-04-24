# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Security guards for the ChatExtension tool-use loop.

Intent guard, target-scope guard, write-arg-bleed guard, and 2-step
confirmation guard. All guards return a JSON content string when
blocking/intercepting, or None when the tool_use should proceed to
execution.
"""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING, Any, Iterable

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

# Canonical error-code taxonomy (P2 Task 19 → imperal_sdk.chat.error_codes.ERROR_TAXONOMY).
# Import with fallback mirroring the exact 9 keys — so a missing/broken
# Task 19 module still leaves the bleed guard operational on the canonical set.
try:
    from imperal_sdk.chat.error_codes import ERROR_TAXONOMY  # type: ignore
except ImportError:  # pragma: no cover — defensive
    ERROR_TAXONOMY = frozenset({
        "VALIDATION_MISSING_FIELD",
        "VALIDATION_TYPE_ERROR",
        "UNKNOWN_TOOL",
        "UNKNOWN_SUB_FUNCTION",
        "PERMISSION_DENIED",
        "BACKEND_TIMEOUT",
        "BACKEND_5XX",
        "RATE_LIMITED",
        "INTERNAL",
    })

log = logging.getLogger(__name__)


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

    # ── Write-arg-bleed guard (I-WRITE-ARG-NO-BLEED) ──────────────
    # Defence-in-depth: reject any write/destructive call whose args contain
    # substrings of prior ERROR_TAXONOMY codes, even if the LLM paraphrased
    # an error_code into user-visible text. Runs BEFORE target_scope so we
    # fail fast on poisoned inputs without wasting cycles on scope checks.
    bleed = check_write_arg_bleed(tu, chat_ext._functions_called, action_type)
    if bleed is not None:
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input,
            "action_type": action_type, "success": False, "intercepted": False,
            "event": "", "result": None,
        })
        return json.dumps({"RESULT": "BLOCKED", "error": bleed})

    # ── Target scope guard ────────────────────────────────────────
    blocked = _check_target_scope_guard(chat_ext, ctx, tu, action_type, confirmation_required)
    if blocked is not None:
        return blocked

    # ── 2-step confirmation guard ─────────────────────────────────
    intercepted = _check_confirmation_guard(chat_ext, ctx, tu, action_type, confirmation_required)
    if intercepted is not None:
        return intercepted

    return None


def check_write_arg_bleed(
    tu,
    functions_called: Iterable[dict[str, Any]],
    action_type: str,
) -> str | None:
    """Reject write/destructive calls whose args contain a substring of any
    ERROR_TAXONOMY code when at least one prior tool call recorded an error
    code.

    Invariant I-WRITE-ARG-NO-BLEED — belt-and-suspenders over Task 19
    (structured error_codes) and Task 20 (tool_result hygiene). Even if an
    LLM paraphrases an error_code into prose, catch it before dispatch.

    Design notes:
    * Skips when ``action_type not in ("write", "destructive")`` — read args
      are free to echo error codes.
    * Skips when there is no prior error code — nothing to bleed from.
    * Serialises ``tu.input`` as JSON so nested dict/list values are scanned
      exhaustively.
    * Matching is case-insensitive — LLMs rephrase casing but preserve
      letter order (``validation_missing_field`` still lights up).
    * Scans the full ERROR_TAXONOMY, not just prior-this-turn codes — any
      taxonomy string appearing in a write arg is suspicious by construction.

    Federal discipline: never logs ``tu.input`` (may contain PII). Logs only
    tool name and the matched error code.

    Returns
    -------
    str | None
        ``None`` to allow, or a human-readable rejection reason to block.
        The caller (``check_guards``) wraps this into the standard
        ``{"RESULT": "BLOCKED", "error": ...}`` JSON envelope and appends
        a ``_functions_called`` audit entry.
    """
    if action_type not in ("write", "destructive"):
        return None

    # Only meaningful when there is at least one prior error code on record.
    has_prior_error_code = False
    for fc in functions_called or ():
        if fc.get("success"):
            continue
        result = fc.get("result")
        if isinstance(result, dict) and result.get("error_code"):
            has_prior_error_code = True
            break
    if not has_prior_error_code:
        return None

    # Exhaustive nested scan via JSON serialisation. Defensive fallback on
    # payloads that cannot be serialised (exotic objects) — we allow rather
    # than block, because we cannot prove a bleed on something we could not
    # serialise; failing closed here would be a DoS vector on legitimate calls.
    try:
        payload_lower = json.dumps(
            getattr(tu, "input", {}),
            ensure_ascii=False,
            default=str,
        ).lower()
    except Exception:
        return None

    # Iterating ERROR_TAXONOMY yields the 9 string keys whether it's a
    # ``dict[str, dict]`` (Task 19 shape) or a ``frozenset[str]`` (fallback).
    for code in ERROR_TAXONOMY:
        if code.lower() in payload_lower:
            log.warning(
                f"ChatExtension guard: WRITE_ARG_BLEED blocked {tu.name} "
                f"(matched error_code={code}, action={action_type})"
            )
            return (
                f"WRITE_ARG_BLEED rejected: tool call '{tu.name}' args contain "
                f"error_code substring '{code}'. The LLM appears to be paraphrasing "
                "a prior error into user-visible output. Retry without that text."
            )

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
    # must flow through ``ctx.cache`` or an explicit ``@ext.skeleton`` tool
    # running in a skeleton-typed context. The guard downgrades to empty
    # rather than cross-ext-leaking, which is the safer default for the
    # target-scope check.
    _connected_emails: list = []

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
