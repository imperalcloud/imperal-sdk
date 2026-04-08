from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActionResult:
    """Universal return type for all @chat.function calls.

    Use factory methods .success() and .error() — do not construct directly.
    """
    status: str
    data: dict = field(default_factory=dict)
    summary: str = ""
    error: Optional[str] = None
    retryable: bool = False

    @staticmethod
    def success(data: dict, summary: str) -> 'ActionResult':
        return ActionResult(status="success", data=data, summary=summary, error=None, retryable=False)

    @staticmethod
    def error(error: str, retryable: bool = False) -> 'ActionResult':
        return ActionResult(status="error", data={}, summary="", error=error, retryable=retryable)

    def to_dict(self) -> dict:
        d = {"status": self.status, "data": self.data, "summary": self.summary}
        if self.error is not None:
            d["error"] = self.error
        if self.retryable:
            d["retryable"] = self.retryable
        return d

    @staticmethod
    def from_dict(d: dict) -> 'ActionResult':
        if d.get("status") == "error":
            return ActionResult.error(d.get("error", "Unknown error"), d.get("retryable", False))
        return ActionResult.success(d.get("data", {}), d.get("summary", ""))
