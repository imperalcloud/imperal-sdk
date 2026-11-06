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

from imperal_sdk.code_index import _lang_for, _slashes

_PY_EXT = (".py", ".pyi")
_TS_EXT = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".d.ts", ".d.mts", ".d.cts", ".vue",
           ".svelte", ".astro")
_JS_TO_TS = {".js": (".ts", ".tsx", ".d.ts"), ".jsx": (".tsx",), ".mjs": (".mts", ".d.mts"), ".cjs": (".cts", ".d.cts")}
_BUILD_DIRS = ("dist", "build", "lib", "out", "esm", "cjs")
_SELF = ("self", "cls", "this")
BY_NAME_SHOWN = 15


# languages whose scope facts come from ``code_langs`` (resolved here by their own module rules)
_OTHER = frozenset({"go", "rust", "java", "kotlin", "csharp", "php", "ruby"})
# languages whose files share one namespace by a declared package (``Binding.kind == "package"``)
_FAMILY = {"java": "jvm", "kotlin": "jvm", "csharp": "cs", "php": "php"}
_PKG = "\0pkg:"
_CALL = "()"              # a chain part: the value a call returns (``code_langs.CALL``)          # a module key that is a group of files (a Go package, a Java package, a C# namespace)


def _lang(path: str) -> str:
    ext = posixpath.splitext(str(path).lower())[1]
    got = {".py": "python", ".pyi": "python", ".ts": "typescript", ".tsx": "tsx", ".mts": "typescript",
           ".cts": "typescript"}.get(
        ext, "javascript" if ext in (".js", ".jsx", ".mjs", ".cjs") else "")
    if got:
        return got
    other = _lang_for(str(path))
    return other if other in _OTHER else ""


_TEST_SUFFIXES = ("_test.py", ".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.tsx", ".spec.js",
                  ".spec.jsx", ".test.mjs", ".test.cjs", ".test.mts", ".spec.mts", "_test.go", "test.java",
                  "tests.java", "test.kt", "tests.kt", "test.cs", "tests.cs", "test.php", "_spec.rb", "_test.rb")


def is_test_path(path: str) -> bool:
    p = "/" + str(path).replace("\\", "/").lower()
    base = posixpath.basename(p)
    return ("/tests/" in p or "/test/" in p or "/__tests__/" in p or "/spec/" in p or base.startswith("test_")
            or base.endswith(_TEST_SUFFIXES))


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
    pkgs = {}
    for c in configs or []:
        if c.get("kind") == "package_json" and (c.get("data") or {}).get("name"):
            pkgs.setdefault(str(c["data"]["name"]), c)
    by_path = {_slashes(str(c.get("path") or "")).lstrip("/"): c for c in configs or []}
    ts = [dict(c, eff=_ts_effective(c, by_path, pkgs, set()))
          for c in configs or [] if c.get("kind") in ("tsconfig", "jsconfig")]
    return {"files": files, "lower": lower, "py": py, "ts": ts, "pkgs": pkgs}


def _ts_effective(c: dict, by_path: dict, pkgs: dict, seen: set) -> dict:
    """A tsconfig with its ``extends`` chain applied: ``base`` (the effective baseUrl directory or None), ``paths`` and
    ``paths_dir`` (the directory of the config that declared them -- paths resolve against baseUrl when there is one,
    else against that directory)."""
    data = c.get("data") or {}
    cdir = posixpath.dirname(_slashes(str(c.get("path") or "")).lstrip("/"))
    out = {"base": None, "paths": None, "paths_dir": None}
    for e in data.get("extends") or []:
        e = str(e)
        if e.startswith("."):
            parent = posixpath.normpath(posixpath.join(cdir, e))
        else:                                  # a workspace package's config: "@acme/tsconfig/base.json"
            name = next((n for n in sorted(pkgs, key=len, reverse=True) if e == n or e.startswith(n + "/")), None)
            if name is None:
                continue
            pdir = posixpath.dirname(_slashes(str(pkgs[name].get("path") or "")).lstrip("/"))
            parent = posixpath.normpath(posixpath.join(pdir, e[len(name):].lstrip("/") or "tsconfig.json"))
        if not parent.endswith(".json"):
            parent += ".json"
        if parent in by_path and parent not in seen:
            pe = _ts_effective(by_path[parent], by_path, pkgs, seen | {parent})
            for k, v in pe.items():
                if v is not None:
                    out[k] = v
    if data.get("baseUrl"):
        out["base"] = posixpath.normpath(posixpath.join(cdir, data["baseUrl"]))
    if data.get("paths"):
        out["paths"], out["paths_dir"] = data["paths"], cdir
    return out


def _package_module(modules: dict, spec: str, lang: str) -> str | None:
    """A bare specifier naming a package of this repo (a monorepo workspace): its ``exports`` subpath, else
    ``source`` / ``types`` / ``module`` / ``main``, else ``src/index`` / ``index``; a build output path is also tried as
    the source it was built from (``dist/x.js`` -> ``src/x.ts``)."""
    pkgs = modules.get("pkgs") or {}
    name = next((n for n in sorted(pkgs, key=len, reverse=True) if spec == n or spec.startswith(n + "/")), None)
    if name is None:
        return None
    c = pkgs[name]
    data = c.get("data") or {}
    pdir = posixpath.dirname(_slashes(str(c.get("path") or "")).lstrip("/"))
    sub = "." + spec[len(name):]
    exports = data.get("exports") or {}
    cands: list = list(exports.get(sub) or [])
    for pattern, targets in exports.items():
        pre, star, post = pattern.partition("*")
        if star and sub.startswith(pre) and sub.endswith(post) and len(sub) >= len(pre) + len(post):
            middle = sub[len(pre):len(sub) - len(post)] if post else sub[len(pre):]
            cands += [t.replace("*", middle) for t in targets]
    if sub == ".":
        cands += [data.get(k) for k in ("source", "types", "module", "main") if data.get(k)] + ["src/index", "index"]
    else:
        cands += [sub, "src/" + sub[2:]]
    for t in cands:
        t = str(t).lstrip("./") if str(t).startswith("./") else str(t)
        for v in _source_forms(t):
            got = _probe(modules, posixpath.join(pdir, v) if pdir else v, lang)
            if got:
                return got
    return None


def _source_forms(t: str) -> list:
    out = [t]
    for d in (".d.ts", ".d.mts", ".d.cts"):
        if t.endswith(d):
            out.append(t[:-len(d)])
    head, _, rest = t.partition("/")
    if head in _BUILD_DIRS and rest:
        for x in list(out):
            r = x.partition("/")[2]
            stem, ext = posixpath.splitext(r)
            out += ["src/" + (stem if ext in (".js", ".mjs", ".cjs", ".jsx") else r)]
    return out


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
    if ext in _JS_TO_TS:
        cands += [stem + e for e in _JS_TO_TS[ext]]
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
        eff = c.get("eff") or _ts_effective(c, {}, {}, set())
        base_dir = eff["base"] if eff["base"] is not None else (eff["paths_dir"] or "")
        for pattern, targets in (eff["paths"] or {}).items():
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
        if eff["base"] is not None:
            got = _probe(modules, posixpath.join(base_dir, spec), lang)
            if got:
                return got
    return _package_module(modules, spec, lang)


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
        self._pkgs: dict = {}                 # module key -> (files, names before the asked ones)
        self.ns: dict = {}                    # (family, package) -> files that declare it
        self.dirs: dict = {}                  # Go: directory -> its .go files (one package)
        self.qual: dict = {}                  # Ruby: qualname -> files defining it (constants are global)
        for path in sorted(self.facts):
            fx = self.facts[path]
            lang = _lang(path)
            if fx is None or lang not in _OTHER:
                continue
            fam = _FAMILY.get(lang)
            if fam:
                for pk in [b.module for b in fx.bindings if b.kind == "package"] or [""]:
                    self.ns.setdefault((fam, pk), []).append(path)
            elif lang == "go":
                self.dirs.setdefault(posixpath.dirname(path), []).append(path)
            elif lang == "ruby":
                for d in fx.defs:
                    self.qual.setdefault(d.qualname, []).append(path)
        self.go_mods = sorted(((posixpath.dirname(_slashes(c.get("path") or "")).lstrip("/"),
                                str((c.get("data") or {}).get("module") or ""))
                               for c in self.configs or [] if c.get("kind") == "go_mod"),
                              key=lambda x: -len(x[1]))
        self.crates = [(posixpath.dirname(_slashes(c.get("path") or "")).lstrip("/"),
                        str((c.get("data") or {}).get("name") or "").replace("-", "_"),
                        str((c.get("data") or {}).get("lib") or ""))
                       for c in self.configs or [] if c.get("kind") == "cargo"]

    def defs(self, path: str) -> dict:
        if path not in self._defs:
            fx = self.facts.get(path)
            self._defs[path] = {d.qualname: d for d in (fx.defs if fx else [])}
        return self._defs[path]

    def bindings(self, path: str) -> list:
        fx = self.facts.get(path)
        return sorted(fx.bindings, key=lambda b: b.line) if fx else []

    def module(self, from_path: str, spec: str) -> str | None:
        lang = _lang(from_path)
        if lang in _OTHER:
            return self._other_module(from_path, str(spec or ""), lang)
        return resolve_module(self.modules, from_path, spec, "python" if lang == "python" else "ts",
                              self.configs)

    # ---- module rules of Go, Rust, Java/Kotlin, C#, PHP, Ruby ----

    def _pkg(self, key: str, files: list, prefix: list) -> str | None:
        if not files:
            return None
        self._pkgs[_PKG + key] = (list(files), list(prefix))
        return _PKG + key

    def _other_module(self, from_path: str, spec: str, lang: str):
        if not spec:
            return None
        fam = _FAMILY.get(lang)
        if fam:
            # a package / namespace, or a type inside one (Java ``import static a.b.C.m``, ``using static``)
            if (fam, spec) in self.ns:
                return self._pkg(f"{fam}:{spec}", self.ns[(fam, spec)], [])
            parent, _, cls = spec.rpartition(".")
            if cls and (fam, parent) in self.ns:
                return self._pkg(f"{fam}:{spec}", self.ns[(fam, parent)], [cls])
            return None
        if lang == "go":
            for d, mod in self.go_mods:
                if mod and (spec == mod or spec.startswith(mod + "/")):
                    rel = spec[len(mod):].strip("/")
                    pdir = posixpath.normpath(posixpath.join(d, rel)) if (d or rel) else ""
                    pdir = "" if pdir == "." else pdir
                    return self._pkg(f"go:{pdir}", self.dirs.get(pdir) or [], [])
            return None
        if lang == "rust":
            return self._rust_module(from_path, spec)
        if lang == "ruby":
            if spec.startswith("."):
                base = posixpath.normpath(posixpath.join(posixpath.dirname(from_path), spec))
                if base.startswith(".."):
                    return None
                cands = [base if base.endswith(".rb") else base + ".rb"]
            else:
                b = spec if spec.endswith(".rb") else spec + ".rb"
                cands = [b, "lib/" + b] + sorted(p for p in self.facts if p.endswith("/lib/" + b))
            return next((c for c in cands if c in self.facts), None)
        return None

    def _rust_crate(self, from_path: str):
        """``(src_dir, root_file)`` of the crate holding ``from_path``: the nearest Cargo.toml, else the nearest
        directory above it that holds ``lib.rs`` / ``main.rs``."""
        best = None
        for d, _name, lib in self.crates:
            if not d or from_path.startswith(d + "/"):
                if best is None or len(d) > len(best[0]):
                    best = (d, lib)
        if best is not None:
            d, lib = best
            if lib:
                root = posixpath.normpath(posixpath.join(d, lib))
                return posixpath.dirname(root), root
            src = posixpath.join(d, "src") if d else "src"
            for f in ("lib.rs", "main.rs"):
                if posixpath.join(src, f) in self.facts:
                    return src, posixpath.join(src, f)
            return src, None
        d = posixpath.dirname(from_path)
        while True:
            for f in ("lib.rs", "main.rs"):
                if posixpath.join(d, f).lstrip("/") in self.facts:
                    return d, posixpath.join(d, f).lstrip("/")
            if not d:
                return None, None
            d = posixpath.dirname(d)

    def _rust_module(self, from_path: str, spec: str):
        segs = [x for x in spec.split("::") if x]
        if not segs:
            return None
        src, root = self._rust_crate(from_path)
        if src is None:
            return None
        first = segs[0]
        rel = from_path[len(src) + 1:] if src else from_path
        here = rel[:-3].split("/") if rel.endswith(".rs") else rel.split("/")
        if (here and here[-1] == "mod") or (len(here) == 1 and here[0] in ("lib", "main")):
            here = here[:-1]
        other = next(((d, lib) for d, name, lib in self.crates if name and name == first), None)
        local_mod = other is None and first not in ("crate", "self", "super") and any(
            b.local_name == first and b.module == "self::" + first for b in self.bindings(from_path))
        if first == "crate":
            mod, rest = [], segs[1:]
        elif first in ("self", "super") or local_mod:
            # ``self::x`` / ``super::x``; 2018 paths also start at a module declared here (``mod repo; use repo::X``)
            mod = here
            rest = segs
            while rest and rest[0] in ("self", "super"):
                if rest[0] == "super":
                    if not mod:
                        return None
                    mod = mod[:-1]
                rest = rest[1:]
        else:
            if other is None:
                return None                     # an external crate
            src, root = self._rust_crate(posixpath.join(other[0], "src", "lib.rs").lstrip("/"))
            if src is None:
                return None
            root = posixpath.join(src, "lib.rs") if posixpath.join(src, "lib.rs") in self.facts else root
            mod, rest = [], segs[1:]
        path = mod + rest
        # the longest prefix that is a file; the rest are inline modules / items inside it
        for k in range(len(path), -1, -1):
            if k == 0:
                f = root
            else:
                base = posixpath.join(src, *path[:k]) if src else "/".join(path[:k])
                f = next((c for c in (base + ".rs", base + "/mod.rs") if c in self.facts), None)
            if f:
                left = path[k:]
                return f if not left else self._pkg(f"rs:{f}:{'.'.join(left)}", [f], left)
        return None

    def _def_in_any(self, files: list, names: list):
        """The longest qualified match over a group of files (a C# partial class / Ruby reopened class: ``Repo`` in
        one file, ``Repo.Open`` in another -- the member wins)."""
        for k in range(min(len(names), 3), 0, -1):
            q = ".".join(names[:k])
            for f in files:
                if q in self.defs(f):
                    return f, q
        return None

    def _def_in(self, path: str, names: list):
        defs = self.defs(path)
        for k in range(min(len(names), 3), 0, -1):
            q = ".".join(names[:k])
            if q in defs:
                return path, q
        return None

    def _other_ref(self, path: str, lang: str, head: str, parts: list, in_def):
        """The rules past bindings and the file's own scopes: Rust ``crate::`` / ``super::`` paths, the same Go /
        Java / Kotlin / C# / PHP package, a fully qualified name, a Ruby constant from its lexical nesting."""
        names = [head] + parts
        if lang == "rust" and head in ("crate", "super"):
            for k in range(len(parts), -1, -1):
                tgt = self.module(path, "::".join([head] + parts[:k]))
                if tgt:
                    got = self.target(tgt, parts[k:])
                    if got:
                        return got[0], got[1], "path"
            return None
        if in_def and lang != "rust":
            # an implicit receiver member (``Flush()`` in a C# partial class, a Go / Kotlin / Ruby method of the
            # same type declared in another file)
            scope = in_def.split(".")
            for i in range(len(scope) - 1, 0, -1):
                got = self._member_elsewhere(path, lang, ".".join(scope[:i]), head)
                if got and self.defs(got[0])[got[1]].kind != "class":     # a nested type is a constant, below
                    return got[0], got[1], "self"
        if lang == "go":
            got = self._def_in_any([f for f in self.dirs.get(posixpath.dirname(path)) or [] if f != path], names)
            return (got[0], got[1], "package") if got else None
        fam = _FAMILY.get(lang)
        if fam:
            fx = self.facts.get(path)
            mine = [b.module for b in (fx.bindings if fx else []) if b.kind == "package"] or [""]
            seen = set()
            for pk in mine:
                chain = [pk]
                if fam == "cs":           # C#: the enclosing namespaces too
                    segs = pk.split(".")
                    chain = [".".join(segs[:i]) for i in range(len(segs), -1, -1)]
                for p in chain:
                    if p in seen:
                        continue
                    seen.add(p)
                    got = self._def_in_any([f for f in self.ns.get((fam, p)) or [] if f != path], names)
                    if got:
                        return got[0], got[1], "package"
            for k in range(len(names) - 1, 0, -1):     # a fully qualified name: com.acme.Repo.save
                got = self._def_in_any(self.ns.get((fam, ".".join(names[:k]))) or [], names[k:])
                if got:
                    return got[0], got[1], "qualified"
            return None
        if lang == "ruby":
            scope = in_def.split(".") if in_def else []
            for i in range(len(scope), -1, -1):
                for k in range(min(len(names), 3), 0, -1):
                    q = ".".join(scope[:i] + names[:k])
                    files = self.qual.get(q)
                    if files:
                        return (path if path in files else files[0]), q, "constant"
        return None

    def _member_elsewhere(self, path: str, lang: str, cls: str, member: str):
        """``self.member`` defined in another file of the same type: a Go method in another file of the package,
        a reopened Ruby class, a C# partial class, a PHP / Kotlin type split over files."""
        q = f"{cls}.{member}"
        if lang == "go":
            files = self.dirs.get(posixpath.dirname(path)) or []
        elif lang == "ruby":
            files = self.qual.get(q) or []
        elif lang in _FAMILY:
            fx = self.facts.get(path)
            pk = [b.module for b in (fx.bindings if fx else []) if b.kind == "package"] or [""]
            files = [f for p in pk for f in self.ns.get((_FAMILY[lang], p)) or []]
        else:
            return None
        return next(((f, q) for f in files if f != path and q in self.defs(f)), None)

    def target(self, path: str, names: list, depth: int = 0):
        """``(path, qualname)`` of ``names`` inside the module ``path`` (re-exports and star exports followed, a
        Python submodule of a package entered); ``qualname`` "" = the module itself."""
        if depth > 8 or not path:
            return None
        if path in self._pkgs:
            files, prefix = self._pkgs[path]
            names = prefix + list(names)
            return self._def_in_any(files, names) if names else None
        if not names:
            return path, ""
        defs = self.defs(path)
        for k in range(min(len(names), 3), 0, -1):
            q = ".".join(names[:k])
            if q in defs:
                return path, q
        alias = next((b.imported for b in self.bindings(path)
                      if b.kind == "default" and b.local_name == names[0] and b.imported), None)
        if alias and alias != names[0]:      # ``export default Foo`` / ``exports.x = y``: the name it stands for
            return self.target(path, [alias] + list(names[1:]), depth + 1)
        if names[0] == "default":
            return path, ""                  # an anonymous default export: the module itself
        for b in self.bindings(path):
            if b.local_name == names[0] and b.kind in ("import", "reexport"):
                tgt = self.module(path, b.module)
                if tgt is None:
                    return None
                rest = ([b.imported] if b.imported else []) + names[1:]
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

    def resolve_ref(self, path: str, head: str, chain: str, in_def: str | None, depth: int = 0):
        """One reference -> ``(path, qualname, origin)``, ``"external"`` (bound to a module outside the repo, or
        instance data) or None (unresolved)."""
        parts = [x for x in chain.split(".") if x] if chain else []
        if _CALL in parts and depth < 4:
            # ``F().m`` (a local typed by its initialiser ``x := F()``): F, then m on the type F declares it returns
            i = parts.index(_CALL)
            got = self.resolve_ref(path, head, ".".join(parts[:i]), in_def, depth + 1)
            rest = parts[i + 1:]
            if not isinstance(got, tuple) or not rest:
                return got
            ret = next((b.imported for b in self.bindings(got[0])
                        if b.kind == "returns" and b.local_name == got[1] + _CALL and b.imported), None)
            if not ret:
                return got
            tp = [x for x in ret.split(".") if x]
            typed = self.resolve_ref(got[0], tp[0], ".".join(tp[1:] + rest), got[1], depth + 1)
            return (typed[0], typed[1], "returns") if isinstance(typed, tuple) and typed[1] else got
        bound = [b for b in self.bindings(path) if b.local_name == head and b.kind != "star"]
        lang = _lang(path)
        if bound:
            b = bound[-1]
            if lang == "rust" and b.imported and b.module:     # ``use crate::store;`` names the module itself
                sub = self.module(path, f"{b.module}::{b.imported}")
                if sub:
                    got = self.target(sub, parts)
                    return (got[0], got[1], "binding") if got else "external"
            tgt = self.module(path, b.module)
            if tgt is None:
                return "external"
            names = ([b.imported] if b.imported else []) + parts
            if not names and tgt in self.facts and any(x.kind == "default" and x.local_name == "default"
                                                       for x in self.bindings(tgt)):
                names = ["default"]           # ``const f = require("./f"); f()``: the module's default export
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
                    if member in defs:
                        return path, member, "self"
                    got = self._member_elsewhere(path, lang, cls, parts[0]) if lang in _OTHER else None
                    return (got[0], got[1], "self") if got else "external"
                if d is None and lang in _OTHER and k == len(q) - 1:
                    # the type is declared in another file of the package (Go methods live beside their type)
                    member = f"{cls}.{parts[0]}"
                    if member in defs:
                        return path, member, "self"
                    got = self._member_elsewhere(path, lang, cls, parts[0])
                    if got:
                        return got[0], got[1], "self"
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
        if lang in _OTHER:
            return self._other_ref(path, lang, head, parts, in_def)
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
