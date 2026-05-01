# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Auto-generate and validate extension manifests (`imperal.json`)."""
from __future__ import annotations
import json
import os
import inspect
from imperal_sdk.extension import Extension
from imperal_sdk.manifest_schema import (
    MANIFEST_SCHEMA,
    Manifest,
    Schedule,
    Signal,
    Tool,
    ToolParam,
    get_schema,
    validate_manifest_dict,
)

__all__ = [
    "generate_manifest",
    "save_manifest",
    "validate_manifest_dict",
    "get_schema",
    "MANIFEST_SCHEMA",
    "Manifest",
    "Tool",
    "ToolParam",
    "Signal",
    "Schedule",
]


def generate_manifest(ext: Extension) -> dict:
    """Auto-generate extension manifest from Extension object."""
    tools = []
    for name, tool_def in ext.tools.items():
        if name.startswith("__"):
            # Synthetic entries (__webhook__*, __panel__*, __widget__*, __tray__*)
            # belong to their own declarative sections — skip from user-facing tools list.
            continue
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
        "manifest_schema_version": 2,
        "app_id": ext.app_id,
        "version": ext.version,
        "capabilities": ext.capabilities,
        "tools": tools,
        "signals": signals,
        "schedules": schedules,
        "required_scopes": _collect_scopes(ext),
    }

    if ext.webhooks:
        manifest["webhooks"] = [wh.to_manifest() for wh in ext.webhooks.values()]

    if ext.event_handlers or ext.declared_emits:
        manifest["events"] = {
            "subscribes": [eh.to_manifest() for eh in ext.event_handlers],
            "emits":      [e.to_manifest() for e in ext.declared_emits],
        }

    if ext.exposed:
        manifest["exposed"] = [e.to_manifest() for e in ext.exposed.values()]

    if ext.lifecycle or ext._health_check:
        manifest["lifecycle"] = ext._build_lifecycle_section()

    if ext.tray_items:
        manifest["tray"] = [t.to_manifest() for t in ext.tray_items.values()]

    if ext.migrations_dir:
        manifest["migrations_dir"] = ext.migrations_dir

    if ext.config_defaults:
        manifest["config_defaults"] = ext.config_defaults

    return manifest


def _merge_disk_manifest(manifest: dict, path: str) -> dict:
    """Merge marketplace-only fields from on-disk imperal.json if it exists."""
    disk_path = os.path.join(path, "imperal.json")
    if not os.path.exists(disk_path):
        return manifest
    with open(disk_path) as f:
        disk = json.load(f)
    for field in ("name", "description", "author", "license", "homepage",
                  "icon", "category", "tags", "marketplace", "pricing"):
        if field in disk:
            manifest[field] = disk[field]
    return manifest


def save_manifest(ext: Extension, path: str = "manifest.json") -> str:
    """Generate and save manifest to file.

    If path is a directory, merges marketplace fields from existing imperal.json
    and writes to imperal.json in that directory.
    """
    manifest = generate_manifest(ext)
    if os.path.isdir(path):
        manifest = _merge_disk_manifest(manifest, path)
        path = os.path.join(path, "imperal.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return path


def _python_type_to_str(t) -> str:
    mapping = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}
    return mapping.get(t, "string")


def _collect_scopes(ext: Extension) -> list[str]:
    scopes = set()
    for name, tool_def in ext.tools.items():
        if name.startswith("__"):
            continue
        scopes.update(tool_def.scopes)
    return sorted(scopes)
