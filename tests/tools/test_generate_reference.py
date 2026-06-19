# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Ф1 — sdk-reference.json generator: code is the single owner of API facts.

Covers the WIDENED surface (Valentin 2026-06-19): client methods, ui
components, decorators, sdl roles, sdl helper functions, and result/def
dataclasses — so "everything important is protected".
"""
from __future__ import annotations

import json

import imperal_sdk
from imperal_sdk.devtools.generate_reference import generate_reference
from imperal_sdk.ui.input_components import INPUT_TYPES

ALL_KINDS = {
    "client_method",
    "ui_component",
    "decorator",
    "sdl_role",
    "sdl_func",
    "dataclass",
}


def test_top_level_shape() -> None:
    ref = generate_reference()
    assert set(ref.keys()) == {"sdk_version", "symbols"}
    assert ref["sdk_version"] == imperal_sdk.__version__
    assert isinstance(ref["symbols"], dict) and ref["symbols"]


def test_deterministic() -> None:
    assert generate_reference() == generate_reference()


def test_every_symbol_has_the_pinned_shape() -> None:
    for name, sym in generate_reference()["symbols"].items():
        assert set(sym.keys()) == {"kind", "params", "returns", "enums"}, name
        assert sym["kind"] in ALL_KINDS, (name, sym["kind"])
        assert isinstance(sym["params"], list)
        for p in sym["params"]:
            assert set(p.keys()) == {"name", "annotation", "default", "required"}
        assert isinstance(sym["enums"], dict)


def test_ui_input_symbol_with_enum() -> None:
    sym = generate_reference()["symbols"]["ui.Input"]
    assert sym["kind"] == "ui_component"
    assert sym["returns"] == "UINode"
    pnames = [p["name"] for p in sym["params"]]
    assert "self" not in pnames
    assert "type" in pnames
    type_param = next(p for p in sym["params"] if p["name"] == "type")
    assert type_param["annotation"] == "str"
    assert type_param["default"] == "text"
    assert type_param["required"] is False
    # the enum is read from INPUT_TYPES (the single source), not string-parsed
    assert sym["enums"]["type"] == list(INPUT_TYPES)


def test_client_method_symbol() -> None:
    sym = generate_reference()["symbols"]["ctx.store.query"]
    assert sym["kind"] == "client_method"
    assert sym["returns"] == "Page[Document]"
    pnames = [p["name"] for p in sym["params"]]
    assert "self" not in pnames
    assert pnames[:1] == ["collection"]
    collection = next(p for p in sym["params"] if p["name"] == "collection")
    assert collection["required"] is True and collection["default"] is None
    where = next(p for p in sym["params"] if p["name"] == "where")
    assert where["annotation"] == "dict | None"
    assert where["required"] is False and where["default"] is None
    limit = next(p for p in sym["params"] if p["name"] == "limit")
    assert limit["default"] == 100 and limit["required"] is False


def test_client_billing_method_present() -> None:
    sym = generate_reference()["symbols"]["ctx.billing.get_balance"]
    assert sym["kind"] == "client_method"


def test_decorator_chat_function_present() -> None:
    sym = generate_reference()["symbols"]["chat.function"]
    assert sym["kind"] == "decorator"
    pnames = [p["name"] for p in sym["params"]]
    assert "name" in pnames and "self" not in pnames
    name_param = next(p for p in sym["params"] if p["name"] == "name")
    assert name_param["required"] is True


def test_decorator_ext_webhook_params() -> None:
    sym = generate_reference()["symbols"]["ext.webhook"]
    assert sym["kind"] == "decorator"
    pnames = [p["name"] for p in sym["params"]]
    assert "self" not in pnames
    for expected in ("path", "method", "secret_header"):
        assert expected in pnames, expected
    method = next(p for p in sym["params"] if p["name"] == "method")
    assert method["default"] == "POST" and method["required"] is False
    path = next(p for p in sym["params"] if p["name"] == "path")
    assert path["required"] is True


def test_sdl_role_present() -> None:
    sym = generate_reference()["symbols"]["sdl.Entity"]
    assert sym["kind"] == "sdl_role"
    # at minimum the namespace fact is captured
    assert "namespace" in sym["enums"]


def test_sdl_func_present() -> None:
    sym = generate_reference()["symbols"]["sdl.field"]
    assert sym["kind"] == "sdl_func"
    pnames = [p["name"] for p in sym["params"]]
    assert "role" in pnames


def test_dataclass_present() -> None:
    sym = generate_reference()["symbols"]["ActionResult"]
    assert sym["kind"] == "dataclass"
    assert sym["returns"] is None
    pnames = [p["name"] for p in sym["params"]]
    assert "status" in pnames and "summary" in pnames


def test_all_six_kinds_represented() -> None:
    kinds = {s["kind"] for s in generate_reference()["symbols"].values()}
    assert kinds == ALL_KINDS, kinds


def test_all_defaults_are_json_serializable() -> None:
    json.dumps(generate_reference())  # must not raise
