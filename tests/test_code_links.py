"""imperal_sdk.code_links: the vault's link rules, computed locally (2026-11-06 report: a function with no caller
answered 481 files when links were made by bare name)."""
from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_python")

from imperal_sdk import code_index as ci  # noqa: E402
from imperal_sdk.code_links import Linker, impact, resolve_module, module_index  # noqa: E402


def _linker(files: dict, configs: list | None = None) -> Linker:
    return Linker({p: ci.scope_facts(p, t) for p, t in files.items()}, configs or [])


PY = {
    "pkg/__init__.py": "from .core import compute as compute_total\n",
    "pkg/core.py": (
        "def compute(x):\n    return helper(x)\n\n\ndef helper(x):\n    return x\n\n\n"
        "def lonely():\n    return 1\n\n\nclass Cart:\n    def total(self):\n        return self.sum()\n\n"
        "    def sum(self):\n        return 0\n"),
    "app/use.py": "from pkg import compute_total\n\n\ndef run():\n    return compute_total(1)\n",
    "app/deep.py": "from app.use import run\n\n\ndef outer():\n    return run()\n",
    "app/other.py": "def go(obj):\n    return obj.lonely()\n\n\ndef unrelated():\n    return 2\n",
    "tests/test_core.py": "from pkg.core import compute\n\n\ndef test_compute():\n    assert compute(2) == 2\n",
}


def test_a_function_nobody_calls_has_no_dependents():
    out = impact(_linker(PY), ["lonely"])
    assert out["data"]["items"] == [] and out["resolved"] == ["pkg/core.py::lonely"]
    # obj.lonely() binds to nothing the resolver can prove: listed apart, by name only -- never a resolved link
    assert [b["path"] for b in out["by_name"]] == ["app/other.py"] and out["by_name_count"] == 1


def test_reexport_alias_and_depth_through_the_enclosing_def_only():
    out = impact(_linker(PY), ["compute"], depth=2)
    items = {i["id"]: i for i in out["data"]["items"]}
    # pkg/__init__.py only re-exports (an import, no use): no user, as in the vault
    assert set(items) == {"app/use.py", "tests/test_core.py", "app/deep.py"}
    assert items["app/use.py"]["depth"] == 1 and items["app/use.py"]["user"] == "run"
    assert items["app/deep.py"]["depth"] == 2 and items["app/deep.py"]["user"] == "outer"
    assert "app/other.py" not in items                       # shares no link, never pulled in by a file's other defs
    groups = [i["group"] for i in out["data"]["items"]]
    assert groups == sorted(groups, key=lambda g: g == "tests")   # code before tests


def test_self_member_and_same_file_users():
    lk = _linker(PY)
    assert lk.resolve_ref("pkg/core.py", "self", "sum", "Cart.total") == ("pkg/core.py", "Cart.sum", "self")
    out = impact(lk, ["helper"])
    assert out["data"]["items"] == [] and out["same_file"][0]["user"] == "compute"


def test_unknown_symbol_is_said_not_scanned():
    out = impact(_linker(PY), ["does_not_exist"])
    assert out["resolved"] == [] and out["data"]["items"] == [] and out["by_name"] == []


def test_qualified_forms():
    lk = _linker(PY)
    assert lk.symbol_targets("pkg/core.py::Cart.sum") == [("pkg/core.py", "Cart.sum")]
    assert lk.symbol_targets("Cart.sum") == [("pkg/core.py", "Cart.sum")]
    assert lk.symbol_targets("pkg/core.py") == [("pkg/core.py", "")]


def test_typescript_paths_and_index():
    pytest.importorskip("tree_sitter_typescript")
    files = {
        "tsconfig.json": "",
        "src/lib/index.ts": "export function fmt(x: number) { return String(x) }\nexport function unused() { return 1 }\n",
        "src/app.ts": "import { fmt } from '@/lib'\nexport function show() { return fmt(1) }\n",
    }
    facts = {p: ci.scope_facts(p, t) for p, t in files.items() if p.endswith(".ts")}
    lk = Linker(facts, [{"path": "tsconfig.json", "kind": "tsconfig",
                         "data": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}])
    assert [i["id"] for i in impact(lk, ["fmt"])["data"]["items"]] == ["src/app.ts"]
    assert impact(lk, ["unused"])["data"]["items"] == []


def test_resolve_module_is_the_vaults():
    mods = module_index(["src/a/__init__.py", "src/a/b.py"], [])
    assert resolve_module(mods, "src/a/__init__.py", ".b", "python") == "src/a/b.py"
    assert resolve_module(mods, "x.py", "a.b", "python") == "src/a/b.py"
    assert resolve_module(mods, "x.py", "requests", "python") is None


FOLDER = {
    "core/wpanel-sdk/pyproject.toml": '[project]\nname = "wpanel-sdk"\n[tool.setuptools.packages.find]\nwhere = ["src"]\n',
    "core/wpanel-sdk/src/wpanel_sdk/__init__.py": "",
    "core/wpanel-sdk/src/wpanel_sdk/ui/__init__.py": "class IRNode:\n    pass\n",
    "modules/wpanel-tickets/wpanel_tickets/__init__.py": "",
    "modules/wpanel-tickets/wpanel_tickets/screens.py": "from wpanel_sdk.ui import IRNode\n\n\ndef screen():\n"
                                                        "    return IRNode()\n",
    # two repos with the same top-level package name and no __init__ above it (namespace packages)
    "gateway/app/sessions.py": "def session_for_sid(sid):\n    return sid\n",
    "gateway/app/routes.py": "from app.sessions import session_for_sid\n\n\ndef me(sid):\n    return session_for_sid(sid)\n",
    "billing/app/sessions.py": "def session_for_sid(sid):\n    return None\n",
    "billing/app/api.py": "from app.sessions import session_for_sid\n\n\ndef pay(sid):\n    return session_for_sid(sid)\n",
    "check-paths-agree.py": "print('IRNode')\n",
}


def _folder_linker(roots):
    facts, configs = {}, []
    for p, t in FOLDER.items():
        if p.endswith(".toml"):
            kind, data = ci.parse_config(p, t)
            configs.append({"path": p, "kind": kind, "data": data})
        else:
            facts[p] = ci.scope_facts(p, t)
    return Linker(facts, configs, roots)


def test_a_folder_of_repositories_resolves_each_import_in_its_own_repository():
    """06.11 #2: a folder indexed as one -- absolute imports from each repository's own root, a package another
    repository provides by its name."""
    lk = _folder_linker(["core/wpanel-sdk", "modules/wpanel-tickets", "gateway", "billing"])
    assert [i["id"] for i in impact(lk, ["IRNode"])["data"]["items"]] == ["modules/wpanel-tickets/wpanel_tickets/screens.py"]
    assert [i["id"] for i in impact(lk, ["gateway/app/sessions.py::session_for_sid"])["data"]["items"]] == \
        ["gateway/app/routes.py"]
    assert [i["id"] for i in impact(lk, ["billing/app/sessions.py::session_for_sid"])["data"]["items"]] == \
        ["billing/app/api.py"]



def test_the_summary_never_reads_as_no_callers_when_names_match():
    out = impact(_linker(PY), ["lonely"])
    assert out["data"]["items"] == [] and "no file uses lonely by a resolved link" in out["summary"]
    assert "1 more file(s) only mention the name" in out["summary"] and "before concluding" in out["summary"]
    assert impact(_linker(PY), ["compute"])["summary"].startswith("3 file(s) use compute by resolved links")
    assert "not a definition" in impact(_linker(PY), ["nope"])["summary"]


def test_python_members_through_typed_locals_fields_and_returns():
    lk = _linker({
        "repo.py": "class Repo:\n    def save(self):\n        return 1\n\n\ndef make_repo() -> 'Repo':\n    return Repo()\n\n\n"
                   "def open_repo() -> Repo:\n    return Repo()\n",
        "svc.py": "from typing import Optional\nfrom repo import Repo, open_repo\n\n\nclass Svc:\n"
                  "    def __init__(self, repo: Repo):\n        self.repo = repo\n\n    def run(self):\n"
                  "        return self.repo.save()\n\n\ndef a():\n    r = Repo()\n    return r.save()\n\n\n"
                  "def b(r: Optional[Repo]):\n    return r.save()\n\n\ndef c():\n    r = open_repo()\n    return r.save()\n\n\n"
                  "def d(x):\n    return x.save()\n",
    })
    got = impact(lk, ["Repo.save"])
    users = {c["user"] for i in got["data"]["items"] for c in i["callers"]}
    assert users == {"Svc.run", "a", "b", "c"}             # d's x is untyped: by name only, never a resolved link
    assert got["by_name"] == [] or all(b["path"] != "svc.py" for b in got["by_name"])



def test_a_member_of_an_unannotated_call_result_is_never_linked_to_the_call():
    """A spot check of real links found ``vs.to_arrays()`` linked to ``VectorStore.from_arrays`` (vs came from it)."""
    lk = _linker({"v.py": "class VectorStore:\n    @classmethod\n    def from_arrays(cls, a):\n        return cls()\n\n"
                          "    def to_arrays(self):\n        return 1\n",
                  "u.py": "from v import VectorStore\n\n\ndef go():\n    vs = VectorStore.from_arrays(1)\n"
                          "    return vs.to_arrays()\n"})
    got = {(l[3], l[5]) for l in lk.links() if l[0] == "u.py"}
    assert (5, "VectorStore.from_arrays") in got and (6, "VectorStore.from_arrays") not in got
