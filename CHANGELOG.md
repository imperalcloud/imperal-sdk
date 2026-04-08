# Changelog

## 0.3.0 — 2026-04-08

### Added
- `ActionResult` — universal return type for `@chat.function`
  - Factory methods: `.success(data, summary)` / `.error(msg, retryable)`
  - Serialization: `.to_dict()` / `.from_dict()` for Redis/JSON
  - Three-layer model: ActionResult (SDK) -> Event (Redis pub/sub) -> Action Record (billing DB)
- `event=` parameter on `@chat.function` decorator
  - Kernel auto-publishes events for successful write/destructive actions
  - Format: `{event_type: "app_id.event", data: ActionResult.data, context: {...}}`
- `event_publisher` module — `publish_kernel_event()` for Redis pub/sub
- `template_resolver` module — variable interpolation for automation steps
  - `resolve_template()` — replaces `{{path.to.var}}` with values
  - `resolve_dot_path()` — nested dict/list traversal with missing-field safety
  - `resolve_params()` — batch-resolve all string values in a params dict
  - Namespaces: `{{event.data.*}}`, `{{steps.N.data.*}}`, `{{prev.data.*}}`, `{{user.*}}`
- Hub Routing Architecture — embeddings as optimization, LLM as multilingual arbiter
  - Score >= 0.5 -> FAST PATH (direct dispatch, skip LLM, saves ~200ms)
  - Score < 0.5 -> LLM routing decides (Haiku handles ANY language)
  - LLM "none" -> navigate. Extension -> dispatch with `tool_choice="any"`
- Hub chain variable passing — `{{steps.N.data.*}}` templates resolved between chain steps
- Navigate proactive mode — skeleton data + time injected into navigate prompt

### Changed
- `ChatExtension._handle()` — validates ActionResult returns, stores in enriched `_functions_called`
- `FunctionDef` dataclass — added `event: str` field
- `_functions_called` entries — new `result` (ActionResult) and `event` (str) fields
- Executor Step 10b — kernel event publishing after extension returns
- Hub — `_routed_intent` propagated in result dict for fabrication detection
- Truth Gate — deterministic via ActionResult.status (zero LLM, any language)

## 0.2.0 — 2026-04-03

### Added
- `ctx.tools` — ToolsClient for inter-extension communication
  - `discover(query)` — semantic tool search via kernel
  - `call(activity_name, params)` — cross-extension calls with full RBAC
- `ctx.config` — ConfigClient for resolved config (read-only)
  - `get(key, default)` — dot-notation access
  - `get_section(section)` — full section dict
  - `all()` — complete resolved config
- `imperal deploy` — real deployment to Registry
  - Pushes tools with required_scopes + triggers embedding generation
  - Pushes config defaults via Registry Settings API
  - Validates manifest before deploy (descriptions, scope format)
- Credentials support (`.imperal/credentials` file + environment variables)
- `Extension(config_defaults=...)` — declare default config in code

### Changed
- Context object: added `tools` and `config` fields
- Manifest generation: includes `config_defaults` section

## 0.1.0 — 2026-04-01

### Added
- Initial release
- Extension framework with `@ext.tool()`, `@ext.signal()`, `@ext.schedule()`
- Context object with 8 platform clients (ai, store, storage, db, billing, notify, skeleton, http)
- Auth SDK (JWT verification, scopes, FastAPI middleware)
- CLI (`imperal init`, `dev`, `test`)
- Auto-generated manifests from code introspection
