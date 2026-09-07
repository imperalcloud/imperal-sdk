"""Imperal SDK · Cross-Extension Unix Piping.

Provides declarative pipe composition between tools and signals across extensions.
Allows chaining output of one tool/signal to the input of another.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass(slots=True)
class PipeStep:
    """Single stage in a pipe chain."""
    app_id: str
    tool_name: str
    params_template: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "tool_name": self.tool_name,
            "params_template": self.params_template,
        }


class ExtensionPipe:
    """A composable pipeline connecting extension tools via Unix-like pipe semantics."""

    def __init__(self, steps: list[PipeStep] | None = None):
        self.steps: list[PipeStep] = list(steps or [])

    def pipe(self, app_id: str, tool_name: str, **params_template) -> ExtensionPipe:
        """Append a downstream stage to the pipe."""
        self.steps.append(PipeStep(app_id=app_id, tool_name=tool_name, params_template=params_template))
        return self

    def __or__(self, other: tuple[str, str] | PipeStep) -> ExtensionPipe:
        """Unix pipe operator support: pipe | ('mailer', 'send_email')."""
        if isinstance(other, PipeStep):
            self.steps.append(other)
        elif isinstance(other, (tuple, list)) and len(other) == 2:
            self.steps.append(PipeStep(app_id=str(other[0]), tool_name=str(other[1])))
        else:
            raise ValueError("Pipe operand must be PipeStep or (app_id, tool_name) tuple")
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "extension_pipe",
            "steps": [s.to_dict() for s in self.steps],
        }


def Pipe(app_id: str, tool_name: str, **params_template) -> ExtensionPipe:
    """Construct an ExtensionPipe starting at app_id/tool_name."""
    return ExtensionPipe([PipeStep(app_id=app_id, tool_name=tool_name, params_template=params_template)])
