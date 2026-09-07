"""Imperal SDK · Reactive Signals.

Signals allow declarative UI components to bind directly to reactive state keys.
When an action, background workflow, or Webbee emits a signal update via
``ctx.signals.emit(key, value)``, the connected UI component updates in-place
without requiring a full panel re-render or page reload.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class UISignal:
    """A reactive state reference for Declarative UI component props."""
    key: str
    default: Any = None

    def to_dict(self) -> dict:
        return {
            "__type__": "signal",
            "key": self.key,
            "default": self.default,
        }


def Signal(key: str, default: Any = None) -> UISignal:
    """Bind a component prop to a reactive signal key.

    Example::
        ui.Badge(
            text=ui.Signal("deploy:status", default="idle"),
            color=ui.Signal("deploy:color", default="gray")
        )
    """
    return UISignal(key=str(key), default=default)
