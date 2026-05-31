# tests/test_sdl_facet_metric.py
"""SDL Phase 2 — Analytics & Metrics family facets."""
from __future__ import annotations

from datetime import datetime

from imperal_sdk.sdl.entity import Entity, roles_of
from imperal_sdk.sdl.facets.metric import (
    Aggregated,
    TimeSeriesPoint,
    Trended,
    Confident,
    Threshold,
    Dimensioned,
)


class MetricDoc(Entity, Aggregated, TimeSeriesPoint, Trended):
    pass


class MetricDoc2(Entity, Confident, Threshold, Dimensioned):
    pass


def test_metric_facets_compose_and_are_optional():
    d = MetricDoc(id=1, title="x")
    assert d.aggregation is None
    assert d.ts_timestamp is None
    assert d.ts_value is None
    assert d.delta is None


def test_metric_facets_accept_values():
    now = datetime(2026, 5, 31, 12, 0, 0)
    d = MetricDoc(
        id=1, title="x",
        aggregation="sum",
        window_start=now,
        ts_value=42.5,
        delta=-1.2,
        trend="down",
        trend_period="7d",
    )
    assert d.aggregation == "sum"
    assert d.window_start == now
    assert d.ts_value == 42.5
    assert d.trend == "down"


def test_metric_roles_present():
    roles = roles_of(MetricDoc)
    assert roles["aggregation"] == "metric.aggregation"
    assert roles["ts_timestamp"] == "metric.ts_timestamp"
    assert roles["ts_value"] == "metric.ts_value"
    assert roles["delta"] == "metric.delta"
    assert roles["trend_period"] == "metric.trend_period"


def test_confident_threshold_dimensioned():
    d = MetricDoc2(id=1, title="x", confidence_level=0.95, threshold_target=100.0, breached=True)
    assert d.confidence_level == 0.95
    assert d.threshold_target == 100.0
    assert d.breached is True


def test_confident_threshold_dimensioned_roles():
    roles = roles_of(MetricDoc2)
    assert roles["confidence_level"] == "metric.confidence_level"
    assert roles["threshold_target"] == "metric.threshold_target"
    assert roles["threshold"] == "metric.threshold"
    assert roles["dimensions"] == "metric.dimensions"
