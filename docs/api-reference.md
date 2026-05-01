# API Reference

**Last updated:** 2026-05-01 (SDK v3.7.0)

> **v3.7.0 additions** — `imperal_sdk.chat.guards.check_id_shape_fabrication`
> federal anti-hallucination guard; new error code `FABRICATED_ID_SHAPE`
> in `imperal_sdk.chat.error_codes.ERROR_TAXONOMY`. See
> [`extension-guidelines.md` § Anti-Hallucination](extension-guidelines.md#anti-hallucination-guards--what-your-extension-gets-for-free-v370).
**SDK version:** imperal-sdk 1.2.0
**Audience:** Extension developers building on Imperal Cloud

---

## Services

Imperal Cloud exposes two API surfaces:

| Service | Base URL | Purpose |
|---------|----------|---------|
| **Auth Gateway** | `https://auth.imperal.io` | Authentication, token issuance, user identity |
| **Registry** | `https://api.imperal.io/v1` | Extension management, tools, keys, settings, automations |

---

## Authentication

| Method | Header | Use case |
|--------|--------|----------|
| JWT Bearer token | `Authorization: Bearer <jwt>` | User-facing applications (Panel, CLI) |
| API key | `x-api-key: imp_live_xxx` | Extension workers, server-to-server |
| Registry admin key | `x-api-key: imp_reg_key_xxx` | Administrative Registry operations |

---

## Error Format

All error responses follow a consistent structure:

```json
{
    "error": "human_readable_error_code",
    "message": "Detailed description of what went wrong.",
    "status": 404
}
```

| HTTP Status | Error Code | Description |
|------------|------------|-------------|
| 400 | `invalid_request` | Malformed request or missing required fields |
| 401 | `unauthorized` | Missing or invalid credentials |
| 403 | `forbidden` | Valid credentials but insufficient permissions |
| 404 | `not_found` | Resource does not exist |
| 409 | `conflict` | Resource already exists |
| 422 | `validation_error` | Request fails schema validation |
| 429 | `rate_limited` | Too many requests (see `Retry-After` header) |
| 500 | `internal_error` | Server error |

---

# Auth Gateway

**Base URL:** `https://auth.imperal.io`

---

## POST /auth/register

Create a new user account. Sends a verification email.

```bash
curl -X POST https://auth.imperal.io/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dev@example.com",
    "password": "secure-password-12",
    "name": "Jane Doe"
  }'
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | Yes | Unique email address |
| `password` | string | Yes | Minimum 12 characters |
| `name` | string | Yes | Display name |
| `tenant_id` | string | No | Join an existing tenant (requires invitation) |

**Response (201):**

```json
{
    "id": "imp_u_9p4k7m2x",
    "email": "dev@example.com",
    "name": "Jane Doe",
    "tenant_id": "imp_t_auto_7x3k",
    "status": "pending_verification",
    "message": "Verification email sent."
}
```

| Error | When |
|-------|------|
| 409 | Email already registered |
| 422 | Password does not meet requirements |

---

## POST /auth/verify

Verify an email address with the token from the verification email.

```bash
curl -X POST https://auth.imperal.io/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"token": "verification-token-from-email"}'
```

**Response (200):**

```json
{
    "message": "Email verified. You can now log in.",
    "user_id": "imp_u_9p4k7m2x"
}
```

---

## POST /auth/login

Authenticate with email and password. Returns JWT tokens.

```bash
curl -X POST https://auth.imperal.io/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dev@example.com",
    "password": "secure-password-12"
  }'
```

**Response (200):**

```json
{
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "user": {
        "id": "imp_u_7k3m9x2p",
        "email": "dev@example.com",
        "tenant_id": "imp_t_4n8r2v6q",
        "role": "admin",
        "scopes": ["cases:read", "cases:write", "billing:read"]
    }
}
```

| Error | When |
|-------|------|
| 401 | Invalid credentials |
| 429 | Too many login attempts (5 per minute per IP) |

---

## POST /auth/refresh

Exchange a refresh token for a new access token.

```bash
curl -X POST https://auth.imperal.io/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJSUzI1NiIs..."}'
```

**Response (200):**

```json
{
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 3600
}
```

| Error | When |
|-------|------|
| 401 | Refresh token expired or revoked |

---

## POST /auth/logout

Revoke the current session. Invalidates both access and refresh tokens.

```bash
curl -X POST https://auth.imperal.io/auth/logout \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIs..."
```

**Response (200):**

```json
{
    "message": "Session revoked."
}
```

---

## GET /auth/me

Return the authenticated user's profile. Includes `cases_user_id` (nullable) -- the Cases API user ID, stored in the auth gateway DB as single source of truth.

```bash
curl https://auth.imperal.io/auth/me \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIs..."
```

**Response (200):**

```json
{
    "id": "imp_u_7k3m9x2p",
    "email": "dev@example.com",
    "tenant_id": "imp_t_4n8r2v6q",
    "role": "admin",
    "scopes": ["cases:read", "cases:write", "billing:read"],
    "cases_user_id": 3,
    "created_at": "2026-01-15T08:00:00Z",
    "last_login_at": "2026-04-01T14:22:00Z"
}
```

---

## PATCH /auth/users/{id}/cases-uid

Set the Cases API user ID for a user. Called by the Panel on first login after auto-provisioning. Requires Bearer token (admin or self).

```bash
curl -X PATCH https://auth.imperal.io/auth/users/imp_u_7k3m9x2p/cases-uid \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{"cases_user_id": 3}'
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cases_user_id` | integer | Yes | Cases API user ID |

**Response (200):**

```json
{
    "message": "cases_user_id updated",
    "user_id": "imp_u_7k3m9x2p",
    "cases_user_id": 3
}
```

| Error | When |
|-------|------|
| 400 | Missing or invalid `cases_user_id` |
| 401 | Not authenticated |
| 404 | User not found |

---

## POST /auth/api-keys/validate

Validate an API key and return associated metadata. Used internally by the platform to authenticate extension workers.

```bash
curl -X POST https://auth.imperal.io/auth/api-keys/validate \
  -H "Content-Type: application/json" \
  -d '{"api_key": "imp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}'
```

**Response (200, valid key):**

```json
{
    "valid": true,
    "app_id": "threat-intel",
    "scope": "full",
    "tenant_id": "imp_t_4n8r2v6q",
    "owner_id": "imp_u_7k3m9x2p"
}
```

**Response (200, invalid key):**

```json
{
    "valid": false,
    "error": "Key not found or revoked."
}
```

---

## POST /auth/forgot-password

Initiate a password reset. Sends a reset link to the email.

```bash
curl -X POST https://auth.imperal.io/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@example.com"}'
```

**Response (200):**

```json
{
    "message": "If the email exists, a reset link has been sent."
}
```

---

## POST /auth/reset-password

Reset the password using a token from the reset email.

```bash
curl -X POST https://auth.imperal.io/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{
    "token": "reset-token-from-email",
    "new_password": "new-secure-password-12"
  }'
```

**Response (200):**

```json
{
    "message": "Password updated. All existing sessions have been revoked."
}
```

---

## Auth Gateway Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /auth/login` | 5 | per minute per IP |
| `POST /auth/register` | 3 | per minute per IP |
| `POST /auth/forgot-password` | 3 | per minute per IP |
| `POST /auth/refresh` | 30 | per minute per user |
| `GET /auth/me` | 60 | per minute per user |
| `POST /auth/api-keys/validate` | 120 | per minute |

---

# Registry API

**Base URL:** `https://api.imperal.io/v1`

---

## Apps

### POST /v1/apps

Create a new application.

```bash
curl -X POST https://api.imperal.io/v1/apps \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{
    "app_id": "threat-intel",
    "display_name": "Threat Intelligence Hub",
    "owner_id": 42,
    "config": {"primary_model": "claude-sonnet-4-6"}
  }'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app_id` | string | Yes | Unique identifier. Lowercase, alphanumeric, hyphens. 3-50 chars. |
| `display_name` | string | Yes | Human-readable name. 1-100 chars. |
| `owner_id` | integer | Yes | Owner user ID |
| `config` | object | No | App configuration |

**Response (201):**

```json
{
    "app_id": "threat-intel",
    "display_name": "Threat Intelligence Hub",
    "owner_id": 42,
    "namespace": "app-threat-intel",
    "status": "provisioning",
    "config": {"primary_model": "claude-sonnet-4-6"},
    "created_at": "2026-04-01T10:00:00Z",
    "updated_at": "2026-04-01T10:00:00Z"
}
```

| Error | When |
|-------|------|
| 409 | `app_id` already exists |
| 400 | Invalid `app_id` format |

---

### GET /v1/apps

List apps. Optional filters: `status` (`provisioning`, `active`, `suspended`, `deleted`, `all`), `owner_id`.

```bash
curl "https://api.imperal.io/v1/apps?status=active" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

**Response (200):**

```json
{
    "apps": [{
        "app_id": "threat-intel",
        "display_name": "Threat Intelligence Hub",
        "owner_id": 42,
        "namespace": "app-threat-intel",
        "status": "active",
        "created_at": "2026-04-01T10:00:00Z"
    }],
    "total": 1
}
```

---

### GET /v1/apps/{app_id}

Get a single app.

```bash
curl https://api.imperal.io/v1/apps/threat-intel \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

---

### PATCH /v1/apps/{app_id}

Partial update. Only provided fields change.

| Field | Type | Description |
|-------|------|-------------|
| `display_name` | string | New name |
| `status` | string | `active` or `suspended` |
| `config` | object | Replaces entire config |

```bash
curl -X PATCH https://api.imperal.io/v1/apps/threat-intel \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"display_name": "Threat Intel Pro"}'
```

---

### DELETE /v1/apps/{app_id}

Soft-delete. Data retained for 30 days.

```bash
curl -X DELETE https://api.imperal.io/v1/apps/threat-intel \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

**Response (200):**

```json
{
    "app_id": "threat-intel",
    "status": "deleted",
    "message": "App soft-deleted. Data retained for 30 days."
}
```

---

## API Keys

### POST /v1/apps/{app_id}/keys

Generate a new API key. The full key is returned **only once** in this response.

```bash
curl -X POST https://api.imperal.io/v1/apps/threat-intel/keys \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"scope": "full"}'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scope` | string | Yes | `"full"` or `"readonly"` |

**Response (201):**

```json
{
    "key_id": "key_8f3a2b1c",
    "api_key": "imp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "prefix": "imp_live_tI9x",
    "scope": "full",
    "created_at": "2026-04-01T10:00:00Z",
    "warning": "Store this key securely. It will not be shown again."
}
```

Key format: `imp_live_{32_random_alphanumeric_chars}`.

---

### GET /v1/apps/{app_id}/keys

List API keys. Only prefixes are returned for security.

```bash
curl https://api.imperal.io/v1/apps/threat-intel/keys \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

**Response (200):**

```json
{
    "keys": [{
        "key_id": "key_8f3a2b1c",
        "prefix": "imp_live_tI9x",
        "scope": "full",
        "created_at": "2026-04-01T10:00:00Z",
        "last_used_at": "2026-04-01T14:22:00Z"
    }],
    "total": 1
}
```

---

### DELETE /v1/apps/{app_id}/keys/{key_id}

Revoke immediately and irreversibly.

```bash
curl -X DELETE https://api.imperal.io/v1/apps/threat-intel/keys/key_8f3a2b1c \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

**Response (200):**

```json
{
    "key_id": "key_8f3a2b1c",
    "status": "revoked"
}
```

---

## Tools and Skeleton

### PUT /v1/apps/{app_id}/tools

Full sync of tools and skeleton sections. Replaces the entire configuration. Omitted tools are removed.

```bash
curl -X PUT https://api.imperal.io/v1/apps/threat-intel/tools \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{
    "version": "1.0.0",
    "tools": [
        {
            "activity": "search_threat_db",
            "name": "search_threats",
            "description": "Search the threat intelligence database",
            "domains": ["threats", "intelligence"]
        }
    ],
    "skeleton_sections": [
        {
            "name": "active_threats",
            "refresh_activity": "refresh_active_threats",
            "alert_activity": "alert_new_threat",
            "ttl": 300,
            "alert_on_change": true
        }
    ]
  }'
```

**Tool object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `activity` | string | Yes | Worker activity name |
| `name` | string | Yes | Tool name for the LLM |
| `description` | string | Yes | Tool description for the LLM |
| `domains` | array[string] | Yes | 1-3 domain tags |

**Skeleton section object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Section identifier |
| `refresh_activity` | string | Yes | Activity that fetches data |
| `alert_activity` | string | No | Activity that runs on change |
| `ttl` | integer | Yes | Refresh interval in seconds |
| `alert_on_change` | boolean | Yes | Enable change detection |

**Response (200):**

```json
{
    "app_id": "threat-intel",
    "tools_count": 1,
    "skeleton_sections_count": 1,
    "status": "active",
    "domains": ["threats", "intelligence"]
}
```

---

### GET /v1/apps/{app_id}/tools

Returns the current tool and skeleton configuration.

```bash
curl https://api.imperal.io/v1/apps/threat-intel/tools \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

---

## Settings

### GET /v1/apps/{app_id}/settings

Full configuration merged with platform defaults.

```bash
curl https://api.imperal.io/v1/apps/my-app/settings \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

**Response (200):**

```json
{
    "general": {},
    "models": {
        "primary_model": "claude-sonnet-4-6",
        "intake_model": "gpt-4o-mini",
        "analysis_model": "claude-opus-4-6",
        "router_model": "gpt-4o-mini",
        "temperature": 0.7,
        "max_tokens": 2048
    },
    "persona": {
        "system_prompt_intake": "",
        "system_prompt_intelligence": "",
        "language": "auto",
        "tone": "formal",
        "use_emojis": false,
        "cite_sources": true
    },
    "alerts": {"enabled": true, "cooldown_seconds": 60, "max_per_hour": 10},
    "router": {"enabled": true, "timeout_ms": 3000, "fallback": "first_tool"},
    "session": {"timeout_hours": 24, "max_history": 40, "compress_at": 30, "history_ttl_days": 7},
    "monitoring": {"tracing_enabled": true}
}
```

---

### PUT /v1/apps/{app_id}/settings

Partial update with deep merge.

```bash
curl -X PUT https://api.imperal.io/v1/apps/my-app/settings \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"models": {"temperature": 0.5}}'
```

**Response (200):**

```json
{
    "message": "Settings updated",
    "updated_sections": ["models"],
    "skeleton_reloaded": true
}
```

**Notes:**
- Only the provided fields are merged. Omitted sections remain unchanged.
- When the `skeleton` section is updated, the running skeleton worker is signaled for live reload.

---

## Automations

### GET /v1/users/{user_id}/automations

Returns user automation rules (per-section TTL overrides, alert toggles).

```bash
curl https://api.imperal.io/v1/users/42/automations \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx"
```

**Response (200):**

```json
{
    "automations": [{
        "user_id": 42,
        "app_id": "case-manager",
        "section_name": "case_status",
        "enabled": true,
        "ttl": 30,
        "alert_config": {"notify_on_change": true, "cooldown_seconds": 120}
    }]
}
```

---

### PUT /v1/users/{user_id}/automations

Full sync. Replaces all rules for the user.

```bash
curl -X PUT https://api.imperal.io/v1/users/42/automations \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{
    "automations": [{
        "app_id": "case-manager",
        "section_name": "case_status",
        "enabled": true,
        "ttl": 30,
        "alert_config": {"notify_on_change": true, "cooldown_seconds": 120}
    }]
  }'
```

**Automation rule object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app_id` | string | Yes | Extension identifier |
| `section_name` | string | Yes | Skeleton section name |
| `enabled` | boolean | Yes | Whether the rule is active |
| `ttl` | integer | No | Refresh interval in seconds (writes to `app_skeleton_config.ttl`) |
| `alert_config` | object | No | `notify_on_change` (bool), `cooldown_seconds` (int) |

**Response (200):**

```json
{
    "message": "Automations saved",
    "rules_count": 1,
    "skeleton_reloaded": true
}
```

---

## Hub

### POST /v1/hub/{user_id}/messages

Send a message to the user's hub session. The hub merges tools from all active extensions.

```bash
curl -X POST https://api.imperal.io/v1/hub/42/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"content": "Show me my active cases", "context": {}}'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | Message text |
| `context` | object | No | Metadata (e.g., `case_id`) |

**Response (202):**

```json
{
    "status": "signaled",
    "namespace": "imperal-hub",
    "workflow_id": "personal-42"
}
```

---

## Registry Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `POST /v1/apps` | 10 | per minute |
| `GET /v1/apps` | 60 | per minute |
| `PUT /v1/apps/{app_id}/tools` | 30 | per minute |
| `POST /v1/apps/{app_id}/keys` | 5 | per minute |
| `POST /v1/hub/{user_id}/messages` | 60 | per minute |
| All other endpoints | 60 | per minute |

Rate-limited responses include a `Retry-After` header.

---

## Full Workflow Example

Complete sequence from account creation to sending a message:

```bash
# 1. Register
curl -X POST https://auth.imperal.io/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@example.com", "password": "secure-password-12", "name": "Dev"}'

# 2. Verify email (token from email)
curl -X POST https://auth.imperal.io/auth/verify \
  -H "Content-Type: application/json" \
  -d '{"token": "verification-token"}'

# 3. Login
curl -X POST https://auth.imperal.io/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@example.com", "password": "secure-password-12"}'

# 4. Create app
curl -X POST https://api.imperal.io/v1/apps \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"app_id": "my-app", "display_name": "My App", "owner_id": 1}'

# 5. Create API key
curl -X POST https://api.imperal.io/v1/apps/my-app/keys \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"scope": "full"}'

# 6. Deploy tools (or use: imperal deploy)
curl -X PUT https://api.imperal.io/v1/apps/my-app/tools \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"tools": [{"activity": "greet", "name": "greet", "description": "Greet the user", "domains": ["general"]}]}'

# 7. Send a message
curl -X POST https://api.imperal.io/v1/hub/1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxxxxxxxxxxxxxxx" \
  -d '{"content": "Hello!", "context": {}}'
```

---

---

# Store Internal API

**Base URL:** `http://internal-gateway:8085/v1/internal/store` (Auth Gateway, `auth.imperal.io:8085`)

The Store API provides persistent document storage for extensions via `ctx.store`. These endpoints are **internal only** -- they are blocked from public access via nginx and require a service token for authentication. The Store API runs on the Auth Gateway alongside all other `ctx.*` backends (ai, skeleton, notify, storage).

All requests must include the `X-Service-Token` header. The platform worker provides this token automatically when executing extension code. Extension developers interact with the store through `ctx.store` methods and never call these endpoints directly.

---

## Authentication

| Header | Value | Description |
|--------|-------|-------------|
| `X-Service-Token` | Platform service token | Required on all requests. Issued to platform workers, not to extension developers. |

---

## POST /v1/internal/store

Create a new document in a collection.

```bash
curl -X POST http://internal-gateway:8085/v1/internal/store \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: <service-token>" \
  -d '{
    "tenant_id": "imp_t_4n8r2v6q",
    "app_id": "my-extension",
    "collection": "notes",
    "data": {"text": "Meeting notes", "priority": "high"}
  }'
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | string | Yes | Tenant identifier |
| `app_id` | string | Yes | Extension identifier |
| `collection` | string | Yes | Collection name (table created automatically on first write) |
| `data` | object | Yes | Document payload (JSON-serializable, max 1 MB) |

**Response (201):**

```json
{
    "id": "doc_8f3a2b1c",
    "collection": "notes",
    "created_at": "2026-04-01T10:00:00Z"
}
```

---

## GET /v1/internal/store/{collection}/{doc_id}

Retrieve a document by ID.

```bash
curl http://internal-gateway:8085/v1/internal/store/notes/doc_8f3a2b1c \
  -H "X-Service-Token: <service-token>" \
  -H "X-Tenant-Id: imp_t_4n8r2v6q" \
  -H "X-App-Id: my-extension"
```

**Response (200):**

```json
{
    "_id": "doc_8f3a2b1c",
    "text": "Meeting notes",
    "priority": "high",
    "created_at": "2026-04-01T10:00:00Z",
    "updated_at": "2026-04-01T10:00:00Z"
}
```

| Error | When |
|-------|------|
| 404 | Document not found or soft-deleted |

---

## POST /v1/internal/store/{collection}/query

Query documents with optional filtering, sorting, and pagination.

```bash
curl -X POST http://internal-gateway:8085/v1/internal/store/notes/query \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: <service-token>" \
  -d '{
    "tenant_id": "imp_t_4n8r2v6q",
    "app_id": "my-extension",
    "filter": {"priority": "high"},
    "sort": "-created_at",
    "limit": 20
  }'
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | string | Yes | Tenant identifier |
| `app_id` | string | Yes | Extension identifier |
| `filter` | object | No | JSON equality filters on document fields |
| `sort` | string | No | Sort field. Prefix with `-` for descending. |
| `limit` | integer | No | Maximum results (default: 100) |

**Response (200):**

```json
{
    "documents": [
        {"_id": "doc_8f3a2b1c", "text": "Meeting notes", "priority": "high", "created_at": "..."}
    ],
    "total": 1
}
```

**Notes:**
- Soft-deleted documents are excluded from query results automatically.

---

## PATCH /v1/internal/store/{collection}/{doc_id}

Partial update of an existing document.

```bash
curl -X PATCH http://internal-gateway:8085/v1/internal/store/notes/doc_8f3a2b1c \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: <service-token>" \
  -d '{
    "tenant_id": "imp_t_4n8r2v6q",
    "app_id": "my-extension",
    "data": {"priority": "low"}
  }'
```

**Response (200):**

```json
{
    "_id": "doc_8f3a2b1c",
    "updated_at": "2026-04-01T11:00:00Z"
}
```

| Error | When |
|-------|------|
| 404 | Document not found or soft-deleted |

---

## DELETE /v1/internal/store/{collection}/{doc_id}

Soft-delete a document. Sets `deleted_at` timestamp. The document is excluded from future queries and counts but retained in the database for audit purposes.

```bash
curl -X DELETE http://internal-gateway:8085/v1/internal/store/notes/doc_8f3a2b1c \
  -H "X-Service-Token: <service-token>" \
  -H "X-Tenant-Id: imp_t_4n8r2v6q" \
  -H "X-App-Id: my-extension"
```

**Response (200):**

```json
{
    "_id": "doc_8f3a2b1c",
    "deleted_at": "2026-04-01T12:00:00Z"
}
```

---

## POST /v1/internal/store/{collection}/count

Count documents matching a filter.

```bash
curl -X POST http://internal-gateway:8085/v1/internal/store/notes/count \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: <service-token>" \
  -d '{
    "tenant_id": "imp_t_4n8r2v6q",
    "app_id": "my-extension",
    "filter": {"priority": "high"}
  }'
```

**Response (200):**

```json
{
    "count": 7
}
```

**Notes:**
- Soft-deleted documents are excluded from counts.

---

## Store API Notes

- **Access control:** All Store API endpoints are blocked from public access via nginx. Only platform workers with a valid service token can reach them.
- **Auto-table creation:** Collections (tables) are created automatically in the tenant's database on first write. No schema migration required.
- **Soft deletes:** DELETE operations set `deleted_at` rather than removing data. An audit trail is maintained for all mutations.
- **Connection pooling:** The platform worker maintains persistent HTTP connection pools to the Store API for performance.
- **Tenant isolation:** Every request is scoped to a `(tenant_id, app_id)` pair. Cross-tenant access is impossible at the API level.

---

# AI Completion Internal API

**Base URL:** `http://internal-gateway:8085/v1/internal/ai`

The AI Completion API provides LLM access for extensions via `ctx.ai`. These endpoints are **internal only** -- blocked from public access via nginx and requiring a service token. The gateway routes to OpenAI (`gpt-*` models) or Anthropic (`claude-*` models) based on the model parameter prefix. Both `openai` and `anthropic` Python packages are installed in the platform worker environment. All usage is automatically metered against the tenant's subscription.

---

## POST /v1/internal/ai/complete

Proxy a completion request to the configured LLM provider.

```bash
curl -X POST http://internal-gateway:8085/v1/internal/ai/complete \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: <service-token>" \
  -d '{
    "user_id": "imp_u_7k3m9x2p",
    "tenant_id": "imp_t_4n8r2v6q",
    "prompt": "Summarize the following document...",
    "model": "gpt-4o-mini",
    "max_tokens": 512,
    "temperature": 0.3
  }'
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | Yes | User ID for metering |
| `tenant_id` | string | Yes | Tenant ID for metering and limits |
| `prompt` | string | No | Single-turn prompt (mutually exclusive with `messages`) |
| `messages` | array | No | Multi-turn chat messages (mutually exclusive with `prompt`) |
| `model` | string | No | Model name. `gpt-*` routes to OpenAI, `claude-*` routes to Anthropic. Default: platform default. |
| `max_tokens` | int | No | Max output tokens (default: 2048) |
| `temperature` | float | No | Sampling temperature (default: 0.7) |

**Response (200):**

```json
{
    "text": "The generated completion text...",
    "model": "gpt-4o-mini",
    "usage": {
        "input": 150,
        "output": 85
    }
}
```

| Error | When |
|-------|------|
| 400 | Neither `prompt` nor `messages` provided |
| 401 | Invalid service token |
| 403 | External access (blocked by nginx) |
| 429 | Tenant AI token limit reached |

---

# Skeleton Internal API

**Base URL:** `http://internal-gateway:8085/v1/internal/skeleton`

Redis-based skeleton read/write endpoints for the SDK's `ctx.skeleton` interface. Data is stored in Redis with per-section TTL management. These endpoints are **internal only** -- blocked from public access via nginx and requiring a service token.

---

## GET /v1/internal/skeleton/{user_id}/{section}

Read a skeleton section from Redis.

```bash
curl "http://internal-gateway:8085/v1/internal/skeleton/imp_u_7k3m9x2p/recent_cases?app_id=my-extension" \
  -H "X-Service-Token: <service-token>"
```

**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `app_id` | string | Yes | Extension that owns the section |

**Response (200):**

```json
{
    "section": "recent_cases",
    "data": {"count": 5, "cases": [{"id": "doc_123", "title": "Case A"}]},
    "ttl": 540
}
```

**Response (200, empty section):**

```json
{
    "section": "recent_cases",
    "data": {},
    "ttl": -1
}
```

---

## PUT /v1/internal/skeleton/{user_id}/{section}

Write data to a skeleton section in Redis.

```bash
curl -X PUT http://internal-gateway:8085/v1/internal/skeleton/imp_u_7k3m9x2p/recent_cases \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: <service-token>" \
  -d '{
    "app_id": "my-extension",
    "data": {"count": 5, "cases": [{"id": "doc_123", "title": "Case A"}]},
    "ttl": 120
  }'
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app_id` | string | Yes | Extension that owns the section |
| `data` | object | Yes | Section data (max 64 KB) |
| `ttl` | int | No | TTL in seconds (default: from skeleton config) |

**Response (200):**

```json
{
    "section": "recent_cases",
    "status": "updated"
}
```

---

# Notify Internal API

**Base URL:** `http://internal-gateway:8085/v1/internal/notify`

Notification queue endpoint for the SDK's `ctx.notify` interface. Notifications are pushed to a Redis list (`imperal:notifications:{user_id}`) and consumed by the delivery service. These endpoints are **internal only** -- blocked from public access via nginx and requiring a service token.

---

## POST /v1/internal/notify

Queue a notification for delivery to the user.

```bash
curl -X POST http://internal-gateway:8085/v1/internal/notify \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: <service-token>" \
  -d '{
    "user_id": "imp_u_7k3m9x2p",
    "tenant_id": "imp_t_4n8r2v6q",
    "title": "Case Update",
    "body": "Case 42 analysis is complete.",
    "priority": "high",
    "source": "my-extension"
  }'
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | Yes | Target user |
| `tenant_id` | string | Yes | Tenant |
| `title` | string | Yes | Notification title |
| `body` | string | Yes | Notification body |
| `priority` | string | No | `low`, `normal` (default), `high`, `urgent` |
| `source` | string | No | Extension or system that generated the notification |

**Response (201):**

```json
{
    "notification_id": "ntf_abc123",
    "status": "queued"
}
```

---

# Storage Internal API

**Base URL:** `http://internal-gateway:8085/v1/internal/storage`

Filesystem-based file storage endpoints for the SDK's `ctx.storage` interface. Files are stored at `/opt/imperal-storage/{tenant_id}/{extension_id}/{path}`. These endpoints are **internal only** -- blocked from public access via nginx and requiring a service token.

---

## POST /v1/internal/storage/upload

Upload a file.

```bash
curl -X POST http://internal-gateway:8085/v1/internal/storage/upload \
  -H "X-Service-Token: <service-token>" \
  -F "tenant_id=imp_t_4n8r2v6q" \
  -F "extension_id=my-extension" \
  -F "path=exports/report.pdf" \
  -F "data=@report.pdf" \
  -F "content_type=application/pdf"
```

**Request:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | string | Yes | Tenant |
| `extension_id` | string | Yes | Extension |
| `path` | string | Yes | File path within the extension's namespace |
| `data` | binary | Yes | File content (multipart form data) |
| `content_type` | string | No | MIME type (default: `application/octet-stream`) |

**Response (201):**

```json
{
    "path": "exports/report.pdf",
    "url": "https://auth.imperal.io/v1/internal/storage/download?tenant_id=...&path=exports/report.pdf",
    "size_bytes": 145832
}
```

| Error | When |
|-------|------|
| 413 | File exceeds 100 MB limit |

---

## GET /v1/internal/storage/download

Download a file by path.

**Query parameters:** `tenant_id`, `extension_id`, `path` (all required).

---

## DELETE /v1/internal/storage

Delete a file.

**Query parameters:** `tenant_id`, `extension_id`, `path` (all required).

---

## GET /v1/internal/storage/list

List files matching a prefix.

**Query parameters:** `tenant_id`, `extension_id`, `prefix` (optional, defaults to `""`).

**Response (200):**

```json
{
    "files": [
        "exports/report.pdf",
        "exports/summary.csv"
    ]
}
```

---

## Internal API Notes

All internal API endpoints (`/v1/internal/*`) share the following properties:

- **Service token authentication.** All requests require `X-Service-Token` header. User JWTs cannot access these endpoints.
- **Nginx blocks external access.** The `/v1/internal/*` path returns 403 for requests from outside the internal network.
- **Kernel RBAC is defense-in-depth.** `_execute_extension` checks `required_scopes` against `kctx.scopes` (pre-resolved via KernelContext). This is a second layer after Auth Gateway API-level RBAC — both must pass. Identity resolution happens ONCE per message in `resolve_kernel_context` activity, not per-tool-call.
- **Persistent connection pools.** The platform worker maintains HTTP connection pools to all internal APIs for performance.

---

## Related Documentation

- [Quickstart](quickstart.md) -- Build and deploy your first extension
- [Tools](tools.md) -- Writing tool implementations
- [Skeleton](skeleton.md) -- Skeleton section configuration
- [Concepts](concepts.md) -- Architecture, identity, storage tiers
