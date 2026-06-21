# L1 declarative app fixtures + smoke-run contract

Committed, validator-clean `impl=declarative` apps used as (a) conformance fixtures and
(b) few-shot exemplars for the L1 compose loop.

- `link_saver.ir.json` — CRUD: `save_link` (store.create), `list_links` (store.list),
  `delete_link` (store.delete).
- `archive_ended.ir.json` — conditional flow: store.list → conditional(count>0) →
  store.update → send (exercises the binding-DSL + conditional).

Together they cover the full non-Turing vocabulary.

## Smoke-run contract

A composed app **passes smoke-run** iff, for the probed function, `HostedEngine.run_function`
returns without error AND — for a `write` function — a follow-up `read` in the **same isolated
store** reflects the write (e.g. after `save_link`, `list_links` count increases). Smoke-run
writes go to an isolated store namespace (a fresh per-run `MockContext` tenant), **never real
data**.

## Compose loop (intent → IR → validate → repair → deploy → smoke)

The composer is handed the enriched catalog (`sdk-reference.json`), the IR JSON Schema, these
exemplars, and the validator as a tool. It emits IR, validates, repairs on `ValidationIssue`s
(bounded cycles), deploys via the registration API, and smoke-runs — **declarative-only** (the
generated artifact is non-Turing, validated, executes no arbitrary code).
