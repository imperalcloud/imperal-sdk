"""Imperal SDK · Declarative UI Components.

Python components that serialize to JSON for Panel rendering.
Usage in extensions:

    from imperal_sdk import ui

    ui.List(items=[
        ui.ListItem(id="1", title="Hello", on_click=ui.Call("read", id="1")),
    ])
    ui.Stat(label="Unread", value=5, color="red")
    ui.Card(title="Summary", content=ui.Text("Hello world"))
"""
from __future__ import annotations

from .components import (
    # Layout
    Stack,
    Grid,
    Tabs,
    # Data display
    Text,
    Badge,
    Avatar,
    Stat,
    List,
    ListItem,
    DataTable,
    Column,
    # Interactive
    Button,
    Icon,
    Card,
    Input,
    # Feedback
    Alert,
    Progress,
    Chart,
)
from .actions import Call, Navigate, Send

__all__ = [
    "Stack", "Grid", "Tabs",
    "Text", "Badge", "Avatar", "Stat", "List", "ListItem", "DataTable", "Column",
    "Button", "Icon", "Card", "Input",
    "Alert", "Progress", "Chart",
    "Call", "Navigate", "Send",
]
