# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Tests for typed binding-point schemas for free-dict UI children.

Covers ``validate_child(kind, value) -> list[str]``:
  - empty list = valid
  - non-empty list = validation errors (missing required keys, wrong type)

Inner-dict shapes sourced directly from ui/*.py docstrings/signatures:
  tabs       : {label: str, content: object}        — layout.py Tabs
  accordion  : {id: str, title: str, children: any} — layout.py Accordion
  datatable_columns : {key: str, label: str}         — data.py DataColumn
  datatable_rows    : any dict                        — data.py DataTable
  select     : {value: str, label: str}              — input_components.py Select
  timeline   : {title: str, ...}                     — data.py Timeline
  tree       : {id: str, label: str, ...}            — data.py Tree
  menu       : {label: str, ...}                     — interactive.py Menu
"""
from imperal_sdk.ir.ui_children import validate_child


# ---------------------------------------------------------------------------
# tabs
# ---------------------------------------------------------------------------

def test_valid_tabs_shape():
    assert validate_child("tabs", [{"label": "A", "content": {"type": "Card", "props": {}}}]) == []


def test_invalid_tabs_shape_reports():
    errs = validate_child("tabs", [{"wrong": "x"}])
    assert errs  # missing required 'label'


def test_tabs_missing_content_reports():
    errs = validate_child("tabs", [{"label": "Home"}])
    assert errs  # missing required 'content'


def test_tabs_label_wrong_type():
    errs = validate_child("tabs", [{"label": 123, "content": {}}])
    assert errs  # label must be string


# ---------------------------------------------------------------------------
# accordion
# ---------------------------------------------------------------------------

def test_valid_accordion_shape():
    assert validate_child("accordion", [
        {"id": "s1", "title": "Section 1", "children": []}
    ]) == []


def test_accordion_missing_id_reports():
    errs = validate_child("accordion", [{"title": "Section 1", "children": []}])
    assert errs


def test_accordion_missing_title_reports():
    errs = validate_child("accordion", [{"id": "s1", "children": []}])
    assert errs


# ---------------------------------------------------------------------------
# datatable_columns
# ---------------------------------------------------------------------------

def test_valid_datatable_columns_shape():
    assert validate_child("datatable_columns", [
        {"key": "name", "label": "Name"}
    ]) == []


def test_datatable_columns_missing_key_reports():
    errs = validate_child("datatable_columns", [{"label": "Name"}])
    assert errs


def test_datatable_columns_extra_fields_ok():
    # additionalProperties: true — sortable, width, editable all optional
    assert validate_child("datatable_columns", [
        {"key": "name", "label": "Name", "sortable": True, "width": "120px"}
    ]) == []


# ---------------------------------------------------------------------------
# select
# ---------------------------------------------------------------------------

def test_valid_select_shape():
    assert validate_child("select", [{"value": "opt1", "label": "Option 1"}]) == []


def test_select_missing_value_reports():
    errs = validate_child("select", [{"label": "Option 1"}])
    assert errs


def test_select_missing_label_reports():
    errs = validate_child("select", [{"value": "opt1"}])
    assert errs


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------

def test_valid_timeline_shape():
    assert validate_child("timeline", [{"title": "Event A"}]) == []


def test_timeline_missing_title_reports():
    errs = validate_child("timeline", [{"description": "no title"}])
    assert errs


def test_timeline_optional_fields_ok():
    assert validate_child("timeline", [
        {"title": "T", "description": "D", "time": "12:00", "icon": "Bell", "color": "blue"}
    ]) == []


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------

def test_valid_tree_shape():
    assert validate_child("tree", [{"id": "n1", "label": "Node 1"}]) == []


def test_tree_missing_id_reports():
    errs = validate_child("tree", [{"label": "Node 1"}])
    assert errs


def test_tree_missing_label_reports():
    errs = validate_child("tree", [{"id": "n1"}])
    assert errs


def test_tree_children_optional():
    assert validate_child("tree", [
        {"id": "n1", "label": "Root", "children": [{"id": "n2", "label": "Child"}]}
    ]) == []


# ---------------------------------------------------------------------------
# menu
# ---------------------------------------------------------------------------

def test_valid_menu_shape():
    assert validate_child("menu", [{"label": "Delete"}]) == []


def test_menu_missing_label_reports():
    errs = validate_child("menu", [{"icon": "Trash2"}])
    assert errs


def test_menu_separator_ok():
    # separator items may omit label — separator=True is a special case
    assert validate_child("menu", [{"separator": True}]) == []


# ---------------------------------------------------------------------------
# unknown kind
# ---------------------------------------------------------------------------

def test_unknown_kind_returns_error():
    errs = validate_child("nonexistent_kind", [{}])
    assert errs


# ---------------------------------------------------------------------------
# non-array values always error
# ---------------------------------------------------------------------------

def test_non_array_tabs_reports():
    errs = validate_child("tabs", {"label": "A", "content": {}})
    assert errs  # must be array


def test_empty_array_is_valid():
    # Empty array is valid for all kinds (no items to validate)
    assert validate_child("tabs", []) == []
    assert validate_child("accordion", []) == []
    assert validate_child("select", []) == []
