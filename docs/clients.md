# SDK Clients Reference -- ctx.* APIs

**SDK version:** imperal-sdk 1.5.6
**Last updated:** 2026-04-17 (v1.5.2: AIClient `service_token` → `X-Service-Token`; StoreClient single-path `get()`; default model `claude-sonnet-4-6`. v1.5.0: BillingClient rewritten with dual auth, track_usage, get_balance. v1.2.0: ctx.extensions IPC implemented. Client API surface stable since 1.5.0 — no client-layer changes in 1.5.1–1.5.6.)
**Audience:** Extension developers building on Imperal Cloud

---

## Quick Reference

| Client | Access | Purpose | Key Methods |
|--------|--------|---------|-------------|
| `AIClient` | `ctx.ai` | LLM completions | `complete()` |
| `StoreClient` | `ctx.store` | Document CRUD | `create()`, `get()`, `query()`, `update()`, `delete()`, `count()` |
| `StorageClient` | `ctx.storage` | File upload/download | `upload()`, `download()`, `delete()`, `list()` |
| `DBClient` | `ctx.db` | SQL database access | `acquire()`, `session()`, `raw()` |
| `BillingClient` | `ctx.billing` | Usage limits, plan info, balance, usage tracking | `check_limits()`, `get_subscription()`, `track_usage()`, `get_balance()` |
| `NotifyClient` | `ctx.notify` | Push notifications to user | `__call__()` (direct invocation) |
| `HTTPClient` | `ctx.http` | Outbound HTTP requests | `get()`, `post()`, `put()`, `patch()`, `delete()` |
| `SkeletonClient` | `ctx.skeleton` | Background state management | `get()`, `update()` |
| `ConfigClient` | `ctx.config` | Resolved extension configuration (read-only) | `get()`, `get_section()`, `all()` |
| `TimeContext` | `ctx.time` | Kernel-injected timezone and time data (read-only) | `.timezone`, `.hour_local`, `.is_business_hours` |
| -- | `ctx.progress` | Task progress updates | `__call__(percent, message)` |
| `ExtensionsClient` | `ctx.extensions` | Inter-extension IPC — direct in-process, kernel-mediated, zero HTTP. Circular call detection via call stack. | `call(app_id, method, **params)`, `emit(event_type, data)` |
| `RAGClient` | `ctx.rag` | Vector search and retrieval (Planned) | `search()`, `index()` |
| `MemoryClient` | `ctx.memory` | Agent memory and knowledge graph (Planned) | `remember()`, `recall()` |

All clients are pre-configured and injected into the `Context` object by the platform. You never instantiate them directly. Authentication, tenant isolation, and extension scoping are handled automatically.

> **Service tokens.** All internal SDK clients (`Store`, `AI`, `Billing`, `Skeleton`, `Notify`, `Storage`) accept a `service_token` kwarg. The `ContextFactory` passes `service_token=` for all kernel-level calls. Extension developers never see or manage service tokens — the platform handles this automatically. The `auth_token` kwarg has a default value and is only needed for user-facing public endpoints.

> **Cross-extension routing:** The Hub handles all inter-extension routing, chain execution, and fallback logic automatically based on the user's message. For cases where your extension has a hard dependency on another extension's function result, use `ctx.extensions.call()` (see section 12). See the Hub documentation for details.

---

## 1. ctx.ai -- AIClient

LLM completion client. Usage is auto-metered by the platform against the user's billing plan.

### Methods

```python
async def complete(
    prompt: str,
    model: str = "claude-sonnet",
    **kwargs
) -> CompletionResult
```

Sends a completion request to the platform AI gateway. The `model` parameter selects the LLM. Additional keyword arguments are forwarded to the API (e.g., `temperature`, `max_tokens`).

**Returns:** `CompletionResult`

```python
@dataclass
class CompletionResult:
    text: str
    tokens_used: int = 0
    model: str = ""
```

### Example

```python
from imperal_sdk import Extension, Context

ext = Extension("my-extension")

@ext.tool("summarize", description="Summarize a document")
async def summarize(ctx: Context, text: str) -> str:
    result = await ctx.ai.complete(
        prompt=f"Summarize the following text:\n\n{text}",
        model="claude-sonnet",
        max_tokens=500
    )
    return result.text
```

### Notes

- All AI usage is metered against the current user's plan. Check limits with `ctx.billing.check_limits()` before expensive operations if needed.
- The default timeout is 120 seconds to accommodate long completions.
- The `model` value is a platform alias, not a raw provider model ID.

---

## 2. ctx.store -- StoreClient

Managed document storage via the Auth Gateway internal API. Tier 1 storage -- no infrastructure setup required. Documents are JSON objects stored in named collections, automatically scoped to the extension and tenant.

### Methods

```python
async def create(collection: str, data: dict) -> Document
```

Create a new document in the given collection.

```python
async def get(collection: str, doc_id: str) -> Document | None
```

Retrieve a document by ID. Returns `None` if not found.

```python
async def query(
    collection: str,
    where: dict | None = None,
    order_by: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> Page[Document]
```

Query documents with optional filtering, ordering, and limit. Returns a `Page[Document]` with `items`, `total`, `cursor` (for next page), and `has_more` fields.

> **Pagination (v1.0.0):** `ctx.store.query()` returns `Page[T]` instead of a plain list. Access results via `page.items`. To paginate: pass `cursor=page.cursor` to the next call. `page.has_more` indicates whether more results exist. The `Page[T]` type is generic — `Page[Document]`, `Page[dict]`, etc.

```python
async def update(collection: str, doc_id: str, data: dict) -> Document
```

Partial update of a document's data.

```python
async def delete(collection: str, doc_id: str) -> bool
```

Delete a document. Returns `True` on success.

```python
async def count(collection: str, where: dict | None = None) -> int
```

Count documents in a collection, optionally filtered.

**Returns:** `Document`

```python
@dataclass
class Document:
    id: str
    collection: str
    data: dict
    created_at: str | None = None
    updated_at: str | None = None
```

The `Document` dataclass supports dict-style access: `doc["field"]` and `doc.get("field", default)` delegate to `doc.data`.

### Example

```python
@ext.tool("save_note", description="Save a note")
async def save_note(ctx: Context, title: str, body: str) -> str:
    doc = await ctx.store.create("notes", {"title": title, "body": body})
    return f"Saved note {doc.id}"

@ext.tool("find_notes", description="Search notes by title")
async def find_notes(ctx: Context, keyword: str) -> str:
    page = await ctx.store.query("notes", where={"title": {"$contains": keyword}}, limit=10)
    return "\n".join(f"- {d['title']}" for d in page.items)

@ext.tool("delete_note", description="Delete a note by ID")
async def delete_note(ctx: Context, note_id: str) -> str:
    ok = await ctx.store.delete("notes", note_id)
    return "Deleted" if ok else "Not found"
```

### Notes

- Collections are automatically namespaced per extension and tenant. Two extensions using the collection name `"notes"` will not collide.
- The `where` parameter supports filter operators defined by the platform backend.
- Default timeout per request is 30 seconds.

---

## 3. ctx.storage -- StorageClient

File storage for binary data (images, PDFs, exports, etc.). Files are scoped to the extension and tenant.

### Methods

```python
async def upload(
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream"
) -> str
```

Upload a file. Returns the download URL.

```python
async def download(path: str) -> bytes
```

Download a file by path. Returns raw bytes.

```python
async def delete(path: str) -> bool
```

Delete a file. Returns `True` on success.

```python
async def list(prefix: str = "") -> list[str]
```

List file paths matching an optional prefix.

### Example

```python
@ext.tool("export_report", description="Generate and store a CSV report")
async def export_report(ctx: Context) -> str:
    csv_data = b"name,value\nfoo,42\nbar,99\n"
    url = await ctx.storage.upload(
        path="reports/monthly.csv",
        data=csv_data,
        content_type="text/csv"
    )
    return f"Report uploaded: {url}"

@ext.tool("list_reports", description="List all stored reports")
async def list_reports(ctx: Context) -> str:
    files = await ctx.storage.list(prefix="reports/")
    return "\n".join(files) if files else "No reports found"
```

### Notes

- Upload timeout is 60 seconds. For very large files, consider chunked approaches.
- The `path` is a logical path within the extension's storage namespace, not a filesystem path.
- The returned URL from `upload()` is a platform-managed URL, not a direct object store link.

---

## 4. ctx.db -- DBClient

> **Status: Available.** ContextFactory creates DBClient when `DB_URL` or `EXTENSION_DB_URL` environment variable is set. Uses `aiomysql` for MySQL/MariaDB (Galera cluster via ProxySQL). Without the env var, `ctx.db` is `None` (Tier 1 extensions). URL format: `mysql+aiomysql://user:pass@host:port/dbname`.

Tier 2 storage: direct SQL database access for extensions that need relational data, joins, or complex queries. Requires a dedicated schema and `DB_URL` configured on the worker.

### Methods

```python
@asynccontextmanager
async def acquire() -> AsyncGenerator[Connection, None]
```

Acquire a raw database connection from the pool. Use as an async context manager. The connection is automatically released when the block exits.

```python
@asynccontextmanager
async def session() -> AsyncGenerator[Session, None]
```

Create a managed session with automatic commit/rollback. Commits on successful exit, rolls back on exception, and always closes the session.

```python
async def raw(query: str, params: tuple | None = None) -> list[dict[str, Any]]
```

Execute a raw SQL query and return results as a list of dicts.

### Example

```python
# Requires DB_URL or EXTENSION_DB_URL env var on the worker.

@ext.tool("find_customers", description="Search customers by name")
async def find_customers(ctx: Context, name: str) -> str:
    rows = await ctx.db.raw(
        "SELECT id, name, email FROM customers WHERE name ILIKE %s LIMIT 10",
        (f"%{name}%",)
    )
    return "\n".join(f"{r['name']} ({r['email']})" for r in rows)

@ext.tool("create_order", description="Create a new order with transaction safety")
async def create_order(ctx: Context, customer_id: str, amount: float) -> str:
    async with ctx.db.session() as session:
        await session.execute(
            "INSERT INTO orders (customer_id, amount) VALUES (%s, %s)",
            (customer_id, amount)
        )
    # Auto-committed on success, rolled back on exception
    return "Order created"
```

### Notes

- `ctx.db` is `None` unless `DB_URL` or `EXTENSION_DB_URL` is configured on the platform worker. Set the env var to enable Tier 2 database access.
- Uses `aiomysql` under the hood — connect to MySQL/MariaDB (Galera cluster via ProxySQL). Pool: minsize=1, maxsize=5.
- The `session()` context manager provides automatic transaction management — commits on success, rolls back on exception.
- `acquire()` gives a lower-level connection for cases where you need more control.
- `raw()` returns results as `list[dict]` with column names as keys (via `DictCursor`).

---

## 5. ctx.billing -- BillingClient

Client for checking the current user's billing plan, token balance, usage tracking, and subscription status. Use this to enforce limits, display plan information, or check balance before expensive operations.

### Dual Auth Pattern

BillingClient supports two authentication modes, selected automatically based on the calling context:

| Auth Mode | Header | Use Case |
|-----------|--------|----------|
| `service_token` | `X-Service-Token` | Internal kernel/platform calls (ContextFactory injects automatically) |
| `auth_token` | `Bearer` | Public endpoints, user-facing API calls |

Extension developers never manage these tokens directly -- `ContextFactory` handles injection. The client is instantiated as `BillingClient(gateway_url, auth_token="", service_token="", user_id="")`.

### Methods

```python
async def check_limits() -> LimitsResult
```

Check current usage against plan token limits. Returns safe defaults on failure (never crashes the calling tool).

**Returns:** `LimitsResult`

```python
@dataclass
class LimitsResult:
    plan: str
    usage: dict[str, int]
    limits: dict[str, int]
    exceeded: list[str]

    def is_exceeded(self, meter: str) -> bool: ...

    @property
    def any_exceeded(self) -> bool: ...
```

```python
async def get_subscription() -> SubscriptionInfo
```

Get subscription details for the current user.

**Returns:** `SubscriptionInfo`

```python
@dataclass
class SubscriptionInfo:
    plan: str
    status: str
    started_at: str | None = None
    expires_at: str | None = None
```

```python
async def track_usage() -> None
```

Record a usage event for the current action. Called internally by the kernel after each tool execution. Extension developers typically do not call this directly -- the platform tracks usage automatically based on the action's pricing category. Logs a warning on failure but never raises.

```python
async def get_balance() -> BalanceInfo
```

Get the current user's token balance and plan cap.

**Returns:** `BalanceInfo`

```python
@dataclass
class BalanceInfo:
    balance: int       # tokens remaining
    cap: int           # plan token cap
    plan: str          # plan name (micro, starter, pro, business, enterprise)
    alert_level: str   # "ok", "warning" (< 20%), "critical" (< 5%)
```

### Example

```python
@ext.tool("check_quota", description="Check if AI quota is available")
async def check_quota(ctx: Context) -> str:
    limits = await ctx.billing.check_limits()
    if limits.is_exceeded("ai_tokens"):
        return f"AI token limit exceeded on plan '{limits.plan}'"
    usage = limits.usage.get("ai_tokens", 0)
    cap = limits.limits.get("ai_tokens", 0)
    return f"Used {usage}/{cap} AI tokens on plan '{limits.plan}'"

@ext.tool("plan_info", description="Show current subscription")
async def plan_info(ctx: Context) -> str:
    sub = await ctx.billing.get_subscription()
    return f"Plan: {sub.plan}, Status: {sub.status}, Expires: {sub.expires_at}"

@ext.tool("check_balance", description="Check token balance")
async def check_balance(ctx: Context) -> str:
    bal = await ctx.billing.get_balance()
    return f"Balance: {bal.balance}/{bal.cap} tokens on {bal.plan} plan (status: {bal.alert_level})"
```

### Notes

- Extensions cannot modify billing state directly. `track_usage()` is called by the kernel, not by extension code.
- All methods return safe defaults on failure -- `check_limits()` returns an empty `LimitsResult`, `get_balance()` returns zero balance, `get_subscription()` returns a default object. Failures are logged via `log.warning` but never raise exceptions.
- Use `limits.any_exceeded` as a quick boolean check before expensive operations.
- The `user` parameter was removed in v1.5.0. The platform resolves the user from the injected `user_id` automatically.
- **Plans:** micro (free, 500 tokens), starter ($9, 15K), pro ($29, 50K), business ($79, 200K), enterprise (custom).

---

## 6. ctx.notify -- NotifyClient

Push notifications to the current user. Delivers messages through the user's active channels (panel, Telegram, etc.).

### Methods

```python
async def __call__(message: str, **kwargs) -> None
```

Send a notification. The client is callable directly -- no method name needed. Additional keyword arguments are forwarded to the notification backend (e.g., `channel`, `priority`).

### Example

```python
@ext.tool("long_task", description="Run a long background task")
async def long_task(ctx: Context) -> str:
    # ... do work ...
    await ctx.notify("Your report is ready for download.")
    return "Task complete"

@ext.tool("alert", description="Send a priority alert")
async def alert(ctx: Context, message: str) -> str:
    await ctx.notify(message, priority="high")
    return "Alert sent"
```

### Notes

- `ctx.notify` is called directly as a function, not as `ctx.notify.send()`. This is by design.
- Fire-and-forget: the method does not raise on delivery failure (timeout is 10 seconds).
- The notification is automatically addressed to the current user via the context.

---

## 7. ctx.http -- HTTPClient

General-purpose outbound HTTP client for calling external APIs. Pre-configured with sensible defaults for timeout and redirect handling.

### Methods

```python
async def get(url: str, **kwargs) -> httpx.Response
async def post(url: str, **kwargs) -> httpx.Response
async def put(url: str, **kwargs) -> httpx.Response
async def patch(url: str, **kwargs) -> httpx.Response
async def delete(url: str, **kwargs) -> httpx.Response
```

All standard HTTP methods. Keyword arguments are forwarded to the underlying `httpx.AsyncClient` call (e.g., `headers`, `json`, `params`, `data`, `timeout`).

**Default configuration:**
- Timeout: 30 seconds
- Max redirects: 5
- Redirect following: enabled

### Example

```python
@ext.tool("fetch_weather", description="Get current weather for a city")
async def fetch_weather(ctx: Context, city: str) -> str:
    resp = await ctx.http.get(
        "https://api.weather.example/v1/current",
        params={"city": city},
        headers={"X-API-Key": "your-key"}
    )
    resp.raise_for_status()
    data = resp.json()
    return f"{city}: {data['temp']}C, {data['condition']}"

@ext.tool("submit_webhook", description="POST data to a webhook")
async def submit_webhook(ctx: Context, url: str, payload: dict) -> str:
    resp = await ctx.http.post(url, json=payload)
    return f"Status: {resp.status_code}"
```

### Notes

- Each method call creates a fresh `httpx.AsyncClient` instance. There is no connection pooling across calls.
- Use `resp.raise_for_status()` to convert HTTP errors into exceptions.
- The `**kwargs` are passed directly to `httpx` -- refer to the [httpx documentation](https://www.python-httpx.org/) for the full parameter list.
- Do not use `ctx.http` to call platform-internal APIs. Use the dedicated clients (`ctx.store`, `ctx.ai`, etc.) instead.

---

## 8. ctx.skeleton -- SkeletonProtocol (v1.6.0: LLM-only, read-only)

**Breaking change in v1.6.0.** Skeleton is now the AI's view of extension state. Accessing `ctx.skeleton` from any non-skeleton handler (`@ext.panel`, `@chat.function`, `@ext.tool`, `@ext.signal`, `@ext.schedule`) raises `SkeletonAccessForbidden`. Only tools decorated with `@ext.skeleton` may call `ctx.skeleton.get(section)`.

For full documentation on the v1.6.0 Skeleton system (LLM-only contract, `@ext.skeleton` decorator, classifier envelope, migration from v1.5.x), see **[skeleton.md](skeleton.md)**.

### Methods (inside `@ext.skeleton` only)

```python
async def get(section: str) -> dict | None
```

Read the current skeleton section. Returns `None` on first run. HMAC-authenticated.

The v1.5.x `update(...)` and `delete(...)` methods are removed. Skeleton tools RETURN new state via `ActionResult.success(data=...)` and the kernel persists it via the privileged `skeleton_save_section` activity (single writer, audit-logged).

### Example — v1.6.0 skeleton tool

```python
from pydantic import BaseModel
from imperal_sdk import Extension, ActionResult

ext = Extension("dashboard", version="1.6.0")


class DashboardSection(BaseModel):
    items: list
    updated_at: str


@ext.skeleton("dashboard", ttl=300, alert=False,
              description="Dashboard summary for classifier")
async def skeleton_refresh_dashboard(ctx) -> ActionResult:
    prev = await ctx.skeleton.get("dashboard") or {}  # legal inside @ext.skeleton
    resp = await ctx.http.get("https://api.example.com/dashboard")
    section = DashboardSection(items=resp.json(), updated_at=_now())
    return ActionResult.success(data=section.model_dump(),
                                summary=f"{len(section.items)} items")
```

### Violations (v1.6.0)

```python
@ext.tool("get_dashboard", description="Get cached dashboard data")
async def get_dashboard(ctx: Context) -> str:
    # BAD — raises SkeletonAccessForbidden in v1.6.0.
    data = await ctx.skeleton.get("dashboard")

@ext.schedule("refresh_dashboard", cron="*/5 * * * *")
async def refresh_dashboard(ctx: Context) -> None:
    # BAD — ctx.skeleton.update() does not exist in v1.6.0.
    # Use @ext.skeleton("dashboard", ttl=300) instead — the kernel
    # refreshes it on its own TTL cadence.
```

### Notes

- Skeleton sections are scoped per extension (`extension_id`) and per user (`user_id`).
- `get()` returns `None` (not an error) for missing sections.
- Skeleton saves honour the section's own `app_id`, not the workflow's (I-SKEL-CHECK-STALE-PER-SECTION-APPID).
- Tick interval equals TTL (not TTL/2). If you set `ttl=60`, the section refreshes every 60s. Redis TTL is set to `ttl * 2` as a safety margin.
- Every `/v1/internal/skeleton` call is HMAC-signed with jti replay protection (I-CALL-TOKEN-HMAC).
- For panel-side runtime data that used to live in skeleton, migrate to [`ctx.cache`](context-object.md#ctxcache).

---

## 9. ctx.config -- ConfigClient

Resolved configuration for the extension. The kernel merges config from all scope levels before creating the Context object -- your extension always receives a fully resolved view.

**Hierarchy:** Platform Defaults -> Tenant Defaults -> Tenant Role Defaults -> App Config -> User Overrides -> Tenant Enforced

```python
@ext.tool("analyze", description="Analyze data")
async def analyze(ctx: Context, query: str):
    model = ctx.config.get("models.primary_model")      # "claude-opus"
    language = ctx.config.get("persona.language")        # "ru"
    pii_safe = ctx.config.get("pii_encryption")          # True (enforced by tenant)

    models_section = ctx.config.get_section("models")    # full dict
    all_config = ctx.config.all()                         # everything
```

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get(key, default=None)` | `Any` | Dot-notation access: `"models.primary_model"` |
| `get_section(section)` | `dict` | Full section as deep copy |
| `all()` | `dict` | Complete resolved config (deep copy) |

Config is **read-only**. Extensions cannot modify config -- writes go through the Registry Settings API.

### Context Window Config Keys (2026-04-07)

Per-extension context limits are available via `ctx.config.get("context.*")`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `context.max_tool_rounds` | `int` | 10 | Maximum LLM tool-calling rounds per request. Gmail=15, Notes=5. |
| `context.max_result_tokens` | `int` | 4000 | Maximum estimated tokens per tool result before trimming. |
| `context.list_truncate_items` | `int` | 20 | Max items in list results before truncation. |
| `context.string_truncate_chars` | `int` | 2000 | Max chars for string fields before truncation. |
| `context.keep_recent_verbatim` | `int` | 6 | Recent messages kept in full (not truncated) in history window. |

Platform-level defaults are available via `ctx.config.get("context_defaults.*")`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `context_defaults.default_context_window` | `int` | 20 | Default history window size (overridden by role/user). |
| `context_defaults.max_result_tokens` | `int` | 4000 | Platform default for result trimming. |
| `context_defaults.max_tool_rounds` | `int` | 10 | Platform default for tool rounds. |
| `context_defaults.quality_ceiling_tokens` | `int` | 80000 | Token threshold for quality warning. |
| `context_defaults.max_stored_messages` | `int` | 100 | Max messages stored in Redis history. |
| `context_defaults.history_ttl_days` | `int` | 7 | Redis history TTL in days. |

These values are set via the Panel (Admin > System > PlatformContextDefaults or per-extension Context tab) and resolved through the Unified Config Store hierarchy.

---

## 10. ctx.progress -- Task Progress

First-class `Context` method for reporting task progress to the Panel System Tray. Available on any `Context` dispatched through the chat pipeline.

When a tool takes more than a few seconds, use `ctx.progress()` to update the progress bar visible in the user's Panel task tray.

### Signature

```python
async def ctx.progress(percent: int, message: str) -> None
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `percent` | `int` | Progress percentage, 0-100 |
| `message` | `str` | Status message displayed in the task tray |

### Example

```python
@ext.tool("process_emails", description="Process a batch of emails")
async def process_emails(ctx: Context, folder: str) -> str:
    emails = await fetch_emails(folder)
    total = len(emails)
    for i, email in enumerate(emails):
        await process_one(email)
        await ctx.progress(int((i + 1) / total * 100), f"Processing {i+1}/{total} emails...")
    return f"Processed {total} emails"
```

### Notes

- `ctx.progress` is only available inside tools dispatched through the chat pipeline. It will not exist on Context objects created by skeleton background agents or schedules.
- The progress update is delivered via SSE to the Panel in real time.
- Calling `ctx.progress(100, "Done")` is optional -- the task tray marks completion automatically when the tool returns.

---

## 11. ctx.time -- TimeContext

Kernel-injected time context for timezone-aware extension logic. Read-only, no network call -- computed from user attributes at kernel dispatch time.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `timezone` | `str` | User's IANA timezone (e.g. `America/New_York`). From `attributes.timezone`, default `UTC`. |
| `utc_offset` | `str` | UTC offset string (e.g. `-04:00`) |
| `now_utc` | `str` | Current time in UTC (ISO 8601) |
| `now_local` | `str` | Current time in user's local timezone (ISO 8601) |
| `hour_local` | `int` | Current hour in user's local timezone (0-23) |
| `is_business_hours` | `bool` | `True` if `hour_local` is between 9 and 17 (inclusive start, exclusive end) |

### Example

```python
@ext.tool("smart_greeting", description="Greet based on time of day")
async def smart_greeting(ctx: Context) -> str:
    hour = ctx.time.hour_local
    tz = ctx.time.timezone
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    return f"{greeting}, {ctx.user.email}! (Your timezone: {tz})"

@ext.tool("check_availability", description="Check if within business hours")
async def check_availability(ctx: Context) -> str:
    if ctx.time.is_business_hours:
        return f"Office is open ({ctx.time.timezone}, {ctx.time.now_local})"
    return f"Outside business hours ({ctx.time.timezone}, local hour: {ctx.time.hour_local})"
```

### Notes

- `ctx.time` is always available -- no opt-in needed.
- The timezone comes from the user's `attributes.timezone` field (set via Panel System Tray or `PATCH /v1/users/{id}`). Defaults to `UTC` if not set.
- `is_business_hours` is a simple 9:00-17:00 check in the user's local timezone. For custom business hour ranges, use `hour_local` directly.
- The data is computed once at kernel dispatch time. If a tool runs for several minutes, the values reflect the time when dispatch started.

---

## 12. ctx.extensions -- ExtensionsClient

Inter-extension API for calling another extension's functions directly or emitting events to other extensions. This is the SDK-level API for controlled cross-extension communication — distinct from the Hub's automatic chain routing.

> **When to use:** Use `ctx.extensions.call()` only when your extension has a hard dependency on another extension's data and you need a synchronous result within the same tool round. For most cross-extension workflows, prefer returning structured data and letting the Hub handle chaining automatically.

### Methods

```python
async def call(
    extension_id: str,
    function_name: str,
    **kwargs
) -> ActionResult
```

Call a `@chat.function` on another extension synchronously. Returns the target function's `ActionResult`. Respects RBAC — the calling user must have access to the target extension.

```python
async def emit(event_type: str, data: dict) -> None
```

Emit an event to other extensions that listen via `@ext.signal`. Format: `extension_id.event_name` (e.g. `"notes.created"`). This is the programmatic equivalent of the `event=` decorator on `@chat.function`.

> **SDK 3.5.0 — federal audit closure.** `emit()` now routes through the kernel audit chokepoint (`imperal_kernel.audit.record_action`) before the legacy Redis pub/sub fan-out. Every emit produces an `action_ledger` row in addition to firing the event — federal-grade forensics on extension-emitted events. Extension developer ergonomics are unchanged (signature stable). When run outside a kernel (unit tests), falls back to direct Redis publish with a log warning.

### Example

```python
from imperal_sdk import Extension, Context
from imperal_sdk.chat import ChatExtension
from imperal_sdk.chat.action_result import ActionResult
from pydantic import BaseModel

ext = Extension("my-app")
chat = ChatExtension(ext, "tool_myapp_chat", "My app with cross-extension calls")

class SaveAndNotifyParams(BaseModel):
    title: str
    content: str

@chat.function("save_and_notify", action_type="write", description="Save a note and notify via another extension")
async def save_and_notify(ctx: Context, params: SaveAndNotifyParams):
    # Save locally
    doc = await ctx.store.create("items", {"title": params.title, "content": params.content})
    # Call notes extension to mirror the entry
    result = await ctx.extensions.call("notes", "create_note", title=params.title, content=params.content)
    if result.status == "error":
        return ActionResult.error(f"Saved locally but notes sync failed: {result.message}")
    return ActionResult.success(
        data={"item_id": doc.id, "note_id": result.data.get("note_id")},
        summary=f"Saved and synced to Notes"
    )
```

### Notes

- `ctx.extensions.call()` enforces RBAC — the current user must have access to the target extension.
- Circular calls (A calls B calls A) are detected and raise `CircularExtensionCallError`.
- Use `ctx.extensions.emit()` for fire-and-forget event fanout; use `ctx.extensions.call()` when you need the return value.

---

## 13. ctx.rag -- RAGClient

> **Status: Planned.** Available in a future SDK release. The interface below reflects the approved design from the SDK Contract spec.

Vector search and retrieval for extensions. Backed by Qdrant + LlamaIndex with optional DGX Spark embeddings.

```python
# Planned interface (not yet available)
results = await ctx.rag.search(query="open cases in Q1", collection="cases", top_k=5)
await ctx.rag.index(collection="cases", doc_id="abc123", text="Case content...", metadata={})
```

---

## 14. ctx.memory -- MemoryClient

> **Status: Planned.** Available in a future SDK release. The interface below reflects the approved design from the SDK Contract spec.

Agent memory and knowledge graph for extensions. Backed by Mem0 (fact extraction) and Cognee (graph). Enables extensions to remember user preferences, past interactions, and domain facts across sessions.

```python
# Planned interface (not yet available)
await ctx.memory.remember("User prefers dark mode and compact layout")
facts = await ctx.memory.recall("user preferences")
```

---

## See Also

- **[context-object.md](context-object.md)** -- Full Context object reference (`ctx.user`, `ctx.time`, `ctx.store`, metadata)
- **[concepts.md](concepts.md)** -- Core SDK concepts (extensions, identity, tools, signals, schedules)
- **[skeleton.md](skeleton.md)** -- Skeleton background agent system (TTL, proactive alerts, configuration)
- **[auth.md](auth.md)** -- Authentication, API keys, and tenant management
