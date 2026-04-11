"""Imperal SDK · Declarative UI Components.

Python components that serialize to JSON for Panel rendering.
Usage in extensions:

    from imperal_sdk import ui

    ui.List(items=[
        ui.ListItem(id="1", title="Hello", on_click=ui.Call("read", id="1")),
    ])
    ui.Stat(label="Unread", value=5, color="red")
    ui.Card(title="Summary", content=ui.Text("Hello world"))
    ui.Form(children=[ui.Input(placeholder="Name")], submit_label="Save")
"""
from __future__ import annotations

from .layout import Stack, Grid, Tabs, Page, Section, Row, Column, Accordion
from .data import (
    ListItem, List, DataColumn, DataTable, Stat, Stats,
    Badge, Avatar, Timeline, Tree, KeyValue,
)
from .display import Text, Icon, Header, Image, Code, Markdown, Empty, Divider
from .interactive import Button, Card, Menu, Dialog, Tooltip, Link, SlideOver
from .feedback import Alert, Progress, Chart, Loading, Error
from .input_components import (
    Input, Form, Select, MultiSelect, Toggle,
    Slider, DatePicker, FileUpload, TextArea, RichEditor, TagInput,
)
from .actions import Call, Navigate, Send

__all__ = [
    # Layout
    "Stack", "Grid", "Tabs", "Page", "Section", "Row", "Column", "Accordion",
    # Data
    "ListItem", "List", "DataColumn", "DataTable", "Stat", "Stats",
    "Badge", "Avatar", "Timeline", "Tree", "KeyValue",
    # Display
    "Text", "Icon", "Header", "Image", "Code", "Markdown", "Empty", "Divider",
    # Interactive
    "Button", "Card", "Menu", "Dialog", "Tooltip", "Link", "SlideOver",
    # Feedback
    "Alert", "Progress", "Chart", "Loading", "Error",
    # Input
    "Input", "Form", "Select", "MultiSelect", "Toggle",
    "Slider", "DatePicker", "FileUpload", "TextArea", "RichEditor", "TagInput",
    # Actions
    "Call", "Navigate", "Send",
]
