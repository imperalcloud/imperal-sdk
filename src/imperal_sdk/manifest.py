# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Auto-generate extension manifest from registered tools/signals/schedules."""
from __future__ import annotations
import json
import inspect
from imperal_sdk.extension import Extension


def generate_manifest(ext: Extension) -> dict:
    """Auto-generate extension manifest from Extension object."""
    tools = []
    for name, tool_def in ext.tools.items():
        sig = inspect.signature(tool_def.func)
        params = {}
        for pname, param in sig.parameters.items():
            if pname == "ctx":
                continue
            ptype = "string"
            if param.annotation != inspect.Parameter.empty:
                ptype = _python_type_to_str(param.annotation)
            params[pname] = {
                "type": ptype,
                "required": param.default == inspect.Parameter.empty,
            }
        tools.append({
            "name": name,
            "description": tool_def.description,
            "scopes": tool_def.scopes,
            "parameters": params,
        })

    signals = [{"name": name} for name in ext.signals]
    schedules = [
        {"name": name, "cron": sched.cron}
        for name, sched in ext.schedules.items()
    ]

    manifest = {
        "app_id": ext.app_id,
        "version": ext.version,
        "capabilities": ext.capabilities,
        "tools": tools,
        "signals": signals,
        "schedules": schedules,
        "required_scopes": _collect_scopes(ext),
    }

    if ext.migrations_dir:
        manifest["migrations_dir"] = ext.migrations_dir

    return manifest


def save_manifest(ext: Extension, path: str = "manifest.json") -> str:
    """Generate and save manifest to file."""
    manifest = generate_manifest(ext)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    return path


def _python_type_to_str(t) -> str:
    mapping = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
    return mapping.get(t, "string")


def _collect_scopes(ext: Extension) -> list[str]:
    scopes = set()
    for tool_def in ext.tools.values():
        scopes.update(tool_def.scopes)
    return sorted(scopes)
