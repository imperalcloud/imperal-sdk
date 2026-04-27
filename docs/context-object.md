# Context Object Reference

**SDK version:** imperal-sdk 1.5.7
**Last updated:** 2026-04-18
**Audience:** Extension developers building on Imperal Cloud

---

## Overview

The `Context` object is a typed dataclass injected by the platform into every tool, signal handler, and scheduled task in your extension. It provides access to the authenticated user, managed storage, AI completions, skeleton state, billing, notifications, file storage, and outbound HTTP.

Extensions never construct a `Context`. The platform's **ContextFactory** (part of the ICNLI OS kernel) creates it, populates it with the current user's session data, and passes it as the first argument to your function. The user's message is delivered as a separate keyword argument (`message`), not as a field on Context.

```python
from imperal_sdk import Extension, Context

ext = Extension("my-app")

@ext.tool("analyze", description="Analyze a case")
async def analyze(ctx: Context, message: str) -> str:
    # ctx is fully populated by the platform's ContextFactory
    # message is the user's input, passed as a keyword argument
    user = ctx.user
    case = await ctx.store.get("cases", message)
    result = await ctx.ai.complete(f"Analyze: {case['title']}")
    return result.text
```

---

## Class Definition

```python
@dataclass
class Context:
    user: User                 # Verified user identity
    history: list              # Pre-loaded conversation history (read-only)
    store: StoreClient         # Tier 1: managed document storage
    db: DBClient               # Tier 2: dedicated schema (requires capability)
    ai: AIClient               # AI completions (auto-metered)
    skeleton: SkeletonProtocol # LLM-only read-only skeleton (v1.6.0). Raises
                               # SkeletonAccessForbidden outside @ext.skeleton tools.
    cache: CacheClient         # v1.6.0: Pydantic-typed runtime cache, TTL 5-300s,
                               # 64 KB cap, per-extension namespace.
    billing: BillingClient     # Check limits and subscription (read-only)
    notify: NotifyClient       # Push notifications to the user
    storage: StorageClient     # File storage (S3-compatible)
    http: HTTPClient           # Outbound HTTP (logged and rate-limited)
    config: ConfigClient       # Resolved config (Platform→Tenant→App→User, read-only)
    tools: ToolsClient         # Inter-extension communication via kernel syscalls

    # Kernel-injected language fields (set per-message, read-only)
    _user_language: str        # ISO 639-1 code (e.g. "ru", "en", "es"). Detected by Hub LLM.
    _user_language_name: str   # Human-readable name (e.g. "Russian", "English", "Spanish")

    # Kernel-injected confirmation state (loaded ALWAYS, skipped only for system/skeleton/automation)
    _confirmation_required: bool  # True when ANY confirmation category is enabled
    _confirmation_actions: dict   # Per-category: {"destructive": True, "write": False}
```

> **Note:** The `Context` is created by the platform's **ContextFactory** in the ICNLI OS kernel. The factory pre-loads `history` before your function runs, so reading it is instant (no network call). The user's message is passed as a separate `message` keyword argument to your tool function, not as a field on Context.
>
> **v1.6.0 change:** `ctx.skeleton_data` is removed. Skeleton is LLM-only — the classifier envelope surfaces skeleton state to the routing LLM. Non-skeleton tools that need panel-side runtime data should use `ctx.cache` (see below). See [docs/skeleton.md](skeleton.md) for migration examples.

---

## ctx.user

The authenticated user who triggered the current request. Identity is verified by the Auth Gateway before the request reaches your extension.

### User fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique user identifier. Format: `imp_u_xxxxx`. Stable across sessions and channels. |
| `email` | `str` | Verified email address. |
| `tenant_id` | `str` | Tenant the user belongs to. Format: `imp_t_xxxxx`. |
| `agency_id` | `str \| None` | **Agency multi-tenancy (rollout 2026-04-18).** Federal / enterprise agency this user belongs to. `None` during rollout for legacy users; backfill + enforcement will follow. Extensions SHOULD forward this value to downstream services (Cases API, etc.) via `X-Imperal-Agency-ID: {ctx.user.agency_id or 'default'}`. |
| `org_id` | `str \| None` | Optional organization ID (sub-agency grouping). |
| `role` | `str` | Role within the tenant: `"admin"`, `"user"`, `"viewer"`, or a custom role string. Available in code but **not injected into ChatExtension system prompts** (only `email` is shown). |
| `scopes` | `list[str]` | Granted permission scopes. Tools check these against their `scopes` requirement. |
| `attributes` | `dict` | ABAC attributes for resource-level access control. |
| `is_active` | `bool` | `False` means account is disabled — request is rejected before reaching the extension. Always `True` for any request you receive. |

### Example

```python
@ext.tool("whoami", description="Show current user info")
async def whoami(ctx: Context) -> str:
    u = ctx.user
    return (
        f"User: {u.email}\n"
        f"ID: {u.id}\n"
        f"Tenant: {u.tenant_id}\n"
        f"Role: {u.role}\n"
        f"Scopes: {', '.join(u.scopes)}"
    )
```

### Notes

- `user.id` is always present and non-empty. It is the canonical identifier for per-user data.
- The same user always gets the same `user.id`, regardless of channel (web, API, mobile).
- Scopes are granted by the tenant administrator and enforced by the platform. If a tool requires `scopes=["cases:write"]` and the user lacks that scope, the platform returns an error before your tool is called.

---

## ctx._user_language / ctx._user_language_name

Kernel-injected language fields. Set per-message by the Hub LLM (Haiku) using `_route_with_llm()`, which returns `"app_id|INTENT|LANG"` in a single call (zero regex). The detected ISO code is persisted in Redis (`imperal:user_lang:{user_id}`, TTL 24h). For short acks that bypass Haiku routing, the kernel reads from this Redis cache. Language switches instantly per-message.

| Field | Type | Description |
|-------|------|-------------|
| `_user_language` | `str` | ISO 639-1 language code (e.g. `"ru"`, `"en"`, `"es"`, `"de"`) |
| `_user_language_name` | `str` | Human-readable language name (e.g. `"Russian"`, `"English"`) |

**Extensions do not need to read these fields.** `ChatExtension._build_system_prompt()` automatically injects `"KERNEL LANGUAGE RULE (NON-NEGOTIABLE): respond ONLY in {language}"` into every LLM call. Language enforcement is transparent.

Extensions may read these fields for custom logic (e.g., selecting a locale for date formatting), but must never add their own language rules to system prompts — the kernel rule already covers it.

```python
@chat.function("report", action_type="read", description="Generate a report", params={})
async def fn_report(self):
    lang = self.ctx._user_language  # e.g. "ru"
    # Use lang for locale-specific formatting if needed
    ...
```

---

## ctx._confirmation_required / ctx._confirmation_actions

Kernel-injected confirmation state. The executor ALWAYS loads confirmation settings at the start of every message (skipped only for system/skeleton/automation tasks).

| Field | Type | Description |
|-------|------|-------------|
| `_confirmation_required` | `bool` | `True` when ANY confirmation category is enabled for the user |
| `_confirmation_actions` | `dict` | Per-category settings, e.g. `{"destructive": True, "write": False}` |

`ChatExtension` reads `_confirmation_actions` automatically and checks the REAL `action_type` from `@chat.function` against the exact per-category setting. Hub intent is irrelevant — only the decorator's `action_type` determines if confirmation fires. Automations (`_is_automation`) always bypass confirmation.

**Extension developers do not need to check these fields.** ChatExtension handles the entire confirmation flow internally. Only implement custom confirmation logic if you are building an extension outside the ChatExtension framework (not recommended).

---

## ctx.history

Pre-loaded conversation history for the current session. This is a **read-only list** of message dictionaries, loaded by the ContextFactory before your function runs. Accessing `ctx.history` is instant -- no network call.

### Structure

Each entry is a dict with `role` (`"user"` or `"assistant"`) and `content` (the message text).

```python
[
    {"role": "user", "content": "Analyze case 42"},
    {"role": "assistant", "content": "Case 42 shows moderate risk..."},
    {"role": "user", "content": "What about the attachments?"},
]
```

### Example

```python
@ext.tool("summarize_conversation", description="Summarize what we discussed so far")
async def summarize_conversation(ctx: Context, message: str) -> str:
    if not ctx.history:
        return "No conversation history yet."
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in ctx.history[-10:])
    result = await ctx.ai.complete(f"Summarize this conversation:\n\n{transcript}")
    return result.text
```

### Notes

- History contains the last 40 messages (configurable per session). Older messages are evicted.
- The list is pre-loaded and read-only. You cannot append to or modify `ctx.history`.
- Use history for context-aware tool responses without making additional API calls.

---

## ctx.skeleton_data (removed in v1.6.0)

**`ctx.skeleton_data` no longer exists.** Skeleton is LLM-only in v1.6.0 — only the routing LLM sees skeleton state via the classifier envelope. Non-skeleton tools (panels, chat functions, regular tools) cannot read it.

If you previously used `ctx.skeleton_data[...]` for panel-side runtime data, migrate to [`ctx.cache`](#ctxcache). If you genuinely need previous skeleton state for a diff, do that work inside an `@ext.skeleton` tool — `ctx.skeleton.get(section)` is legal in that context only.

See [`docs/skeleton.md`](skeleton.md) § Migration for worked examples.

---

## ctx.store

Tier 1 managed document storage. Every extension gets a document store provisioned automatically -- no database setup, no connection strings, no schema migrations. The Store API backend is **fully operational** with persistent storage in each tenant's database.

The store is scoped to the current tenant. Documents created by one tenant are invisible to another.

### Implementation details

- The platform worker communicates with the Store API using a **service token** (`X-Service-Token` header), not the user's JWT. This is handled automatically -- extension developers never see or manage the service token.
- The client maintains a **persistent HTTP connection pool** for performance (connections are reused across requests within the same session).
- Documents are stored in the tenant's own database with **auto-table creation** -- the platform creates the backing table on first write to a new collection.
- Deletes are **soft deletes** with an audit trail (`deleted_at` timestamp). Deleted documents are excluded from queries by default.
- Query filters support **JSON equality matching** on any document field.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `create` | `create(collection: str, data: dict) -> Document` | Create a new document. Returns a `Document` object with `.id`. |
| `get` | `get(collection: str, doc_id: str) -> Document \| None` | Retrieve a document by ID. Returns `None` if not found. |
| `query` | `query(collection: str, where: dict = None, order_by: str = None, limit: int = 100) -> list[Document]` | Query documents with optional filtering and ordering. |
| `update` | `update(collection: str, doc_id: str, data: dict) -> Document` | Partial update of a document. |
| `delete` | `delete(collection: str, doc_id: str) -> bool` | Delete a document. Returns `True` on success. |
| `count` | `count(collection: str, where: dict = None) -> int` | Count documents matching the filter. |

### Example

```python
@ext.tool("create_ticket", scopes=["tickets:write"], description="Create a support ticket")
async def create_ticket(ctx: Context, subject: str, body: str) -> str:
    doc = await ctx.store.create("tickets", {
        "subject": subject,
        "body": body,
        "status": "open",
        "created_by": ctx.user.imperal_id,
    })
    return f"Ticket created: {doc.id}"


@ext.tool("get_ticket", scopes=["tickets:read"], description="Get a ticket by ID")
async def get_ticket(ctx: Context, ticket_id: str) -> str:
    ticket = await ctx.store.get("tickets", ticket_id)
    if not ticket:
        return "Ticket not found."
    return f"**{ticket['subject']}**\nStatus: {ticket['status']}\n\n{ticket['body']}"


@ext.tool("open_tickets", scopes=["tickets:read"], description="List open tickets")
async def open_tickets(ctx: Context) -> str:
    tickets = await ctx.store.query(
        "tickets",
        where={"status": "open"},
        order_by="-created_at",
        limit=10,
    )
    if not tickets:
        return "No open tickets."
    lines = [f"- [{t.id}] {t['subject']}" for t in tickets]
    return "Open tickets:\n" + "\n".join(lines)
```

### Notes

- Collections are created implicitly on first write (auto-table creation in the tenant's database). No schema definition required.
- Every document gets an `.id` attribute (string) assigned by the platform if not provided.
- Documents are JSON-serializable dicts. Maximum document size: 1 MB.
- Queries support filter operators defined by the platform backend.
- Sort strings use `-` prefix for descending: `"-created_at"`, `"title"`.
- Deletes are soft deletes with an audit trail. Deleted documents are excluded from queries and counts automatically.
- The store is automatically metered. Usage counts toward the tenant's storage quota.

### `ctx.store.list_users(collection, page_size=500)`

**System context only.** Returns AsyncIterator yielding user_ids with records in this extension's collection. Raises `RuntimeError` if called in user-context.

```python
async for user_id in ctx.store.list_users("wt_monitors"):
    user_ctx = ctx.as_user(user_id)
    monitors = await user_ctx.store.query("wt_monitors", where={"enabled": True})
    for m in monitors.data:
        await check_monitor(user_ctx, m)
```

**Invariants:** I-LIST-USERS-1..4.

**Raises:**
- `RuntimeError` — caller is not system-context
- `StoreUnavailable` — Auth Gateway unreachable (catch + skip scheduler tick)
- `ValueError` — forbidden chars in collection or invalid page_size

**Performance:** paginated (cursor-based, 500/page default). Suitable for collections up to 100k+ users.

### `ctx.store.query_all(collection, limit=500)`

**System context only.** Returns `list[Document]` in a single HTTP call. Use for bulk fan-out when `list_users` + `as_user` + per-user query would be N+1 inefficient (e.g. event poller scanning all OAuth tokens).

```python
docs = await ctx.store.query_all("gmail_accounts")
for doc in docs:
    if doc.data.get("provider") == "gmail":
        # doc.user_id is populated by query_all
        ...
```

**Invariants:** I-LIST-USERS-1 (reused), I-SDK-GW-CONTRACT-1.

### `ctx.as_user(user_id) -> Context`

**System context only.** Returns a new `Context` scoped to `user_id` — rewires `store`, `skeleton`, `notify`, `billing` clients with the new user_id. `ai`, `storage`, `http`, `config`, `time`, `_extension_id`, `agency_id` are inherited.

```python
# Inside @ext.schedule:
user_ctx = ctx.as_user("user-123")
doc = await user_ctx.store.get("my_coll", "doc-id")  # scoped to user-123
await user_ctx.notify("hi from scheduler")  # notifies user-123
```

**Invariants:** I-AS-USER-1 (system-context guard), I-AS-USER-2 (only user.id changes; extension/tenant/agency preserved).

**Raises:**
- `RuntimeError` — caller is not system-context (prevents chain-rescoping)
- `ValueError` — empty user_id or `"__system__"`

---

## ctx.db

Tier 2 dedicated database schema. For extensions that need relational queries, joins, or transactions beyond what the document store provides.

**Requires the `db` capability** in your extension manifest. The platform provisions a dedicated PostgreSQL schema for your extension when this capability is declared.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute` | `execute(sql: str, params: list = None) -> int` | Execute a write query. Returns affected row count. |
| `fetch_one` | `fetch_one(sql: str, params: list = None) -> dict` | Fetch a single row. Returns `None` if no match. |
| `fetch_all` | `fetch_all(sql: str, params: list = None) -> list[dict]` | Fetch all matching rows. |
| `transaction` | `transaction() -> AsyncContextManager` | Begin a transaction block. |

### Example

```python
@ext.tool("run_report", scopes=["reports:read"], description="Run a custom SQL report")
async def run_report(ctx: Context, query_name: str) -> str:
    if query_name == "top_users":
        rows = await ctx.db.fetch_all(
            "SELECT user_id, COUNT(*) as ticket_count "
            "FROM tickets GROUP BY user_id ORDER BY ticket_count DESC LIMIT 10"
        )
        lines = [f"- {r['user_id']}: {r['ticket_count']} tickets" for r in rows]
        return "Top users by ticket count:\n" + "\n".join(lines)
    return f"Unknown report: {query_name}"
```

### Notes

- The schema is isolated per extension and per tenant. Extensions cannot access each other's schemas.
- SQL queries are parameterized. Never interpolate user input directly into SQL strings.
- The `db` capability must be declared in the manifest. If not declared, `ctx.db` raises `CapabilityNotEnabled`.
- **Note:** The `ctx.db` method signatures shown here (`execute`, `fetch_one`, `fetch_all`, `transaction`) reflect the high-level SDK interface. The [Clients Reference](clients.md) documents lower-level methods (`acquire`, `session`, `raw`) that are also available. The API surface may vary depending on the provisioned database driver.

---

## ctx.ai

AI completions client. Provides access to language models with automatic usage metering and billing. You do not need your own API keys for supported models.

**Status: Fully operational.** The backend (`POST /v1/internal/ai/complete` on the Auth Gateway) is deployed and serving requests. The gateway routes to OpenAI (`gpt-*` models) or Anthropic (`claude-*` models) based on the model parameter prefix, meters usage per tenant, and enforces plan limits. Both `openai` and `anthropic` Python packages are installed in the platform worker environment.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `complete` | `complete(prompt: str, model: str = None, max_tokens: int = 2048, temperature: float = 0.7) -> AIResponse` | Single-turn completion. |
| `chat` | `chat(messages: list[dict], model: str = None, max_tokens: int = 2048, temperature: float = 0.7) -> AIResponse` | Multi-turn chat completion. |

### AIResponse fields

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | The generated text. |
| `model` | `str` | The model that was used. |
| `usage` | `dict` | Token counts: `{"input": int, "output": int}`. |

### Example

```python
@ext.tool("summarize", description="Summarize a document")
async def summarize(ctx: Context, doc_id: str) -> str:
    doc = await ctx.store.get("documents", doc_id)
    result = await ctx.ai.complete(
        prompt=f"Summarize the following document in 3 bullet points:\n\n{doc['content']}",
        max_tokens=512,
        temperature=0.3,
    )
    return result.text


@ext.tool("ask", description="Ask a question about a case")
async def ask(ctx: Context, question: str) -> str:
    case = await ctx.store.get("cases", ctx.user.imperal_id)
    messages = [
        {"role": "system", "content": f"You are analyzing case data:\n{case['summary']}"},
        {"role": "user", "content": question},
    ]
    result = await ctx.ai.chat(messages, temperature=0.5)
    return result.text
```

### Notes

- The default model is configured per extension in the Settings API. If not specified, the platform default is used.
- All AI usage is automatically metered and billed to the tenant's account. No separate API keys needed.
- Token counts in `usage` are exact values from the underlying provider.

---

## ctx.skeleton (v1.6.0 — LLM-only, read-only)

Skeleton is the routing LLM's view of extension state. In v1.6.0 it is:

- **Read-only** — `SkeletonProtocol` has no `update(...)` method. Skeleton tools RETURN new state via `ActionResult` and the kernel persists it via the privileged `skeleton_save_section` activity.
- **Forbidden outside `@ext.skeleton` tools** — accessing `ctx.skeleton` from a panel, `@chat.function`, or regular `@ext.tool` raises `SkeletonAccessForbidden` (a `PermissionError` subclass).

### Methods (inside `@ext.skeleton` only)

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `get(section: str) -> dict \| None` | Read the current skeleton section for this user. Returns `None` on first run. HMAC-authenticated call to Auth GW. |

`update(...)` and `delete(...)` are removed. The kernel writes skeleton via the privileged `skeleton_save_section` activity; the Auth GW PUT endpoint is gone. Extensions that need to remove or reset a section should return an empty payload from their `@ext.skeleton` tool.

### Using `ctx.skeleton` correctly

```python
from imperal_sdk import Extension, ActionResult

ext = Extension("mail", version="1.6.0")

@ext.skeleton("mail", ttl=525, alert=True,
              description="Mail unread/total counts")
async def skeleton_refresh_mail(ctx) -> ActionResult:
    # Legal — ctx.skeleton is unlocked inside an @ext.skeleton tool.
    prev = await ctx.skeleton.get("mail") or {}
    inbox = await _fetch_mail(ctx)
    new_state = {"unread": sum(1 for m in inbox if m["unread"]),
                 "total": len(inbox)}
    # RETURN the new state. No ctx.skeleton.update(...) in v1.6.0.
    return ActionResult.success(data=new_state, summary=f"{new_state['unread']} unread")
```

### Violations (v1.6.0 — raise `SkeletonAccessForbidden`)

```python
from imperal_sdk.errors import SkeletonAccessForbidden

@ext.panel("inbox", slot="main", title="Inbox")
async def panel_inbox(ctx, **kwargs):
    # BAD — raises SkeletonAccessForbidden.
    mail = await ctx.skeleton.get("mail")
    # GOOD — use ctx.cache for panel-side runtime data (see below).

@chat.function("unread_count", action_type="read")
async def fn_unread(ctx, params) -> ActionResult:
    # BAD — raises SkeletonAccessForbidden.
    mail = await ctx.skeleton.get("mail")
    # GOOD — call your own fetch logic or expose a skeleton tool and let
    # the classifier surface the count through the envelope.
```

### Notes

- Auth GW verifies every skeleton call with HMAC call-token authentication (`I-CALL-TOKEN-HMAC`) + Redis SETNX jti replay protection.
- Maximum payload per section: 64 KB.
- See [`docs/skeleton.md`](skeleton.md) for the `@ext.skeleton` decorator, TTL + alert semantics, classifier envelope format, and migration patterns from v1.5.x.

---

## ctx.cache (new in v1.6.0)

Pydantic-typed runtime cache for panel-side data, API response caching, paginated list snapshots, throttled counters — anything that used to live in skeleton but is **not** meant for the routing LLM.

**Status:** Backed by Auth GW `/v1/internal/extcache/{app_id}/{user_id}/{model}/{hash}`. HMAC call-token authenticated. Redis-backed, per-extension namespace, per-user scope.

### Properties

| Constraint | Value |
|---|---|
| Value shape | Pydantic `BaseModel` subclass registered via `@ext.cache_model("name")` |
| Namespace | Per extension + per user (no cross-bleed) |
| TTL range | 5–300 seconds (inclusive, Pydantic `Field(ge=5, le=300)`) |
| Value size cap | 64 KB after Pydantic `model_dump_json()` |
| Key charset | `[A-Za-z0-9_:.-]+`, max length 128 |
| Auth | HMAC call-token on every call |

### Registering a cache model

`@ext.cache_model(name)` is a decorator on your `Extension` instance. It registers a Pydantic class under `name` for use with `ctx.cache.get/set(..., model=...)`.

```python
from pydantic import BaseModel
from imperal_sdk import Extension

ext = Extension("mail", version="1.6.0")


class InboxPage(BaseModel):
    cursor: str
    items: list[dict]
    has_more: bool


@ext.cache_model("inbox_page")
class _InboxPageCache(InboxPage):
    pass
```

Each extension has its own registry; two extensions can register the same cache model name with different shapes without collision.

### Methods

| Method | Signature | Description |
|---|---|---|
| `get` | `get(key: str, *, model: type[BaseModel]) -> BaseModel \| None` | Fetch + validate; `None` on 404 or on model-name mismatch. |
| `set` | `set(key: str, value: BaseModel, *, ttl_seconds: int) -> None` | Store (validated, 64 KB cap, TTL 5-300s). |
| `delete` | `delete(key: str) -> None` | Remove for every registered model. |
| `get_or_fetch` | `get_or_fetch(key, *, model, ttl_seconds, fetcher) -> BaseModel` | Cache-aside: hit cache, else call `fetcher()`, store, return. |

### Example — panel cache-aside

```python
from pydantic import BaseModel
from imperal_sdk import Extension, ui

ext = Extension("mail", version="1.6.0")

class InboxPage(BaseModel):
    cursor: str
    items: list[dict]

@ext.cache_model("inbox_page")
class _InboxPageCache(InboxPage):
    pass


async def _fetch_inbox(ctx, page: int) -> InboxPage:
    resp = await ctx.http.get(f"https://api.mail.example/inbox?page={page}")
    data = resp.json()
    return InboxPage(cursor=data["cursor"], items=data["items"])


@ext.panel("inbox", slot="main", title="Inbox")
async def panel_inbox(ctx, **kwargs):
    page = await ctx.cache.get_or_fetch(
        key="page:1",
        model=InboxPage,
        ttl_seconds=60,
        fetcher=lambda: _fetch_inbox(ctx, page=1),
    )
    return ui.List(items=[_row(m) for m in page.items])
```

### Invariants

- **I-CACHE-MODEL-REGISTERED** — `get/set` reject models that are not registered with `@ext.cache_model`.
- **I-CACHE-TTL-RANGE** — `set` enforces `5 <= ttl_seconds <= 300` via Pydantic `Field(ge=5, le=300)`.
- **I-CACHE-SIZE-64K** — `set` rejects values whose JSON serialisation exceeds 64 KB.
- **I-CACHE-NAMESPACE** — Redis keyspace is `imperal:extcache:{app_id}:{user_id}:{model}:{hash}`; no cross-extension or cross-user bleed.
- **I-CALL-TOKEN-HMAC** — Every `/v1/internal/extcache` call is HMAC-SHA256 signed with jti replay protection.

### Notes

- Use `ctx.cache` for panel-side data that the routing LLM does not need to see. Skeleton remains the right place for summary state the classifier uses (unread count, open case count, today's visitor total, ...).
- `get_or_fetch` returns a fully-validated Pydantic model — no manual `model_validate` required.
- Cache misses return `None` (for `get`) or invoke the `fetcher` (for `get_or_fetch`). There is no `exists()` method by design — operate on concrete values.

---

## ctx.billing

Read-only access to the tenant's billing and subscription information. Use this to enforce feature gates and quota limits. The billing client uses a **persistent connection pool** and authenticates with the user's JWT (this is a public endpoint, unlike the internal Store API).

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `check_limits` | `check_limits() -> LimitsResult` | Check current usage against plan limits. Returns `LimitsResult` with `.plan`, `.usage`, `.limits`, `.exceeded`, `.any_exceeded`, `.is_exceeded(meter)`. |
| `get_subscription` | `get_subscription() -> SubscriptionInfo` | Get subscription details: `.plan`, `.status`, `.started_at`, `.expires_at`. |

### Example

```python
@ext.tool("premium_analysis", scopes=["analysis:run"], description="Run premium AI analysis")
async def premium_analysis(ctx: Context, doc_id: str) -> str:
    limits = await ctx.billing.check_limits()
    if limits.plan == "starter":
        return "Premium analysis requires a Professional or Enterprise plan."

    if limits.is_exceeded("ai_tokens"):
        used = limits.usage.get("ai_tokens", 0)
        cap = limits.limits.get("ai_tokens", 0)
        return f"AI token limit reached ({used}/{cap}). Please upgrade your plan."

    doc = await ctx.store.get("documents", doc_id)
    result = await ctx.ai.complete(
        prompt=f"Perform deep analysis:\n\n{doc['content']}",
        max_tokens=4096,
    )
    return result.text
```

### Notes

- Billing data is read-only. Extensions cannot modify subscription or usage data.
- Usage counters are updated in near-real-time (within 5 seconds of the metered event).
- Use `limits.any_exceeded` as a quick boolean check before expensive operations.

---

## ctx.notify

Push notifications to the user across all their connected channels (web, mobile, email).

**Status: Fully operational.** The backend (`POST /v1/internal/notify` on the Auth Gateway) is deployed and serving requests. Notifications are queued in a Redis list (`imperal:notifications:{user_id}`) and consumed by the delivery service.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `__call__` | `(message: str, **kwargs) -> None` | Send a notification — preferred, used by every production extension. Call `ctx.notify(...)` directly. Optional kwargs: `priority` (`"low"`, `"normal"`, `"high"`, `"urgent"`), `channel` (`"in_app"`, `"email"`, `"telegram"`, …), `subject`, `body`. |
| `send` | `(message: str, channel: str = "in_app", **kwargs) -> None` | Alias for `__call__` — accepts an explicit `channel` parameter. Forwards to `__call__`. Added in SDK 1.5.8 (session 30, 2026-04-18) so the Protocol, concrete client, and mock all support both styles end-to-end. Prior to 1.5.8 only the Protocol declared `send`; the real `NotifyClient` had only `__call__`, so `ctx.notify.send(...)` crashed at runtime — historical docs showing that pattern were wrong. |

### Example

```python
@ext.schedule("quota_check", cron="0 */6 * * *")
async def quota_check(ctx: Context) -> None:
    limits = await ctx.billing.check_limits()
    storage_used = limits.usage.get("storage_bytes", 0)
    storage_limit = limits.limits.get("storage_bytes", 1)
    pct = (storage_used / storage_limit) * 100
    if pct > 90:
        await ctx.notify(
            f"Storage Warning: Your storage is {pct:.0f}% full. Consider archiving old data.",
            priority="high",
        )
```

### Notes

- Both invocation styles are supported from **SDK 1.5.8**: `await ctx.notify("msg", priority="high")` (preferred — production extensions use this) and `await ctx.notify.send("msg", channel="email")` (alias — forwards to `__call__`). Choose the style that reads naturally in your code; both hit the same Auth GW endpoint with the same payload.
- Notification delivery respects the user's channel preferences (configured in the Imperal Panel).
- Fire-and-forget: the method does not raise on delivery failure (timeout is 10 seconds).

---

## ctx.storage

File storage for binary assets (documents, images, exports). Files are scoped to the tenant.

**Status: Fully operational.** The backend (`POST /v1/internal/storage/upload`, `GET /download`, `DELETE`, `GET /list` on the Auth Gateway) is deployed and serving requests. Files are stored on the filesystem at `/opt/imperal-storage/{tenant_id}/{extension_id}/{path}`.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `upload` | `upload(path: str, data: bytes, content_type: str = "application/octet-stream") -> str` | Upload a file. Returns the public URL. |
| `download` | `download(path: str) -> bytes` | Download a file by path. |
| `delete` | `delete(path: str) -> bool` | Delete a file. |
| `list` | `list(prefix: str = "") -> list[str]` | List file paths matching the prefix. |

### Example

```python
@ext.tool("export_report", scopes=["reports:export"], description="Export a report as PDF")
async def export_report(ctx: Context, report_id: str) -> str:
    report = await ctx.store.get("reports", report_id)
    pdf_bytes = generate_pdf(report)

    url = await ctx.storage.upload(
        path=f"exports/{report_id}.pdf",
        data=pdf_bytes,
        content_type="application/pdf",
    )
    return f"Report exported: {url}"
```

### Notes

- Storage paths are relative to the tenant's namespace. Two tenants can use the same path without collision.
- Maximum file size: 100 MB per upload.
- URLs returned by `upload` are signed and expire after 24 hours. For permanent links, use the `storage.permanent_url()` method (Enterprise plan only).

---

## ctx.http

Outbound HTTP client for calling external APIs. All requests are logged and rate-limited by the platform for security and auditability.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `get` | `get(url: str, headers: dict = None, params: dict = None) -> HTTPResponse` | HTTP GET request. |
| `post` | `post(url: str, headers: dict = None, json: dict = None, data: bytes = None) -> HTTPResponse` | HTTP POST request. |
| `put` | `put(url: str, headers: dict = None, json: dict = None) -> HTTPResponse` | HTTP PUT request. |
| `delete` | `delete(url: str, headers: dict = None) -> HTTPResponse` | HTTP DELETE request. |

### HTTPResponse fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | `int` | HTTP status code. |
| `json` | `dict` | Parsed JSON body (if applicable). |
| `text` | `str` | Raw response body as string. |
| `headers` | `dict` | Response headers. |

### Example

```python
@ext.tool("check_domain", description="Check if a domain is available")
async def check_domain(ctx: Context, domain: str) -> str:
    resp = await ctx.http.get(
        f"https://api.example.com/domains/{domain}/availability",
        headers={"Authorization": "Bearer YOUR_API_KEY"},
    )
    if resp.status == 200 and resp.json.get("available"):
        return f"Domain {domain} is available."
    return f"Domain {domain} is not available."
```

### Notes

- All outbound HTTP requests are logged in the platform's audit trail with URL, method, status code, and latency.
- The platform enforces rate limits: 100 requests per minute per extension per tenant by default. This is configurable in the Settings API.
- Requests have a default timeout of 30 seconds. Override with the `timeout` parameter (max 120 seconds).
- The HTTP client follows redirects (up to 5 hops) and validates TLS certificates.

---

## ctx.config — ConfigClient

**Available:** Always (kernel resolves before Context creation)

Resolved configuration for the current user+app+tenant combination. **Read-only** — extensions cannot modify config.

The kernel resolves config from all scope levels before creating Context:
1. Platform Defaults (global)
2. Tenant Defaults + `role_defaults[user.role]`
3. App Config (extension-specific)
4. User Overrides (personal)
5. Tenant Enforced (compliance — cannot be overridden)

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get(key, default=None)` | `Any` | Dot-notation access: `"models.primary_model"` |
| `get_section(section)` | `dict` | Full section as deep copy |
| `all()` | `dict` | Complete resolved config (deep copy) |

### Examples

```python
@ext.tool("analyze", description="Analyze data")
async def analyze(ctx: Context, query: str):
    # Dot-notation access
    model = ctx.config.get("models.primary_model")       # "claude-opus"
    language = ctx.config.get("persona.language")          # "ru"
    pii_safe = ctx.config.get("pii_encryption")            # True (tenant enforced)

    # Full section
    models = ctx.config.get_section("models")
    # {"primary_model": "claude-opus", "temperature": 0.7, ...}

    # Missing keys return default
    custom = ctx.config.get("custom.missing", "fallback")  # "fallback"
```

> Config is resolved **once** when Context is created. It does not change during a tool call. Writes go through the Registry Settings API.

---

## ctx.tools — ToolsClient

**Available:** Always (kernel injects at Context creation)

Inter-extension communication via kernel syscalls. All calls go through `execute_sdk_tool` (requires pre-resolved `_kernel_ctx`) → `_execute_extension` with full RBAC enforcement, audit trail, and capability boundary checks. Context is built via `ContextFactory.create_from_kctx()` from typed KernelContext (no HTTP calls at Context creation time).

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `discover(query, top_k=3)` | `list[ToolInfo]` | Semantic search across all registered tools |
| `call(activity_name, params)` | `ToolResult` | Call another extension through kernel |

### ToolInfo Fields

| Field | Type | Description |
|-------|------|-------------|
| `app_id` | `str` | Extension that owns the tool |
| `activity_name` | `str` | Kernel activity name |
| `name` | `str` | Human-readable name |
| `description` | `str` | Tool description |
| `domains` | `list[str]` | Domain tags |
| `required_scopes` | `list[str]` | Scopes needed to call |
| `relevance` | `float` | Semantic similarity score (0-1) |

### ToolResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `response` | `str \| dict` | Tool response |
| `app_id` | `str` | Extension that handled the call |
| `tool_name` | `str` | Activity name called |

### Examples

```python
@ext.tool("cross_check", scopes=["cases:read"], description="Cross-check data")
async def cross_check(ctx: Context, query: str):
    # Discover tools by semantic query
    tools = await ctx.tools.discover("case analysis")
    for tool in tools:
        print(f"{tool.name} (score: {tool.relevance:.2f})")

    # Call another extension — goes through kernel with RBAC
    result = await ctx.tools.call("tool_sharelock_chat", {"message": query})
    return {"analysis": result.response}
```

> **Security:** `ctx.tools.call()` enforces RBAC — the calling extension must have the required scopes for the target tool. Calls are logged for audit.

---

## Internal Client Architecture

> **All ctx.\* backends are now operational.** As of 2026-04-03, every internal platform API endpoint (`ctx.store`, `ctx.ai`, `ctx.skeleton`, `ctx.notify`, `ctx.storage`, `ctx.config`, `ctx.tools`) is deployed on the Auth Gateway and serving requests in production.

All internal platform clients (`ctx.store`, `ctx.ai`, `ctx.skeleton`, `ctx.notify`, `ctx.storage`) authenticate with the platform using **service tokens** (`X-Service-Token` header) and maintain **persistent HTTP connection pools** for efficient request handling. These are internal APIs blocked from public access at the network level.

The billing client (`ctx.billing`) is the exception -- it calls a public API endpoint and authenticates with the **user's JWT** (`Authorization: Bearer` header). It also uses a persistent connection pool.

Extension developers do not need to manage tokens or connections. The platform handles all authentication and connection lifecycle automatically.

---

## Context Availability by Handler Type

| Attribute | `@ext.tool` | `@ext.signal` | `@ext.schedule` | `@chat.function` | `@ext.skeleton` | `@ext.panel` |
|-----------|:-----------:|:-------------:|:---------------:|:----------------:|:---------------:|:------------:|
| `ctx.user` | Yes | Yes | Yes | Yes (via `self.ctx`) | Yes | Yes |
| `ctx.history` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.store` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.db` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.ai` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.skeleton` (v1.6.0 read-only) | **SkeletonAccessForbidden** | **SkeletonAccessForbidden** | **SkeletonAccessForbidden** | **SkeletonAccessForbidden** | Yes (`get` only) | **SkeletonAccessForbidden** |
| `ctx.cache` (v1.6.0) | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.billing` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.notify` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.storage` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.http` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.config` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx.tools` | Yes | Yes | Yes | Yes | Yes | Yes |
| `ctx._user_language` | Yes | No | No | Yes | No | Yes |
| `ctx._user_language_name` | Yes | No | No | Yes | No | Yes |
| `ctx._confirmation_required` | No | No | No | Yes (kernel-set) | No | No |
| `message` (kwarg) | Yes | No | No | No (params via function args) | No | No |

**v1.6.0 changes:**
- `ctx.skeleton_data` is removed — no longer in `Context`.
- `ctx.skeleton` raises `SkeletonAccessForbidden` from every handler type except `@ext.skeleton`. Inside `@ext.skeleton` tools, only `get(section)` is available — `update` and `delete` are removed.
- `ctx.cache` is the new runtime cache for panel-side data (TTL 5-300s, Pydantic-typed, 64 KB cap). See [§ ctx.cache](#ctxcache).

---

## Related Documentation

- [Tools](tools.md) -- Defining tools that receive the Context object
- [Skeleton](skeleton.md) -- Background state management via `ctx.skeleton`
- [Concepts](concepts.md) -- Two-tier storage, identity model, billing
- [API Reference](api-reference.md) -- Registry and Auth Gateway endpoints
