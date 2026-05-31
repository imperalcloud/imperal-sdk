# tests/test_sdl_facet_security.py
"""SDL Phase 2 — Security & Compliance family facets."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from imperal_sdk.sdl.entity import Entity, Ref, roles_of
from imperal_sdk.sdl.facets.security import (
    AccessLeveled,
    Permissioned,
    Auditable,
    Consented,
    Compliant,
    Attested,
    Signed,
    Retained,
    Alertable,
    Caseable,
    RiskScored,
)


class SecDoc(Entity, AccessLeveled, Permissioned, Auditable):
    pass


class SecDoc2(Entity, Consented, Compliant, Attested):
    pass


class SecDoc3(Entity, Signed, Retained, Alertable, Caseable, RiskScored):
    pass


def test_security_facets_compose_and_are_optional():
    d = SecDoc(id=1, title="x")
    assert d.classification is None
    assert d.access_visibility is None
    assert d.sec_permissions is None
    assert d.audit_target is None


def test_security_facets_accept_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = SecDoc(
        id=1, title="x",
        classification="confidential",
        access_visibility="team",
        sec_permissions=["read", "write"],
        can_read=True,
        can_write=True,
        can_delete=False,
        action="document.update",
        occurred_at=now,
        outcome="success",
    )
    assert d.classification == "confidential"
    assert d.access_visibility == "team"
    assert d.sec_permissions == ["read", "write"]
    assert d.can_delete is False
    assert d.outcome == "success"


def test_security_roles_present():
    roles = roles_of(SecDoc)
    assert roles["classification"] == "sec.classification"
    assert roles["access_visibility"] == "sec.visibility"
    assert roles["sec_permissions"] == "sec.permissions"
    assert roles["can_read"] == "sec.can_read"
    assert roles["audit_target"] == "sec.target"
    assert roles["occurred_at"] == "sec.occurred_at"
    assert roles["outcome"] == "sec.outcome"


def test_consented_compliant_attested():
    d = SecDoc2(id=1, title="x", consent_state="granted", compliance_status="compliant",
                attestation_result="verified", attestation_confidence=Decimal("0.99"))
    assert d.consent_state == "granted"
    assert d.compliance_status == "compliant"
    assert d.attestation_confidence == Decimal("0.99")
    roles = roles_of(SecDoc2)
    assert roles["consent_state"] == "sec.consent_state"
    assert roles["compliance_status"] == "sec.compliance_status"
    assert roles["attestation_confidence"] == "sec.attestation_confidence"


def test_signed_retained_alertable_caseable_riskscored():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = SecDoc3(
        id=1, title="x",
        signature_is_valid=True,
        sec_retain_until=now,
        legal_hold=False,
        alert_severity="warning",
        alert_threshold=0.8,
        case_resolution="resolved",
        risk_score=0.3,
        risk_level="low",
    )
    assert d.signature_is_valid is True
    assert d.sec_retain_until == now
    assert d.alert_severity == "warning"
    assert d.alert_threshold == 0.8
    assert d.case_resolution == "resolved"
    assert d.risk_score == 0.3
    roles = roles_of(SecDoc3)
    assert roles["signature_is_valid"] == "sec.signature_is_valid"
    assert roles["sec_retain_until"] == "sec.retain_until"
    assert roles["alert_severity"] == "sec.alert_severity"
    assert roles["alert_threshold"] == "sec.alert_threshold"
    assert roles["case_resolution"] == "sec.case_resolution"
    assert roles["risk_score"] == "sec.risk_score"
