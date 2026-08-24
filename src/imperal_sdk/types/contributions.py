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


# === How a tray badge is drawn (Ф3.1) ========================================
#
# `zone` says WHERE an item sits; this says WHAT ITS NUMBER LOOKS LIKE. They
# are separate questions and the host cannot guess the second one, because the
# right answer depends on what the number MEANS:
#
#   "corner" — a small overlay dot on the corner of the icon. The OS
#              convention for a COUNT you might act on: unread mail, pending
#              invites. It is deliberately tiny; it says "there are some",
#              not "there are exactly 1,240,000".
#
#   "inline" — the value sits NEXT TO the glyph, on the same baseline, in
#              tabular figures. The right shape for a MEASUREMENT the user
#              reads rather than clears: a credit balance, an agent count, a
#              temperature. A 7-character value ("1.2M") is legible here and
#              illegible squeezed onto a 14px corner disc.
#
# WHY THIS EXISTS AT ALL. The platform's own credit counter and agent counter
# were hardcoded React components drawing their number inline. When they moved
# out to `@ext.billing` / `@ext.automations` — which is the whole point of
# `@ext.tray` being a real contract — the host had only one way to draw a
# badge, the corner dot, so a balance the user had read inline for a year
# silently became a dot with "1.2M" crushed into it. The contract was missing
# a word for a difference the user could see, so the host had to guess, and it
# guessed the same way for everyone.
#
# Default is "corner": it is the conservative choice for an unknown count, and
# it keeps every manifest emitted before this field rendering exactly as it did.
TRAY_BADGE_STYLES: tuple[str, ...] = ("corner", "inline")
ALLOWED_TRAY_BADGE_STYLES: frozenset[str] = frozenset(TRAY_BADGE_STYLES)
DEFAULT_TRAY_BADGE_STYLE: str = "corner"


# === What colour a tray GLYPH is (Ф3.2) ======================================
#
# `badge_style` says how the NUMBER is drawn. This says what the ICON ITSELF
# looks like, which is a different question the host also cannot guess.
#
# WHY IT IS NEEDED. The platform's own tray items were hardcoded React, and
# every one of them was tinted: the agent bot went green while agents were
# armed, the credit mark went amber then red as the balance ran down, the
# shield went blue while confirmations were on. Colour was carrying real
# meaning at a glance. When those items moved out to their own extensions
# through `@ext.tray`, the contract had no word for it, so every contributed
# glyph rendered in the same neutral grey -- the strip lost a whole channel
# of information, and the swap from built-in to contributed item was visible
# precisely BECAUSE the colour vanished.
#
# NAMES, NOT HEX. An extension says what the state MEANS ("danger"), never
# what shade to paint ("#ef4444"). The host maps the word onto its own design
# tokens, so a contributed icon follows the active theme, respects contrast,
# and keeps working when the palette changes. A manifest full of raw hex codes
# would freeze one theme into every extension on the platform forever.
#
#   "default" — inherit the tray's own text colour (what a normal item does)
#   "primary" — the accent: this is on / active / selected
#   "success" — healthy, armed, connected
#   "warning" — needs attention soon (a balance getting low, an expiring job)
#   "danger"  — broken, empty, failing
#   "muted"   — deliberately de-emphasised; present but not asking for the eye
#
# The badge colours ('red'/'green'/'blue'/'yellow'/'gray') are accepted as
# aliases so an author does not have to remember two vocabularies for the same
# six ideas.
TRAY_ICON_COLORS: tuple[str, ...] = (
    "default", "primary", "success", "warning", "danger", "muted",
)
TRAY_ICON_COLOR_ALIASES: dict[str, str] = {
    "blue": "primary",
    "green": "success",
    "yellow": "warning",
    "amber": "warning",
    "red": "danger",
    "gray": "muted",
    "grey": "muted",
}
ALLOWED_TRAY_ICON_COLORS: frozenset[str] = (
    frozenset(TRAY_ICON_COLORS) | frozenset(TRAY_ICON_COLOR_ALIASES)
)
DEFAULT_TRAY_ICON_COLOR: str = "default"


def normalize_tray_icon_color(value: str | None) -> str:
    """Fold an alias onto its canonical name.

    Done ONCE here, at the edge of the contract, so the manifest that reaches
    the host is already canonical and the host never has to know the alias
    table. Two spellings of one colour must not be able to become two
    behaviours further down the pipe.
    """
    if not value:
        return DEFAULT_TRAY_ICON_COLOR
    v = value.strip().lower()
    return TRAY_ICON_COLOR_ALIASES.get(v, v)


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
