# tests/test_sdl_facet_quantity.py
"""SDL Phase 2 — Quantities & Units family facets."""
from __future__ import annotations

from decimal import Decimal

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.quantity import (
    Measured, Range, Dimensions3D, Area, Angle, Bitrate, DataSize,
    Temperature, Length, Weight, Speed, Percentage,
)


class MeasuredDoc(Entity, Measured, Range):
    pass


def test_quantity_facets_compose_and_are_optional():
    d = MeasuredDoc(id=1, title="x")
    assert d.value is None
    assert d.unit is None
    assert d.min_value is None


def test_measured_accepts_decimal():
    d = MeasuredDoc(id=1, title="x", value=Decimal("42.5"), unit="kg", min_value=Decimal("0"), max_value=Decimal("100"))
    assert d.value == Decimal("42.5")
    assert d.unit == "kg"
    assert d.max_value == Decimal("100")


def test_measured_roles():
    roles = roles_of(MeasuredDoc)
    assert roles["value"] == "quantity.value"
    assert roles["unit"] == "quantity.unit"
    assert roles["min_value"] == "quantity.min_value"
    assert roles["max_value"] == "quantity.max_value"


def test_dimensions3d_roles():
    class DimDoc(Entity, Dimensions3D):
        pass

    roles = roles_of(DimDoc)
    assert roles["dim_width"] == "quantity.dim_width"
    assert roles["dim_height"] == "quantity.dim_height"
    assert roles["dim_depth"] == "quantity.dim_depth"
    assert roles["dim_unit"] == "quantity.dim_unit"


def test_scalar_facets_roles():
    class PhysDoc(Entity, Temperature, Length, Weight, Speed, Percentage):
        pass

    roles = roles_of(PhysDoc)
    assert roles["temp_c"] == "quantity.temp_c"
    assert roles["length_m"] == "quantity.length_m"
    assert roles["weight_kg"] == "quantity.weight_kg"
    assert roles["speed_mps"] == "quantity.speed_mps"
    assert roles["percent"] == "quantity.percent"


def test_other_quantity_facets():
    class OtherDoc(Entity, Area, Angle, Bitrate, DataSize):
        pass

    roles = roles_of(OtherDoc)
    assert roles["area_m2"] == "quantity.area_m2"
    assert roles["angle_deg"] == "quantity.angle_deg"
    assert roles["bitrate_bps"] == "quantity.bitrate_bps"
    assert roles["bytes"] == "quantity.bytes"
