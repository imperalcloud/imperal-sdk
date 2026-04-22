# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for api_surface generator — guards against silent SDK API erosion.

Ensures core methods never silently disappear from the public surface
(which would break the kernel linter + let phantom references slip in).
"""
from __future__ import annotations

from imperal_sdk.tools.generate_api_surface import generate_surface


CORE_STORE = {"get", "set", "delete", "query", "count", "list_users"}
# Note: list_users was added in Task 3 (GAP-A closure) — shipping here as
# part of 1.5.23; its presence in the surface confirms it's callable.


def test_store_has_core_methods():
    surface = generate_surface()
    missing = CORE_STORE - set(surface["store"])
    assert not missing, f"core store methods missing: {missing}"


def test_surface_is_deterministic():
    """Two consecutive generations must produce identical output."""
    assert generate_surface() == generate_surface()


def test_surface_methods_sorted():
    for ns, methods in generate_surface().items():
        assert methods == sorted(methods), f"{ns} not sorted"


def test_surface_excludes_private_methods():
    for ns, methods in generate_surface().items():
        for name in methods:
            assert not name.startswith("_"), f"private leaked: {ns}.{name}"


def test_surface_includes_core_namespaces():
    surface = generate_surface()
    # Must-have (hard deps for kernel linter)
    required = {"store", "config", "http"}
    assert required.issubset(set(surface.keys())), \
        f"missing core namespaces: {required - set(surface.keys())}"
