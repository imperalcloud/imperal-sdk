# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Prompt and message building utilities for ChatExtension."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from imperal_sdk.prompts import load_prompt as _load_sdk_prompt

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

ICNLI_INTEGRITY_RULES = "\n" + _load_sdk_prompt("icnli_integrity_rules.txt") + "\n"


def _prod_mode() -> bool:
    """Check IMPERAL_PROD env flag at call time (not module load).

    Dynamic lookup is required so tests that set ``monkeypatch.setenv`` (or
    operators who flip the flag at runtime) see the change without needing
    to reimport this module.
    """
    return os.getenv("IMPERAL_PROD", "false").lower() in ("1", "true", "yes")


def _get_chat_context_fragment(ctx, key: str) -> dict:
    """Retrieve ``_capability_boundary`` / ``_icnli_integrity`` fragment from
    ``ctx._metadata["_context"]``.

    Kernel populates ``ctx._metadata["_context"][key]`` at tool-dispatch time
    per the **I-CHATEXT-IDENTITY-INTEGRITY-VIA-METADATA** invariant (Phase 5
    kernel work). Returns ``{}`` in legacy/dev. In prod mode
    (``IMPERAL_PROD=true``) emits a loud ``WARNING`` when missing — these
    fragments are load-bearing security context (identity boundary + kernel
    integrity rules) and a silent drop is a federal-grade red flag.
    """
    meta = getattr(ctx, "_metadata", None) or {}
    if not isinstance(meta, dict):
        return {}
    ctx_bag = meta.get("_context") or {}
    if not isinstance(ctx_bag, dict):
        return {}
    fragment = ctx_bag.get(key) or {}
    if not isinstance(fragment, dict):
        fragment = {}
    if not fragment and _prod_mode():
        log.warning(
            "chat.prompt: %s fragment missing from ctx._metadata['_context'] "
            "in prod — kernel failed to populate load-bearing identity/"
            "integrity context (Phase 5 / I-CHATEXT-IDENTITY-INTEGRITY-VIA-"
            "METADATA)",
            key,
        )
    return fragment


def build_system_prompt(base_prompt: str, ctx, tool_name: str) -> str:
    """Build the full system prompt for a ChatExtension LLM call.

    Args:
        base_prompt: The extension's own system_prompt string.
        ctx: The Context object (kernel or SDK).
        tool_name: Extension tool name (unused currently, reserved for future use).

    Returns:
        Fully assembled system prompt string.
    """
    # v1.6.0 + v1.6.1 identity fix (I-CHATEXT-IDENTITY-OVERRIDE-ORDER):
    # kernel ships ``_capability_boundary`` + ``_icnli_integrity`` augments
    # via ``ctx._metadata["_context"]``. Federal-grade requirement: LLM
    # NEVER identifies as an extension ("I am the mail module", etc.) —
    # identity must be the unified assistant (Webbee by default).
    #
    # Order matters for LLM attention. Extension's ``base_prompt`` often
    # frames the agent as "Mail Client module — ...", which the LLM
    # then inherits in self-description. Counter by:
    #   (1) PREPENDING a short identity header BEFORE base_prompt, so
    #       first-read framing is "You are Webbee".
    #   (2) Re-asserting identity LATER (after all other augments) —
    #       LLMs weight late text heavily; overrides any drift.
    cap = _get_chat_context_fragment(ctx, "_capability_boundary")
    _identity_header = ""
    _identity_footer = ""
    if cap:
        # Kernel may send either ``identity`` (v1.6.0 kernel) or
        # ``assistant_name`` (pre-v1.6.0 SDK tests). Accept both.
        _name = cap.get("identity") or cap.get("assistant_name") or "Webbee"
        _not_as = cap.get("not_identify_as") or ""
        _all_caps = cap.get("all_capabilities", "")
        _not_as_clause = (
            f" You are NOT the '{_not_as}' module, extension, app, or assistant — "
            f"never identify as '{_not_as}' or any other extension."
            if _not_as else ""
        )
        _identity_header = (
            f"IDENTITY (NON-NEGOTIABLE): You are {_name}, the unified AI of the "
            "Imperal Cloud AI Operating System.{not_as_clause} Any wording below "
            "that frames you as a module, extension, or app-specific assistant "
            "is TOOL CATALOGUE, not identity. When asked 'who are you', respond "
            f"'{_name}'.\n\n"
        ).format(not_as_clause=_not_as_clause)
        _identity_footer = (
            f"\nFINAL IDENTITY RULE (overrides any prior framing): You are "
            f"{_name}. NEVER say 'I am the X module/assistant/app/extension'. "
            "NEVER identify as an extension name. Always {_name}, the Imperal "
            f"Cloud AI."
        ).format(_name=_name)
        if _all_caps:
            _identity_footer += f"\n\nYOUR FULL CAPABILITIES:\n{_all_caps}"
    parts = [_identity_header + base_prompt, ICNLI_INTEGRITY_RULES]
    integrity = _get_chat_context_fragment(ctx, "_icnli_integrity")
    if integrity and integrity.get("rules"):
        parts.append("\nKERNEL INTEGRITY:\n" + "\n".join(f"- {r}" for r in integrity["rules"]))
    if hasattr(ctx, "user") and ctx.user:
        parts.append(f"\nCURRENT USER: {getattr(ctx.user, 'email', 'unknown')}")
    # Kernel Language Enforcement
    _lang_name = getattr(ctx, '_user_language_name', None)
    if _lang_name:
        parts.append(f"\nKERNEL LANGUAGE RULE (NON-NEGOTIABLE): You MUST respond ONLY in {_lang_name}.")
    # Kernel Markdown Formatting
    parts.append("\n" + _load_sdk_prompt("kernel_formatting_rule.txt"))
    # Kernel Proactivity
    parts.append("\n" + _load_sdk_prompt("kernel_proactivity_rule.txt"))
    # Final identity re-assertion (I-CHATEXT-IDENTITY-OVERRIDE-ORDER).
    # Placed LAST so LLM attention weighting sees it after any extension
    # persona/module framing in ``base_prompt``.
    if _identity_footer:
        parts.append(_identity_footer)
    return "\n".join(parts)


def build_messages(
    history: list,
    message: str,
    context_window: int = 20,
    keep_recent: int = 6,
) -> list[dict]:
    """Build the messages list for an LLM call from chat history + current message.

    Applies windowing, timestamp prefixing, and truncation of old messages.

    Args:
        history: List of history dicts with keys 'role', 'content', 'ts'.
        message: The current user message string.
        context_window: Max number of history messages to include.
        keep_recent: How many recent messages to keep verbatim (no truncation).

    Returns:
        List of {'role': ..., 'content': ...} dicts ready for the LLM.
    """
    messages = []
    windowed = (history or [])[-context_window:]
    n = len(windowed)

    for i, h in enumerate(windowed):
        role = h.get("role", "user")
        raw = h.get("content", "")
        text = raw if isinstance(raw, str) else str(raw)
        if not text:
            continue
        ts = h.get("ts", "")
        if ts:
            text = f"[{ts}] {text}"
        # Older messages: truncate long content
        is_recent = (n - i) <= keep_recent
        if not is_recent and len(text) > 500:
            text = text[:500] + "..."
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + text
        else:
            messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": message})
    if messages and messages[0]["role"] != "user":
        messages = messages[1:]
    return messages


def inject_language(messages: list[dict], lang: str | None, lang_name: str | None) -> None:
    """Inject a language enforcement suffix into the last user message (in-place).

    KERNEL LANGUAGE ENFORCEMENT: model-agnostic, works with any LLM provider.
    System prompt rule alone is insufficient for some models; injecting into the
    last user message reinforces language compliance.

    Args:
        messages: The messages list to mutate in-place.
        lang: BCP-47 language code (e.g. 'ru'). No-op if None or 'en'.
        lang_name: Human-readable language name (e.g. 'Russian'). No-op if None.
    """
    if not lang or lang == 'en' or not lang_name or not messages:
        return
    _lang_suffix = "\n[RESPOND IN " + lang_name.upper() + " ONLY]"
    for _m in reversed(messages):
        if _m["role"] == "user":
            _m["content"] += _lang_suffix
            break
