# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for ui.theme(ctx) accessor + dataclass shape."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from imperal_sdk import ui
from imperal_sdk.ui.theme import AgencyTheme, ColorPair, _from_dict


# ─── Defaults ────────────────────────────────────────────────────────────────

def test_theme_returns_defaults_when_ctx_is_none():
    t = ui.theme(None)
    assert isinstance(t, AgencyTheme)
    assert t.density == "default"
    assert t.radius == "default"
    assert t.colors == {}


def test_theme_returns_defaults_when_ctx_has_no_theme():
    class _Ctx:
        pass
    t = ui.theme(_Ctx())
    assert t.density == "default"
    assert t.colors == {}


def test_theme_returns_defaults_when_agency_theme_is_none():
    class _Ctx:
        agency_theme = None
    t = ui.theme(_Ctx())
    assert t.density == "default"


# ─── Parsing ─────────────────────────────────────────────────────────────────

def test_theme_reads_colors_density_radius_from_ctx():
    class _Ctx:
        agency_theme = {
            "colors": {"primary": {"light": "#003366", "dark": "#4a90e2"}},
            "density": "compact",
            "radius": "sharp",
        }
    t = ui.theme(_Ctx())
    assert t.density == "compact"
    assert t.radius == "sharp"
    assert "primary" in t.colors
    assert t.colors["primary"].light == "#003366"
    assert t.colors["primary"].dark == "#4a90e2"


def test_theme_silently_drops_malformed_color_pairs():
    class _Ctx:
        agency_theme = {
            "colors": {
                "primary": {"light": "#003366", "dark": "#4a90e2"},
                "broken":  {"light": "#abc"},        # missing dark — dropped
                "wrong":   "not-a-dict",             # not a dict — dropped
                "typed":   {"light": 1, "dark": 2},  # non-string — dropped
            },
        }
    t = ui.theme(_Ctx())
    assert set(t.colors.keys()) == {"primary"}


def test_theme_falls_back_on_unknown_density_and_radius():
    class _Ctx:
        agency_theme = {"density": "huge", "radius": "spiky"}
    t = ui.theme(_Ctx())
    assert t.density == "default"
    assert t.radius == "default"


def test_theme_handles_non_dict_agency_theme():
    class _Ctx:
        agency_theme = "not-a-dict"
    t = ui.theme(_Ctx())
    assert t == AgencyTheme()


# ─── Dataclass shape ─────────────────────────────────────────────────────────

def test_color_pair_is_frozen():
    cp = ColorPair(light="#fff", dark="#000")
    with pytest.raises(FrozenInstanceError):
        cp.light = "#abc"  # type: ignore[misc]


def test_agency_theme_is_frozen():
    t = AgencyTheme(density="compact")
    with pytest.raises(FrozenInstanceError):
        t.density = "spacious"  # type: ignore[misc]


def test_agency_theme_slots():
    # Slots means no per-instance __dict__ — memory footprint + layout win
    # on top of frozen immutability.
    cp = ColorPair(light="#fff", dark="#000")
    assert not hasattr(cp, "__dict__")


# ─── _from_dict internal helper ──────────────────────────────────────────────

def test_from_dict_empty_input():
    assert _from_dict(None) == AgencyTheme()
    assert _from_dict({}) == AgencyTheme()


def test_from_dict_full_payload():
    data = {
        "colors": {
            "primary":   {"light": "#003366", "dark": "#4a90e2"},
            "surface-0": {"light": "#ffffff", "dark": "#0a0a0a"},
        },
        "density": "spacious",
        "radius":  "rounded",
    }
    t = _from_dict(data)
    assert t.density == "spacious"
    assert t.radius == "rounded"
    assert len(t.colors) == 2


# ─── Public API surface ──────────────────────────────────────────────────────

def test_public_exports():
    assert callable(ui.theme)
    assert ui.AgencyTheme is AgencyTheme
    assert ui.ColorPair is ColorPair
