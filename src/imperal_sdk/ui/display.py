"""Imperal SDK · Display UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


def Text(content: str, variant: str = "body") -> UINode:
    """Text block. variant: heading/body/caption/code."""
    return UINode(type="Text", props={"content": content, "variant": variant})


def Icon(name: str, size: int = 16, color: str = "") -> UINode:
    """Lucide icon by name."""
    return UINode(type="Icon", props={"name": name, "size": size, "color": color})


def Header(text: str, level: int = 2, subtitle: str = "") -> UINode:
    """Heading element h1-h4 with optional subtitle."""
    props: dict[str, Any] = {"text": text, "level": level}
    if subtitle: props["subtitle"] = subtitle
    return UINode(type="Header", props=props)


def Image(src: str, alt: str = "", width: str = "", height: str = "") -> UINode:
    """Image element."""
    props: dict[str, Any] = {"src": src}
    if alt: props["alt"] = alt
    if width: props["width"] = width
    if height: props["height"] = height
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
    """Empty state placeholder."""
    props: dict[str, Any] = {"message": message}
    if icon: props["icon"] = icon
    if action: props["action"] = action
    return UINode(type="Empty", props=props)


def Divider(label: str = "") -> UINode:
    """Horizontal rule with optional centered label."""
    props: dict[str, Any] = {}
    if label: props["label"] = label
    return UINode(type="Divider", props=props)
