"""Imperal SDK · Input UI Components."""
from __future__ import annotations

from typing import Any
from .base import UINode, UIAction


def Input(
    placeholder: str = "",
    on_submit: UIAction | None = None,
    value: str = "",
    param_name: str = "value",
) -> UINode:
    """Text input field. on_submit fires on Enter, value merged as param_name."""
    props: dict[str, Any] = {"placeholder": placeholder, "value": value, "param_name": param_name}
    if on_submit: props["on_submit"] = on_submit
    return UINode(type="Input", props=props)


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
) -> UINode:
    """Single-select dropdown. Each option: {"value", "label"}."""
    props: dict[str, Any] = {"options": options, "value": value, "param_name": param_name}
    if placeholder: props["placeholder"] = placeholder
    if on_change: props["on_change"] = on_change
    return UINode(type="Select", props=props)


def MultiSelect(
    options: list[dict],
    values: list[str] | None = None,
    placeholder: str = "",
    param_name: str = "values",
) -> UINode:
    """Multi-select dropdown. Each option: {"value", "label"}."""
    props: dict[str, Any] = {"options": options, "values": values or [], "param_name": param_name}
    if placeholder: props["placeholder"] = placeholder
    return UINode(type="MultiSelect", props=props)


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
) -> UINode:
    """Numeric range slider."""
    props: dict[str, Any] = {"min": min, "max": max, "value": value, "step": step, "param_name": param_name}
    if label: props["label"] = label
    return UINode(type="Slider", props=props)


def DatePicker(
    value: str = "",
    placeholder: str = "Select date",
    on_change: UIAction | None = None,
    param_name: str = "date",
) -> UINode:
    """Date picker calendar input."""
    props: dict[str, Any] = {"value": value, "placeholder": placeholder, "param_name": param_name}
    if on_change: props["on_change"] = on_change
    return UINode(type="DatePicker", props=props)


def FileUpload(
    accept: str = "*",
    max_size_mb: int = 10,
    multiple: bool = False,
    on_upload: UIAction | None = None,
    param_name: str = "files",
    blocked_extensions: list[str] | None = None,
    max_total_mb: int = 0,
    max_files: int = 0,
) -> UINode:
    """File upload dropzone with validation.
    blocked_extensions: reject these file types (e.g. ["exe", "bat"]).
    max_total_mb: total size limit across all files (0 = no limit).
    max_files: max number of files (0 = no limit).
    Frontend sends base64 file data in on_upload action.
    """
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
    return UINode(type="FileUpload", props=props)


def TextArea(
    placeholder: str = "",
    value: str = "",
    rows: int = 4,
    on_submit: UIAction | None = None,
    param_name: str = "text",
) -> UINode:
    """Multi-line text area."""
    props: dict[str, Any] = {"placeholder": placeholder, "value": value, "rows": rows, "param_name": param_name}
    if on_submit: props["on_submit"] = on_submit
    return UINode(type="TextArea", props=props)


def RichEditor(content: str = "", placeholder: str = "Start writing...",
               on_save: UIAction | None = None, on_change: UIAction | None = None,
               param_name: str = "content", toolbar: bool = True) -> UINode:
    """Rich text editor (TipTap). content: HTML string. on_save fires on Ctrl+S."""
    props: dict[str, Any] = {"content": content, "placeholder": placeholder,
             "param_name": param_name, "toolbar": toolbar}
    if on_save: props["on_save"] = on_save
    if on_change: props["on_change"] = on_change
    return UINode(type="RichEditor", props=props)


def TagInput(
    values: list[str] | None = None,
    suggestions: list[str] | None = None,
    placeholder: str = "Add...",
    param_name: str = "tags",
    on_change: UIAction | None = None,
    grouped_by: str = "",
) -> UINode:
    """Tag/chip input with autocomplete. grouped_by: group suggestions by prefix (e.g. 'extensions:read')."""
    props: dict[str, Any] = {
        "values": values or [],
        "suggestions": suggestions or [],
        "placeholder": placeholder,
        "param_name": param_name,
        "grouped_by": grouped_by,
    }
    if on_change: props["on_change"] = on_change
    return UINode(type="TagInput", props=props)
