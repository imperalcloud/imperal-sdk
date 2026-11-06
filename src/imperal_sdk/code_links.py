"""Links between definitions, computed from the files' scope facts -- the ONE algorithm (2026-11-06).

The vault's code graph resolves every reference of a file (``code_index.scope_facts``: defs, bindings with aliases,
reference chains) to the definition it names: Python relative/absolute imports through the package roots, TS/JS
specifiers with extension and ``index.*`` probing and ``tsconfig``/``jsconfig`` ``baseUrl``/``paths``, re-exports and
star imports followed, ``self``/``this`` members, local and enclosing scopes. A client without the vault (offline, a
repo not synced yet) used to link by bare NAME instead -- a function with no caller answered hundreds of files (report
06.11). This module is that resolver as pure functions over plain data, so the client answers the way the vault does:

* ``module_index`` / ``resolve_module`` -- literally the vault's (``vault_service/stores/repos.py``) stitching code;
* ``Linker`` -- ``target`` / ``resolve_ref`` with the vault's rules, over a ``{path: BlobFacts}`` map (sync, no DB);
* ``impact`` -- the vault's ``impact`` answer (files that use a symbol, the line, the user, depth through the
  ENCLOSING definition only, code before tests) plus the files that only share the name, listed apart and marked.

Languages without scope facts (``scope_facts`` returns None) have no resolved links: their uses are reported by name
only, marked so -- never mixed into the resolved answer.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

from imperal_sdk.code_index import _slashes

_PY_EXT = (".py", ".pyi")
_TS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".d.ts")
_SELF = ("self", "cls", "this")
BY_NAME_SHOWN = 15


def _lang(path: str) -> str:
    ext = posixpath.splitext(str(path).lower())[1]
    return {".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "tsx"}.get(
        ext, "javascript" if ext in (".js", ".jsx", ".mjs", ".cjs") else "")


def is_test_path(path: str) -> bool:
    p = "/" + str(path).replace("\\", "/").lower()
    base = posixpath.basename(p)
    return ("/tests/" in p or "/test/" in p or "/__tests__/" in p or base.startswith("test_")
            or base.endswith(("_test.py", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js")))


# ---- module resolution (the vault's stitching code, §4.6.3) ----

def module_index(paths, configs: list) -> dict:
    """The repo's files as the resolver probes them: every path (exact and case-blind), and every
    Python module name under each package root -- the repo root, ``src/`` layouts, the roots the
    configs declare (pyproject ``where`` / ``package-dir``, setup.cfg ``package_dir``) and the top
    of each ``__init__.py`` chain."""
    paths = sorted(set(paths), key=lambda p: (not p.endswith(".py"), p))
    files = set(paths)
    lower: dict = {}
    for p in paths:
        lower.setdefault(p.lower(), p)
    roots = {""}
    if any(p.startswith("src/") for p in paths):
        roots.add("src")
    for c in configs or []:
        data = c.get("data") or {}
        base = posixpath.dirname(str(c.get("path") or ""))
        for w in data.get("where") or []:
            roots.add(_slashes(posixpath.join(base, str(w))).lstrip("/"))
        for k, v in (data.get("package_dir") or {}).items():
            if str(k) == "" and v:
                roots.add(_slashes(posixpath.join(base, str(v))).lstrip("/"))
    py: dict = {}
    inits = {posixpath.dirname(p) for p in paths if posixpath.basename(p) in ("__init__.py", "__init__.pyi")}
    for p in paths:
        if not p.endswith(_PY_EXT):
            continue
        stem = p.rsplit(".", 1)[0]
        if posixpath.basename(stem) == "__init__":
            stem = posixpath.dirname(stem)
        mine = set(roots)
        d = posixpath.dirname(p) if posixpath.basename(p).startswith("__init__") else posixpath.dirname(p)
        top = d
        while top and top in inits:
            top = posixpath.dirname(top)
        mine.add(top)
        for root in mine:
            if root and not (stem == root or stem.startswith(root + "/")):
                continue
            rel = stem[len(root) + 1:] if root else stem
            if rel:
                py.setdefault(rel.replace("/", "."), p)
    ts = [c for c in configs or [] if c.get("kind") in ("tsconfig", "jsconfig")]
    return {"files": files, "lower": lower, "py": py, "ts": ts}


def _probe(modules: dict, base: str, lang: str) -> str | None:
    base = _slashes(base).lstrip("/")
    files, lower = modules["files"], modules["lower"]

    def hit(c: str):
        return c if c in files else lower.get(c.lower())
    if lang == "python":
        for c in (base + ".py", base + ".pyi", base + "/__init__.py", base + "/__init__.pyi"):
            if hit(c):
                return hit(c)
        return None
    cands = [base]
    stem, ext = posixpath.splitext(base)
    if ext in (".js", ".jsx", ".mjs", ".cjs"):
        cands += [stem + e for e in (".ts", ".tsx", ".d.ts")]
    cands += [base + e for e in _TS_EXT] + [base + "/index" + e for e in _TS_EXT]
    for c in cands:
        if posixpath.splitext(c)[1] and hit(c):
            return hit(c)
    return None


def resolve_module(modules: dict, from_path: str, spec: str, lang: str, configs: list | None = None) -> str | None:
    """The file of this repo a module specifier names, or None (an external package: no link).
    Python: relative imports from the importing file's package, absolute names through the package
    roots. TS/JS: relative specifiers with extension and ``index.*`` probing, ``tsconfig`` /
    ``jsconfig`` ``baseUrl`` / ``paths`` (the config nearest the importing file); a bare package
    specifier is external."""
    spec = str(spec or "")
    if not spec:
        return None
    if lang == "python":
        if spec.startswith("."):
            level = len(spec) - len(spec.lstrip("."))
            rest = spec[level:]
            parts = [x for x in posixpath.dirname(from_path).split("/") if x]
            if level > 1:
                if level - 1 > len(parts):
                    return None
                parts = parts[:len(parts) - (level - 1)]
            target = "/".join(parts + ([x for x in rest.split(".") if x] if rest else []))
            return _probe(modules, target, "python") if target else _probe(modules, "__init__", "python")
        return modules["py"].get(spec)
    if spec.startswith("."):
        return _probe(modules, posixpath.join(posixpath.dirname(from_path), spec), lang)
    confs = sorted((c for c in modules.get("ts") or []
                    if not posixpath.dirname(c["path"]) or from_path.startswith(posixpath.dirname(c["path"]) + "/")),
                   key=lambda c: -len(posixpath.dirname(c["path"])))
    for c in confs:
        data = c.get("data") or {}
        cdir = posixpath.dirname(c["path"])
        base_dir = posixpath.join(cdir, data.get("baseUrl") or ".")
        for pattern, targets in (data.get("paths") or {}).items():
            pre, star, post = pattern.partition("*")
            if star and spec.startswith(pre) and spec.endswith(post) and len(spec) >= len(pre) + len(post):
                middle = spec[len(pre):len(spec) - len(post)] if post else spec[len(pre):]
                for tgt in targets:
                    got = _probe(modules, posixpath.join(base_dir, tgt.replace("*", middle)), lang)
                    if got:
                        return got
            elif not star and spec == pattern:
                for tgt in targets:
                    got = _probe(modules, posixpath.join(base_dir, tgt), lang)
                    if got:
                        return got
        if data.get("baseUrl"):
            got = _probe(modules, posixpath.join(base_dir, spec), lang)
            if got:
                return got
    return None


# ---- reference resolution (the vault's ``_Facts.target`` / ``_resolve_ref``, over plain data) ----

@dataclass
class Linker:
    """A repo's resolver: ``facts`` = ``{path: BlobFacts}`` (None for a file without scope facts), ``configs`` the
    parsed resolution configs (``code_index.parse_config``: ``{path, kind, data}``)."""
    facts: dict
    configs: list = field(default_factory=list)

    def __post_init__(self):
        self.modules = module_index(list(self.facts), self.configs)
        self._defs: dict = {}

    def defs(self, path: str) -> dict:
        if path not in self._defs:
            fx = self.facts.get(path)
            self._defs[path] = {d.qualname: d for d in (fx.defs if fx else [])}
        return self._defs[path]

    def bindings(self, path: str) -> list:
        fx = self.facts.get(path)
        return sorted(fx.bindings, key=lambda b: b.line) if fx else []

    def module(self, from_path: str, spec: str) -> str | None:
        return resolve_module(self.modules, from_path, spec, "python" if _lang(from_path) == "python" else "ts",
                              self.configs)

    def target(self, path: str, names: list, depth: int = 0):
        """``(path, qualname)`` of ``names`` inside the module ``path`` (re-exports and star exports followed, a
        Python submodule of a package entered); ``qualname`` "" = the module itself."""
        if depth > 8 or not path:
            return None
        if not names:
            return path, ""
        defs = self.defs(path)
        for k in range(min(len(names), 3), 0, -1):
            q = ".".join(names[:k])
            if q in defs:
                return path, q
        for b in self.bindings(path):
            if b.local_name == names[0] and b.kind in ("import", "reexport"):
                tgt = self.module(path, b.module)
                if tgt is None:
                    return None
                rest = ([b.imported] if b.imported and b.imported != "default" else []) + names[1:]
                got = self.target(tgt, rest, depth + 1)
                if got is None and b.imported and _lang(path) == "python":
                    mod = b.module
                    sub = self.module(path, (mod.rstrip(".") + "." if not mod.endswith(".") else mod) + b.imported) \
                        if mod.startswith(".") else self.module(path, f"{mod}.{b.imported}")
                    got = self.target(sub, names[1:], depth + 1) if sub else None
                return got
        for b in self.bindings(path):
            if b.kind == "star":
                tgt = self.module(path, b.module)
                got = self.target(tgt, names, depth + 1) if tgt else None
                if got and got[1]:
                    return got
        if _lang(path) == "python" and posixpath.basename(path).startswith("__init__."):
            sub = _probe(self.modules, posixpath.join(posixpath.dirname(path), names[0]), "python")
            if sub:
                return self.target(sub, names[1:], depth + 1)
        return path, ""

    def resolve_ref(self, path: str, head: str, chain: str, in_def: str | None):
        """One reference -> ``(path, qualname, origin)``, ``"external"`` (bound to a module outside the repo, or
        instance data) or None (unresolved)."""
        parts = [x for x in chain.split(".") if x] if chain else []
        bound = [b for b in self.bindings(path) if b.local_name == head and b.kind != "star"]
        if bound:
            b = bound[-1]
            tgt = self.module(path, b.module)
            if tgt is None:
                return "external"
            names = ([b.imported] if b.imported and b.imported != "default" else []) + parts
            got = self.target(tgt, names)
            if got is None and b.imported and _lang(path) == "python":
                mod = b.module
                sub = self.module(path, (mod if mod.endswith(".") else mod + ".") + b.imported if mod.startswith(".")
                                  else f"{mod}.{b.imported}")
                got = self.target(sub, parts) if sub else None
            return (got[0], got[1], "binding") if got else "external"
        defs = self.defs(path)
        if head in _SELF:
            if not in_def or not parts:
                return "external"
            q = in_def.split(".")
            for k in range(len(q) - 1, 0, -1):
                cls = ".".join(q[:k])
                d = defs.get(cls)
                if d is not None and d.kind == "class":
                    member = f"{cls}.{parts[0]}"
                    return (path, member, "self") if member in defs else "external"
            return "external"
        if head in defs:
            q = f"{head}.{parts[0]}" if parts and f"{head}.{parts[0]}" in defs else head
            return path, q, "local"
        if in_def:
            scope = in_def.split(".")
            for k in range(len(scope), 0, -1):
                q = ".".join(scope[:k] + [head])
                if q in defs:
                    return path, q, "local"
        for b in self.bindings(path):
            if b.kind == "star":
                tgt = self.module(path, b.module)
                got = self.target(tgt, [head] + parts) if tgt else None
                if got and got[1]:
                    return got[0], got[1], "star"
        return None

    # ---- the repo's link table, built once ----

    def links(self) -> list:
        """Every resolved use: ``(src_path, user_qualname, kind, line, dst_path, dst_qualname, origin)``."""
        if getattr(self, "_links", None) is None:
            out = []
            for path in sorted(self.facts):
                fx = self.facts[path]
                if fx is None:
                    continue
                for r in fx.refs:
                    got = self.resolve_ref(path, r.head, r.chain, r.in_def)
                    if isinstance(got, tuple):
                        out.append((path, r.in_def or "", r.kind, r.line, got[0], got[1], got[2]))
            self._links = out
        return self._links

    def symbol_targets(self, symbol: str) -> list:
        """``[(path, qualname)]`` a symbol names: ``path::qualname`` / ``path:qualname``, a qualname
        (``Class.method``) or a bare name (every definition of it), or a file path (the module)."""
        s = str(symbol or "").strip()
        if not s:
            return []
        for sep in ("::", ":"):
            if sep in s and not s.startswith(sep):
                p, q = s.split(sep, 1)
                p = _slashes(p).lstrip("/")
                if p in self.facts and (q in self.defs(p) or not q):
                    return [(p, q)]
        p = _slashes(s).lstrip("/")
        if p in self.facts:
            return [(p, "")]
        exact = [(path, s) for path in sorted(self.facts) if s in self.defs(path)]
        if exact:
            return exact
        tail = s.rsplit(".", 1)[-1]
        return [(path, q) for path in sorted(self.facts) for q, d in self.defs(path).items() if d.name == tail]


def impact(linker: Linker, symbols: list, depth: int = 2) -> dict:
    """The vault's ``impact`` answer, computed locally: ``items`` = files that use the symbols (resolved links only),
    each ``{id, title, kind: "file", via: "scope", depth, line, uses, user, callers, targets, group, origin}``, depth
    growing ONLY through the enclosing definition of a use (a module-level use: the module); code before tests, then
    depth, then path. ``by_name`` = files whose uses only share the name (resolver could not bind them, or the language
    has no scope facts), bounded and marked; ``resolved`` = the definitions asked about (empty: no such definition)."""
    targets: list = []
    for s in symbols or []:
        targets += linker.symbol_targets(str(s))
    links = linker.links()
    origin_files = {p for p, _ in targets}
    items: dict = {}
    seen = set(targets)
    frontier = list(targets)

    def hits(dst: list):
        want = {}
        for p, q in dst:
            want.setdefault(p, set()).add(q)
        for src, user, kind, line, tp, tq, origin in links:
            qs = want.get(tp)
            if qs is None:
                continue
            for q in qs:
                if q == "" or tq == q or tq.startswith(q + "."):
                    yield src, user, kind, line, (tp, q or tq), origin
                    break
    for level in range(1, max(1, int(depth or 1)) + 1):
        nxt = []
        for src, user, kind, line, tgt, origin in hits(frontier):
            if src == tgt[0] or (level > 1 and src in origin_files):
                continue
            tname = f"{tgt[0]}::{tgt[1]}" if tgt[1] else tgt[0]
            it = items.get(src)
            if it is None or level < it["depth"]:
                it = items[src] = {"id": src, "title": src, "kind": "file", "via": "scope", "confidence": 1.0,
                                   "targets": [], "origin": origin, "depth": level, "line": line,
                                   "uses": tgt[1] or tgt[0], "user": user, "callers": [],
                                   "group": "tests" if is_test_path(src) else "code"}
            if level == it["depth"]:
                if tname not in it["targets"]:
                    it["targets"] = sorted(set(it["targets"]) | {tname})
                c = {"user": user, "line": line, "kind": kind}
                if c not in it["callers"] and len(it["callers"]) < 20:
                    it["callers"].append(c)
            nk = (src, user)
            if nk not in seen:
                seen.add(nk)
                nxt.append(nk)
        frontier = nxt
        if not frontier:
            break
    names = sorted({(q or "").rsplit(".", 1)[-1] for _, q in targets if q})
    by_name: list = []
    by_name_files: set = set()
    if names:
        nameset = set(names)
        for path in sorted(linker.facts):
            if path in items or path in origin_files:
                continue
            fx = linker.facts[path]
            line = 0
            hit = False
            if fx is not None:
                for r in fx.refs:
                    last = (r.chain.rsplit(".", 1)[-1] if r.chain else r.head)
                    if last in nameset:
                        line, hit = r.line, True
                        break
                # a method called on a local or a parameter (``obj.name()``, ``svc.graph.name()``) leaves no ref --
                # the scope facts drop chains with a local head -- but its name is in the file's identifiers
                if not hit and nameset & set(fx.names or ()):
                    hit = True
            if hit:
                by_name_files.add(path)
                by_name.append({"path": path, "line": line, "name": next(iter(nameset)) if len(nameset) == 1 else "",
                                "group": "tests" if is_test_path(path) else "code"})
    by_name.sort(key=lambda b: (b["group"] == "tests", b["path"]))
    same_file = []
    for p, q in targets:
        if q:
            same_file += [{"path": p, "user": user, "line": line} for src, user, _k, line, tp, tq, _o in links
                          if src == p and tp == p and tq == q and user != q][:20]
    out = sorted(items.values(), key=lambda i: (i["group"] == "tests", i["depth"], i["id"]))
    return {"ok": True, "data": {"items": out, "total": len(out), "has_more": False},
            "by_name_count": len(by_name_files), "by_name": by_name[:BY_NAME_SHOWN], "same_file": same_file,
            "resolved": [f"{p}::{q}" if q else p for p, q in targets]}
