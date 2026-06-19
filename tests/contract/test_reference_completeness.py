# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Ф1 T6 — SDK reference completeness gate.

Derives the EXPECTED public surface **independently** from the live code —
no call to generate_reference() or its frozen lists — then asserts every
live symbol is a key in the committed sdk-reference.json.

Anti-circularity principle: if a new public symbol is added to any of the six
kinds (ui_component / sdl_role / sdl_func / client_method / decorator /
dataclass) and the reference collectors are NOT updated, this test fails.

Kinds and how the expected set is derived independently
-------------------------------------------------------
ui_component
    ``imperal_sdk.ui.__all__`` — every capitalized callable factory.
    Non-function entries (``AgencyTheme``, ``ColorPair``) are excluded;
    they are data objects, not component factories.

sdl_role
    Capitalized names in ``dir(imperal_sdk.sdl)`` that are classes and not
    exceptions. Filtered against ``_SDl_ROLE_NON_ROLE_CAPS`` (constants
    that are caps but not roles).

sdl_func
    Lowercase callable names in ``dir(imperal_sdk.sdl)``.
    Submodule names (``entity``, ``roles``, ``facets``) degrade to a note
    in the reference — allowlisted here with reason "submodule, not a fn".

client_method
    Derived via ``_load_namespaces`` (federal: reuse the same enumerator
    generate_reference uses, but called independently). Each
    ``ctx.<ns>.<method>`` is a live public callable.

decorator
    Public function-type members of ``Extension`` that are decorator
    factories, plus ``chat.function`` from ``ChatExtension``. Properties,
    collection attrs, and non-factory helpers are excluded via
    ``_EXT_NON_DECORATOR_FNS``. ``ext.lifecycle`` is allowlisted as a
    property (not callable-type). ``ext.on_refresh`` was a mistaken entry
    in the reference and has been removed.

dataclass
    Entries in ``imperal_sdk.__all__`` that are dataclasses or pydantic
    models. Non-result types (``Context``, ``User``, ``UserContext``,
    ``Tenant``, ``TenantContext``, ``LLMConfig``, ``LLMUsage``,
    ``ValidationReport``, ``ValidationIssue``) are intentionally excluded
    from the reference (they are implementation / auth types, not API
    result/def types surfaced to extension authors) — allowlisted with
    reason.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Allowlist: symbol → reason why it is legitimately absent from the reference
# ---------------------------------------------------------------------------
REFERENCE_COVERAGE_EXCLUSIONS: dict[str, str] = {
    # sdl submodules — present in dir(sdl) as lowercase names but are
    # modules, not callable functions; the reference records them as degraded
    # _note placeholders which still produce a reference KEY — they are covered.
    # (No exclusion needed; they ARE keys in the reference.)
    #
    # ext.lifecycle — property on Extension, not a decorator factory. The
    # reference carries it as a degraded placeholder with a note.
    # (No exclusion needed; "ext.lifecycle" IS a key in the reference.)
    #
    # Dataclasses intentionally NOT in the reference (implementation / auth
    # types, not extension-author API result/def types):
    "Context": "internal kernel dataclass, not an extension-author result/def type",
    "User": "auth pydantic model, not an extension-author result/def type",
    "UserContext": "auth pydantic model, not an extension-author result/def type",
    "Tenant": "auth pydantic model, not an extension-author result/def type",
    "TenantContext": "auth pydantic model, not an extension-author result/def type",
    "LLMConfig": "LLM plumbing dataclass, not surfaced to extension authors",
    "LLMUsage": "LLM plumbing dataclass, not surfaced to extension authors",
    "ValidationReport": "dev-tool type, not an extension-author result/def type",
    "ValidationIssue": "dev-tool type, not an extension-author result/def type",
    #
    # ui non-factory exports — data objects, not component factories
    "ui.AgencyTheme": "data class, not a UINode factory",
    "ui.ColorPair": "data class, not a UINode factory",
    "ui.theme": "utility function returning a theme dict, not a UINode factory",
}

# Extension members that are functions but NOT decorator factories
# (collection accessors, utility callers, etc.).
_EXT_NON_DECORATOR_FNS: frozenset[str] = frozenset({
    "call_signal",
    "call_tool",
    "expose",
    "health_check",
    "on_disable",
    "on_enable",
    "on_event",
    "on_install",
    "on_uninstall",
    "schedule",
    "signal",
})

# Capitalized sdl exports that are constants, not facet-role classes.
_SDL_ROLE_NON_ROLE_CAPS: frozenset[str] = frozenset({
    "CORE_ROLES", "RESERVED_NAMESPACES", "ROLE_KEY",
})


# ---------------------------------------------------------------------------
# Independent expected-set derivers (one per kind)
# ---------------------------------------------------------------------------

def _expected_ui_components() -> set[str]:
    """ui.* component factories: capitalized callable entries in ui.__all__."""
    import imperal_sdk.ui as ui
    result: set[str] = set()
    for name in ui.__all__:
        obj = getattr(ui, name)
        if not inspect.isfunction(obj):
            continue  # AgencyTheme, ColorPair are data types not factories
        result.add(f"ui.{name}")
    return result


def _expected_sdl_roles() -> set[str]:
    """sdl.* roles: capitalized classes in dir(sdl), minus exceptions/constants."""
    import imperal_sdk.sdl as sdl
    result: set[str] = set()
    for name in dir(sdl):
        if not name[:1].isupper() or name in _SDL_ROLE_NON_ROLE_CAPS:
            continue
        obj = getattr(sdl, name)
        if not inspect.isclass(obj):
            continue
        if issubclass(obj, Exception):
            continue
        result.add(f"sdl.{name}")
    return result


def _expected_sdl_funcs() -> set[str]:
    """sdl.* functions: public lowercase callables in dir(sdl).

    Submodules (entity, roles, facets) are in dir(sdl) as modules — the
    reference carries them as degraded placeholders (still present as keys),
    so no exclusion is needed for them.
    """
    import imperal_sdk.sdl as sdl
    result: set[str] = set()
    for name in dir(sdl):
        if name.startswith("_") or not name[:1].islower():
            continue
        obj = getattr(sdl, name)
        # Accept callables and modules; the reference must have a key for both.
        if callable(obj) or inspect.ismodule(obj):
            result.add(f"sdl.{name}")
    return result


def _expected_client_methods() -> set[str]:
    """ctx.<ns>.<method>: derived from _load_namespaces (federal reuse)."""
    from imperal_sdk.devtools.generate_api_surface import _load_namespaces
    result: set[str] = set()
    for ns, cls in _load_namespaces().items():
        for name, _ in inspect.getmembers(cls, predicate=callable):
            if not name.startswith("_"):
                result.add(f"ctx.{ns}.{name}")
    return result


def _expected_decorators() -> set[str]:
    """chat.function + ext.* decorator factories.

    Extension methods that are function-type but NOT in _EXT_NON_DECORATOR_FNS
    are decorator factories. Properties (like ext.lifecycle) ARE expected as
    reference keys (the reference carries them as degraded notes); they cannot
    be derived here as "function" members — the reference must have them.
    We separately assert ext.lifecycle and NOT ext.on_refresh.
    """
    from imperal_sdk.extension import Extension
    from imperal_sdk.chat.extension import ChatExtension  # noqa: F401

    result: set[str] = {"chat.function"}
    for name in dir(Extension):
        if name.startswith("_"):
            continue
        member = inspect.getattr_static(Extension, name, None)
        if not inspect.isfunction(member):
            continue  # skip properties, descriptors, non-callables
        if name in _EXT_NON_DECORATOR_FNS:
            continue
        result.add(f"ext.{name}")
    return result


def _expected_dataclasses() -> set[str]:
    """imperal_sdk.__all__ entries that are dataclasses or pydantic models."""
    import imperal_sdk
    result: set[str] = set()
    for name in imperal_sdk.__all__:
        obj = getattr(imperal_sdk, name, None)
        if obj is None or not inspect.isclass(obj):
            continue
        if dataclasses.is_dataclass(obj) or hasattr(obj, "model_fields"):
            result.add(name)
    return result


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_sdk_reference_is_complete() -> None:
    """Every live public SDK symbol must be a key in sdk-reference.json.

    Fails if a new public symbol is added to any kind and the reference
    collectors (or this allowlist) are not updated.
    """
    committed = json.loads((REPO / "sdk-reference.json").read_text(encoding="utf-8"))
    ref_keys: set[str] = set(committed["symbols"].keys())

    failures: list[str] = []

    def _check(label: str, expected: set[str], exclusions: set[str]) -> None:
        missing = expected - exclusions - ref_keys
        if missing:
            for sym in sorted(missing):
                failures.append(f"{label}: {sym!r} is a live public symbol but has no key in sdk-reference.json")

    # 1. ui components
    _check(
        "ui_component",
        _expected_ui_components(),
        {k for k in REFERENCE_COVERAGE_EXCLUSIONS if k.startswith("ui.")},
    )

    # 2. sdl roles
    _check(
        "sdl_role",
        _expected_sdl_roles(),
        {k for k in REFERENCE_COVERAGE_EXCLUSIONS if k.startswith("sdl.")},
    )

    # 3. sdl funcs / modules
    _check(
        "sdl_func",
        _expected_sdl_funcs(),
        {k for k in REFERENCE_COVERAGE_EXCLUSIONS if k.startswith("sdl.")},
    )

    # 4. ctx client methods
    _check(
        "client_method",
        _expected_client_methods(),
        {k for k in REFERENCE_COVERAGE_EXCLUSIONS if k.startswith("ctx.")},
    )

    # 5. decorators
    _check(
        "decorator",
        _expected_decorators(),
        {k for k in REFERENCE_COVERAGE_EXCLUSIONS if k.startswith("ext.")
         or k.startswith("chat.")},
    )
    # ext.lifecycle is a property: verify the reference has it as degraded key
    assert "ext.lifecycle" in ref_keys, (
        "ext.lifecycle (property on Extension) must be a key in sdk-reference.json "
        "(recorded as degraded with note 'property, not a decorator method')"
    )
    # ext.on_refresh must NOT be in the reference (non-existent member removed)
    assert "ext.on_refresh" not in ref_keys, (
        "ext.on_refresh does not exist on Extension and must not be a key in "
        "sdk-reference.json — remove it from _EXT_DECORATORS in decorators.py"
    )

    # 6. dataclasses
    _check(
        "dataclass",
        _expected_dataclasses(),
        set(REFERENCE_COVERAGE_EXCLUSIONS.keys()),
    )

    if failures:
        bullet = "\n  ".join(failures)
        pytest.fail(
            f"sdk-reference.json is missing {len(failures)} live public symbol(s):\n"
            f"  {bullet}\n\n"
            "Fix: update the relevant reference collector in "
            "src/imperal_sdk/devtools/reference/ and regenerate:\n"
            "  python -m imperal_sdk.devtools.generate_reference "
            "--output sdk-reference.json\n"
            "OR add to REFERENCE_COVERAGE_EXCLUSIONS with a documented reason."
        )
