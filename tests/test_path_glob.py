"""One path-glob rule for every tool (gate 2026-11-15: five fnmatch copies, no {a,b}, src/**/*.py missed src/a.py)."""
from imperal_sdk.code_index import path_matches as m


def test_path_matches():
    assert m("imperal-mcp/src/a.py", "{imperal-mcp,webbee}/**/*.py")
    assert m("webbee/x.py", "{imperal-mcp,webbee}/**/*.py")
    assert not m("imperal-sdk/x.py", "{imperal-mcp,webbee}/**/*.py")
    assert m("src/a.py", "src/**/*.py") and m("src/x/y/a.py", "src/**/*.py")
    assert m("deep/a.py", "*.py") and m("App/Main.PY", "app/*.py")
    assert m("core/app/x.py", "app/*.py")          # spelled from a sub-root (vault's rule)
    assert not m("src/a.ts", "src/**/*.py")
    assert m("a.py", "{a,b}.py") and m("b.py", "{a,{b,c}}.py") and m("c.py", "{a,{b,c}}.py")
    assert m("./src/a.py", "src/*.py") and m("src\\a.py", "src/*.py")
