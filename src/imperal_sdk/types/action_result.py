"""ActionResult[T] — universal return type for @chat.function.

Supports both plain dict (backward compat) and Pydantic BaseModel (typed path).
Use factory methods .success() and .error() — do not construct directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class ActionResult(Generic[T]):
    """Universal return type for @chat.function handlers.

    Generic over T (Pydantic BaseModel). When T is not specified,
    data is treated as plain dict for backward compatibility.

    NOTE: Always use factory methods .success() / .error(), or pass all kwargs
    explicitly when constructing directly. The @staticmethod 'error' shadows
    the field default — omitting error= in the constructor returns the method.
    """

    status: str
    data: T | dict = field(default_factory=dict)
    summary: str = ""
    error: str | None = None
    retryable: bool = False

    @staticmethod
    def success(data: T | dict, summary: str) -> ActionResult[T]:
        """Create a success result."""
        return ActionResult(status="success", data=data, summary=summary, error=None, retryable=False)

    @staticmethod
    def error(error: str, retryable: bool = False) -> ActionResult:
        """Create an error result."""
        return ActionResult(status="error", data={}, summary="", error=error, retryable=retryable)

    def to_dict(self) -> dict:
        """Serialize to dict. Pydantic models are converted via model_dump()."""
        d: dict = {"status": self.status, "summary": self.summary}
        if isinstance(self.data, BaseModel):
            d["data"] = self.data.model_dump()
        else:
            d["data"] = self.data
        # Guard: error might be the staticmethod if constructed without explicit error=
        err = self.error
        if err is not None and isinstance(err, str):
            d["error"] = err
        if self.retryable:
            d["retryable"] = self.retryable
        return d

    @staticmethod
    def from_dict(d: dict) -> ActionResult:
        """Deserialize from dict. Data remains as plain dict."""
        return ActionResult(
            status=d.get("status", "error"),
            data=d.get("data", {}),
            summary=d.get("summary", ""),
            error=d.get("error", None),
            retryable=d.get("retryable", False),
        )
