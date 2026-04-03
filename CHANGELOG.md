# Changelog

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
