"""Imperal SDK · Interactive UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


def Button(
    label: str,
    variant: str = "primary",
    on_click: UIAction | None = None,
    disabled: bool = False,
    size: str = "md",
    full_width: bool = False,
    icon: str = "",
    icon_left: str = "",
    icon_right: str = "",
    loading: bool = False,
    loading_label: str = "",
    type: str = "",
) -> UINode:
    """Clickable button. size: sm/md/lg. icon: Lucide icon name.

    icon_left / icon_right: place the glyph on a specific side. ``icon`` stays
    as the shorthand for the leading position.
    loading: show a spinner and block re-entry while the action runs — use it
    for anything that writes, so a slow save cannot be double-submitted.
    loading_label: what to say while it runs ("Saving…"); the label alone often
    leaves the user unsure whether the click registered.
    type: native button type — ``submit`` inside a Form, ``button`` otherwise.
    """
    props: dict[str, Any] = {
        "label": label, "variant": variant, "disabled": disabled, "size": size,
    }
    if full_width: props["full_width"] = True
    if on_click: props["on_click"] = on_click
    if icon: props["icon"] = icon
    if icon_left: props["icon_left"] = icon_left
    if icon_right: props["icon_right"] = icon_right
    if loading: props["loading"] = True
    if loading_label: props["loading_label"] = loading_label
    if type: props["type"] = type
    return UINode(type="Button", props=props)


def Card(
    title: str = "",
    subtitle: str = "",
    content: UINode | None = None,
    footer: UINode | None = None,
    on_click: UIAction | None = None,
    border: bool | None = None,
    padding: str = "",
) -> UINode:
    """Container card with optional title, subtitle, content and footer slots.

    border: tri-state. ``None`` keeps the renderer default; ``False`` drops the
    frame for a card nested inside another card, where a second border reads as
    clutter rather than structure.
    padding: ``none`` | ``sm`` | ``md`` | ``lg``. Use ``none`` when the content
    is a full-bleed table or image that should touch the card edges.
    """
    props: dict[str, Any] = {}
    if title: props["title"] = title
    if subtitle: props["subtitle"] = subtitle
    if content: props["content"] = content
    if footer: props["footer"] = footer
    if on_click: props["on_click"] = on_click
    if border is not None: props["border"] = border
    if padding: props["padding"] = padding
    return UINode(type="Card", props=props)


def Menu(items: list[dict], trigger: UINode | None = None,
         align: str = "") -> UINode:
    """Dropdown menu. Each item: {"label", "icon", "on_click", "separator"}.

    An item may also carry ``"confirm": "Delete this?"`` — the renderer gates
    that entry behind an inline confirmation, so a destructive menu row does not
    need its own Dialog.
    align: ``start`` | ``end`` — which edge the panel aligns to. Use ``end`` for
    a trigger sitting at the right of a row, so the menu opens inward.
    """
    props: dict[str, Any] = {"items": items}
    if trigger: props["trigger"] = trigger
    if align: props["align"] = align
    return UINode(type="Menu", props=props)


def Dialog(
    title: str,
    content: UINode | None = None,
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
    on_confirm: UIAction | None = None,
    destructive: bool = False,
) -> UINode:
    """Modal dialog with confirm/cancel actions.

    destructive: turn this into a STRICT confirmation for an irreversible
    action — delete, purge, revoke. It cannot be dismissed by clicking the
    backdrop or pressing Escape (only an explicit button closes it), and the
    confirm button takes the danger tint.

    Why it exists: a stray click on the backdrop must never be able to *look*
    like a decision on "permanently delete 15,769 rows". A soft modal is right
    for a form the user can reopen; it is wrong for a one-way door. Design
    systems that split Dialog from AlertDialog encode exactly this distinction
    — here it is one primitive with an explicit flag, so the safe default and
    the strict variant cannot drift apart.
    """
    props: dict[str, Any] = {
        "title": title,
        "confirm_label": confirm_label,
        "cancel_label": cancel_label,
    }
    if content: props["content"] = content
    if on_confirm: props["on_confirm"] = on_confirm
    if destructive: props["destructive"] = True
    return UINode(type="Dialog", props=props)


def Tooltip(content: str, children: UINode | None = None,
            delay_ms: int = 0) -> UINode:
    """Hover tooltip wrapping an optional child node.

    delay_ms: hover dwell before it appears. Raise it for tooltips on dense
    rows, so sweeping the cursor across a table does not flash a trail of them.

    A tooltip is supplementary by nature — it is unreachable on touch and
    transient for screen readers, so never put information here that the user
    needs in order to act.
    """
    props: dict[str, Any] = {"content": content}
    if children: props["children"] = children
    if delay_ms: props["delay_ms"] = delay_ms
    return UINode(type="Tooltip", props=props)


def Link(
    label: str = "",
    href: str = "",
    on_click: UIAction | None = None,
    *,
    text: str = "",
) -> UINode:
    """Hyperlink — navigates via href or fires on_click action.

    The visible text can be passed as either ``label`` (canonical) or
    ``text`` (alias matching the HTML/JSX `<a>text</a>` mental model).
    Exactly one must be provided; ``label`` wins if both are set.
    """
    resolved = label or text
    if not resolved:
        raise TypeError("ui.Link requires a 'label' (or 'text' alias)")
    props: dict[str, Any] = {"label": resolved}
    if href: props["href"] = href
    if on_click: props["on_click"] = on_click
    return UINode(type="Link", props=props)


def SlideOver(
    title: str,
    children: list[UINode] | None = None,
    subtitle: str = "",
    open: bool = True,
    width: str = "md",
    on_close: UIAction | None = None,
) -> UINode:
    """Side panel sliding in from right. width: sm/md/lg/xl."""
    props: dict[str, Any] = {
        "title": title,
        "subtitle": subtitle,
        "open": open,
        "width": width,
    }
    if children: props["children"] = children
    if on_close: props["on_close"] = on_close
    return UINode(type="SlideOver", props=props)
