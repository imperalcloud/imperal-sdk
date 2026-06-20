# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""generate_ir — map an Extension's manifest onto the IR envelope (impl=code)."""
from __future__ import annotations

from typing import Any

from ..manifest import generate_manifest


_IR_VERSION = "1.0"

# Tool name prefixes that belong to ui/skeleton slots — handled in later tasks
# (E2/E5). Exclude them from the IR functions list.
_SKIP_PREFIXES = ("__panel__", "__webhook__", "__widget__", "__tray__", "skeleton_refresh_", "skeleton_alert_")


def generate_ir(ext: Any) -> dict[str, Any]:
    """Map an Extension's manifest onto the IR envelope.

    All handlers are ``impl.kind="code"`` — the pure-declarative impl kind
    (``declarative``) is reserved for future tasks (L0-2 phase B).

    Skips synthetic tool entries:
    - ``__panel__`` / ``__webhook__`` / ``__widget__`` / ``__tray__`` —
      handled by their own manifest sections.
    - ``skeleton_refresh_`` / ``skeleton_alert_`` — handled by the skeleton
      slot (E2/E5).
    """
    m = generate_manifest(ext)
    functions: list[dict[str, Any]] = []

    for tool in m.get("tools", []):
        name: str = tool["name"]
        # Skip any tool whose name starts with a synthetic prefix.
        if any(name.startswith(prefix) for prefix in _SKIP_PREFIXES):
            continue
        functions.append({
            "name": name,
            "description": tool.get("description", ""),
            "params_schema": tool.get("params_schema") or {},
            "return_schema": tool.get("return_schema") or None,
            "action_type": tool.get("action_type") or "read",
            "effects": list(tool.get("effects") or []),
            "event": tool.get("event") or "",
            "impl": {
                "kind": "code",
                "module": "handlers",
                "entry": tool.get("owner_chat_tool") or name,
            },
        })

    panels_ir: list[dict] = []
    for p in m.get("panels", []):
        tree = p.get("tree") or {}
        if tree:
            render: dict = {"kind": "static", "tree": tree}
        else:
            render = {
                "kind": "code",
                "module": "panels",
                "entry": f"__panel__{p['panel_id']}",
            }
        panels_ir.append({
            "panel_id": p["panel_id"],
            "slot": p.get("slot", "center"),
            "title": p.get("title", ""),
            "render": render,
        })

    app: dict = {
        "id": m.get("app_id", ""),
        "version": m.get("version", ""),
        "title": m.get("name", "") or m.get("app_id", ""),
        "description": m.get("description", ""),
        "capabilities": list(m.get("capabilities") or []),
        "functions": functions,
    }
    if panels_ir:
        app["ui"] = {"panels": panels_ir}

    return {
        "ir_version": _IR_VERSION,
        "sdl_vocab_version": "1",
        "contract_version": "1.0",
        "app": app,
    }
