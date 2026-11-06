# SPDX-License-Identifier: AGPL-3.0-only
"""Scope facts for Go, Rust, Java, Kotlin, C#, PHP and Ruby (report 06.11: "the graph does not work with all languages").

``code_index.scope_facts`` walked only Python and TS/JS; every other language went through the TS walker and came out
with no imports and no references -- so no links. Here ONE walker reads the same facts (definitions, bindings with
aliases, reference chains with the enclosing definition) for each of these languages from a table of the grammar's
own node types (read off each tree-sitter grammar, nothing per repository):

* ``defs`` -- ``code_index.DEF_NODES``; a Go method is ``Type.Method`` (its receiver), Rust ``impl T`` / ``impl X for
  T`` members are ``T.method``, a Ruby ``class A::B`` is ``A.B``;
* bindings -- ``import`` (Go, Java/Kotlin, Rust ``use``, C# ``using X = A.B``, PHP ``use``), ``star`` (``.*``, Rust
  ``::*``, C# ``using A.B;``, Go dot import, Ruby ``require``), and ``package`` (the file's own package / namespace,
  ``local_name`` "") -- the key the resolver groups files by;
* refs -- ``head`` + dotted ``chain`` (``db.Open``, ``self.go``, ``crate.util.helper``, ``Billing.Tax.rate``); the
  receiver of a method (Go ``s``, ``this``, ``$this``, ``self``, ``Self``) is ``self``; locals and parameters are
  dropped as in Python.

Module resolution for these languages lives with the other resolution rules in ``code_links``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from imperal_sdk.code_index import DEF_NODES, Binding, Def, Ref, _first_line, _line_of, _name_of, _retype, _type_chain


def _f(node, name):
    return node.child_by_field_name(name) if node is not None else None


@dataclass(frozen=True)
class Spec:
    idents: frozenset                       # node types that name something (a chain's head or a bare use)
    types: frozenset = frozenset()          # of those, type names -> ref kind "type"
    member: dict = field(default_factory=dict)   # node type -> (object field, name field): a.b
    calls: dict = field(default_factory=dict)    # call node type -> callee field ("" = the call node is the chain)
    self_words: frozenset = frozenset()     # the receiver's names
    inherit: frozenset = frozenset()        # node types whose names are base types
    locals: dict = field(default_factory=dict)   # node type -> field (None: every name below it) declaring locals
    decl_parents: frozenset = frozenset()   # a name directly under these node types declares, never uses (kotlin)
    scopes: dict = field(default_factory=dict)   # non-definition node -> field naming a qualname scope (rust impl)
    skip: frozenset = frozenset()           # subtrees without references
    transparent: frozenset = frozenset()    # definition-like nodes that add no name (C# namespace, kotlin companion)


SPECS: dict = {
    "go": Spec(
        idents=frozenset({"identifier", "type_identifier", "package_identifier"}),
        types=frozenset({"type_identifier"}),
        member={"selector_expression": ("operand", "field"), "qualified_type": ("package", "name")},
        calls={"call_expression": "function", "composite_literal": "type"},
        locals={"short_var_declaration": "left", "range_clause": "left", "var_spec": "name",
                "parameter_declaration": "name", "variadic_parameter_declaration": "name", "const_spec": "name",
                "func_literal": None},
        inherit=frozenset({"interface_type"}),
        skip=frozenset({"import_declaration", "package_clause", "interpreted_string_literal",
                        "raw_string_literal", "comment", "field_identifier"}),
    ),
    "rust": Spec(
        idents=frozenset({"identifier", "type_identifier", "self", "crate", "super"}),
        types=frozenset({"type_identifier"}),
        member={"field_expression": ("value", "field"), "scoped_identifier": ("path", "name"),
                "scoped_type_identifier": ("path", "name"), "generic_type": ("type", None)},
        calls={"call_expression": "function", "struct_expression": "name", "macro_invocation": ""},
        self_words=frozenset({"self", "Self"}),
        locals={"let_declaration": "pattern", "parameter": "pattern", "closure_parameters": None,
                "for_expression": "pattern", "match_arm": "pattern", "if_let_expression": "pattern",
                "let_condition": "pattern"},
        inherit=frozenset({"trait_bounds"}),
        scopes={"impl_item": "type"},
        skip=frozenset({"use_declaration", "string_literal", "raw_string_literal", "line_comment",
                        "block_comment", "attribute_item", "inner_attribute_item", "field_identifier",
                        "lifetime", "primitive_type", "token_tree"}),
    ),
    "java": Spec(
        idents=frozenset({"identifier", "type_identifier", "this"}),
        types=frozenset({"type_identifier"}),
        member={"field_access": ("object", "field"), "method_invocation": ("object", "name"),
                "scoped_type_identifier": (None, None), "generic_type": (None, None)},
        calls={"method_invocation": "", "object_creation_expression": "type"},
        self_words=frozenset({"this"}),
        locals={"variable_declarator": "name", "formal_parameter": "name", "catch_formal_parameter": "name",
                "spread_parameter": None, "lambda_expression": "parameters", "enhanced_for_statement": "name",
                "resource": "name"},
        inherit=frozenset({"superclass", "super_interfaces", "extends_interfaces"}),
        skip=frozenset({"import_declaration", "package_declaration", "string_literal", "line_comment",
                        "block_comment", "marker_annotation", "annotation"}),
    ),
    "kotlin": Spec(
        idents=frozenset({"simple_identifier", "type_identifier", "this_expression"}),
        types=frozenset({"type_identifier"}),
        member={"navigation_expression": ("@0", "@suffix"), "user_type": ("@types", None)},
        calls={"call_expression": "@0", "constructor_invocation": "@0"},
        self_words=frozenset({"this"}),
        locals={"variable_declaration": None, "parameter": "@0", "class_parameter": "@name",
                "lambda_parameters": None, "for_statement": "@decl"},
        decl_parents=frozenset({"variable_declaration", "parameter", "class_parameter", "function_declaration",
                                "class_declaration", "object_declaration", "type_alias", "value_argument_label",
                                "enum_entry", "type_parameter", "import_alias", "package_header"}),
        inherit=frozenset({"delegation_specifier"}),
        transparent=frozenset({"companion_object"}),
        skip=frozenset({"string_literal", "line_comment",
                        "multiline_comment", "annotation"}),
    ),
    "csharp": Spec(
        idents=frozenset({"identifier", "this"}),
        member={"member_access_expression": ("expression", "name"), "qualified_name": ("qualifier", "name"),
                "generic_name": (None, None)},
        calls={"invocation_expression": "function", "object_creation_expression": "type"},
        self_words=frozenset({"this"}),
        locals={"variable_declarator": "name", "parameter": "name", "foreach_statement": "left",
                "catch_declaration": "name", "implicit_parameter": None, "declaration_expression": "name",
                "lambda_expression": "parameters"},
        inherit=frozenset({"base_list"}),
        transparent=frozenset({"namespace_declaration", "file_scoped_namespace_declaration"}),
        skip=frozenset({"using_directive", "string_literal", "verbatim_string_literal",
                        "interpolated_string_expression", "comment", "attribute_list"}),
    ),
    "php": Spec(
        idents=frozenset({"name", "variable_name", "qualified_name", "relative_scope"}),
        member={"member_call_expression": ("object", "name"), "scoped_call_expression": ("scope", "name"),
                "member_access_expression": ("object", "name"),
                "class_constant_access_expression": ("@0", "@1"), "nullsafe_member_call_expression": ("object", "name")},
        calls={"function_call_expression": "function", "member_call_expression": "", "scoped_call_expression": "",
               "object_creation_expression": "@0", "nullsafe_member_call_expression": ""},
        self_words=frozenset({"this", "self", "static"}),
        inherit=frozenset({"base_clause", "class_interface_clause"}),
        skip=frozenset({"namespace_use_declaration", "namespace_definition", "string", "encapsed_string",
                        "comment", "php_tag", "text", "attribute_list", "heredoc", "nowdoc"}),
    ),
    "ruby": Spec(
        idents=frozenset({"identifier", "constant", "self"}),
        types=frozenset({"constant"}),
        member={"call": ("receiver", "method"), "scope_resolution": ("scope", "name")},
        calls={"call": ""},
        self_words=frozenset({"self"}),
        locals={"assignment": "left", "method_parameters": None, "block_parameters": None,
                "lambda_parameters": None, "operator_assignment": "left", "for": "pattern",
                "exception_variable": None},
        inherit=frozenset({"superclass"}),
        skip=frozenset({"string", "comment", "heredoc_body", "simple_symbol", "symbol", "regex"}),
    ),
}

LANGS = frozenset(SPECS)
# the field declarations of a type (``this.repo.save()`` / ``s.db.Query()`` -> the field's type)
_FIELDS = {"go": ("field_declaration",), "rust": ("field_declaration",), "java": ("field_declaration",),
           "csharp": ("field_declaration", "property_declaration"),
           "kotlin": ("property_declaration", "class_parameter"),
           "php": ("property_declaration", "property_promotion_parameter")}
_IMPLICIT_THIS = frozenset({"java", "csharp", "kotlin"})
# where a definition declares what it returns (``x := NewShaper()`` -> ``x`` is a ``Shaper``)
_RETURNS = {"go": "result", "rust": "return_type", "java": "type", "csharp": "returns", "php": "return_type"}
# a call expression -> its callee (an initialiser ``x := F()`` types ``x`` by F's declared return)
_CALLEE = {"go": "function", "rust": "function", "java": "", "csharp": "function", "kotlin": "@0"}
CALL = "()"                       # a chain part: "the value this call returns"
_RUBY_LOADS = ("require", "require_relative", "load")


def _child(node, sel):
    """A field (``"name"``), a positional named child (``"@0"``, ``"@1"``) or a kotlin special."""
    if node is None or sel is None:
        return None
    if not sel.startswith("@"):
        return node.child_by_field_name(sel)
    named = node.named_children
    if sel[1:].isdigit():
        i = int(sel[1:])
        return named[i] if i < len(named) else None
    if sel == "@suffix":       # kotlin navigation_suffix -> its name
        suf = next((c for c in named if c.type == "navigation_suffix"), None)
        return next((c for c in (suf.named_children if suf else []) if c.type == "simple_identifier"), None)
    if sel == "@name":
        return next((c for c in named if c.type == "simple_identifier"), None)
    if sel == "@decl":
        return next((c for c in named if c.type in ("variable_declaration", "multi_variable_declaration")), None)
    return None


class _Walk:
    def __init__(self, lang: str, src: bytes):
        self.lang = lang
        self.sp: Spec = SPECS[lang]
        self.defs_of = DEF_NODES.get(lang, {})
        self.src = src
        self.defs: list = []
        self.bindings: list = []
        self.refs: list = []
        self._seen: set = set()
        self.consumed: set = set()       # names a chain already reported
        self.typed: dict = {}            # def qualname -> {local: type chain}
        self.fields: dict = {}           # type qualname -> {field: type chain}

    def text(self, node) -> str:
        return self.src[node.start_byte:node.end_byte].decode("utf-8", "replace")

    # ---- names ----

    def _word(self, node, selfnames: set) -> str | None:
        t, s = node.type, self.text(node)
        if self.lang == "php":
            if t == "variable_name":
                return "self" if s == "$this" else None        # a variable is never a module-level name
            if t == "qualified_name":
                return None                                   # handled as a chain
        if t in ("this", "this_expression"):
            return "self"
        if s in selfnames or s in self.sp.self_words:
            return "self"
        return s

    def chain(self, node, selfnames: set, used: set) -> list | None:
        """``[head, part, ...]`` of a name or a member access; ``used`` collects the nodes the chain consumed."""
        t = node.type
        if self.lang == "php" and t == "qualified_name":
            used.add(node.id)
            self.consumed.add(node.id)
            parts = [x for x in self.text(node).replace("\\", ".").split(".") if x]
            return parts or None
        if t in self.sp.idents:
            w = self._word(node, selfnames)
            if not w:
                return None
            used.add(node.id)
            self.consumed.add(node.id)
            return [w]
        if t in ("this", "self", "this_expression"):
            used.add(node.id)
            return ["self"]
        m = self.sp.member.get(t)
        if m is None:
            return None
        obj_sel, name_sel = m
        used.add(node.id)
        if self.lang == "kotlin" and t == "user_type":
            parts = [self.text(c) for c in node.named_children if c.type == "type_identifier"]
            return parts or None
        if obj_sel is None and name_sel is None:     # a wrapper (generic type): its first named child
            inner = node.named_children[0] if node.named_children else None
            return self.chain(inner, selfnames, used) if inner is not None else None
        obj, name = _child(node, obj_sel), _child(node, name_sel)
        if obj is None and self.lang == "csharp" and t == "member_access_expression":
            obj = next((c for c in node.children if c.type == "this"), None)
        if name is None:
            return self.chain(obj, selfnames, used) if obj is not None else None
        nm = self.text(name)
        if self.lang == "php" and name.type == "variable_name":
            return None
        used.add(name.id)
        self.consumed.add(name.id)
        if obj is None:
            # a call with no receiver (java ``go()``, ruby ``helper(n)``): the name alone
            return [self._word(name, selfnames) or nm]
        left = self.chain(obj, selfnames, used)
        return left + [nm] if left else None

    def ref(self, parts: list, in_def, kind: str, line: int, local: set) -> None:
        if parts and (self.typed or self.fields):
            parts = _retype(parts, in_def, self.typed, self.fields, local, self.lang in _IMPLICIT_THIS)
        if not parts or (parts[0] in local and parts[0] != "self"):
            return
        r = Ref(parts[0], ".".join(parts[1:6]), in_def, kind, line)
        if r not in self._seen:
            self._seen.add(r)
            self.refs.append(r)

    # ---- locals of a definition ----

    def locals_of(self, node) -> set:
        out: set = set()
        stack = list(node.children)
        while stack:
            n = stack.pop()
            if n.type in self.defs_of:
                continue
            if n.type in self.sp.locals:
                sel = self.sp.locals[n.type]
                tgt = n if sel is None else _child(n, sel)
                if tgt is not None:
                    out |= self._names_in(tgt)
            stack.extend(n.children)
        return out

    def typed_of(self, node) -> dict:
        """``{local: type chain}`` of a definition: declared types of parameters and locals, ``new T()`` /
        ``T{}`` / ``T()`` (kotlin) / ``T::new()`` (rust) initialisers."""
        out: dict = {}
        stack = list(node.children)
        while stack:
            n = stack.pop()
            if n.type in self.defs_of:
                continue
            if n.type in self.sp.locals and self.sp.locals[n.type] is not None:
                tgt = _child(n, self.sp.locals[n.type])
                ch = self._decl_type(n)
                if tgt is not None and ch:
                    for name in self._names_in(tgt):
                        out[name] = ch
            stack.extend(n.children)
        return out

    def _decl_type(self, n) -> list | None:
        tnode = _f(n, "type")
        if tnode is None and n.parent is not None and n.type == "variable_declarator":
            tnode = _f(n.parent, "type")
        if tnode is None:
            tnode = next((c for c in n.named_children if c.type == "user_type"), None)
        if tnode is not None and tnode.type != "implicit_type":
            ch = _type_chain(self.src, tnode)
            if ch and ch != ["var"]:            # java ``var x = ...``: inferred, see the initialiser
                return ch
        for c in n.named_children:                  # the initialiser
            v = c
            if v.type == "expression_list" and v.named_children:           # go ``x := F()``
                v = v.named_children[0]
            ch = self._call_type(v)
            if ch:
                return ch
            if v.type == "unary_expression" and v.named_children:          # go &T{}
                v = v.named_children[0]
            if v.type in ("object_creation_expression", "composite_literal"):
                return _type_chain(self.src, _f(v, "type") or (v.named_children[0] if v.named_children else None))
            if self.lang == "kotlin" and v.type == "call_expression" and v.named_children:
                callee = v.named_children[0]
                if callee.type == "simple_identifier" and self.text(callee)[:1].isupper():
                    return [self.text(callee)]
            if self.lang == "rust" and v.type == "call_expression":
                fn = _f(v, "function")
                path = _f(fn, "path") if fn is not None and fn.type == "scoped_identifier" else None
                ch = _type_chain(self.src, path) if path is not None else None
                if ch and ch[-1][:1].isupper():
                    return ch
        return None

    def _call_type(self, v) -> list | None:
        """``F()`` / ``pkg.F()`` / ``a.b.make()`` as ``[F, "()"]``: the value the call returns (the resolver reads the
        callee's declared return type)."""
        call_types = {"go": "call_expression", "rust": "call_expression", "java": "method_invocation",
                      "csharp": "invocation_expression", "kotlin": "call_expression"}
        if v.type != call_types.get(self.lang):
            return None
        sel = _CALLEE.get(self.lang)
        fn = v if sel == "" else _child(v, sel)
        if fn is None:
            return None
        used: set = set()
        before = set(self.consumed)
        parts = self.chain(fn, set(), used)
        self.consumed = before                # a probe, not a walk: nothing is consumed
        if not parts or (self.lang == "kotlin" and parts[-1][:1].isupper() and len(parts) == 1):
            return None                       # kotlin ``T()`` is a constructor (``_decl_type``)
        if self.lang == "rust" and len(parts) >= 2 and parts[-2][:1].isupper():
            return None                       # rust ``T::new()``: the type itself (``_decl_type``)
        return parts + [CALL]

    def fields_of(self, node) -> dict:
        out: dict = {}
        kinds = _FIELDS.get(self.lang, ())
        stack = list(node.children)
        while stack:
            n = stack.pop()
            if n.type in self.defs_of and n.type not in ("constructor_declaration",) and not (
                    self.lang == "php" and n.type == "method_declaration"):
                continue
            if n.type in kinds:
                ch = self._decl_type(n)
                if not ch:
                    vd = next((c for c in n.named_children if c.type in ("variable_declaration",)), None)
                    ch = self._decl_type(vd) if vd is not None else None
                names = self._field_names(n)
                if ch:
                    for name in names:
                        out[name] = ch
                continue
            stack.extend(n.children)
        return out

    def _field_names(self, n) -> list:
        name = _f(n, "name")
        if name is not None:
            return [self.text(name).lstrip("$")]
        out = []
        for c in _all(n, "variable_declarator") + _all(n, "property_element"):
            nm = _f(c, "name") or next((x for x in c.named_children if x.type in ("identifier", "variable_name")), None)
            if nm is not None:
                out.append(self.text(nm).lstrip("$"))
        if not out:
            vd = next((c for c in n.named_children if c.type == "variable_declaration"), n)
            nm = next((c for c in vd.named_children if c.type == "simple_identifier"), None)
            if nm is not None:
                out.append(self.text(nm))
        return out

    def _names_in(self, node) -> set:
        if node.type in ("identifier", "simple_identifier", "variable_name") or \
                (self.lang == "ruby" and node.type == "identifier"):
            return {self.text(node).lstrip("$")}
        out: set = set()
        for c in node.named_children:
            if c.type in ("type_identifier", "constant", "scoped_identifier", "scoped_type_identifier",
                          "user_type", "qualified_name") or c.type in self.sp.types:
                continue
            out |= self._names_in(c)
        return out

    # ---- imports ----

    def imports(self, node) -> bool:
        lang, t, line = self.lang, node.type, _line_of(node)
        add = self.bindings.append
        if lang == "go" and t == "import_declaration":
            for spec in _all(node, "import_spec"):
                p = _f(spec, "path")
                if p is None:
                    continue
                path = self.text(p).strip('"`')
                alias = _f(spec, "name")
                a = self.text(alias) if alias is not None else ""
                if a == "_":
                    continue
                if a == ".":
                    add(Binding("*", path, None, "star", _line_of(spec)))
                else:
                    add(Binding(a or path.rstrip("/").rsplit("/", 1)[-1], path, None, "import", _line_of(spec)))
            return True
        if lang == "rust" and t == "use_declaration":
            arg = _f(node, "argument")
            if arg is not None:
                self._rust_use(arg, [], line)
            return True
        if lang == "rust" and t == "mod_item" and _f(node, "body") is None:
            n = _f(node, "name")
            if n is not None:          # ``mod store;`` -- the file store.rs / store/mod.rs, bound under its name
                add(Binding(self.text(n), "self::" + self.text(n), None, "import", line))
            return True
        if lang == "java" and t in ("import_declaration", "package_declaration"):
            name = next((c for c in node.named_children if c.type in ("scoped_identifier", "identifier")), None)
            if name is None:
                return True
            full = self.text(name)
            if t == "package_declaration":
                add(Binding("", full, None, "package", line))
            elif any(c.type == "asterisk" for c in node.children):
                add(Binding("*", full, None, "star", line))
            else:
                mod, _, last = full.rpartition(".")
                add(Binding(last, mod, last, "import", line))
            return True
        if lang == "kotlin" and t in ("import_header", "package_header"):
            ident = next((c for c in node.named_children if c.type == "identifier"), None)
            if ident is None:
                return True
            full = ".".join(self.text(c) for c in ident.named_children) or self.text(ident)
            if t == "package_header":
                add(Binding("", full, None, "package", line))
            elif any(c.type == "wildcard_import" for c in node.children):
                add(Binding("*", full, None, "star", line))
            else:
                alias = next((c for c in node.named_children if c.type == "import_alias"), None)
                mod, _, last = full.rpartition(".")
                local = self.text(alias.named_children[-1]) if alias is not None and alias.named_children else last
                add(Binding(local, mod, last, "import", line))
            return True
        if lang == "csharp" and t == "using_directive":
            alias = _f(node, "name")
            target = next((c for c in node.named_children if (alias is None or c.id != alias.id)
                           and c.type in ("qualified_name", "identifier", "generic_name")), None)
            if target is None:
                return True
            full = self.text(target)
            if alias is not None:
                mod, _, last = full.rpartition(".")
                add(Binding(self.text(alias), mod, last, "import", line))
            else:                       # ``using A.B;`` and ``using static A.B.C;``: every name of it
                add(Binding("*", full, None, "star", line))
            return True
        if lang == "csharp" and t in ("namespace_declaration", "file_scoped_namespace_declaration"):
            n = _f(node, "name")
            if n is not None:
                add(Binding("", self.text(n), None, "package", line))
            return False                # its body is walked
        if lang == "php" and t == "namespace_definition":
            n = _f(node, "name")
            add(Binding("", self.text(n).replace("\\", ".") if n is not None else "", None, "package", line))
            return _f(node, "body") is None
        if lang == "php" and t == "namespace_use_declaration":
            group = _f(node, "body")
            prefix = ""
            if group is not None:
                pre = next((c for c in node.named_children if c.type == "namespace_name"), None)
                prefix = self.text(pre).replace("\\", ".").strip(".") if pre is not None else ""
            clauses = _all(group if group is not None else node, "namespace_use_clause")
            for cl in clauses:
                alias = _f(cl, "alias")
                tgt = next((c for c in cl.named_children if (alias is None or c.id != alias.id) and c.type in ("qualified_name", "name")),
                           None)
                if tgt is None:
                    continue
                full = ".".join(x for x in (prefix, self.text(tgt).replace("\\", ".").strip(".")) if x)
                mod, _, last = full.rpartition(".")
                add(Binding(self.text(alias) if alias is not None else last, mod, last, "import", _line_of(cl)))
            return True
        if lang == "ruby" and t == "call" and _f(node, "receiver") is None:
            m = _f(node, "method")
            if m is not None and self.text(m) in _RUBY_LOADS:
                args = _f(node, "arguments")
                s = next((c for c in (args.named_children if args else []) if c.type == "string"), None)
                content = "".join(self.text(c) for c in (s.named_children if s else []) if c.type == "string_content")
                if content:
                    spec = content if self.text(m) != "require_relative" or content.startswith(".") \
                        else "./" + content
                    add(Binding("*", spec, None, "star", line))
                return True
        return False

    def _rust_use(self, node, prefix: list, line: int) -> None:
        t = node.type
        add = self.bindings.append
        if t in ("scoped_identifier", "identifier", "crate", "self", "super"):
            segs = [x for x in self.text(node).split("::") if x]
            full = prefix + segs
            if full and full[-1] == "self":       # ``use a::{self}``: the module a
                full = full[:-1]
            if full:
                add(Binding(full[-1], "::".join(full[:-1]), full[-1], "import", line))
        elif t == "use_as_clause":
            p, a = _f(node, "path"), _f(node, "alias")
            if p is not None and a is not None:
                full = prefix + [x for x in self.text(p).split("::") if x]
                add(Binding(self.text(a), "::".join(full[:-1]), full[-1], "import", line))
        elif t == "scoped_use_list":
            p, lst = _f(node, "path"), _f(node, "list")
            pre = prefix + ([x for x in self.text(p).split("::") if x] if p is not None else [])
            for c in (lst.named_children if lst is not None else []):
                self._rust_use(c, pre, line)
        elif t == "use_list":
            for c in node.named_children:
                self._rust_use(c, prefix, line)
        elif t == "use_wildcard":
            inner = node.named_children[0] if node.named_children else None
            segs = prefix + ([x for x in self.text(inner).split("::") if x] if inner is not None else [])
            add(Binding("*", "::".join(segs), None, "star", line))

    # ---- the walk ----

    def def_name(self, node) -> str:
        if self.lang == "ruby":
            n = _f(node, "name")
            return self.text(n).replace("::", ".") if n is not None else ""
        return _name_of(node, self.src)

    def walk(self, node, scope: list, local: set, selfnames: set, inherit: bool, field_name: str | None,
             parent_type: str | None) -> None:
        t = node.type
        sp = self.sp
        in_def = ".".join(scope) if scope else None
        if node.id in self.consumed or self.imports(node) or t in sp.skip:
            return
        if self.lang == "php" and t == "variable_name" and self.text(node) != "$this":
            return                      # a PHP variable is never a module-level name
        if t in sp.transparent:
            for i, c in enumerate(node.children):
                if c.is_named and node.field_name_for_child(i) != "name":
                    self.walk(c, scope, local, selfnames, inherit, None, t)
            return
        kind = self.defs_of.get(t)
        if kind is not None:
            self._def(node, kind, scope, local, selfnames)
            return
        if t in sp.scopes:
            tn = _child(node, sp.scopes[t])
            name = self._type_name(tn) if tn is not None else ""
            for i, c in enumerate(node.children):
                if c.is_named:
                    self.walk(c, scope + ([name] if name else []), local, selfnames, inherit,
                              node.field_name_for_child(i), t)
            return
        inh = inherit or t in sp.inherit
        # a declaring name (a parameter, a local, a field) is not a use
        if self.lang == "java" and t == "type_identifier" and self.text(node) == "var":
            return
        if t in sp.idents and (parent_type in sp.decl_parents or
                               (field_name in ("name", "pattern", "alias", "label", "left")
                                and parent_type not in sp.member and parent_type not in sp.calls)):
            return
        callee_sel = sp.calls.get(t)
        if callee_sel is not None:
            fn = node if callee_sel == "" else _child(node, callee_sel)
            used: set = set()
            parts = self.chain(fn, selfnames, used) if fn is not None else None
            if parts:
                self.ref(parts, in_def, "inherit" if inh else "call", _line_of(node), local)
                self._rest(node, used, scope, local, selfnames, inh)
                return
        elif t in sp.idents or t in sp.member or (self.lang == "php" and t == "qualified_name"):
            used = set()
            parts = self.chain(node, selfnames, used)
            if parts:
                k = "inherit" if inh else ("type" if (t in sp.types or t in ("scoped_type_identifier", "user_type",
                                                                                 "qualified_type", "generic_type"))
                                           else "read")
                if self.lang == "ruby" and t == "identifier" and k == "read":
                    k = "call"            # a bare ruby name that is not a local is a method call
                self.ref(parts, in_def, k, _line_of(node), local)
                self._rest(node, used, scope, local, selfnames, inh)
                return
        for i, c in enumerate(node.children):
            if c.is_named:
                self.walk(c, scope, local, selfnames, inh, node.field_name_for_child(i), t)

    def _rest(self, node, used: set, scope, local, selfnames, inh) -> None:
        """The parts of a consumed chain that are not the chain itself (arguments, index expressions)."""
        for i, c in enumerate(node.children):
            if not c.is_named or c.id in self.consumed:
                continue
            if c.id in used:
                self._rest(c, used, scope, local, selfnames, inh)
            else:
                self.walk(c, scope, local, selfnames, inh, node.field_name_for_child(i), node.type)

    def _type_name(self, node) -> str:
        if node is None:
            return ""
        if node.type in ("type_identifier", "identifier", "constant", "simple_identifier", "name"):
            return self.text(node)
        for sel in ("type", "name"):
            inner = _f(node, sel)
            if inner is not None:
                return self._type_name(inner)
        for c in node.named_children:
            got = self._type_name(c)
            if got:
                return got
        return ""

    def _def(self, node, kind: str, scope: list, local: set, selfnames: set) -> None:
        lang = self.lang
        name = self.def_name(node)
        if not name:
            for c in node.named_children:
                self.walk(c, scope, local, selfnames, False, None, node.type)
            return
        mine = set(selfnames)
        qual_scope = list(scope)
        if lang == "go" and node.type == "method_declaration":
            recv = _f(node, "receiver")
            pd = next((c for c in (recv.named_children if recv else []) if c.type == "parameter_declaration"), None)
            tname = self._type_name(_f(pd, "type")) if pd is not None else ""
            rn = _f(pd, "name") if pd is not None else None
            if tname:
                qual_scope = [tname]
            if rn is not None:
                mine = {self.text(rn)}
        if lang == "go" and node.type == "type_spec":
            ty = _f(node, "type")
            kind = "class" if ty is not None and ty.type in ("struct_type", "interface_type") else "type"
        if lang == "ruby" and node.type == "singleton_method":
            kind = "method"
        if qual_scope and kind == "function" and lang in ("rust", "kotlin", "php", "java", "csharp"):
            kind = "method"
        qual = ".".join(qual_scope + [name])
        ret = _child(node, _RETURNS[lang]) if lang in _RETURNS and kind in ("function", "method") else None
        if ret is None and lang == "kotlin" and kind in ("function", "method"):
            ret = next((c for c in node.named_children if c.type in ("user_type", "nullable_type")), None)
        rch = _type_chain(self.src, ret) if ret is not None else None
        if rch == ["Self"] and qual_scope:
            rch = list(qual_scope)
        if rch:
            self.bindings.append(Binding(qual + CALL, "", ".".join(rch), "returns", _line_of(node)))
        self.defs.append(Def(name.rsplit(".", 1)[-1], qual, kind, _line_of(node), node.end_point[0] + 1,
                             _first_line(self.text(node)), self._exported(node, name)))
        inner_local = (local | self.locals_of(node)) - {"self"}
        typed = self.typed_of(node)
        if typed:
            self.typed[qual] = typed
        if kind == "class":
            fields = self.fields_of(node)
            if fields:
                self.fields.setdefault(qual, {}).update(fields)
        if lang == "go" and mine:
            inner_local -= mine
        name_node = _f(node, "name")
        for i, c in enumerate(node.children):
            if not c.is_named or (name_node is not None and c.id == name_node.id):
                continue
            fname = node.field_name_for_child(i)
            if (lang == "go" and fname == "receiver") or (lang == "ruby" and fname == "object"):
                continue
            self.walk(c, qual.split("."), inner_local, mine, False, fname, node.type)

    def _exported(self, node, name: str) -> bool:
        lang = self.lang
        base = name.rsplit(".", 1)[-1]
        if lang == "go":
            return base[:1].isupper()
        if lang == "rust":
            return any(c.type == "visibility_modifier" for c in node.children)
        if lang in ("java", "kotlin", "csharp", "php"):
            mods = " ".join(self.text(c) for c in node.children
                            if c.type in ("modifiers", "modifier", "visibility_modifier"))
            return "private" not in mods
        return True


def _all(node, typ: str) -> list:
    out, stack = [], [node]
    while stack:
        n = stack.pop()
        if n.type == typ:
            out.append(n)
        else:
            stack.extend(reversed(n.named_children))
    return out


def walk_facts(lang: str, tree, src: bytes) -> tuple:
    """``(defs, bindings, refs)`` of one file of ``lang`` (one of ``LANGS``)."""
    w = _Walk(lang, src)
    for c in tree.root_node.named_children:
        w.walk(c, [], set(), set(), False, None, tree.root_node.type)
    return w.defs, w.bindings, w.refs
