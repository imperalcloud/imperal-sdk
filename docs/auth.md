# Auth SDK — Imperal Authentication for Python

**SDK version:** imperal-sdk 1.5.7
**Last updated:** 2026-04-18

The Imperal Auth SDK provides JWT token verification, user identity, scope-based access control, and FastAPI middleware. It works in two modes: **automatic** (inside extensions, auth is transparent) and **standalone** (protect any Python service with Imperal Auth).

Part of the `imperal-sdk` package.

---

## Installation

```bash
# Core (token verification, User, scopes)
pip install imperal-sdk

# With FastAPI middleware support
pip install imperal-sdk[fastapi]
```

---

## Quick Start — Verify a Token in 5 Lines

```python
from imperal_sdk.auth import ImperalAuth

auth = ImperalAuth()  # defaults to https://auth.imperal.io
user = auth.verify(token)

print(user.imperal_id, user.email, user.role, user.scopes)
```

That's it. `verify()` fetches the public key from the JWKS endpoint, validates the RS256 signature, checks expiration, and returns a `User` object. Keys are cached for 1 hour.

---

## For Extension Developers

If you're building an Imperal Cloud extension, **authentication is automatic**. The platform injects an authenticated `Context` with `ctx.user` already populated from the JWT token. You never call `ImperalAuth` directly.

### Accessing the User

```python
from imperal_sdk import Extension

ext = Extension("my-extension")

@ext.tool("my-tool", scopes=["cases:read"])
async def my_tool(ctx) -> dict:
    # ctx.user is already authenticated
    user = ctx.user
    return {"response": f"Hello {user.email}, your role is {user.role}"}
```

### Scope-Based Tool Access

The `scopes` parameter on `@ext.tool()` declares what permissions the tool requires. The platform checks these before the tool is even called:

```python
# Only users with cases:write scope can call this
@ext.tool("create-case", scopes=["cases:write"])
async def create_case(ctx, title: str) -> dict:
    ...

# Multiple scopes — user must have ALL of them
@ext.tool("admin-report", scopes=["cases:read", "admin:reports"])
async def admin_report(ctx) -> dict:
    ...
```

### Manual Scope Checks

For fine-grained control within a tool:

```python
@ext.tool("case-action", scopes=["cases:read"])
async def case_action(ctx, action: str) -> dict:
    if action == "delete" and not ctx.user.has_scope("cases:delete"):
        return {"response": "You don't have permission to delete cases."}
    ...
```

---

## For Service Developers (Standalone)

If you're building your own service (API, microservice, webhook handler) and want to authenticate users via Imperal Auth, use the SDK directly.

### Protect a FastAPI Endpoint

```python
from fastapi import FastAPI, Depends
from imperal_sdk.auth import ImperalAuth
from imperal_sdk.auth.middleware import require_auth, require_scope

app = FastAPI()

# Any authenticated user
@app.get("/profile")
async def profile(user=Depends(require_auth())):
    return {"id": user.imperal_id, "email": user.email, "role": user.role}

# Requires specific scope
@app.get("/admin/users")
async def admin_users(user=Depends(require_scope("admin:users"))):
    return {"message": f"Welcome admin {user.email}"}

# Multiple required scopes
@app.get("/admin/billing")
async def admin_billing(user=Depends(require_scope("admin:users", "billing:read"))):
    return {"message": "Billing data"}
```

The middleware extracts the `Bearer` token from the `Authorization` header, verifies it via JWKS, and returns a `User` object. On failure, it raises `HTTPException(401)` or `HTTPException(403)`.

### Custom Gateway URL

For development or self-hosted environments:

```python
from imperal_sdk.auth import ImperalAuth
from imperal_sdk.auth.middleware import require_auth

# Point to a different auth gateway
auth = ImperalAuth(gateway_url="http://localhost:8085")

@app.get("/protected")
async def protected(user=Depends(require_auth(auth=auth))):
    return {"user": user.imperal_id}
```

### Direct Token Verification (No FastAPI)

```python
from imperal_sdk.auth import ImperalAuth, AuthError

auth = ImperalAuth()

try:
    user = auth.verify(token)
    print(f"Authenticated: {user.imperal_id} ({user.role})")
    print(f"Scopes: {user.scopes}")
except AuthError as e:
    print(f"Authentication failed: {e}")
```

### Get Full User Info from Auth Gateway

```python
# Returns the full user profile from the auth gateway
user_info = await auth.get_user_info(token)
# {"id": "...", "email": "...", "role": "...", "scopes": [...], ...}
```

---

## Auth Flow

```
Client (browser/app/extension)
    │
    ├── POST /v1/auth/login  →  Auth Gateway (auth.imperal.io)
    │                                │
    │   ← JWT access_token ──────────┘
    │
    ├── GET /api/data  ──────→  Your Service
    │   Authorization: Bearer <token>     │
    │                                     │
    │                              ImperalAuth.verify(token)
    │                                     │
    │                              Fetch JWKS public key
    │                              (cached 1 hour)
    │                                     │
    │                              Validate RS256 signature
    │                              Check expiration
    │                              Extract claims → User object
    │                                     │
    │   ← Response ──────────────────────┘
```

**Token lifecycle:**
1. User logs in via `POST /v1/auth/login` → receives `access_token` (JWT, 15min) + `refresh_token`
2. Client sends `Authorization: Bearer <access_token>` with every request
3. Your service calls `ImperalAuth.verify(token)` → gets `User` object
4. When token expires, client calls `POST /v1/auth/refresh` with the refresh token

---

## API Reference

### `ImperalAuth`

```python
class ImperalAuth:
    def __init__(self, gateway_url: str = "https://auth.imperal.io")
```

JWT token verification client. Fetches public keys from the JWKS endpoint and caches them for 1 hour.

| Method | Description |
|--------|-------------|
| `verify(token: str) -> User` | Verify JWT, return User. Raises `AuthError` on failure. |
| `async get_user_info(token: str) -> dict` | Call `/v1/auth/me` to get full user profile. |

### `User`

```python
@dataclass
class User:
    id: str
    email: str = ""
    tenant_id: str = "default"
    # Agency multi-tenancy (rollout 2026-04-18). None during rollout for legacy
    # users; backfill + enforcement will follow. Extensions SHOULD forward this
    # value to downstream services (Cases API, etc.) via
    # `X-Imperal-Agency-ID: {ctx.user.agency_id or 'default'}`.
    agency_id: str | None = None
    org_id: str | None = None
    role: str = "user"          # "admin" | "user" | "viewer" | custom role
    scopes: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)  # ABAC attributes
    is_active: bool = True
```

| Method | Description |
|--------|-------------|
| `has_scope(scope: str) -> bool` | Check if user has a specific scope (supports wildcards). |
| `has_attribute(key: str, value: Any = None) -> bool` | Check if user has an ABAC attribute (optionally with a specific value). |
| `can(scope: str, resource: dict = None) -> bool` | Combined RBAC + ABAC check. Verifies scope and optionally evaluates resource-level attribute conditions. |
| `get_attribute(key: str, default: Any = None) -> Any` | Retrieve an ABAC attribute value by key. |

### `AuthError`

```python
class AuthError(Exception)
```

Raised when token verification fails (expired, invalid signature, malformed).

### `require_auth()`

```python
def require_auth(
    auth: ImperalAuth | None = None,
    gateway_url: str = "https://auth.imperal.io"
) -> Callable
```

FastAPI dependency. Extracts Bearer token from `Authorization` header, verifies it, returns `User`. Raises `HTTPException(401)` on failure.

### `require_scope()`

```python
def require_scope(
    *required_scopes: str,
    auth: ImperalAuth | None = None,
    gateway_url: str = "https://auth.imperal.io"
) -> Callable
```

FastAPI dependency. Same as `require_auth()` but also checks that the user has ALL required scopes. Raises `HTTPException(403)` if a scope is missing.

---

## Scopes & Permissions

Scopes are strings that represent permissions. Extensions declare what they need (Info.plist / AndroidManifest style); dispatch enforces `tool.required_scopes ⊆ extension.declared_scopes`.

### Declaring scopes (session 27+)

Two complementary places to declare. The kernel ExtensionLoader takes the **union** of both as the granted capability set for the extension.

```python
from imperal_sdk import Extension, ChatExtension

# 1. Extension-level — broad capability surface
ext = Extension(
    "my-extension",
    version="1.0.0",
    capabilities=["mail:read", "mail:send"],  # what the extension needs overall
)

chat = ChatExtension(ext, tool_name="mail", description="Mail client")

# 2. Per-tool (optional, tightening) — only if this function needs less than the whole set
@chat.function("send_mail", scopes=["mail:send"], description="Send an email", action_type="write")
async def send_mail(ctx, params): ...

# Per-@ext.tool also supported
@ext.tool("debug_status", scopes=[], description="Read-only status endpoint")
async def debug_status(ctx): ...
```

Rules:
- If the extension declares **neither** `capabilities=[...]` nor any per-tool `scopes=`, the loader logs a `[SCOPES]` WARN and falls back to wildcard `["*"]` for backwards compat. This is the migration signal — fix it.
- The auto-registered ChatExtension entry tool now uses `scopes=[]` (was `["*"]` before session 27). The granted capability set comes from `capabilities=[...]` + per-tool declarations.
- Canonical delimiter is **colon** (`mail:send`). Dot format (`mail.send`) is still accepted for backwards compat but new code should use colon.

### Scope naming — common namespaces

| Namespace | Meaning / typical verbs |
|-----------|-------------------------|
| `mail:*` | `mail:read`, `mail:send` |
| `admin:*` | `admin:users`, `admin:billing`, `admin:extensions` |
| `store:*` | `store:read`, `store:write` — Tier 1 document store |
| `config:*` | `config:read`, `config:write` — Unified Config Store |
| `storage:*` | `storage:read`, `storage:write` — object storage |
| `ai:complete` | Access to `ctx.ai.complete()` — LLM calls |
| `notify:push` | Access to `ctx.notify.push()` — user notifications |
| `sharelock:cases:*` | Sharelock case data (`:read`, `:write`, `:delete`) |
| `reports:export` | Generate / export reports |
| `*` | Superadmin — all permissions |

| Example scope | Meaning |
|-------|---------|
| `cases:read` | Read case data |
| `cases:write` | Create/modify cases |
| `cases:*` | All case permissions (wildcard) |

> **See also:** the kernel's `scope_guard` is the authority on exact matching rules (wildcards, prefix hierarchy, fallthrough). Refer to `docs/imperal-cloud/conventions.md` for the current guard semantics.

### Wildcard Matching

`has_scope()` supports hierarchical wildcards:

```python
user.scopes = ["cases:*"]

user.has_scope("cases:read")    # True  — matches wildcard
user.has_scope("cases:write")   # True  — matches wildcard
user.has_scope("cases")         # True  — prefix matches
user.has_scope("admin:users")   # False — different domain
```

```python
user.scopes = ["*"]

user.has_scope("anything")      # True  — superadmin
```

### Kernel RBAC Enforcement

The kernel enforces scopes at two levels:

1. **Tool Discovery:** `discover_tools` filters results by user's scopes — users only see tools they can call
2. **Tool Execution:** `_execute_extension` (called by execute_sdk_tool and Hub) checks `required_scopes` against `kctx.scopes` (from KernelContext) before dispatching to any extension. Missing scopes → access denied.

Scopes support wildcards:
- `"*"` — matches everything (admin/system)
- `"cases:*"` — matches `cases:read`, `cases:write`, etc.
- `"cases:read"` — exact match

### Scope Resolution with Unified Config Store

User scopes come from the Auth Gateway identity resolution (cached in Redis 5min). The Unified Config Store adds **tenant-enforced** configuration that cannot be overridden:

```python
# Tenant enforced config — applied LAST, overrides everything
{
    "enforced": {
        "pii_encryption": true      # No user or app can disable this
    }
}
```

Scopes (what you CAN do) are separate from config (how the system BEHAVES). Both are resolved before tool execution.

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gateway_url` | `https://auth.imperal.io` | Auth Gateway base URL |
| JWKS cache TTL | 3600s (1 hour) | How long public keys are cached before re-fetch |
| JWT algorithm | RS256 | Signature algorithm (not configurable) |
| Required claims | `sub`, `exp`, `iat` | Token must contain these claims |

### Environment-Based Configuration

```python
import os
from imperal_sdk.auth import ImperalAuth

auth = ImperalAuth(
    gateway_url=os.getenv("IMPERAL_AUTH_URL", "https://auth.imperal.io")
)
```

---

## Auth Gateway Endpoints

For reference — these are the Auth Gateway endpoints your users interact with:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/auth/register` | POST | Register a new user |
| `/v1/auth/login` | POST | Login, receive JWT + refresh token |
| `/v1/auth/refresh` | POST | Refresh expired access token |
| `/v1/auth/logout` | POST | Revoke refresh token |
| `/v1/auth/me` | GET | Get current user profile (Bearer token) |
| `/v1/auth/.well-known/jwks.json` | GET | JWKS public keys for token verification |

---

## HMAC Call-Token Authentication (v1.6.0)

Internal kernel ↔ Auth Gateway calls for `/v1/internal/skeleton` and `/v1/internal/extcache` are authenticated with HMAC-SHA256 call tokens (not JWTs). Extension developers do not interact with this layer directly — the SDK's `SkeletonClient` and `CacheClient` mint tokens automatically when `ctx.skeleton.get(...)` or `ctx.cache.set(...)` is invoked from a legitimate kernel execution context.

### Flow

```
kernel (or SDK client running in kernel worker)
   |
   | Authorization: ImperalCallToken <HMAC-SHA256(payload, shared_secret)>
   | Header payload: tool_type, app_id, user_id, jti, exp
   |
   v
Auth Gateway /v1/internal/skeleton or /v1/internal/extcache
   |
   | 1. Verify HMAC with IMPERAL_CALL_TOKEN_HMAC_SECRET (shared env var)
   | 2. Check exp
   | 3. Redis SETNX on jti → prevents replay
   | 4. Enforce tool_type scope ("skeleton" or "extcache")
```

### Configuration

The shared secret is provisioned as the environment variable `IMPERAL_CALL_TOKEN_HMAC_SECRET` on every kernel worker and on the Auth Gateway. See `docs/imperal-cloud/secrets.md` in the internal infrastructure repo for rotation procedures and the ops playbook.

### Invariants

- `I-CALL-TOKEN-HMAC` — every `/v1/internal/skeleton` + `/v1/internal/extcache` call carries `Authorization: ImperalCallToken <signature>`; Auth GW rejects missing/invalid/expired/replayed tokens with 401.
- `I-CALL-TOKEN-SCOPE` — the payload's `tool_type` claim restricts what the token can be used for (`"skeleton"` cannot be used against `/v1/internal/extcache` and vice versa).

Extension developers do not need to call `mint_call_token` directly. The SDK clients handle it. The module is exposed at `imperal_sdk.security.call_token` for internal kernel use only.

---

## See Also

- [SDK Quickstart](quickstart.md) — full SDK setup guide
- [API Reference](api-reference.md) — all platform API endpoints
- [Auth Gateway Architecture](../auth-gateway.md) — internal auth gateway design
- [Skeleton (v1.6.0)](skeleton.md) — skeleton-LLM-only contract
- [Context Object § ctx.cache](context-object.md#ctxcache) — Pydantic-typed runtime cache
