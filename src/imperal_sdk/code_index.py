"""Code index: one code file -> its symbols, imports, references and contracts.

Moved from the Webbee Code client (webbee/intel/models.py, contracts.py, indexer.py,
2026-10-20) so the client and the Imperal kernel share ONE extractor
(spec: docs/superpowers/specs/2026-10-19-code-graph-everywhere-design.md, ipw-repo).
tree-sitter is imported lazily: install the ``code-index`` extra to parse code.
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable


# ---- models (from webbee/intel/models.py) ----

@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str            # "function" | "class" | "method" | "symbol"
    path: str            # workspace-relative
    start_line: int
    end_line: int
    signature: str = ""


@dataclass
class FileIndex:
    path: str
    lang: str            # "python" | "typescript" | "javascript" | "other"
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)   # imported module/path strings
    refs: list[str] = field(default_factory=list)      # referenced identifier names (for the graph)
    content_hash: str = ""
    endpoints: list[dict] = field(default_factory=list)
    schemas: list[dict] = field(default_factory=list)


@dataclass
class ProjectIndex:
    files: dict[str, FileIndex] = field(default_factory=dict)
    git_ref: str = ""


# ---- contracts (from webbee/intel/contracts.py) ----

"""Deterministic endpoint/schema evidence extraction.

This is deliberately a projection over source snapshots, not a second source
of truth. Every record carries file+line provenance and is rebuilt from the
content-addressed repository index. Unsupported syntax is simply absent; no
LLM inference is stored as fact.
"""


_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head"})


@dataclass(frozen=True)
class EndpointEvidence:
    method: str
    route: str
    handler: str
    path: str
    line: int
    schema_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SchemaEvidence:
    name: str
    schema_kind: str
    path: str
    line: int
    fields: tuple[str, ...] = ()
    storage_name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    return ""


def _literal_string(node) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _annotation_names(node) -> set[str]:
    if node is None:
        return set()
    names = set()
    for part in ast.walk(node):
        n = _name(part)
        if n and n.split(".")[-1][:1].isupper():
            names.add(n.split(".")[-1])
    return names


_ROUTER_CTORS = frozenset({"APIRouter", "Blueprint", "FastAPI", "Flask"})


def _router_prefixes(tree) -> dict:
    """``name -> prefix`` of the routers this module builds (``router = APIRouter(prefix="/api")``,
    ``Blueprint("x", __name__, url_prefix="/x")``): a route is the router's prefix + its path."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                and _name(node.value.func).split(".")[-1] in _ROUTER_CTORS:
            prefix = next((_literal_string(k.value) for k in node.value.keywords
                           if k.arg in ("prefix", "url_prefix")), "")
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = prefix
    return out


def _route_of(prefixes: dict, owner: str, route: str) -> str:
    """The full route (the router's prefix + the path; a FastAPI router path may be "" under a
    prefix), or "" when it is not a route."""
    full = prefixes.get(owner, "") + route
    return full if full.startswith("/") else ""


def _methods_kw(call) -> list:
    for kw in call.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
            return [m.lower() for m in (_literal_string(e) for e in kw.value.elts) if m]
    return []


def _endpoint_refs(fn, call) -> tuple:
    refs = set()
    if fn is not None:
        for arg in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs):
            refs.update(_annotation_names(arg.annotation))
        refs.update(_annotation_names(fn.returns))
    for kw in call.keywords:
        if kw.arg in {"response_model", "request_model", "model"}:
            refs.update(_annotation_names(kw.value))
    return tuple(sorted(refs))


def _python_contracts(path: str, text: str):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return [], []
    prefixes = _router_prefixes(tree)
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    endpoints, schemas = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_api_route" and len(node.args) >= 2:
            # router.add_api_route("/x", handler, methods=["GET"])
            owner, route = _name(node.func.value), _literal_string(node.args[0])
            full, handler = _route_of(prefixes, owner, route), _name(node.args[1])
            for method in (_methods_kw(node) or ["get"]):
                if full and method in _HTTP_METHODS:
                    endpoints.append(EndpointEvidence(method.upper(), full, handler.split(".")[-1], path,
                                                      node.lineno, _endpoint_refs(funcs.get(handler), node)))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                verb = dec.func.attr.lower()
                route = _literal_string(dec.args[0]) if dec.args else ""
                full = _route_of(prefixes, _name(dec.func.value), route)
                # @router.get(...), and @app.route / @router.api_route(..., methods=[...])
                methods = [verb] if verb in _HTTP_METHODS else (
                    _methods_kw(dec) or ["get"] if verb in ("route", "api_route") else [])
                for method in methods:
                    if not full or method not in _HTTP_METHODS:
                        continue
                    endpoints.append(EndpointEvidence(
                        method.upper(), full, node.name, path,
                        getattr(dec, "lineno", node.lineno), _endpoint_refs(node, dec)))
        elif isinstance(node, ast.ClassDef):
            bases = {_name(b).split(".")[-1] for b in node.bases}
            is_model = bool(bases & {"BaseModel", "TypedDict", "Schema", "Serializer"})
            is_table = bool(bases & {"Base", "DeclarativeBase", "Model"})
            if not (is_model or is_table):
                continue
            fields, storage = set(), ""
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.add(stmt.target.id)
                elif isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "__tablename__":
                                storage = _literal_string(stmt.value)
                            elif isinstance(stmt.value, ast.Call):
                                call = _name(stmt.value.func).split(".")[-1]
                                if call in {"Column", "mapped_column", "Field"}:
                                    fields.add(target.id)
            schemas.append(SchemaEvidence(
                node.name, "table" if is_table else "model", path, node.lineno,
                tuple(sorted(fields)), storage))
    return endpoints, schemas


_TS_ENDPOINT = re.compile(
    r"(?m)\b(?:app|router|server)\s*\.\s*(get|post|put|patch|delete|options|head)"
    r"\s*\(\s*([\"'])(/[^\"']*)\2\s*,\s*([A-Za-z_$][\w$]*)"
)
_TS_SCHEMA = re.compile(
    r"(?ms)\b(?:export\s+)?(?:interface|type|class)\s+([A-Za-z_$][\w$]*)"
    r"(?:\s+extends[^\{=]{1,500})?\s*(?:\{|=\s*\{)([^}]{0,20000})\}"
)
_TS_FIELD = re.compile(r"(?m)^\s*([A-Za-z_$][\w$]*)\s*\??\s*:")


def _typescript_contracts(path: str, text: str):
    endpoints = [EndpointEvidence(
        m.group(1).upper(), m.group(3), m.group(4), path,
        text.count("\n", 0, m.start()) + 1)
        for m in _TS_ENDPOINT.finditer(text)]
    schemas = []
    for m in _TS_SCHEMA.finditer(text):
        schemas.append(SchemaEvidence(
            m.group(1), "model", path, text.count("\n", 0, m.start()) + 1,
            tuple(sorted(set(_TS_FIELD.findall(m.group(2)))))))
    return endpoints, schemas


_NEXT_HANDLER = re.compile(
    r"(?m)^\s*export\s+(?:async\s+)?(?:function\s+|const\s+)(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b")
_NEXT_APP_ROUTE = re.compile(r"(?:^|/)app/(.*?)/?route\.(?:ts|tsx|js|jsx|mjs)$")
_NEXT_PAGES_API = re.compile(r"(?:^|/)pages/(api(?:/.*?)?)(?:/index)?\.(?:ts|tsx|js|jsx)$")


def _next_route(segments: str) -> str:
    """A Next.js file route: route groups ``(x)`` and parallel slots ``@x`` vanish."""
    parts = [p for p in segments.split("/") if p and not (p.startswith("(") and p.endswith(")"))
             and not p.startswith("@")]
    return "/" + "/".join(parts)


def _next_contracts(path: str, text: str):
    """Next.js route handlers: ``app/**/route.ts`` exporting GET/POST/..., and ``pages/api/**``."""
    p = path.replace("\\", "/")
    m = _NEXT_APP_ROUTE.search(p)
    if m:
        route = _next_route(m.group(1))
        return [EndpointEvidence(h.group(1), route, h.group(1), path, text.count("\n", 0, h.start()) + 1)
                for h in _NEXT_HANDLER.finditer(text)]
    m = _NEXT_PAGES_API.search(p)
    if m and re.search(r"(?m)^\s*export\s+default\b", text):
        return [EndpointEvidence("ANY", _next_route(m.group(1)), "default", path, 1)]
    return []


def extract_contracts(path: str, text: str, lang: str):
    if lang == "python":
        return _python_contracts(path, text)
    if lang in {"typescript", "javascript"}:
        endpoints, schemas = _typescript_contracts(path, text)
        return endpoints + _next_contracts(path, text), schemas
    return [], []


def match_contracts(repos: Iterable[dict]) -> list[dict]:
    """Build deterministic cross-repo links from exact contract identities.

    Endpoint route+method and schema names are intentionally exact. Semantic
    guesses belong in retrieval ranking, never in the evidence graph.
    """
    repos = sorted(repos, key=lambda r: r.get("repo_key", ""))
    out = []
    for i, left in enumerate(repos):
        for right in repos[i + 1:]:
            lk, rk = left.get("repo_key", ""), right.get("repo_key", "")
            le = {(x.method, x.route): x for x in left.get("endpoints", ())}
            re_ = {(x.method, x.route): x for x in right.get("endpoints", ())}
            for key in sorted(le.keys() & re_.keys()):
                out.append({"relation": "endpoint_identity", "source_repo": lk,
                            "target_repo": rk, "identity": f"{key[0]} {key[1]}"})
            # A schema contract can be declared as a concrete model/table OR
            # referenced by an endpoint annotation/response_model. Both are
            # deterministic source evidence; including references lets a
            # producer endpoint link to a consumer's shared DTO even when the
            # producer imports that DTO from another package.
            def schema_names(repo):
                names = {x.name for x in repo.get("schemas", ())}
                for endpoint in repo.get("endpoints", ()):
                    names.update(endpoint.schema_refs)
                return names

            for name in sorted(schema_names(left) & schema_names(right)):
                source, target = sorted((lk, rk))
                out.append({"relation": "schema_name_match", "source_repo": source,
                            "target_repo": target, "identity": name})
    return out


# ---- indexer (from webbee/intel/indexer.py) ----

LANG_BY_EXT = {".py": "python", ".ts": "typescript", ".tsx": "typescript",
               ".js": "javascript", ".jsx": "javascript"}

# tree-sitter Language handles are lazy-loaded + cached (import cost is real).
_LANG_CACHE: dict = {}


def _get_language(lang: str):
    if lang in _LANG_CACHE:
        return _LANG_CACHE[lang]
    try:
        if lang == "python":
            import tree_sitter_python as ts_py
            from tree_sitter import Language
            obj = Language(ts_py.language())
        elif lang == "typescript":
            import tree_sitter_typescript as ts_ts
            from tree_sitter import Language
            obj = Language(ts_ts.language_typescript())
        elif lang == "javascript":
            import tree_sitter_javascript as ts_js
            from tree_sitter import Language
            obj = Language(ts_js.language())
        else:
            obj = None
    except Exception:
        obj = None
    _LANG_CACHE[lang] = obj
    return obj


# Minimal per-language node-type -> symbol-kind maps (clean-room; NOT the AGPL
# package's queries). We walk the tree once and pick definition nodes; this is
# syntax-level extraction, exactly what tree-sitter guarantees.
_DEF_NODES = {
    "python": {"function_definition": "function", "class_definition": "class"},
    "typescript": {"function_declaration": "function", "class_declaration": "class",
                   "method_definition": "method", "interface_declaration": "class"},
    "javascript": {"function_declaration": "function", "class_declaration": "class",
                   "method_definition": "method"},
}


def _lang_for(path: str) -> str:
    return LANG_BY_EXT.get(os.path.splitext(path)[1].lower(), "other")


def _name_of(node, src_bytes: bytes) -> str:
    n = node.child_by_field_name("name")
    if n is not None:
        return src_bytes[n.start_byte:n.end_byte].decode("utf-8", "replace")
    return ""


def parse_file(path: str, text: str) -> FileIndex | None:
    lang = _lang_for(path)
    fi = FileIndex(path=path, lang=lang, content_hash=hashlib.sha256(text.encode("utf-8", "replace")).hexdigest())
    endpoints, schemas = extract_contracts(path, text, lang)
    fi.endpoints = [x.to_dict() for x in endpoints]
    fi.schemas = [x.to_dict() for x in schemas]
    if lang == "other":
        return fi  # line-only fallback (no symbols) — never crash
    L = _get_language(lang)
    if L is None:
        return fi
    try:
        from tree_sitter import Parser
        parser = Parser(L)
        src = text.encode("utf-8", "replace")
        tree = parser.parse(src)
        defmap = _DEF_NODES.get(lang, {})
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            kind = defmap.get(node.type)
            if kind:
                # A def/class node's own name-identifier must NOT be walked
                # as a generic child -- otherwise it lands in `refs` too,
                # making the defining file its own "caller"/"dependent".
                # Nested defs (methods, inner functions) are still reached:
                # every other child is still pushed onto the stack.
                # NOTE: tree-sitter Node objects are re-wrapped on each
                # access, so `is`/`is not` identity checks don't hold across
                # two separate child_by_field_name/children calls -- compare
                # by (start_byte, end_byte) span instead.
                name_node = node.child_by_field_name("name")
                name_span = (name_node.start_byte, name_node.end_byte) if name_node is not None else None
                nm = _name_of(node, src)
                if nm:
                    sig = src[node.start_byte:min(node.end_byte, node.start_byte + 200)].decode("utf-8", "replace").split("\n", 1)[0]
                    fi.symbols.append(Symbol(name=nm, kind=kind, path=path,
                                             start_line=node.start_point[0] + 1,
                                             end_line=node.end_point[0] + 1, signature=sig))
                for ch in node.children:
                    if name_span is None or (ch.start_byte, ch.end_byte) != name_span:
                        stack.append(ch)
                continue
            if node.type in ("identifier", "call", "call_expression"):
                fi.refs.append(src[node.start_byte:node.end_byte].decode("utf-8", "replace").split("(")[0].strip())
            stack.extend(node.children)
    except Exception:
        return fi  # parse error -> line-only, fail-soft
    return fi


def build_index(root: str, files: list[str]) -> ProjectIndex:
    idx = ProjectIndex()
    base = os.path.realpath(root)
    for rel in files:
        path = os.path.join(base, rel)
        real = os.path.realpath(path)
        # stay inside the root: no absolute or ``..`` escapes, no symlink leaving it
        if os.path.isabs(rel) or os.path.islink(path) or os.path.commonpath([base, real]) != base:
            continue
        try:
            with open(real, "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        fi = parse_file(rel, text)
        if fi is not None:
            idx.files[rel] = fi
    return idx
