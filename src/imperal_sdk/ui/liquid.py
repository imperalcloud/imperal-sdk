# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""ICNLI Liquid Intent UI — Adaptive, Surface-Agnostic Morphing Interfaces.

Part of the ICNLI protocol foundation for Imperal Cloud OS.
Instead of designing static screens (buttons, layouts, forms), developers declare
the semantic state of an intention, its affordances, cognitive context, and urgency.
The platform's Projector automatically morphs this intent into the optimal representation
across all connected surfaces:
- Terminal (PTY ANSI / TUI key-driven blocks)
- Web Panel (Topological graph, rich tables, interactive cards)
- Telegram (Urgent action cards, confirmation gates, inline buttons)
- Ambient / Voice (Spoken essence, hands-free consent)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union, Literal
from dataclasses import dataclass, field
from imperal_sdk.ui.base import UINode, _serialize

UrgencyLevel = Literal["low", "normal", "elevated", "critical"]
RiskLevel = Literal["read", "write", "destructive"]
AttentionBudget = Literal["glance", "focused", "investigative"]
SurfaceKind = Literal["terminal", "panel", "telegram", "ambient", "auto"]


@dataclass
class Affordance:
    """A semantic action that can be performed on the current intent state."""

    id: str
    label: str
    description: str = ""
    primary: bool = False
    risk: RiskLevel = "read"
    requires_confirmation: bool = False
    shortcut: Optional[str] = None  # e.g. "Enter", "y", "Esc"
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "primary": self.primary,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "shortcut": self.shortcut,
            "payload": self.payload,
        }


@dataclass
class CognitiveContext:
    """The situational context and psychological/operational posture of the user."""

    situation: str = "general"  # e.g. "incident_response", "code_review", "billing_alert"
    urgency: UrgencyLevel = "normal"
    attention_budget: AttentionBudget = "focused"
    modality_hint: Optional[str] = None  # e.g. "keyboard_primary", "touch_mobile", "desktop_mouse"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "situation": self.situation,
            "urgency": self.urgency,
            "attention_budget": self.attention_budget,
            "modality_hint": self.modality_hint,
        }


class MorphingState(UINode):
    """Declarative Liquid Intent State that morphs according to surface and context.

    Developers return this from SDK tools or handlers. The ICNLI surface projector
    collapses or expands this state into the ideal UI form factor.
    """

    def __init__(
        self,
        context: str,
        summary: str,
        urgency: UrgencyLevel = "normal",
        risk: RiskLevel = "read",
        details: Optional[str] = None,
        affected_entities: Optional[List[str]] = None,
        metrics: Optional[Dict[str, Union[int, float, str]]] = None,
        affordances: Optional[List[Union[Affordance, Dict[str, Any]]]] = None,
        cognitive: Optional[Union[CognitiveContext, Dict[str, Any]]] = None,
        projection_hints: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ):
        norm_affordances: List[Dict[str, Any]] = []
        for aff in (affordances or []):
            if isinstance(aff, Affordance):
                norm_affordances.append(aff.to_dict())
            elif isinstance(aff, dict):
                norm_affordances.append(dict(aff))

        norm_cognitive = cognitive.to_dict() if isinstance(cognitive, CognitiveContext) else (cognitive or {})

        props = {
            "context": context,
            "summary": summary,
            "urgency": urgency,
            "risk": risk,
            "details": details or "",
            "affected_entities": list(affected_entities or []),
            "metrics": dict(metrics or {}),
            "affordances": norm_affordances,
            "cognitive": norm_cognitive,
            "projection_hints": dict(projection_hints or {}),
        }
        props.update(kwargs)
        super().__init__(type="MorphingState", props=props)

    @property
    def context(self) -> str:
        return self.props.get("context", "")

    @property
    def summary(self) -> str:
        return self.props.get("summary", "")

    @property
    def urgency(self) -> UrgencyLevel:
        return self.props.get("urgency", "normal")

    @property
    def risk(self) -> RiskLevel:
        return self.props.get("risk", "read")

    @property
    def details(self) -> str:
        return self.props.get("details", "")

    @property
    def affected_entities(self) -> List[str]:
        return self.props.get("affected_entities", [])

    @property
    def metrics(self) -> Dict[str, Any]:
        return self.props.get("metrics", {})

    @property
    def affordances(self) -> List[Dict[str, Any]]:
        return self.props.get("affordances", [])

    @property
    def cognitive(self) -> Dict[str, Any]:
        return self.props.get("cognitive", {})

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to standard JSON-compatible dict."""
        res = super().to_dict()
        # Merge top-level conveniences matching ICNLI component wire contracts
        res.update({
            "component": "MorphingState",
            "context": self.context,
            "summary": self.summary,
            "urgency": self.urgency,
            "risk": self.risk,
            "details": self.details,
            "affected_entities": self.affected_entities,
            "metrics": self.metrics,
            "affordances": self.affordances,
            "cognitive": self.cognitive,
        })
        return res

    def project_for_surface(self, surface: SurfaceKind) -> Dict[str, Any]:
        """Synthesize a surface-optimized projection payload."""
        base = self.to_dict()
        if surface == "telegram":
            # Compact action card with high-priority affordances
            return {
                "surface": "telegram",
                "format": "action_card",
                "headline": f"{'🚨 ' if self.urgency == 'critical' else 'ℹ️ '}{self.summary}",
                "body": self.details or f"Entities: {', '.join(self.affected_entities[:3])}",
                "buttons": [
                    {"id": a["id"], "text": a["label"], "style": "danger" if a.get("risk") == "destructive" else "primary"}
                    for a in self.affordances[:4]
                ],
            }
        elif surface == "terminal":
            # TUI block with numbered shortcuts
            return {
                "surface": "terminal",
                "format": "tui_block",
                "urgency": self.urgency,
                "summary": self.summary,
                "shortcuts": [
                    f"[{idx + 1}] {a['label']} ({a.get('shortcut') or (idx + 1)})"
                    for idx, a in enumerate(self.affordances)
                ],
            }
        elif surface == "panel":
            # Full topological / card layout
            return {
                "surface": "panel",
                "format": "rich_intent_card",
                "full_state": base,
            }
        return base
