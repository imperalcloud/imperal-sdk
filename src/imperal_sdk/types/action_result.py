"""ActionResult[T] — universal return type for @chat.function.

Supports both plain dict (backward compat) and Pydantic BaseModel (typed path).
Use factory methods .success() and .error() — do not construct directly.
"""
from __future__ import annotations

from typing import Generic, TypeVar, overload

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_MISSING = object()


def _error_factory(error: str, retryable: bool = False) -> ActionResult:
    """Create an error result."""
    return ActionResult(status="error", error=error, retryable=retryable)


class _ErrorDescriptor:
    """Descriptor that dispatches to factory when called on class,
    and returns the error string when accessed on an instance."""

    def __get__(self, obj: ActionResult | None, objtype: type | None = None):
        if obj is None:
            # Class-level access: return the factory function so
            # ActionResult.error("msg") works.
            return _error_factory
        # Instance-level access: return the stored error string.
        return obj.__dict__.get("_error_val")


class ActionResult(Generic[T]):
    """Universal return type for @chat.function handlers.

    Generic over T (Pydantic BaseModel). When T is not specified,
    data is treated as plain dict for backward compatibility.
    """

    error = _ErrorDescriptor()

    def __init__(
        self,
        status: str,
        data: T | dict | None = None,
        summary: str = "",
        error: str | None = None,
        retryable: bool = False,
    ) -> None:
        self.status = status
        self.data: T | dict = data if data is not None else {}
        self.summary = summary
        self.__dict__["_error_val"] = error
        self.retryable = retryable

    @staticmethod
    def success(data: T | dict, summary: str) -> ActionResult[T]:
        """Create a success result."""
        return ActionResult(status="success", data=data, summary=summary)

    def to_dict(self) -> dict:
        """Serialize to dict. Pydantic models are converted via model_dump()."""
        d: dict = {"status": self.status, "summary": self.summary}
        if isinstance(self.data, BaseModel):
            d["data"] = self.data.model_dump()
        else:
            d["data"] = self.data
        error_val = self.__dict__.get("_error_val")
        if error_val is not None:
            d["error"] = error_val
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
            error=d.get("error"),
            retryable=d.get("retryable", False),
        )

    def __repr__(self) -> str:
        error_val = self.__dict__.get("_error_val")
        return (
            f"ActionResult(status={self.status!r}, data={self.data!r}, "
            f"summary={self.summary!r}, error={error_val!r}, "
            f"retryable={self.retryable!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ActionResult):
            return NotImplemented
        return (
            self.status == other.status
            and self.data == other.data
            and self.summary == other.summary
            and self.__dict__.get("_error_val") == other.__dict__.get("_error_val")
            and self.retryable == other.retryable
        )
