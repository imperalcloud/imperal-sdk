"""Imperal SDK · Feedback UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


def Alert(message: str, title: str = "", type: str = "info") -> UINode:
    """Alert banner — info/success/warn/error."""
    return UINode(type="Alert", props={"message": message, "title": title, "type": type})


def Progress(value: int, label: str = "", variant: str = "bar") -> UINode:
    """Progress bar or circular indicator. value: 0-100."""
    return UINode(type="Progress", props={"value": value, "label": label, "variant": variant})


def Chart(data: list[dict], type: str = "line", x_key: str = "name", height: int = 200) -> UINode:
    """Chart — line/bar/pie using Recharts."""
    return UINode(type="Chart", props={"chart_type": type, "data": data, "x_key": x_key, "height": height})


def Loading(message: str = "Loading...", variant: str = "spinner") -> UINode:
    """Loading state indicator. variant: spinner/skeleton/dots."""
    return UINode(type="Loading", props={"message": message, "variant": variant})


def Error(message: str, title: str = "Error", retry: UIAction | None = None) -> UINode:
    """Error state with optional retry action."""
    props: dict[str, Any] = {"message": message, "title": title}
    if retry: props["retry"] = retry
    return UINode(type="Error", props=props)
