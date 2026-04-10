"""UI Contribution types — Panel, Widget, Command, ContextMenu, Setting, Theme.

Extensions declare UI contributions via these types. Platform renders them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Panel:
    """A movable UI panel contributed by an extension."""
    id: str
    title: str
    icon: str = ""
    slot: str = "main"  # main, left, right, overlay, chat-sidebar, bottom
    component: str = ""
    default_position: int = 0
    movable: bool = True
    resizable: bool = True
    min_width: int = 200
    max_width: int | None = None
    permissions: list[str] = field(default_factory=list)
    context_trigger: str | None = None
    badge: str | None = None


@dataclass
class Widget:
    """A small UI widget embedded at injection points."""
    id: str
    slot: str  # dashboard.stats, chat.message-actions, email.toolbar, etc.
    component: str = ""
    size: str = "md"  # xs, sm, md, lg
    label: str = ""
    icon: str = ""
    permissions: list[str] = field(default_factory=list)


@dataclass
class Command:
    """A command registered in the command palette."""
    id: str
    title: str
    icon: str = ""
    shortcut: str = ""
    category: str = ""
    handler: str = ""
    when: str = ""


@dataclass
class ContextMenu:
    """A context menu item for right-click menus."""
    slot: str  # chat.message, email.message, file.item, table.row
    label: str
    icon: str = ""
    handler: str = ""
    separator_before: bool = False
    when: str = ""
    group: str = ""


@dataclass
class Setting:
    """A user-configurable setting for the extension."""
    id: str
    type: str  # string, number, boolean, secret, select, list, color, json
    label: str
    description: str = ""
    default: Any = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    options: list[dict] | None = None
    placeholder: str = ""
    group: str = ""
    admin_only: bool = False


@dataclass
class Theme:
    """Extension theme customization."""
    accent_color: str = ""
    dark_mode: bool = True
    custom_css: str = ""
    chat_bubble_style: str = "default"  # default, minimal, card
    icon_style: str = "outline"  # outline, solid, duotone
    border_radius: str = "md"  # none, sm, md, lg, full
