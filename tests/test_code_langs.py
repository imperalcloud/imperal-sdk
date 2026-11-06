"""Links for Go, Rust, Java, Kotlin, C#, PHP, Ruby (report 06.11: "the graph does not work with all languages").

Each language: a small repo, the exact files that use a definition, and a definition nobody uses -> no dependents.
"""
import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_language_pack")

from imperal_sdk import code_index as ci  # noqa: E402
from imperal_sdk.code_links import Linker, impact  # noqa: E402


def _lk(files: dict) -> Linker:
    facts, configs = {}, []
    for p, t in files.items():
        if ci.indexable(p) == "config":
            kind, data = ci.parse_config(p, t)
            configs.append({"path": p, "kind": kind, "data": data})
        else:
            facts[p] = ci.scope_facts(p, t)
    return Linker(facts, configs)


def _users(lk, sym, depth=1):
    return {i["id"]: i for i in impact(lk, [sym], depth=depth)["data"]["items"]}


GO = {
    "go.mod": "module example.com/app\n\ngo 1.22\n",
    "internal/db/db.go": "package db\n\nfunc Open(n int) *Conn { return newConn(n) }\n\n"
                         "func newConn(n int) *Conn { return &Conn{} }\n\ntype Conn struct{}\n\nfunc Unused() {}\n",
    "internal/db/conn.go": "package db\n\nfunc (c *Conn) Close() error { return c.flush() }\n",
    "internal/db/flush.go": "package db\n\nfunc (c *Conn) flush() error { return nil }\n",
    "svc/server.go": 'package svc\n\nimport (\n\t"fmt"\n\tstore "example.com/app/internal/db"\n)\n\n'
                     "type Server struct{}\n\nfunc (s *Server) Run(n int) error {\n\tc := store.Open(n)\n"
                     "\tfmt.Println(c)\n\treturn s.stop(c)\n}\n",
    "svc/stop.go": 'package svc\n\nimport "example.com/app/internal/db"\n\n'
                   "func (s *Server) stop(c *db.Conn) error { return c.Close() }\n",
    "cmd/main.go": 'package main\n\nimport "example.com/app/svc"\n\nfunc main() { s := &svc.Server{}; s.Run(1) }\n',
    "svc/server_test.go": "package svc\n\nfunc TestRun() { s := &Server{}; _ = s.Run(2) }\n",
}


def test_go_packages_through_go_mod_and_aliases():
    lk = _lk(GO)
    u = _users(lk, "Open")
    assert set(u) == {"svc/server.go"} and u["svc/server.go"]["user"] == "Server.Run"
    assert set(_users(lk, "Conn")) == {"svc/stop.go"}                   # a type through the package name
    assert set(_users(lk, "Server")) == {"cmd/main.go", "svc/server_test.go"}
    assert _users(lk, "Unused") == {}


def test_go_methods_across_files_of_a_package():
    lk = _lk(GO)
    # s.stop lives in stop.go, Server in server.go; c.flush in flush.go
    assert lk.resolve_ref("svc/server.go", "self", "stop", "Server.Run") == ("svc/stop.go", "Server.stop", "self")
    assert lk.resolve_ref("internal/db/conn.go", "self", "flush", "Conn.Close") == \
        ("internal/db/flush.go", "Conn.flush", "self")
    assert set(_users(lk, "newConn")) == set()                           # same file only
    assert impact(lk, ["newConn"])["same_file"][0]["user"] == "Open"


RUST = {
    "Cargo.toml": '[package]\nname = "my-app"\nversion = "0.1.0"\n',
    "src/lib.rs": "pub mod store;\nmod util;\npub use store::Repo;\n\npub fn entry() -> u32 { util::helper(1) }\n",
    "src/store.rs": "pub struct Repo { n: u32 }\n\nimpl Repo {\n    pub fn new() -> Self { Repo { n: 0 } }\n"
                    "    pub fn save(&self) -> u32 { self.n }\n}\n\npub fn open() -> Repo { Repo::new() }\n"
                    "pub fn lonely() {}\n",
    "src/util/mod.rs": "pub mod deep;\n\npub fn helper(x: u32) -> u32 { deep::inner(x) }\n",
    "src/util/deep.rs": "use crate::store::{Repo as R, open};\n\npub fn inner(x: u32) -> u32 {\n"
                        "    let r = open();\n    R::new();\n    super::super::store::open();\n    r.save() + x\n}\n",
    "src/bin/tool.rs": "use my_app::store;\n\nfn main() { store::open(); }\n",
}


def test_rust_crate_super_alias_and_mod_files():
    lk = _lk(RUST)
    assert set(_users(lk, "open")) == {"src/util/deep.rs", "src/bin/tool.rs"}
    assert set(_users(lk, "Repo.new")) == {"src/util/deep.rs"}
    assert set(_users(lk, "helper")) == {"src/lib.rs"}
    assert set(_users(lk, "inner")) == {"src/util/mod.rs"}
    assert _users(lk, "lonely") == {}


def test_rust_depth_through_the_enclosing_fn():
    lk = _lk(RUST)
    items = _users(lk, "inner", depth=2)
    assert items["src/util/mod.rs"]["depth"] == 1 and items["src/lib.rs"]["depth"] == 2


JAVA = {
    "src/main/java/com/acme/db/Repo.java":
        "package com.acme.db;\n\npublic class Repo {\n  public static Repo open() { return new Repo(); }\n"
        "  public void save() { flush(); }\n  private void flush() {}\n  public void unused() {}\n}\n",
    "src/main/java/com/acme/db/Cache.java":
        "package com.acme.db;\n\nclass Cache {\n  Repo backing() { return Repo.open(); }\n}\n",
    "src/main/java/com/acme/app/Svc.java":
        "package com.acme.app;\n\nimport com.acme.db.Repo;\nimport static com.acme.util.Strings.trim;\n\n"
        "public class Svc extends Base {\n  public int run(String s) {\n    Repo r = Repo.open();\n    r.save();\n"
        "    trim(s);\n    return 0;\n  }\n}\n",
    "src/main/java/com/acme/app/Base.java": "package com.acme.app;\n\npublic class Base {}\n",
    "src/main/java/com/acme/util/Strings.java":
        "package com.acme.util;\n\npublic final class Strings {\n  public static String trim(String s) { return s; }\n}\n",
    "src/main/kotlin/com/acme/web/Api.kt":
        "package com.acme.web\n\nimport com.acme.db.Repo as R\nimport com.acme.app.*\n\n"
        "class Api(private val svc: Svc) {\n  fun handle(): Int { R.open(); return svc.run(\"x\") }\n}\n"
        "fun build() = Api(Svc())\n",
    "src/test/java/com/acme/app/SvcTest.java":
        "package com.acme.app;\n\nclass SvcTest {\n  void t() { new Svc().run(\"a\"); }\n}\n",
}


def test_java_kotlin_packages_imports_static_and_same_package():
    lk = _lk(JAVA)
    assert set(_users(lk, "Repo.open")) == {"src/main/java/com/acme/db/Cache.java",
                                            "src/main/java/com/acme/app/Svc.java",
                                            "src/main/kotlin/com/acme/web/Api.kt"}
    assert set(_users(lk, "trim")) == {"src/main/java/com/acme/app/Svc.java"}
    assert set(_users(lk, "Base")) == {"src/main/java/com/acme/app/Svc.java"}           # same package, no import
    svc = _users(lk, "Svc")
    assert set(svc) == {"src/main/kotlin/com/acme/web/Api.kt", "src/test/java/com/acme/app/SvcTest.java"}
    assert svc["src/test/java/com/acme/app/SvcTest.java"]["group"] == "tests"
    assert _users(lk, "Repo.unused") == {}


CSHARP = {
    "Db/Repo.cs": "namespace Acme.Db\n{\n  public partial class Repo\n  {\n    public static Repo Open() => new Repo();\n"
                  "    public void Save() { Flush(); }\n  }\n}\n",
    "Db/Repo.Flush.cs": "namespace Acme.Db;\n\npublic partial class Repo\n{\n  void Flush() {}\n  public void Unused() {}\n}\n",
    "Core/Clock.cs": "namespace Acme\n{\n  public static class Clock { public static int Now() => 0; }\n}\n",
    "App/Svc.cs": "using System;\nusing Acme.Db;\nusing R = Acme.Db.Repo;\n\nnamespace Acme.App\n{\n"
                  "  public class Svc\n  {\n    public void Run() { var r = Repo.Open(); r.Save(); R.Open(); Clock.Now(); }\n"
                  "  }\n}\n",
}


def test_csharp_usings_alias_partial_and_parent_namespace():
    lk = _lk(CSHARP)
    assert set(_users(lk, "Repo.Open")) == {"App/Svc.cs"}
    assert set(_users(lk, "Clock.Now")) == {"App/Svc.cs"}                 # Acme is a parent of Acme.App
    assert lk.resolve_ref("Db/Repo.cs", "Flush", "", "Repo.Save") == ("Db/Repo.Flush.cs", "Repo.Flush", "self")
    assert _users(lk, "Repo.Unused") == {}


PHP = {
    "composer.json": '{"autoload": {"psr-4": {"App\\\\": "src/"}}}',
    "src/Models/User.php": "<?php\nnamespace App\\Models;\n\nclass User extends Model {\n"
                           "  public static function find($id) { return new static(); }\n"
                           "  public function save() { return $this->touch(); }\n  private function touch() {}\n}\n",
    "src/Models/Model.php": "<?php\nnamespace App\\Models;\n\nabstract class Model {}\n",
    "src/Support/helpers.php": "<?php\nnamespace App\\Support;\n\nfunction helper($x) { return $x; }\n"
                               "function unused() {}\n",
    "src/Http/Ctl.php": "<?php\nnamespace App\\Http;\n\nuse App\\Models\\User;\nuse App\\Support\\{Str as S};\n"
                        "use function App\\Support\\helper;\n\nclass Ctl {\n  public function show($id) {\n"
                        "    $u = User::find($id);\n    $u->save();\n    helper($id);\n"
                        "    return \\App\\Models\\User::find(1);\n  }\n}\n",
}


def test_php_namespaces_use_function_and_fully_qualified():
    lk = _lk(PHP)
    u = _users(lk, "User.find")
    assert set(u) == {"src/Http/Ctl.php"} and u["src/Http/Ctl.php"]["user"] == "Ctl.show"
    assert set(_users(lk, "helper")) == {"src/Http/Ctl.php"}
    assert set(_users(lk, "Model")) == {"src/Models/User.php"}             # same namespace, no use
    assert _users(lk, "unused") == {}


RUBY = {
    "lib/billing/tax.rb": "module Billing\n  class Tax\n    def self.rate\n      0.2\n    end\n  end\nend\n",
    "lib/billing/invoice.rb": "require_relative \"tax\"\n\nmodule Billing\n  class Invoice\n    def total(n)\n"
                              "      n * (1 + Tax.rate) + fee\n    end\n\n    def fee\n      1\n    end\n  end\nend\n",
    "lib/billing/invoice_ext.rb": "module Billing\n  class Invoice\n    def unused\n      fee\n    end\n  end\nend\n",
    "lib/util.rb": "def fmt(x)\n  x.to_s\nend\n\ndef lonely\nend\n",
    "app/report.rb": "require \"util\"\n\nclass Report\n  def show(i)\n    fmt(Billing::Tax.rate)\n"
                     "    Billing::Invoice.new.total(1)\n  end\nend\n",
}


def test_ruby_constants_reopened_classes_and_require():
    lk = _lk(RUBY)
    assert set(_users(lk, "Billing.Tax.rate")) == {"lib/billing/invoice.rb", "app/report.rb"}
    assert set(_users(lk, "fmt")) == {"app/report.rb"}                    # through require "util" -> lib/util.rb
    assert lk.resolve_ref("lib/billing/invoice_ext.rb", "fee", "", "Billing.Invoice.unused") == \
        ("lib/billing/invoice.rb", "Billing.Invoice.fee", "self")
    assert _users(lk, "lonely") == {}


def test_configs_go_mod_and_cargo_are_resolution_configs():
    assert ci.indexable("go.mod") == "config" and ci.indexable("crates/x/Cargo.toml") == "config"
    assert ci.parse_config("go.mod", "// c\nmodule example.com/app // x\n") == ("go_mod", {"module": "example.com/app"})
    assert ci.parse_config("Cargo.toml", '[package]\nname = "a-b"\n[lib]\npath = "src/x.rs"\n') == \
        ("cargo", {"name": "a-b", "lib": "src/x.rs"})
