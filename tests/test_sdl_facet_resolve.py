# tests/test_sdl_facet_resolve.py
"""SDL Phase C — resolve_facets: by-name facet resolution to field/role map."""
from __future__ import annotations

import pytest
from imperal_sdk.sdl.facet_resolve import resolve_facets


def test_resolve_known_facet_returns_field_roles():
    # "Invoiced" is a real facet in imperal_sdk.sdl.facets (money family).
    # Its roles include 'money.total', 'money.tax', etc. — all dotted.
    roles = resolve_facets(["Invoiced"])
    assert isinstance(roles, dict) and roles
    assert all("." in r for r in roles.values())  # roles are dotted, e.g. "money.total"


def test_resolve_multiple_facets_merges_fields():
    # Monetary + Invoiced together should yield a superset of both role maps.
    single = resolve_facets(["Invoiced"])
    merged = resolve_facets(["Monetary", "Invoiced"])
    # merged must contain at least all keys from single
    assert single.items() <= merged.items()
    # merged must have more keys (Monetary adds its own fields)
    assert len(merged) > len(single)


def test_unknown_facet_name_raises():
    with pytest.raises(KeyError):
        resolve_facets(["NoSuchFacetXYZ"])


def test_empty_list_returns_empty_dict():
    assert resolve_facets([]) == {}
