"""UI Contribution types — Panel, Widget, Command, ContextMenu, Setting, Theme.

Extensions declare UI contributions via these types. Platform renders them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ALLOWED_PANEL_SLOTS: frozenset[str] = frozenset({
    "center", "left", "right", "overlay", "bottom", "chat-sidebar",
})


# === System tray zones (Ф3) ==================================================
#
# The tray is the OS-style status strip in the Panel's top bar. It is NOT a
# free-for-all row of icons: every item — the platform's own clock and gear
# just as much as an extension's — declares WHICH zone it belongs to, and the
# host renders the zones in a fixed left-to-right order with separators
# between them. One contract for built-ins and extensions, which is the whole
# point: before this, the built-in items were hardcoded JSX and extensions had
# no way in at all.
#
#   "status"  — passive, at-a-glance state. Live connection, running tasks,
#               unread counts, balance. Read-only: a click may open a detail
#               dropdown, but the icon itself never toggles anything.
#   "actions" — things the user flips or triggers. Toggles, quick switches.
#   "system"  — the platform's own furniture at the far right: clock,
#               settings. Extensions MAY contribute here, but should not
#               unless the item genuinely belongs next to the clock.
#
# Rendered left to right in exactly this order; within a zone, items sort by
# `order` ascending, then by id for a stable tie-break.
TRAY_ZONE_ORDER: tuple[str, ...] = ("status", "actions", "system")
ALLOWED_TRAY_ZONES: frozenset[str] = frozenset(TRAY_ZONE_ORDER)


# === User-menu sections (Ф3) =================================================
#
# The avatar menu at the top right. Sections render in this fixed order,
# separated by hairlines. `account` (identity + theme) and `footer` (sign out)
# are owned by the platform — an extension contributing there would push
# "Sign out" around, so they are declarable but reserved for the host.
#
#   "main"   — the normal place for an extension's own entry.
#   "admin"  — admin-only tools; the host hides the whole section for
#              non-admins, so an item here inherits that gate for free.
MENU_SECTION_ORDER: tuple[str, ...] = ("account", "main", "admin", "footer")
ALLOWED_MENU_SECTIONS: frozenset[str] = frozenset(MENU_SECTION_ORDER)

# Declarable (the host renders them) but NOT contributable: `account` carries
# identity and the theme switch, `footer` carries sign-out. Both sit at the
# ends of the menu where muscle memory lives, so an extension landing there
# would move "Sign out" under a cursor already on its way to it. Enforced in
# two places — @ext.menu_item raises at decoration time, MenuItemDecl rejects
# at manifest-validation time — because a manifest can be hand-edited.
RESERVED_MENU_SECTIONS: frozenset[str] = frozenset({"account", "footer"})
CONTRIBUTABLE_MENU_SECTIONS: frozenset[str] = ALLOWED_MENU_SECTIONS - RESERVED_MENU_SECTIONS


# I-PANEL-RENDERING-CONTRACT (federal v4.1.6+):
# Single source of truth for *what the Imperal Panel host actually does*
# with each declared slot. The keys MUST equal ALLOWED_PANEL_SLOTS exactly
# (asserted by tests/test_panel_rendering_contract.py). The values are:
#
#   "permanent"      — fetched at session-init batch discovery; rendered
#                      as a persistent column. Currently: left, right.
#   "center-overlay" — fetched on demand via __panel__<id> action when the
#                      panel_id is in the host's isCenterOverlay allowlist
#                      (currently {compose, email_viewer+message_id,
#                      editor+note_id, workshop}). Renders over the chat
#                      region; chat collapses to a 380px right rail.
#   "reserved"       — accepted by the SDK validator but the frontend has
#                      no render path. @ext.panel(slot=...) is a no-op for
#                      these. Reserved for future host work.
#
# When the frontend's render path for a slot changes, BOTH this map and
# the docs table at docs.imperal.io/concepts/panels.mdx MUST be updated.
PANEL_SLOT_RENDERING_STATUS: dict[str, str] = {
    "left":         "permanent",
    "right":        "permanent",
    "center":       "center-overlay",
    "overlay":      "reserved",
    "bottom":       "reserved",
    "chat-sidebar": "reserved",
}


@dataclass
class Panel:
    """A movable UI panel contributed by an extension.

    `slot` selects which region of the host the panel renders in. The
    canonical middle-content slot is `"center"` (used by notes, mail,
    sql-db, tasks, whiteboard). `"main"` was the SDK default through
    3.3.x but was never rendered by any host — removed in 3.4.0.
    """
    id: str
    title: str
    icon: str = ""
    slot: str = "center"  # center, left, right, overlay, chat-sidebar, bottom
    component: str = ""
    default_position: int = 0
    movable: bool = True
    resizable: bool = True
    min_width: int = 200
    max_width: int | None = None
    permissions: list[str] = field(default_factory=list)
    context_trigger: str | None = None
    badge: str | None = None

    def __post_init__(self) -> None:
        if self.slot not in ALLOWED_PANEL_SLOTS:
            raise ValueError(
                f"Panel(id={self.id!r}, slot={self.slot!r}): unknown slot. "
                f"Must be one of {sorted(ALLOWED_PANEL_SLOTS)}. "
                "Note: 'main' was removed in SDK 3.4.0; use 'center' instead."
            )


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
