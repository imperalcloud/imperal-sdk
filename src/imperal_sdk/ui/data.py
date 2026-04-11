"""Imperal SDK · Data Display UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


def Badge(label: str = "", value: Any = None, color: str = "gray") -> UINode:
    """Colored badge/pill."""
    return UINode(type="Badge", props={"label": label, "value": value, "color": color})


def Avatar(fallback: str = "?", src: str = "", size: str = "md") -> UINode:
    """Avatar with image or fallback initial."""
    return UINode(type="Avatar", props={"fallback": fallback, "src": src, "size": size})


def Stat(label: str, value: Any, trend: str = "", icon: str = "", color: str = "blue") -> UINode:
    """Metric card — label + value + optional trend."""
    return UINode(type="Stat", props={"label": label, "value": value, "trend": trend, "icon": icon, "color": color})


def ListItem(
    id: str,
    title: str,
    subtitle: str = "",
    meta: str = "",
    avatar: UINode | None = None,
    badge: UINode | None = None,
    selected: bool = False,
    on_click: UIAction | None = None,
    actions: list[dict] | None = None,
) -> UINode:
    """Single list entry — used inside List.

    actions: hover actions, e.g. [{"icon": "Trash2", "on_click": Call(...), "confirm": "Delete?"}]
    """
    props: dict[str, Any] = {"id": id, "title": title}
    if subtitle: props["subtitle"] = subtitle
    if meta: props["meta"] = meta
    if avatar: props["avatar"] = avatar
    if badge: props["badge"] = badge
    if selected: props["selected"] = selected
    if on_click: props["on_click"] = on_click
    if actions: props["actions"] = actions
    return UINode(type="ListItem", props=props)


def List(items: list[UINode], searchable: bool = False, grouped_by: str = "", page_size: int = 0) -> UINode:
    """Scrollable list of ListItems. Searchable + auto-paginated.

    page_size: items per page. 0 = no pagination (show all).
    """
    props: dict[str, Any] = {"items": items, "searchable": searchable, "grouped_by": grouped_by}
    if page_size > 0: props["page_size"] = page_size
    return UINode(type="List", props=props)


def DataColumn(key: str, label: str, sortable: bool = True, width: str = "") -> dict:
    """Column definition for DataTable. Returns plain dict (not UINode)."""
    col: dict = {"key": key, "label": label, "sortable": sortable}
    if width: col["width"] = width
    return col


def DataTable(columns: list[dict], rows: list[dict], on_row_click: UIAction | None = None) -> UINode:
    """Sortable data table."""
    props: dict[str, Any] = {"columns": columns, "rows": rows}
    if on_row_click: props["on_row_click"] = on_row_click
    return UINode(type="DataTable", props=props)


def Stats(children: list[UINode], columns: int = 0) -> UINode:
    """Horizontal grid of Stat cards. columns=0 means auto."""
    props: dict[str, Any] = {"children": children}
    if columns > 0: props["columns"] = columns
    return UINode(type="Stats", props=props)


def Timeline(items: list[dict]) -> UINode:
    """Vertical timeline. Each item: {"title", "description", "time", "icon", "color"}."""
    return UINode(type="Timeline", props={"items": items})


def Tree(nodes: list[dict]) -> UINode:
    """Hierarchical tree view. Each node: {"id", "label", "children": [...], "icon"}."""
    return UINode(type="Tree", props={"nodes": nodes})


def KeyValue(items: list[dict], columns: int = 1) -> UINode:
    """Key-value pairs grid. Each item: {"key", "value"}."""
    return UINode(type="KeyValue", props={"items": items, "columns": columns})
