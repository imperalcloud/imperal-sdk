"""Imperal SDK · Layout UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode


def Stack(
    children: list[UINode],
    direction: str = "v",
    gap: int = 3,
    wrap: bool = False,
    align: str = "",
    justify: str = "",
) -> UINode:
    """Flex layout — vertical or horizontal. wrap: flex-wrap. align/justify: flex alignment."""
    props: dict[str, Any] = {"children": children, "direction": direction, "gap": gap}
    if wrap: props["wrap"] = True
    if align: props["align"] = align
    if justify: props["justify"] = justify
    return UINode(type="Stack", props=props)


def Grid(children: list[UINode], columns: int = 2, gap: int = 3) -> UINode:
    """CSS Grid layout."""
    return UINode(type="Grid", props={"children": children, "columns": columns, "gap": gap})


def Tabs(tabs: list[dict], default_tab: int = 0) -> UINode:
    """Tabbed content. Each tab: {"label": str, "content": UINode}."""
    return UINode(type="Tabs", props={"tabs": tabs, "default_tab": default_tab})


def Page(children: list[UINode], title: str = "", subtitle: str = "") -> UINode:
    """Top-level page container."""
    props: dict[str, Any] = {"children": children}
    if title: props["title"] = title
    if subtitle: props["subtitle"] = subtitle
    return UINode(type="Page", props=props)


def Section(children: list[UINode], title: str = "", collapsible: bool = False) -> UINode:
    """Grouped section with optional title and collapsible behaviour."""
    props: dict[str, Any] = {"children": children, "collapsible": collapsible}
    if title: props["title"] = title
    return UINode(type="Section", props=props)


def Row(children: list[UINode], gap: int = 3) -> UINode:
    """Horizontal flex row — alias for Stack(direction='h')."""
    return UINode(type="Stack", props={"children": children, "direction": "h", "gap": gap})


def Column(children: list[UINode], gap: int = 3) -> UINode:
    """Vertical flex column — alias for Stack(direction='v')."""
    return UINode(type="Stack", props={"children": children, "direction": "v", "gap": gap})


def Accordion(sections: list[dict], allow_multiple: bool = False) -> UINode:
    """Collapsible accordion. Each section: {"id", "title", "children"}."""
    return UINode(type="Accordion", props={"sections": sections, "allow_multiple": allow_multiple})
