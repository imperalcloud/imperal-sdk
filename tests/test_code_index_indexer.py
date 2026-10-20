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


# ---- one language table, file rules (code graph phase 1, Task 1) ----

def test_tsx_with_jsx_parses_with_the_tsx_grammar():
    from imperal_sdk.code_index import language
    from tree_sitter import Parser
    src = 'export function A() { return <div className="x"/>; }'
    tree = Parser(language("tsx")).parse(src.encode())
    assert not tree.root_node.has_error
    fi = indexer.parse_file("ui/A.tsx", src)
    assert fi.lang == "tsx" and [s.name for s in fi.symbols] == ["A"]


def test_one_table_and_the_old_private_names_stay_aliases():
    assert indexer.LANG_BY_EXT[".tsx"] == "tsx" and indexer.LANG_BY_EXT[".mjs"] == "javascript"
    assert indexer.LANG_BY_EXT[".cjs"] == "javascript"
    assert indexer.DEF_NODES["typescript"]["type_alias_declaration"] == "type"
    assert indexer.DEF_NODES["typescript"]["enum_declaration"] == "class"
    assert indexer._DEF_NODES is indexer.DEF_NODES and indexer._get_language is indexer.language
    assert indexer.EXTRACTOR_VERSION == "2" and indexer.MAX_FILE_BYTES == 1_048_576
    assert indexer.MAX_REPO_FILES == 20_000


def test_normalised_text_and_blob_identity():
    from imperal_sdk.code_index import blob_hash, normalise_text
    assert normalise_text(b"a\r\nb") == normalise_text(b"a\nb") == "a\nb"
    assert normalise_text(b"\xef\xbb\xbfa\r\n") == "a\n"
    assert normalise_text(b"\xff\xfe" + "x\r\ny".encode("utf-16-le")) == "x\ny"
    assert normalise_text(b"\xfe\xff" + "z".encode("utf-16-be")) == "z"
    assert normalise_text(b"\x00\xff\x00") is None
    assert blob_hash(normalise_text(b"a\r\nb")) == blob_hash(normalise_text(b"a\nb"))


def test_canonical_path_keeps_the_case_and_any_spelling():
    from imperal_sdk.code_index import canonical_path
    assert canonical_path("/C:/Users/u/proj/Pkg\\Foo.py", "/C:/Users/u/proj", windows=True) == "Pkg/Foo.py"
    assert canonical_path("C:\\Users\\u\\proj\\Pkg\\Foo.py", "/c:/users/U/proj", windows=True) == "Pkg/Foo.py"
    assert canonical_path("/srv/App/Pkg/Foo.py", "/srv/App") == "Pkg/Foo.py"
    assert canonical_path("/srv/app/Pkg/Foo.py", "/srv/App") == "/srv/app/Pkg/Foo.py"   # POSIX: case is identity
    assert canonical_path("./a//b/../c.py", "") == "a/c.py"


def test_indexable_code_config_and_never():
    from imperal_sdk.code_index import indexable
    assert indexable("app/x.py") == "code" and indexable("src/a.mjs") == "code"
    assert indexable("tsconfig.base.json") == "config" and indexable("package.json") == "config"
    assert indexable("pyproject.toml") == "config" and indexable("setup.cfg") == "config"
    for never in (".env.prod", "keys/id_ed25519", "setup.py", "node_modules/a/b.js", ".venv/lib/x.py",
                  "certs/a.pem", "secrets/token.py", ".ssh/config", ".git/objects/x", "dist/a.js", "a.key"):
        assert indexable(never) is None, never


# ---- scope facts (Task 2) ----

def _facts(path, text):
    from imperal_sdk.code_index import BlobFacts, scope_facts
    f = scope_facts(path, text)
    assert BlobFacts.from_dict(f.to_dict()) == f
    return f


def test_python_alias_binding_and_reference_chain():
    from imperal_sdk.code_index import Binding, Ref
    f = _facts("m.py", "import a.b as x\nx.f()\n")
    assert Binding("x", "a.b", None, "import", 1) in f.bindings
    assert Ref("x", "f", None, "call", 2) in f.refs


def test_python_relative_alias_call_inside_a_def():
    from imperal_sdk.code_index import Binding, Ref
    f = _facts("svc_user.py", "from .svc import cancel as c\ndef run():\n    c()\n")
    assert Binding("c", ".svc", "cancel", "import", 1) in f.bindings
    assert Ref("c", "", "run", "call", 3) in f.refs


def test_python_class_method_self_and_inheritance():
    from imperal_sdk.code_index import Ref
    f = _facts("k.py", "class A(Base):\n    def m(self):\n        self.n()\n    def n(self):\n        pass\n")
    assert {(d.qualname, d.kind) for d in f.defs} >= {("A", "class"), ("A.m", "method"), ("A.n", "method")}
    assert Ref("Base", "", None, "inherit", 1) in f.refs
    assert Ref("self", "n", "A.m", "call", 3) in f.refs


def test_python_init_reexport_and_all_decides_exported():
    f = _facts("pkg/__init__.py", "from .x import y\n__all__ = ['y']\n")
    assert [(b.local_name, b.module, b.imported, b.kind) for b in f.bindings] == [("y", ".x", "y", "reexport")]
    g = _facts("m.py", "__all__ = ['pub']\ndef pub(): pass\ndef other(): pass\ndef _hidden(): pass\n")
    assert {d.name: d.exported for d in g.defs} == {"pub": True, "other": False, "_hidden": False}
    h = _facts("n.py", "def pub(): pass\ndef _hidden(): pass\n")
    assert {d.name: d.exported for d in h.defs} == {"pub": True, "_hidden": False}


def test_ts_imports_reexports_this_and_default_export():
    from imperal_sdk.code_index import Binding, Ref
    f = _facts("web/m.ts", 'import { b as c } from "./a"; c();\nimport * as ns from "@/lib/x"; ns.go();\n'
                           'export { y } from "./x";\nexport * from "./z";\n'
                           'export class K { m() { this.n(); } n() {} }\nconst f = () => {}; export default f;\n')
    assert Binding("c", "./a", "b", "import", 1) in f.bindings and Ref("c", "", None, "call", 1) in f.refs
    assert Binding("ns", "@/lib/x", None, "import", 2) in f.bindings and Ref("ns", "go", None, "call", 2) in f.refs
    assert Binding("y", "./x", "y", "reexport", 3) in f.bindings
    assert Binding("*", "./z", None, "star", 4) in f.bindings
    assert Ref("this", "n", "K.m", "call", 5) in f.refs
    assert {d.qualname: d.exported for d in f.defs} == {"K": True, "K.m": True, "K.n": True, "f": True}


def test_parse_file_keeps_its_file_index():
    fi = indexer.parse_file("m.py", "def a():\n    return b()\n")
    assert [s.name for s in fi.symbols] == ["a"] and "b" in fi.refs and fi.content_hash
