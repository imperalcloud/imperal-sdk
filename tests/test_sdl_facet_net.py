# tests/test_sdl_facet_net.py
"""SDL Phase 2 — Tech / Infra / Network / Data family facets."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.net import (
    NetAsset,
    ApiEndpoint,
    HostResource,
    ComputeSpec,
    Container,
    ServiceHealth,
    Certificated,
    DataRecord,
    ConfigSetting,
    Backup,
)


class Doc(Entity, NetAsset, ApiEndpoint):
    pass


def test_net_facets_compose_and_are_optional():
    d = Doc(id=1, title="x")
    assert d.domain is None
    assert d.ip is None
    assert d.method is None


def test_net_facets_accept_values():
    d = Doc(id=1, title="x", domain="example.com", ip="1.2.3.4", port=443, method="GET")
    assert d.domain == "example.com"
    assert d.ip == "1.2.3.4"
    assert d.port == 443
    assert d.method == "GET"


def test_net_roles_present():
    roles = roles_of(Doc)
    assert roles["domain"] == "net.domain"
    assert roles["ip"] == "net.ip"
    assert roles["method"] == "net.method"


def test_api_path_field_prefixed():
    # net.ApiEndpoint uses api_path (not path) to avoid clash with media.FileObject.path
    d = Doc(id=1, title="x")
    assert d.api_path is None
    roles = roles_of(Doc)
    assert roles["api_path"] == "net.path"


def test_host_and_compute_roles():
    class T(Entity, HostResource, ComputeSpec):
        pass

    roles = roles_of(T)
    assert roles["hostname"] == "net.hostname"
    assert roles["host_region"] == "net.host_region"
    assert roles["vcpus"] == "net.vcpus"
    assert roles["memory_bytes"] == "net.memory_bytes"


def test_container_and_health_roles():
    class T(Entity, Container, ServiceHealth):
        pass

    roles = roles_of(T)
    assert roles["container_id"] == "net.container_id"
    assert roles["health"] == "net.health"
    assert roles["uptime_s"] == "net.uptime_s"


def test_certificated_roles():
    class T(Entity, Certificated):
        pass

    roles = roles_of(T)
    assert roles["cert_issuer"] == "net.cert_issuer"
    assert roles["cert_subject"] == "net.cert_subject"
    assert roles["cert_is_valid"] == "net.cert_is_valid"


def test_config_value_type_prefixed():
    # net.ConfigSetting uses config_value_type (not value_type) to avoid clash with quantity.Measured.value_type
    class T(Entity, ConfigSetting):
        pass

    d = T(id=1, title="x")
    assert d.config_value_type is None
    roles = roles_of(T)
    assert roles["config_value_type"] == "net.value_type"
    assert roles["config_value"] == "net.config_value"


def test_backup_roles():
    class T(Entity, Backup):
        pass

    roles = roles_of(T)
    assert roles["backup_size_bytes"] == "net.backup_size_bytes"
    assert roles["backup_kind"] == "net.backup_kind"
