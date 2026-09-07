"""Imperal SDK · Spatial Workspace & Interactive Canvas Component.

Provides a 2D interactive canvas for spatial layout of services, micro-frontends,
nodes, and topology diagrams. Supports draggable nodes, animated edges,
real-time metrics (latency/throughput), and in-place agentic overlays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from .base import UINode, UIAction


@dataclass(slots=True)
class CanvasNode:
    """Individual node on the spatial canvas."""
    id: str
    title: str
    x: float = 0.0
    y: float = 0.0
    type: str = "service"  # 'service' | 'database' | 'worker' | 'gateway' | 'custom'
    status: str = "healthy"  # 'healthy' | 'warning' | 'error' | 'idle'
    metrics: dict[str, Any] = field(default_factory=dict)
    icon: str = ""
    on_click: UIAction | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "type": self.type,
            "status": self.status,
            "metrics": self.metrics,
            "icon": self.icon,
        }
        if self.on_click is not None:
            d["on_click"] = self.on_click.to_dict() if hasattr(self.on_click, "to_dict") else self.on_click
        return d


@dataclass(slots=True)
class CanvasEdge:
    """Directed connection between two canvas nodes."""
    from_node: str
    to_node: str
    protocol: str = ""
    status: str = "active"  # 'active' | 'congested' | 'failed'
    latency_ms: float | None = None
    animated: bool = True

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "from": self.from_node,
            "to": self.to_node,
            "protocol": self.protocol,
            "status": self.status,
            "animated": self.animated,
        }
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        return d


def Canvas(
    nodes: list[CanvasNode | dict],
    edges: list[CanvasEdge | dict] | None = None,
    *,
    height: int = 700,
    interactive: bool = True,
    show_minimap: bool = True,
    show_controls: bool = True,
    on_node_click: UIAction | None = None,
) -> UINode:
    """Create an interactive spatial workspace canvas."""
    serialized_nodes = [
        n.to_dict() if hasattr(n, "to_dict") else n for n in (nodes or [])
    ]
    serialized_edges = [
        e.to_dict() if hasattr(e, "to_dict") else e for e in (edges or [])
    ]
    props: dict[str, Any] = {
        "nodes": serialized_nodes,
        "edges": serialized_edges,
        "height": height,
        "interactive": interactive,
        "show_minimap": show_minimap,
        "show_controls": show_controls,
    }
    if on_node_click is not None:
        props["on_node_click"] = on_node_click
    return UINode(type="Canvas", props=props)
