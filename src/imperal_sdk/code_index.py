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


# The scope graph of one file version (a blob), built from that file alone (spec 4.6.1):
# what it defines, the names it brings in (with their aliases) and every qualified use.

@dataclass(frozen=True)
class Def:
    name: str
    qualname: str        # inside the file: Class.method, outer.inner
    kind: str            # function | class | method | variable | type
    start_line: int
    end_line: int
    signature: str = ""
    exported: bool = False


@dataclass(frozen=True)
class Binding:
    local_name: str      # the name as used in this file (the alias); "*" for a star import
    module: str          # the specifier as written (a.b, .svc, ./a, @/lib/x)
    imported: str | None  # the original name; None = the module itself
    kind: str            # import | reexport | star
    line: int


@dataclass(frozen=True)
class Ref:
    head: str            # first name of the chain (ss, self, this, User)
    chain: str           # the rest, dotted (cancel / client.send); "" for a bare name
    in_def: str | None   # qualname of the enclosing definition; None at module level
    kind: str            # call | read | type | inherit | decorate
    line: int


@dataclass(frozen=True)
class StringKey:
    domain: str          # activity | workflow | signal | query | route | event | queue | schema
    key: str             # dispatch_local_tool | GET /v1/memory/repos
    role: str            # provides | uses
    in_def: str | None
    line: int


@dataclass
class BlobFacts:
    lang: str
    lines: int
    defs: list[Def] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)
    refs: list[Ref] = field(default_factory=list)
    strings: list[StringKey] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"lang": self.lang, "lines": self.lines,
                "defs": [asdict(d) for d in self.defs], "bindings": [asdict(b) for b in self.bindings],
                "refs": [asdict(r) for r in self.refs], "strings": [asdict(s) for s in self.strings]}

    @classmethod
    def from_dict(cls, d: dict) -> "BlobFacts":
        return cls(lang=str(d.get("lang") or ""), lines=int(d.get("lines") or 0),
                   defs=[Def(**x) for x in d.get("defs") or []],
                   bindings=[Binding(**x) for x in d.get("bindings") or []],
                   refs=[Ref(**x) for x in d.get("refs") or []],
                   strings=[StringKey(**x) for x in d.get("strings") or []])


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
    if lang in {"typescript", "tsx", "javascript"}:
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


# ---- string keys (spec 4.6.2): links by string, recognised on the syntax tree ----
# activity / workflow / signal / query: Temporal's names; route: an HTTP route provided by a
# decorator, a router or a Next.js file and used by a client call with a literal path; event /
# queue: a publish / subscribe with a literal channel. Generalises the kernel's registry rule
# (``execute_activity("<name>"`` -> the workflow that schedules it) to every language rule here.

_ACTIVITY_USES = frozenset({"execute_activity", "execute_local_activity", "start_activity", "start_local_activity"})
_WORKFLOW_USES = frozenset({"start_workflow", "execute_workflow", "start_child_workflow", "execute_child_workflow"})
_EVENT_USES, _EVENT_PROVIDES = frozenset({"publish"}), frozenset({"subscribe", "psubscribe"})
_QUEUE_USES, _QUEUE_PROVIDES = frozenset({"lpush", "rpush", "xadd"}), frozenset({"blpop", "brpop"})
_SERVER_OBJECTS = frozenset({"app", "router", "server", "api_router", "bp", "blueprint"})
_PLACEHOLDER = re.compile(r"\{[^{}]*\}|\[[^\[\]]+\]|(?<=/):[A-Za-z_]\w*")


def route_key(method: str, route: str) -> str:
    """``METHOD /normalised/path`` -- one spelling of a route for its provider and its users:
    no scheme / host / query, placeholders (``{id}``, ``${x}``, ``[id]``, ``:id``) as ``{}``,
    no doubled or trailing slash."""
    p = str(route or "").strip()
    if "://" in p:
        p = "/" + p.split("://", 1)[1].partition("/")[2]
    p = p.split("?", 1)[0].split("#", 1)[0]
    p = _PLACEHOLDER.sub("{}", p)
    p = re.sub(r"/{2,}", "/", p)
    if len(p) > 1:
        p = p.rstrip("/")
    return f"{str(method or 'GET').upper()} {p or '/'}"


def _in_def(defs: list, line: int) -> str | None:
    """The innermost definition holding ``line`` (its qualname), None at module level."""
    best = None
    for d in defs or []:
        if d.start_line <= line <= d.end_line and (best is None or d.end_line - d.start_line
                                                    <= best.end_line - best.start_line):
            best = d
    return best.qualname if best else None


def _py_literal_path(node) -> str | None:
    """A literal path (``"/v1/x"``, ``f"/v1/x/{i}"`` -> ``/v1/x/{}``), else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        s = node.value
    elif isinstance(node, ast.JoinedStr):
        s = "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}"
                    for v in node.values)
    else:
        return None
    return s if s.startswith("/") and len(s) > 1 or "://" in s else None


def _python_string_keys(path: str, text: str, defs: list) -> list:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out: list = []
    decorator_calls: set = set()

    def add(domain, key, role, line, in_def=None):
        if key:
            out.append(StringKey(domain, str(key), role, in_def if in_def is not None else _in_def(defs, line), line))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                call = dec if isinstance(dec, ast.Call) else None
                if call is not None:
                    decorator_calls.add(id(call))
                fn = _name(call.func if call is not None else dec)
                owner, _, verb = fn.rpartition(".")
                named = next((_literal_string(k.value) for k in (call.keywords if call is not None else [])
                              if k.arg == "name"), "")
                domain = ({("activity", "defn"): "activity", ("workflow", "defn"): "workflow",
                           ("workflow", "signal"): "signal", ("workflow", "query"): "query"}
                          .get((owner.rsplit(".", 1)[-1], verb)))
                if domain:
                    add(domain, named or node.name, "provides", getattr(dec, "lineno", node.lineno),
                        _in_def(defs, node.lineno))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in decorator_calls:
            continue
        fn = _name(node.func)
        last = fn.rsplit(".", 1)[-1]
        first = node.args[0] if node.args else None
        lit = _literal_string(first) if first is not None else ""
        if last in _ACTIVITY_USES and lit:
            add("activity", lit, "uses", node.lineno)
        elif last in _WORKFLOW_USES and lit:
            add("workflow", lit, "uses", node.lineno)
        elif last == "signal" and isinstance(node.func, ast.Attribute) and lit:
            add("signal", lit, "uses", node.lineno)
        elif last in _EVENT_USES | _EVENT_PROVIDES and lit:
            add("event", lit, "uses" if last in _EVENT_USES else "provides", node.lineno)
        elif last in _QUEUE_USES | _QUEUE_PROVIDES and lit:
            add("queue", lit, "uses" if last in _QUEUE_USES else "provides", node.lineno)
        elif isinstance(node.func, ast.Attribute) and last in _HTTP_METHODS and first is not None \
                and last != "add_api_route":
            route = _py_literal_path(first)
            if route:
                add("route", route_key(last, route), "uses", node.lineno)
        elif isinstance(node.func, ast.Attribute) and last == "request" and len(node.args) >= 2 \
                and _literal_string(node.args[0]).lower() in _HTTP_METHODS:
            route = _py_literal_path(node.args[1])
            if route:
                add("route", route_key(_literal_string(node.args[0]), route), "uses", node.lineno)
    endpoints, _schemas = _python_contracts(path, text)
    for e in endpoints:
        add("route", route_key(e.method, e.route), "provides", e.line, _in_def(defs, e.line) or e.handler)
    return out


def _ts_text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _ts_literal_path(src: bytes, node) -> str | None:
    """A literal string / template (``${x}`` -> ``{}``) that is a path or a URL, else None."""
    if node is None:
        return None
    if node.type == "string":
        s = "".join(_ts_text(src, c) for c in node.children if c.type == "string_fragment")
    elif node.type == "template_string":
        s = "".join(_ts_text(src, c) if c.type == "string_fragment" else "{}"
                    for c in node.children if c.type in ("string_fragment", "template_substitution"))
    else:
        return None
    return s if s.startswith("/") and len(s) > 1 or "://" in s else None


def _ts_literal(src: bytes, node) -> str:
    if node is None or node.type != "string":
        return ""
    return "".join(_ts_text(src, c) for c in node.children if c.type == "string_fragment")


def _ts_string_keys(path: str, text: str, tree, src: bytes, defs: list) -> list:
    out: list = []

    def add(domain, key, role, line, in_def=None):
        if key:
            out.append(StringKey(domain, str(key), role, in_def if in_def is not None else _in_def(defs, line), line))

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call_expression":
            continue
        fn = node.child_by_field_name("function")
        args = node.child_by_field_name("arguments")
        argv = [c for c in (args.named_children if args is not None else []) if c.type != "comment"]
        if fn is None or not argv:
            continue
        line = node.start_point[0] + 1
        if fn.type == "identifier":
            name, obj = _ts_text(src, fn), ""
        elif fn.type == "member_expression":
            prop = fn.child_by_field_name("property")
            o = fn.child_by_field_name("object")
            name, obj = (_ts_text(src, prop) if prop is not None else ""), (_ts_text(src, o) if o is not None else "")
        else:
            continue
        if name == "fetch":
            route = _ts_literal_path(src, argv[0])
            method = "GET"
            if route and len(argv) > 1 and argv[1].type == "object":
                for pair in argv[1].named_children:
                    k = pair.child_by_field_name("key") if pair.type == "pair" else None
                    if k is not None and _ts_text(src, k).strip("'\"") == "method":
                        method = _ts_literal(src, pair.child_by_field_name("value")) or method
            if route:
                add("route", route_key(method, route), "uses", line)
        elif fn.type == "member_expression" and name in _HTTP_METHODS:
            route = _ts_literal_path(src, argv[0])
            # app.get("/x", handler) / router.post(...) define a route (the endpoint rules); a client calls
            if route and not (obj.rsplit(".", 1)[-1] in _SERVER_OBJECTS and len(argv) > 1):
                add("route", route_key(name, route), "uses", line)
        elif name in _EVENT_USES | _EVENT_PROVIDES and _ts_literal(src, argv[0]):
            add("event", _ts_literal(src, argv[0]), "uses" if name in _EVENT_USES else "provides", line)
    endpoints, _schemas = extract_contracts(path, text, "typescript")
    for e in endpoints:
        add("route", route_key(e.method, e.route), "provides", e.line, _in_def(defs, e.line))
    return out


def string_keys(lang: str, tree, text: str, defs: list, path: str = "") -> list[StringKey]:
    """Every string-keyed link the file provides or uses (``StringKey`` rows). ``tree`` is the
    file's tree-sitter tree (TS/JS rules walk it); Python's rules read its ``ast``."""
    if lang == "python":
        return _python_string_keys(path, text, defs) + _schema_keys(lang, path, text, defs)
    if lang in ("typescript", "tsx", "javascript") and tree is not None:
        return _ts_string_keys(path, text, tree, text.encode("utf-8", "replace"), defs) \
            + _schema_keys(lang, path, text, defs)
    return []


def _schema_keys(lang: str, path: str, text: str, defs: list) -> list:
    """The contract evidence (``extract_contracts``) as string keys of domain ``schema``: a model /
    table provides its name; an endpoint uses the schemas it references, under its handler -- what
    the account graph's ``schema`` nodes and ``endpoint_schema_ref`` edges are built from."""
    try:
        endpoints, schemas = extract_contracts(path, text, lang)
    except Exception:
        return []
    out = [StringKey("schema", s.name, "provides", _in_def(defs, s.line), s.line) for s in schemas]
    for e in endpoints:
        handler = next((d.qualname for d in defs or [] if d.name == e.handler), None) or _in_def(defs, e.line)
        out += [StringKey("schema", name, "uses", handler, e.line) for name in e.schema_refs]
    return out


# ---- indexer (from webbee/intel/indexer.py; the language table of the kernel's code_outline) ----

# ONE language table for the client and the kernel: .tsx is TSX (JSX parses), .mjs / .cjs are JavaScript.
LANG_BY_EXT = {".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "tsx",
               ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript"}

# tree-sitter Language handles are lazy-loaded + cached (import cost is real).
_LANG_CACHE: dict = {}


def language(lang: str):
    """The tree-sitter Language of ``lang`` (``tsx`` uses the TSX grammar), or None when the
    parser is not installed (the ``code-index`` extra) or the language is not one it knows."""
    if lang in _LANG_CACHE:
        return _LANG_CACHE[lang]
    try:
        from tree_sitter import Language
        if lang == "python":
            import tree_sitter_python as ts_py
            obj = Language(ts_py.language())
        elif lang in ("typescript", "tsx"):
            import tree_sitter_typescript as ts_ts
            obj = Language(ts_ts.language_tsx() if lang == "tsx" else ts_ts.language_typescript())
        elif lang == "javascript":
            import tree_sitter_javascript as ts_js
            obj = Language(ts_js.language())
        else:
            obj = None
    except Exception:
        obj = None
    _LANG_CACHE[lang] = obj
    return obj


_get_language = language          # the client imported the private name


# Minimal per-language node-type -> symbol-kind maps (clean-room; NOT the AGPL
# package's queries). We walk the tree once and pick definition nodes; this is
# syntax-level extraction, exactly what tree-sitter guarantees.
DEF_NODES = {
    "python": {"function_definition": "function", "class_definition": "class"},
    "typescript": {"function_declaration": "function", "class_declaration": "class", "method_definition": "method",
                   "interface_declaration": "class", "type_alias_declaration": "type", "enum_declaration": "class"},
    "javascript": {"function_declaration": "function", "class_declaration": "class", "method_definition": "method"},
}
DEF_NODES["tsx"] = DEF_NODES["typescript"]
_DEF_NODES = DEF_NODES


def _lang_for(path: str) -> str:
    return LANG_BY_EXT.get(os.path.splitext(path)[1].lower(), "other")


# ---- what any source may index (spec 4.2: one list, enforced by every source, refused by the vault) ----

EXTRACTOR_VERSION = "2"
MAX_FILE_BYTES = 1_048_576
MAX_REPO_FILES = 20_000
INDEXABLE_EXT = (".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
# the resolution configs (read and stored parsed); setup.py is code to execute -- never read
CONFIG_NAMES = ("pyproject.toml", "setup.cfg", "jsconfig.json", "package.json")
_TSCONFIG = re.compile(r"^tsconfig(?:\.[\w.-]+)?\.json$")
SECRET_PATTERNS = (".env*", "*.pem", "*.key", "*.crt", "id_*", "*.p12", "*.pfx", "*.kdbx",
                   "secrets/", ".ssh/", ".aws/", ".git/")
# the client's ``service.skipped_dir`` (every dotted directory, dependency caches) and the kernel's
# vendored-tree filter (``marathon_graph_feed._VENDOR``) merged: never the project's own code
SKIP_DIRS = frozenset({"node_modules", "site-packages", "dist-packages", "__pycache__", "venv", "virtualenv",
                       "dist", "build", "out", "coverage", "vendor", "third_party", "bower_components",
                       "AppData", "Library", "secrets"})


def normalise_text(raw: bytes) -> str | None:
    """The text of a file as every source hashes and parses it: UTF-8 (with or without BOM) or
    UTF-16 LE/BE with a BOM, CRLF / CR -> LF. None for anything else (binary, skipped)."""
    if not isinstance(raw, (bytes, bytearray)):
        return None
    raw = bytes(raw)
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            text = raw[3:].decode("utf-8")
        elif raw.startswith(b"\xff\xfe"):
            text = raw[2:].decode("utf-16-le")
        elif raw.startswith(b"\xfe\xff"):
            text = raw[2:].decode("utf-16-be")
        else:
            text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "\x00" in text:
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def blob_hash(text: str) -> str:
    """A file version's id: SHA-256 of its normalised text."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


_DRIVE = re.compile(r"^/?([A-Za-z]):(?=/|$)")


def _slashes(path: str) -> str:
    """Forward slashes, one leading ``/`` before a drive (``C:\\x`` and ``/C:/x`` -> ``/C:/x``),
    no doubled slashes, no ``.`` parts, ``..`` resolved."""
    import posixpath
    p = str(path or "").replace("\\", "/")
    m = _DRIVE.match(p)
    drive = ""
    if m:
        drive, p = f"/{m.group(1).upper()}:", p[m.end():] or "/"
    absolute = p.startswith("/") or bool(drive)
    p = posixpath.normpath(p) if p else ""
    if p in (".", ""):
        p = "/" if absolute else ""
    if absolute and not p.startswith("/"):
        p = "/" + p
    return (drive + p).rstrip("/") if drive else (p if p == "/" else p.rstrip("/"))


def canonical_path(path: str, root: str, windows: bool = False) -> str:
    """One spelling of a file path: forward slashes, relative to ``root`` (a Windows drive path
    as SFTP reports it -- ``/C:/...`` -- or as Windows writes it, ``C:\\...``), the file's own
    case kept. On a Windows repo the root is matched case-blind; the vault matches any spelling
    of a path case-blind when no exact path exists (owner, 2026-10-20: any form, any system)."""
    p, r = _slashes(path), _slashes(root)
    if r and r != "/":
        same = (p.lower() == r.lower()) if windows else p == r
        under = (p.lower().startswith(r.lower() + "/")) if windows else p.startswith(r + "/")
        if same:
            return ""
        if under:
            return p[len(r) + 1:]
    elif r == "/" and p.startswith("/"):
        return p[1:]
    return p


def indexable(rel_path: str) -> str | None:
    """``"code"``, ``"config"`` (a resolution config) or None (never read: secrets, setup.py, a
    dependency / build / dotted tree, anything that is not code)."""
    import fnmatch
    parts = [x for x in _slashes(rel_path).split("/") if x]
    if not parts or (parts and _DRIVE.match(parts[0])):
        parts = parts[1:] if parts else parts
    if not parts:
        return None
    dirs, name = parts[:-1], parts[-1]
    for d in dirs:
        if d.startswith(".") or d in SKIP_DIRS or d.startswith("Program Files"):
            return None
    low = name.lower()
    if any(fnmatch.fnmatchcase(low, pat) for pat in SECRET_PATTERNS if not pat.endswith("/")):
        return None
    if low == "setup.py":
        return None
    if low in CONFIG_NAMES or _TSCONFIG.match(low):
        return "config"
    return "code" if os.path.splitext(low)[1] in INDEXABLE_EXT else None


# ---- the scope graph of one file (spec 4.6.1): defs, bindings with aliases, reference chains ----

_CHAIN_PARTS = 6
_PY_BUILTINS = frozenset(dir(__import__("builtins"))) - {"self", "cls"}
_JS_GLOBALS = frozenset({
    "console", "window", "document", "globalThis", "Math", "JSON", "Object", "Array", "Promise", "String",
    "Number", "Boolean", "Date", "Error", "TypeError", "Symbol", "Map", "Set", "WeakMap", "WeakSet", "RegExp",
    "parseInt", "parseFloat", "isNaN", "setTimeout", "clearTimeout", "setInterval", "clearInterval", "require",
    "module", "exports", "process", "undefined", "NaN", "Infinity", "fetch", "URL", "URLSearchParams",
    "Response", "Request", "Headers", "Buffer", "Intl", "Reflect", "Proxy", "BigInt", "arguments", "super",
    "Record", "Partial", "Required", "Readonly", "Pick", "Omit", "ReturnType", "Parameters", "Awaited",
    "Exclude", "Extract", "NonNullable", "InstanceType", "Uint8Array", "ArrayBuffer", "AbortController",
    "localStorage", "sessionStorage", "navigator", "location", "history", "crypto", "TextEncoder", "TextDecoder",
    "structuredClone", "queueMicrotask", "requestAnimationFrame", "Event", "CustomEvent", "FormData", "Blob",
})


class _Scope:
    """What one walk collects: the file's defs, bindings and refs, and the locals of each def."""

    def __init__(self, src: bytes):
        self.src = src
        self.defs: list = []
        self.bindings: list = []
        self.refs: list = []
        self._seen: set = set()

    def text(self, node) -> str:
        return self.src[node.start_byte:node.end_byte].decode("utf-8", "replace")

    def ref(self, parts: list, in_def, kind: str, line: int, local: set) -> None:
        if not parts or (parts[0] in local and parts[0] not in ("self", "cls")):
            return
        r = Ref(parts[0], ".".join(parts[1:_CHAIN_PARTS]), in_def, kind, line)
        if r not in self._seen:
            self._seen.add(r)
            self.refs.append(r)


def _line_of(node) -> int:
    return node.start_point[0] + 1


def _first_line(text: str, n: int = 200) -> str:
    return " ".join(text.split("\n", 1)[0].split())[:n]


# Python ------------------------------------------------------------------------------------------

def _py_chain(sc: _Scope, node) -> list | None:
    if node.type == "identifier":
        return [sc.text(node)]
    if node.type == "attribute":
        left = _py_chain(sc, node.child_by_field_name("object"))
        attr = node.child_by_field_name("attribute")
        return left + [sc.text(attr)] if left is not None and attr is not None else None
    return None


def _py_targets(sc: _Scope, node, out: set) -> None:
    """The plain names an assignment / loop / with / except target binds."""
    if node is None:
        return
    if node.type == "identifier":
        out.add(sc.text(node))
    elif node.type in ("pattern_list", "tuple_pattern", "list_pattern", "list_splat_pattern", "tuple", "list",
                       "as_pattern_target"):
        for c in node.named_children:
            _py_targets(sc, c, out)


def _py_locals(sc: _Scope, fn) -> set:
    """The names a function binds itself (parameters, assignments, loop / with / except targets) --
    a use of one of them is not a reference to the outside."""
    out: set = set()
    params = fn.child_by_field_name("parameters")
    for p in (params.named_children if params is not None else []):
        if p.type == "identifier":
            out.add(sc.text(p))
        else:
            n = p.child_by_field_name("name")
            if n is not None and n.type == "identifier":
                out.add(sc.text(n))
            for c in p.named_children:
                if c.type == "identifier" and p.type in ("typed_parameter", "list_splat_pattern",
                                                         "dictionary_splat_pattern"):
                    out.add(sc.text(c))
                    break
    stack = list((fn.child_by_field_name("body") or fn).children)
    while stack:
        n = stack.pop()
        if n.type in ("function_definition", "class_definition", "lambda"):
            continue
        if n.type in ("assignment", "augmented_assignment"):
            _py_targets(sc, n.child_by_field_name("left"), out)
        elif n.type in ("for_statement", "for_in_clause"):
            _py_targets(sc, n.child_by_field_name("left"), out)
        elif n.type == "as_pattern":
            _py_targets(sc, n.child_by_field_name("alias"), out)
        elif n.type in ("global_statement", "nonlocal_statement"):
            for c in n.named_children:
                out.discard(sc.text(c))
        stack.extend(n.children)
    return out


def _py_all(sc: _Scope, root) -> set | None:
    for st in root.named_children:
        node = st.named_children[0] if st.type == "expression_statement" and st.named_children else None
        if node is not None and node.type == "assignment":
            left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
            if left is not None and sc.text(left) == "__all__" and right is not None:
                return {sc.text(s).strip("'\"") for s in right.named_children if s.type == "string"}
    return None


def _py_import(sc: _Scope, node, is_init: bool) -> None:
    line = _line_of(node)
    if node.type == "import_statement":
        for c in node.named_children:
            if c.type == "aliased_import":
                mod, alias = c.child_by_field_name("name"), c.child_by_field_name("alias")
                sc.bindings.append(Binding(sc.text(alias), sc.text(mod), None, "import", line))
            elif c.type == "dotted_name":
                m = sc.text(c)
                sc.bindings.append(Binding(m.split(".", 1)[0], m.split(".", 1)[0] if "." in m else m, None,
                                           "import", line))
        return
    mod_node = node.child_by_field_name("module_name")
    module = sc.text(mod_node).replace(" ", "") if mod_node is not None else ""
    if module == "__future__":
        return
    kind = "reexport" if is_init else "import"
    for c in node.named_children:
        if c.type == "wildcard_import":
            sc.bindings.append(Binding("*", module, None, "star", line))
    for c in node.children_by_field_name("name"):
        if c.type == "aliased_import":
            name, alias = c.child_by_field_name("name"), c.child_by_field_name("alias")
            sc.bindings.append(Binding(sc.text(alias), module, sc.text(name), kind, line))
        elif c.type == "dotted_name":
            sc.bindings.append(Binding(sc.text(c), module, sc.text(c), kind, line))


def _py_walk(sc: _Scope, node, scope: list, ctx: str, local: set, exported_names, is_init: bool) -> None:
    t = node.type
    in_def = scope[-1][0] if scope else None
    if t in ("import_statement", "import_from_statement"):
        _py_import(sc, node, is_init)
        return
    if t == "future_import_statement":
        return
    if t == "decorated_definition":
        definition = node.child_by_field_name("definition")
        for c in node.children:
            if c.type == "decorator":
                for e in c.named_children:
                    _py_walk(sc, e, scope, "decorate", local, exported_names, is_init)
        if definition is not None:
            _py_def(sc, definition, node, scope, local, exported_names, is_init)
        return
    if t in ("function_definition", "class_definition"):
        _py_def(sc, node, node, scope, local, exported_names, is_init)
        return
    if t == "call":
        fn = node.child_by_field_name("function")
        chain = _py_chain(sc, fn) if fn is not None else None
        if chain:
            sc.ref(chain, in_def, "decorate" if ctx == "decorate" else "call", _line_of(node), local)
        elif fn is not None:
            _py_walk(sc, fn, scope, ctx, local, exported_names, is_init)
        args = node.child_by_field_name("arguments")
        if args is not None:
            _py_walk(sc, args, scope, "read" if ctx != "inherit" else ctx, local, exported_names, is_init)
        return
    if t in ("identifier", "attribute"):
        chain = _py_chain(sc, node)
        if chain:
            kind = ctx if ctx in ("decorate", "inherit", "type") else "read"
            sc.ref(chain, in_def, kind, _line_of(node), local)
            return
    if t == "type":
        for c in node.named_children:
            _py_walk(sc, c, scope, "type", local, exported_names, is_init)
        return
    if t == "keyword_argument":
        value = node.child_by_field_name("value")
        if value is not None:
            _py_walk(sc, value, scope, ctx, local, exported_names, is_init)
        return
    if t in ("assignment", "augmented_assignment"):
        left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
        typ = node.child_by_field_name("type")
        if not scope and left is not None and left.type == "identifier" and t == "assignment":
            name = sc.text(left)
            if name != "__all__":
                exp = (name in exported_names) if exported_names is not None else not name.startswith("_")
                sc.defs.append(Def(name, name, "variable", _line_of(node), node.end_point[0] + 1,
                                   _first_line(sc.text(node)), exp))
        elif left is not None and left.type in ("attribute", "subscript"):
            _py_walk(sc, left, scope, ctx, local, exported_names, is_init)
        for part in (typ, right):
            if part is not None:
                _py_walk(sc, part, scope, "type" if part is typ else ctx, local, exported_names, is_init)
        return
    if t in ("parameters", "lambda_parameters"):
        for p in node.named_children:
            for f in ("type", "value"):
                v = p.child_by_field_name(f)
                if v is not None:
                    _py_walk(sc, v, scope, "type" if f == "type" else "read", local, exported_names, is_init)
        return
    if t == "string":
        for c in node.named_children:
            if c.type == "interpolation":
                _py_walk(sc, c, scope, ctx, local, exported_names, is_init)
        return
    for c in node.children:
        _py_walk(sc, c, scope, ctx, local, exported_names, is_init)


def _py_def(sc: _Scope, node, outer, scope: list, local: set, exported_names, is_init: bool) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = sc.text(name_node)
    parent = scope[-1] if scope else None
    is_class = node.type == "class_definition"
    kind = "class" if is_class else ("method" if parent and parent[1] == "class" else "function")
    qual = f"{parent[0]}.{name}" if parent else name
    if parent is None:
        exp = (name in exported_names) if exported_names is not None else not name.startswith("_")
    else:
        exp = bool(parent[2]) and parent[1] == "class" and not name.startswith("_")
    sc.defs.append(Def(name, qual, kind, _line_of(outer), node.end_point[0] + 1,
                       _first_line(sc.text(node)), exp))
    inner = (qual, "class" if is_class else "function", exp)
    sup = node.child_by_field_name("superclasses")
    if sup is not None:
        for c in sup.named_children:
            _py_walk(sc, c, scope, "inherit", local, exported_names, is_init)
    for f, ctx in (("parameters", "read"), ("return_type", "type")):
        part = node.child_by_field_name(f)
        if part is not None:
            _py_walk(sc, part, scope, ctx, local, exported_names, is_init)
    body = node.child_by_field_name("body")
    if body is not None:
        mine = local if is_class else _py_locals(sc, node)
        _py_walk(sc, body, scope + [inner], "read", mine, exported_names, is_init)


# TypeScript / JavaScript -------------------------------------------------------------------------

_TS_DEFS = {"function_declaration": "function", "generator_function_declaration": "function",
            "class_declaration": "class", "abstract_class_declaration": "class", "method_definition": "method",
            "interface_declaration": "type", "type_alias_declaration": "type", "enum_declaration": "type"}
_TS_FUNCTION_VALUES = frozenset({"arrow_function", "function_expression", "function", "generator_function"})


def _ts_chain(sc: _Scope, node) -> list | None:
    if node.type in ("identifier", "this", "type_identifier", "shorthand_property_identifier"):
        return [sc.text(node)]
    if node.type in ("member_expression", "nested_type_identifier", "nested_identifier"):
        obj = node.child_by_field_name("object") or node.child_by_field_name("module") or \
            (node.named_children[0] if node.named_children else None)
        prop = node.child_by_field_name("property") or node.child_by_field_name("name") or \
            (node.named_children[-1] if len(node.named_children) > 1 else None)
        left = _ts_chain(sc, obj) if obj is not None else None
        if left is None or prop is None or prop.type == "private_property_identifier":
            return None
        return left + [sc.text(prop)]
    return None


def _ts_string(sc: _Scope, node) -> str:
    return "".join(sc.text(c) for c in node.children if c.type == "string_fragment") if node is not None else ""


def _ts_locals(sc: _Scope, fn) -> set:
    out: set = set()
    stack = list(fn.children)
    while stack:
        n = stack.pop()
        if n.type in ("required_parameter", "optional_parameter"):
            pat = n.child_by_field_name("pattern")
            if pat is not None and pat.type == "identifier":
                out.add(sc.text(pat))
        elif n.type == "formal_parameters":
            for c in n.named_children:
                if c.type == "identifier":
                    out.add(sc.text(c))
        elif n.type == "variable_declarator":
            name = n.child_by_field_name("name")
            if name is not None and name.type == "identifier":
                out.add(sc.text(name))
        elif n.type in ("for_in_statement",):
            left = n.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                out.add(sc.text(left))
        elif n.type == "catch_clause":
            p = n.child_by_field_name("parameter")
            if p is not None and p.type == "identifier":
                out.add(sc.text(p))
        if n.type in _TS_DEFS and n is not fn:
            continue
        stack.extend(n.children)
    return out


def _ts_import(sc: _Scope, node) -> None:
    src_node = node.child_by_field_name("source")
    module = _ts_string(sc, src_node)
    line = _line_of(node)
    if node.type == "import_statement":
        for clause in (c for c in node.named_children if c.type == "import_clause"):
            for c in clause.named_children:
                if c.type == "identifier":
                    sc.bindings.append(Binding(sc.text(c), module, "default", "import", line))
                elif c.type == "namespace_import":
                    ident = next((x for x in c.named_children if x.type == "identifier"), None)
                    if ident is not None:
                        sc.bindings.append(Binding(sc.text(ident), module, None, "import", line))
                elif c.type == "named_imports":
                    for spec in (x for x in c.named_children if x.type == "import_specifier"):
                        name, alias = spec.child_by_field_name("name"), spec.child_by_field_name("alias")
                        if name is not None:
                            sc.bindings.append(Binding(sc.text(alias or name), module, sc.text(name), "import", line))
        return
    # export ... from "<module>"
    clause = next((c for c in node.named_children if c.type == "export_clause"), None)
    ns = next((c for c in node.named_children if c.type == "namespace_export"), None)
    if clause is not None:
        for spec in (x for x in clause.named_children if x.type == "export_specifier"):
            name, alias = spec.child_by_field_name("name"), spec.child_by_field_name("alias")
            if name is not None:
                sc.bindings.append(Binding(sc.text(alias or name), module, sc.text(name), "reexport", line))
    elif ns is not None:
        ident = next((x for x in ns.named_children if x.type in ("identifier", "string")), None)
        sc.bindings.append(Binding(sc.text(ident) if ident is not None else "*", module, None, "reexport", line))
    else:
        sc.bindings.append(Binding("*", module, None, "star", line))


def _ts_require(sc: _Scope, decl) -> bool:
    """``const x = require("./a")`` / ``const {a: b, c} = require("./a")``: bindings like an import."""
    value = decl.child_by_field_name("value")
    if value is None or value.type != "call_expression":
        return False
    fn, args = value.child_by_field_name("function"), value.child_by_field_name("arguments")
    if fn is None or sc.text(fn) != "require" or args is None or not args.named_children \
            or args.named_children[0].type != "string":
        return False
    module, line = _ts_string(sc, args.named_children[0]), _line_of(decl)
    name = decl.child_by_field_name("name")
    if name is not None and name.type == "identifier":
        sc.bindings.append(Binding(sc.text(name), module, None, "import", line))
    elif name is not None and name.type == "object_pattern":
        for p in name.named_children:
            if p.type == "shorthand_property_identifier_pattern":
                sc.bindings.append(Binding(sc.text(p), module, sc.text(p), "import", line))
            elif p.type == "pair_pattern":
                k, v = p.child_by_field_name("key"), p.child_by_field_name("value")
                if k is not None and v is not None and v.type == "identifier":
                    sc.bindings.append(Binding(sc.text(v), module, sc.text(k), "import", line))
    return True


def _ts_walk(sc: _Scope, node, scope: list, ctx: str, local: set, exported: bool, named_exports: set) -> None:
    t = node.type
    in_def = scope[-1][0] if scope else None
    if t == "import_statement":
        _ts_import(sc, node)
        return
    if t == "export_statement":
        if node.child_by_field_name("source") is not None:
            _ts_import(sc, node)
            return
        for c in node.named_children:
            if c.type == "export_clause":
                for spec in (x for x in c.named_children if x.type == "export_specifier"):
                    n = spec.child_by_field_name("name")
                    if n is not None:
                        named_exports.add(sc.text(n))
            elif c.type == "identifier" and node.child_by_field_name("value") is not None:
                named_exports.add(sc.text(c))
            elif c.type == "decorator":
                for e in c.named_children:
                    _ts_walk(sc, e, scope, "decorate", local, False, named_exports)
            else:
                _ts_walk(sc, c, scope, ctx, local, True, named_exports)
        return
    if t in _TS_DEFS:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            for c in node.children:
                _ts_walk(sc, c, scope, ctx, local, exported, named_exports)
            return
        name = sc.text(name_node)
        parent = scope[-1] if scope else None
        kind = _TS_DEFS[t]
        qual = f"{parent[0]}.{name}" if parent else name
        exp = exported if parent is None else (bool(parent[2]) and parent[1] == "class")
        sc.defs.append(Def(name, qual, kind, _line_of(node), node.end_point[0] + 1, _first_line(sc.text(node)), exp))
        inner = (qual, "class" if kind == "class" else "function", exp)
        mine = local | (_ts_locals(sc, node) if kind in ("function", "method") else set())
        for c in node.children:
            if c.type in ("class_heritage", "extends_clause", "implements_clause", "extends_type_clause"):
                _ts_walk(sc, c, scope, "inherit", local, False, named_exports)
            elif c.type == "decorator":
                for e in c.named_children:
                    _ts_walk(sc, e, scope, "decorate", local, False, named_exports)
            elif not (name_node.start_byte == c.start_byte and name_node.end_byte == c.end_byte):
                _ts_walk(sc, c, scope + [inner], ctx if c.type != "type_annotation" else "type", mine, False,
                         named_exports)
        return
    if t in ("lexical_declaration", "variable_declaration"):
        for decl in (c for c in node.named_children if c.type == "variable_declarator"):
            if _ts_require(sc, decl):
                continue
            name, value = decl.child_by_field_name("name"), decl.child_by_field_name("value")
            typ = decl.child_by_field_name("type")
            if name is not None and name.type == "identifier" and (not scope or scope[-1][1] == "class"):
                fn_value = value is not None and value.type in _TS_FUNCTION_VALUES
                if not scope or fn_value:
                    nm = sc.text(name)
                    parent = scope[-1] if scope else None
                    qual = f"{parent[0]}.{nm}" if parent else nm
                    sc.defs.append(Def(nm, qual, "function" if fn_value else "variable", _line_of(decl),
                                       decl.end_point[0] + 1, _first_line(sc.text(decl)), exported and not scope))
                    if fn_value:
                        mine = local | _ts_locals(sc, value)
                        _ts_walk(sc, value, scope + [(qual, "function", exported)], "read", mine, False, named_exports)
                        continue
            if typ is not None:
                _ts_walk(sc, typ, scope, "type", local, False, named_exports)
            if value is not None:
                _ts_walk(sc, value, scope, "read", local, False, named_exports)
        return
    if t == "public_field_definition" and scope and scope[-1][1] == "class":
        name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
        if name is not None and value is not None and value.type in _TS_FUNCTION_VALUES:
            qual = f"{scope[-1][0]}.{sc.text(name)}"
            sc.defs.append(Def(sc.text(name), qual, "method", _line_of(node), node.end_point[0] + 1,
                               _first_line(sc.text(node)), bool(scope[-1][2])))
            _ts_walk(sc, value, scope + [(qual, "function", False)], "read", local | _ts_locals(sc, value), False,
                     named_exports)
            return
    if t in ("call_expression", "new_expression"):
        fn = node.child_by_field_name("function") or node.child_by_field_name("constructor")
        chain = _ts_chain(sc, fn) if fn is not None else None
        if chain and chain[0] not in _JS_GLOBALS:
            sc.ref(chain, in_def, "decorate" if ctx == "decorate" else "call", _line_of(node), local)
        elif fn is not None and not chain:
            _ts_walk(sc, fn, scope, ctx, local, False, named_exports)
        for c in node.children:
            if c.type in ("arguments", "type_arguments", "template_string"):
                _ts_walk(sc, c, scope, "read" if ctx != "inherit" else ctx, local, False, named_exports)
        return
    if t in ("identifier", "this", "member_expression", "type_identifier", "nested_type_identifier",
             "nested_identifier", "shorthand_property_identifier"):
        chain = _ts_chain(sc, node)
        if chain:
            if chain[0] not in _JS_GLOBALS:
                kind = ctx if ctx in ("decorate", "inherit", "type") else (
                    "type" if t in ("type_identifier", "nested_type_identifier") else "read")
                sc.ref(chain, in_def, kind, _line_of(node), local)
            return
    if t in ("type_annotation", "type_arguments", "type_parameters"):
        for c in node.named_children:
            _ts_walk(sc, c, scope, "type", local, False, named_exports)
        return
    if t in ("jsx_opening_element", "jsx_self_closing_element"):
        name = node.child_by_field_name("name")
        chain = _ts_chain(sc, name) if name is not None else None
        if chain and chain[0][:1].isupper():
            sc.ref(chain, in_def, "call", _line_of(node), local)
        for c in node.named_children:
            if name is None or c.start_byte != name.start_byte:
                _ts_walk(sc, c, scope, ctx, local, False, named_exports)
        return
    if t in ("pair",):
        value = node.child_by_field_name("value")
        if value is not None:
            _ts_walk(sc, value, scope, ctx, local, False, named_exports)
        return
    if t in ("property_identifier", "string", "comment", "jsx_text", "regex", "number"):
        return
    for c in node.children:
        _ts_walk(sc, c, scope, ctx, local, False, named_exports)


def scope_facts(path: str, text: str) -> BlobFacts | None:
    """The file's scope graph (its defs, bindings with aliases, reference chains) and string keys,
    from this file alone. None when it is not code the parser knows (or the parser is absent)."""
    lang = _lang_for(path)
    lang_obj = language(lang) if lang != "other" else None
    if lang_obj is None:
        return None
    try:
        from tree_sitter import Parser
        src = str(text).encode("utf-8", "replace")
        tree = Parser(lang_obj).parse(src)
        sc = _Scope(src)
        if lang == "python":
            is_init = os.path.basename(str(path).replace("\\", "/")) == "__init__.py"
            exported_names = _py_all(sc, tree.root_node)
            for c in tree.root_node.children:
                _py_walk(sc, c, [], "read", set(), exported_names, is_init)
        else:
            named: set = set()
            for c in tree.root_node.children:
                _ts_walk(sc, c, [], "read", set(), False, named)
            if named:
                sc.defs = [Def(d.name, d.qualname, d.kind, d.start_line, d.end_line, d.signature, True)
                           if (d.qualname in named and "." not in d.qualname) else d for d in sc.defs]
        defs = sorted(sc.defs, key=lambda d: (d.start_line, d.qualname))
        facts = BlobFacts(lang=lang, lines=str(text).count("\n") + 1, defs=defs, bindings=sc.bindings,
                          refs=sc.refs, strings=string_keys(lang, tree, str(text), defs, path))
        return facts
    except Exception:
        return None


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
