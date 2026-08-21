# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""The single source of truth for "what can the platform CALL on this app?".

Why this module exists (2026-08-21, WordPress Hub deploy report)
----------------------------------------------------------------
An extension declares callables through TWO decorators that write to TWO
separate registries:

  * ``@ext.tool``      -> ``Extension._tools``            (plus synthetic
                          ``__panel__*`` / ``__tray__*`` / ``__widget__*`` /
                          ``__webhook__*`` / ``__menu__*`` entries)
  * ``@chat.function`` -> ``ChatExtension._functions``    (reachable only via
                          ``ext._chat_extensions``)

``generate_manifest`` reads BOTH -- which is why a manifest is complete. Every
other consumer that reached for ``ext.tools`` alone silently saw a fraction of
the app. WordPress Hub made the gap impossible to miss: 260 ``@chat.function``
declarations, 1 ``@ext.tool``, 3 ``@ext.panel``, 1 ``@ext.skeleton`` -- so the
Developer Portal's registry sync reported "5 tools registered" for an app with
260 callables, and the catalog served 5.

The bug was never in WordPress Hub. It was in having two registries and no
agreed way to ask "all of them". Anything that needs the callable surface must
call ``callable_functions(ext)`` -- never iterate a registry directly.

``I-CALLABLE-SURFACE-SINGLE-SOURCE`` pins this: a federal test asserts the set
of names here is EXACTLY the set of names ``generate_manifest`` emits, so the
two can never drift apart again.
"""
from __future__ import annotations

from typing import Any

__all__ = ["callable_functions", "callable_function_names", "SYNTHETIC_TOOL_PREFIX"]

# Synthetic ``_tools`` entries are UI/transport plumbing (a panel route, a tray
# button, a webhook sink). They are addressable internally but are not part of
# the app's callable surface, and the manifest deliberately keeps them out of
# ``tools[]`` -- they belong to their own declarative sections.
SYNTHETIC_TOOL_PREFIX = "__"


def _tool_entry(name: str, tool_def: Any) -> dict:
    """Normalize an ``@ext.tool`` registration."""
    return {
        "name": name,
        "description": getattr(tool_def, "description", "") or "",
        "scopes": list(getattr(tool_def, "scopes", None) or []),
        # ``@ext.tool`` has no action_type; "read" is the conservative default
        # (it is the only value that never triggers a confirmation gate, so a
        # mis-default can never silently WAIVE one).
        "action_type": "read",
        "kind": "tool",
        "owner_chat_tool": "",
    }


def _chat_entry(fn_name: str, fn_def: Any, chat_tool_name: str) -> dict:
    """Normalize a ``@chat.function`` registration."""
    return {
        "name": fn_name,
        "description": getattr(fn_def, "description", "") or "",
        "scopes": [],
        "action_type": getattr(fn_def, "action_type", "read") or "read",
        "kind": "chat_function",
        "owner_chat_tool": chat_tool_name,
    }


def callable_functions(ext: Any, *, include_synthetic: bool = False) -> list[dict]:
    """Every callable this extension exposes, from BOTH registries.

    Ordering matches ``generate_manifest``: ``@ext.tool`` entries first (in
    declaration order), then each chat extension's functions. Deterministic
    order matters -- callers diff these lists across deploys.

    Args:
        ext: a loaded ``Extension``.
        include_synthetic: also return ``__panel__*``/``__tray__*``/... entries.
            Off by default: they are plumbing, not the app's callable surface.

    Returns:
        A list of plain dicts -- ``name``, ``description``, ``scopes``,
        ``action_type``, ``kind`` (``"tool"`` | ``"chat_function"``) and
        ``owner_chat_tool``. Plain dicts, not SDK types, so consumers outside
        this package (the Developer Portal registry sync) need no imports.

    Never raises: a malformed registry yields fewer entries, never an
    exception. This runs inside deploy, and a deploy must not fail because an
    app declared something odd.
    """
    out: list[dict] = []
    seen: set[str] = set()

    for name, tool_def in (getattr(ext, "tools", None) or {}).items():
        if not include_synthetic and str(name).startswith(SYNTHETIC_TOOL_PREFIX):
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(_tool_entry(name, tool_def))

    for chat_tool_name, chat_ext in (getattr(ext, "_chat_extensions", None) or {}).items():
        for fn_name, fn_def in (getattr(chat_ext, "functions", None) or {}).items():
            if fn_name in seen:
                # A name declared BOTH ways: the manifest emits the chat entry
                # too, but the catalog must stay a set -- first wins, and the
                # duplicate is the app author's problem, not a crash here.
                continue
            seen.add(fn_name)
            out.append(_chat_entry(fn_name, fn_def, str(chat_tool_name)))

    return out


def callable_function_names(ext: Any) -> set[str]:
    """Just the names -- for equality assertions and drift checks."""
    return {entry["name"] for entry in callable_functions(ext)}
