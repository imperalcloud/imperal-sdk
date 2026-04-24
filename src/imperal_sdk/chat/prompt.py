# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Prompt and message building utilities for ChatExtension."""
from __future__ import annotations

from typing import TYPE_CHECKING

from imperal_sdk.prompts import load_prompt as _load_sdk_prompt

if TYPE_CHECKING:
    pass

ICNLI_INTEGRITY_RULES = "\n" + _load_sdk_prompt("icnli_integrity_rules.txt") + "\n"


def build_system_prompt(base_prompt: str, ctx, tool_name: str) -> str:
    """Build the full system prompt for a ChatExtension LLM call.

    Args:
        base_prompt: The extension's own system_prompt string.
        ctx: The Context object (kernel or SDK).
        tool_name: Extension tool name (unused currently, reserved for future use).

    Returns:
        Fully assembled system prompt string.
    """
    parts = [base_prompt, ICNLI_INTEGRITY_RULES]
    # v1.6.0: ``ctx.skeleton_data`` removed. The kernel now ships the
    # ``_capability_boundary`` + ``_icnli_integrity`` augment as an explicit
    # ``ctx._metadata`` fragment so chat extensions that were relying on the
    # passive snapshot still see it, but there is no implicit skeleton
    # read-through any more.
    _md = getattr(ctx, "_metadata", {}) or {}
    _ctx = _md.get("_context", {}) if isinstance(_md, dict) else {}
    cap = _ctx.get("_capability_boundary", {}) if isinstance(_ctx, dict) else {}
    if cap:
        _name = cap.get("assistant_name", "Webbee")
        _all_caps = cap.get("all_capabilities", "")
        parts.append(
            f"\nIDENTITY: You are {_name} — the AI of Imperal Cloud AI OS. "
            "You are powerful, intelligent, and capable of handling any task across the entire platform. "
            "You can ONLY use your available functions. If you cannot handle a request, "
            "say you'll take care of it — the platform routes automatically. "
            f"NEVER say 'I am the X assistant' or 'I'm the X app'. You are always {_name}."
        )
        if _all_caps:
            parts.append(f"\nYOUR FULL CAPABILITIES:\n{_all_caps}")
    integrity = _ctx.get("_icnli_integrity", {}) if isinstance(_ctx, dict) else {}
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
