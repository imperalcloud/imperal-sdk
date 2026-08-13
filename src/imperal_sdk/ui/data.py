"""Imperal SDK · Data Display UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction

# The single source of truth for Stat trend arrows. "up" is NOT always good —
# rising spend is bad, rising revenue is good — so direction is stated
# explicitly by the caller and never inferred from the trend text.
STAT_TREND_DIRECTIONS = ("up", "down", "neutral")


def Badge(label: str = "", value: Any = None, color: str = "gray",
          size: str = "", dot: bool = False) -> UINode:
    """Colored badge/pill.

    size: 'sm' (default) | 'md' | 'lg'.
    dot: prefix a filled status dot in the same colour — for live/offline style
    state, where the colour IS the information and must not rely on text alone.
    """
    props: dict[str, Any] = {"label": label, "value": value, "color": color}
    if size:
        props["size"] = size
    if dot:
        props["dot"] = True
    return UINode(type="Badge", props=props)


def Avatar(fallback: str = "?", src: str = "", size: str = "md") -> UINode:
    """Avatar with image or fallback initial."""
    return UINode(type="Avatar", props={"fallback": fallback, "src": src, "size": size})


def Stat(
    label: str,
    value: Any,
    trend: str = "",
    icon: str = "",
    color: str = "blue",
    description: str = "",
    trend_direction: str = "",
) -> UINode:
    """Metric card — label + value + optional trend.

    color: semantic tint for the value (blue default, green, red, yellow,
    purple, gray). Use it to make a number mean something at a glance —
    money spent in red, healthy balance in green.

    trend_direction: 'up' | 'down' | 'neutral'. Drives the arrow and its
    colour independently of ``trend``'s text, because "up" is not always good:
    rising spend is bad, rising revenue is good. Defaults to neutral.

    description: one short line under the value for the caveat that would
    otherwise be lost — e.g. "excludes admin grants".
    """
    props: dict[str, Any] = {
        "label": label, "value": value, "trend": trend, "icon": icon, "color": color,
    }
    if description:
        props["description"] = description
    if trend_direction:
        if trend_direction not in STAT_TREND_DIRECTIONS:
            raise ValueError(
                f"ui.Stat trend_direction must be one of {STAT_TREND_DIRECTIONS}, "
                f"got {trend_direction!r}"
            )
        props["trend_direction"] = trend_direction
    return UINode(type="Stat", props=props)


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
    draggable: bool = False,
    droppable: bool = False,
    on_drop: UIAction | None = None,
    icon: str = "",
    expandable: bool = False,
    expanded_content: list[UINode] | None = None,
) -> UINode:
    """Single list entry — used inside List.

    actions: hover actions, e.g. [{"icon": "Trash2", "on_click": Call(...), "confirm": "Delete?"}]
    expandable: if True, clicking toggles expanded_content instead of firing on_click.
    expanded_content: list of UINodes rendered when expanded.
    """
    props: dict[str, Any] = {"id": id, "title": title}
    if subtitle: props["subtitle"] = subtitle
    if meta: props["meta"] = meta
    if avatar: props["avatar"] = avatar
    if badge: props["badge"] = badge
    if selected: props["selected"] = selected
    if on_click: props["on_click"] = on_click
    if actions: props["actions"] = actions
    if draggable: props["draggable"] = draggable
    if droppable: props["droppable"] = droppable
    if on_drop: props["on_drop"] = on_drop
    if icon: props["icon"] = icon
    if expandable: props["expandable"] = expandable
    if expanded_content: props["expanded_content"] = expanded_content
    return UINode(type="ListItem", props=props)


def List(
    items: list[UINode],
    searchable: bool = False,
    grouped_by: str = "",
    page_size: int = 0,
    on_end_reached: UIAction | None = None,
    selectable: bool = False,
    bulk_actions: list[dict] | None = None,
    total_items: int = 0,
    extra_info: str = "",
    title: str = "",
    empty_text: str = "",
    search_placeholder: str = "",
    max_height: int = 0,
) -> UINode:
    """Scrollable list of ListItems. Searchable + auto-paginated.

    page_size: items per page. 0 = no pagination (show all).
    on_end_reached: action fired when user scrolls to bottom (infinite scroll).
    selectable: enable multi-select with checkboxes on hover.
    bulk_actions: buttons for bulk operations. Each: {"label", "icon", "action": Call(...)}.
        Selected item IDs are injected as 'message_ids' param.
    total_items: total number of items across all pages (for Paginator display).
    extra_info: extra text in Paginator footer (e.g. "3 unread").
    title: header above the list.
    empty_text: what to show when there are no items. For a genuinely empty
        collection prefer ``ui.Empty(..., action=...)``, which can offer the way
        out instead of just stating the absence.
    search_placeholder: hint in the search box — name what is searched
        ("Search by email or id") rather than a bare "Search".
    max_height: pixel cap that makes the list scroll instead of the page.
    """
    props: dict[str, Any] = {"items": items, "searchable": searchable, "grouped_by": grouped_by}
    if page_size > 0: props["page_size"] = page_size
    if on_end_reached: props["on_end_reached"] = on_end_reached
    if selectable: props["selectable"] = selectable
    if bulk_actions: props["bulk_actions"] = bulk_actions
    if total_items > 0: props["total_items"] = total_items
    if extra_info: props["extra_info"] = extra_info
    if title: props["title"] = title
    if empty_text: props["empty_text"] = empty_text
    if search_placeholder: props["search_placeholder"] = search_placeholder
    if max_height: props["max_height"] = max_height
    return UINode(type="List", props=props)


def DataColumn(key: str, label: str, sortable: bool = True, width: str = "",
               editable: bool = False, edit_type: str = "text") -> dict:
    """Column definition for DataTable. Returns plain dict (not UINode).

    editable: enable inline cell editing for this column.
    edit_type: "text" for text input, "toggle" for boolean toggle.
    """
    col: dict = {"key": key, "label": label, "sortable": sortable}
    if width: col["width"] = width
    if editable: col["editable"] = editable; col["edit_type"] = edit_type
    return col


def DataTable(columns: list[dict], rows: list[dict],
              on_row_click: UIAction | None = None,
              on_cell_edit: UIAction | None = None,
              empty_text: str = "",
              max_height: int = 0,
              sticky_header: bool = False) -> UINode:
    """Sortable data table with optional inline cell editing.

    Pair ``DataColumn(editable=True, edit_type=...)`` with ``on_cell_edit`` to
    get BULK edits without opening each row: the action fires per committed
    cell with the row id and the new value. Without ``on_cell_edit`` an
    ``editable`` column stays read-only — the renderer refuses to offer an
    edit affordance it cannot deliver.

    empty_text: what to say when ``rows`` is empty. Say what is actually empty
    ("No refunds in this period"), never a bare "No data".
    max_height: pixel cap that makes the body scroll instead of the page.
    sticky_header: keep the header row visible while the body scrolls — pair it
    with ``max_height`` for long tables, otherwise column meaning scrolls away.
    """
    props: dict[str, Any] = {"columns": columns, "rows": rows}
    if on_row_click: props["on_row_click"] = on_row_click
    if on_cell_edit: props["on_cell_edit"] = on_cell_edit
    if empty_text: props["empty_text"] = empty_text
    if max_height: props["max_height"] = max_height
    if sticky_header: props["sticky_header"] = True
    return UINode(type="DataTable", props=props)


def Stats(children: list[UINode], columns: int = 0) -> UINode:
    """Horizontal grid of Stat cards. columns=0 means auto."""
    props: dict[str, Any] = {"children": children}
    if columns > 0: props["columns"] = columns
    return UINode(type="Stats", props=props)


def Timeline(items: list[dict]) -> UINode:
    """Vertical timeline — the canonical AUDIT TRAIL / history primitive.

    Each item: ``{"title", "description", "time", "icon", "color"}``.

    * ``title`` — what happened (required in practice; the only line always shown)
    * ``description`` — the detail: who did it, what changed
    * ``time`` — when, as a preformatted string. The renderer prints it verbatim,
      so format it for humans ("13 Aug 2026, 20:39") and keep the timezone honest.
    * ``icon`` — Lucide icon name, drawn inside the dot
    * ``color`` — ``blue`` | ``green`` | ``red`` | ``amber`` | ``purple`` | ``gray``,
      the dot's tint. Note ``amber`` (not "yellow") is the warning tone here.

    Prefer this over a List for anything chronological — review history, revision
    history, chain of custody: the rail makes "one thing after another" visible,
    which a list of rows only implies.
    """
    return UINode(type="Timeline", props={"items": items})


def Tree(nodes: list[dict], label: str = "") -> UINode:
    """Hierarchical tree view — for real parent/child structure.

    Each node::

        {
          "id":       "cat-7",           # stable key
          "label":    "Case studies",    # visible text
          "children": [ ...same shape... ],
          "icon":     "FolderOpen",      # optional Lucide name; falls back to
                                         # folder/file by whether it has children
          "badge":    12,                # optional trailing count
          "expanded": True,              # optional: open this branch initially
          "on_click": Call("open", id="cat-7"),
        }

    ``children`` nests the same shape to any depth; a node with children gets a
    disclosure chevron, one without renders as a leaf. ``on_click`` fires a
    UIAction for that node.

    ``label`` names the whole tree for assistive tech ("Product categories") —
    the tree is exposed with real tree/treeitem semantics, so a screen reader
    announces depth and expanded state instead of a wall of anonymous buttons.

    Use it wherever a hierarchy is currently flattened into an indented list —
    content categories, product categories, folder structures: the nesting is
    real information, and a flat list throws it away.
    """
    props: dict[str, Any] = {"nodes": nodes}
    if label:
        props["label"] = label
    return UINode(type="Tree", props=props)


def KeyValue(items: list[dict], columns: int = 1) -> UINode:
    """Key-value pairs grid. Each item: {"key", "value"}."""
    return UINode(type="KeyValue", props={"items": items, "columns": columns})
