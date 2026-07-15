# Changelog

All notable changes to `imperal-sdk` are documented here.

## 5.9.5 — Fix: generator↔validator manifest parity closed both ways

Patch — bug fixes + CI hardening; no intended API surface change. Kills the `I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC` drift class that shipped in 5.9.4.

### Fixed
- **`Panel` schema accepts generator-emitted panel metadata.** 5.9.4's generator started re-emitting the full `@ext.panel` decorator metadata (`icon`/`refresh`/`center_overlay` + `default_width`/`min_width`/`max_width` + ad hoc kwargs), but the `Panel` model still had `extra="forbid"` without those fields — `imperal build && imperal validate` failed with 12 M3 errors on any extension with sized sidebar panels. The model now declares them and uses `extra="allow"` (panel metadata is intentionally open-ended); static `imperal.schema.json` regenerated.
- **`secrets[].scope` / `env_fallback` validate.** `SecretSpec.to_manifest_dict()` has emitted `scope` unconditionally (and `env_fallback` for app scope) since 5.8.0, but `SecretDecl` never gained the fields — every secret-declaring extension failed local `imperal validate` (and `imperal deploy`) with M3. `SecretDecl` now mirrors the spec's own rules: `scope: "user"|"app"`, `env_fallback` only for app scope and only in the `IMPERAL_APPSECRET_` namespace. Static schema regenerated.
- **`imperal build` no longer drops schema-known hand-maintained manifest fields.** The disk merge preserved a hand-copied 10-field marketplace tuple; anything else (e.g. `hidden_in_sidebar`) was silently deleted on every rebuild. The preserved set is now derived from the `Manifest` model minus the generator-owned fields (`GENERATOR_OWNED_FIELDS` / `disk_preserved_fields()` in `imperal_sdk.manifest`), so a field added to the schema can never be silently lost again.

### CI
- **Roundtrip parity gate is now maximal and bidirectional.** The `I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC` canary exercises every manifest emission site the SDK offers (secrets in both scopes, oauth, emits, tray, full lifecycle, panels with sizing/overlay/custom kwargs/static tree, migrations/config/system, chat functions) and asserts a structural closure: every schema field is either emitted by the canary or preserved by the disk merge, and every emission is schema-known. It also validates the merged on-disk manifest through the exact path `imperal validate` uses, plus the live-extension V-rules.
- **Publishing a red suite is now impossible.** `publish.yml` runs the full pytest suite (py3.11 + 3.12) as a `test` job the PyPI publish job `needs` — 5.9.4 was published from a tag with the parity gate failing because the publish workflow never ran tests. OIDC publish mechanics unchanged.

## 5.9.4 — 2026-07-14 — Feature: `NotifyClient` extension_id attribution

Patch — additive, backwards-compatible. First piece of Notification Preferences v1 (per-app notification routing).

### Added
- **`ctx.notify` now attributes outgoing notifications to the calling extension.** `NotifyClient` gains an optional `extension_id: str = ""` constructor kwarg; when set, `POST /v1/internal/notify` includes `extension_id` in the wire payload so the gateway's per-app notification matrix can gate delivery. An explicit `extension_id=` kwarg passed to `ctx.notify(...)` still wins over the constructor value. `ctx.as_user(...)` threads the acting extension's `extension_id` through to the rebuilt `NotifyClient`, matching the existing `store`/`skeleton` rebuild pattern. Omitted when empty — no wire-shape change for callers that don't set it.

### Notes
- Kernel-side attribution (`imperal_kernel.core.context_factory` passing `extension_id=extension_id` into `NotifyClient(...)`) and the federal invariant `I-NOTIFY-APP-ATTRIBUTED` land separately.

## 5.9.3 — 2026-07-05 — Fix: `ctx.cache.set()` size guard measures the exact wire body

Patch — bug fix; no API surface change. Fixes intermittent `413 Request Entity Too Large` on large cache writes.

### Fixed
- **`CacheClient.set()` no longer under-measures the PUT body.** The 64 KB guard measured a *compact* re-serialization of only the inner envelope, while the actual request body (httpx `json=`) was serialized with *default* (spaced) separators plus the `{envelope, ttl_seconds}` wrapper — a strictly larger payload. Separator-heavy values (many small fields) could pass the guard by several KB and still be rejected by the gateway with `413`, and because `get_or_fetch` writes fail after the fetch, callers silently lost caching on every TTL expiry. `set()` now serializes the final request body exactly once with compact separators (`(",", ":")`) and uses those same bytes for **both** the size check **and** the wire body (`content=` with explicit `Content-Type: application/json`). The guard is now truthful, and the wire body is ~7-8% smaller for separator-heavy payloads. The 64 KB cap (`I-CACHE-VALUE-SIZE-CAP-64KB`) is unchanged.

### Notes
- Pairs with the Auth Gateway extcache fix that measures and stores the envelope with the same compact separators. Values that fit compact now fit end-to-end.

## 5.9.2 — 2026-06-30 — Fix: `@ext.secret(scope=, env_fallback=)` now reach the manifest

Patch — completes the 5.8.0 app-level secrets feature on the decorator.

### Fixed
- **`ext.secret(scope="app")` no longer raises `TypeError`.** 5.8.0 added `scope` / `env_fallback` to `SecretSpec` + the manifest schema, but the `ext.secret(...)` decorator never accepted or forwarded them — so declaring an app-scope secret from code (the documented way) failed. The decorator now accepts `scope="user"|"app"` (default `"user"`) and `env_fallback=...` and forwards both to `SecretSpec`, so `@ext.secret(scope="app")` declarations emit `scope`/`env_fallback` into `secrets[]` as documented.

## 5.9.1 — 2026-06-30 — Security: OAuth `state` requires a configured signing secret

Patch — hardens the 5.9.0 OAuth-connect `state` signing.

### Security
- **No hardcoded fallback signing key.** `oauth_state` previously fell back to a constant string when no env secret was set. Since this package is published, that constant is world-readable — an attacker could forge a `state` (provider, user_id) and drive an OAuth CSRF / account-takeover. The signer now **requires `IMPERAL_OAUTH_STATE_SECRET`** (set to the same value on the kernel and the gateway) and raises loudly if it is unset — no insecure fallback. Set it before using the unified OAuth-connect flow. (Stronger defense-in-depth — a per-request nonce bound to the user session — is a planned follow-up.)

## 5.9.0 — 2026-06-30 — Feature: unified OAuth-connect (`ext.oauth` + `ctx.oauth_authorize_url`)

Minor — additive. Lets an extension hand OAuth account-connect to the platform instead of hand-rolling the dance.

### Added
- **`ext.oauth(provider, *, collection=None, scopes=None)`** — declare an OAuth provider the platform connects on your behalf. The unified gateway route `/v1/ext/{app_id}/oauth/{provider}/callback` runs the whole dance (code exchange → profile → save) and writes a standard account record to `collection` (default `f"{provider}_accounts"`). Client creds come from your **app-scope secrets** `{provider}_client_id` / `{provider}_client_secret` — never from env. Emitted to the manifest `oauth[]` section (schema rule, `manifest_schema_version` unchanged — additive optional field). Built-in providers: `google` (Gmail getProfile), `microsoft` (Graph `/me`), `yahoo`.
- **`await ctx.oauth_authorize_url(provider, *, login_hint=None)`** — build the provider authorize URL the user's browser opens. Reads the public `client_id` from the app-scope secret and the scopes from your `ext.oauth(...)` declaration; the redirect URI targets the unified callback; `state` is signed (HMAC) so the gateway can verify it. Your `connect()` returns this URL — no hardcoded scopes/redirect.

### Notes
- The optional per-extension `on_oauth_success` persistence hook is reserved (manifest `oauth[].has_hook`) and ships with its gateway-side dispatch in a later release; the default platform writer covers the common case with zero extension OAuth code.
- Shared signing key: set `IMPERAL_OAUTH_STATE_SECRET` to the same value on the kernel and the gateway so SDK-signed `state` verifies.

## 5.8.2 — 2026-06-30 — Fix: `@ext.webhook` path is slash-normalized (OAuth callback dispatch)

Patch — bug fix; no API change. Affects any extension whose webhook path was declared with a leading slash.

### Fixed
- **`@ext.webhook("/callback")` now dispatches correctly.** A leading slash in the declared path leaked into the dispatch tool name (`__webhook__/callback`), but the platform routes incoming webhooks by the URL path it receives — always slash-free — so it looked up `__webhook__callback` and failed with *"System function not found"*. This broke OAuth callbacks (the user's "connect account" step). The decorator now normalizes the path: the **dispatch tool name is slash-free** (`__webhook__callback`) regardless of how you declare it (`"callback"`, `"/callback"`, `"/callback/"` all work), while the **manifest `webhooks[].path` keeps its single leading slash** (`/callback`) as the manifest schema requires. Internal separators are preserved (`"/oauth/callback"` → tool `__webhook__oauth/callback`, manifest `/oauth/callback`).

## 5.8.1 — 2026-06-30 — Fix: `ctx.as_user(uid).secrets` works in system-context fan-out

Patch — bug fix; no API surface change. Required if an extension reads secrets from a `@ext.schedule` cron or any `ctx.as_user(...)` fan-out.

### Fixed
- **`ctx.as_user(uid).secrets` no longer raises `AttributeError`.** `ctx.secrets` is attached to the Context after construction, so the scoped Context returned by `ctx.as_user(uid)` did not carry it — `await ctx.as_user(uid).secrets.get(...)` raised `'Context' object has no attribute 'secrets'`. `as_user()` now carries the secrets client across, **rebound to the target user** (mirroring `store` / `skeleton` / `notify`). A new `SecretClient.for_user(user_id)` returns a copy bound to a different acting-user; app-scope secrets still resolve to the shared store regardless of acting-user, so reads are correct for both `scope="user"` and `scope="app"`. A Context with no `secrets` attached still scopes cleanly (back-compatible).

Minor — additive `@ext.secret` kwargs; fully back-compatible (absent `scope` ⇒ `"user"`, the existing behaviour).

### Added
- **`@ext.secret(scope="user" | "app")`** — a secret can now be **developer-owned and shared by every user** (`scope="app"`) instead of per-user (`scope="user"`, the default). An app-scope secret is stored ONCE for the extension (keyed by `ext_id`, not by user), set by the app owner in the Developer Portal, and read transparently by your handlers for **every** user via the same `await ctx.secrets.get(name)` — no code change. This is for credentials *you* own: OAuth client_id/client_secret, a shared API key you pay for. Per-user credentials (the user's own key, their OAuth refresh token after they authorize) stay `scope="user"`. See the [Secrets concept — two scopes](/en/concepts/secrets/) guide and the [`@ext.secret` reference](/en/sdk/decorator-secret-reference/).
- **`@ext.secret(env_fallback="IMPERAL_APPSECRET_<EXT>_<NAME>")`** — optional, `scope="app"` only: a temporary migration bridge that lets an app-scope read fall back to an env var until the value is saved in the Dev Portal. **Security:** the name MUST be in the `IMPERAL_APPSECRET_` namespace — `SecretSpec` rejects anything else at build time so an extension can never point a fallback at an arbitrary platform secret.

### Federal contract (gateway-enforced)
`scope="app"` is keyed under a shared sentinel; app-scope **writes/deletes require the app owner** (Developer Portal) or an admin — extension code and end-users get `403`; app-scope **plaintext reads are kernel-only** — an end-user can neither read nor list an app-scope secret, and the value never reaches the LLM. New invariants `I-SECRET-SCOPE-APP-SHARED`, `I-SECRET-APP-WRITE-OWNER-ONLY`, `I-SECRET-APP-READ-NOT-USER`, `I-SECRET-APP-NO-LLM-EGRESS`.

## 5.7.3 — 2026-06-21 — Fix: validate_step is now binding-DSL-aware

Patch — declarative validation; no API change.

### Fixed
- **`validate_step` accepts a whole-match binding-DSL value (`{{ path }}`) in any typed field.** A binding resolves at runtime to the raw referenced object (any type), so its static type is unknowable. E.g. `store.update`'s `ids: "{{steps.s1.ids}}"` (resolves to a list) previously failed with `ids: expected array, got str`, blocking every declarative flow that binds a prior step's list into an array field. Whole-match `{{...}}` now skips the static type-check; interpolated strings (`"...{{x}}..."`) still type-check as `str` (they always resolve to a string). The interpreter already handled bindings at runtime — this aligns the validator (`ir/actions.py`).

## 5.7.2 — 2026-06-21 — Fix: store.create schema required `set`, interpreter reads `data`

Patch — declarative action-schema ↔ interpreter alignment; no API change.

### Fixed
- **`store.create` step schema now requires `data`** (`schemas/actions/store_create.json`), matching what the interpreter's `run_store` reads (`args["data"]`) and the create-with-`data` / update-with-`set` convention. The schema previously required `set`, so a declarative `store.create` step could pass `validate_step` XOR run — never both. A full audit of the 11-verb action vocabulary confirms this was the only hard schema↔interpreter mismatch. Added `test_store_create_schema_agrees_with_interpreter` to pin them together.

## 5.7.1 — 2026-06-20 — Fix: declarative `store.list` returned count=0

Patch — bug fix in the declarative interpreter; no API change.

### Fixed
- **`run_store` `list` now reads `Page.data`** (`runtime/verbs.py`). It previously read a non-existent `Page.items`, so `store.list` silently returned `count=0`/empty against the real `Page`/`MockStore` — breaking every declarative app that lists (the L1 prerequisite). Unit-test fakes had masked it by exposing `.items`; the fakes are corrected to the real `Page` contract and a real-`MockStore` regression test added (`tests/runtime/test_verb_store.py`).

## 5.7.0 — 2026-06-20 — Metering rails (L0-4 core)

Minor — additive metering contract + identity hardening. The one behavior tightening: an empty `imperal_id`/`tenant_id` on `UserContext` is now rejected (was always invalid).

### Added
- **`MeteredEvent`** — the sealed, dimension-only usage-metering DTO (frozen Pydantic; two version axes `v` + `meter.meter_version`; nested `identity`/`meter`/`attribution` + open `dimensions`). Carries WHAT was consumed, never the price — price resolution stays platform-closed-side. Exported lazily (`from imperal_sdk import MeteredEvent`), cataloged in `sdk-reference.json`, with a vendored, freshness-gated JSON schema (`schemas/metered_event.schema.json`). A `model_validator` forbids the price keys (`base_price`/`platform_fee`/`cost`/`model_tier`/`price`) anywhere in `dimensions` — the canonical dimension-only seal. (The published JSON schema leaves `dimensions` open; validate via the Pydantic model to inherit the seal.)
- Cross-repo metered-XADD envelope contract test (`tests/contract/test_meter_lua_contract.py`) pinning the `event_id` → `type` → `data` field order shared by the billing-stream Lua copies.

### Changed
- **`UserContext.imperal_id` and `tenant_id` now require `min_length=1`** — an empty identity raises `ValidationError` at construction. `agency_id` stays nullable (B2B known-gap). Mirrors the `RpcRequest` precedent.

## 5.6.1 — 2026-06-20 — Engine-seal completion (L0-3)

Patch — **nothing to migrate** (internal/cosmetic; no public API changed or removed).

### Changed
- **Guarded-import shim** (`runtime/_platform`, internal): the SDK's optional
  platform-runtime imports are now owned by a single substrate-neutral module.
  Runtime fallback warnings/tracebacks (when the platform runtime is absent, e.g.
  standalone unit tests) no longer name internal engine modules — they read
  "platform runtime unavailable" / "platform event store unavailable". `emit()`
  and the target-scope check route through it; behavior is unchanged.
- Scrubbed the remaining engine-module references from public docstrings
  (`chat/error_codes`, `chat/narration`, `runtime/llm_provider`).

### Added (tests only)
- Permanent boundary-seal guards: `tests/rpc/test_boundary_seal.py` (RpcReply/RpcError
  can never carry an engine token — structural + behavioral) and a public-docstring
  engine-neutrality gate. (A companion kernel-side federal SSE-event guard ships in
  the kernel repo.)

## 5.6.0 — 2026-06-20 — IR envelope + minimal declarative executor (L0-2)

Minor — **nothing to migrate** (purely additive; no existing API changed or removed).

### Added
- **IR envelope** (`imperal_sdk.ir`) — a versioned, schema'd definition of what an
  app *is*: `IREnvelope`/`IRApp` (+ committed `schemas/ir.schema.json`), the explicit
  `impl` discriminator (`code` | `declarative`), `validate_ir_dict()`, `generate_ir(ext)`
  (maps an Extension's manifest onto the IR with zero rewrite), and a versioned
  `migrate_ir()` registry. `ir_version`/`contract_version`/`sdl_vocab_version` are
  stamped from canonical sources.
- **Engine SPI + minimal declarative executor** (`imperal_sdk.runtime`) — the abstract
  `KernelEngine`, `LocalDevEngine` (in-process, no engine), and `HostedClient`
  (injected transport), all provably interchangeable via the engine-parity test. A
  small, **non-Turing** step interpreter executes the declarative vocabulary
  (`call`/`navigate`/`send`/`open` · `store.{get,list,create,update,delete}` ·
  `ai.complete` · static `conditional`) over the `{{event/steps/prev}}` binding-DSL,
  with a step-budget guard. Real logic stays `impl=code`.
- **Bounded SDL projection** — by-name facet resolution (`resolve_facets`), inline
  `custom_roles` (reserved-namespace-validated), and a non-Turing `canon` projection
  (`id_from` fallback chains · `kind_const` · `title_template` with a closed
  `count`/`default`/`format` filter whitelist).
- **3-tier UI + first-class skeleton** in the IR — `static` tree | data-bound
  `template` (server-resolved bindings + `$repeat`/`$if`) | `impl=code` render;
  typed binding-point schemas for the renderer-interpreted `list[dict]` children
  (Tabs/Accordion/DataTable/Select/Timeline/Tree/Menu); a first-class `skeleton` slot.
- **Enriched symbol catalog** — `sdk-reference.json` now carries per-symbol
  `description`, a structured `type` graph per param, and `declarative_capable` /
  `action_vocab_safe` flags; per-verb action JSON Schemas under `schemas/actions/`.
  A new gate asserts the catalog generator emits no engine-implementation names.

## 5.5.1 — 2026-06-19 — Sync chat_result schema artifact (completes Seal-B)

Patch — **nothing to migrate** (no API or behavior change).

### Fixed
- Regenerated the committed `schemas/chat_result.schema.json` so its embedded
  description matches the runtime model after the 5.5.0 engine-neutral-docs pass
  (the static artifact still carried the old engine wording, and the full test
  suite caught it on 3.11/3.12). Completes Seal-B — no engine-implementation
  names remain anywhere in the shipped package; SDK suite green (1240 passed).

## 5.5.0 — 2026-06-19 — Apache-2.0 relicense + engine-neutral docs

Licensing + documentation — **nothing to migrate** (no API or behavior change).

### Changed
- **Relicensed from AGPL-3.0 to Apache-2.0.** The SDK — the language you build
  Imperal apps in — is now under the permissive Apache License 2.0, removing
  copyleft friction for commercial adopters. `LICENSE` and `pyproject.toml`
  updated; no runtime or public-API change.
- **Engine-neutral public docs.** Public docstrings/comments no longer name
  internal implementation details (the orchestration engine, the state/event
  store) or carry internal invariant IDs — they describe behavior in
  substrate-neutral terms ("the platform", "platform execution", "the platform
  state/event store"). Pure docstring/comment edits; the SDK↔kernel contract is
  unchanged (contract suite green).

## 5.4.3 — 2026-06-18 — Fix secrets-panel render crash

Bugfix — **nothing to migrate**.

### Fixed
- Auto-generated `__panel__secrets` panel (created for any extension declaring
  `@ext.secret`) called `ui.Heading(...)`, which does not exist — the display
  element is exported as `ui.Header`. Every secrets-panel render raised
  `AttributeError: module 'imperal_sdk.ui' has no attribute 'Heading'`. Switched
  to `ui.Header`. No public API change.

## 5.4.2 — 2026-06-16 — BillingClient renew_subscription

Additive — **nothing to migrate**.

### Added
- `ctx.billing.renew_subscription()` — renews an **expired** subscription for
  the same plan: charges the saved default card for one fresh period and
  restores access immediately (POST `/v1/billing/renew`). Surfaces errors
  (`402` no card / SCA required, `409` not expired). Returns the gateway result
  dict (`{status, plan, expires_at, payment_intent_id}`).

`BillingProtocol` 18 → 19 methods.

## 5.4.1 — 2026-06-16 — BillingClient resume + cancel_at_period_end

Additive — **nothing to migrate**.

### Added
- `ctx.billing.resume_subscription()` — undoes a pending cancel-at-period-end
  (POST `/v1/billing/resume`); returns the gateway result dict
  (`{status, plan, expires_at, cancel_at_period_end}`). Surfaces errors.
- `SubscriptionInfo.cancel_at_period_end: bool` (defaults `False`) —
  `get_subscription()` now maps it from the gateway response so extensions can
  show whether an active subscription is set to cancel at period end.

`BillingProtocol` 17 → 18 methods.

## 5.4.0 — 2026-06-16 — BillingClient portal + full Webbee parity

Additive — **nothing to migrate**.

### Added
- `ctx.billing.create_billing_portal_session()` — mints a Stripe Customer
  Portal session and returns its hosted URL (for `ui.Open`), so extensions can
  let users manage cards + view invoices on Stripe's hosted page (PAN never
  touches our backend). Surfaces errors.
- Five `ctx.billing` parity methods so Webbee can fully drive billing via chat:
  `list_plans()` (public plan catalog → `list[PlanInfo]`, safe-degrades to `[]`),
  `get_auto_topup()` (→ `AutoTopupSettings`, safe-degrades to disabled defaults),
  `set_auto_topup(enabled, threshold_pct=10, recharge_tokens=20000, payment_method_id="")`
  (surfaces errors), `cancel_subscription()` (cancel-at-period-end → result dict,
  surfaces errors), `update_billing_profile(profile)` (writes name/company/vat/country,
  surfaces errors).
- New dataclasses `PlanInfo` and `AutoTopupSettings` in `imperal_sdk.types.models`.

## 5.3.0 — 2026-06-16 — BillingClient write/payment methods

Additive — **nothing to migrate**.

### Added
- `ctx.billing` write/payment methods: `list_payment_methods`, `list_payments`,
  `create_setup_intent`, `set_default_payment_method`, `remove_payment_method`,
  `change_plan`, `topup`. Reads degrade safely; writes surface errors so the
  caller can render Stripe failures / drive the Payment Element.
- `BillingClient` now sends `X-Acting-User` on the service-token path so
  `get_user_or_service` gateway endpoints resolve the acting user.

## 5.2.2 — 2026-06-11 — Import-light package root

Performance / robustness release. **Zero API changes** — every public name,
submodule attribute, star-import and `dir()` entry resolves exactly as before
(verified by an eager-parity test over the whole surface).

### Changed

- **The package root is now import-light (PEP 562 lazy surface).**
  `import imperal_sdk` — and importing transport-free helpers such as
  `imperal_sdk.chat.filters` or `imperal_sdk.chat.error_codes` — no longer
  loads the HTTP client stack. Heavy dependencies load on first use of the
  names that actually need them (`Context`, the service clients,
  `get_llm_provider`, …). Benefits: faster cold imports, and helper modules
  are now safe to import from restricted/sandboxed execution contexts that
  forbid network-stack loading.

Nothing to migrate — rebuild against `imperal-sdk>=5.2.2` at your convenience.

## 5.2.1 — 2026-06-01 — ChatExtension ergonomics & honest deprecations

Small, fully backward-compatible cleanup of `ChatExtension`. No API removals;
existing extensions are unaffected.

### Changed

- `ChatExtension(tool_name=...)` no longer emits a `DeprecationWarning`. The
  kwarg is the **canonical** chat-registration key — it groups your
  `@chat.function` tools in the manifest, anchors the per-turn prompt, and
  labels scope-guard audit lines. It is load-bearing and not going away; the
  prior "removed in 5.1.0" warning was incorrect and has been removed.

### Added

- `ChatExtension(...)` now accepts an **optional** `tool_name`. When omitted it
  defaults to `f"tool_{ext.app_id}_chat"`. Pass it explicitly to pin a stable
  routing name (recommended for production extensions). `description=` is now
  optional as well.

## 5.2.0 — 2026-05-31 — Structured Data Layer (SDL) foundation

Introduces the **SDL (`imperal_sdk.sdl`)** — a typed, semantic vocabulary for the
data an extension returns, so the platform can read an entity's id / title / kind
and its facets directly instead of inferring them from field names. This release
ships the SDK foundation (canonical types + the standard facet library + a schema
marker for platform detection). **The platform reads SDL in production today.** Fully **additive** — the existing API and existing
extensions are unchanged; adopting SDL is opt-in via `data_model=`.

### Added

- **SDL — Structured Data Layer (Phase 1: Core).** New `imperal_sdk.sdl` module
  for returning *typed* entities whose field meanings the platform reads directly
  instead of inferring from field names:
  - `sdl.Entity` — canonical base with `id` / `title` / `kind` (+ optional
    `subtitle` / `description` / `status` / `url`). `kind` defaults to the
    subclass name.
  - `sdl.Ref` — lightweight reference (id / kind / title / app_id) for relations
    and list items.
  - `sdl.EntityList[T]` — typed list with `items` / `total` / `page` / `has_more`.
  - `sdl.field(role="...")` — declare a custom semantic role on a field; roles
    follow a dotted grammar and reserved namespaces are protected.
  - `sdl.roles_of(model)` — introspect a model's field→role map.

  Use it via `data_model=` on `@chat.function` (e.g.
  `class Note(sdl.Entity): ...` → `data_model=Note`). **The platform reads SDL
  entities in production today.**
- **SDL — Standard Facet Library (Phase 2).** 123 composable facet mixins across
  17 families (Identity, Time, People, Content, Communication, Media, Quantities,
  Money, Catalog, Tasks, Location, Tech/Network, Analytics, Events, Ratings,
  Security, Devices/Health). Compose the facets an entity needs and every field
  carries a standard semantic role:

  ```python
  class Task(sdl.Entity, sdl.Schedulable, sdl.Prioritized, sdl.Progress):
      estimate_s: int | None = None
  ```

  564 standard roles are catalogued in `sdl_roles.json`. Every facet field is
  optional; for anything not covered, use `sdl.field(role="yourapp.x")` with a
  non-reserved namespace. Full guide: `docs/sdl-facets.md`. **Live in production** —
  extensions adopt the types and the platform reads them today.
- **SDL — schema marker on `Entity` / `EntityList`.** Both stamp
  `x-sdl: "entity"` / `"entity-list"` into their JSON schema so the platform can
  detect an SDL-typed result from a function's return schema alone. Inherited by
  subclasses — no extension action needed beyond subclassing `sdl.Entity`.

## 5.1.0 — 2026-05-30 — Accuracy & correctness pass

This release makes the SDK faithful to current platform behavior: a billing
fix, removal of unused surface, a corrected limit, and documentation that now
matches what the platform actually does. Everything removed was unused (never
wired by the platform); the single signature change is on a method that
previously could not record usage correctly.

### Fixed

- **`ctx.billing.track_usage(...)` now records the requested amount.** Previously
  every call was recorded as a single unit regardless of the amount passed, and
  one code path could not reach the platform at all. The method now sends the
  correct request. **Signature changed** to
  `track_usage(meter: str, quantity: int = 1, user=None) -> bool`
  (previously `track_usage(tokens, resource)`).
- **Inter-extension call-depth limit** now matches the platform's actual nesting
  allowance, so a legitimate chain of nested `ctx.extensions.call(...)` hops is no
  longer rejected one level too early.
- **Manifest pre-flight validation** now reports an `sdk_version` below `5.0.0`
  as an error. The platform rejects such extensions at load, so this is now
  caught before deploy instead of after.

### Removed (unused — never wired by the platform)

- `ctx.db` and `ctx.tools` — use `ctx.extensions` for inter-extension calls.
- The `event_schema=` parameter on `@chat.function`.
- `ctx.config.require()` — use `ctx.config.get(...)`.
- Internal LLM-router methods left over from the 5.0.0 refactor.

### Documentation & test doubles

- `effects`, `background`, and `long_running` are now documented as advisory,
  declared-intent metadata. Declare them for convention; the long-running
  runtime path remains `ctx.background_task(long_running=...)`.
- Corrected the documented behavior of `data_model`, `chain_callable`, and
  `validate_manifest_dict` (which raises on duplicate webhook paths,
  cross-namespace event types, and duplicate exposed names).
- `MockSkeleton` is read-only, matching the real skeleton client; tests prime
  sections via the test-only `_seed(...)` helper.

## 5.0.3 — 2026-05-27 — Manifest `hidden_in_sidebar` field (system-only)

System apps may opt out of the Imperal Panel sidebar tile by declaring
`hidden_in_sidebar: true` in their `imperal.json`. Chat tools, lifecycle
hooks, skeleton refreshes, and audit ledger continue to function — only
the visual sidebar icon is suppressed.

### Federal contract — `I-EXT-MANIFEST-HIDDEN-SIDEBAR-SYSTEM-ONLY`

`hidden_in_sidebar=true` is only honoured when `system=true` is also set.
Third-party extensions MUST NOT hide themselves from the user-facing
sidebar. A new root model validator on `Manifest` rejects any manifest
that pairs `hidden_in_sidebar=true` with `system=false`/`None`:

```text
hidden_in_sidebar=True requires system=True (federal
I-EXT-MANIFEST-HIDDEN-SIDEBAR-SYSTEM-ONLY — third-party extensions
cannot hide themselves from the sidebar)
```

### Runtime flow (kernel + auth-gw, shipped 2026-05-27)

1. SDK validates the manifest at `imperal build` / publish time.
2. Kernel scans `/opt/extensions/*/imperal.json` on worker boot and on
   Registry catalog invalidation, publishes the set of opted-out
   `app_id`s to Redis SET `imperal:hidden_in_sidebar_apps`.
3. `imperal-auth-gateway` `GET /v1/users/{user_id}/extensions` reads the
   set via a second Redis client (`kernel_shared_redis_url`) and drops
   matching tiles from the response so the Imperal Panel sidebar never
   renders the icon.

### Touched files

- `src/imperal_sdk/manifest_schema.py` — adds
  `Manifest.hidden_in_sidebar: Optional[bool] = None` next to `system`
  and a `model_validator(mode="after")` that enforces the system-only
  rule. `validate_manifest_dict` surfaces violations as `M4`
  ValidationIssues.
- `src/imperal_sdk/schemas/imperal.schema.json` — regenerated to include
  the new field (static-vs-runtime gate in
  `tests/test_manifest_schema.py` and `tests/test_spec_validation.py`).

No other public API changes. No schema-version bump (still v3).

## 5.0.2 — 2026-05-26 — Federal source-cite hygiene

**Docs-only release. No behavior change. No new APIs.** Adds two federal-contract
citation comments in source so the kernel's federal source-cite test gates
(`I-SDK-DECORATOR-DATA-MODEL-KWARG` + `I-SDK-RETURN-DATA-VALIDATED-AT-EMIT`)
stay green across SDK reinstalls.

### Touched files

- `src/imperal_sdk/chat/extension.py` — `data_model` kwarg docstring now cites
  `I-SDK-DECORATOR-DATA-MODEL-KWARG`.
- `src/imperal_sdk/types/action_result.py` — `validate_against` docstring now
  cites `I-SDK-RETURN-DATA-VALIDATED-AT-EMIT`.

### Why

The kernel federal suite asserts the literal invariant IDs appear in SDK
source. 5.0.1 shipped without the comments; the kernel's 2 source-cite
tests stayed pinned green by an in-place edit of the venv `site-packages`
copy which would not survive a future `pip install -U`. 5.0.2 closes that
durability gap.

No federal contracts changed, no public API changes, no schema drift.

## 5.0.1 — 2026-05-17 — Federal Typed Return Contract

**Additive (no breaking changes).** Adds typed return contract for
`@chat.function` handlers so the platform can validate `$REF` paths in
multi-step chains against a declared schema and prevent input/output
field-name drift. Extensions built against 5.0.0 continue to work
unmodified — V23 ships as **WARN** in 5.0.1 and may promote to **ERROR**
in a future minor after third-party adoption (env-toggle:
`IMPERAL_VALIDATOR_V23_SEVERITY=error`).

### What's new

- **`@chat.function(data_model=...)` kwarg.** Declare the Pydantic
  `BaseModel` subclass that describes `ActionResult.data` for this tool.
  When declared, the SDK populates `FunctionDef._return_model` directly,
  emits a `return_schema` field into the manifest, and the platform uses
  the schema to:
  1. Validate `$REF:<app_id>[<n>].path` references in chain steps against
     real field names (closes the "next step references field that doesn't
     exist" class).
  2. Render `return_fields` in the classifier envelope so the LLM knows
     what shape it can read.
  3. Run `data.model_validate(...)` at emit time (warn-only in 5.0.1).
- **`ActionResult[T]` generic auto-detection.** `-> ActionResult[NoteRecord]`
  return annotations now populate `_return_model=NoteRecord` automatically.
  Resolution priority for `_return_model`:
  1. Explicit `data_model=` kwarg — wins.
  2. Direct `-> SomeBaseModel` return annotation.
  3. `-> ActionResult[T]` generic extraction.
  4. None of the above → `_return_model = None`.
- **`ActionResult.validate_against(model_class)` method.** Validates
  `self.data` against a Pydantic model class, logs a structured warning
  on mismatch, never raises. Useful for early type assurance in handler
  code.
- **Validator V23 (read tools, WARN by default).** Every
  `@chat.function(action_type="read", ...)` SHOULD declare `data_model=`
  (or use `-> ActionResult[T]` / `-> SomeBaseModel`). Toggle via
  `IMPERAL_VALIDATOR_V23_SEVERITY=warn|error`.
- **Validator V24 (write/destructive tools, WARN).** Same rule as V23
  but advisory — declaring `data_model` on writes lets the chain narrator
  and audit ledger describe the resulting entity shape without
  re-deriving from text.
- **`V31` first-party allowlist is now env-driven.** The SDK no longer
  ships with an embedded allowlist. Set `IMPERAL_FIRSTPARTY_AUTHOR_IDS`
  (comma-separated) at validation time to enable the local check; the
  Dev Portal continues to enforce server-side at publish.
- **Synthetic `Secrets` panel is lazy-registered.** Previously every
  `Extension` got a synthetic `__panel__secrets` entry on the right slot
  of the chat UI — even when the extension declared zero secrets, the
  user saw an empty placeholder titled "Secrets" with developer-guidance
  text. As of 5.0.1 the panel is registered ONLY when the extension
  calls `@ext.secret(...)` for the first time. Extensions with secrets
  see the same UI as before; extensions without secrets no longer ship
  an empty placeholder panel. No code change required for ext authors;
  no platform-side contract change (the federal secrets contract is
  enforced manifest-side and is independent of UI presence).

### Migration for extension authors

**Reads (V23).** Add `data_model=...` to every `@chat.function(action_type="read", ...)`:

```python
from pydantic import BaseModel
from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension
from imperal_sdk.chat.action_result import ActionResult

class NoteRecord(BaseModel):
    note_id: str
    title: str
    content: str
    folder_id: str | None = None

class ListNotesParams(BaseModel):
    folder_id: str | None = None
    limit: int = 50

@chat.function(
    name="list_notes",
    description="List notes — paginated, optionally filtered by folder.",
    action_type="read",
    data_model=NoteRecord,
)
async def list_notes(ctx, params: ListNotesParams) -> ActionResult:
    notes = await ctx.api.notes.list(folder_id=params.folder_id, limit=params.limit)
    return ActionResult.success(data={"notes": notes}, summary=f"{len(notes)} notes")
```

Equivalent using the `ActionResult[T]` generic (no `data_model` kwarg
needed):

```python
async def list_notes(ctx, params: ListNotesParams) -> ActionResult[NoteRecord]:
    ...
```

**Field-name symmetry.** Use the **same field names** in your
`data_model` as in the corresponding input `*Params` model. Closes a real
drift class where input was `content_text` but the record exposed
`content`, so chain steps referencing `$REF:notes[0].content_text` silently
got `None`. If your input uses `content_text`, your `data_model` should
expose `content_text` too (or vice versa — pick one and be consistent).

**Writes (V24).** Same `data_model=` kwarg, recommended but not required:

```python
@chat.function(
    name="create_note",
    description="Create a new note with title, content, optional folder.",
    action_type="write",
    event="notes.created",
    data_model=NoteRecord,  # what the call returns
)
async def create_note(ctx, params: CreateNoteParams) -> ActionResult:
    note = await ctx.api.notes.create(params.model_dump())
    return ActionResult.success(data=note, summary=f"Created {note['title']!r}")
```

### Skeleton contract reminder

The skeleton layer is the **LLM context cache** read by the classifier
and narrator — handlers must NOT read from it (V24-AST enforces this).
Conventions when authoring an extension:

1. **Refresh tools** that populate the skeleton MUST be named
   `skeleton_refresh_<section>` (or use the `@ext.skeleton("<section>")`
   decorator, which applies the convention automatically). The platform
   auto-derives `skeleton_sections` rows from these names; tools named
   `refresh_<section>` are NOT auto-wired (validator V13 WARN).
2. **Alert tools** that fire when a refreshed section changes MUST be
   named `skeleton_alert_<section>` (V13 INFO when prefix is missing).
3. **Skeleton data is read-only to your handlers.** Never write
   `ctx.skeleton.X = ...` or read `ctx.skeleton.X` inside a
   `@chat.function` body — validator V24-AST hard-rejects it. Use
   `ctx.api` to talk to the real backend; skeleton is refreshed
   automatically after writes via your refresh tools.
4. **Skeleton sections SHOULD have stable, typed shapes.** Document the
   shape in a Pydantic model and serialise via `model_dump()` before
   returning from your refresh tool — this keeps the LLM context cache
   parseable and helps the classifier hint at what fields it can rely
   on.

### Dev Portal enforcement (publish gate)

The Dev Portal runs `imperal_sdk.validator.validate_extension` against
every submitted build. To make V23 a hard publish gate after third-party
adoption, set the env var on the Dev Portal validator process:

```
IMPERAL_VALIDATOR_V23_SEVERITY=error
```

V23 then promotes from WARN to ERROR; submissions missing `data_model`
on any `read` tool will be rejected at publish with a structured fix-hint
pointing at the offending function.

### Tests

15 new tests covering:

- `data_model=` kwarg propagation to `FunctionDef._return_model`.
- Precedence: `data_model=` wins over `-> ActionResult[T]`.
- `-> ActionResult[T]` generic auto-detection when `data_model` is absent.
- V23 WARN (default) and ERROR (`IMPERAL_VALIDATOR_V23_SEVERITY=error`)
  modes for read tools missing `data_model`.
- V23 passes when `data_model=` declared OR `-> ActionResult[T]` used.
- V24 WARN for write + destructive tools missing `data_model`.
- V24 passes when `data_model=` declared.
- `ActionResult.validate_against` passes / warns / no-ops correctly.
- Synthetic `Secrets` panel: not registered when no secrets declared,
  registered after first `@ext.secret(...)` call (lazy registration).

### Compatibility

- **No breaking change.** SDK 5.0.0 extensions continue to load and run
  unmodified; V23 will surface as WARNs in the validation report but
  publish stays green by default.
- **Required platform.** Kernel that ingests `return_schema` from
  manifests for `$REF` path validation: 5.0.1+. Earlier kernels ignore
  the new field gracefully.

## 5.0.0 — 2026-05-15 — Unified Chain Orchestrator

**BREAKING:**
- `ChatExtension._route_with_llm` and the SDK-internal LLM router loop removed. All multi-tool reasoning now routes through kernel `chain_executor`.
- `ChatExtension.__init__` kwargs `tool_name=` and `system_prompt=` deprecated (no-op with WARN; removed in 5.1.0).
- Manifest emitter no longer produces `tool_<ext>_chat` orchestrator-tool entries.
- New validator V25 (ERROR severity): rejects manifests containing `tool_*_chat` entries.

**Migration:** Move content from `ChatExtension(system_prompt=...)` into `Extension(description=...)` and per-`@chat.function(description=...)`. Required kernel: 5.0.0+.

Closes a class of fabrication bugs in multi-tool dispatches where the SDK LLM router aggregated N inner tool calls into one DispatchResult with cloned `.data`, producing identical structured records for distinct tool functions.

## 4.2.16 — 2026-05-15

Enriched tool_use log with `UNKNOWN_FUNCTION(will-reject)` marker when the
LLM hallucinates a tool name not in the extension's `_functions` schema.
Caught at `handler.py:185` guard with `UNKNOWN_SUB_FUNCTION` error_code;
this change makes the rejection visible operator-side. Soak monitoring
can grep `UNKNOWN_FUNCTION(will-reject)` to track LLM hallucination rate.

Behavior change: log line format only. No federal contract impact. No
SDK API surface change.

Closes: sql-db isolation investigation false-positive (operator reading
journals saw `tool_sql_db_chat (round 2): send(...)` and assumed an
isolation breach; actual cause was LLM hallucination caught by existing
UNKNOWN_SUB_FUNCTION guard).

## 4.2.15 — 2026-05-14

**Feat: federal placeholder-args guard (I-PARAMS-NO-PLACEHOLDER-VALUES)**

New ChatExtension guard that rejects any tool call whose arg values look
like LLM-emitted placeholder sentinels — e.g. `<UNKNOWN>`, `<TODO>`,
`<MISSING>`, `<EMAIL>`, `<PASSWORD>`, `<USER_ID>`. Runs **before**
write-arg-bleed, target-scope, and 2-step confirmation guards so the
dispatch is short-circuited before any billing-charged work or audit-ledger
pollution. Friendly instruction-to-LLM rejection text feeds back through
the chat loop as a synthetic tool_result so the LLM can self-correct
and ask the user a clarifying question.

Motivating incident (2026-05-14): admin extension's `tool_admin_chat`
ChatExtension wrapper LLM produced `create_user({'email': '<UNKNOWN>',
'password': '<UNKNOWN>'})` when the user had not yet provided concrete
values. The anti-fab response-side layer correctly caught the drift
(`server did not reflect 'email': requested '<UNKNOWN>', got None`) but by
then the dispatch had already wasted billing, polluted `action_ledger`
with `target=<UNKNOWN>` rows, and produced an opaque user-visible failure.
This guard fails fast on the request side.

### Added

- **`check_placeholder_args(tu, action_type) -> str | None`** in
  `imperal_sdk.chat.guards` — recursive scan of `tu.input` (dict/list/str)
  for values matching `^<[A-Z][A-Z0-9_]*>$`. Tight regex — narrow
  false-positive surface: matches only uppercase-ASCII sentinel tokens,
  ignores prose containing `<UNKNOWN>` as a substring (e.g. error message
  bodies). Whitespace-tolerant via `.strip()`.

- **`_PLACEHOLDER_RE`** and **`_scan_for_placeholders(value)`** helpers
  (module-private; recursive over dict values and list/tuple items).

- Integration into `check_guards()` orchestrator before
  `check_write_arg_bleed`. Federal invariant
  **I-PARAMS-NO-PLACEHOLDER-VALUES** registered in kernel
  `tests/federal/_invariant_assertions.py`.

### Why a PATCH bump (not MINOR)

Strictly additive — new guard with default-allow surface. Existing
extensions emit no placeholder sentinels in legitimate flows, so the
guard is a no-op for every real call. No manifest schema change, no API
break, no rebuild required for downstream extensions.

## 4.2.14 — 2026-05-14

**Fix: regenerate static `imperal.schema.json` to match runtime `Manifest` model**

v4.2.13 added `background` + `long_running` to the `Tool` Pydantic model
in `manifest_schema.py` but forgot to regenerate the committed
`src/imperal_sdk/schemas/imperal.schema.json` static mirror. The CI
gate `test_static_schema_file_in_sync` caught the drift on the v4.2.13
release commit (same pattern as the v4.2.8 → v4.2.9 fix).

### Fixed

- Regenerated `src/imperal_sdk/schemas/imperal.schema.json` from runtime
  `manifest_schema.get_schema()`. Static artifact equals runtime model
  again.

No public API change. Single-file fix paired with v4.2.13.

## 4.2.13 — 2026-05-14

**Feat: `@chat.function(background=True)` declarative flag**

Sugar over `ctx.background_task(coro, ...)` from v4.2.12 — author writes
one handler body, the SDK auto-wraps the call in `ctx.background_task()`
when the flag is set.

### Added

- **`@chat.function(..., background=True, long_running=False)`** — when
  `background=True`, the SDK chat handler wraps the function call in
  `ctx.background_task()` instead of running the handler synchronously.
  The LLM receives an immediate ack envelope carrying `task_id`; the
  platform delivers the handler's returned `ActionResult` as a fresh
  bot turn when the work finishes. `long_running=True` raises the
  federal 180-second cap to 1800 seconds.

  ```python
  @chat.function(
      "refine_output",
      description="Refine the given text via AI completion.",
      action_type="write",
      event="text_refined",
      background=True,        # auto-wrap in ctx.background_task
      long_running=False,     # default cap 180s; True → 1800s
  )
  async def refine_output(ctx, params: RefineParams) -> ActionResult:
      # Body runs detached. No inner _work() wrapper, no manual task_id.
      await ctx.progress(50, "Generating with AI")
      resp = await ctx.http.post(api_url, json={...}, timeout=120)
      return ActionResult.success(
          summary="Refined output ready!",
          data={"text": resp.body["text"]},
      )
  ```

- **Manifest emission** — tools in `imperal.json` now carry `background`
  and `long_running` booleans. Strict `Manifest.Tool` schema gains
  matching optional fields.

### Trade-offs vs. explicit `ctx.background_task(coro)`

- **Sugar** is best for handlers whose entire body is the long work.
- **Explicit** stays preferred when you need to return a custom
  acknowledgement summary, choose `background_task()` conditionally at
  runtime, or run mixed sync + background work in the same handler.

### Migration

None required — `background` defaults to `False`. Existing
`@chat.function` handlers work unchanged.

## 4.2.12 — 2026-05-14

**Feat: LONGRUN-V1 Session 1 — long-running operations primitives**

Three new SDK surfaces for ops that exceed the 30s `ctx.http` ceiling:

### Added

- **`ctx.http.{get,post,put,patch,delete}(..., timeout=N)` per-call kwarg.**
  Federal cap 180s (`I-LONGRUN-HTTP-CAP-180S`). Anything larger raises
  `ValueError("ctx.http timeout {N}s exceeds federal cap (180s)...")` —
  use `ctx.background_task()` for longer ops.

- **`ctx.background_task(coro, *, long_running=False, name="") -> str`**
  — explicit opt-in for the kernel's auto-promote path. Coro runs detached
  via `asyncio.create_task`; kernel auto-delivers its returned
  `ActionResult` as a fresh bot message to the user's chat when done.
  `long_running=True` raises the 180s cap to 1800s
  (`LONG_RUNNING_TASK_S`). Returns task_id immediately.

- **`ctx.deliver_chat_message(text, *, msg_type="response", refresh_panels=None)`**
  — public API for extension-initiated bot turn injection. Text truncated
  to 64KB with marker. `msg_type` ∈ `{response, system, tool_result}`.

### Federal invariants (new)

- `I-LONGRUN-HTTP-CAP-180S` — per-call timeout federal cap.
- `I-LONGRUN-BG-CORO-RETURNS-ACTIONRESULT` — the coroutine MUST return
  `ActionResult`; non-ActionResult return triggers a critical audit row
  and delivers a fallback error to chat.
- `I-LONGRUN-BG-USER-SCOPED` — every background task is bound to
  `(ext_id, user_id)` at creation; cross-user cancel/status returns 403.
- `I-LONGRUN-CHAT-INJECT-USER-SCOPED` — chat inject scoped to
  `(ext_id, user_id)`; cross-user inject returns 403.
- `I-LONGRUN-CHAT-INJECT-AUDIT-EVERY` — every chat inject writes an
  audit row.

### Migration

None required — all additions are additive opt-in. Existing extensions
work unchanged.

## 4.2.11 — 2026-05-13

**Fix: `ui.Link(text=...)` no longer breaks panel render**

`ui.Link` now accepts the visible text via either `label=` (canonical) or
`text=` (alias matching the HTML/JSX `<a>text</a>` mental model). Before
v4.2.11, passing `text=` raised `TypeError: Link() got an unexpected
keyword argument 'text'` at panel-render time, which killed the right
panel for any extension that used the natural-looking kwarg.

```python
# All three are now equivalent
ui.Link("Read docs", href="https://docs.imperal.io")           # positional
ui.Link(label="Read docs", href="https://docs.imperal.io")     # canonical kwarg
ui.Link(text="Read docs",  href="https://docs.imperal.io")     # alias kwarg
```

Calling `ui.Link()` with neither `label` nor `text` raises a clear
`TypeError("ui.Link requires a 'label' (or 'text' alias)")` instead of
silently rendering an empty anchor. `label` wins if both are passed.

No migration required — existing `label=` callers are unchanged.

## 4.2.10 — 2026-05-13

**Feat: `@chat.function` default `chain_callable=True` for ALL action_types (was write/destructive only)**

V19 federal default: `chain_callable` now defaults to `True` for read
action_types too, not just `write` / `destructive`. This closes the
wrapper-LLM paraphrase risk for typed read handlers (`list_*`,
`search_*`, `get_*`) — when the classifier picks a read with concrete
args, the kernel `chain_executor._resolve_typed_dispatch` dispatches
the typed call directly instead of routing through the ChatExtension
BYOLLM tool-use loop.

Authors who need the wrapper-LLM tool-use loop for their handler
(conversational catch-all like `case_chat`) must explicitly set
`chain_callable=False`. The change is backward-compatible — existing
manifests with explicit `True` / `False` are unaffected; only the
implicit default for reads flips.

Migration: run `imperal build` to regenerate manifests; read functions
without explicit `chain_callable` will now emit `chain_callable: true`.

Federal invariant: closes the wrapper-LLM paraphrase risk class for
read intents, completing the `I-CHAT-FUNCTION-VERBATIM-PARAMS`
structural enforcement.

## 4.2.9 — 2026-05-13

**Fix: regenerate `src/imperal_sdk/schemas/imperal.schema.json` after SecretDecl addition**

v4.2.8 added the `SecretDecl` Pydantic model + `Manifest.secrets` field but
forgot to regenerate the committed static JSON Schema mirror. CI gate
`test_spec_validation.py::test_static_schema_matches_runtime_export[imperal]`
caught the drift — runtime Pydantic schema (with `SecretDecl` + `secrets[]`)
no longer matched the committed file.

This release ships the regenerated `imperal.schema.json` so the static
artifact equals the runtime model again. No public API change.

## 4.2.8 — 2026-05-13

**Fix: `secrets[]` finally in `Manifest` Pydantic schema**

EXT-SECRETS-V1 manifest emitter has been writing `manifest["secrets"] = [...]`
since v4.2.2, but the `Manifest` Pydantic model in `manifest_schema.py` had
no matching field. With `model_config = ConfigDict(extra="forbid")`, this
should have caused `validate_manifest_dict()` to reject every manifest that
declared secrets — but publish-time validators didn't gate through this
schema, so the drift lived silently for six PATCH releases.

### Added

- **`SecretDecl` Pydantic model** in `manifest_schema.py` — mirrors
  `imperal_sdk.secrets.spec.SecretSpec.to_manifest_dict()`. Validates
  `name` regex (`^[a-z][a-z0-9_]{0,62}$`), `write_mode` in
  `{user, extension, both}`, `max_bytes` in `[1, 65536]`,
  `rotation_hint_days >= 1` when present, non-empty `description`.
- **`Manifest.secrets: Optional[List[SecretDecl]]`** field — additive,
  back-compatible with manifests that don't declare any secrets.

### Federal invariants

| Invariant | What it pins |
|---|---|
| `I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC` | (already declared in v4.1.6 canary roundtrip test) Now actually holds for `secrets[]` — emitter and schema agree. |

### Migration notes

- **No code change required** in any extension. Existing manifests with
  `secrets[]` (emitted since v4.2.2) now pass strict Pydantic validation
  instead of relying on validators that didn't gate through the schema.
- Manifests with malformed secret entries (e.g. `name` with uppercase or
  invalid `write_mode`) will now fail `validate_manifest_dict()` at
  publish time. Previously they slipped through.

## 4.2.7 — 2026-05-13

**OAuth callback infrastructure + `ctx.webhook_url()` helper**

Closes the architectural gap that made `@ext.webhook("/callback", method="GET")`
non-functional for OAuth providers (Spotify, GitHub, Google). Before this
release: hardcoded redirect URIs in `*_config.py` landed users on a Next.js
404 (no nginx route for `/v1/ext/*`), and even if they reached auth-gw the
`ext_router` was POST-only.

### Added

- **`Context.webhook_url(path)`** — builds the canonical public callback
  URL from kernel-authoritative `_extension_id` (folder/manifest name, not
  the drift-prone Python `Extension("X", ...)` value). Returns
  `https://{IMPERAL_PUBLIC_HOST}/v1/ext/{app_id}/webhook/{path}` — default
  host `panel.imperal.io`. Path leading slash is normalised. Use this
  instead of hardcoding the URL in config files; hardcoded URLs are the
  #1 cause of OAuth-callback drift bugs.

- **Federal `ctx.secrets` inject moved to `ContextFactory._build_context`** —
  every dispatch path (chat tool, panel, skeleton, schedule, webhook,
  lifecycle, health check) now gets `ctx.secrets` uniformly. Previously
  the inject lived in `pipeline/extension_runner.py` and only fired for
  chat tool dispatch; panel handlers and others crashed with
  `AttributeError` when reading `ctx.secrets` despite the documented
  federal contract. `_HealthCheckCtx` gained a `_StubSecrets` graceful
  no-op so `@ext.health_check` handlers that read `ctx.secrets` don't
  crash with `AttributeError`.

- **Kernel-authoritative `app_id` in `ctx.cache`** — `CacheClient` is now
  constructed with `self._extension_id` (kernel parameter) instead of
  `getattr(self._extension, "app_id", ...)` (Python runtime). Fixes the
  401 class observed in production when an ext author writes
  `Extension("X-extension", ...)` while the deployed folder/manifest is
  `X` — auth-gw extcache row uses the deployed app_id and would never
  authorise the drifted Python value.

### Platform changes (live, not in the package)

- **nginx** on `panel.imperal.io` now routes `/v1/ext/*` to Imperal Auth
  Gateway (was: caught by Next.js catch-all → 404). Renamed config from
  `sharelock-panel*` → `imperal-panel`.
- **Auth-gw `ext_router`** accepts both `GET` (OAuth callbacks,
  verification challenges) and `POST` (server-to-server hooks) on the
  same `/v1/ext/{app_id}/webhook/{path}` endpoint.
- **Auth-gw `marketplace/router.py`** new public endpoint
  `GET /v1/marketplace/apps/{app_id}/webhooks` returns `[{path, method}]`
  for each declared `@ext.webhook`. Strips `secret_header`.
- **Imperal Panel** Secrets tab renders a blue info card listing every
  webhook URL with Copy buttons so end-users know what to paste into
  OAuth provider developer consoles.
- **Dev Portal App Details** gained a Webhooks tab (`imperal-ext-developer`
  v1.3.0) showing the per-app callback URLs with method badges.

### Migration notes

- Replace `SP_REDIRECT_URI = "https://..."` hardcodes with
  `ctx.webhook_url("/callback")` at runtime. Existing hardcoded URLs that
  match the canonical shape keep working — but new extensions should
  prefer the helper. No SDK-blocking change in this release.
- `@ext.health_check` handlers that call `await ctx.secrets.list()` /
  `.get(...)` now receive a graceful no-op stub instead of
  `AttributeError`. Reads return `None`/`[]`/`False`; writes raise
  `RuntimeError` (health checks have no per-user context).
- All shadow patches applied on 2026-05-13 to platform-worker and
  session-worker venvs are superseded by this release. Run
  `pip install --upgrade imperal-sdk==4.2.7` to clear them.

### Federal invariants

| Invariant | What it pins |
|---|---|
| `I-SECRETS-HANDLER-SCOPE-MEMORY` | Already pinned; the ContextFactory move preserves it — plaintext stays a local variable in the handler call. |
| `I-EXT-CACHE-APP-ID-KERNEL-AUTHORITATIVE` | (new) `CacheClient.app_id` sourced from kernel `_extension_id`, never from Python `ext.app_id`. |
| `I-WEBHOOK-URL-CANONICAL` | (new) `ctx.webhook_url(path)` returns `https://{IMPERAL_PUBLIC_HOST}/v1/ext/{kernel-authoritative-app_id}/webhook/{path}`. Source-inspection-friendly: env var lookup + no Python-instance attribute drift. |

## 4.2.6 — 2026-05-13

**New: `ui.Password` primitive + `ui.Input(type=)` kwarg**

Adds a browser-blind credential-entry primitive for EXT-SECRETS-V1 Panel UIs.
Renders as `<input type="password" autocomplete="new-password" spellcheck="false">`
so values are visually masked while the user types and don't get saved into
the browser's autofill database.

### Added

- **`ui.Password(placeholder=, on_submit=, value=, param_name=)`** — canonical
  credential-entry component. Federal EXT-SECRETS-V1 entry surfaces (Dev Portal
  Secrets tab, Panel SecretManagerCard equivalents) MUST use this instead of
  `ui.Input` for write_mode='user'/'both' secrets.
- **`ui.Input(type=)` kwarg** — accepts `"text"` (default), `"password"`,
  `"email"`, `"number"`, `"url"`. Backward-compatible: existing `ui.Input(...)`
  calls without `type=` continue rendering as text. The `type` prop is only
  emitted into manifest when != `"text"`.

### Panel rendering

`DInput.tsx` now reads `type` from props and applies to the native
`<input type={...}>` element. When `type === "password"` it also sets
`autoComplete="new-password"` (suppresses browser autofill/save prompts) and
`spellCheck={false}` (no red squiggle on opaque base64 / hex values).

### Federal note

`type="password"` is a defence against shoulder-surfing, not a security
control. The plaintext still travels in the POST body to the server, which
is the only correctness boundary. Audit chokepoint + Vault transit are what
make this federal-grade — see EXT-SECRETS-V1 spec for the contract.

## 4.2.5 — 2026-05-13

**Fix: synthetic `__panel__*` tools excluded from validator tool_count + tests**

v4.2.4 introduced an unconditional synthetic `secrets` panel via `Extension.__init__`,
which auto-registers a `__panel__secrets` tool internally. The validator's `tool_count`
logic was counting this synthetic tool as a user-authored tool, masking V3 ("at least
one tool") error detection for extensions with zero user tools and inflating
marketplace tool counts.

### Fixed

- **`validator.tool_count`** now excludes any tool whose name matches the
  synthetic-prefix allowlist (`__panel__`, `__widget__`, `__tray__`, `__webhook__`).
  These are platform-provided, not author-authored, and shouldn't count.
- **`V3 "at least one tool"`** check now correctly fires for ext'ы with only
  synthetic auto-registered tools.
- `tests/test_panels.py::test_multiple_panels` updated to assert +1 for the
  always-present synthetic `secrets` panel.

### Notes

- No behavior change for extensions with at least one real `@ext.tool` or
  ChatExtension. Strict-tool-count-zero ext'ы now properly fail V3 again.
- Marketplace tool counts shown to users no longer count synthetic panels.

## 4.2.4 — 2026-05-13

**EXT-SECRETS-V1 — unconditional synthetic Secrets panel**

In v4.2.3 the synthetic Secrets panel was registered conditionally on the
first `@ext.secret(...)` call, which meant extensions that did not declare
secrets had no menu entry — leaving end-users without a discoverable place
to manage credentials when developers later add declarations.

This release flips the registration to **unconditional**: every Extension
instance auto-registers the synthetic `secrets` panel in `__init__` (slot
`right`, title `Secrets`, icon `KeyRound`). When the manifest has zero
declared secrets, the panel renders an empty state with developer guidance
(`@ext.secret(...)` code example + link to docs). When declarations exist,
it renders one card per secret with `is_set` status + Manage button.

### Migration notes

- **No code changes required**. Bump your ext's SDK pin to `>= 4.2.4` and
  redeploy via Dev Portal — the Secrets tab appears automatically.
- Extensions that genuinely never need credentials still get the tab; this
  is intentional for UX consistency. Federal V32 contract still requires
  `@ext.secret` for any real credential access at runtime.

## 4.2.3 — 2026-05-13

**EXT-SECRETS-V1 UX polish — synthetic `secrets` panel auto-injected**

When an extension declares one or more `@ext.secret(...)` entries, the SDK
now auto-registers a synthetic `secrets` panel (slot=`right`, title=`Secrets`,
icon=`KeyRound`) so the user-facing Secrets manager appears alongside the
extension's own tabs without the author writing any panel code.

### Added

- **Auto-injected `secrets` panel**: `Extension.secret(...)` on first call
  registers a built-in handler from `imperal_sdk.secrets.panel_handler`. The
  handler reads declared secrets + live is_set state from `ctx.secrets.list()`
  and renders `ui.Card` rows with status badges + a `Manage` button that
  routes to the dedicated `/ext/{ext_id}/secrets` page.
- The synthetic panel uses **slot=`right`** defensively — most extensions use
  `left` (sidebar nav) and `center` (main content); `right` is rarely-used so
  the panel-sync logic in `imperal-ext-developer` won't overwrite it. If your
  extension already declares a `right`-slot panel, your panel wins; users
  still reach the Secrets UI via the chat-top ribbon and the direct
  `/ext/{ext_id}/secrets` route.
- Panel idempotent — multiple `@ext.secret(...)` calls register the panel
  only once.

### Migration notes

- **No code changes required** to receive the synthetic panel. Bump your
  ext's SDK pin to `>= 4.2.3` and redeploy via Dev Portal.
- Once your extension is on v4.2.3+, the chat-top ribbon (added in Panel for
  v4.2.2 discoverability) becomes redundant for that ext — synthetic panel
  appears in the `right` slot as a proper tab.

## 4.2.2 — 2026-05-13

### Added — EXT-SECRETS-V1 (closes ARCH-D1 in compliance-posture.md)

- **`@ext.secret(name, description, ...)`** declarative decorator. Extensions
  declare what user-supplied credentials they need (API keys, OAuth tokens,
  webhook signing secrets). Each declaration carries `required`,
  `write_mode` (`user` / `extension` / `both`), `max_bytes`, optional
  `rotation_hint_days`. Manifest emits `secrets[]` as an additive optional
  field (manifest schema v3 stays — back-compat).

- **`ctx.secrets`** accessor on `KernelContext` (resolved kernel-side; SDK
  ships `SecretClient` HTTP proxy to auth-gw `/v1/secrets/*`). Methods:
  `get(name)` → plaintext or None; `set(name, value)` → raises
  `SecretWriteForbidden` for `write_mode='user'`; `delete(name)`;
  `is_set(name)` (cheap metadata, no audit); `list()` (descriptions +
  is_set, never values).

- **Dev mode** (`IMPERAL_DEV_MODE=true`): `get(name)` reads
  `IMPERAL_SECRET_<UPPER_NAME>` env var; set/delete are no-ops with WARN
  log. Manifest contract still enforced (I-SECRETS-CONTRACT-DECLARED —
  undeclared names raise even in dev).

- **`imperal_sdk.testing.MockSecretStore`** for pytest fixtures. Optional
  `declared` set to mirror SecretNotDeclaredError semantics.

- **Federal invariants enforced SDK-side**:
  - `I-SECRETS-HANDLER-SCOPE-MEMORY` — no module/class-level plaintext
    cache in `SecretClient`; source-inspection-friendly
  - `I-SECRETS-CONTRACT-DECLARED` — runtime read/write of undeclared
    name raises `SecretNotDeclaredError`; manifest is single source of truth
  - `I-SECRETS-VAULT-DEPENDENCY` — auth-gw 503 → `SecretVaultUnavailable`

- **Federal invariants enforced auth-gw-side** (live in production
  whm-gateway since 2026-05-13):
  - `I-SECRETS-USER-SCOPED` — cross-user 403
  - `I-SECRETS-NEVER-LOGGED` — `action_ledger` row stores length +
    sha256-prefix-8 only, never the value
  - `I-SECRETS-EXT-SCOPED` — extension token's `ext_id` claim must
    match URL `{ext_id}`
  - `I-SECRETS-AUDIT-FOREVER` — every op writes
    `retention_class='security_forever'`

- **New JWT claims**: `actor_kind` (`'user'` or `'extension'`) and `ext_id`
  (extension tokens only). `build_session_claims` and
  `build_extension_claims` helpers in `app.auth.claims` on the auth-gw side.

### Notes

- Migration of existing plaintext-stored credentials (BYOLLM keys, OAuth
  refresh tokens, etc.) is at extension-author pace; no automated migration.
  The V32 publish-time validator blocks *new* extensions that read
  credential-like fields without an `@ext.secret` declaration
  (validator implementation deferred).

## 4.2.1 — 2026-05-11

### Fixed

- **`MANIFEST-SKELETON-1` false positive on `@ext.tool("skeleton_alert_*")`**.
  The local AST validator (`validator_v1_6_0.py`) was flagging the
  canonical paired-alert pattern as a rule violation with the fix
  suggestion *"Replace with `@ext.skeleton(<section>)`"* — but that
  suggestion is wrong. `@ext.skeleton(section, alert=True)` registers
  **only** `skeleton_refresh_<section>`; the paired
  `skeleton_alert_<section>` handler **must** be registered separately
  with `@ext.tool` (the kernel discovers alerts by tool-name presence
  in `tools[]`, not via any `@ext.skeleton` metadata). The validator
  now flags only `skeleton_refresh_*` tools, leaving
  `skeleton_alert_*` as the documented, kernel-supported pattern.
  See `Extension.skeleton` docstring and
  `docs.imperal.io/en/sdk/decorator-skeleton-reference`.

  Test updates: `test_manifest_skeleton_1_triggers_on_wrong_decorator`
  expects exactly 1 hit (refresh only); new
  `test_manifest_skeleton_1_silent_on_paired_alert_via_ext_tool` locks
  the canonical pattern as silent.

## 4.2.0 — 2026-05-11

### Added

- **`Extension(system: bool = False)` kwarg** declares an extension as
  a platform-managed system app. System apps are auto-installed for
  every user on registration, never shown in marketplace listings, and
  cannot be uninstalled. Federal contract additions:
  - `I-SYSTEM-APPS-NEVER-UNINSTALLABLE` — uninstall on `system=true`
    returns 403 at the auth-gw level.
  - `I-MARKETPLACE-HIDES-SYSTEM` — `/v1/marketplace/*` SELECT queries
    filter `system = FALSE` at the SQL layer.
  - `I-SYSTEM-FLAG-RESERVED-FOR-IMPERAL` — only first-party Imperal
    authors may set `system=True`; Dev Portal rejects 3rd-party
    publishes at the author allowlist.
- **Manifest field**: top-level `system: bool` is emitted by
  `imperal build` whenever `Extension(system=…)` is set. `manifest.py`
  and `manifest_schema.Manifest` both carry it; the JSON schema file
  (`src/imperal_sdk/schemas/imperal.schema.json`) is regenerated.
- **Validator V31**: local check that rejects `system=True` for
  non-Imperal authors. Triggered by `IMPERAL_AUTHOR_ID` env var so
  local dev without the env continues to pass (Dev Portal is the
  authoritative gate at publish time). 4 new unit tests pinning the
  contract.

### Migration notes

- The four first-party Imperal extensions (`admin`, `billing`,
  `developer`, `automations`) should add `system=True` to their
  `Extension(...)` declaration. Existing rows in `developer_apps.system`
  were backfilled during the Sprint B platform deploy, so the live
  marketplace already hides them — re-publishing them through the
  Dev Portal will keep manifest and DB consistent.

978 tests pass, 3 skipped.

## 4.1.9 — 2026-05-10

### Fixed

- **`imperal init <name>` template now passes federal validators
  cleanly.** The previous scaffold generated `Extension(name, version="1.0.0")`
  without `display_name=`/`description=`/`icon=`/`actions_explicit=` —
  failing V14 (description ≥40 chars), V15 (display_name ≥3 chars
  ≠ app_id), V16 (per-function description ≥20 chars), and V21 (icon.svg
  required) on the very first `imperal validate`. New scaffold writes
  v4-correct kwargs, a proper `ChatExtension(...)` declaration, an
  `icon.svg` placeholder (V21-compliant XML root + viewBox),
  `requirements.txt: imperal-sdk>=4.0.0` (was `>=1.0.0`), and a test
  file that exercises Pydantic param validation + `MockContext`.

### Changed

- CLI `init` next-steps message updated to the canonical workflow:
  `pip install` → `imperal build` → `imperal validate` →
  `imperal test` → `imperal deploy`.

974 tests pass, 3 skipped.

## 4.1.8 — 2026-05-10

### Added

- **`@ext.panel(..., center_overlay=True)`** federal v4.1.8 — replaces
  the legacy hardcoded TypeScript `isCenterOverlay` allowlist in the
  Imperal Panel host (`usePanelDiscovery.ts`). When set, the kernel
  publishes `center_overlay: true` into the panel's `unified_config`
  entry; the frontend reads the flag declaratively instead of
  consulting a hardcoded list of `panel_id` literals (`compose`,
  `email_viewer`, `editor`, `workshop`).
- Backward compatibility: the legacy hardcoded allowlist remains as a
  fallback for extensions that haven't been redeployed since v4.1.7.
  It will be dropped once `compose`/`email_viewer`/`editor` migrate
  to declarative `center_overlay=True`.

974 tests pass (3 skipped).

## 4.1.7 — 2026-05-10

### Added

- **`PANEL_SLOT_RENDERING_STATUS`** federal contract in
  `imperal_sdk.types.contributions` — single source of truth for
  what the Imperal Panel host actually does with each slot:
  `"permanent"` (always-fetched column), `"center-overlay"`
  (on-demand via `__panel__<id>` action when panel_id matches the
  host's `isCenterOverlay` allowlist; chat collapses to 380 px
  right rail), or `"reserved"` (accepted by SDK validator but
  frontend has no render path).
- **`I-PANEL-RENDERING-CONTRACT`** invariant gate
  (`tests/test_panel_rendering_contract.py`) — when a contributor
  adds a slot to `ALLOWED_PANEL_SLOTS` they MUST also declare its
  rendering status. Closes the v4.1.x class of bug where extensions
  decorated with `slot="overlay"` etc. and the SDK accepted the
  registration but the frontend silently dropped them.
- Companion `docs.imperal.io/concepts/panels.mdx` rewrite to match
  the contract — accurate slot table + center-overlay activation
  walk-through (auto_action wire-up + isCenterOverlay allowlist).

974 tests pass, 3 skipped.

## 4.1.6 — 2026-05-10

### CI / federal hardening

- **`I-MANIFEST-EMITTER-SCHEMA-SYMMETRIC`** invariant added — new
  `tests/test_manifest_roundtrip_gate.py` builds a canary Extension
  exercising every emitter code path (`@ext.tool` / `@ext.signal` /
  `@ext.schedule` / `@ext.webhook` / `@ext.on_event` / `@ext.on_install` /
  `@ext.health_check` / `@ext.panel` / `@chat.function` with all v4
  fields including `effects` + `id_projection`) and asserts every
  field emitted by `generate_manifest()` round-trips through
  `validate_manifest_dict()` cleanly. Catches the v4.1.4 → v4.1.5
  class of bug at PR time instead of at CLI-validate time.
- Hard-floor checks for v4 required top-level fields and per-tool
  v4 contract fields (action_type / chain_callable / effects /
  params_schema / event / id_projection).

No runtime behaviour change. 971 tests pass (was 968 + 3 new gates).

## 4.1.5 — 2026-05-09

### Fixed

- `manifest_schema.Tool` now accepts `id_projection` (federal v4.1.2).
  The chat extension emitter wrote this field into manifests, but
  `Tool.model_config = ConfigDict(extra="forbid")` rejected it during
  `imperal validate`, breaking every extension that used the v4.1.2
  feature. Production extensions (notes, sql-db, tasks) shipped with
  this field via the Dev Portal validator pipeline; the local CLI
  validator was the only consumer that erred.
- `manifest_schema.Manifest` now accepts `sdk_version` so the field
  emitted by `generate_manifest` round-trips through validation.

### Added

- `generate_manifest(ext)` now emits `sdk_version` (sourced from
  `imperal_sdk.__version__`) at the top level of `imperal.json`. Stops
  the `SDK-VERSION-1` validator from warning on every fresh build that
  uses v1.6.0 features (`ctx.cache`, `@ext.skeleton`).
- Static `src/imperal_sdk/schemas/imperal.schema.json` regenerated to
  reflect the new optional fields.

### Tests

- 968 tests pass (3 skipped) including the static-schema-matches-runtime
  spec validator that catches schema drift.

## 4.1.4 — 2026-05-09

### Documentation

- Repository hygiene cleanup. The canonical, version-locked,
  code-validated documentation lives at https://docs.imperal.io.
  Removed the stale local `docs/` tree (most files predated the v4
  Federal Extension Contract) and `examples/hello_extension/` (pre-v4
  scaffold that would fail validators V14, V15, V19, V21, V24).
- README rewritten under the canonical positioning: *"Imperal Cloud
  is the world's first AI Cloud OS. Webbee 🐝 is its agent."* The
  5-minute quickstart now ships v4 federal-contract-correct code,
  release notes no longer duplicated inline (CHANGELOG.md is the
  single source of release history), broken or removed deep links
  cleaned up.

### Tests

- OpenAPI specs relocated from `docs/openapi/` to
  `tests/fixtures/openapi/` — semantically they were always test
  fixtures (read by `tests/test_spec_validation.py`) rather than
  user-facing documentation. `OPENAPI_DIR` updated to the new path.
  No public-API or runtime change.

### Repository

- GitHub `description` updated to put Webbee front-and-centre:
  *"The SDK for Webbee 🐝 — the agent of Imperal Cloud, the world's
  first AI Cloud OS. Build extensions in Python."*
- GitHub homepage URL set to https://docs.imperal.io.

## 4.1.3 — 2026-05-06

### Refactor

- Split `chat/handler.py` (807 LOC, violated rule 6 >300 LOC) into thinner
  `chat/handler.py` + new `chat/retry.py` containing the Pydantic feedback
  loop helpers (`format_pydantic_for_llm`, `_emit_retry_outcome`,
  `_RETRY_BUDGET`, `_validation_missing_field_response`).
- Public API surface unchanged — these symbols remain importable from
  `imperal_sdk.chat.handler` via re-export. No behavioral change vs v4.1.2.
- Logger name for `validation_retry_outcome` lines pinned to
  `imperal_sdk.chat.handler` (NOT `__name__`) to preserve SigNoz scrape
  pipeline contract and existing `caplog` test scoping.
- Federal: closes ARCH-FILES-SPLIT-2 (active_followups 2026-05-02).

## v4.1.2 — 2026-05-05 — `@chat.function(id_projection=...)` for chain-step target projection (NEW-5)

Federal extension contract addition: `@chat.function` accepts an optional
`id_projection` kwarg declaring the params field that carries the resolved
target id when the tool runs as a downstream chain step. Closes the
architectural gap surfaced by `delete_notes_from_folder` whose composite
name made the kernel's verb-prefix heuristic produce
`notes_from_folder_id` instead of `folder_id`.

Required for tools where the heuristic fails (compound names like
`delete_notes_from_folder`, `mark_emails_as_read`,
`archive_drafts_in_project`). Optional for simple `delete_<entity>` /
`update_<entity>` names — the heuristic continues to work.

### Added

- **`@chat.function(id_projection=...)`** kwarg (`chat/extension.py`).
  Declares the params field carrying the resolved target id for chain
  dispatch. Empty string default — backward-compat for legacy authors.
- **FunctionDef.id_projection** field surfaces the declaration to the
  manifest emitter.
- **Manifest serialization** includes `id_projection` per tool entry —
  kernel reads it at ext load and populates `ToolEntry.id_projection` so
  `_project_item_to_args` consults it before falling back to the
  Pydantic-field auto-detect or verb-prefix heuristic.

### Tests

- `test_chat_function_id_projection_kwarg_propagated` — kwarg flows into
  FunctionDef.
- `test_chat_function_id_projection_default_empty` — default empty
  preserves backward compat.

### Migration

- For tools whose name DOES directly imply the target field
  (`delete_note` -> `note_id`), no change required. The kernel heuristic
  continues to work.
- For composite names where the heuristic produces a wrong field, declare
  explicitly:

  ```python
  @chat.function(
      "delete_notes_from_folder",
      action_type="destructive",
      id_projection="folder_id",
  )
  async def delete_notes_from_folder(ctx, params: DeleteNotesFromFolderParams):
      ...
  ```

  Without `id_projection`, chain step that resolved a folder upstream
  would have its id dropped on the floor (kernel would look for
  `notes_from_folder_id` field which the params model does not have).

## v4.1.1 — 2026-05-05 — Tighten emit_narration mode/prose schema descriptions (NEW-1)

Production runtime fix for a P0 hallucination class observed in BYOLLM extensions:
when `narration_mode="audit"` reaches a single-extension write/destructive turn,
the LLM over-applies the audit-brevity semantic GLOBALLY across all tool calls
in the same turn. Concrete repro: user asks `"создай заметку ВАВАВА с эссе про
зелёный цвет 200 слов"`, LLM emits `create_note(title='ВАВАВА',
content_text='<essay about green color, 200 words>')` — a placeholder pattern
instead of the actual 200-word essay.

Root cause: the `mode` and `prose` field descriptions in `EMIT_NARRATION_TOOL`
described audit semantics without explicitly scoping them to the prose field.
The LLM (Anthropic Haiku 4.5 + Sonnet 4 BYOLLM models) faithfully read the
description and generalized "audit = brief / structured / no creative prose"
to all tools the BYOLLM dispatched — including content-bearing fields in
`create_note`, `send_email`, `write_post`, etc.

### Changed

- **`mode` field description** in `EMIT_NARRATION_TOOL` schema (`chat/narration.py`)
  now carries an explicit `SCOPE` clause clarifying that audit semantics control
  only the `prose` field's interpretation by the kernel renderer — NOT a global
  brevity directive. Other tool calls (create_note, send_email, write_post)
  MUST contain the full user-requested content in their own parameter fields,
  regardless of audit vs. narrative mode.
- **`prose` field description** now carries a `CRITICAL` clause that warns
  against placeholder anti-patterns (e.g. `<essay 200 words>`) and explicitly
  references concrete content fields in other tools (`create_note.content_text`,
  `send_email.body`) that must always carry the full user-requested content.

### Tests

- `test_mode_description_scope_clause_present` — guards the SCOPE clause + the
  "Other tool calls" reference + the "FULL user-requested content" instruction.
- `test_prose_description_warns_against_placeholders` — guards the CRITICAL
  clause + placeholder anti-pattern callout + concrete `create_note.content_text`
  example.

### Migration

No code changes required from extension authors. Pure schema-description
tightening; the LLM observes the new descriptions on the next turn after
deploy. PyPI publish + `pip install --upgrade imperal-sdk==4.1.1` on the
kernel host and auth-gateway venvs is the only operational step.

## v4.1.0 — 2026-05-02 — Pydantic feedback loop: bounded retry on validation failure (SPEC2-LLM-ARGS-QUALITY)

Production runtime fix for the largest single hallucination class observed in current
production traffic: 75% of audit-window hallucinations traced to LLM emitting
wrong-shape arguments to ``@chat.function`` calls. v4.1.0 adds a bounded retry loop
inside the SDK chat tool-use path that catches ``pydantic.ValidationError``, formats
structured prose feedback to the LLM, and lets the LLM self-correct with corrected
arguments.

Production evidence: 11 ``validation_rejected/24h`` rows on ``tasks/create_task`` —
all from LLM omitting required ``title`` / ``project_id``. Expected to drop to ≤3/24h
after this release.

### Added

- **Pydantic feedback loop** in ``chat/handler.py`` (SPEC2-LLM-ARGS-QUALITY). When
  ``@chat.function`` Pydantic validation fails, the SDK formats structured prose
  feedback and retries the LLM call up to twice per tool before falling back to the
  existing ``VALIDATION_MISSING_FIELD`` response.
- New top-level helper ``format_pydantic_for_llm(e)`` translates
  ``pydantic.ValidationError`` into per-field human-readable lines. Supports the
  Pydantic 2 error type prefixes ``string_*``, ``int_*``, ``datetime_*``, plus exact
  matches ``missing``, ``list_type``, ``extra_forbidden``, with fallback to
  Pydantic's own ``msg`` for unknown types.
- New SigNoz log-derived metric ``validation_retry_outcome`` with outcome enum
  ``no_retry | success | exhausted | llm_gave_up | redundant | fabricated_id_on_retry``.
  No new dependencies — counters derived from log-line scrape, same pattern kernel
  uses elsewhere.
- ``_validation_missing_field_response`` private helper extracts shared
  VALIDATION_MISSING_FIELD JSON construction from ``exhausted`` and ``llm_gave_up``
  branches (DRY per CLAUDE.md rule 9).
- Federal invariants: I-PYDANTIC-RETRY-BUDGET (max 2 retries per tool),
  I-PYDANTIC-RETRY-SCOPE (only ``PydanticValidationError`` triggers retry —
  not ``FABRICATED_ID_SHAPE`` / ``UNKNOWN_SUB_FUNCTION`` / generic ``Exception`` /
  ``TaskCancelled``), I-PYDANTIC-FEEDBACK-STRUCTURED (structured prose, not raw
  JSON), I-PYDANTIC-FC-SINGLE-APPEND (one ``_functions_called`` entry per logical
  tool call across retries), I-PYDANTIC-WIRE-FROZEN (no schema or contract
  changes).
- 17 new TDD test cases in ``tests/test_chat_pydantic_retry.py`` covering pure
  function (8), SigNoz emission (3), retry success / exhausted (2), edge cases
  (4 — gave-up / redundant / multi-tool_use / switched-tool), retry scope
  (5 — non-Pydantic failure classes), fc-uniqueness (4), wire contract
  preservation (2), token budget regression (1), exception propagation (1).
- ``tests/test_chat_pydantic_retry.py::allow_target_scope`` pytest fixture
  monkeypatches the SDK-standalone ``_check_target_scope`` fallback for retry
  integration tests, allowing them to exercise the retry path without
  ``imperal_kernel`` installed.

### Changed

- ``_execute_function`` accepts a new keyword-only kwarg
  ``retry_ctx: dict | None = None``. Without it, behavior is exactly the v4.0.1
  implementation (legacy ``**kwargs`` extensions and any caller not yet updated
  remain unaffected). With it, the Pydantic retry loop activates.
- ``handle_message`` tool-use loop now passes ``retry_ctx`` to ``_execute_function``
  on the single per-tu call site.
- Module constant ``_RETRY_BUDGET = 2`` defines the per-tool-call retry cap.
- Retry call-site invokes the ``_llm_usage_callback`` for token cost
  observability, mirroring the main loop's billing telemetry pattern.

### Security

- I-AH-1 ``check_id_shape_fabrication`` now re-runs on every retry attempt input,
  not just the first attempt. Federal security guard remains effective across
  retries; new SigNoz alert at ``outcome=fabricated_id_on_retry > 0`` flags any
  case where the LLM hallucinates an ID slug specifically in a retry round.

### Fixed

- ``runtime/executor.py`` SDK-standalone fallback for ``_check_target_scope``
  (used when ``imperal_kernel`` is not installed) now returns a complete dict
  shape with all keys callers expect (``allowed``, ``reason``, ``target_user_id``,
  ``required_scope``, ``force_confirmation``, ``cross_user``, ``verdict``).
  Previously the partial dict caused ``KeyError`` in ``chat/guards.py:258`` when
  running SDK tests standalone. Production behavior unchanged (production has
  ``imperal_kernel`` installed and uses the real implementation). Log level
  also dropped from ``error`` to ``warning`` since standalone is an expected
  scenario for SDK testing, not an operational failure.

### Wire contract

- **No changes** to ``FunctionCall`` dataclass, ``FunctionCallModel`` Pydantic
  schema, or ``chat_result.schema.json``. SHA256 snapshot pinned in
  ``test_chat_result_schema_unchanged``.

### Token cost

Sonnet 4.6 retry call ≈ 700 input + 150 output tokens. Per-call cost ~$0.0044.
At current production rate (11 rejected/24h × max 2 retries), worst-case
additional spend ≈ $3/month. Negligible compared to existing chain LLM cost.

## v4.0.1 — 2026-05-01 — Federal validator polish: V18 ActionResult, V21 XML parser, V23 dropped, V24 AST walk

Patch release that swaps regex / substring anti-patterns in V14-V24 for proper structural validation, and drops V23 as redundant.

### Changed

- **V18 — typed return annotation.** Now accepts the Generic-based ``ActionResult`` class (and its subclasses) in addition to Pydantic ``BaseModel`` subclasses. Previously V18 only checked the auto-detected ``_return_model`` field, which the decorator only populates for BaseModel returns; ``-> ActionResult`` annotations were rejected falsely. Uses the existing ``_resolve_hints`` + ``_looks_like_action_result`` helpers.
- **V21 — SVG icon validation.** Replaced lowercase substring scan (``"<svg" in head``, ``"viewbox" in head``, ``"data:image" in head``) with proper ``xml.etree.ElementTree`` parsing. Now correctly: (a) ignores XML namespaces when checking the root tag, (b) reads the ``viewBox`` attribute via ``root.attrib`` lookup, (c) walks every ``<image>`` element and inspects its ``href`` / ``xlink:href`` attributes for embedded base64 raster, (d) returns a precise ``ParseError`` message when the SVG is malformed.
- **V24 — ``ctx.skeleton`` access scan.** Replaced the regex ``\bctx\s*\.\s*skeleton\b`` with an ``ast.NodeVisitor`` that walks ``Attribute(value=Name('ctx'), attr='skeleton')`` nodes. The AST walk ignores incidental matches inside string literals, comments, and unrelated identifiers, and reports the precise line numbers of offending accesses.

### Removed

- **V23 — capability shape validator.** Dropped as redundant. ``manifest_schema.SCOPE_PATTERN`` already enforces capability/scope shape via the existing Pydantic field validator, and the federal capability registry check is a kernel-side concern (scope chokepoint), not the SDK's job. The previous V23 regex was also too strict (rejected real production patterns like ``events:subscribe`` and ``admin:users:read``).

### Fixed

- **Backward-compat ``_ext_functions`` accessor** — validator now reads from either ``chat_ext.functions`` (real ``ChatExtension`` property) or ``chat_ext._functions`` (older test fixtures), so unit tests using ``FakeChatExt`` mocks continue to work without breaking changes.
- **Synthetic tools restored to their declarative sections** — ``__webhook__/__panel__/__widget__/__tray__`` entries skipped from the user-facing ``tools`` list again (the v4.0.0 release accidentally emitted them with a ``synthetic`` flag, which broke the ``M5`` identifier check downstream).
- **Defensive ``getattr`` on ``FunctionDef`` fields** in V16/V19/V20 — older test fixtures without ``description`` / ``chain_callable`` / ``effects`` attributes no longer crash the validator with ``AttributeError``.
- **``Manifest`` schema version literal expanded to ``[1, 2, 3]``** — the static ``imperal.schema.json`` file is regenerated to include the new v4.0.0 federal fields (``actions_explicit``, ``icon_size_bytes``, ``lifecycle_hooks`` + per-tool ``action_type``, ``chain_callable``, ``effects``, ``params_schema``, ``return_schema``, ``event``, ``owner_chat_tool``).

### Tests

- 934 passed, 3 skipped, 0 failed (was 12 failed in v4.0.0).
- ``test_is_valid_no_errors`` updated to construct a federal-compliant ``Extension`` fixture (``display_name``, ``description``, ``icon``, ``actions_explicit``).
- ``test_manifest_schema_version_rejects_3`` renamed to ``test_manifest_schema_version_rejects_4`` — v4.0.0 accepts ``schema_version=3``; v5.0.0 will accept ``=4``.
- ``test_manifest_emits_webhooks_section`` asserts ``schema_version == 3`` (was ``2``).

## v4.0.0 — 2026-05-01 — Federal Extension Contract: typed dispatch, manifest v3, V14-V24 validators

**BREAKING.** Major release. Closes the chain-planner BYOLLM-router gap that allowed silent write failures (extension says "deleted" but nothing was deleted because the router LLM summarised instead of dispatching the typed call). Federal contract: every extension that passes V14-V24 is GUARANTEED to work with the kernel's typed-dispatch chain pipeline — no LLM guessing, no path divergence.

### Added — Federal v4.0.0 contract surface

- **`Extension(display_name=, description=, icon=, actions_explicit=)` kwargs.** Every extension declares its identity, federal description, SVG icon, and the typed-dispatch contract opt-in (default `True`).
- **`@chat.function(chain_callable=, effects=)` kwargs.** `chain_callable` defaults to `True` for `action_type in ("write","destructive")` so the kernel issues direct typed calls instead of delegating to the ChatExtension LLM router. `effects=["create:note"]` declares the side-effect surface for the audit ledger + chain narrator.
- **Manifest schema v3** — `manifest_schema_version=3`. New top-level fields: `name`, `description`, `icon`, `icon_size_bytes`, `actions_explicit`, `lifecycle_hooks`. Per-tool fields: `action_type`, `chain_callable`, `effects`, `params_schema`, `return_schema`, `event`, `owner_chat_tool`, `synthetic`. Every `@chat.function` is now emitted as a typed tool with full Pydantic schema — kernel chain planner reads these directly.
- **Auto-detected return type from Pydantic annotation.** `async def fn(ctx, params: XParams) -> ActionResult` populates `_return_model` automatically; manifest emits `return_schema` from `model_json_schema()`.

### Added — Federal validators V14-V24 (all ERROR severity)

- **V14** — Extension `description` must be ≥40 chars and ≠ `app_id`.
- **V15** — Extension `display_name` must be ≥3 chars and ≠ `app_id` (case-sensitive verbatim).
- **V16** — Every `@chat.function` description ≥20 chars (skip `__*` synthetic tools).
- **V17** — Every `@chat.function` declares an explicit Pydantic `BaseModel` param. No `**kwargs`, no `Any`, no `func.__doc__`-derived params.
- **V18** — Every `@chat.function` returns a Pydantic model (subclass of `ActionResult`).
- **V19** — `Extension(actions_explicit=True)` AND every `action_type in ("write","destructive")` tool has `chain_callable=True`.
- **V20** — Every write/destructive `@chat.function` declares `effects=[...]` (WARN-level v4.0.0, ERROR v5.0.0).
- **V21** — Required SVG icon. Must be valid SVG with `<svg>` root + `viewBox`, max 100KB, no embedded base64 raster.
- **V22** — Lifecycle hooks (`on_install` / `on_refresh` / `on_uninstall` / `on_upgrade`) match SDK signature contract. Closes the `on_refresh() got unexpected keyword 'message'` TypeError class.
- **V23** — `capabilities` declared in known shape `<namespace>:read|write|admin|*`.
- **V24** — `@chat.function` handlers MUST NOT read from `ctx.skeleton.*` (AST scan). Skeleton is the LLM-context cache only; handlers use `ctx.api` for real backend ops.

### Removed — BREAKING

- `AA_BRANCH` typed-call fastpath in kernel `session_workflow.py` — replaced by federal manifest-driven dispatch in `chain_planner.py`. The systemd drop-in `IMPERAL_KERNEL_ACTION_AUTHORITY=true` is no longer read; remove it from your worker config. Single federal pipeline now serves all read/write/destructive paths uniformly.
- `ChatExtension(model=...)` parameter — deprecated since 3.3.0. LLM resolution lives in kernel ctx-injection (`ctx._llm_configs`).

### Why this matters

Pre-v4.0.0, the kernel's chain planner saw only the `tool_<ext>_chat` BYOLLM router in the manifest — `delete_folder`, `create_note`, etc. were invisible. The planner had to delegate to `tool_<ext>_chat` which made its own LLM call, and that LLM sometimes summarised the request instead of calling the typed function. Result: user said "delete X", Webbee responded "done", but X was still there. Federal-grade catastrophe.

v4.0.0 closes this by making every typed `@chat.function` visible in the manifest with full schema. Kernel reads `chain_callable=True` and issues the typed call directly. No LLM router in the dispatch path. No silent write failures.

Combined with the SDK 3.7.0 anti-hallucination guards (I-AH-1 FABRICATED_ID_SHAPE) and the kernel-side I-AH-2/3/4 + I-MAGIC-UX-1/2 invariants shipped 2026-05-01, this closes ~75% of recent hallucination/regression bug classes. Remaining 25% is classifier accuracy, narrator prose, external API failures, and user input ambiguity — separate workstreams.

### Migration

Imperal-owned extensions (`admin`, `automations`, `billing`, `developer`, `hello-world`, `sharelock-v2`) ship retrofitted in this release. Third-party extensions: their next Dev Portal publish runs against V14-V24. Existing deployed manifests continue to work at runtime via legacy compatibility (kernel infers `chain_callable` from `action_type` when the new field is missing).

## v3.7.0 — 2026-05-01 — Anti-Hallucination Federal Hardening: I-AH-1 fabricated message_id guard

### Added

- **I-AH-1 — `imperal_sdk.chat.guards.check_id_shape_fabrication`** rejects empirically observed fabricated `message_id` slug pattern `^[a-z][a-z0-9]*-[a-z][a-z0-9]*-\d+$` at the chat handler boundary. Closes Bug-1 from the prod chat anti-hallucination test 2026-05-01 02:25 UTC where the LLM emitted `message_id="webhostmost-outlook-1"` and `message_id="ivalik-gmail-4"` — slugs that do not exist in any provider's ID format. Real Outlook IDs are ~150-char base64; real Gmail IDs are 16-char hex.
- The guard returns a structured `error_code=FABRICATED_ID_SHAPE` envelope with an actionable hint instructing the LLM to call `inbox()`, `search()`, `folder()`, or the `mail_inbox_summary` skeleton first. The wire integration sits in `_execute_function` BEFORE Pydantic coercion so the LLM gets a specific self-correction signal.
- New error code `FABRICATED_ID_SHAPE` added to `imperal_sdk.chat.error_codes.ERROR_TAXONOMY` (10 codes total now). Kernel mirror at `imperal_kernel.narration.error_codes` updated in parallel — catalog sync invariant preserved.
- Coverage for `_ID_SHAPE_FIELDS = ("message_id", "thread_id", "email_id", "msg_id")` — all four exercised in `tests/test_id_shape_guard.py` (10 unit tests + 1 wire test in `tests/test_chat_guards.py`).

### Notes

I-AH-1 is one of six federal anti-hallucination invariants shipped on
2026-05-01 across SDK + kernel. The other five (I-AH-2 v2, I-AH-3,
I-AH-4, I-MAGIC-UX-1, I-MAGIC-UX-2) live in the kernel and don't
require an SDK release; together they form the full sprint package.
See workspace doc `imperal/webbee/docs/anti-hallucination-federal-hardening.md`
for the full federal record + kernel commits.

## v3.6.0 — 2026-05-01 — UEB Phase 1a: Manifest v2 + Event envelope EV6..EV8 + @ext.emits

First slice of Universal Event Bus (UEB). Closes Manifest Gap from
`contracts-roadmap.md` §2.1 by emitting five new declarative sections
in `imperal.json`. Adds the federal cross-namespace block at decoration
time and tightens manifest validation. **Backward-compat additive** —
v1 manifests continue to validate without change.

### New — Event envelope EV6..EV8

- `Event` Pydantic model (new in `types/contracts.py`) carries the v2
  UEB envelope: `type`, `scope`, `action`, `actor`, `tenant_id`,
  `user_id`, `timestamp`, `data` plus three new optional fields:
  - `event_id: str | None` (EV6) — UUIDv7 dedup key for SETNX
    idempotency
  - `schema_version: int | None` (EV7) — monotone, breaking-change
    marker. `Field(ge=1)` enforced
  - `source: Literal["user", "system", "automation", "rbac", "mcp",
    "webhook"] | None` (EV8) — AuditSource value
- `EventModel` (existing v1 Redis-streams contract) extended with the
  same EV6..EV8 fields as optional. Required because `get_event_schema()`
  derives the published JSON Schema from `EventModel`. The static
  `event.schema.json` carries the new properties verbatim.

### New — `@ext.emits` decorator

```python
@ext.emits("billing.topup_completed", schema_ref="#/schemas/topup")
async def credit(ctx, amount: int):
    ...
```

- Symmetric with `@ext.on_event` — declares an event the extension
  emits. Powers the manifest `events.emits[]` section so Registry,
  Marketplace, and Dev Portal can see emit declarations.
- Federal cross-namespace block fires at decoration time:
  `@ext.emits("notes.foo")` from an extension with `app_id="billing"`
  raises `ValueError` immediately — no namespace impersonation possible.
- Dotted-format guard: undotted event types raise `ValueError`.

### New — Manifest v2 (`manifest_schema_version: 2`)

`generate_manifest()` now emits five additional optional sections when
the corresponding decorators / declarations are present (sections are
omitted entirely when empty — clean v1 manifest preserved):

- **M6 `webhooks`** — from `@ext.webhook(path, method, secret_header)`
- **M7 `events`** — `subscribes` (from `@ext.on_event`) + `emits`
  (from `@ext.emits`)
- **M8 `exposed`** — from `@ext.expose(name, action_type)`
- **M9 `lifecycle`** — `on_install`/`on_uninstall`/`on_enable`/
  `on_disable` (from existing decorators) + `on_upgrade: [versions]`
  + `health_check.interval_sec`
- **M10 `tray`** — from `@ext.tray(tray_id, icon, tooltip)`

### Changed — `__`-dunder synthetic tools no longer leak into `tools[]`

The `@ext.webhook` / `@ext.tray` / `@ext.panel` / `@ext.widget`
decorators register synthetic `__webhook__path` / `__tray__id` /
`__panel__id` / `__widget__id` entries into `_tools` so
`DirectCallWorkflow` can dispatch them. Previously these synthetic
names leaked into the manifest `tools` list, producing M5 validation
failures (slashes / underscores not valid identifiers).

`generate_manifest()` now filters `name.startswith("__")` from both the
emitted `tools` list and `_collect_scopes()` accumulation. User-facing
manifest is clean; declarative sections (`webhooks`, `tray`, etc.)
carry the synthetic data instead.

### Changed — Static `imperal.schema.json` v2 with constraint enforcement

JSON Schema regenerated from updated Pydantic models, now carries:

- `manifest_schema_version: enum [1, 2]`
- `webhooks[].path: pattern ^/[a-z0-9_/-]+$`
- `webhooks[].method: enum [POST, GET, PUT, DELETE]`
- `exposed[].action_type: enum [read, write]`
- `tray[].tray_id: pattern ^[a-z][a-z0-9_-]+$`
- `lifecycle.health_check.interval_sec: minimum 30`
- `events.{subscribes,emits}[].type: minLength 1`
  (federal no-silent-drop)

### New — Semantic validators (M6.3 / M7.3 / M8.2)

`validate_manifest_dict` raises `ValueError` on three rules JSON
Schema cannot express:

- **M6.3** `webhooks[].path` uniqueness — duplicate webhook paths
  rejected
- **M7.3** `events.emits[].type` must be prefixed by `app_id + "."`
  (cross-namespace block, second line of defense after the decorator)
- **M8.2** `exposed[].name` uniqueness — duplicate exposed methods
  rejected

The Pydantic-error path continues to return `list[ValidationIssue]`
unchanged; only the new rules raise.

### Backward compat

- v1 manifests (no `manifest_schema_version`, no v2 sections) validate
  unchanged against the new static schema.
- All new fields and sections are optional with `default=None` /
  conditional emission.
- Existing `validate_manifest_dict(...) == []` round-trip assertions
  continue to pass for valid v1/v2 manifests.

### Bookkeeping

- 37 new tests covering envelope v2, decorator, manifest sections,
  schema constraints, and semantic validators.
- Federal feedback applied: `feedback_no_silent_drop_in_truthy_guards`
  (use `is not None` / `min_length=1` instead of truthy guards),
  `feedback_audit_chokepoint_no_bypasses` (cross-namespace enforced
  at decoration time), `feedback_sdk_upgrade_must_audit_all_venvs`
  (deploy script audits every site-packages install).

### Known follow-ups (post-Phase-1a)

- `manifest_schema.py` is 441 LOC, over the 300-line workspace rule;
  split into per-section sub-modules tracked for cleanup pass.
- UEB Phase 1b (kernel-side `audit/_streams.py` + `_consumer.py` +
  catalogue) lands separately.

## v3.5.2 — 2026-04-30 — Hotfix: federal determinism restored

### Fixed (latent bug)

- `LLMProvider._call_anthropic` had a guard `if temperature > 0:` that
  silently dropped explicit `temperature=0.0` from the kwargs sent to
  the Anthropic API. Anthropic's default is `1.0` (non-deterministic),
  so callers passing `0.0` for federal determinism were actually being
  served by a `1.0` temperature provider for an unknown duration.
- Fix: `if temperature is not None:` — explicit `0.0` now reaches the
  provider. `None` continues to be dropped (provider default applies).
- `_call_openai` was not affected — it uses
  `_openai_supports_custom_temperature(provider, model)` which is
  model-aware (filters reasoning models) and passes `temperature`
  unconditionally for non-reasoning models. OpenAI gpt-5/o-series still
  receive no `temperature` kwarg (filtered both at call site and via
  `_supported_params_for` in `cfg.api_kwargs()`).

## v3.5.1 — 2026-04-30 — LCU Phase 3: LLMConfig AI params + tool-use cap fix

### LLM config unification (LCU-7)

- `LLMConfig` extended with 6 admin-tunable AI param fields:
  `temperature`, `max_tokens`, `top_p`, `presence_penalty`,
  `frequency_penalty`, `stop_sequences`. All default to `None` ("no
  override; provider's own default applies"). Mirrors kernel-side LCU
  Phase 1 schema so kernel-built configs deserialize cleanly into SDK.
- New `LLMConfig.api_kwargs()` method returns provider-filtered kwargs
  via `_supported_params_for(provider, model)`. Drops unsupported fields
  (e.g. `presence_penalty` for Anthropic, all but `max_tokens` for
  OpenAI gpt-5/o-series reasoning models) silently — no more 400s when
  admin sets a slot the provider doesn't accept.
- `_call_anthropic` and `_call_openai` now apply `cfg.api_kwargs()` for
  the non-overlapping params (top_p, penalties, stop_sequences) so admin
  per-purpose / per-extension slots reach the upstream API. `max_tokens`
  and `temperature` continue to use caller-explicit precedence (TBC-FULL
  invariant from spec).

### Fixed

- `chat/handler.py:362` tool-use loop `max_tokens` no longer hardcoded
  to `2048`. Now reads from a federal-grade cascade:
  1. `cfg.max_tokens` (admin per-purpose / per-extension)
  2. `ctx.config.tool_use_max_tokens` (TBC-FULL slot, future)
  3. `ctx.config.max_response_tokens` (general response cap)
  4. `2048` (absolute backstop)

  Until LCU-7, the hardcoded `2048` silently capped admin's carefully-
  chosen TBC-FULL settings. With the cascade alive, admins can lift the
  cap per-extension or per-purpose without touching SDK code.

### Backward compat

- All new `LLMConfig` fields default to `None`. Existing call sites that
  build `LLMConfig` without the new kwargs continue to work unchanged.
- `api_kwargs()` returns `{}` for a freshly-default `LLMConfig`, so
  `_call_*` paths that loop over it become no-ops in the absence of
  admin overrides — pre-LCU behaviour.

## v3.5.0 — 2026-04-30

### Federal closure
- `ExtensionsClient.emit()` now routes through `imperal_kernel.audit.record_action`
  chokepoint instead of direct Redis pub/sub. Federal user_id propagation closed at SDK level.
- Every extension emit now produces an `action_ledger` row in addition to firing the
  Redis pub/sub event, enabling forensics on extension-emitted events.
- Backward compatible: emit signature unchanged; behavior is identical for callers
  except that audit rows are now created (federal-grade observability).

### Backward compat
- If `imperal_kernel.audit` is not importable (extension running outside kernel
  context, e.g., in unit tests), falls back to legacy direct Redis publish with
  log warning. No breaking change for extension developer ergonomics.

## 3.4.1 — 2026-04-29 — LLM-FU-2: gpt-5 / o-series temperature drop

### Fixed

- `LLMProvider._call_openai` now omits the `temperature` kwarg entirely
  for OpenAI reasoning models (`gpt-5`, `gpt-5-mini`, `gpt-5-nano`,
  `o1*`, `o3*`, `o4*`), letting OpenAI use its mandatory default of 1.0.
  Sending any custom value (including the kernel default `0.0`) raised
  400 `'temperature' does not support 0.0 with this model. Only the
  default (1) value is supported.`, which started flooding production
  logs once the 2026-04-29 admin LLM dropdown began routing chains
  through `gpt-5`. Every chain hitting the model failed over to
  `anthropic/haiku`. Mirror of the LLM-FU-1 `max_completion_tokens`
  rename — same prefix list, same gating shape.

### Added

- `imperal_sdk.runtime.llm_provider._openai_supports_custom_temperature(
  provider, model)` — returns `False` for OpenAI gpt-5 / o-series and
  `True` everywhere else. Reuses `_OPENAI_MCT_MODEL_PREFIXES` so the
  two helpers always agree on which models are reasoning models.

## 3.4.0 — 2026-04-29 — BREAKING: panel slot validation + `main` removal

### Breaking

- `@ext.panel(slot="main")` and `Panel(slot="main")` now raise `ValueError`
  at decoration / instantiation time. The `main` value was the SDK default
  but was never rendered as a middle panel by any host — the runtime
  middle-content slot has always been `"center"`. Use `slot="center"`.
- The default value of `slot` on `@ext.panel(...)` and `Panel(...)` is now
  `"center"` (was `"main"`). Extensions that omitted `slot=` now register
  in the centre slot instead of the dead `main` slot.
- Unknown slot values (typos, deprecated names, future placeholders) now
  raise `ValueError` instead of silently registering. Whitelist:
  `{center, left, right, overlay, bottom, chat-sidebar}`.

### Added

- `imperal_sdk.types.contributions.ALLOWED_PANEL_SLOTS` — public frozenset
  constant; single source of truth for the slot whitelist. Imported by
  the decorator, the dataclass `__post_init__`, and the validator.
- Validator rule `PANEL-SLOT-1` — AST check that flags
  `@ext.panel(slot=<unknown literal>)` at CI and Developer Portal upload
  time, before the extension imports.
- `docs/extension-ui.md` gains a "Panel slots" section with a 6-row table
  of valid slots, deprecation note for `main`, and a copy-paste
  master-detail layout snippet.

### Migration

If your extension declares `@ext.panel(..., slot="main")`, change it to
`slot="center"`. If you relied on the old default by omitting `slot=`,
audit whether you wanted the centre panel (most likely yes) or a sidebar
(in which case add `slot="left"` or `slot="right"` explicitly). All
in-tree Imperal extensions were already using explicit
`center`/`left`/`right` and require no migration.

## 3.3.1 — 2026-04-29 — LLM-FU-1: gpt-5 / o-series max_completion_tokens

### Fixed

- `LLMProvider._call_openai` now sends `max_completion_tokens` instead of
  the legacy `max_tokens` kwarg when the resolved config matches OpenAI
  reasoning models — `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `o1*`, `o3*`,
  `o4*`. OpenAI rejects `max_tokens` for these families with
  `'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.`,
  which surfaced after the 2026-04-29 admin LLM dropdown expansion added
  these models. Anthropic, Gemini (OpenAI-compat), and Ollama/vLLM
  (`openai_compatible`) keep `max_tokens` — sending the new kwarg to
  those providers is unsafe.
- Helper `_openai_uses_max_completion_tokens(provider, model)` gates the
  rename; matches by model-name prefix (`gpt-5`, `o1`, `o3`, `o4`)
  case-insensitively, scoped to `provider == "openai"` only.

### Tests

- `tests/test_openai_max_completion_tokens.py` — 24 parametrized cases
  covering reasoning models, legacy OpenAI, cross-provider safety, and
  edge cases (empty model, empty provider).

## 3.3.0 — 2026-04-28 — UI extensions + deprecation (Sprint 2)

### Deprecated

- `ChatExtension(model=...)` constructor parameter is now deprecated.
  Default changes from `"claude-haiku-4-5-20251001"` → `None`. When
  explicitly passed, emits a class-level WARN-once log:
  > `ChatExtension(tool_name=...): the model= parameter is deprecated
  > since SDK 3.3.0. LLM model resolution moved to kernel ctx-injection
  > (see ctx._llm_configs). Will be removed in SDK 4.0.0.`
- Backward compat preserved until SDK 4.0.0 — out-of-tree extensions
  passing `model=` continue to work; in-tree extensions cleaned of the
  parameter as part of this sprint.

### Federal

- `_model_deprecation_warned` flag is class-level (not instance-level)
  so 11 in-tree extensions don't each warn at boot during transition
  state. After they migrate, the warn fires only for external
  out-of-tree extensions until they update.
- Companion: Admin > LLM Config UI gains `chain_narrative_model` +
  `judge_model` Select rows (admin extension change shipped in
  `/opt/extensions` monorepo + 7 inner-git extensions per Developer
  Portal convention).
- Documentation: SDK docs `extension-guidelines.md` + `tools.md`
  ChatExtension examples updated to omit `model=`. External
  developers reading docs do not propagate the deprecated pattern.

## 3.2.0 — 2026-04-28 — Architectural cleanup (Sprint 1.2)

### Changed (BREAKING-internal — public API preserved with shim)

- **Single resolver:** kernel becomes the sole LLM-config resolver.
  SDK `LLMProvider` is now a thin executor consuming pre-resolved
  `LLMConfig` from `ctx._llm_configs[purpose]` (kernel
  `context_factory` populates this via setattr-post-build at
  ctx-build time).
- **`create_message` signature:** now accepts `cfg=LLMConfig`
  (preferred) OR legacy `purpose=`/`user_id=` (DEPRECATED, ENV-only
  fallback path with one-time WARN per process). Legacy form will
  be removed in SDK 4.0.0.

### Removed

- SDK provider's own resolution methods: `_load_config_store`,
  `_resolve`, `_resolve_byollm`, `_fetch_byollm_data`,
  `_build_byollm_config`, `_resolve_failover`,
  `_invalidation_listener`, `_ensure_listener`. Caches:
  `_byollm_cache`, `_config_cache`. ~200 LOC stripped.
- HTTP fetch from auth-gw `/v1/internal/config/llm` (Sprint 1.1
  bridge). Kernel resolves directly; SDK never touches gateway
  for LLM config now.

### Added

- `LLMConfig.failover_config: LLMConfig | None` — pre-resolved
  failover pair. `create_message` reads this for runtime retry on
  primary failure (replaces SDK's runtime `_resolve_failover`).
- `LLMConfig.api_key` is now `field(repr=False)` — never appears
  in default `__repr__`. Locks against accidental f-string leaks.
- `LLMConfig` field shape aligned with kernel: adds `thinking_mode`,
  `byollm_tool_choice` with safe defaults.
- `LLMProvider._env_default_config_for_purpose(purpose)` — used
  for standalone-SDK fallback when `ctx._llm_configs` is None
  (extension developer running outside kernel).

### Federal

- LLM usage telemetry RESTORED. Sprint 1.1 discovered
  `_track_usage` was silently broken via the same `shared_redis`
  ImportError; Sprint 1.1 no-op'd it. Sprint 1.2 routes usage via
  `ctx._llm_usage_callback`; kernel `_track_usage` (uses correct
  `imperal_kernel.core.redis` path) writes Redis. Closes
  `SP1.1-USAGE-TRACK`.
- BYOLLM lookup happens once at ctx-build (single auth-gw HTTP
  call per chain) instead of N (per LLM call).
- Federal customers without Redis can deploy SDK standalone with
  ENV-only fallback (no infrastructure dependencies in SDK).

### Compatibility matrix

| Combo | Status |
|---|---|
| New kernel + new SDK 3.2.0 | ✅ Primary path; ctx-injection works |
| New kernel + old SDK 3.1.1 | ✅ Old SDK ignores ctx._llm_configs; uses its own HTTP path. Functional but inefficient. |
| Old kernel + new SDK 3.2.0 | ⚠️ ctx._llm_configs is None → SDK ENV fallback. Production must redeploy in lockstep. |
| Standalone SDK (no kernel) | ✅ ENV-only |

## 3.1.1 — 2026-04-28 — HOTFIX

### Fixed
- `LLMProvider._load_config_store()` was silently failing with
  `ModuleNotFoundError: shared_redis` since the kernel refactor that
  renamed `shared_redis` → `imperal_kernel.core.redis`. The broad
  `except Exception` swallowed the import error at DEBUG level,
  causing every extension `purpose=execution` call to fall through to
  `_PROVIDER_DEFAULTS["anthropic"]["model"]` (claude-haiku) regardless
  of Admin > LLM Config setting.
- Replaced the Redis-import path with an HTTP fetch against the
  auth-gw's existing `GET /v1/internal/config/llm` endpoint.
  Symmetric with `_fetch_byollm_data` — same gateway URL + service
  token, same `httpx` client, same caching pattern. **Zero new SDK
  dependencies** (httpx already core).
- Per-instance warn-once flags for each failure class
  (`_config_store_warned_envmissing`, `_config_store_warned_status`,
  `_config_store_warned_shape`, `_config_store_warned_fetch`) prevent
  log-spam while preserving visibility on first occurrence.

### Federal
- All callers (extensions running inside kernel workers) now respect
  Admin > LLM Config provider/model + per-purpose + per-extension
  overrides. BYOLLM continues to take precedence (separate code
  path, unaffected).
- Federal customers without Redis still work — SDK no longer
  attempts a Redis connection of any kind.

### Discovered + temporarily disabled
- `LLMProvider._track_usage()` and `LLMProvider._invalidation_listener()`
  also imported the broken `shared_redis` module — telemetry and
  pubsub cache invalidation have been silently broken since the same
  kernel refactor. Both are now explicit no-ops with WARN-once on
  first call (telemetry) or silent no-op (listener; pubsub is OOS
  per spec §13, 60s TTL polling is the degraded mode).
- Tracked as Sprint 1.2 follow-up `SP1.1-USAGE-TRACK`. Sprint 1.2
  architectural cleanup will restore both via kernel-side resolution
  + ctx-injection (or via dedicated auth-gw endpoints).

## 3.1.0 — 2026-04-27

### Added
- New `imperal_sdk.rpc` sub-package: typed envelope contract for Fast-RPC
  between auth-gw and kernel via Redis Streams.
  - `RpcRequest`, `RpcReply` Pydantic v2 models, frozen, `extra="ignore"`.
  - `v: Literal[1]` envelope discriminator (discriminated-union ready).
  - `RpcStatus`, `RpcErrorCategory` enums; typed `RpcError`.
  - Pure codec: `encode_request/decode_request/encode_reply/decode_reply`
    with loose-mode missing-`v` shim + `strict_version` kwarg.
  - `build_error_reply` helper, `should_cache_reply` idempotency policy.

### Backward compatibility
- Additive only; no SDK 3.0.x callers affected.
- Required runtime env on consumers: `IMPERAL_RPC_STRICT_VERSION` (default
  unset = loose mode = accept missing `v`); flip to `true` after the W2 D1
  soak window (≥24h with `legacy_envelope_total = 0`).

## 3.0.0 — 2026-04-27

**Breaking — Identity Contract Unification (W1)**

Single source of truth for `User` / `Tenant` shapes now lives in
`imperal_sdk.types.identity`. The legacy `imperal_sdk.auth.user.User`
dataclass has been **deleted**. AuthGW's `UserResponse` / `TenantResponse`
now subclass the canonical SDK types so wire shape is identical
everywhere. Federal-strict `extra="forbid"` blocks accidental field
leakage (e.g. `password_hash`).

### Migrating

1. **Replace legacy import:**
   ```python
   # Before (v2.x):
   from imperal_sdk.auth.user import User
   # After (v3.0.0):
   from imperal_sdk.types.identity import User          # full — admin/API surface
   from imperal_sdk.types.identity import UserContext   # lean — what `ctx.user` is
   ```
2. **Rename `.id` → `.imperal_id` on user objects:**
   ```python
   # Before:
   uid = ctx.user.id
   # After:
   uid = ctx.user.imperal_id
   ```
3. **Pin SDK in your extension's `requirements.txt`:**
   ```
   imperal-sdk>=3.0.0,<4.0.0
   ```

### What's new

- **`imperal_sdk.types.identity`** module — four canonical Pydantic v2
  models, all `frozen=True` + `extra="forbid"`:
  - `User` — full (admin/API). Fields: `imperal_id`, `email`, `tenant_id`,
    `agency_id`, `org_id`, `role`, `auth_method`, `scopes`, `attributes`,
    `is_active`, `created_at`, `last_login`, `cases_user_id`.
  - `UserContext` — lean (runtime, what `ctx.user` is). Strict subset of
    `User` minus `auth_method` / `created_at` / `last_login` /
    `cases_user_id`.
  - `Tenant` — full. Fields: `id`, `tenant_id`, `name`, `db_backend`,
    `isolation`, `allowed_auth_methods`, `max_connections`, `features`,
    `is_active`, `created_at`, `updated_at`, `parent_tenant_id`,
    `can_resell`, `custom_pricing`, `ui_config`.
  - `TenantContext` — lean (runtime, what `ctx.tenant` is). Subset:
    `tenant_id`, `name`, `is_active`, `features`, `isolation`.
- **`has_scope(scope)` / `has_role(role)` helpers** preserved on both
  `User` and `UserContext`. `has_scope` uses dot-notation —
  `user.has_scope("cases.read")` returns `True` if user has `"cases.*"`.
- **Import-time invariant** — `set(UserContext.fields) ⊆ set(User.fields)`
  (and same for Tenant). Module raises `RuntimeError` on import if
  someone adds a lean-only field. Federal: drift caught at deploy time.
- **Drift validator** — `python -m imperal_sdk.tools.validate_identity_contract
  --authgw-path=<auth-gw app dir>` parses auth-gw SQLAlchemy `Mapped[...]`
  columns and asserts they match the SDK Pydantic fields (excluding
  documented allowlist: `User.id`, `User.password_hash`,
  `Tenant.db_config`). Used by the auth-gw pre-commit hook + GitHub
  Actions CI gate + hourly SigNoz sweeper.

### Removed

- `imperal_sdk.auth.user.User` dataclass — superseded by
  `imperal_sdk.types.identity.User`. The `auth/user.py` file no longer
  exists in the package; `from imperal_sdk.auth.user import User`
  raises `ModuleNotFoundError` on v3.0.0.
- `User.id` attribute — renamed to `User.imperal_id` to match the
  canonical wire field name.

### Federal posture

`extra="forbid"` on all four models means any unexpected field on a
response (e.g. `password_hash` accidentally serialized) fails Pydantic
validation BEFORE leaving the auth-gw process. This is the desired
deny-over-leak posture for CJIS/FedRAMP-high tenants.

### Drift CI gate

Two enforcement layers were added:
1. **Pre-commit hook** in `imperal-auth-gateway` (`.pre-commit-config.yaml`)
   — runs the validator on every commit touching `app/models/*.py`.
2. **GitHub Actions workflow** in `imperal-sdk` (`.github/workflows/identity-contract.yml`)
   — runs on every push/PR; blocks merge on drift.

### Runtime sweeper

`signoz:/opt/imperal-monitoring/tools/sweep_identity_contract.py`
runs hourly via `sweep-identity-contract.timer`, emits
`imperal_identity_contract_drift_count` gauge to journald → SigNoz.

---

## 2.0.1 — 2026-04-25

### Strategy note

This release **supersedes 2.0.0 without yanking it**. v2.0.0 shipped the
Webbee Single Voice cutover (deleted `ChatExtension` class, required
`@sdk_ext.tool` + Pydantic `output_schema`, removed `_system_prompt`).
That cutover was rolled back same-day; production continued on v1
ChatExtension architecture. v2.0.1 restores the v1 contract on top of
v1.6.2 baseline + two production hotfixes from the 2026-04-25 ICNLI
Action Authority marathon. Anyone installing `imperal-sdk` without a
pin will now resolve to 2.0.1 and get the working v1 architecture; the
2.0.0 wheel remains on PyPI as historical record (see GitHub tag
`archive/v2.0.0-2026-04-25` for source).

For incremental Webbee Single Voice re-roll see `release/v2.0.0` archive
tag and the kernel `feature/webbee-single-voice` branch.

### Architecture

- **Restored:** `ChatExtension` class, `@chat.function` decorator,
  `ActionResult.success/.error`, per-extension `system_prompt.txt`,
  v1.6.0+ `@ext.skeleton` decorator, `ctx.cache`, HMAC call-token,
  Narration Verifier (audit + narrative modes).
- **Removed (relative to 2.0.0):** v2 `Extension`-as-base-class with
  `@sdk_ext.tool` methods, mandatory `output_schema`, V14 validator
  rejecting v1 patterns.
- **Validators V1-V13** active. V14 (no-ChatExtension) inactive on this
  release.

### Fixed

- **`chat/guards.py` destructive ESCALATE (I-CHATEXT-DESTRUCTIVE-ESCALATE)**
  — when classifier returns `intent=read action=read` but extension LLM
  picks a destructive tool, we now `ESCALATE` (mirror existing write
  ESCALATE) so the kernel-side confirmation_gate becomes the federal
  authority on 2-step. The previous `BLOCK` path produced a prose-loop
  ("ARE YOU SURE?" repeated forever) because the LLM kept re-asking
  without ever reaching the confirmation gate. Production observation
  2026-04-25, repro: "удали 1 любую заметку".

- **`core/intent.action_plan.args` JSON-encoded string**
  (I-ACTION-PLAN-ARGS-JSON-STRING) — OpenAI strict mode rejects
  `type=["object","null"]` without `additionalProperties=false` on every
  nested object. Free-form dicts cannot satisfy the constraint at
  schema-build time, so `args` is now a JSON-encoded string and the
  kernel parses with `json.loads`. Fresh installs of imperal-sdk into
  any tenant using OpenAI strict-mode classifier no longer hard-fail at
  classifier emit.

### Compatibility

- **API surface** same as 1.6.2. Existing extensions running on 1.6.2
  upgrade to 2.0.1 by changing only their pin (`imperal-sdk==1.6.2` →
  `imperal-sdk==2.0.1` or `>=2.0.1,<3.0.0`).
- **Extensions on 2.0.0** (Single Voice contract — V14 enforced) WILL
  NOT load on 2.0.1. Roll those extensions back to v1 contract or pin
  `imperal-sdk==2.0.0` explicitly. The architecture revert is the
  intentional content of this release.

## 1.6.2 — 2026-04-24

### Fixed

- **`chat/prompt.py` tool-catalog framing (I-CHATEXT-TOOL-CATALOG-FRAMING)** —
  v1.6.1 identity header/footer was not enough to overcome strong identity
  framing in extensions' `system_prompt` (e.g. "Mail Client module — …",
  "Sharelock Intelligence module — …"). At ~2000 tokens of identity-framed
  documentation vs 150 tokens of `IDENTITY (NON-NEGOTIABLE)`, LLM attention
  still answered "I'm the X module" when asked "who are you".
  Structural fix: wrap the extension's `base_prompt` in an explicit
  `<TOOL_CATALOG:app_id>` container with neutralizing preamble ("this is
  REFERENCE DOCUMENTATION describing what you can DO, not WHO YOU ARE")
  and closing tag. The extension's prompt is no longer read as persona —
  it becomes tool documentation. Language-agnostic, convention-based,
  works for every extension regardless of authoring style. No regex,
  no per-extension hardcoded patterns.

## 1.6.1 — 2026-04-24

### Fixed

- **`chat/prompt.py` identity override order (I-CHATEXT-IDENTITY-OVERRIDE-ORDER)** —
  federal-grade identity leak fix. When a user asked "who are you", Webbee
  could reply "I'm the mail module" because the extension's `base_prompt`
  (e.g. "Mail Client module — …") framed the agent as an extension and
  LLMs weight early-prompt text heavily.
  - Key mapping: `_capability_boundary` now reads `identity` (v1.6.0 kernel)
    with fallback to `assistant_name` (pre-v1.6.0 SDK tests). The v1.6.0
    kernel shipped `identity` but the SDK read `assistant_name` only,
    silently falling back to the hardcoded `"Webbee"` default.
  - `not_identify_as`: the kernel's `app_id`-scoped negative-identity hint
    is now rendered into an explicit clause — "You are NOT the 'X' module,
    extension, app, or assistant". Previously populated by the kernel but
    never consumed on the SDK side.
  - Prompt order: identity header is PREPENDED before the extension's
    `base_prompt` (frames first read) AND a final identity rule is
    APPENDED after all other augments (late-text attention weighting
    overrides any extension persona drift). Identity brackets `base_prompt`
    instead of sitting in the middle.

## 1.6.0 — 2026-04-24

### BREAKING CHANGES

- `ctx.skeleton.update()` method removed. `SkeletonProtocol` is read-only.
  Kernel skeleton_save_section activity is sole writer. (I-SKELETON-PROTOCOL-READ-ONLY)
- `ctx.skeleton_data` attribute removed from Context. Skeleton tools must call
  `await ctx.skeleton.get(section)` explicitly to diff against previous state.
  (I-NO-CTX-SKELETON-DATA)
- `ctx.skeleton` access from `@ext.panel`, `@ext.tool`, `@chat.function`
  contexts raises `SkeletonAccessForbidden`. Only `@ext.skeleton` tools may
  access skeleton. (I-SKELETON-LLM-ONLY)
- Non-skeleton tools no longer receive skeleton snapshot in kernel dispatch
  args. (I-KERNEL-EMPTY-SKELETON-ARG)
- Auth GW `/v1/internal/skeleton` PUT endpoint removed; GET requires
  `Authorization: ImperalCallToken <HMAC-SHA256>` header with tool_type="skeleton"
  scope.

### NEW

- `ctx.cache` — Pydantic-typed runtime cache with TTL 5-300s, 64 KB value cap,
  per-extension namespace. Register models via `@<ext>.cache_model("name")`.
  Backed by Auth GW `/v1/internal/extcache/{app_id}/{user_id}/{model}/{hash}`
  with HMAC call-token + Pydantic Field(ge=5, le=300) enforcement.
- `Extension.cache_model(name)` — decorator method for registering cache value
  shapes per extension instance (no global module state).
- HMAC call-token authentication for `/v1/internal/skeleton` and
  `/v1/internal/extcache`. Kernel mints per-call; Auth GW verifies with shared
  `IMPERAL_CALL_TOKEN_HMAC_SECRET` + jti replay protection via Redis SETNX.
- Validator rules: SKEL-GUARD-1/2/3, CACHE-MODEL-1, CACHE-TTL-1,
  MANIFEST-SKELETON-1, SDK-VERSION-1.
- `SkeletonAccessForbidden(PermissionError)` exposed via `imperal_sdk.errors`.

### MIGRATION

External
extensions must migrate their own code — kernel v1.6.0 deploy breaks
`ctx.skeleton_data` / `ctx.skeleton.update()` / cross-context `ctx.skeleton.get()`
users.

## 1.5.27 — 2026-04-24

Packaging-only release. Bundles the P2 Task 20 hotfix that was applied
to production site-packages on 2026-04-23 but never committed to git or
published to PyPI. Without this release, any `pip install
--force-reinstall imperal-sdk` on a worker venv silently reintroduces
the `FunctionCall.to_dict()` AttributeError.

### Fix

- **fix(chat/types): `FunctionCall.to_dict()` defensive dispatch.**
  The 1.5.26 structured error taxonomy (Task 19) causes
  `_execute_function`'s exception path to store a plain `dict` in
  `FunctionCall.result` (error_code envelope), not an `ActionResult`.
  Pre-fix, `to_dict()` unconditionally called `self.result.to_dict()`,
  raising `AttributeError: 'dict' object has no attribute 'to_dict'`
  and crashing the Temporal activity whenever an extension tool raised.
  Now dispatches on `hasattr(result, 'to_dict')` → ActionResult path,
  `isinstance(result, dict)` → passthrough, else `{'repr': str(x)[:500]}`
  fallback. Never raises on serialisation.

### Affected path

Any chain step where an `@chat.function` tool raised an exception: the
structured error envelope now serialises cleanly, the kernel 5-gate
verifier receives the classified `error_code`, the user sees the i18n
message from the error taxonomy instead of a generic chain failure.

Commits: working-tree diff on top of `2b3a837`.

## 1.5.26 — 2026-04-23

### Features

- **feat(chat/narration): `EMIT_NARRATION_TOOL` schema + `NarrationEmission`
  Pydantic parser.** New structural tool the kernel injects into every
  ChatExtension turn; replaces soft-rule narration_guard postamble (kept
  as belt-and-suspenders). Every claim is now verified against
  `_functions_called` by the kernel's 5-gate verifier (I-NARRATION-VERIFIED).
- **feat(chat/error_codes): structured error taxonomy.** 9 codes mapped to
  i18n keys; replaces raw `str(e)` content in tool_results. Closes P0-4
  (error string bleeding into user-visible write args). SDK + kernel
  carry identical catalogs (drift-guarded).
- **feat(chat/handler): three bundled changes:** structured error_code in
  `_execute_function` exception handlers (Task 20); `EMIT_NARRATION_TOOL`
  wiring into tool schema + terminal branch in the tool-use loop
  (Task 27); fresh-fetch round-0 `tool_choice` enforcement from
  `ctx.skeleton._fresh_fetch_required` (Task 32, closes P1-7).
- **feat(chat/guards): `check_write_arg_bleed` pre-dispatch guard.**
  Belt-and-suspenders layer on top of structured error codes: rejects
  write/destructive tool calls whose args contain any ERROR_TAXONOMY
  substring. I-WRITE-ARG-NO-BLEED. Case-insensitive, nested-value coverage.

### Invariants introduced (wire-contract with kernel)

- I-NARRATION-TOOL-SHAPE-1 — EMIT_NARRATION_TOOL schema frozen
- I-NARRATION-STATUS-ENUM-1 — status enum `{success, error, intercepted}` shared with kernel `_functions_called[*].status`
- I-NARRATION-FROZEN-1 — `NarrationEmission` immutable post-parse
- I-WRITE-ARG-NO-BLEED — write args scanned for ERROR_TAXONOMY substrings pre-dispatch

### Tests

9 new tests in `test_handler_p2.py` (structured errors + emit_narration wire + fresh-fetch) + 11 in `test_narration_emission.py` + 7 in `test_error_codes.py` + 12 in `test_write_arg_bleed.py` = **39 new tests, all green**.

Commits: `e130426` `762af72` `abfe937` `a78d429` (rebased onto origin/main 265f201 from pre-P2 baseline d5ca155).

## 1.5.25 — 2026-04-22

### Refactor

- **`Document` dataclass dedup.** Consolidated
  `imperal_sdk.store.client.Document` (which previously declared its own
  local copy) and `imperal_sdk.types.models.Document` into a single
  canonical class in `imperal_sdk.types.models`. The canonical class now
  includes every field (`id`, `collection`, `data`, `extension_id`,
  `tenant_id`, `created_at`, `updated_at`, `user_id`) and the helper
  methods (`__getitem__`, `get`) that previously lived only on the
  `store.client` variant. Both `imperal_sdk.Document` and
  `imperal_sdk.store.client.Document` now resolve to the same class,
  verified by contract test `tests/test_document_contract.py`.

### Backward compatibility

- `user_id`, `created_at`, `updated_at` defaults are now `""` on the
  `store.client.Document` path (previously `None`). Wire contract now
  matches `DocumentModel` Pydantic (which already used `""` defaults).
  All `StoreClient` methods coerce `None` responses from the Auth
  Gateway to `""` via `r.get("created_at") or ""`, so the only caller
  impact is code that explicitly checked
  `if doc.created_at is None: ...` — change to
  `if not doc.created_at: ...`.

### Docs

- Narration guardrail documentation added in `docs/` (Rule 21 in
  `extension-guidelines.md`, `tools.md` guardrail subsection,
  `quickstart.md` callout, `concepts.md` integrity protocol section).
  Committed post-1.5.24 (`4d76cb8`) and included in this release.

### Internal

- New regression test `tests/test_document_contract.py` asserts:
  (a) dataclass field set is a subset of the `DocumentModel` Pydantic
  field set, (b) dataclass → `asdict` → `DocumentModel.model_validate`
  roundtrips cleanly, (c) `store.client.Document is types.models.Document`
  identity, (d) top-level `imperal_sdk.Document` re-export identity,
  (e) helper methods `__getitem__` and `get` work, (f) default values
  match the Pydantic contract.

## 1.5.24 — 2026-04-22

### Security / Integrity: strict narration anti-fabrication postamble

Every ChatExtension narration LLM call now carries a **language-agnostic
system-prompt postamble** that binds the model's final prose to the
structurally-true `_functions_called` list. The rule is stated in plain
language, works for any human language (English, Russian, Ukrainian,
Turkish, Hebrew, German, Chinese, Arabic, …), and does NOT rely on
regex / vocabulary / post-hoc detection.

This closes a federal-compliance gap where the final narration round
could fabricate operations that never ran (e.g. claiming "I archived
3 emails" when only `mail.list` executed). The prior detection-based
approach (kernel commit `d66db64`, `truth_gate.py` regex) has been
**reverted** in favor of this preventive fix at source.

**New module:** `imperal_sdk.chat.narration_guard`

- `STRICT_NARRATION_POSTAMBLE` — the frozen rule text with a
  `{functions_called_summary}` slot.
- `format_functions_called_summary(fc_list)` — render
  `_functions_called` as a bulleted summary with SUCCESS / ERROR /
  CONFIRM_REQUIRED status per call plus totals line.
- `augment_system_with_narration_rule(system, fc_list)` — appends the
  postamble to any system prompt, substituting the current snapshot.

**Wiring** (`imperal_sdk.chat.handler`):

- The main tool-use loop call (final narration round) now passes the
  augmented system prompt on every round, so whenever the LLM decides
  no more tools are needed the concluding prose is bound to truth.
- `_build_factual_response` (post-write summary) also augments.

**Invariants**

- **I-NARRATION-STRICT-1**: every narration LLM call in the SDK routes
  through `augment_system_with_narration_rule`. No direct
  `system=`-only call is allowed in the narration path.
- **I-NARRATION-STRICT-2**: the postamble text is frozen and identical
  in every language — it describes the rule rather than parroting
  phrasing back.

### Tests

- `tests/test_narration_guard.py` — 16 tests covering postamble shape,
  summary format (success / error / intercepted / mixed / empty),
  augmentation behaviour (empty prompt, None fc, slot substitution).

## 1.5.23 — 2026-04-22

### Added
- `ctx.store.list_users(collection=None)` — system-context AsyncIterator for user-iteration (GAP-A closure)
- `ctx.store.query_all(collection)` — bulk Documents in single HTTP call for system-context fan-out
- `ctx.as_user(user_id)` — scoped Context primitive for per-user work inside system handlers
- Shared contracts module `imperal_sdk.types.store_contracts` — drift-proofed via JSON Schema snapshot
- SDK tools module: `imperal_sdk.tools.generate_api_surface` — emits public API surface for docs-vs-api linter
- `Document.user_id: str | None = None` — optional field populated by `query_all`
- `StoreUnavailable` and `StoreContractError` exceptions

### Fixed
- GAP-A root cause: `ctx.store.query()` in system-context silently returned empty because `StoreClient.user_id` was frozen to `"__system__"`. The new `list_users` + `as_user` pair enables proper fan-out.
- `imperal_kernel/services/ext_scheduler.py:24` phantom reference to non-existent `list_users` method

### Internal
- Kernel migrations: 4 direct-httpx bypasses in `activities/kernel_resolve.py`, `services/event_poller/accounts.py`, `llm/provider.py` migrated to SDK `StoreClient` surface (I-KERNEL-NO-DIRECT-HTTPX-STORE-1)
- Text-linter `docs-vs-api` shipped in kernel with fixture-based self-tests + baseline CI gate (I-DOCS-VS-API-1..3)
- Doctest CI integration (I-DOCTEST-SDK-1)
- Web-tools `wt_monitor_runner` migrated to list_users+as_user fan-out (was silently broken)

## 1.5.22 — 2026-04-22

### New: `@ext.skeleton` decorator + V13 validator rule

Sugar over `@ext.tool` that applies the platform's skeleton-refresh naming
convention automatically. Extensions shipping a `skeleton_refresh_<X>` tool
(or using the new decorator) are auto-wired into the kernel's skeleton
workflow — no Registry `skeleton_sections` row required. Pairs with the
2026-04-22 kernel-side release (`I-SKEL-AUTO-DERIVE-1`,
`I-SKEL-SUMMARY-VALUES-1`, `I-SKEL-LIVE-INVALIDATE`, `I-PURGE-SKELETON-SCOPE`).

**`extension.py` — new `skeleton()` method:**

```python
@ext.skeleton("monitors", alert=True, ttl=60)
async def refresh_monitors(ctx) -> dict:
    items = await ctx.store.query("wt_monitors", where={"owner_id": ctx.user.imperal_id})
    return {"response": {
        "total":    len(items.data),
        "critical": sum(1 for m in items.data if m.data.get("status") == "critical"),
        "warning":  sum(1 for m in items.data if m.data.get("status") == "warning"),
        "ok":       sum(1 for m in items.data if m.data.get("status") == "ok"),
    }}
```

- Registers the function as `skeleton_refresh_<section_name>` under the hood.
- `alert=True` hints that a sibling `skeleton_alert_<section_name>` tool
  exists — declare it with `@ext.tool` if you want change alerts.
- `ttl=300` is a hint; authoritative TTL lives in Registry (or the kernel's
  auto-derive default of 300 s).
- Rejects `*`, `?`, `[`, `]`, `:`, `/` in `section_name` — these would
  break the Redis key path `imperal:skeleton:{app}:{user}:{section}` and
  are rejected by the kernel-side purge helper defence-in-depth.
- Metadata (`section_name`, `alert_on_change`, `ttl`) is stashed on the
  registered `ToolDef` via `_skeleton` for platform tooling to read.

**`validator.py` — new V13 rule:**

Warns when a tool is named `refresh_<X>` without the `skeleton_refresh_`
prefix (won't be auto-wired by kernel). Informational issue when a tool
is named `alert_<X>` without `skeleton_alert_` prefix.

**`docs/skeleton.md`** — rewritten "Skeleton Refresh Tools" section
covering naming convention, `@ext.skeleton` vs bare `@ext.tool`, scalar-
field envelope best practices, idempotency, live-invalidate contract
on enable/disable (< 2 s propagation), federal-grade purge safety
(chat history unreachable by construction).

**Tests:** `tests/test_skeleton_decorator.py` — 11 cases covering
registration, metadata exposure, TTL defaults, function-preservation,
empty-section rejection, wildcard rejection, multi-section coexistence,
V13 warnings fire correctly for bare `refresh_*`/`alert_*` names, V13
silent when convention followed, version bump sanity.

No breaking changes. Existing `@ext.tool("skeleton_refresh_*")` registrations
continue to work; they now also satisfy V13 (no warnings).

## 1.5.21 — 2026-04-21

- **fix(chat/guards): escalate read→write, keep BLOCK for destructive.**
  When the extension LLM confidently picks a write tool under a turn
  classified as read, promote `ctx._intent_type` to "write" and proceed
  rather than BLOCK. LLM tool choice is authoritative over the classifier's
  heuristic. Destructive actions retain the BLOCK path — they require
  explicit user intent. Closes session-42 bug #2.

  Invariant: **I-GUARDS-ESCALATE-WRITE-ONLY** — see
  `docs/imperal-cloud/conventions.md`.

## 1.5.20 (2026-04-21)

### Chore: single-source-of-truth for version

Split-brain bug in 1.5.19: `pyproject.toml` was bumped to `1.5.19` but
`src/imperal_sdk/__init__.py::__version__` was still `"1.5.18"`. The wheel
metadata on PyPI was correct (1.5.19 tag, 1.5.19 filename) but
`imperal_sdk.__version__` at runtime reported `"1.5.18"`, confusing any
code that uses the attribute for logging / tagging / compat checks.

Root cause: two independent version declarations. Fix: switch to
**hatch dynamic version** — `pyproject.toml` declares
`dynamic = ["version"]` and `[tool.hatch.version]` points at
`src/imperal_sdk/__init__.py`. Now the `__version__` constant in
`__init__.py` is the **single source of truth**; building the wheel
derives metadata from it, and the runtime attribute always matches.

Also bumps `__version__` to `1.5.20` for this release.

No code / API changes from 1.5.19 otherwise — all the BYOLLM
hardening from 1.5.19 (`reasoning_effort="none"`, 300s httpx timeout,
I-BYOLLM-PARTIAL-RECOVERY) ships unchanged.

### Recommended action

Anyone on 1.5.19 should upgrade to 1.5.20 — the runtime version
attribute is now accurate:

```bash
pip install --force-reinstall --no-deps imperal-sdk==1.5.20
```

---

## 1.5.19 (2026-04-21)

### Fix: Ollama / openai_compatible BYOLLM hardening (session 41 PM)

Three SDK-side fixes landed after a live smoke against dorif's DGX Spark
deployment (Ollama behind HAProxy-EU, `qwen3:14b-fast` and `qwen3.5:27b`).
All three are **scoped to `cfg.provider == "openai_compatible"`** — real
OpenAI / Anthropic client stacks are untouched.

**`runtime/llm_provider.py::_call_openai` — add `reasoning_effort: "none"`
to `extra_body` for openai_compatible** when `thinking_mode != "on"`:

Ollama ignores the native `think: false` parameter on the OpenAI-compatible
`/v1/chat/completions` endpoint (tracked as `ollama/ollama#14820`).
`reasoning_effort` is the OpenAI-standard parameter Ollama ≥ 0.6 honours on
that endpoint. Without it, reasoning-enabled models (qwen3.*, Nemotron,
reasoning phi4, etc.) burn `max_tokens` on the reasoning trace and return
`content=""` — breaking downstream structured_gen and ChatExtension
tool-use loops. Measured 2.9s → 0.7s latency with `content` populated
against a live qwen3:14b-fast deployment.

```python
if cfg.provider == "openai_compatible":
    _extra_body = {"think": _think_val}
    if not _think_val:
        _extra_body["reasoning_effort"] = "none"
    kwargs["extra_body"] = _extra_body
```

**`runtime/llm_provider.py::_create_client` — explicit
`httpx.Timeout(300.0, connect=10.0)` on `AsyncOpenAI`** for openai_compatible:

The default transport's per-read idle threshold (~30s) was causing false
`Connection error` retries on multi-round tool-use loops against heavy local
models (27B+ on DGX-class hardware) whose token cadence exceeds those
thresholds. 300s aligns with the kernel's `_TOOL_TIMEOUT` and
`haproxy timeout server 300s` — end-to-end timeout budget is now consistent
across all layers. Real OpenAI / Anthropic clients keep library defaults.

**`chat/handler.py` — preserve successfully-executed tool calls when the
final narration round raises (I-BYOLLM-PARTIAL-RECOVERY)**:

Previously, if round-1/2 tool calls succeeded (inbox / search / etc.) but
the final narration round raised (Connection error, RemoteProtocolError —
common with heavy local models dropping TCP on big contexts), the exception
handler returned `ChatResult(..., handled=False)` and the kernel emitted
`"No extension handled this request"` — **discarding the already-completed
tool results**. That was a silent data-loss UX.

New behaviour: the handler inspects `_functions_called` for successful
non-intercepted entries. If present, returns `handled=True` with an honest
partial-result message naming the tools that did run:

> I ran inbox, search and collected your data, but the model hit a
> Connection issue while formatting the final reply. Retry in a moment
> if you want the full narrative.

The kernel then records the turn as handled and the user sees what was
actually done instead of a generic refusal. Pure-error path (no successful
tool calls) preserves the old `handled=False` behaviour — we don't paper
over genuine errors.

### Zero contract change for extension authors

`ctx._intent_type` read surface unchanged. `emit_refusal` tool unchanged.
All three fixes are internal to the SDK runtime / chat handler layer;
existing extensions get the hardening for free on upgrade.

### Platform-side cross-references

- Kernel-side spec: `docs/imperal-cloud/intent-classifier.md` (WebHostMost
  platform docs, not shipped with this repo)
- BYOLLM operational guide: `docs/imperal-cloud/byollm-operational-guide.md`
- Kernel-side mirror commits: `d5d1fd8` (reasoning_effort), `e888ef4` (httpx
  timeout) in `imperal_kernel/llm/provider.py`
- Related invariants (enforced at review): I-REASONING-EFFORT-NONE,
  I-HTTPX-TIMEOUT-300S-OPENAI-COMPAT, I-BYOLLM-PARTIAL-RECOVERY
- Ollama docs: <https://docs.ollama.com/capabilities/thinking>
- Ollama reasoning_effort tracker: <https://github.com/ollama/ollama/issues/14820>

---

## 1.5.18 (2026-04-21)

### New: ICNLI v7 TASK-11 — SessionMemory slice reader + emit_refusal primitive

Two related v7 features that close the extension-consumer side of the TASK-11 design. Kernel-side injection was already in production (`imperal_kernel/pipeline/extension_runner.py:362` pushes `_session_memory_slice` into each extension's skeleton); v1.5.18 adds the SDK side that reads it + a new refusal primitive.

**`chat/extension.py` — SM slice reader:**

In `ChatExtension._handle`, before dispatching to `handle_message`, the SDK now propagates the kernel-injected `_session_memory_slice` from `ctx.skeleton` to `ctx.session_memory_slice` as a typed attribute. Extensions opting into cross-turn awareness can consume:

```python
async def my_tool(ctx, ...):
    sm = getattr(ctx, "session_memory_slice", None) or {}
    history = sm.get("history_for_this_app", "")
    cross_ext = sm.get("cross_ext_summary", "")
    # Feed either into the extension's internal LLM prompt if it runs one
```

Shape (populated by kernel):
- `history_for_this_app`: str — last ≤5 turns' tool-call summaries for THIS extension (`fn_name (ok/failed) — data_summary[:100]`)
- `cross_ext_summary`: str — last ≤3 turns' cross-extension summary

Falls back silently (no `session_memory_slice` attribute) when kernel has not injected it — backward compatible with pre-v7 kernels.

**`chat/refusal.py` — `emit_refusal` primitive (NEW module):**

Structured tool an extension's internal LLM can emit when it decides it cannot complete the user's request. Kernel receives a typed `Refusal` (preferred over the historical free-text "в этом режиме ты не можешь..." pattern) and renders it via a dedicated Panel template. Exported surface:

```python
from imperal_sdk.chat.refusal import EMIT_REFUSAL_TOOL, RefusalEmission, parse_refusal_tool_use

# EMIT_REFUSAL_TOOL — Anthropic tool_use spec dict. Register alongside your
# extension's real tools when constructing the tool list for the LLM turn.
# Required inputs: reason (enum: no_scope | missing_params | out_of_policy
# | upstream_error | other), user_message (str). Optional: next_steps
# (list[str]).

# parse_refusal_tool_use(tool_input_dict) -> RefusalEmission
# Frozen dataclass — safe to pass to kernel delivery layer.
```

Feature is opt-in at the extension level; kernel handles emitted refusals when the extension returns them in tool_use. No refactor required for extensions that don't surface refusals.

### Minimal tests
- `tests/test_v7_emit_refusal.py` — schema shape + parse round-trip (2 tests).
- Integration coverage deferred — no extension consumes `emit_refusal` yet. See cross-ref below.

### Cross-reference
- Kernel side (already prod): `imperal_kernel/pipeline/extension_runner.py:362`
- Design / rationale: `docs/imperal-cloud/icnli-v7-architecture.md`
- WIP preservation history: branch `feat/icnli-v7-task11-sm-slice` (commit `dfebe07`, session 40 preservation)

---

## 1.5.17 (2026-04-21)

### New: Markdown rendering hygiene (Layer 1 prompt + Layer 2 normalizer)

Webbee responses occasionally rendered `** Рекомендации**` (literal asterisks) instead of bold. CommonMark requires emphasis runs to have no leading/trailing whitespace inside `**` delimiters; LLMs occasionally emit `** text **` which breaks the Panel renderer. Two-layer fix:

**Layer 1 — `imperal_sdk/prompts/kernel_formatting_rule.txt` rewrite:**

The kernel-injected formatting prompt is replaced with an explicit **DO** / **NEVER** example table. DO: bold label-value pairs, `|`-separated tables with `|---|` header rows, numbered lists with literal `.` after the number, `##` for major sections, inline `**text**` for sub-headers, `---` for major separators, backticks for IDs / emails / IPs / URLs. NEVER: `** text **` (whitespace inside markers), columns separated by spaces (not a table), `1 item` (missing dot), ALLCAPS without header, `*** text ***`. A `WHEN IN DOUBT` cheatsheet at the bottom maps content shapes to the correct construct. The prompt is injected into every extension's skeleton via the existing `_inject_capability_boundary` wire — no new plumbing.

**Layer 2 — `imperal_sdk/chat/filters.py::normalize_markdown` (new function):**

```python
from imperal_sdk.chat.filters import normalize_markdown

normalize_markdown("Hello ** world **!")  # → "Hello **world**!"
normalize_markdown("** **")               # → ""
normalize_markdown("**a b c**")           # → "**a b c**"  (internal spaces preserved)
```

- Regex `r"\*\*([^*\n]*?)\*\*"` finds each `**...**` run; inner whitespace trimmed via `.strip()`. Empty bolds (`** **`) collapse to empty string.
- Pure function. No state. Idempotent: `normalize_markdown(normalize_markdown(x)) == normalize_markdown(x)`.
- Lazy-compiled regex (`_BOLD_WS_FIX` module global; first call only).
- Auto-applied at 2 sites in `imperal_sdk/chat/handler.py` (after `enforce_response_style`) — every LLM text output on the chat delivery path passes through. No extension code change required.

Layer 1 teaches the model correct form up-front; Layer 2 cleans up residual slips. Both layers are required — the prompt is a hint, not a guarantee.

### Invariants

- **I-MD-1** — `kernel_formatting_rule.txt` MUST keep the DO / NEVER pair format and concrete examples. Rewrites that drop the rule risk a regression in markdown emission quality.
- **I-MD-2** — `normalize_markdown` MUST stay pure, idempotent, and called at every chat-handler text return site. Adding a new return site without the call surfaces as broken bold rendering on user-visible output.

### Note — ICNLI v7 SDK contract extension (cross-reference)

In parallel, the kernel-side ICNLI v7 deploy introduced SDK-visible flag gates + `ctx.session_memory_slice` propagation for extensions, plus an `emit_refusal` tool schema consumed by `ChatExtension._handle`. Those additions are documented in [`docs/imperal-cloud/icnli-v7-architecture.md`](https://github.com/imperalcloud) and are live on the deployed `/opt/imperal-sdk` tree on `whm-ai-worker`. They are **not** packaged as part of 1.5.17 — this release is limited to the markdown hygiene change so the federal customer can opt in without taking the v7 kernel-integration surface.

### See also

- Authoritative architecture reference: `docs/imperal-cloud/icnli-v7-architecture.md` (§ "Markdown rendering hygiene").
- Invariants registered in `docs/imperal-cloud/conventions.md` under `## Invariants` table (I-MD-1, I-MD-2).

## 1.5.16 (2026-04-20)

### Fix: `ui.Stack(wrap=...)` is now tri-state — opt-out of Panel auto-wrap is reachable

The Panel-side DUI renderer started auto-wrapping horizontal `Stack` children in session 33 (2026-04-19) to prevent toolbar overflow on narrow extension panes. The rule on the Panel is `isHorizontal ? (wrap !== false) : (wrap === true)` — horizontal Stacks wrap **unless** `wrap` is explicitly `false`.

In SDK ≤ 1.5.15, `Stack(wrap=False)` silently dropped the prop (only `True` was emitted), so a developer passing `wrap=False` on a horizontal Stack could not reach the opt-out — the rendered Stack still wrapped. v1.5.16 makes `wrap` tri-state:

```python
# default — Panel applies direction-specific default
ui.Stack([...], direction="h")             # wraps (Panel default)
ui.Stack([...], direction="v")             # does not wrap (Panel default)

# explicit — Panel respects as-is
ui.Stack([...], direction="h", wrap=False) # does NOT wrap (opt-out now reachable)
ui.Stack([...], direction="v", wrap=True)  # wraps
```

**Signature change:** `wrap: bool = False` → `wrap: bool | None = None`. The default behaviour (no explicit wrap → Panel picks) is unchanged from the caller's perspective — only the opt-out path is newly reachable. No extension code needs to change unless it was passing `wrap=False` on horizontal Stacks expecting it to take effect.

### Docs — session 33 DUI design-system alignment

- `docs/extension-ui.md` — Principle 6 added: Automatic spacing + agency theming. Guarantee table, semantic variant reference, and examples showing when to rely on container-owned padding vs emitting custom spacing.
- `docs/ui-components.md` — version bumped to v1.5.16, session-33 changelog block documenting the Tailwind `@theme inline` remap, container-level padding philosophy (DPage owns page padding, DSection inherits, DCard owns its own), the horizontal Stack auto-wrap default, element-level sizing tokens in `tokens.css`, the Panel ESLint wall forbidding hardcoded Tailwind scales, and the L1–L4 authority hierarchy (primitives > declarative > extensions > pages).
- `docs/extension-guidelines.md` — Rule 19 added: **UI Styling — Emit Semantic Intent, NEVER Hardcode Visuals**. Extensions must use semantic variants (`variant="primary"`, `tone="danger"`) and the declarative layout primitives; hardcoded Tailwind colours and `style={}` are forbidden. Guarantee table explains what the renderer provides automatically (padding, gaps, agency theming, dark-mode, WCAG AA). `ui.theme(ctx)` remains the sole escape hatch for legitimate custom rendering.

### Test coverage

Two new regression guards in `tests/test_ui.py::TestStack`:
- `test_wrap_default_not_emitted` — `wrap=None` default must not emit the prop (Panel picks direction-specific default).
- `test_wrap_false_explicit_emitted` — `wrap=False` MUST be emitted so horizontal Stacks can opt out of auto-wrap.

### See also

Authoritative DUI design-system reference: [`docs/imperal-cloud/design-system.md`](https://github.com/imperalcloud/imperal-sdk) in the internal infra repo. Panel-side CSS vars: `/opt/imperal-panel/src/styles/tokens.css`. Session 33 rollout summary: `docs/imperal-cloud/dui-design-tokens.md`.

## 1.5.15 (2026-04-19)

### New: `ui.theme(ctx)` — typed accessor for agency white-label theme

```python
from imperal_sdk import ui

async def my_tool(ctx):
    theme = ui.theme(ctx)
    primary_hex = theme.colors["primary"].light if "primary" in theme.colors else "#2563eb"
    return ui.Card(...)
```

Returns a frozen, slotted `AgencyTheme` dataclass mirroring the Auth GW Pydantic schema — `colors: dict[str, ColorPair]`, `density: Literal["compact", "default", "spacious"]`, `radius: Literal["sharp", "default", "rounded"]`. `ctx=None` returns the empty default for unit tests.

The SDK performs no validation — payload is already validated upstream at the Auth GW boundary (`AgencyTheme` Pydantic model with WCAG AA contrast, 26-key whitelist, `extra="forbid"`). Malformed colour pairs from a schema-drifted DB row are silently dropped rather than raising.

### `Context` gains `agency_id` + `agency_theme`

Kernel populates both on workflow start. `agency_id: str | None` is the data-isolation boundary (matches the session-28 agency multi-tenancy rollout); `agency_theme: dict | None` carries the raw JSON from `agencies.theme`.

### Exports

`imperal_sdk.ui.theme`, `imperal_sdk.ui.AgencyTheme`, `imperal_sdk.ui.ColorPair`.

### Test coverage

13 cases: default fallback for missing ctx / attribute / None / non-dict, full payload parse, malformed colour-pair drop, unknown enum fallback, frozen-instance, slots (no `__dict__`), `_from_dict` helper, public-export surface.

## 1.5.14 (2026-04-19)

### Contract tests — spec validation in CI + schemathesis for live verification

Closes the contracts roadmap with tests that keep the 12 JSON Schemas and 3 OpenAPI specs honest on every commit, plus an env-gated integration layer for running contract tests against live Imperal services.

### New: `tests/test_spec_validation.py` (always runs in CI)

Offline, fast, no network. Fails the build the moment any committed contract drifts or malforms:

- **Every `imperal_sdk/schemas/*.schema.json`** validates against Draft 2020-12 (`jsonschema.Draft202012Validator.check_schema`). Confirms `$id` is under `https://imperal.io/schemas/`, `title` is set.
- **Every `docs/openapi/*.json`** validates against the full OpenAPI 3.x spec (`openapi_spec_validator.validate`). Confirms `openapi` is 3.0.x or 3.1.x, `info.title`/`version`/`paths` are present.
- **`operationId` uniqueness** — duplicates break every code-generator that keys on them (openapi-generator, openapi-python-client, openapi-typescript, …).
- **`$ref` resolution** — every internal reference (`#/components/schemas/X`) must point to an existing component. Catches orphan refs left behind by service refactors.
- **Static-vs-runtime schema drift** — each committed `schemas/*.schema.json` file must equal the runtime `get_*_schema()` export from its Pydantic source-of-truth. Forgot to regenerate? CI fails.

**Result on current repo:** 12 schemas ✓, 3 specs ✓, 287 unique operationIds across 229 paths, 0 broken refs, 0 drift.

### New: `tests/test_contracts_live.py` (env-gated — skipped by default)

Integration layer using [schemathesis](https://schemathesis.readthedocs.io/):

- Reads the committed OpenAPI spec, generates property-based requests per endpoint, replays them against a live service, asserts every real response matches its declared schema.
- **Skipped unless `[contract]` extra is installed and `IMPERAL_CONTRACT_{REGISTRY,AUTH,CASES}_{URL,API_KEY}` env vars are set.** No credentials in CI → tests skip. Developers point at localhost or staging before shipping a service change.

Install and run locally:

```bash
pip install imperal-sdk[contract]
export IMPERAL_CONTRACT_REGISTRY_URL="https://auth.imperal.io"
export IMPERAL_CONTRACT_REGISTRY_API_KEY="imp_reg_key_xxxxxxxxxxxxxxxx"
pytest tests/test_contracts_live.py -v
```

### New `[contract]` optional extra

- `schemathesis>=3.30.0` — only pulled when installing `imperal-sdk[contract]`. Keeps the core + dev install light.

### `[dev]` additions

- `openapi-spec-validator>=0.7.1`, `jsonschema>=4.21.0` — both used by `test_spec_validation.py`, small, fast, well-maintained.

### docs/openapi/README.md
- New "Contract-test your extension" section walks through installing `[contract]`, exporting env vars, running `pytest tests/test_contracts_live.py`, and points back at the offline suite for what CI already checks.

### Roadmap — contract coverage now 100%

| Layer | Shipped in |
|-------|------------|
| Extension manifest (`imperal.json`) | v1.5.9 |
| Cross-kernel payloads (ActionResult, Event, FunctionCall, ChatResult) | v1.5.10 + v1.5.13 |
| HTTP client response types (Document, CompletionResult, LimitsResult, SubscriptionInfo, BalanceInfo, FileInfo, HTTPResponse) | v1.5.13 |
| OpenAPI 3.x for Auth GW / Registry / Cases | v1.5.11 |
| Offline spec validation in CI | **v1.5.14** |
| schemathesis live contract testing | **v1.5.14** |

## 1.5.13 (2026-04-19)

### Contracts — full SDK type coverage

Completes the contract wave started in v1.5.9. Every typed return/payload an extension touches — cross-kernel and HTTP-client alike — now has a Pydantic mirror, a non-raising validator, and a static JSON Schema shipped with the wheel.

### New in `imperal_sdk.types.contracts` (cross-boundary platform payloads)

- **`FunctionCallModel`** + `validate_function_call_dict` (rule codes `FC1..FC5`) — record of a single `@chat.function` invocation. Crosses Temporal activity history on every chat turn.
- **`ChatResultModel`** + `validate_chat_result_dict` (rule codes `CR1..CR5`) — serialized return from `ChatExtension._handle()`. Enforces the underscore-prefixed wire format (`_handled`, `_functions_called`, ...) — the kernel's hub dispatcher depends on that prefix to distinguish transport metadata from raw tool response, and a validator catches attribute-name-instead-of-alias typos that would silently lose data.

### New module `imperal_sdk.types.client_contracts` (HTTP client response types)

Seven Pydantic mirrors of the `ctx.*` client dataclasses in `types/models.py` — the runtime-enforceable contracts for what comes back from Auth Gateway and Imperal-platform HTTP services:

- **`DocumentModel`** (`DOC1..5`)         — `ctx.store.get/query/create/update()` row
- **`CompletionResultModel`** (`CPL1..5`) — `ctx.ai.complete()` response
- **`LimitsResultModel`** (`LIM1..5`)     — `ctx.billing.check_limits()` response
- **`SubscriptionInfoModel`** (`SUB1..5`) — `ctx.billing.get_subscription()`
- **`BalanceInfoModel`** (`BAL1..5`)      — `ctx.billing.get_balance()`
- **`FileInfoModel`** (`FIL1..5`)         — `ctx.storage.upload/list()` entry
- **`HTTPResponseModel`** (`HRS1..5`)     — `ctx.http.*` wrapped response (status 100-599, body dict/str/list; bytes bodies are local-only and intentionally out-of-contract)

### Static JSON Schemas (Draft 2020-12)

Nine new files under `imperal_sdk/schemas/`, all wheel-shipped via `hatch force-include`:

`function_call.schema.json`, `chat_result.schema.json`, `document.schema.json`, `completion_result.schema.json`, `limits_result.schema.json`, `subscription_info.schema.json`, `balance_info.schema.json`, `file_info.schema.json`, `http_response.schema.json`.

### Complete contract surface now

| Contract | Schema file | Rule codes | Module |
|----------|-------------|------------|--------|
| `imperal.json` manifest | `imperal.schema.json` | M1..M5 | `manifest_schema` (v1.5.9) |
| `ActionResult` payload | `action_result.schema.json` | AR1..AR5 | `types.contracts` (v1.5.10) |
| `Event` envelope | `event.schema.json` | EV1..EV5 | `types.contracts` (v1.5.10) |
| `FunctionCall` record | `function_call.schema.json` | FC1..FC5 | `types.contracts` (**v1.5.13**) |
| `ChatResult` payload | `chat_result.schema.json` | CR1..CR5 | `types.contracts` (**v1.5.13**) |
| `Document` row | `document.schema.json` | DOC1..5 | `types.client_contracts` (**v1.5.13**) |
| `CompletionResult` | `completion_result.schema.json` | CPL1..5 | `types.client_contracts` (**v1.5.13**) |
| `LimitsResult` | `limits_result.schema.json` | LIM1..5 | `types.client_contracts` (**v1.5.13**) |
| `SubscriptionInfo` | `subscription_info.schema.json` | SUB1..5 | `types.client_contracts` (**v1.5.13**) |
| `BalanceInfo` | `balance_info.schema.json` | BAL1..5 | `types.client_contracts` (**v1.5.13**) |
| `FileInfo` | `file_info.schema.json` | FIL1..5 | `types.client_contracts` (**v1.5.13**) |
| `HTTPResponse` | `http_response.schema.json` | HRS1..5 | `types.client_contracts` (**v1.5.13**) |

Plus OpenAPI 3.x for Auth Gateway, Registry, Sharelock Cases under `docs/openapi/` (v1.5.11).

### Tests
- `tests/test_contracts.py` — expanded with FC / ChatResult cases (~12 new tests).
- `tests/test_client_contracts.py` — 40+ new tests covering validation, round-trip via real dataclasses (`Document`, `CompletionResult`, …), and committed-file drift detection for every new schema.

## 1.5.12 (2026-04-19)

### Package metadata — PyPI badges now work correctly

Follow-up release addressing stale/missing metadata on the PyPI project page and in the README badge row. No functional changes to the SDK surface.

- **PyPI `classifiers` block added** — Development Status, Intended Audience, Operating System, Python versions (3.11, 3.12), Topic, Framework, Typing. Enables `shields.io/pypi/pyversions/imperal-sdk` badge (was showing "missing") to render correctly.
- **SPDX `license = "AGPL-3.0-or-later"`** + explicit `authors` + explicit `readme = "README.md"` in `[project]`. Matches PEP 621 + PEP 639.
- **`.github/workflows/test.yml`** — pytest matrix on Python 3.11 + 3.12 runs on every push/PR to `main`. Powers the README `Tests` badge (was hardcoded `343 passing` — stale). First run verified: both matrix jobs green in ~18-19s.
- **Rolls up** v1.5.10 payload-contract schemas and v1.5.11 OpenAPI specs into PyPI (which had stayed at v1.5.9 — the `publish.yml` workflow triggers on GitHub Release events, not raw tag pushes). Cutting this as an explicit Release pushes the accumulated work to PyPI.

## 1.5.11 (2026-04-19)

### Contracts — OpenAPI specs for every Imperal service an extension talks to

Third-party developers previously had no machine-readable reference for the HTTP surface their extensions interact with. The `ctx.*` clients in the SDK abstract it, but anyone building a non-Python integration (TypeScript panel, CI contract test, custom bridge) had to read Python source to figure out request/response shapes. This release ships the canonical OpenAPI 3.x specs for the three Imperal platform services alongside the markdown docs.

- **New directory `docs/openapi/`** — OpenAPI 3.x specs captured from each service's `/openapi.json` endpoint.
  - `auth-gateway.json` — **151 paths, 92 schemas**. JWT issuance, users, tenants, apps, billing, automations, agencies. Base URL: `https://auth.imperal.io`.
  - `registry.json` — **15 paths, 9 schemas**. Extension catalog, tool discovery, per-app settings, hub dispatch.
  - `sharelock-cases.json` — **63 paths, 38 schemas**. Forensic case store (Sharelock v3 backend — only relevant if building on top of it).
  - `README.md` — how to browse/generate clients/validate against/contract-test the specs.

**Total: 229 endpoints, 139 schemas, ~570 KB.**

### Non-Imperal specs

Internal platform services on shared infrastructure (DirectAdmin proxy, WHMCS bridge, ad-network controllers, diagnostics tooling — 11 specs / 446 endpoints / ~2.2 MB) are intentionally **not** included. They document internal attack surface and live only in the ops-side archive.

### README
- Links section now references `docs/openapi/` alongside `docs.imperal.io`.

### Tooling examples

The new README covers: interactive browse (Swagger Editor), typed-client generation (`openapi-python-client`, `openapi-typescript`), runtime validation (`jsonschema.validate`), and contract testing against a live service (`schemathesis run`).

## 1.5.10 (2026-04-19)

### Contracts — cross-boundary payloads now have machine-validated schemas

Building on v1.5.9 (which closed the `imperal.json` manifest gap), this release contracts two more payloads that leave a single Python process — across Temporal activities, Redis pub/sub, SSE, and the Fast-RPC transport.

Until now `ActionResult.to_dict()` and the Redis-streams `Event` envelope were dataclasses without a runtime-enforceable contract. Malformed dicts from non-SDK producers (legacy extensions, platform-side rewriters, and anything in the kernel executor pipeline) would silently propagate and be caught only by whoever downstream happened to rely on a specific field. The 10 textual `RPC-I1..I10` invariants documented on the platform side are now backed by a schema anyone can validate against.

- **New module `imperal_sdk.types.contracts`** — Pydantic mirrors of the two canonical cross-boundary types:
  - `ActionResultModel` — the strict contract for `ActionResult.to_dict()`. Enforces `status ∈ {success, error}`, cross-field rule (`status='error'` requires non-empty `error`, `status='success'` forbids `error`), refuses unknown top-level keys (catches typos like `retryble` → `retryable`), and whitelists the exact shape `data / summary / error / retryable / ui / refresh_panels`.
  - `EventModel` — the Redis-streams event envelope. Enforces `event_type` shape (`namespace.action` or `namespace:action`, both dot- and colon-forms accepted for the session-27/28 migration), validates `user_id` against `imp_u_* | __system__ | ""` and `tenant_id` against `imp_t_* | default | ""`.
- **Validators** — non-raising, return `list[ValidationIssue]` for unified CLI/report handling:
  - `validate_action_result_dict(data)` — rule codes `AR1..AR5`
  - `validate_event_dict(data)`         — rule codes `EV1..EV5`
- **Static JSON Schema files** — Draft 2020-12, shipped with the wheel via `hatch force-include`:
  - `imperal_sdk/schemas/action_result.schema.json`
  - `imperal_sdk/schemas/event.schema.json`
- **Re-exports from `imperal_sdk.types`** — `ActionResultModel`, `EventModel`, `validate_action_result_dict`, `validate_event_dict`, `get_action_result_schema`, `get_event_schema`, `ACTION_RESULT_SCHEMA`, `EVENT_SCHEMA`.

### Cross-field invariants enforced (AR4)

- `status='error'` **must** carry a non-empty `error` — kernel has no user-facing message otherwise, a bug that silently produced empty red toasts in production before.
- `status='success'` **must not** carry an `error` — catches extensions that set both by mistake and produce contradictory logs.

### Tests
- `tests/test_contracts.py` — 30+ cases covering every rule code (AR1..AR5, EV1..EV5), accepted event-type / user-id / tenant-id forms, round-trip through the real `ActionResult.success()` / `.error()` factory methods and the `Event` dataclass, and drift detection against committed static schema files.

### Not yet contracted (next)
- `ChatResult` / `FunctionCall` (ChatExtension → kernel) — typed dataclasses, not yet schema'd.
- `ctx.*` client response types (`Document`, `CompletionResult`, `LimitsResult`, `SubscriptionInfo`, `BalanceInfo`, `FileInfo`, `HTTPResponse`) — dataclasses, SDK-internal.

## 1.5.9 (2026-04-19)

### Contracts — `imperal.json` now has a machine-validated schema

Closes the long-standing V8 hole in `validator.py` ("Cannot verify imperal.json manifest"). Third-party extensions shipped with malformed manifests for months — typos like `schedule` (singular) silently disabled scheduled tasks, missing `description` broke embeddings, and no one caught invalid scope / cron values until runtime. The platform Registry now has a single source of truth for manifest shape, and `imperal validate` / `imperal deploy` enforce it.

- **New module `imperal_sdk.manifest_schema`** — Pydantic models (`Manifest`, `Tool`, `ToolParam`, `Signal`, `Schedule`) that are the canonical contract for the shape `generate_manifest()` produces. Re-exported from `imperal_sdk.manifest` for convenience: `from imperal_sdk.manifest import validate_manifest_dict, MANIFEST_SCHEMA, Manifest`.
- **`validate_manifest_dict(data: dict) -> list[ValidationIssue]`** — non-raising validator. Rule codes: `M1` (root not a dict), `M2` (missing required field), `M3` (unknown top-level field — typo detection), `M4` (invalid value — regex/type/enum mismatch), `M5` (nested-field error in tool/signal/schedule). Reuses `ValidationIssue` from `validator.py` so CLI output is uniform.
- **`imperal_sdk/schemas/imperal.schema.json`** — committed static JSON Schema (Draft 2020-12) shipped with the wheel. External tooling, IDE plugins, CI, and non-Python services can validate manifests without importing the SDK.
- **`imperal validate` closes V8** — if an `imperal.json` exists in the extension directory, it is loaded and validated against the schema. Structural issues (M0..M5) are merged into the existing report alongside V1-V12. The runtime-only V8 placeholder is dropped when the filesystem answer is available.
- **`imperal deploy` uses the full validator** — replaces the 5-line ad-hoc check with `validate_manifest_dict`. Deploy now blocks on every M1..M5 violation in addition to the embeddings-critical "no description" check.
- **Validated fields (M4/M5)**: `app_id` regex `[a-z0-9][a-z0-9-]*[a-z0-9]` (matches V1), semver version with pre-release/build suffix, scope forms (`*`, `ns:*`, `ns:action`, legacy `ns.action`), cron (5-field unix or `@keyword`), `ToolParam.type` whitelist (`string|integer|number|boolean|array|object`), tool name as Python identifier.

### Accepted shapes (confirmed against production manifests)

- Base manifest: `app_id`, `version`, `capabilities`, `tools`, `signals`, `schedules`, `required_scopes` — all 7 SDK-canonical fields.
- SDK-optional: `migrations_dir`, `config_defaults`.
- Marketplace merge (from disk overlay): `name`, `description`, `author`, `license`, `homepage`, `icon`, `category`, `tags`, `marketplace`, `pricing`.
- Per-schedule / per-signal `description` — accepted (some production extensions add it; harmless).

All 7 first-party extension manifests in the monorepo validate clean (`notes`, `sql-db`, `google-ads`, `mail`, `meta-ads`, `microsoft-ads`, `web-tools`).

### Tests
- `tests/test_manifest_schema.py` — 20+ cases covering every rule code, accepted cron/scope forms, generate→validate round-trip, schema export stability, and static-file drift detection (fails CI if the committed `imperal.schema.json` drifts from the runtime model).

## 1.5.8-1 (2026-04-19)

### Documentation
- **`docs/` folder added to the repo** — full SDK documentation (14 files, 8.6K lines) now lives in-tree: `quickstart`, `concepts`, `api-reference`, `clients`, `context-object`, `tools`, `skeleton`, `auth`, `cli`, `extension-ui`, `ui-components`, `extension-guidelines`, `context-router`, `testing`. Previously the canonical source lived only in an internal infrastructure repo; third-party developers reading the repo on GitHub now have it in-tree. `docs.imperal.io` can be built from this source.
- **All example API keys and IPs sanitized** to explicit placeholders: `imp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`, `imp_reg_key_xxxxxxxxxxxxxxxx`, `sl_cases_api_xxxxxxxxxxxxxxxx`, `auth.imperal.io:8085`, `203.0.113.42` (RFC 5737 docs range). Random-looking example strings that could have been mistaken for live credentials are gone.
- `README.md` — Links section and top nav reference in-repo `docs/` alongside `docs.imperal.io`.

### Package version unchanged (`1.5.8`)
- No code changes — documentation/metadata-only follow-up. Same convention as `v1.5.6-1`.

## 1.5.8 (2026-04-18)

### DUI additions (SDK-side, backward compatible)
- **`ui.Progress(color=...)`** — semantic colors for status bars. One of `blue` (default), `green`, `red`, `yellow`, `purple`. Empty string keeps the default. Use for budget bars, compliance progress, any state that benefits from at-a-glance semantics. Panel React component already supported `color` via `BAR_COLOR_CLASSES`; SDK now passes it through.
- **`ui.Chart(colors=..., y2_keys=...)`**. `colors: dict[str,str]` maps series key → hex/CSS color; SDK emits `series=[{key,label,color}]` that the Recharts renderer honors. `y2_keys: list[str]` adds a secondary right-side Y-axis and routes the named series to it — use for mixed-scale metrics (spend $ on left, clicks count on right). Pie charts unaffected.
- **`ui.TagInput(delimiters=..., validate=..., validate_message=...)`**. `delimiters: list[str]` — extra keys that create a tag in addition to Enter (e.g. `[" ", ",", ";"]`); paste is also split on these. `validate: str` — regex pattern; tags failing it are refused with a red caption for 1.8s. `validate_message: str` — human hint shown on rejection. Defaults preserve prior Enter-only behaviour.

### `NotifyProtocol` drift fix — CRITICAL for test code
- `NotifyClient` now implements BOTH `__call__(message, **kwargs)` (preferred — matches every production extension that uses `await ctx.notify("msg")`) AND `send(message, channel="in_app", **kwargs)` (alias forwarding to `__call__`). `NotifyProtocol` declares both. `MockNotify` supports both — each call path writes to `self.sent` with identical shape. Prior versions declared `send` only in the Protocol but implemented only `__call__` in the concrete client — `ctx.notify.send(...)` crashed at runtime in production despite being shown in the testing docs.

### Form child-input initial-value registration (Panel-side, ships with SDK compatibility)
- `DToggle` + `DSelect` Panel components now register their `initValue` with `FormContext` on mount if `form.values[param_name]` is still `undefined`. Before this, unchanged toggles / selects never appeared in the submit payload — the server saw "field missing" instead of their actual initial value. This fixes the long-standing "unticked toggles silently dropped" class of bugs. The SDK side (Python) is unchanged; the fix lives in the Panel DUI runtime. No extension code change needed.

### Accumulated from v1.5.7 (not in the tagged release)
- **`User.agency_id: str | None = None`** field (session 28, 2026-04-18) — added for agency multi-tenancy rollout. Extensions SHOULD forward `X-Imperal-Agency-ID: {ctx.user.agency_id or 'default'}` to downstream services (Cases API and similar).
- **`ChatExtension` scope tightening** (session 27) — auto-registered chat entry tool now uses `scopes=[]` instead of `scopes=["*"]`. Granted capability set = union(`Extension.capabilities`, per-tool `scopes=`). Loader falls back to `["*"]` with a WARN log when an extension declares neither — that's the migration signal to add explicit capabilities.
- **`enforce_os_identity()` fallback** (session 29) — when ALL sentences in the LLM output match an identity-leak pattern, the filter now returns a neutral acknowledgement (`"Чем могу помочь?"` for Cyrillic-containing input, `"How can I help?"` otherwise) instead of leaking the original text. Previously the all-stripped case fell through to the original string verbatim, defeating the filter.

### Platform-side notes (consumers of this SDK benefit automatically)
- **Kernel `@ext.schedule` dispatcher shipped** (platform session 30, 2026-04-18). The decorator has existed for a long time in this SDK, but the kernel silently ignored it until 2026-04-18. Extensions declaring `@ext.schedule("name", cron="...")` now actually fire on schedule — exactly once per (app, schedule, minute) across the 3-worker cluster via Redis-SETNX dedup. Runs under a synthetic `__system__` user (`scopes=["*"]`). Wall-clock cap `IMPERAL_EXT_SCHEDULE_TIMEOUT_S=600`. See platform docs `conventions.md` invariants SCHED-EXT-I1/I2.
- **Panel `/call` transport moved to Redis Streams** on platform for `__panel__*` calls (Phase 2 of Fast-RPC rollout). End-to-end latency dropped 388ms → 3ms. Extension code is untouched — same `direct_call_extension` activity runs handlers. See platform `fast-rpc.md`.
- **Webhook URL clarified** — `@ext.webhook(path)` registers at `POST /v1/ext/{app_id}/webhook/{path}` (not `/webhooks/{app_id}/{path}` as older guidelines said). Handler receives `(ctx, headers, body, query_params)`.

### Docs
- `docs/imperal-cloud/sdk/ui-components.md` — v1.5.8 changelog entry, Progress/Chart/TagInput prop tables updated with session 30 additions, examples rewritten for semantic colors + domain TagInput + dual Y-axis chart, Form section clarifies Context propagation through arbitrary nesting depth.
- `docs/imperal-cloud/sdk/context-object.md` — `ctx.notify` Methods table declares both `__call__` (preferred) and `send` (alias) with the drift history.
- `docs/imperal-cloud/sdk/testing.md` — MockNotify example shows both call-styles.
- `docs/imperal-cloud/sdk/extension-guidelines.md` — webhook URL fixed, `on_event` / `expose` / `tray` / `schedule` handler signatures expanded.
- `docs/imperal-cloud/sdk/concepts.md` — added availability note for `@ext.schedule` dispatcher.

## 1.5.7 (2026-04-17)

### CRITICAL BUGFIX
- **`imperal validate` V5/V6 false positives under `from __future__ import annotations` (PEP 563) are FIXED.** The validator previously read raw `__annotations__` / `inspect.signature` parameter annotations, which are STRINGS — not classes — when the source module opts into PEP 563. Every `@chat.function(ctx, params: MyPydanticModel)` in extensions that use the modern annotation style raised a V6 false positive (`params should be a Pydantic BaseModel subclass`), and V5 would similarly miss aliased `ActionResult` imports. **Fix:** validator now uses `typing.get_type_hints(func)` to resolve forward references via the function's `__globals__` before `isinstance` / `issubclass` checks, with graceful fallback to raw annotation substring match when resolution fails (e.g. circular imports). Shared helpers `_resolve_hints`, `_looks_like_action_result`, `_is_basemodel_subclass` ensure every future type-annotation check reuses the same resolution path. 9 regression tests cover `from __future__` + BaseModel + ActionResult + subclass + unresolvable hints.

## 1.5.6 (2026-04-17)

### CRITICAL BUGFIX
- **`@chat.function(event=...)` events now publish correctly**. Previously `ChatExtension._make_chat_result` constructed `FunctionCall` without passing the `result` field — so `FC.result` stayed `None`, `FC.to_dict()` omitted `result`, and the kernel's event-publishing check at `extension_runner.py` never fired. **Impact pre-fix**: sidebar `refresh="on_event:..."` never triggered (notes, sql-db, mail, billing, developer); automation rules filtering by `event_type` never stirred; extensions had no way to publish specific events (only generic `scope.action` fallbacks). **Fix**: one-line addition `result=fc_dict.get("result")` in the FC constructor. Companion fix in platform kernel (`extension_runner.py`): accept either `ActionResult` object (in-process) or dict (post-transport) via `ActionResult.from_dict()` hydration.

## 1.5.5 (2026-04-16)

### UI Components
- **`ui.Graph`** — new Cytoscape-backed interactive graph component. Accepts Cases API `/graph` payload directly (unwraps Cytoscape `{data: {...}}` format server-side). Layouts: `cose-bilkent` (default), `circle`, `grid`, `breadthfirst`, `concentric`. Props: `nodes`, `edges`, `layout`, `height`, `min_node_size`, `max_node_size`, `edge_label_visible`, `color_by`, `on_node_click`. Rendered by new Panel `DGraph` component (registered as `graph`). Designed for forensic entity/relationship visualisation (Sharelock v3 Intelligence Graph); performance target ~5000 nodes.

## 1.5.4 (2026-04-16)

### System Tray SDK
- **`@ext.tray()`** — new decorator for System Tray items in the OS top bar. Extensions can publish icon + badge + dropdown panel directly into the system tray (next to clock). Props: `tray_id`, `icon` (Lucide name), `tooltip`. Handler returns UINode (badge/panel). Registers `__tray__{id}` ToolDef for /call dispatch.
- **`TrayDef`** — new dataclass exported from SDK. Stored in `ext.tray_items` dict.

### OS Identity Enforcement
- **SDK Identity Guard** — `ChatExtension.__init__` now warns if `system_prompt` contains "You are [a/an/the]". Developers see `[SDK] ChatExtension 'tool': system_prompt contains 'You are ...'` warning in logs. Extensions must describe MODULE capabilities, not AI identity — the kernel injects `{assistant_name}` identity automatically.
- **`enforce_os_identity()` expanded** — `filters.py` now catches ~50 self-identification patterns (EN + RU) in addition to redirect patterns. Strips sentences like "I'm the Notes assistant" from LLM output.

### Deploy Pipeline
- **Registry auto-sync** — `deploy_app` now calls `_sync_tools_to_registry()` after successful validation. Loads extension, reads tools + skeleton, calls `PUT /v1/apps/{app_id}/tools`. Auto-creates app in Registry if missing (`_ensure_app_in_registry()`, 409=OK). Extensions appear in AI catalog immediately after deploy.
- **R10: `check_system_prompt_identity`** — new validation check. Scans `system_prompt.txt` AND inline `system_prompt=` keyword args in `main.py` via AST analysis. Catches "You are [a/an/the]" patterns. Critical severity — deploy fails.
- **R11: `check_registry_sync`** — new post-deploy verification. Confirms tools registered in Registry catalog. Falls back to direct API check if sync returned 0. Critical severity.
- **`validate_checks_deploy.py`** — new validation script (R10 + R11). Separate from R4-R9 to stay under 300L per file.

### Prompt System
- **`kernel_capability_boundary.txt`** — rewritten to use `{assistant_name}` placeholder. "You are {assistant_name} — the AI of Imperal Cloud AI OS."
- **`prompt.py` IDENTITY section** — replaces old CAPABILITY BOUNDARY. Injects assistant_name + full catalog capabilities into every LLM call.
- **`_build_all_capabilities()`** — new function in `system_handlers.py`. Builds compact summary of ALL extensions from catalog, injected into every extension LLM call.
- **`state.assistant_name`** — new field cached from Redis `imperal:platform:assistant`. Resolved by `navigator.py:_resolve_assistant_name()`.
- **All 13 extension system prompts fixed** — removed "You are X" identity from 8 `.txt` files + 5 inline `main.py`/`app.py` prompts (notes, mail, admin, developer, web-tools, automations, microsoft-ads, sql-db, video-creator, ocr-tool, hello-world, sharelock-v2, billing).
### UI Component Fixes (Panel)
- **`renderChildren()` normalized** — now accepts `UINode | UINode[] | undefined | null`, always normalizes to array. Fixes `e.map is not a function` crash when children is a single node. Affects **DSection**, **DSlideOver**, and any component using `renderChildren`.
- **DTagInput** — `values`, `suggestions` from Form context normalized to array before `.map()`. Single string values wrapped in `[string]`.
- **DMultiSelect** — `options`, `values` normalized to array. Same Form context fix.
- **DTimeline** — `items` normalized to array. `undefined` → `[]`.
- **Root cause:** SDK serializes props as JSON. Form context and skeleton can return single values instead of arrays (especially with one element). All array-consuming components now defensively normalize inputs.

### Scheduler Patterns (Documentation)
- **Static cron** — `@ext.schedule("name", cron="0 9 * * *")` runs at fixed intervals. Set at deploy time. Best for: daily reports, hourly syncs, periodic cleanup.
- **Dynamic scheduling pattern** — for user-created schedules (e.g. monitors with custom intervals), use a single hourly cron + `last_run_at` check:
  ```python
  @ext.schedule("scan_runner", cron="0 * * * *")
  async def scan_runner(ctx):
      monitors = await ctx.store.query("monitors", where={"active": True})
      now = time.time()
      for m in monitors:
          if now - m.get("last_run_at", 0) >= m["interval_hours"] * 3600:
              await run_scan(ctx, m["id"])
              await ctx.store.update("monitors", m["id"], {"last_run_at": now})
  ```
- **No `ctx.scheduler` needed** — the cron + last_run_at pattern is the standard production approach. Avoids kernel complexity while supporting arbitrary per-user intervals.


## 1.5.0 (2026-04-13)

### New UI Components & Enhancements
- **`ui.Html`** — raw HTML block with DOMPurify sanitization. `sandbox=True` renders in isolated iframe with ResizeObserver auto-height. Props: `content`, `sandbox`, `max_height`, `theme` (`"dark"` or `"light"` for email rendering with white bg).
- **`ui.Open`** — action type for opening URLs in new tab/popup. Used by Button `on_click` for downloads and OAuth.
- **`ui.Image(on_click=)`** — click handler for image gallery / lightbox patterns.
- **`ui.FileUpload`** — file upload with drag-and-drop, base64 encoding. Props: `accept`, `max_size_mb`, `max_total_mb`, `max_files`, `multiple`, `blocked_extensions`.
- **`ui.Button(icon=)`** — Lucide icon rendering in buttons via `(LucideIcons as any)[name]` lookup.
- **`ui.List()` multi-select** — `selectable=True` enables checkbox selection on hover. `bulk_actions=[{label, icon, action}]` renders sticky BulkActionBar. Selected IDs auto-injected as `message_ids` param.
- **`ui.List(on_end_reached=)`** — infinite scroll support via IntersectionObserver sentinel. `total_items` and `extra_info` for footer Paginator.
- **`ui.Stack(sticky=)`** — `sticky=True` pins element to top of scroll container. For toolbars and action bars.
- **`ui.Stack(className=)`** — custom CSS classes, overrides default system padding.
- **`ui.Stack` direction** — frontend accepts both `"h"` and `"horizontal"`.
- **System padding** — horizontal Stacks get default `px-3 py-2.5` (sticky) / `py-1.5` (non-sticky) for consistent alignment.

### Frontend DUI
- **DHtml.tsx** — DOMPurify sanitization + iframe sandbox + `theme="light"` with white bg for email + `overflow: auto` (was hidden) + 600px initial height.
- **DList.tsx** — BulkActionBar (sticky top), footer Paginator (sticky bottom), multi-select with checkboxes on hover, infinite scroll sentinel.
- **DButton.tsx** — Lucide icon resolution with PascalCase fallback.
- **DImage.tsx** — click action support, object-fit, caption.
- **DFileUpload.tsx** — drag-and-drop zone, base64 encoding, file type/size validation.
- **Stack.tsx** — direction "horizontal" + sticky prop + system padding.
- **usePanelDiscovery** — `get_oauth_url` excluded from chat echo. Compose as centerOverlay. `mergeListItems` for any container.
- **ExtensionPage** — ChatClient persists via CSS show/hide (reduces reload on email open/close).

### Mail DUI — Full Panel Migration
- 5 DUI panels: inbox (selectable, bulk actions, infinite scroll), email_viewer (sticky toolbar, Reply All, Gmail-style header), accounts, compose (BCC, Back button, Reply All CC pre-fill), add_account (3-step OAuth/IMAP wizard).
- 6 panel action handlers: mail_action, folder_counts, get_oauth_url, add_imap, compose_send, switch_account.
- Center overlay: email viewer and compose open in CENTER (chat moves right).
- **`_decode_body_with_type()`** — preserves raw HTML for panel viewer. Old `_decode_body()` kept for chat/LLM.
- **Full email body** — removed `body[:4000]` truncation in Google/Microsoft `read_email()`.
- **Image proxy** — `_proxy_images()` base64url-encodes URLs correctly.
- God file split: imap.py (839 to 4 files), helpers.py (500 to 4 files).

### Kernel Fix
- **`_serialize_result`** in `direct_call.py` — UINode returns in `ui` field (was `data`). Affects ALL extensions.

### Notes DUI — Full Panel Migration (v2.4.0)
- 2 DUI panels: sidebar (left — folders with counts, searchable note list, drag-drop, trash), editor (center overlay — TipTap RichEditor with auto-save).
- 1 panel handler: `note_save` (title/content/pin with targeted `refresh_panels`).
- Auto-open: sidebar returns `auto_action` on first load — frontend auto-opens most recent note.
- Markdown support: `_prepare_content()` detects plain text vs HTML, converts markdown via Python `markdown` library (extra, nl2br, sane_lists).
- Drag & drop: notes `draggable=True`, folders `droppable=True` with `on_drop=move_note`.
- Metadata: KeyValue display with Words, Created, Modified, Tags, ID.

### Generic Platform Improvements
- **`isCenterOverlay()` / `shouldClearOverlay()`** — extracted as generic functions in usePanelDiscovery (supports mail + notes + future extensions).
- **`auto_action`** — left panel root UINode can include `auto_action` prop; frontend auto-executes on first load via useEffect.
- **`overlayKey`** — counter in usePanelDiscovery, forces React remount of stateful components (TipTap) on overlay change.
- **`refresh_panels` from `ActionResult.data`** — usePanelDiscovery checks `result.data.refresh_panels` (was only checking top-level). Empty array = skip refresh.
- **Active item highlight** — usePanelDiscovery refreshes left panel with `active_note_id`/`active_message_id` context after opening centerOverlay.
- **ExtensionShell right panel** — shows when `rightSlot` provided even without `rightPanelCfg` (sensible defaults: 22% width).
- **DList paginator** — `mt-auto` ensures paginator always sticks to bottom even with few items.
- **Component count** — corrected from 53 to **55** (Html + Open were added in v1.5.0 but count wasn't updated).


## 1.4.0 (2026-04-13)

### Panel Discovery — Zero-Rebuild Registration
- **`config.ui` auto-publish** — kernel publishes `ext._panels` metadata to Auth GW config store after `loader.load()`. New extensions show panels automatically without Panel rebuild.
- **`panel_publish.py`** — new kernel module: `_build_ui_config()` groups panels by slot, merges refresh events; `maybe_publish_panels()` PUTs to Auth GW with MD5 hash dedup; `invalidate_publish_cache()` on hot-reload.
- **Dynamic frontend config** — `ExtensionPage.tsx` reads `config.ui` from Auth GW, builds `ShellConfig` dynamically. Hardcoded `CONFIGS` dict, `DISCOVERY_PANELS` list, and `LEFT_PANELS` set removed.
- **`@ext.panel()` kwargs** — `default_width`, `min_width`, `max_width` stored in `ext._panels` and published to `config.ui.panels.{slot}`.

### UI Test Suite
- **`test_ui.py`** — 50 tests covering all 55 UI components: serialization, props, defaults, actions, negative tests (TypeError on nonexistent props).
- **`test_panels.py`** — 10 tests for `@ext.panel()` decorator: tool registration, metadata storage, wrapper returns `{ui, panel_id}`, param passthrough, kwargs preservation.
- **Total: 309 tests** (was 249).

### DUI Component Polish
- **DToggle** — rewritten 1:1 with React standard (`w-9 h-5`, `translate-x-4`, `toBool()` for string boolean coercion in form defaults).
- **DStat** — renders Lucide icons properly via `icons[name]` import (was rendering icon name as text).
- **DSection** — added `py-1 px-0.5` spacing on title.
- **DList expanded content** — opens fully (removed `max-h-96` internal scroll).
- **ExtensionShell** — `overflow-x-hidden` on both panels, `p-4 overflow-y-auto` on right panel.

### Documentation
- **`ui-components.md` rewritten** — all 53 components with exact prop tables matching Python function signatures.
- Corrected: `Chart` param is `type` (serialized as `chart_type` in JSON), `Button` has no `icon_left`/`icon_right`, `Tabs` uses `{label, content}` with int `default_tab`.

## 1.3.0 (2026-04-11)

### New UI Components
- **`ui.SlideOver`** — side panel (title, subtitle, children, width sm/md/lg/xl, on_close)
- **`ui.RichEditor`** — TipTap rich text editor (content, placeholder, toolbar, on_save, on_change)
- **`ui.TagInput`** — tag/chip input with autocomplete and `grouped_by` for prefix grouping

### Enhanced Components
- **`ui.DataTable`** — `on_cell_edit` action for inline cell editing
- **`ui.DataColumn`** — `editable` and `edit_type` ("text"/"toggle") props
- **`ui.ListItem`** — `expandable` + `expanded_content` for collapsible inline content
- **`ui.Button`** — `size` (sm/md/lg) and `full_width` props

### Build & Marketplace
- **`imperal build`** — generates manifests with marketplace metadata merge

## 1.2.0 (2026-04-11)

### ChatExtension Split (6 files, all <300L)
- `chat/extension.py` — core ChatExtension class
- `chat/handler.py` — message handling loop
- `chat/guards.py` — KAV, intent guard, confirmation
- `chat/prompt.py` — system prompt builder
- `chat/filters.py` — context window management
- `chat/action_result.py` — ActionResult type

### Declarative UI — 43 Components
- **Layout (8):** Stack, Grid, Tabs, Page, Section, Row, Column, Accordion
- **Display (8):** Text, Icon, Header, Image, Code, Markdown, Empty, Divider
- **Interactive (6):** Button, Card, Menu, Dialog, Tooltip, Link
- **Input (9):** Input, Form, Select, MultiSelect, Toggle, Slider, DatePicker, FileUpload, TextArea
- **Data (11):** ListItem, List, DataColumn, DataTable, Stat, Stats, Badge, Avatar, Timeline, Tree, KeyValue
- **Feedback (5):** Alert, Progress, Chart, Loading, Error
- **Actions (3):** Call, Navigate, Send

### Extension Decorators
- **`@ext.panel()`** — registers `__panel__{id}` ToolDef + stores panel metadata
- **`@ext.widget()`** — registers `__widget__{id}` ToolDef
- **`@ext.webhook()`** — registers `__webhook__{path}` ToolDef
- **`ActionResult.ui`** — inline Declarative UI in chat responses

### Inter-Extension IPC
- **`ctx.extensions.call(app_id, method, **params)`** — direct in-process, kernel-mediated
- **`ctx.extensions.emit(event_type, data)`** — event broadcasting
- `ContextFactory.create_child()` — fork() semantics for child contexts

### Kernel Package Separation
- Runtime files moved to `imperal-kernel` package (internal, not on PyPI)

## 1.1.0 (2026-04-11)

### Declarative UI Module (Initial)
- **`from imperal_sdk import ui`** — first 16 components (Stack, Grid, Tabs, List, ListItem, Stat, Badge, Text, Avatar, DataTable, Button, Input, Icon, Card, Alert, Progress, Chart)
- **UINode** base class with `.to_dict()` serialization
- **UIAction** base class for Call, Navigate, Send

### Pydantic Fix
- **DirectCallWorkflow** — `func_def._pydantic_model` for PEP 563 compatibility
- Auto-detect Pydantic BaseModel params in `@chat.function` signatures

## 1.0.0 (2026-04-10)

### Typed Everything
- **Context** — typed `User`, `Tenant` dataclasses with `has_scope()`, `has_role()`
- **Client returns** — `Store→Document`, `AI→CompletionResult`, `Billing→LimitsResult`, `Storage→FileInfo`, `HTTP→HTTPResponse`
- **ChatResult + FunctionCall** — typed returns for ChatExtension._handle()
- **Page[T]** — cursor-based pagination with iteration support

### Extension Protocol & Validation
- **ExtensionProtocol** — formal interface for extensions
- **Validator** — 12 rules (V1 app_id, V2 version, V3 tools, V5 ActionResult return, V6 Pydantic params, V7 no direct LLM imports, V9 health check, etc.)
- **`imperal validate`** — CLI command for extension validation

### Extension Lifecycle
- **`@ext.on_install`**, **`@ext.on_upgrade(version)`**, **`@ext.on_uninstall`**, **`@ext.on_enable`**, **`@ext.on_disable`**
- **`@ext.health_check`** — health check endpoint
- **`@ext.on_event(event_type)`** — event handler registration
- **`@ext.expose(name, action_type)`** — inter-extension IPC method

### Testing
- **MockContext** — 10 mock clients for extension unit testing
- **`imperal init`** — project template updated to v1.0.0 pattern (ChatExtension + ActionResult)

### Error Hierarchy
- `ImperalError` → `AuthError`, `RateLimitError`, `StoreError`, `ConfigError`, `ExtensionError`

## 0.4.0 (2026-04-08)

### Multi-Model LLM Abstraction
- **LLMProvider** — unified multi-model provider with config resolution, client pool, automatic failover, per-call usage tracking
- **MessageAdapter** — Anthropic ↔ OpenAI message format translation
- **BYOLLM** — users bring their own LLM API keys (stored encrypted in ext_store)
- **Per-purpose routing** — different models for routing/execution/navigate
- **Per-extension override** — admin configures specific model per extension
- **Usage tracking** — Redis `imperal:llm_usage:{user_id}:{date}`
- **Zero direct anthropic imports** — all LLM calls through `get_llm_provider()`

## 0.3.0 (2026-04-08)

### ActionResult + Event Publishing
- **ActionResult** — universal return type with `.success()` / `.error()` factories
- **Event Publisher** — automatic kernel event publishing for write/destructive actions
- **Deterministic Truth Gate** — ActionResult.status as ground truth
- **Template Resolver** — `{{steps.N.data.*}}` variable passing for automation chains

## 0.2.0 (2026-04-03)

### ChatExtension + Hub Routing
- **ChatExtension** — single entry point with LLM routing for extensions
- **Hub LLM Routing** — embeddings optimize, LLM decides (multilingual)
- **Context Window Management** — 6 configurable guards
- **KAV** — Kernel Action Verification for write/destructive actions
- **2-Step Confirmation** — user approval for sensitive actions

## 0.1.0 (2026-04-02)

- Initial release: Extension, Context, Auth, Tool registration, SDK CLI stubs
