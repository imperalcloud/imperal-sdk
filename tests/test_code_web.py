"""Web code linked to the maximum (owner 2026-11-06): TS/TSX/JS in monorepos (workspace packages through ``exports``,
tsconfig ``extends``), default exports, CommonJS, dynamic ``import()``, ``.mts``/``.cts``, typed locals and
dependency-injected fields, JSX, and Vue / Svelte / Astro components."""
import json

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_typescript")

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


MONO = {
    "tsconfig.base.json": json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@ui/*": ["packages/ui/src/*"]}}}),
    "apps/web/tsconfig.json": json.dumps({"extends": "../../tsconfig.base.json", "compilerOptions": {"jsx": "x"}}),
    "packages/ui/package.json": json.dumps({"name": "@acme/ui", "main": "dist/index.js", "types": "dist/index.d.ts",
                                            "exports": {".": {"import": "./dist/index.mjs", "types": "./dist/index.d.ts"},
                                                        "./button": "./src/Button.tsx"}}),
    "packages/core/package.json": json.dumps({"name": "@acme/core", "main": "./dist/main.js"}),
    "packages/core/src/main.ts": "export function boot() { return 1 }\n",
    "packages/ui/src/index.ts": "export { Button } from './Button'\nexport * from './Card'\n",
    "packages/ui/src/Button.tsx": "export function Button(p: {label: string}) { return <button>{p.label}</button> }\n"
                                  "export default function Fancy() { return null }\n",
    "packages/ui/src/Card.tsx": "export const Card = ({children}: any) => <div>{children}</div>\n"
                                "export class Store { load() { return this.parse() } parse() { return 1 } }\n"
                                "export class Api { constructor(private readonly store: Store) {}\n"
                                "  get() { return this.store.load() } }\n",
    "apps/web/src/App.tsx": "import { Button, Card } from '@acme/ui'\nimport Fancy from '@acme/ui/button'\n"
                            "import { Store } from '@ui/Card'\nimport { boot } from '@acme/core'\n"
                            "export function App() { const s = new Store(); s.load(); boot()\n"
                            "  return <Card><Button label='x' /><Fancy/></Card> }\n",
    "apps/web/src/lazy.ts": "export async function lazy() { const m = await import('./util.mjs'); return m.fmt(1) }\n",
    "apps/web/src/util.mts": "export function fmt(x: number) { return String(x) }\n",
    "apps/web/src/cjs.js": "const { fmt } = require('./legacy')\nconst legacy = require('./legacy')\n"
                           "module.exports = { run: () => fmt(1), other: () => legacy.other() }\n",
    "apps/web/src/legacy.js": "function fmt(x) { return x }\nexports.fmt = fmt\n"
                              "module.exports.other = function other() {}\nexports.unused = () => 0\n",
    "apps/web/src/one.js": "module.exports = function single() { return 1 }\n",
    "apps/web/src/use-one.js": "const single = require('./one')\nfunction go() { return single() }\n",
}


def test_monorepo_packages_exports_and_tsconfig_extends():
    lk = _lk(MONO)
    assert set(_users(lk, "Button")) == {"apps/web/src/App.tsx"}       # @acme/ui -> exports "." -> src/index.ts
    assert set(_users(lk, "Fancy")) == {"apps/web/src/App.tsx"}        # @acme/ui/button + its default export
    assert set(_users(lk, "boot")) == {"apps/web/src/App.tsx"}         # main dist/main.js -> src/main.ts
    assert set(_users(lk, "Store")) >= {"apps/web/src/App.tsx"}        # @ui/* from the extended tsconfig


def test_typed_locals_and_injected_fields():
    lk = _lk(MONO)
    assert set(_users(lk, "Store.load")) == {"apps/web/src/App.tsx"}   # const s = new Store(); s.load()
    assert impact(lk, ["Store.load"])["same_file"][0]["user"] == "Api.get"   # this.store.load(), store: Store


def test_commonjs_dynamic_import_and_mts():
    lk = _lk(MONO)
    assert set(_users(lk, "apps/web/src/legacy.js::fmt")) == {"apps/web/src/cjs.js"}
    assert set(_users(lk, "apps/web/src/util.mts::fmt")) == {"apps/web/src/lazy.ts"}
    assert set(_users(lk, "other")) == {"apps/web/src/cjs.js"}
    assert set(_users(lk, "single")) == {"apps/web/src/use-one.js"}   # module.exports = function single
    assert _users(lk, "unused") == {}
    assert {d.qualname for d in lk.facts["apps/web/src/cjs.js"].defs} >= {"run", "other"}


SFC = {
    "tsconfig.json": json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}),
    "src/components/user-card.vue":
        '<template>\n  <div>\n    <BaseButton @click="go" />\n    <ui-icon name="x"/>\n    <router-link to="/" />\n'
        '  </div>\n</template>\n<script setup lang="ts">\nimport BaseButton from "./BaseButton.vue"\n'
        'import UiIcon from "@/ui/UiIcon.vue"\nimport { fmt } from "@/lib/fmt"\nfunction go() { return fmt(1) }\n'
        '</script>\n<style>.a{}</style>\n',
    "src/components/BaseButton.vue": "<template><button><slot/></button></template>\n<script>\n"
                                     "export default { name: 'BaseButton' }\n</script>\n",
    "src/ui/UiIcon.vue": "<template><i/></template>\n",
    "src/lib/fmt.ts": "export function fmt(x: number) { return String(x) }\nexport function unused() {}\n",
    "src/App.svelte": "<script lang=\"ts\">\n  import Card from './Card.svelte'\n  import { fmt } from './lib/fmt'\n"
                      "  let n = fmt(2)\n</script>\n\n<Card title={n} />\n<my-element/>\n",
    "src/Card.svelte": "<script>\n  export let title\n</script>\n<h1>{title}</h1>\n",
    "src/pages/index.astro": "---\nimport Layout from '../layouts/Layout.astro'\n"
                             "import UserCard from '../components/user-card.vue'\nconst t = 'x'\n---\n"
                             "<Layout title={t}>\n  <UserCard client:load />\n</Layout>\n",
    "src/layouts/Layout.astro": "---\nconst { title } = Astro.props\n---\n<html><body><slot/></body></html>\n",
    "src/main.ts": "import { createApp } from 'vue'\nimport UserCard from './components/user-card.vue'\n"
                   "createApp(UserCard)\n",
}


def test_vue_svelte_astro_components():
    lk = _lk(SFC)
    fx = lk.facts["src/components/user-card.vue"]
    assert fx.lang == "vue" and fx.defs[0].qualname == "UserCard"
    tags = {(r.head, r.line) for r in fx.refs if r.in_def == "UserCard"}
    assert ("BaseButton", 3) in tags and ("UiIcon", 4) in tags          # kebab tag of an imported component
    assert not any(r.head == "RouterLink" for r in fx.refs)             # not imported: a global, no link
    assert {r.line for r in fx.refs if r.head == "fmt"} == {12}          # script lines are the file's lines
    assert set(_users(lk, "UserCard")) == {"src/main.ts", "src/pages/index.astro"}
    bb = _users(lk, "BaseButton", depth=2)
    assert bb["src/components/user-card.vue"]["depth"] == 1 and bb["src/pages/index.astro"]["depth"] == 2
    assert set(_users(lk, "fmt")) == {"src/App.svelte", "src/components/user-card.vue"}
    assert set(_users(lk, "Card")) == {"src/App.svelte"} and set(_users(lk, "Layout")) == {"src/pages/index.astro"}
    assert _users(lk, "unused") == {}


def test_web_extensions_are_indexed():
    for p in ("a.mts", "a.cts", "a.vue", "a.svelte", "a.astro", "a.go", "a.rs", "A.java", "a.kt", "a.cs", "a.php",
              "a.rb"):
        assert ci.indexable("src/" + p) == "code", p


def test_ts_factory_return_types():
    lk = _lk({
        "src/store.ts": "export class Store { load() { return 1 } }\nexport function createStore(): Store "
                        "{ return new Store() }\n",
        "src/app.ts": "import { createStore } from './store'\nexport function app() { const s = createStore(); "
                      "return s.load() }\n",
    })
    got = _users(lk, "Store.load")
    assert set(got) == {"src/app.ts"} and got["src/app.ts"]["origin"] == "returns"
