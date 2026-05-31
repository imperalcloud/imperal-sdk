# tests/test_sdl_facet_catalog.py
"""SDL Phase 2 — Catalog, Products & Inventory family facets."""
from __future__ import annotations

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.catalog import (
    Branded, Inventory, Bundle, ColorMaterial, ProductCompliance,
)


class ProductDoc(Entity, Branded, Inventory, ColorMaterial):
    pass


def test_catalog_facets_compose_and_are_optional():
    d = ProductDoc(id=1, title="x")
    assert d.brand is None
    assert d.in_stock is None
    assert d.color is None


def test_branded_accept_values():
    d = ProductDoc(
        id=1, title="x",
        brand="Acme", manufacturer="Acme Corp", model_name="Widget Pro",
        model_year=2026, country_of_origin="US",
    )
    assert d.brand == "Acme"
    assert d.manufacturer == "Acme Corp"
    assert d.model_year == 2026


def test_inventory_accept_values():
    d = ProductDoc(
        id=1, title="x",
        in_stock=True, availability="in_stock",
        low_stock_threshold=5, is_low_stock=False,
        backorderable=True, preorder=False,
    )
    assert d.in_stock is True
    assert d.availability == "in_stock"
    assert d.low_stock_threshold == 5


def test_color_material_accept_values():
    d = ProductDoc(
        id=1, title="x",
        color="Red", material_color_hex="#FF0000", material="Cotton",
        pattern="Solid", finish="Matte",
    )
    assert d.color == "Red"
    assert d.material_color_hex == "#FF0000"
    assert d.finish == "Matte"


def test_catalog_roles_present():
    roles = roles_of(ProductDoc)
    assert roles["brand"] == "catalog.brand"
    assert roles["manufacturer"] == "catalog.manufacturer"
    assert roles["in_stock"] == "catalog.in_stock"
    assert roles["availability"] == "catalog.availability"
    assert roles["color"] == "catalog.color"
    assert roles["material"] == "catalog.material"


def test_bundle_roles():
    class BundleDoc(Entity, Bundle):
        pass

    roles = roles_of(BundleDoc)
    assert roles["is_bundle"] == "catalog.is_bundle"
    assert roles["bundle_type"] == "catalog.bundle_type"


def test_product_compliance_roles():
    class ComplianceDoc(Entity, ProductCompliance):
        pass

    d = ComplianceDoc(
        id=1, title="x",
        certifications=["CE", "FCC"], hs_code="1234.56",
        age_restriction=18, restricted_regions=["US", "EU"],
        requires_prescription=False,
    )
    assert d.certifications == ["CE", "FCC"]
    assert d.age_restriction == 18

    roles = roles_of(ComplianceDoc)
    assert roles["certifications"] == "catalog.certifications"
    assert roles["hs_code"] == "catalog.hs_code"
    assert roles["age_restriction"] == "catalog.age_restriction"
    assert roles["requires_prescription"] == "catalog.requires_prescription"
