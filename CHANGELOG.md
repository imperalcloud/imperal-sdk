# Changelog

All notable changes to `imperal-sdk` are documented here.

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
