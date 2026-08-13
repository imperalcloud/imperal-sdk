"""Imperal SDK · Display UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


def Text(content: str, variant: str = "body", truncate: bool = False,
         className: str = "") -> UINode:
    """Text block. variant: heading/body/caption/code.

    truncate: clip to a single line with an ellipsis instead of wrapping. For
    unbounded values inside a fixed-width cell (a long email, a raw ledger
    reason) — the full text stays in the DOM, so it is still selectable and
    readable by assistive tech; only the pixels are clipped.
    className: escape hatch for one-off spacing. Prefer a layout primitive.
    """
    props: dict[str, Any] = {"content": content, "variant": variant}
    if truncate:
        props["truncate"] = True
    if className:
        props["className"] = className
    return UINode(type="Text", props=props)


def Icon(name: str, size: int = 16, color: str = "", className: str = "") -> UINode:
    """Lucide icon by name.

    name: exact Lucide export, PascalCase (``"Coins"``, ``"TriangleAlert"``).
    An unknown name renders nothing at all, so verify the spelling rather than
    trusting a guess.
    className: extra classes for alignment tweaks.
    """
    props: dict[str, Any] = {"name": name, "size": size, "color": color}
    if className:
        props["className"] = className
    return UINode(type="Icon", props=props)


def Header(text: str, level: int = 2, subtitle: str = "") -> UINode:
    """Heading element h1-h4 with optional subtitle."""
    props: dict[str, Any] = {"text": text, "level": level}
    if subtitle: props["subtitle"] = subtitle
    return UINode(type="Header", props=props)


def Image(src: str, alt: str = "", width: str = "", height: str = "",
          on_click: UIAction | None = None, object_fit: str = "",
          caption: str = "") -> UINode:
    """Image element with optional click action and styling."""
    props: dict[str, Any] = {"src": src}
    if alt: props["alt"] = alt
    if width: props["width"] = width
    if height: props["height"] = height
    if on_click: props["on_click"] = on_click
    if object_fit: props["object_fit"] = object_fit
    if caption: props["caption"] = caption
    return UINode(type="Image", props=props)


def Code(content: str, language: str = "", line_numbers: bool = False) -> UINode:
    """Syntax-highlighted code block."""
    props: dict[str, Any] = {"content": content, "line_numbers": line_numbers}
    if language: props["language"] = language
    return UINode(type="Code", props=props)


def Markdown(content: str) -> UINode:
    """Raw markdown rendered to HTML."""
    return UINode(type="Markdown", props={"content": content})


def Empty(message: str = "No data", icon: str = "", action: UIAction | None = None) -> UINode:
    """Empty state placeholder — the standard for "there is nothing here yet".

    Always prefer this over a bare ``ui.Text("No cases yet")``: an empty screen
    is the moment the user most needs a way forward, and plain text gives none.

    message: name what is missing in the user's own terms.
    icon: Lucide name, sized and muted by the renderer.
    action: the way OUT of the empty state — ``Send("Start an evidence case")``
        to put the request in chat, or ``Call(...)`` to run a handler directly.
        The button label comes from the action's own ``label`` param when set.

    An empty state with no ``action`` is a dead end; add one whenever a
    sensible next step exists.
    """
    props: dict[str, Any] = {"message": message}
    if icon: props["icon"] = icon
    if action: props["action"] = action
    return UINode(type="Empty", props=props)


def Divider(label: str = "") -> UINode:
    """Horizontal rule with optional centered label."""
    props: dict[str, Any] = {}
    if label: props["label"] = label
    return UINode(type="Divider", props=props)


def Html(
    content: str,
    sandbox: bool = True,
    max_height: int = 0,
    theme: str = "dark",
) -> UINode:
    """Raw HTML block.

    sandbox: True isolates in an iframe.
    max_height: scroll container height (0 = auto-size).
    theme: "dark" (default, transparent bg) or "light" (white bg, for email).
    """
    props: dict[str, Any] = {"content": content, "sandbox": sandbox}
    if max_height: props["max_height"] = max_height
    if theme != "dark": props["theme"] = theme
    return UINode(type="Html", props=props)


def Video(
    src: str,
    poster: str = "",
    title: str = "",
    autoplay: bool = False,
    controls: bool = True,
    loop: bool = False,
    muted: bool = False,
    width: str = "",
    height: str = "",
) -> UINode:
    """HTML5 video player.

    src: video URL (mp4, webm, ogg, or HLS m3u8).
    poster: thumbnail image shown before playback.
    controls: show play/pause/seek/volume (default True).
    """
    props: dict[str, Any] = {"src": src, "controls": controls}
    if poster: props["poster"] = poster
    if title: props["title"] = title
    if autoplay: props["autoplay"] = autoplay
    if loop: props["loop"] = loop
    if muted: props["muted"] = muted
    if width: props["width"] = width
    if height: props["height"] = height
    return UINode(type="Video", props=props)


def Audio(
    src: str,
    title: str = "",
    controls: bool = True,
    autoplay: bool = False,
    loop: bool = False,
) -> UINode:
    """HTML5 audio player.

    src: audio URL (mp3, wav, ogg).
    controls: show play/pause/seek/volume (default True).
    """
    props: dict[str, Any] = {"src": src, "controls": controls}
    if title: props["title"] = title
    if autoplay: props["autoplay"] = autoplay
    if loop: props["loop"] = loop
    return UINode(type="Audio", props=props)
