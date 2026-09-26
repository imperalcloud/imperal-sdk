# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the Apache License, Version 2.0.
"""ICNLI Fluid Terminal Canvas — Ephemeral Stage Primitive (v6.1.0).

Represents an ephemeral, interactive UI stage rendered dynamically
within the neo-terminal chat stream. Evaporates into a deterministic terminal
audit receipt when conversational context shifts or execution completes.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union

from imperal_sdk.ui.base import UINode, _serialize


class Stage(UINode):
    """Ephemeral Generative Stage component.

    Attributes:
        id: Unique stage identifier (e.g. 'cluster-telemetry-hud').
        title: Human-readable stage title for the HUD header.
        content: The Declarative UI tree mounted inside the stage (Grid, Stack, Card, etc.).
        hotkeys: Mapping of keyboard keys to action triggers (e.g. {'1': 'flush_cache'}).
        receipt: Terminal audit string or formatter callable executed upon evaporation.
        telemetry: Optional live metric indicators displayed in the stage header bar.
        auto_collapse: Whether to automatically collapse the stage when new input arrives.
    """

    def __init__(
        self,
        id: str,
        title: str,
        content: Optional[Union[UINode, List[UINode]]] = None,
        hotkeys: Optional[Dict[str, Union[str, Dict[str, Any]]]] = None,
        receipt: Optional[Union[str, Callable[[Any], str]]] = None,
        telemetry: Optional[Dict[str, Any]] = None,
        auto_collapse: bool = True,
        command: Optional[str] = None,
        status: str = "active",
        **extra_props: Any,
    ) -> None:
        children: List[UINode] = []
        if content is not None:
            if isinstance(content, list):
                children = content
            else:
                children = [content]

        props: Dict[str, Any] = {
            "id": id,
            "title": title,
            "command": command or id,
            "hotkeys": hotkeys or {},
            "auto_collapse": auto_collapse,
            "status": status,
            "telemetry": telemetry or {},
            "children": children,
            **extra_props,
        }

        self.type = "Stage"
        self.props = props
        self._children = children
        self._receipt_template = receipt

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["children"] = [_serialize(c) for c in self._children]
        return d

    def generate_receipt(
        self,
        result: Optional[Any] = None,
        delta: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> str:
        """Synthesize the collapsed terminal audit receipt string."""
        if callable(self._receipt_template):
            try:
                return self._receipt_template(result)
            except Exception:
                pass
        elif isinstance(self._receipt_template, str) and self._receipt_template:
            return self._receipt_template

        cmd = self.props.get("command", self.props.get("id", "stage"))
        title = self.props.get("title", "")
        summary = delta or title
        dur = f"{duration_ms}ms" if duration_ms is not None else "OK"
        return f"❯ {cmd}: {summary} ── [{dur}] ✓"
