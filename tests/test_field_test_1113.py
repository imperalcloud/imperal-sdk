"""imperal-mcp field test 2026-11-13: what search_code, impact_of_change and contract_slice missed."""
import pytest

pytest.importorskip("tree_sitter")

from imperal_sdk.code_index import extract_contracts, parse_file, scope_facts  # noqa: E402
from imperal_sdk.code_links import Linker  # noqa: E402

TSX = '''/** Login page of the panel. */
export default function LoginPage() {
  /** Finish the sign-in after the code is approved. */
  const completeSignIn = async () => { return 1 };
  const handleLogin = () => { completeSignIn() };
  const count = 3;
  return null
}
'''


def test_arrow_functions_inside_a_component_are_definitions_with_their_docs():
    defs = {d.qualname: d for d in scope_facts("src/app/page.tsx", TSX).defs}
    assert "LoginPage.completeSignIn" in defs and "LoginPage.handleLogin" in defs
    assert "LoginPage.count" not in defs                      # a local value is no definition
    syms = {s.name: s for s in parse_file("src/app/page.tsx", TSX).symbols}
    assert {"LoginPage", "completeSignIn", "handleLogin"} <= set(syms) and "count" not in syms
    assert syms["completeSignIn"].doc.startswith("Finish the sign-in") and syms["LoginPage"].doc


def test_a_python_module_constant_is_a_symbol_and_functions_carry_their_docstring():
    py = 'PANEL_ORIGIN = "https://x"\n\n\ndef build_url(p):\n    """Join the panel origin with a path."""\n    return PANEL_ORIGIN + p\n'
    syms = {s.name: s for s in parse_file("app/config.py", py).symbols}
    assert syms["PANEL_ORIGIN"].kind == "variable" and syms["build_url"].doc.startswith("Join the panel")


def test_an_import_alone_is_named_by_name_never_hidden():
    # an import with no use stays no resolved user (as in the vault: test_reexport_alias_...), but impact names it
    from imperal_sdk.code_links import impact
    files = {"config.py": 'PANEL_ORIGIN = "https://x"\n', "onlyimport.py": "from config import PANEL_ORIGIN\n"}
    out = impact(Linker({p: scope_facts(p, t) for p, t in files.items()}), ["PANEL_ORIGIN"])
    assert [b["path"] for b in out.get("by_name") or []] == ["onlyimport.py"]


def test_a_projects_own_route_decorator_declares_an_endpoint():
    src = ('@door("/v1/panel/redirect", methods=["GET"])\nasync def redirect(r):\n    return 1\n\n'
           '@door(path="/v1/x", method="POST")\ndef make_x(r):\n    return 2\n\n'
           '@lru_cache(128)\ndef cached():\n    return 3\n\n@retry("again")\ndef r2():\n    return 4\n')
    eps, _ = extract_contracts("app/routes.py", src, "python")
    assert sorted((e.method, e.route, e.handler) for e in eps) == [
        ("GET", "/v1/panel/redirect", "redirect"), ("POST", "/v1/x", "make_x")]
