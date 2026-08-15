"""Imperal SDK · Feedback UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


# The single source of truth for Alert severities. The renderer keys its colour
# ramp and icon off this exact vocabulary.
ALERT_VARIANTS = ("info", "success", "warn", "error")

# Spellings that mean exactly one of the four above and nothing else. They are
# normalised rather than rejected because the alternative is worse than either:
# `Alert(type="warning")` was NOT an error before this release — it serialized
# happily and the renderer, which only ever knew "warn", silently fell back to
# blue "info". So a whole fleet of extensions has been shipping warnings that
# render as neutral notices, and a hard error would now break working panels
# over a synonym everyone reasonably expects to work.
#
# Deliberately NOT a general fuzzy matcher: only unambiguous aliases live here.
# A genuine typo ("critical", "warnign") still raises, because guessing what a
# developer meant is how a red alert quietly becomes a green one.
ALERT_SYNONYMS = {
    "warning": "warn",
    "danger": "error",
    "err": "error",
    "ok": "success",
}


def Alert(
    message: str,
    title: str = "",
    variant: str = "",
    dismissible: bool = False,
    *,
    type: str = "",
) -> UINode:
    """Alert banner — info/success/warn/error.

    The severity is ``variant``. ``type`` is kept as a permanent alias because
    every extension written before v5.9.15 passes it; ``variant`` wins if both
    are given.

    Why this matters: the renderer only ever read ``variant``, so a node built
    as ``Alert(type="error")`` used to serialize a prop nothing consumed and
    fell back to blue "info" — a red warning silently rendered as a neutral
    notice. Both spellings now land on the prop the renderer actually reads.

    dismissible: give the banner a close button (transient notices only —
    never for a state the user still needs to see after a refresh).
    """
    resolved = variant or type or "info"
    resolved = ALERT_SYNONYMS.get(resolved, resolved)
    if resolved not in ALERT_VARIANTS:
        raise ValueError(f"ui.Alert variant must be one of {ALERT_VARIANTS}, got {resolved!r}")
    props: dict[str, Any] = {"message": message, "title": title, "variant": resolved}
    if dismissible:
        props["dismissible"] = True
    return UINode(type="Alert", props=props)


def Progress(
    value: int,
    label: str = "",
    variant: str = "bar",
    color: str = "",
    max: int = 0,
    show_value: bool = False,
    size: str = "",
) -> UINode:
    """Progress bar or circular indicator.

    value: current amount. Percentage by default (0-100); pass ``max`` to count
    in natural units instead (e.g. ``value=7, max=12`` for "7 of 12 files") so
    callers stop hand-computing percentages and rounding away the real numbers.
    color: one of 'blue' (default), 'green', 'red', 'yellow', 'purple'. Empty string
    uses the default blue. Use semantic colors for status bars (e.g. red for
    over-budget, green for healthy).
    show_value: print the number next to the track.
    size: 'sm' | 'md' | 'lg' — track thickness.
    """
    props: dict[str, Any] = {"value": value, "label": label, "variant": variant}
    if color:
        props["color"] = color
    if max:
        props["max"] = max
    if show_value:
        props["show_value"] = True
    if size:
        props["size"] = size
    return UINode(type="Progress", props=props)


def Chart(
    data: list[dict],
    type: str = "line",
    x_key: str = "name",
    height: int = 200,
    colors: dict[str, str] | None = None,
    y2_keys: list[str] | None = None,
    title: str = "",
    description: str = "",
    show_legend: bool = False,
    show_data_table: bool = False,
) -> UINode:
    """Chart — line/bar/pie using Recharts.

    colors : optional mapping ``{series_key: color}`` (CSS color or hex). Series not
             listed fall through to the default PALETTE.
    y2_keys : keys in ``data`` that should render on a secondary Y-axis (right side).
              Use for mixed-scale metrics (e.g. spend $ on left, clicks on right).
    """
    props: dict = {"chart_type": type, "data": data, "x_key": x_key, "height": height}
    # Build series list when colors is provided so React receives per-key color.
    if colors and data:
        keys = [k for k in data[0].keys() if k != x_key]
        props["series"] = [
            {"key": k, "label": k, "color": colors[k]} if k in colors else {"key": k, "label": k}
            for k in keys
        ]
    if y2_keys:
        props["y2_keys"] = list(y2_keys)
    if title:
        props["title"] = title
    if description:
        props["description"] = description
    if show_legend:
        props["show_legend"] = True
    if show_data_table:
        props["show_data_table"] = True
    return UINode(type="Chart", props=props)


#: Toast severities. Deliberately the SAME vocabulary as ``ui.Alert`` — an
#: author should not have to remember two spellings for "this went wrong"
#: depending on which primitive they reached for. The renderer maps them onto
#: its own toast-* colour ramp.
TOAST_VARIANTS = ALERT_VARIANTS

#: Same unambiguous aliases Alert accepts, plus the two the renderer's own
#: internal vocabulary uses, so both spellings work either way round.
TOAST_SYNONYMS = ALERT_SYNONYMS


def Toast(
    message: str,
    variant: str = "info",
    duration: int = 5000,
    *,
    title: str = "",
    action: UIAction | None = None,
    action_label: str = "",
) -> UINode:
    """Transient notification that appears over the panel and fades away.

    Use it for the outcome of something the user just did — "Saved", "Deploy
    started", "Could not reach the API". It is NOT for state the user still
    needs after a refresh: a toast disappears, so anything that must survive
    belongs in ``ui.Alert`` (banner) or the panel body itself.

    Severity uses the SAME vocabulary as ``ui.Alert``: info / success / warn /
    error, with the same unambiguous aliases ("warning", "danger", "ok", "err").

    ``duration``: milliseconds before it fades. Pass ``0`` to make it stay
    until the user dismisses it — appropriate for an error the user must
    actually read, never for routine success.

    ``action`` + ``action_label``: one optional button inside the toast, for
    the natural follow-up ("Undo", "View"). Both must be given together.

    Example::

        return ui.Toast("Draft saved", variant="success")

        return ui.Toast(
            "Could not reach the Analytics API",
            variant="error", duration=0,
            action=ui.Call("retry_sync"), action_label="Retry",
        )
    """
    resolved = TOAST_SYNONYMS.get(variant, variant)
    if resolved not in TOAST_VARIANTS:
        raise ValueError(
            f"ui.Toast variant must be one of {TOAST_VARIANTS}, got {variant!r}"
        )
    if duration < 0:
        raise ValueError("ui.Toast duration must be >= 0 (0 = stays until dismissed)")
    if bool(action) != bool(action_label):
        raise ValueError(
            "ui.Toast: pass action and action_label together — an action button "
            "with no label is invisible, a label with no action does nothing"
        )

    props: dict[str, Any] = {"message": message, "variant": resolved}
    # Only travel non-defaults, so the common one-liner stays a tiny payload.
    if duration != 5000: props["duration"] = duration
    if title: props["title"] = title
    if action:
        props["action"] = action
        props["action_label"] = action_label
    return UINode(type="Toast", props=props)


def Loading(message: str = "Loading...", variant: str = "spinner") -> UINode:
    """Loading state indicator. variant: spinner/skeleton/dots."""
    return UINode(type="Loading", props={"message": message, "variant": variant})


def Error(message: str, title: str = "Error", retry: UIAction | None = None) -> UINode:
    """Error state with optional retry action."""
    props: dict[str, Any] = {"message": message, "title": title}
    if retry: props["retry"] = retry
    return UINode(type="Error", props=props)
