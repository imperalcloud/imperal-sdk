# tests/test_sdl_facet_geo.py
"""SDL Phase 2 — Location & Geo family facets."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.geo import (
    Geolocated,
    PostalAddress,
    AdminRegion,
    BoundingBox,
    Geofence,
    Routed,
    Placed,
)


class Doc(Entity, Geolocated, PostalAddress):
    pass


def test_geo_facets_compose_and_are_optional():
    d = Doc(id=1, title="x")
    assert d.lat is None
    assert d.lon is None
    assert d.city is None


def test_geo_facets_accept_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = Doc(id=1, title="x", lat=51.5074, lon=-0.1278, city="London", country="GB", located_at=now)
    assert d.lat == 51.5074
    assert d.lon == -0.1278
    assert d.city == "London"
    assert d.located_at == now


def test_geo_roles_present():
    roles = roles_of(Doc)
    assert roles["lat"] == "geo.lat"
    assert roles["lon"] == "geo.lon"
    assert roles["city"] == "geo.city"
    assert roles["country"] == "geo.country"


def test_geolocated_speed_field_prefixed():
    # speed_mps in geo is geo_speed_mps to avoid clash with quantity.speed_mps
    d = Doc(id=1, title="x")
    assert d.geo_speed_mps is None
    roles = roles_of(Doc)
    assert roles["geo_speed_mps"] == "geo.speed_mps"


def test_admin_and_bounding_box_roles():
    class T(Entity, AdminRegion, BoundingBox):
        pass

    roles = roles_of(T)
    assert roles["country_code"] == "geo.country_code"
    assert roles["min_lat"] == "geo.min_lat"
    assert roles["max_lon"] == "geo.max_lon"


def test_geofence_routed_placed_roles():
    class T(Entity, Geofence, Routed, Placed):
        pass

    roles = roles_of(T)
    assert roles["center_lat"] == "geo.center_lat"
    assert roles["route_duration_s"] == "geo.route_duration_s"
    assert roles["place_name"] == "geo.place_name"
