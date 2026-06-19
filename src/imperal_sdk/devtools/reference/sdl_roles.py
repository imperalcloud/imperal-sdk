# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""``sdl_role`` kind — every facet role / marker class exported by ``imperal_sdk.sdl``.

Roles are the capitalized marker classes in ``dir(sdl)`` (Entity, EntityList,
Monetary, Geolocated, …). Non-role capitalized exports are excluded: data
constants (CORE_ROLES, RESERVED_NAMESPACES, ROLE_KEY) and the RoleError
exception. Each role captures its facet field roles (``sdl.roles_of``) as
params and its namespace (``sdl.namespace_of``) under ``enums.namespace``.
"""
from __future__ import annotations

import inspect
from typing import Any

# Capitalized sdl exports that are NOT facet roles.
_NON_ROLE_CAPS = {"CORE_ROLES", "RESERVED_NAMESPACES", "ROLE_KEY"}


def collect() -> dict[str, dict[str, Any]]:
    import imperal_sdk.sdl as sdl

    symbols: dict[str, dict[str, Any]] = {}
    for name in dir(sdl):
        if not name[:1].isupper() or name in _NON_ROLE_CAPS:
            continue
        obj = getattr(sdl, name)
        if not inspect.isclass(obj):
            continue
        if issubclass(obj, Exception):  # RoleError et al. are not roles
            continue
        symbols[f"sdl.{name}"] = _role_symbol(sdl, name, obj)
    return symbols


def _role_symbol(sdl: Any, name: str, obj: Any) -> dict[str, Any]:
    enums: dict[str, list[str]] = {}
    try:
        enums["namespace"] = [sdl.namespace_of(name)]
    except Exception:  # core markers like Entity have no namespaced split
        enums["namespace"] = [name]

    # Facet field roles → params (name=field, annotation=role string).
    params: list[dict[str, Any]] = []
    try:
        for field_name, role in sdl.roles_of(obj).items():
            params.append({
                "name": field_name,
                "annotation": role,
                "default": None,
                "required": False,
            })
    except Exception:
        params = []

    return {
        "kind": "sdl_role",
        "params": sorted(params, key=lambda p: p["name"]),
        "returns": None,
        "enums": enums,
    }
