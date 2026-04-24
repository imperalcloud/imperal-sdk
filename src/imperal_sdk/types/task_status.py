"""TaskStatus — Pydantic model for long_running tool status probes.

Every long_running=True tool MUST declare a companion status_tool that
returns this shape. Kernel's webbee.task_status built-in, active task
registry, and Narrator all consume this contract.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TaskStatus(BaseModel):
    """Status of a long-running background task.

    Fields:
        phase: short machine-readable phase name (e.g. "extraction",
            "entity_linking", "completed", "failed"). Extension-specific.
        percent: 0-100 progress indicator. Integer.
        eta_seconds: estimated seconds until completion. 0 if complete
            or failed.
        human_label: 1-120 char natural-language description for Narrator
            ("глубокий форензический анализ Test Files"). NOT phase name.
        started_at: UTC datetime task was dispatched.
        completed_at: UTC datetime task finished (success or fail).
            None while running.
        error: machine-readable error code if failed. None otherwise.
    """
    phase: str = Field(min_length=1, max_length=64)
    percent: int = Field(ge=0, le=100)
    eta_seconds: int = Field(ge=0)
    human_label: str = Field(min_length=1, max_length=120)
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = Field(default=None, max_length=256)

    @field_validator("phase")
    @classmethod
    def phase_no_whitespace(cls, v: str) -> str:
        if v != v.strip():
            raise ValueError("phase must not have leading/trailing whitespace")
        return v
