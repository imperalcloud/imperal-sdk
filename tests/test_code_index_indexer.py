import pytest
pytest.importorskip("tree_sitter")  # skip when the intel extra isn't installed
from imperal_sdk import code_index as indexer
from imperal_sdk.code_index import ProjectIndex


def test_parse_python_symbols(tmp_path):
    src = "def alpha(x):\n    return beta(x)\n\nclass Gamma:\n    def method(self):\n        pass\n"
    fi = indexer.parse_file("m.py", src)
    names = {s.name for s in fi.symbols}
    assert {"alpha", "Gamma", "method"} <= names
    a = next(s for s in fi.symbols if s.name == "alpha")
    assert a.kind == "function" and a.start_line == 1


def test_parse_ts_symbols():
    fi = indexer.parse_file("m.ts", "export function widget(a: number){ return a }\nclass Box {}\n")
    names = {s.name for s in fi.symbols}
    assert "widget" in names and "Box" in names


def test_unsupported_ext_is_line_only_not_crash():
    fi = indexer.parse_file("data.bin", "\x00\x01binary")
    assert fi is not None and fi.symbols == [] and fi.lang == "other"


def test_build_index(tmp_path):
    (tmp_path / "a.py").write_text("def a():\n    return b()\n")
    (tmp_path / "b.py").write_text("def b():\n    return 1\n")
    idx = indexer.build_index(str(tmp_path), ["a.py", "b.py"])
    assert isinstance(idx, ProjectIndex)
    assert set(idx.files) == {"a.py", "b.py"}
    assert any(s.name == "a" for s in idx.files["a.py"].symbols)


def test_def_own_name_is_not_recorded_as_a_ref():
    # A def's own name-identifier must not land in fi.refs -- otherwise the
    # defining file counts itself as a "caller"/"dependent" of its own
    # symbol, inflating callers_of/impact_of_change with a false positive.
    src = "def alpha():\n    return 1\n"
    fi = indexer.parse_file("m.py", src)
    assert "alpha" not in fi.refs


def test_nested_def_inside_class_still_discovered_after_name_exclusion():
    # The name-node exclusion must not break traversal into a def's body --
    # nested/inner defs (e.g. methods) still need to be found.
    src = "class Gamma:\n    def method(self):\n        return other()\n"
    fi = indexer.parse_file("m.py", src)
    names = {s.name for s in fi.symbols}
    assert {"Gamma", "method"} <= names
    assert "other" in fi.refs        # the call inside the method body is still a ref
    assert "method" not in fi.refs   # but the method's own name is not


def test_build_index_stays_inside_the_root(tmp_path):
    import os
    from imperal_sdk.code_index import build_index
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("def a():\n    return 1\n")
    outside = tmp_path / "secret.py"
    outside.write_text("def leaked():\n    pass\n")
    os.symlink(outside, root / "link.py")
    idx = build_index(str(root), ["a.py", "../secret.py", str(outside), "link.py"])
    assert set(idx.files) == {"a.py"}


def test_ts_schema_regex_is_bounded():
    import time
    from imperal_sdk.code_index import _TS_SCHEMA
    text = "interface X extends " + "a" * 200000
    t0 = time.monotonic()
    _TS_SCHEMA.findall(text)
    assert time.monotonic() - t0 < 2.0
    m = _TS_SCHEMA.search("export interface User { id: string; name?: string }")
    assert m and m.group(1) == "User" and "id" in m.group(2)
