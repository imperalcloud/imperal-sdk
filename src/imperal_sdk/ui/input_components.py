"""Imperal SDK · Input UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction

# The single source of truth for the allowed ui.Input HTML input types.
# Consumed by Input() validation (here), the manifest schema (Ф2), the
# reference generator (Ф1), and the docs <SdkRef> (Ф3). Add new types here only.
INPUT_TYPES = ("text", "password", "email", "number", "url")

# The single source of truth for ui.FileUpload presentational variants. The
# panel renderer picks pixels off this hint; the wire contract stays declarative
# (kernel emits the node, renderer owns the look). Add new variants here only.
FILEUPLOAD_VARIANTS = ("default", "futuristic", "compact")

# Presentational variants shared by the text-entry fields (Input/TextArea).
# "default" = the recessed control chrome; "ghost" = transparent, for dense
# toolbars and inline edit cells where a full control frame is visual noise.
FIELD_VARIANTS = ("default", "ghost")


def _field_props(
    props: dict[str, Any],
    *,
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
    readonly: bool | None = None,
) -> dict[str, Any]:
    """Attach the shared LABELED-FIELD contract to any input node.

    SYSTEM REQUIREMENT — labeled input variant (design, 2026-08-13). Every
    Imperal input supports two shapes:

    * **without label** — the original one, still valid where the purpose is
      already unambiguous from the immediate context;
    * **with label** — the DEFAULT for new screens, where label and control
      live in one container.

    Passing ``label`` is all an extension has to do. The renderer wraps the
    control in its ``Field`` primitive, which puts label + control inside a
    container carrying the ``.field-gap`` class and binds them together with a
    real ``for``/``id`` pair (generated via ``useId``), so the association is
    programmatic, not visual — that is what makes it accessible.

    A placeholder is NOT a label. ``placeholder`` may show an example of the
    expected format, but it disappears the moment the user types, so it can
    never be the field's only name.

    Every key stays off the wire at its default, so existing label-less inputs
    serialize byte-identically and older renderers are unaffected.
    """
    if label: props["label"] = label
    if description: props["description"] = description
    if error: props["error"] = error
    if required: props["required"] = True
    if disabled: props["disabled"] = True
    if readonly: props["readonly"] = True
    return props


def Input(
    placeholder: str = "",
    on_submit: UIAction | None = None,
    value: str = "",
    param_name: str = "value",
    type: str = "text",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
    readonly: bool = False,
    variant: str = "default",
) -> UINode:
    """Text input field. on_submit fires on Enter, value merged as param_name.

    ``type`` (v4.2.6+) is a hint to the Panel renderer for native HTML input
    behaviour: ``"text"`` (default), ``"password"`` (browser-blind, no echo),
    ``"email"``, ``"number"``, ``"url"``. Prefer ``ui.Password(...)`` for
    credential entry — it's a thin convenience wrapper that pins type for
    federal EXT-SECRETS-V1 UIs.

    LABELED VARIANT (v5.9.15+, preferred for new screens)::

        ui.Input(label="Contract amount", placeholder="e.g. 500.00",
                 description="Empty = use the plan price.",
                 param_name="contract_amount")

    Pass ``label`` and the renderer emits the label/control pair inside one
    ``.field-gap`` container, wired together with a proper ``for``/``id``.
    ``description`` renders as help text below the control (and is announced
    via ``aria-describedby``); ``error`` renders an inline error and flips
    ``aria-invalid``; ``required`` marks it both visually and semantically.
    Use the label-less form only deliberately, where a nearby heading already
    names the field — a placeholder alone does not.

    ``variant``: ``"default"`` (recessed control chrome) or ``"ghost"``
    (transparent, for dense toolbars and inline editing).
    """
    if type not in INPUT_TYPES:
        raise ValueError(f"ui.Input type must be one of {INPUT_TYPES}, got {type!r}")
    if variant not in FIELD_VARIANTS:
        raise ValueError(f"ui.Input variant must be one of {FIELD_VARIANTS}, got {variant!r}")
    props: dict[str, Any] = {"placeholder": placeholder, "value": value, "param_name": param_name}
    if type and type != "text":
        props["type"] = type
    if on_submit: props["on_submit"] = on_submit
    if variant != "default": props["variant"] = variant
    return UINode(type="Input", props=_field_props(
        props, label=label, description=description, error=error,
        required=required, disabled=disabled, readonly=readonly))


def Password(
    placeholder: str = "paste value…",
    on_submit: UIAction | None = None,
    value: str = "",
    param_name: str = "value",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
    readonly: bool = False,
) -> UINode:
    """Password input — browser-blind, no echo, autocomplete='new-password'.

    EXT-SECRETS-V1 (federal v4.2.6+) — the canonical credential-entry primitive.
    Renders as ``<input type="password" autocomplete="new-password">`` in the
    Panel UI so values are visually masked while the user types. Submitted
    value rides into the action as ``param_name`` (default ``"value"``); use
    inside ``ui.Form(defaults={...})`` to attach hidden context fields like
    ``app_id`` and ``name``.

    Federal note: type=password is a defence against shoulder-surfing, NOT a
    security control. The plaintext still travels in the POST body to the
    server, which is the only correctness boundary. Audit chokepoint + Vault
    transit are what make this federal-grade.

    Supports the same LABELED-FIELD contract as ``ui.Input`` (v5.9.17+) — and
    needs it more than most: a credential field asks for something the user
    cannot verify by reading it back, so "which secret does this want?" must be
    answerable from a permanent label. A masked control shows dots the moment
    typing starts, which is exactly when a placeholder disappears.
    """
    return Input(
        placeholder=placeholder,
        on_submit=on_submit,
        value=value,
        param_name=param_name,
        type="password",
        label=label,
        description=description,
        error=error,
        required=required,
        disabled=disabled,
        readonly=readonly,
    )


def Form(
    children: list[UINode],
    action: str = "",
    submit_label: str = "Submit",
    defaults: dict | None = None,
) -> UINode:
    """Form container — collects child input values and submits as one action."""
    props: dict[str, Any] = {"children": children, "submit_label": submit_label}
    if action: props["action"] = action
    if defaults: props["defaults"] = defaults
    return UINode(type="Form", props=props)


def Select(
    options: list[dict],
    value: str = "",
    placeholder: str = "",
    on_change: UIAction | None = None,
    param_name: str = "value",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
) -> UINode:
    """Single-select dropdown. Each option: {"value", "label"}.

    Supports the same LABELED-FIELD contract as ``ui.Input``: pass ``label``
    to get the label/control pair in one ``.field-gap`` container, bound with
    a proper ``for``/``id``. Preferred for new screens.
    """
    props: dict[str, Any] = {"options": options, "value": value, "param_name": param_name}
    if placeholder: props["placeholder"] = placeholder
    if on_change: props["on_change"] = on_change
    return UINode(type="Select", props=_field_props(
        props, label=label, description=description, error=error,
        required=required, disabled=disabled))


def MultiSelect(
    options: list[dict],
    values: list[str] | None = None,
    placeholder: str = "",
    param_name: str = "values",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
) -> UINode:
    """Multi-select dropdown. Each option: {"value", "label"}.

    Supports the same LABELED-FIELD contract as ``ui.Input`` (v5.9.17+): pass
    ``label`` to get the label/control pair in one ``.field-gap`` container,
    bound with a proper ``for``/``id``. Preferred for new screens.

    This control needs the label more than a plain input does: once the first
    chip is selected the placeholder is replaced by the selection itself, so
    without a label nothing on screen still says what is being chosen.
    """
    props: dict[str, Any] = {"options": options, "values": values or [], "param_name": param_name}
    if placeholder: props["placeholder"] = placeholder
    return UINode(type="MultiSelect", props=_field_props(
        props, label=label, description=description, error=error,
        required=required, disabled=disabled))


def Toggle(
    label: str = "",
    value: bool = False,
    on_change: UIAction | None = None,
    param_name: str = "enabled",
) -> UINode:
    """Boolean toggle switch."""
    props: dict[str, Any] = {"value": value, "param_name": param_name}
    if label: props["label"] = label
    if on_change: props["on_change"] = on_change
    return UINode(type="Toggle", props=props)


def Slider(
    min: int = 0,
    max: int = 100,
    value: int = 50,
    step: int = 1,
    label: str = "",
    param_name: str = "value",
    disabled: bool = False,
) -> UINode:
    """Numeric range slider.

    The renderer already pairs ``label`` with the control inside a
    ``.field-gap`` container and binds them via ``for``/``id``.
    """
    props: dict[str, Any] = {"min": min, "max": max, "value": value, "step": step, "param_name": param_name}
    if label: props["label"] = label
    if disabled: props["disabled"] = True
    return UINode(type="Slider", props=props)


def DatePicker(
    value: str = "",
    placeholder: str = "Select date",
    on_change: UIAction | None = None,
    param_name: str = "date",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
    min: str = "",
    max: str = "",
) -> UINode:
    """Date picker calendar input.

    Supports the LABELED-FIELD contract (``label``/``description``/``error``/
    ``required``) exactly like ``ui.Input``, plus ``min``/``max`` to bound the
    selectable range (ISO ``YYYY-MM-DD``) — the renderer enforces both natively.

    Note: a native date control paints its own ``dd/mm/yyyy`` hint, so a
    placeholder is physically not displayable here. The parameter is kept so
    existing calls keep working, but it is NOT put on the wire — an ignored
    prop travelling in every payload is a lie about what the UI does. Name the
    field with ``label`` instead.
    """
    props: dict[str, Any] = {"value": value, "param_name": param_name}
    if on_change: props["on_change"] = on_change
    if min: props["min"] = min
    if max: props["max"] = max
    return UINode(type="DatePicker", props=_field_props(
        props, label=label, description=description, error=error,
        required=required, disabled=disabled))


def FileUpload(
    accept: str = "*",
    max_size_mb: int = 10,
    multiple: bool = False,
    on_upload: UIAction | None = None,
    param_name: str = "files",
    blocked_extensions: list[str] | None = None,
    max_total_mb: int = 0,
    max_files: int = 0,
    title: str = "",
    hint: str = "",
    variant: str = "default",
    show_previews: bool = False,
) -> UINode:
    """File upload dropzone with validation.
    blocked_extensions: reject these file types (e.g. ["exe", "bat"]).
    max_total_mb: total size limit across all files (0 = no limit).
    max_files: max number of files (0 = no limit).
    Frontend sends base64 file data in on_upload action.

    Presentational hints (renderer owns pixels; wire stays declarative):
    title/hint — heading + sub-line over the dropzone; variant — one of
    ``FILEUPLOAD_VARIANTS`` (``"futuristic"`` = animated per-file rows with
    progress/status; ``"compact"`` = dense); show_previews — image thumbnails.
    All hints stay off the wire at their defaults, so older renderers are
    unaffected.
    """
    if variant not in FILEUPLOAD_VARIANTS:
        raise ValueError(
            f"ui.FileUpload variant must be one of {FILEUPLOAD_VARIANTS}, got {variant!r}")
    props: dict[str, Any] = {
        "accept": accept,
        "max_size_mb": max_size_mb,
        "multiple": multiple,
        "param_name": param_name,
    }
    if on_upload: props["on_upload"] = on_upload
    if blocked_extensions: props["blocked_extensions"] = blocked_extensions
    if max_total_mb: props["max_total_mb"] = max_total_mb
    if max_files: props["max_files"] = max_files
    if title: props["title"] = title
    if hint: props["hint"] = hint
    if variant and variant != "default": props["variant"] = variant
    if show_previews: props["show_previews"] = True
    return UINode(type="FileUpload", props=props)


def TextArea(
    placeholder: str = "",
    value: str = "",
    rows: int = 4,
    on_submit: UIAction | None = None,
    param_name: str = "text",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
    readonly: bool = False,
) -> UINode:
    """Multi-line text area.

    HOW ``on_submit`` ACTUALLY FIRES — **Ctrl+Enter / Cmd+Enter**, not a plain
    Enter. A bare Enter inserts a newline, which is the whole point of a
    multi-line field; ``ui.Input`` submits on Enter precisely because it is
    single-line. This was previously undocumented, so a TextArea with
    ``on_submit`` looked like it silently did nothing.

    READING THE VALUE FROM ELSEWHERE — wrap it in ``ui.Form``. Inside a Form
    the current text is registered under ``param_name``, so the Form's submit
    button sends it automatically::

        ui.Form(action="save_note", submit_label="Save", children=[
            ui.TextArea(label="Note", param_name="body"),
        ])

    Outside a Form there is no shared state: a plain ``ui.Button`` sitting next
    to a TextArea CANNOT read what the user typed — buttons carry a fixed
    action, they do not read sibling controls. Use ``ui.Form``, or
    ``on_submit`` with Ctrl/Cmd+Enter. There is no third way, by design.

    Supports the same LABELED-FIELD contract as ``ui.Input`` — pass ``label``
    and the renderer pairs label + control inside one ``.field-gap`` container
    with a real ``for``/``id`` binding. See ``_field_props`` for the full rule.
    """
    props: dict[str, Any] = {"placeholder": placeholder, "value": value, "rows": rows, "param_name": param_name}
    if on_submit: props["on_submit"] = on_submit
    return UINode(type="TextArea", props=_field_props(
        props, label=label, description=description, error=error,
        required=required, disabled=disabled, readonly=readonly))


def RichEditor(content: str = "", placeholder: str = "Start writing...",
               on_save: UIAction | None = None, on_change: UIAction | None = None,
               param_name: str = "content", toolbar: bool = True,
               label: str = "", description: str = "", error: str = "",
               required: bool = False) -> UINode:
    """Rich text editor (TipTap). content: HTML string. on_save fires on Ctrl+S.

    Supports the same LABELED-FIELD contract as ``ui.Input`` (v5.9.17+): pass
    ``label`` to get the label/control pair in one ``.field-gap`` container,
    bound with a proper ``for``/``id``. Preferred for new screens.

    The editor's placeholder lives *inside* the editable area and is gone after
    the first keystroke, so on a screen with several editors (body, summary,
    notes) only a real label still tells them apart.
    """
    props: dict[str, Any] = {"content": content, "placeholder": placeholder,
             "param_name": param_name, "toolbar": toolbar}
    if on_save: props["on_save"] = on_save
    if on_change: props["on_change"] = on_change
    return UINode(type="RichEditor", props=_field_props(
        props, label=label, description=description, error=error,
        required=required))


def TagInput(
    values: list[str] | None = None,
    suggestions: list[str] | None = None,
    placeholder: str = "Add...",
    param_name: str = "tags",
    on_change: UIAction | None = None,
    grouped_by: str = "",
    delimiters: list[str] | None = None,
    validate: str = "",
    validate_message: str = "",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
) -> UINode:
    """Tag/chip input with autocomplete.

    Supports the same LABELED-FIELD contract as ``ui.Input`` (v5.9.17+): pass
    ``label`` to get the label/control pair in one ``.field-gap`` container,
    bound with a proper ``for``/``id``. Preferred for new screens — here the
    placeholder is only rendered while the field is still empty, so after the
    first tag nothing on screen names the field any more.

    grouped_by      : group suggestions by prefix (e.g. 'extensions:read').
    delimiters      : extra keystrokes that create a tag in addition to Enter.
                      Accepts individual characters (e.g. [' ', ',', ';']). Default
                      is Enter-only to preserve prior behaviour.
    validate        : optional regex pattern (string). Tags failing the pattern are
                      refused; the input is highlighted red and ``validate_message``
                      is shown as a tooltip. Anchor yourself — use '^...$' for
                      full-string match.
    validate_message: human-readable hint shown on rejected tags. Fallback generic
                      message is used when empty.
    """
    props: dict[str, Any] = {
        "values": values or [],
        "suggestions": suggestions or [],
        "placeholder": placeholder,
        "param_name": param_name,
        "grouped_by": grouped_by,
    }
    if on_change: props["on_change"] = on_change
    if delimiters:
        # Keep the list homogenous — strings only, each one a single char or short key.
        props["delimiters"] = [str(d) for d in delimiters if d]
    if validate:
        props["validate"] = validate
    if validate_message:
        props["validate_message"] = validate_message
    return UINode(type="TagInput", props=_field_props(
        props, label=label, description=description, error=error,
        required=required))


def Checkbox(
    label: str = "",
    value: bool = False,
    on_change: UIAction | None = None,
    param_name: str = "checked",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
) -> UINode:
    """A single boolean checkbox — consent, opt-in, one independent flag.

    Distinct from ``ui.Toggle``: a toggle applies its change immediately (a
    setting that takes effect the moment it flips), while a checkbox is a form
    value submitted with the rest of the form. Use ``ui.Toggle`` for "dark mode
    on/off", ``ui.Checkbox`` for "I agree to the terms".

    Unlike every other labeled field the label renders BESIDE the box rather
    than above it — a checkbox reads as one sentence with its label, and a
    label floating above an empty box is a known usability failure. It is still
    a real ``for``/``id`` binding, so clicking the text ticks the box.

    ::

        ui.Checkbox(label="Send me the monthly report",
                    description="One email a month. Unsubscribe anytime.",
                    param_name="subscribe")
    """
    props: dict[str, Any] = {"value": bool(value), "param_name": param_name}
    if on_change:
        props["on_change"] = on_change
    return UINode(type="Checkbox", props=_field_props(
        props, label=label, description=description, error=error,
        required=required, disabled=disabled))


def RadioGroup(
    options: list[dict],
    value: str = "",
    on_change: UIAction | None = None,
    param_name: str = "value",
    label: str = "",
    description: str = "",
    error: str = "",
    required: bool = False,
    disabled: bool = False,
    orientation: str = "vertical",
) -> UINode:
    """Pick exactly ONE option from a small set, with every choice visible.

    Each option is ``{"value", "label"}`` — the same shape as ``ui.Select``,
    plus an optional per-option ``"description"`` and ``"disabled"``.

    Prefer this over ``ui.Select`` when there are 2-5 options and the choice
    matters enough that the user should see them all without opening a dropdown
    (billing mode, plan tier, destructive-vs-safe strategy). Past roughly six
    options a dropdown is kinder.

    ``orientation``: ``"vertical"`` (default) or ``"horizontal"`` for short
    labels that fit on one line.

    The group renders as a real ``role="radiogroup"`` labelled by its own
    label, and arrow keys move between options — the native radio behaviour
    keyboard and assistive-technology users expect.

    ::

        ui.RadioGroup(label="How should this customer pay?",
                      options=[
                          {"value": "card", "label": "By card",
                           "description": "Charged automatically each period."},
                          {"value": "manual", "label": "Manually, by invoice"},
                          {"value": "free", "label": "Free — no charge"},
                      ],
                      value="card", param_name="billing_mode")
    """
    if orientation not in ("vertical", "horizontal"):
        raise ValueError(
            f"ui.RadioGroup(orientation={orientation!r}) is not valid — "
            "use 'vertical' or 'horizontal'."
        )
    props: dict[str, Any] = {
        "options": options or [],
        "value": value,
        "param_name": param_name,
        "orientation": orientation,
    }
    if on_change:
        props["on_change"] = on_change
    return UINode(type="RadioGroup", props=_field_props(
        props, label=label, description=description, error=error,
        required=required, disabled=disabled))
