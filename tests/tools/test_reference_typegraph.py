# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""B4 — structured type-graph per param (alongside opaque annotation string)."""
from __future__ import annotations

from imperal_sdk.devtools.generate_reference import generate_reference
from imperal_sdk.devtools.reference._introspect import type_graph


# ---------------------------------------------------------------------------
# generate_reference integration
# ---------------------------------------------------------------------------

def test_param_has_structured_type():
    syms = generate_reference()["symbols"]
    for s in syms.values():
        for p in s.get("params", []):
            assert "type" in p, f"missing 'type' key in param {p}"
            assert isinstance(p["type"], dict), f"'type' must be dict, got {type(p['type'])}"
            return
    raise AssertionError("no params found to check")


def test_every_param_has_type_key():
    """Every param in every symbol must carry the 'type' structured field."""
    for sym_name, sym in generate_reference()["symbols"].items():
        for p in sym.get("params", []):
            assert "type" in p, f"{sym_name}.{p['name']} missing 'type'"
            assert isinstance(p["type"], dict), f"{sym_name}.{p['name']} 'type' not dict"


# ---------------------------------------------------------------------------
# type_graph unit tests
# ---------------------------------------------------------------------------

import inspect
import typing


def test_type_graph_no_annotation():
    """Missing annotation → {"kind": "any"}."""
    assert type_graph(inspect.Parameter.empty) == {"kind": "any"}


def test_type_graph_none_type():
    assert type_graph(type(None)) == {"kind": "none"}


def test_type_graph_simple_ref():
    class Foo:
        pass
    assert type_graph(Foo) == {"ref": "Foo"}


def test_type_graph_union_with_none():
    ann = typing.Optional[str]  # Union[str, None]
    result = type_graph(ann)
    assert result["kind"] == "union"
    assert {"ref": "str"} in result["of"]
    assert {"kind": "none"} in result["of"]


def test_type_graph_list():
    ann = typing.List[int]
    result = type_graph(ann)
    assert result == {"kind": "list", "of": {"ref": "int"}}


def test_type_graph_list_no_args():
    result = type_graph(list)
    # bare list has no origin → falls through to __name__ check
    assert result == {"ref": "list"}


def test_type_graph_generic_list():
    ann = list[str]  # py3.9+ style
    result = type_graph(ann)
    assert result == {"kind": "list", "of": {"ref": "str"}}


def test_type_graph_dict():
    ann = typing.Dict[str, int]
    assert type_graph(ann) == {"kind": "dict"}


def test_type_graph_bare_dict():
    result = type_graph(dict)
    assert result == {"ref": "dict"}


def test_type_graph_never_raises():
    """type_graph must never raise — unknown → {"kind": "any"}."""
    import dataclasses

    @dataclasses.dataclass
    class Weird:
        x: int

    # Feed in increasingly exotic annotations
    for ann in [
        None,
        42,
        object(),
        typing.Any,
        typing.Callable[[int], str],
    ]:
        result = type_graph(ann)  # must not raise
        assert isinstance(result, dict)


def test_type_graph_string_annotation():
    """String annotations (PEP 563 forward refs) are treated as named refs."""
    result = type_graph("MyClass")
    assert result == {"ref": "MyClass"}
