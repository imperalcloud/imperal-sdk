# tests/test_sdl_facet_device.py
"""SDL Phase 2 — Devices & Health family facets."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.device import (
    DeviceIdentity,
    DeviceState,
    SensorReading,
    ActuatorState,
    Consumable,
    ActivityMetrics,
    BodyComposition,
    VitalSign,
    Biometric,
    SleepRecord,
    AIProvenance,
)


class DeviceDoc(Entity, DeviceIdentity, DeviceState, SensorReading):
    pass


class DeviceDoc2(Entity, ActuatorState, Consumable, ActivityMetrics):
    pass


class HealthDoc(Entity, BodyComposition, VitalSign, Biometric):
    pass


class HealthDoc2(Entity, SleepRecord, AIProvenance):
    pass


def test_device_facets_compose_and_are_optional():
    d = DeviceDoc(id=1, title="x")
    assert d.device_id is None
    assert d.device_model is None
    assert d.online is None
    assert d.device_last_seen_at is None
    assert d.sensor_value is None


def test_device_facets_accept_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = DeviceDoc(
        id=1, title="x",
        device_id="dev-abc-123",
        device_model="SensorPro 2000",
        device_manufacturer="AcmeCorp",
        firmware_version="1.2.3",
        online=True,
        battery_pct=85,
        device_last_seen_at=now,
        sensor_type="temperature",
        sensor_value=23.5,
        sensor_unit="celsius",
        measured_at=now,
    )
    assert d.device_id == "dev-abc-123"
    assert d.device_model == "SensorPro 2000"
    assert d.battery_pct == 85
    assert d.sensor_value == 23.5
    assert d.device_last_seen_at == now


def test_device_roles_present():
    roles = roles_of(DeviceDoc)
    assert roles["device_id"] == "device.device_id"
    assert roles["device_model"] == "device.device_model"
    assert roles["device_manufacturer"] == "device.device_manufacturer"
    assert roles["online"] == "device.online"
    assert roles["device_last_seen_at"] == "device.device_last_seen_at"
    assert roles["sensor_value"] == "device.sensor_value"
    assert roles["measured_at"] == "device.measured_at"


def test_actuator_consumable_activity():
    d = DeviceDoc2(
        id=1, title="x",
        on=True,
        level_pct=80,
        actuator_color_hex="#FF5500",
        actuator_position="open",
        steps=8500,
        activity_distance_m=6200.0,
        active_calories_kcal=420.5,
        consumable_type="filter",
        remaining_pct=30,
    )
    assert d.on is True
    assert d.actuator_color_hex == "#FF5500"
    assert d.actuator_position == "open"
    assert d.steps == 8500
    assert d.activity_distance_m == 6200.0
    roles = roles_of(DeviceDoc2)
    assert roles["on"] == "device.on"
    assert roles["actuator_color_hex"] == "device.actuator_color_hex"
    assert roles["actuator_position"] == "device.actuator_position"
    assert roles["steps"] == "device.steps"
    assert roles["activity_distance_m"] == "device.activity_distance_m"


def test_health_facets():
    d = HealthDoc(
        id=1, title="x",
        body_weight_kg=75.5,
        bmi=24.2,
        heart_rate_bpm=72,
        spo2_pct=98.5,
        biometric_type="cortisol",
        biometric_value=14.3,
        biometric_unit="mcg/dL",
    )
    assert d.body_weight_kg == 75.5
    assert d.heart_rate_bpm == 72
    assert d.biometric_type == "cortisol"
    roles = roles_of(HealthDoc)
    assert roles["body_weight_kg"] == "device.weight_kg"
    assert roles["heart_rate_bpm"] == "device.heart_rate_bpm"
    assert roles["biometric_type"] == "device.biometric_type"
    assert roles["biometric_value"] == "device.biometric_value"


def test_sleep_ai_provenance():
    d = HealthDoc2(
        id=1, title="x",
        sleep_duration_s=28800,
        sleep_quality_score=0.85,
        generated_by_ai=True,
        ai_model="claude-sonnet",
        ai_confidence=0.95,
    )
    assert d.sleep_duration_s == 28800
    assert d.generated_by_ai is True
    roles = roles_of(HealthDoc2)
    assert roles["sleep_duration_s"] == "device.sleep_duration_s"
    assert roles["sleep_quality_score"] == "device.sleep_quality_score"
    assert roles["generated_by_ai"] == "device.generated_by_ai"
    assert roles["ai_model"] == "device.ai_model"
