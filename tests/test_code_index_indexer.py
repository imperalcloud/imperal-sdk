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


# ---- code graph phases 2-7: remote identity, chunks, one sync, the SFTP walk ----

def test_git_identity_from_heads_loose_ref_packed_refs_and_config():
    from imperal_sdk.code_index import git_identity
    sha1, sha2 = "a" * 40, "b" * 40
    loose = git_identity({".git/HEAD": b"ref: refs/heads/main\n", ".git/refs/heads/main": (sha1 + "\n").encode(),
                          ".git/config": b'[core]\n[remote "origin"]\n\turl = https://u:tok@git.x.io/r.git\n'})
    assert loose == {"remote": "https://git.x.io/r.git", "branch": "main", "commit": sha1}
    packed = git_identity({".git/HEAD": b"ref: refs/heads/dev", ".git/packed-refs": f"# p\n{sha2} refs/heads/dev\n".encode()})
    assert packed["branch"] == "dev" and packed["commit"] == sha2 and packed["remote"] == ""
    assert git_identity({".git/HEAD": sha1.encode()}) == {"remote": "", "branch": "", "commit": sha1}


def test_chunk_blob_covers_definitions_and_gaps():
    from imperal_sdk.code_index import chunk_blob, scope_facts
    text = "def a():\n    return 1\n\nX = 1\n" + "".join(f"y{i} = {i}\n" for i in range(70))
    chunks = chunk_blob(scope_facts("m.py", text), text)
    assert chunks[0]["def_qualname"] == "a" and chunks[0]["text"].startswith("def a()")
    assert all(c["end_line"] - c["start_line"] < 60 for c in chunks)
    assert {c["def_qualname"] for c in chunks} >= {"a", "X"}


def test_embed_without_a_backend_is_empty_and_a_vector_round_trips(monkeypatch):
    import array
    from imperal_sdk import code_index as ci
    monkeypatch.setattr(ci, "_BACKEND", [None])
    assert ci.embed(["x"]) == [] and ci.embed_query("x") == b""

    class Fake:            # float32 rows with tobytes(), as numpy's are -- the stdlib array is enough here
        def embed(self, texts):
            return [array.array("f", [1.0, 2.0, 3.0]) for _ in texts]

        def embed_query(self, text):
            return array.array("f", [0.5, 0.25, 0.0])
    monkeypatch.setattr(ci, "_BACKEND", [Fake()])
    v = array.array("f")
    v.frombytes(ci.embed(["a"])[0])
    assert list(v) == [1.0, 2.0, 3.0] and len(ci.embed_query("q")) == 12


def test_sync_source_reads_only_changed_and_batches_the_apply(tmp_path):
    import asyncio
    from imperal_sdk import code_index as ci
    plans, applies, reads = [], [], []

    async def plan(items, meta):
        plans.append((items, meta))
        return {"changed": [i["path"] for i in items if i["path"] != "same.py"], "removed": ["gone.py"],
                "have_blobs": []}

    async def apply(**payload):
        applies.append(payload)
        return {"files": len(payload["files"]), "links": 1}

    async def read(paths):
        reads.append(list(paths))
        return {p: {"a.py": b"def a():\n    pass\n", "b.py": b"def a():\n    pass\n",
                    "big.py": b"x" * (ci.MAX_FILE_BYTES + 5), "pyproject.toml": b"[project]\nname='x'\n"}.get(p, b"")
                for p in paths if p != "lost.py"}
    listing = [{"path": p, "size": 10, "mtime": 1.0} for p in ("a.py", "b.py", "same.py", "lost.py", "big.py",
                                                               "pyproject.toml", ".env")]
    out = asyncio.run(ci.sync_source(plan, apply, {"source": "t"}, listing, read, embed_chunks=False))
    assert plans[0][1]["extractor_version"] == ci.EXTRACTOR_VERSION
    assert ".env" not in [i["path"] for i in plans[0][0]] and "same.py" not in reads[0]
    assert len(applies) == 1 and len(applies[0]["blobs"]) == 1 and len(applies[0]["files"]) == 2   # one blob, two files
    assert applies[0]["removed"] == ["gone.py"] and applies[0]["configs"][0]["path"] == "pyproject.toml"
    assert "lost.py" in out["partial_reason"] and "big.py over 1 MB" in out["partial_reason"]
    parts = ci.apply_batches([{"path": "a", "blob": "h1"}, {"path": "b", "blob": "h2"}],
                             [{"hash": "h1", "text": "x" * 10}, {"hash": "h2", "text": "y" * 10}], [], limit=15)
    assert [len(p["blobs"]) for p in parts] == [1, 1] and parts[1]["files"][0]["path"] == "b"


def test_sftp_walk_honours_gitignore_secrets_and_symlinks():
    import asyncio
    from imperal_sdk import code_index as ci

    class E:
        def __init__(self, name, kind, size=10):
            self.filename = name
            self.attrs = type("A", (), {"type": kind, "size": size, "mtime": 5})()

    tree = {"/r": [E("app", 2), E(".git", 2), E("node_modules", 2), E("gen", 2), E("venv2", 2), E(".gitignore", 1),
                   E(".env", 1), E("setup.py", 1), E("link.py", 3), E("pyproject.toml", 1)],
            "/r/app": [E("main.py", 1), E("data.bin", 1)], "/r/gen": [E("x.py", 1)],
            "/r/venv2": [E("pyvenv.cfg", 1), E("lib.py", 1)]}
    files = {"/r/.gitignore": b"gen/\n", "/r/app/main.py": b"print(1)\n", "/r/.git/HEAD": b"ref: refs/heads/main\n",
             "/r/pyproject.toml": b"[project]\n", "/r/setup.py": b"x"}

    class F:
        def __init__(self, data):
            self.data = data

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def read(self, n=-1):
            return self.data

    class S:
        async def readdir(self, p):
            if p not in tree:
                raise OSError(p)
            return tree[p]

        def open(self, p, mode="rb"):
            if p not in files:
                raise OSError(p)
            return F(files[p])
    got = asyncio.run(ci.sftp_list_tree(S(), "/r"))
    assert sorted(i["path"] for i in got["items"]) == ["app/main.py", "pyproject.toml"] and got["os"] == "posix"
    many = asyncio.run(ci.sftp_read_many(S(), "/r", ["app/main.py", "../etc/passwd", ".env"]))
    assert many["files"] == {"app/main.py": b"print(1)\n"} and set(many["skipped"]) == {"../etc/passwd", ".env"}
    meta = asyncio.run(ci.sftp_read_meta(S(), "/r"))
    assert set(meta["files"]) == {".git/HEAD", "pyproject.toml"}        # never setup.py
    assert asyncio.run(ci.sftp_repo_root(S(), "/r/app")) == "/r" and ci.sftp_os("/C:/u/p") == "windows"


def test_an_unchanged_sync_refreshes_the_copy_with_a_meta_only_apply():
    """Nothing changed: no read, one apply with no files -- the vault's synced_at says the copy is current."""
    import asyncio
    from imperal_sdk import code_index as ci
    applies, reads = [], []

    async def plan(items, meta):
        return {"changed": [], "removed": [], "have_blobs": []}

    async def apply(**payload):
        applies.append(payload)
        return {}

    async def read(paths):
        reads.append(paths)
        return {}
    out = asyncio.run(ci.sync_source(plan, apply, {"source": "t"}, [{"path": "a.py", "size": 3, "mtime": 1.0}], read))
    assert not reads and not out["applied"]
    assert len(applies) == 1 and applies[0]["files"] == [] and applies[0]["blobs"] == [] and applies[0]["meta"]["listed_at"]


def test_sftp_reads_never_follow_a_link_and_never_ship_git_credentials():
    """Security review of 6.3.0: a symlinked config / git file or a linked directory leading out of the
    root is never read; only the origin URL (no credentials) leaves the server from .git/config."""
    import asyncio
    from imperal_sdk import code_index as ci

    class A:
        def __init__(self, link):
            self.type = 3 if link else 1

    files = {"/r/.git/HEAD": b"ref: refs/heads/main\n",
             "/r/.git/config": b'[core]\n\tbare = false\n[remote "origin"]\n\turl = https://bob:s3cret@git.x/r.git\n',
             "/r/pyproject.toml": b"[project]\n", "/r/tsconfig.json": b"{}", "/r/app/x.py": b"x = 1\n",
             "/r/out/passwd": b"root:x:0:0\n"}
    links = {"/r/tsconfig.json"}
    real = {"/r/out/passwd": "/etc/passwd"}

    class F:
        def __init__(self, data):
            self.data = data

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def read(self, n=-1):
            return self.data

    class E:
        def __init__(self, name):
            self.filename = name
            self.attrs = A(False)

    class S:
        async def readdir(self, p):
            return [E("pyproject.toml"), E("tsconfig.json"), E(".git"), E("app")]

        async def lstat(self, p):
            return A(p in links)

        async def realpath(self, p):
            return real.get(p, p)

        def open(self, p, mode="rb"):
            if p not in files:
                raise OSError(p)
            return F(files[p])
    meta = asyncio.run(ci.sftp_read_meta(S(), "/r"))
    assert "tsconfig.json" not in meta["files"] and "pyproject.toml" in meta["files"]
    assert b"s3cret" not in meta["files"][".git/config"]
    assert ci.git_identity(meta["files"])["remote"] == "https://git.x/r.git"
    many = asyncio.run(ci.sftp_read_many(S(), "/r", ["app/x.py", "out/passwd", "tsconfig.json"]))
    assert many["files"] == {"app/x.py": b"x = 1\n"} and set(many["skipped"]) == {"out/passwd", "tsconfig.json"}


def test_a_remote_never_carries_credentials_however_it_is_written():
    from imperal_sdk.code_index import clean_remote
    assert clean_remote("https://u:p@ss@host.x/r.git") == "https://host.x/r.git"
    assert clean_remote('"https://bob:tok@git.x:8443/r.git?x=1#f"') == "https://git.x:8443/r.git"
    assert clean_remote("ssh://git@host/r.git") == "ssh://host/r.git"
    assert clean_remote("git@github.com:org/r.git") == "git@github.com:org/r.git"
    assert clean_remote("bob:secret@host:r.git") == "host:r.git"
    assert clean_remote("https://[::1]:9/r") == "https://[::1]:9/r" and clean_remote("http://h:bad/r") == ""
    assert clean_remote("") == "" and clean_remote("a b") == ""


def test_every_apply_part_fits_the_vault_body_cap_as_sent():
    """Live 2026-10-20: a first sync of the kernel repo hit the vault's 8 MiB body cap (413) -- the parts
    were sized by file text alone while each blob also carries its facts and its chunks' vectors."""
    import json
    from imperal_sdk import code_index as ci
    blobs = [{"hash": f"h{i}", "text": "x" * 200_000,
              "facts": {"defs": [{"name": f"d{j}", "qualname": f"q{j}" * 20} for j in range(4000)]}} for i in range(40)]
    files = [{"path": f"f{i}.py", "blob": f"h{i}"} for i in range(40)]
    chunks = [{"blob": f"h{i}", "vector": "A" * 2000, "start_line": k} for i in range(40) for k in range(50)]
    parts = ci.apply_batches(files, blobs, chunks)
    assert len(parts) > 1 and sum(len(p["blobs"]) for p in parts) == 40
    for p in parts:
        assert len(json.dumps(p).encode("utf-8")) <= ci.APPLY_BATCH_BYTES + 64_000
    assert ci.APPLY_BATCH_BYTES <= 4_200_000
