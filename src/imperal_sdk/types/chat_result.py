"""ChatResult and FunctionCall — typed returns from ChatExtension._handle().

Replaces raw dict returns. Provides to_dict()/from_dict() for kernel
serialization (Temporal activities expect dict).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from imperal_sdk.types.action_result import ActionResult


@dataclass
class FunctionCall:
    """Record of a single @chat.function invocation."""

    name: str
    params: dict
    action_type: str
    success: bool
    result: ActionResult | None = None
    intercepted: bool = False
    event: str = ""

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "params": self.params,
            "action_type": self.action_type,
            "success": self.success,
            "intercepted": self.intercepted,
            "event": self.event,
        }
        if self.result is not None:
            d["result"] = self.result.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> FunctionCall:
        from imperal_sdk.types.action_result import ActionResult

        result = None
        if d.get("result"):
            result = ActionResult.from_dict(d["result"])
        return FunctionCall(
            name=d.get("name", ""),
            params=d.get("params", {}),
            action_type=d.get("action_type", "read"),
            success=d.get("success", False),
            result=result,
            intercepted=d.get("intercepted", False),
            event=d.get("event", ""),
        )


@dataclass
class ChatResult:
    """Typed return from ChatExtension._handle(). Replaces ad-hoc dict."""

    response: str
    handled: bool = False
    functions_called: list[FunctionCall] = field(default_factory=list)
    had_successful_action: bool = False
    message_type: str = "text"
    action_meta: dict = field(default_factory=dict)
    intercepted: bool = False
    task_cancelled: bool = False

    def to_dict(self) -> dict:
        """Serialize to dict for kernel/Temporal transport."""
        return {
            "response": self.response,
            "_handled": self.handled,
            "_functions_called": [fc.to_dict() for fc in self.functions_called],
            "_had_successful_action": self.had_successful_action,
            "_message_type": self.message_type,
            "_action_meta": self.action_meta,
            "_intercepted": self.intercepted,
            "_task_cancelled": self.task_cancelled,
        }

    @staticmethod
    def from_dict(d: dict) -> ChatResult:
        """Deserialize from kernel dict format."""
        return ChatResult(
            response=d.get("response", ""),
            handled=d.get("_handled", False),
            functions_called=[
                FunctionCall.from_dict(fc) for fc in d.get("_functions_called", [])
            ],
            had_successful_action=d.get("_had_successful_action", False),
            message_type=d.get("_message_type", "text"),
            action_meta=d.get("_action_meta", {}),
            intercepted=d.get("_intercepted", False),
            task_cancelled=d.get("_task_cancelled", False),
        )
