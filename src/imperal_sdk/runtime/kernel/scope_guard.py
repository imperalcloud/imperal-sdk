# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Kernel scope enforcement — tool scopes + target scope guard.

Pure functions, zero state, zero I/O.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# ── Tool Scope Checking ──────────────────────────────────────────


def _check_tool_scopes(user_scopes: list[str], required_scopes: list[str]) -> tuple[bool, list[str]]:
    """Check scopes with colon format (resource:action). Supports wildcards."""
    if not required_scopes or required_scopes == ["*"]:
        return True, []
    if "*" in user_scopes:
        return True, []
    missing = []
    for required in required_scopes:
        if required in user_scopes:
            continue
        resource, sep, action = required.partition(":")
        if sep and f"{resource}:*" in user_scopes:
            continue
        # extensions:ACTION covers all extension tools (meta-scope)
        if sep and action and f"extensions:{action}" in user_scopes:
            continue
        if "extensions:*" in user_scopes:
            continue
        # Legacy dot format fallback
        if "." in required:
            parts = required.split(".")
            if parts[0] + ".*" in user_scopes:
                continue
        missing.append(required)
    return len(missing) == 0, missing


# ── Target Scope Guard ────────────────────────────────────────────
# Kernel-level guard: prevents cross-user actions without proper scopes.
# Convention-based parameter detection + graduated scope requirements.

TARGET_PARAM_CONVENTIONS = {
    "user_id": "user_id",
    "target_user": "user_id",
    "user_ids": "user_id_list",
    "email": "email",
    "target_email": "email",
    "account_id": "account_id",
}

# Graduated scope requirements by intent type
_TARGET_SCOPE_BY_INTENT = {
    "read": ["users:read"],
    "write": ["users:manage"],
    "destructive": ["users:admin"],
}


def _check_target_scope(
    tool_use_params: dict,
    caller_id: str,
    caller_email: str,
    caller_scopes: list[str],
    intent_type: str = "read",
    connected_emails: list[str] | None = None,
    target_params_override: list[str] | None = None,
) -> dict:
    """Kernel target scope guard.

    Inspects tool_use parameters for target user identifiers.
    If target differs from caller, checks graduated scopes.

    Args:
        tool_use_params: The parameters from tool_use (e.g. {"user_id": "xxx", "role": "admin"})
        caller_id: The requesting user's imperal_id (ctx.user.id)
        caller_email: The requesting user's email (ctx.user.email)
        caller_scopes: The requesting user's scopes list
        intent_type: "read", "write", or "destructive"
        connected_emails: List of caller's connected email addresses (multi-account)
        target_params_override: SDK decorator override — explicit list of param names that are targets

    Returns:
        dict with keys:
            "allowed": bool
            "cross_user": bool
            "target_user_id": str|None
            "target_param": str|None
            "required_scope": str|None
            "force_confirmation": bool
            "verdict": str — "self_target" | "no_target" | "pass" | "blocked" | "escalated"
    """
    if not tool_use_params or not isinstance(tool_use_params, dict):
        return {"allowed": True, "cross_user": False, "target_user_id": None,
                "target_param": None, "required_scope": None,
                "force_confirmation": False, "verdict": "no_target"}

    # Determine which params to check
    params_to_check = target_params_override or list(TARGET_PARAM_CONVENTIONS.keys())
    caller_emails = set()
    if caller_email:
        caller_emails.add(caller_email.lower())
    if connected_emails:
        caller_emails.update(e.lower() for e in connected_emails)

    # Scan params for target identifiers
    for param_name in params_to_check:
        if param_name not in tool_use_params:
            continue
        value = tool_use_params[param_name]
        if value is None or value == "":
            continue

        # Determine identifier type
        id_type = TARGET_PARAM_CONVENTIONS.get(param_name, "user_id")

        # Handle list params (e.g. user_ids)
        if id_type == "user_id_list":
            if not isinstance(value, list) or not value:
                continue
            # All-or-nothing: if ANY element is cross-user, entire op is cross-user
            has_cross_user = any(str(uid) != str(caller_id) for uid in value)
            if not has_cross_user:
                continue  # All self-targets
            return _evaluate_cross_user(
                target_id=",".join(str(v) for v in value),
                param_name=param_name,
                caller_scopes=caller_scopes,
                intent_type=intent_type,
            )

        # Handle single value
        value_str = str(value).strip()

        if id_type == "email":
            if value_str.lower() in caller_emails:
                continue  # Self-target
        elif id_type in ("user_id", "account_id"):
            if value_str == str(caller_id):
                continue  # Self-target

        # Cross-user detected
        return _evaluate_cross_user(
            target_id=value_str,
            param_name=param_name,
            caller_scopes=caller_scopes,
            intent_type=intent_type,
        )

    # No cross-user targets found
    return {"allowed": True, "cross_user": False, "target_user_id": None,
            "target_param": None, "required_scope": None,
            "force_confirmation": False, "verdict": "no_target"}


def _evaluate_cross_user(
    target_id: str,
    param_name: str,
    caller_scopes: list[str],
    intent_type: str,
) -> dict:
    """Evaluate whether a cross-user action is allowed based on scopes."""
    required_scopes = _TARGET_SCOPE_BY_INTENT.get(intent_type, ["users:read"])
    allowed, missing = _check_tool_scopes(caller_scopes, required_scopes)

    if not allowed:
        log.warning(
            f"TARGET_SCOPE BLOCKED: target={target_id} param={param_name} "
            f"intent={intent_type} missing={missing}"
        )
        return {
            "allowed": False,
            "cross_user": True,
            "target_user_id": target_id,
            "target_param": param_name,
            "required_scope": required_scopes[0] if required_scopes else None,
            "force_confirmation": False,
            "verdict": "blocked",
        }

    # Scope sufficient — but destructive cross-user forces 2-Step
    force_confirm = (intent_type == "destructive")
    if force_confirm:
        log.info(
            f"TARGET_SCOPE ESCALATED: target={target_id} param={param_name} "
            f"intent={intent_type} → forced 2-Step Confirmation"
        )
    else:
        log.info(
            f"TARGET_SCOPE PASS: target={target_id} param={param_name} "
            f"intent={intent_type}"
        )

    return {
        "allowed": True,
        "cross_user": True,
        "target_user_id": target_id,
        "target_param": param_name,
        "required_scope": required_scopes[0] if required_scopes else None,
        "force_confirmation": force_confirm,
        "verdict": "escalated" if force_confirm else "pass",
    }
