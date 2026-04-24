"""TaskStatus contract tests — shape required by long_running tool companion status probes."""
import pytest
from datetime import datetime
from imperal_sdk import TaskStatus


def test_task_status_minimal_fields():
    """Core fields required for any long_running task status probe."""
    status = TaskStatus(
        phase="entity_linking",
        percent=72,
        eta_seconds=280,
        human_label="глубокий форензический анализ Test Files",
        started_at=datetime(2026, 4, 24, 14, 30, 0),
    )
    assert status.phase == "entity_linking"
    assert status.percent == 72
    assert status.eta_seconds == 280
    assert status.completed_at is None
    assert status.error is None


def test_task_status_completed():
    status = TaskStatus(
        phase="completed",
        percent=100,
        eta_seconds=0,
        human_label="анализ завершён",
        started_at=datetime(2026, 4, 24, 14, 30, 0),
        completed_at=datetime(2026, 4, 24, 14, 45, 0),
    )
    assert status.completed_at is not None
    assert status.error is None


def test_task_status_failed():
    status = TaskStatus(
        phase="failed",
        percent=42,
        eta_seconds=0,
        human_label="анализ прерван",
        started_at=datetime(2026, 4, 24, 14, 30, 0),
        error="upstream_api_503",
    )
    assert status.error == "upstream_api_503"


def test_percent_out_of_range_rejected():
    with pytest.raises(ValueError):
        TaskStatus(
            phase="x", percent=150, eta_seconds=0,
            human_label="x", started_at=datetime.now(),
        )
    with pytest.raises(ValueError):
        TaskStatus(
            phase="x", percent=-1, eta_seconds=0,
            human_label="x", started_at=datetime.now(),
        )


def test_human_label_non_empty():
    with pytest.raises(ValueError):
        TaskStatus(
            phase="x", percent=50, eta_seconds=0,
            human_label="", started_at=datetime.now(),
        )
