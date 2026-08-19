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


def BackButton(
    to: str = "",
    on_click: UIAction | None = None,
    *,
    label: str = "",
) -> UINode:
    """The standard 'go back' control for a detail view.

    ``to`` names the DESTINATION, not the button::

        ui.BackButton("Projects", on_click=ui.Call("open_list"))   # "← Back to Projects"
        ui.BackButton(on_click=ui.Call("open_list"))               # "← Back"

    WHY THIS EXISTS (platform sweep #10): the platform had no standard for
    this, so every app invented one. A live scan found NINE hand-rolled
    variants across the installed apps -- "← Back", "← Back to Extensions",
    "← Back to articles", "← Back to overview", "← Back to newsletters" -- plus
    a private ``_back_button()`` helper in billing. Each picked its own arrow,
    variant and size, so the same gesture looked different on every screen and
    every new detail page re-litigated the decision.

    Composition on purpose: this returns an ordinary ``Button`` node, NOT a new
    node type. Every panel already renders Button, so this works on every
    deployed frontend with no host-side change and nothing to keep in sync --
    the standard lives in ONE place (here) instead of in a renderer the SDK
    cannot see. Only the chrome is fixed: the arrow glyph, ``variant="ghost"``
    and ``size="sm"`` -- the three things the nine copies happened to agree on
    anyway.

    ``on_click`` stays the caller's business: only the app knows where "back"
    goes (a ``Call`` to reopen the list, a ``Navigate``, a state reset).
    ``label`` overrides the whole string when a screen genuinely needs its own
    wording; prefer ``to`` so the phrasing stays consistent.
    """
    text = label or (f"← Back to {to}" if to else "← Back")
    return Button(label=text, variant="ghost", size="sm", on_click=on_click)


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


#: Named widths for ``ui.Modal(size=...)``. ``md`` is 32rem — the width the old
#: hard-coded overlay always had, so untouched code looks pixel-identical.
MODAL_SIZES = ("xs", "sm", "md", "lg", "xl", "2xl", "full")


def Modal(
    title: str = "",
    content: UINode | None = None,
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
    on_confirm: UIAction | None = None,
    *,
    subtitle: str = "",
    size: str = "md",
    max_width: str = "",
    dismissible: bool = True,
    destructive: bool = False,
    on_close: UIAction | None = None,
    open: bool = True,
) -> UINode:
    """A modal window: an overlay layered on top of the current panel.

    This is the correctly-named primitive. It used to be called ``ui.Dialog``,
    which was simply the wrong word — "dialog" is the native browser
    ``<dialog>``/``window.confirm`` concept, while this is a modal window in
    every UI vocabulary. ``ui.Dialog`` still works as a deprecated alias.

    Sizing (fixes the "center overlays are stuck at one width" bug):
      * ``size`` — xs (20rem), sm (24rem), md (32rem, default), lg (42rem),
        xl (56rem), 2xl (72rem), full (fills the viewport).
      * ``max_width`` — any CSS length ("40rem", "600px", "80%") when the named
        steps do not fit. Wins over ``size``.

    Responsive by construction, no per-extension work:
      * phones get a full-width bottom sheet that respects the safe-area inset;
      * from ``sm`` up it is a centred window capped at 90dvh;
      * the body is the only scrolling region, so the title and the buttons
        stay put no matter how long the content is.

    Content:
      * ``content`` — any UINode (use ``ui.Stack`` for several children).
      * ``subtitle`` — optional secondary line under the title.

    Buttons: pass ``confirm_label=""`` or ``cancel_label=""`` to drop that
    button; blank both and the footer is not rendered at all.

    Args:
        title: Heading. Wraps to two lines instead of being cut off.
        content: Body node.
        confirm_label: Primary button text; "" hides it.
        cancel_label: Secondary button text; "" hides it.
        on_confirm: Action fired by the primary button.
        subtitle: Optional line under the title.
        size: One of ``MODAL_SIZES``.
        max_width: Explicit CSS width; overrides ``size``.
        dismissible: When False, Esc / backdrop / ✕ do not close it.
        destructive: STRICT confirmation for an irreversible action — delete,
            purge, revoke. Implies not dismissible (a stray backdrop click must
            never look like a decision on "permanently delete 15,769 rows") and
            tints the confirm button with the danger colour.
        on_close: Action fired when it closes.
        open: Render it closed by passing False.
    """
    # A typo must fail HERE, loudly, instead of silently rendering at the
    # default width and leaving the author wondering why `size` did nothing.
    # A raw CSS length is accepted too — that is what `max_width` is for, but
    # people reach for `size` first, so honour it rather than scold them.
    if size and size not in MODAL_SIZES and not size[0].isdigit():
        raise ValueError(
            f"ui.Modal: unknown size {size!r}. "
            f"Use one of {', '.join(MODAL_SIZES)}, or pass max_width='40rem'."
        )

    props: dict[str, Any] = {
        "confirm_label": confirm_label,
        "cancel_label": cancel_label,
    }
    # An empty title means "no heading" — do not ship the empty string.
    if title: props["title"] = title
    if content: props["content"] = content
    if on_confirm: props["on_confirm"] = on_confirm
    if subtitle: props["subtitle"] = subtitle
    # Only travel non-defaults: keeps the wire payload identical to the old
    # component for code that does not use the new knobs.
    if size and size != "md": props["size"] = size
    if max_width: props["max_width"] = max_width
    if not dismissible: props["dismissible"] = False
    # A one-way door: no backdrop/Esc dismissal, danger-tinted confirm.
    if destructive: props["destructive"] = True
    if on_close: props["on_close"] = on_close
    if not open: props["open"] = False
    return UINode(type="Modal", props=props)


def Dialog(
    title: str,
    content: UINode | None = None,
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
    on_confirm: UIAction | None = None,
    destructive: bool = False,
    **kwargs: Any,
) -> UINode:
    """Deprecated alias for :func:`Modal` — use ``ui.Modal`` in new code.

    Kept working for every extension already shipped against ``ui.Dialog``.
    It deliberately still emits ``type="Dialog"`` rather than ``"Modal"``, so
    panels running an older renderer keep rendering it exactly as before; both
    wire types resolve to the same component on current panels.

    Accepts everything :func:`Modal` does, ``destructive`` included.
    """
    node = Modal(
        title=title,
        content=content,
        confirm_label=confirm_label,
        cancel_label=cancel_label,
        on_confirm=on_confirm,
        destructive=destructive,
        **kwargs,
    )
    node.type = "Dialog"
    return node


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
