"""Imperal SDK · All 15 Declarative UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


# ─── Layout ───────────────────────────────────────────────────────────── #

def Stack(children: list[UINode], direction: str = "v", gap: int = 3) -> UINode:
    """Flex layout — vertical or horizontal."""
    return UINode(type="Stack", props={"children": children, "direction": direction, "gap": gap})


def Grid(children: list[UINode], columns: int = 2, gap: int = 3) -> UINode:
    """CSS Grid layout."""
    return UINode(type="Grid", props={"children": children, "columns": columns, "gap": gap})


def Tabs(tabs: list[dict], default_tab: int = 0) -> UINode:
    """Tabbed content. Each tab: {"label": str, "content": UINode}."""
    return UINode(type="Tabs", props={"tabs": tabs, "default_tab": default_tab})


# ─── Data Display ─────────────────────────────────────────────────────── #

def Text(content: str, variant: str = "body") -> UINode:
    """Text block. variant: heading/body/caption/code."""
    return UINode(type="Text", props={"content": content, "variant": variant})


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


def Column(key: str, label: str, sortable: bool = True, width: str = "") -> dict:
    """Column definition for DataTable. Returns plain dict (not UINode)."""
    col: dict = {"key": key, "label": label, "sortable": sortable}
    if width: col["width"] = width
    return col


def DataTable(columns: list[dict], rows: list[dict], on_row_click: UIAction | None = None) -> UINode:
    """Sortable data table."""
    props: dict[str, Any] = {"columns": columns, "rows": rows}
    if on_row_click: props["on_row_click"] = on_row_click
    return UINode(type="DataTable", props=props)


# ─── Interactive ──────────────────────────────────────────────────────── #

def Button(label: str, variant: str = "primary", on_click: UIAction | None = None, disabled: bool = False) -> UINode:
    """Clickable button."""
    props: dict[str, Any] = {"label": label, "variant": variant, "disabled": disabled}
    if on_click: props["on_click"] = on_click
    return UINode(type="Button", props=props)


def Icon(name: str, size: int = 16, color: str = "") -> UINode:
    """Lucide icon by name."""
    return UINode(type="Icon", props={"name": name, "size": size, "color": color})


def Card(title: str = "", subtitle: str = "", content: UINode | None = None,
         footer: UINode | None = None, on_click: UIAction | None = None) -> UINode:
    """Container card with optional slots."""
    props: dict[str, Any] = {}
    if title: props["title"] = title
    if subtitle: props["subtitle"] = subtitle
    if content: props["content"] = content
    if footer: props["footer"] = footer
    if on_click: props["on_click"] = on_click
    return UINode(type="Card", props=props)


# ─── Feedback ─────────────────────────────────────────────────────────── #

def Alert(message: str, title: str = "", type: str = "info") -> UINode:
    """Alert banner — info/success/warn/error."""
    return UINode(type="Alert", props={"message": message, "title": title, "type": type})


def Progress(value: int, label: str = "", variant: str = "bar") -> UINode:
    """Progress bar or circular indicator. value: 0-100."""
    return UINode(type="Progress", props={"value": value, "label": label, "variant": variant})


def Chart(data: list[dict], type: str = "line", x_key: str = "name", height: int = 200) -> UINode:
    """Chart — line/bar/pie using Recharts."""
    return UINode(type="Chart", props={"chart_type": type, "data": data, "x_key": x_key, "height": height})


# ─── Input ────────────────────────────────────────────────────────────── #

def Input(placeholder: str = "", on_submit: "UIAction | None" = None,
          value: str = "", param_name: str = "value") -> UINode:
    """Text input field. on_submit fires on Enter, input value merged as param_name."""
    props: dict[str, Any] = {"placeholder": placeholder, "value": value, "param_name": param_name}
    if on_submit: props["on_submit"] = on_submit
    return UINode(type="Input", props=props)
