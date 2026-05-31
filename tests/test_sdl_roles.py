# tests/test_sdl_roles.py
"""SDL Phase 1 — role grammar + reserved-namespace registry."""
from __future__ import annotations

import pytest

from imperal_sdk.sdl.roles import (
    is_valid_role, namespace_of, validate_custom_role,
    RoleError, RESERVED_NAMESPACES, CORE_ROLES,
)


@pytest.mark.parametrize("role", ["core.title", "audio.bpm", "time.start_at", "x.y_z2"])
def test_valid_roles(role):
    assert is_valid_role(role) is True


@pytest.mark.parametrize("role", ["", "Core.Title", "single", "a..b", "a.", ".b", "a.B", "1a.b", "a.b\n", "a.b\nc.d"])
def test_invalid_roles(role):
    assert is_valid_role(role) is False


def test_namespace_of():
    assert namespace_of("audio.bpm") == "audio"
    assert namespace_of("time.start_at") == "time"


def test_validate_custom_role_ok():
    assert validate_custom_role("audio.bpm") is None  # valid custom role → no raise, returns None


def test_validate_custom_role_rejects_reserved_namespace():
    with pytest.raises(RoleError):
        validate_custom_role("core.title")
    with pytest.raises(RoleError):
        validate_custom_role("time.start_at")


def test_validate_custom_role_rejects_malformed():
    with pytest.raises(RoleError):
        validate_custom_role("NotARole")


def test_reserved_namespaces_cover_core():
    assert "core" in RESERVED_NAMESPACES
    assert {"time", "people", "content", "money", "geo", "net", "metric"} <= RESERVED_NAMESPACES


def test_core_roles_present_and_valid():
    assert CORE_ROLES["title"] == "core.title"
    assert CORE_ROLES["id"] == "core.id"
    for role in CORE_ROLES.values():
        assert is_valid_role(role)
        assert namespace_of(role) == "core"
