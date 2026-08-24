"""Imperal SDK · UI Actions."""
from __future__ import annotations

from .base import UIAction


def Call(function: str, **params) -> UIAction:
    """Direct function call — bypasses chat, executes @chat.function directly."""
    return UIAction(action="call", params={"function": function, "params": params})


def Navigate(path: str) -> UIAction:
    """Client-side navigation."""
    return UIAction(action="navigate", params={"path": path})


def Send(message: str) -> UIAction:
    """Send a message to chat."""
    return UIAction(action="send", params={"message": message})


def Open(url: str) -> UIAction:
    """Open URL in new browser tab."""
    return UIAction(action="open", params={"url": url})


def TrayResponse(badge=None, panel=None, icon_color=None):
    """Structure a system tray handler response.

    NOTE — this is an ENVELOPE, not a rendered component. It is consumed by the
    kernel (the manifest carries a ``tray`` section and ``__tray__*`` synthetic
    handlers), which unpacks ``badge`` and ``panel`` and renders each with its
    own real component. So there is deliberately no ``TrayResponse`` entry in
    the panel component registry, and its absence there is not a gap.

    Args:
        badge: UINode for the tray icon badge (e.g. Badge("5", color="red")).
               Shown as a small number/dot overlay on the tray icon.
        panel: UINode for the dropdown panel (e.g. List of alerts).
               Shown when user clicks the tray icon.
        icon_color: Tint the GLYPH for THIS reading, overriding the static
               ``icon_color`` declared on ``@ext.tray``. The declaration is the
               item's resting colour; this is its colour right now. That
               distinction is the whole point: a balance is amber when it runs
               low and red when it is empty, an agent count is green while
               agents are armed and muted when none are. A manifest cannot
               know any of that — only the handler that just read the number
               does. Same vocabulary as the declaration ("default", "primary",
               "success", "warning", "danger", "muted", plus the badge-colour
               aliases); names, never hex.

    Example::

        @ext.tray("unread", icon="Mail", tooltip="Unread")
        async def tray_mail(ctx, **kw):
            count = await ctx.store.count("messages", where={"read": False})
            msgs = await ctx.store.query("messages", where={"read": False}, limit=5)
            return TrayResponse(
                badge=Badge(str(count), color="red" if count else "gray"),
                panel=List(items=[
                    ListItem(id=m["id"], title=m["subject"], subtitle=m["from"])
                    for m in msgs
                ]) if msgs else None,
            )
    """
    from .base import UINode
    props = {}
    if badge is not None:
        props["badge"] = badge
    if panel is not None:
        props["panel"] = panel
    if icon_color is not None:
        # Normalised here, once, so the host only ever sees a canonical name
        # and an alias ('green') behaves exactly like its canonical twin
        # ('success'). An unknown word is dropped rather than forwarded: the
        # honest reading of a typo is "no opinion about the colour", which
        # leaves the declared resting colour in place instead of blanking the
        # glyph over a spelling mistake.
        from imperal_sdk.types.contributions import (
            ALLOWED_TRAY_ICON_COLORS,
            normalize_tray_icon_color,
        )
        if icon_color in ALLOWED_TRAY_ICON_COLORS:
            props["icon_color"] = normalize_tray_icon_color(icon_color)
    return UINode(type="TrayResponse", props=props)
