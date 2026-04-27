# Core Concepts

**SDK version:** imperal-sdk 0.5.0
**Last updated:** 2026-04-08
**Audience:** Extension developers building on Imperal Cloud

---

## 1. Extensions

An **extension** is the unit of deployment on Imperal Cloud. It is a Python package that defines tools, signals, and schedules using the `imperal-sdk` framework.

### What an extension contains

```python
from imperal_sdk import Extension, Context

ext = Extension("my-extension")

@ext.tool("search", description="Search documents")
async def search(ctx: Context, query: str) -> str: ...

@ext.signal("on_user_login")
async def on_login(ctx: Context, user: dict) -> None: ...

@ext.schedule("daily_report", cron="0 9 * * *")
async def daily_report(ctx: Context) -> None: ...
```

| Component | Decorator | Purpose |
|-----------|-----------|---------|
| **Tools** | `@ext.tool()` | Business logic the AI assistant can invoke |
| **Signals** | `@ext.signal()` | Event handlers triggered by platform events |
| **Schedules** | `@ext.schedule()` | Cron-based background tasks (kernel dispatcher live since 2026-04-18 — see below) |

> **`@ext.schedule` dispatcher availability.** The decorator has existed in the SDK for a while, but the kernel-side cron dispatcher landed only on **2026-04-18** (session 30, GAP-6). Schedules declared before that were accepted by the SDK, written into `imperal.json`, and then silently ignored — `web-tools.wt_monitor_runner` (`cron="0 * * * *"`) never fired for its entire lifetime. The new `imperal_kernel/services/ext_scheduler.py` walks every loaded extension every 60s, matches cron via `croniter.match(cron, now_utc)`, and dedups across the 3 platform workers with Redis SETNX. Schedules run under a synthetic `__system__` user (`scopes=["*"]`); for per-user work the schedule body must iterate users explicitly via the data layer. Every invocation is wall-clock-capped at `IMPERAL_EXT_SCHEDULE_TIMEOUT_S` (default 600s). See `docs/imperal-cloud/conventions.md` invariants **SCHED-EXT-I1/I2**.

### Extension lifecycle

```
1. DEVELOP     imperal init my-extension    Create project
               imperal test                 Run tests locally
               imperal dev                  Local dev server

2. DEPLOY      imperal deploy               Code placed at /opt/extensions/{app_id}/main.py
                                            Manifest auto-generated and uploaded
                                            Tools registered in Registry
                                            Extension goes ACTIVE

3. RUNTIME     Users interact via assistant
               ICNLI OS kernel loads extension (ExtensionLoader)
               ContextFactory creates Context per request
               execute_sdk_tool dispatches tool calls (activity_name is source of truth)
               Signals fire on events
               Schedules run on cron
               Extension activation signals skeleton update_config immediately
               Classifier envelope surfaces per-user skeleton state to the routing LLM

4. UPDATE      Edit code, re-run deploy
               ExtensionLoader detects mtime change
               Auto-reload on next request -- no restarts
               No downtime for users
```

> **No per-extension workers.** All extensions execute through the platform's shared ICNLI Worker. The kernel loads, caches, and dispatches extensions automatically. You deploy code; the platform runs it.

### Manifest auto-generation

The manifest is a JSON declaration of your extension's capabilities. It is **auto-generated** by the SDK from your decorators and type hints:

```bash
imperal manifest    # Generates manifest.json
imperal deploy      # Generates + uploads manifest
```

You never write the manifest by hand. The SDK inspects your `Extension` instance, discovers all `@ext.tool()`, `@ext.signal()`, and `@ext.schedule()` decorators, and produces a complete manifest including parameter schemas, scopes, and capabilities.

---

## 2. Identity

Every entity in Imperal Cloud has a prefixed identifier:

| Entity | Prefix | Example |
|--------|--------|---------|
| User | `imp_u_` | `imp_u_7k3m9x2p` |
| Tenant | `imp_t_` | `imp_t_4n8r2v6q` |
| API Key | `imp_live_` | `imp_live_xxxxxxxx...` |
| Registry Key | `imp_reg_key_` | `imp_reg_key_xxxxxx...` |

### Users

Users are identified by `ctx.user.imperal_id` (format: `imp_u_xxxxx`). This ID is:

- **Stable** across sessions, devices, and channels.
- **Verified** by the Auth Gateway before reaching your extension.
- **Unique** within the platform. The same email address always maps to the same user ID.

### Tenants

A tenant is an organization. All users belong to exactly one tenant. Tenants provide:

- **Data isolation.** Storage, skeleton, and billing are scoped to the tenant.
- **Shared configuration.** Extension settings, AI model defaults, and user permissions are tenant-wide.
- **Billing boundary.** Usage metering and subscription plans apply at the tenant level.

### API keys

Extensions authenticate with the platform using API keys:

- **`imp_live_`** keys are for production use (extension workers, server-to-server calls).
- **`imp_reg_key_`** keys are for administrative Registry operations.
- Keys are created via the Registry API and displayed only once. Store them securely.
- Keys can be revoked instantly via the API.

---

## 3. Two-Tier Storage

Imperal Cloud provides two storage tiers for extensions. Every extension gets Tier 1 automatically. Tier 2 is opt-in.

### Tier 1: Document Store (`ctx.store`)

A managed document store. No schema, no migrations, no connection strings. The Store API backend is **fully operational** -- all CRUD operations work end-to-end with persistent storage.

| Property | Value |
|----------|-------|
| Access | `ctx.store` |
| Provisioned | Automatically for every extension |
| Data model | JSON documents in named collections |
| Storage location | Tenant's own database (not the auth gateway DB) |
| Table creation | Automatic on first write to a new collection |
| Queries | JSON equality filters, sorting, pagination |
| Deletes | Soft deletes (`deleted_at` timestamp) with audit trail |
| Isolation | Per tenant, per extension |
| Max document size | 1 MB |
| Billing | Metered by document count |

```python
# Write
await ctx.store.create("cases", {"title": "Case 42", "status": "open"})

# Read
case = await ctx.store.get("cases", doc_id)

# Query with JSON filters
open_cases = await ctx.store.query("cases", filter={"status": "open"}, limit=10)

# Count
total = await ctx.store.count("cases", filter={"status": "open"})

# Delete (soft -- sets deleted_at, excluded from future queries)
await ctx.store.delete("cases", doc_id)
```

**Use Tier 1 when:**
- You need simple CRUD with key-value or document semantics.
- Your queries are based on equality filters.
- You want zero setup and zero maintenance.
- You need an audit trail of data mutations.

### Tier 2: Dedicated Database (`ctx.db`)

A dedicated PostgreSQL schema for relational queries, joins, and transactions.

| Property | Value |
|----------|-------|
| Access | `ctx.db` |
| Provisioned | On demand (declare `db` capability in manifest) |
| Data model | Relational tables (you define the schema) |
| Queries | Full SQL |
| Isolation | Per tenant, per extension (dedicated schema) |
| Billing | Metered by query count |

```python
# Query
rows = await ctx.db.fetch_all(
    "SELECT id, title FROM cases WHERE status = $1 ORDER BY created_at DESC LIMIT 10",
    ["open"],
)

# Transaction
async with ctx.db.transaction():
    await ctx.db.execute("UPDATE cases SET status = $1 WHERE id = $2", ["closed", case_id])
    await ctx.db.execute("INSERT INTO audit_log (action) VALUES ($1)", ["case_closed"])
```

**Use Tier 2 when:**
- You need JOIN queries, aggregations, or full-text search.
- You need transactions across multiple tables.
- You need custom indexes for performance.

### Choosing between tiers

| Requirement | Tier 1 (Store) | Tier 2 (DB) |
|-------------|:-:|:-:|
| Simple key-value storage | Yes | Overkill |
| Equality-based queries | Yes | Yes |
| JOIN queries | No | Yes |
| Transactions | No | Yes |
| Full-text search | No | Yes |
| Zero setup | Yes | Requires capability declaration |
| Custom indexes | No | Yes |

Most extensions start with Tier 1 and add Tier 2 only when they need relational capabilities.

---

## 4. Multi-Tenant Architecture

Imperal Cloud is multi-tenant by design. Every piece of data is scoped to a tenant, and the platform enforces isolation at every layer.

### Isolation boundaries

```
Tenant: Acme Corp (imp_t_4n8r2v6q)
  |
  +-- Extension: case-manager
  |     +-- Store: cases, audit_log
  |     +-- Skeleton: case_status, dashboard
  |     +-- Files: exports/report.pdf
  |
  +-- Extension: threat-intel
        +-- Store: threats, blocklist
        +-- Skeleton: active_threats
        +-- Files: reports/weekly.md

Tenant: Globex Inc (imp_t_8m2x5k7p)
  |
  +-- Extension: case-manager        <-- Same extension, completely isolated data
        +-- Store: cases, audit_log  <-- Different cases than Acme Corp
```

### What the platform isolates

| Resource | Isolation Key | Mechanism |
|----------|--------------|-----------|
| Documents (ctx.store) | `(tenant_id, app_id)` | Row-level security |
| Database (ctx.db) | `(tenant_id, app_id)` | Dedicated PostgreSQL schema |
| Skeleton | `(app_id, user_id)` | Redis key prefix |
| Files (ctx.storage) | `(tenant_id, app_id)` | S3 key prefix |
| Billing | `tenant_id` | Separate subscription and usage |
| AI usage | `tenant_id` | Separate token budget |

### As an extension developer

You do not need to implement multi-tenancy in your code. The platform handles it transparently:

- `ctx.store.query("cases")` returns only the current tenant's cases.
- `@ext.skeleton("status", ttl=60)` tools write to the current user's skeleton key (kernel-persisted, v1.6.0).
- `ctx.cache.set("key", value, ttl_seconds=60)` writes to the current user's cache slot in this extension's namespace.
- `ctx.storage.upload("file.pdf", data)` stores the file in the current tenant's namespace.
- `ctx.billing.check_limits("ai_tokens")` checks the current tenant's limits.

Write your extension as if there were only one tenant. The platform takes care of the rest.

---

## 5. Automatic Billing and Metering

All platform resource usage is automatically metered and billed to the tenant's subscription.

### Metered resources

| Resource | Metric | How it accrues |
|----------|--------|---------------|
| AI completions | Tokens (input + output) | Per `ctx.ai.complete()` or `ctx.ai.chat()` call |
| Document store | Document count | Per `ctx.store.create()` |
| Database queries | Query count | Per `ctx.db.execute()` / `ctx.db.fetch_all()` |
| File storage | Bytes stored | Per `ctx.storage.upload()` |
| Outbound HTTP | Request count | Per `ctx.http.*()` call |
| Notifications | Notification count | Per `ctx.notify()` |

### Checking limits

Extensions can check billing limits before performing expensive operations:

```python
@ext.tool("premium_feature", description="Run premium analysis")
async def premium_feature(ctx: Context, doc_id: str) -> str:
    if not await ctx.billing.check_limits("ai_tokens"):
        return "Your organization's AI token limit has been reached."
    # Proceed with expensive AI call
    ...
```

### Subscription plans

| Plan | AI Tokens | Documents | Storage | HTTP Requests |
|------|-----------|-----------|---------|---------------|
| Starter | 100K/month | 10K | 1 GB | 10K/month |
| Professional | 1M/month | 100K | 10 GB | 100K/month |
| Enterprise | Custom | Custom | Custom | Custom |

### As an extension developer

- You do not handle payments or subscriptions. The platform manages all billing.
- Your extension code checks limits via `ctx.billing.check_limits()` and reports usage status to users.
- AI calls through `ctx.ai` are automatically metered. You do not need your own API keys for supported models.

---

## 6. Session Model

Every user interaction runs within a **session** -- a long-lived, durable conversational process managed by the platform.

### Key properties

| Property | Value |
|----------|-------|
| Session duration | 24 hours, then auto-renewed |
| Message delivery | Durable signals (queued if worker is temporarily down) |
| History | Last 40 messages, stored in Redis, 7-day TTL |
| Compression | LZ4 for messages over 1 KB |
| Continue-as-new | Resets internal state every 24h without losing context |

### How sessions work

1. User sends a message through the Imperal Panel, API, or integrated channel.
2. The platform delivers the message to the session (creates one if needed).
3. The Tool Discovery Engine routes the message to the best matching extension via semantic search (~50ms). Intent detection catches management operations.
4. The extension's LLM generates a response, calling tools as needed. Auto-reroute handles refusals and errors.
5. Your tool receives `ctx: Context` with full user, skeleton, and history data.
6. Your tool returns a string result.
7. The platform delivers the response to the user.

### Hub mode

In the Imperal Panel, each user has a single unified session (the "hub") that merges tools from **all** of their active extensions. The hub automatically routes tool calls to the correct extension.

This means users do not need to switch between extensions -- they have one assistant that can do everything.

---

## 7. Tool Discovery Engine

> **Replaces (v0.2.0):** The legacy Context Router (GPT-4o-mini domain classification) has been replaced by the [Tool Discovery Engine](../icnli-platform-core/tool-discovery-engine.md) with semantic vector search (~50ms, deterministic).

The Tool Discovery Engine routes user messages to the correct extension tool using embedding-based semantic search.

### How it works

```
User: "Upload this contract to my case"
       |
       v
Intent Detection: _is_admin_intent(message)?
  NO → proceed to discover_tools
       |
       v
discover_tools embeds query → cosine similarity search
Top candidates: [sharelock-v2 (0.45), admin (0.28)]
       |
       v
Auto-reroute loop:
  try sharelock-v2 → handled → DONE
  (or: refused/errored → try admin → try hub_chat)
```

### Intent Detection (2026-04-03)

Management operations (suspend/activate extensions, list users, etc.) are detected by LLM intent classification (Haiku) **before** discover_tools runs. When detected, the admin extension is forced as the first candidate, bypassing embedding ranking.

### Auto-reroute on errors (2026-04-03)

If an extension returns an error response (exception, traceback, internal server error), the session workflow automatically tries the next candidate instead of showing the raw error to the user.

### As an extension developer

You influence routing through your tool descriptions:

```python
# Good -- specific, actionable description
@ext.tool("search_cases", description="Search cases by keyword, status, or date range")

# Bad -- vague description leads to poor routing
@ext.tool("do_stuff", description="Handle requests")
```

Write clear, specific descriptions. The Tool Discovery Engine and primary LLM both read them.

---

## 7a. ICNLI Integrity Protocol (2026-04-03)

The kernel automatically injects 8 zero-hallucination rules into every extension context before tool execution. These rules are enforced at the kernel level -- extensions cannot disable or override them.

### The 8 rules

1. Never fabricate data -- if you lack real data from a function call, say so.
2. Never fabricate URLs -- no OAuth links, API endpoints, or any URLs unless returned by a function.
3. Never claim unverified success -- if a function returned an error, report it honestly.
4. Always call functions for data -- never answer data questions from cached context alone.
5. Report errors honestly -- tell the user exactly what failed and why.
6. Never invent capabilities -- only claim actions you have actual tools for.
7. Never contradict function results -- if a function says "not found", do not say "found".
8. Distinguish "I don't know" from "error" -- missing data is not an error.

### As an extension developer

You do not need to implement these rules. The kernel injects them into the classifier envelope (v1.6.0) and into every LLM call the platform makes on your extension's behalf. If your extension uses an LLM directly via `ctx.ai`, these rules are appended to the system prompt automatically, making the LLM less likely to hallucinate.

For best results, combine with:
- **Let the LLM decide** -- in normal (single) dispatch, let the LLM decide when to call functions vs respond with text. Add a text fallback rule in your system prompt for out-of-scope requests. Note: in chain mode, `tool_choice={"type":"any"}` is **forced by the kernel** on the first LLM round — this is automatic and correct behavior; extension developers do not set this.
- **Verify-after-write** patterns -- after mutating state, read it back to confirm the change
- **Return `ActionResult`** -- use `ActionResult.success(data, summary)` and `ActionResult.error(msg, retryable)` for unambiguous status reporting. Explicit RESULT prefixes in string returns are legacy — use ActionResult instead.

### Narration guardrail (SDK 1.5.24+)

On top of the 8 ICNLI rules, ChatExtension's final narration round is bound to structural truth: the SDK handler passes every narration LLM call through `augment_system_with_narration_rule(system, fc_list)` (module `imperal_sdk.chat.narration_guard`), which appends a frozen, language-agnostic postamble + the live `_functions_called` snapshot. This means the user-facing prose cannot fabricate successes for functions that never ran, and cannot soften `status=error` into a success claim — the truth flows `_functions_called` → postamble → final text. Extensions get this automatically; see Rule 21 in [extension-guidelines.md](extension-guidelines.md).

---

## 8. Skeleton (LLM-only Background State, v1.6.0)

The Skeleton is the routing LLM's view of extension state — auto-refreshed, classifier-visible, read-only for non-skeleton code. See the [Skeleton Reference](skeleton.md) for full v1.6.0 details.

### Summary (v1.6.0)

| Property | Value |
|----------|-------|
| Purpose | Give the classifier / routing LLM fresh state to make target_apps decisions |
| Storage | Redis (keyspace `imperal:skeleton:{app}:{user}:{section}`) + per-section TTL |
| Writer | Kernel `skeleton_save_section` activity (sole writer); `@ext.skeleton` tools RETURN new state |
| Reader | Classifier envelope (automatic), `ctx.skeleton.get(section)` from `@ext.skeleton` tools only |
| Non-skeleton access | Raises `SkeletonAccessForbidden` |
| Change detection | Automatic via `_refreshed_at` + `alert=True` decorator |
| Auth | HMAC call-token on every `/v1/internal/skeleton` call |
| Runtime cache alternative | Use `ctx.cache` (v1.6.0) for panel-side data (TTL 5-300s, Pydantic-typed, 64 KB cap) |

### Why skeleton matters for assistant quality

Without skeleton:
```
User: "How many open cases do I have?"
Assistant: "Let me check..." (calls API, waits 2 seconds)
Assistant: "You have 5 open cases."
```

With skeleton:
```
User: "How many open cases do I have?"
Assistant: "You have 5 open cases. The most recent is 'Contract Review' from today."
(read from ctx.skeleton -- instant, no API call)
```

---

## 9. Namespaces

Extensions run within the platform's namespace architecture. The ICNLI OS kernel manages all extensions through a shared worker pool with per-tenant queue isolation.

### Namespace strategy

| Namespace | Purpose |
|-----------|---------|
| `imperal-hub` | Primary namespace for all extensions. The kernel loads and dispatches extensions here. Merges tools from all active extensions for hub users. |

### What the platform provides

- **Fault isolation.** The kernel wraps each tool execution in error handling. A bug in one extension cannot crash another.
- **Per-tenant queue isolation.** Each tenant's requests are dispatched independently. A slow extension for one tenant cannot starve another.
- **Separate monitoring.** Logs and traces are tagged by `app_id` and `tenant_id` for scoped observability.
- **Zero-downtime deployment.** Updating an extension (new file at `/opt/extensions/{app_id}/main.py`) does not affect other extensions or active sessions.

---

## 10. ICNLI OS Kernel Architecture

The platform runtime is organized as an operating system kernel. Extensions are user-space programs; the kernel provides process isolation, resource management, and a single system call interface.

### Kernel components

| Component | Role | OS Analogy |
|-----------|------|------------|
| **ExtensionLoader** | Loads extension code from `/opt/extensions/{app_id}/main.py`. Uses file mtime for cache invalidation -- deploy new code, and the next request picks it up automatically. No restarts. | Dynamic linker / module loader |
| **ContextFactory** | Creates a fully populated `Context` for each request. Pre-loads `history` (conversation) so tools can read it instantly. Also resolves `ctx.config` from the Unified Config Store (v0.2.0). Wires `ctx.cache` + `ctx.skeleton` (latter guarded — raises `SkeletonAccessForbidden` outside `@ext.skeleton` tools, v1.6.0). | Process environment setup |
| **KernelContext** | Typed dataclass resolved ONCE per message by `resolve_kernel_context` activity. Contains identity, config, confirmation settings, time, language, allowed_apps, routing info. Passed through entire pipeline. | Process credentials / env |
| **execute_sdk_tool** | The single entry point for all tool execution. Requires pre-resolved `_kernel_ctx` (KernelContext). Delegates to `_execute_extension` which enforces RBAC, loads extension, builds Context via `create_from_kctx()`, and dispatches. Hub calls `_execute_extension` directly for dispatch (no re-resolution). | System call (syscall) |
| **Per-tenant queue isolation** | Each tenant's requests are dispatched to isolated task queues. A slow extension for one tenant cannot starve another tenant's requests. | Process scheduling / cgroups |

### Config Resolution (v0.2.0)

As of v0.2.0, configuration is resolved as part of `resolve_kernel_context` activity (was in ContextFactory, moved to KernelContext in v0.5.0). The merged config from the Unified Config Store:

1. Platform Defaults
2. Tenant Defaults + `role_defaults[user.role]`
3. App Config
4. User Overrides
5. Tenant Enforced (cannot be overridden)

The resolved config is injected as `ctx.config` — a read-only `ConfigClient`. See [Auth Gateway — Unified Config Store](../auth-gateway.md#unified-config-store) for details.

### How the kernel executes a tool call

```
1. Message arrives from user (auth verified at API layer)
2. Intent Detection → Tool Discovery Engine selects tool + extension
3. resolve_kernel_context activity (parallel: identity + config + settings + time + language → KernelContext)
4. execute_sdk_tool (kernel syscall, requires _kernel_ctx):
   a. Intercept system tools (discover_tools, hub_chat)
   b. Delegate to _execute_extension (or Hub._dispatch_one for routed calls)
   c. _execute_extension: verify app_id, enforce RBAC, load extension, build Context from KernelContext
   f. ContextFactory builds Context:
      - user identity, history, config, service clients
      - ctx.cache wired (v1.6.0); ctx.skeleton wired with tool_type guard
   g. Inject capability boundary + ICNLI Integrity Protocol
   h. Call tool function with (ctx, message=message)
   i. For @ext.skeleton tools: persist returned state via skeleton_save_section activity
   j. Return result as {"response": dict}, metrics, trace span
4. Auto-reroute if refused/errored → try next candidate
5. Result delivered to user
```

### Extension deployment model

Extensions live at a fixed filesystem path:

```
/opt/extensions/
  my-extension/
    main.py              # Your extension code
    requirements.txt     # Dependencies (installed by platform)
  threat-intel/
    main.py
    requirements.txt
```

When you run `imperal deploy`, the CLI places your code at `/opt/extensions/{app_id}/main.py`. The ExtensionLoader detects the file change via mtime comparison and reloads it on the next request. There is no restart, no downtime, and no coordination with other extensions.

### Key design principles

- **Single execution path.** All extension code runs through `execute_sdk_tool`. There is no way to skip metrics or bypass the kernel. The kernel enforces RBAC (required_scopes) before dispatching to extensions -- two-layer defense with Auth Gateway at the API layer and kernel at the dispatch layer.
- **Pre-loaded context.** The ContextFactory loads history before your tool runs. Reading `ctx.history` is a list access, not a network call. Skeleton is LLM-only in v1.6.0 — use `ctx.cache` for panel-side runtime data.
- **Mtime-based cache.** The ExtensionLoader caches loaded modules keyed by `(app_id, mtime)`. Deploy = new mtime = auto-reload. No restarts needed.
- **Shared workers.** There are no per-extension workers. All extensions share the platform's ICNLI Worker pool, which handles scheduling, fault tolerance, and scaling transparently.

---

## 11. Inter-Extension Communication (v0.2.0)

Extensions can discover and call other extensions through `ctx.tools`. All calls route through the kernel's `execute_sdk_tool` as OS-level syscalls:

- **RBAC enforced** — caller must have required scopes
- **Audit trail** — all cross-extension calls are logged
- **Capability boundary** — extensions know what they can and cannot do

```python
tools = await ctx.tools.discover("case analysis")
result = await ctx.tools.call("tool_sharelock_chat", {"message": query})
```

This is analogous to Unix IPC — processes cannot access each other's memory directly; they communicate through kernel syscalls.

---

## 12. Extension Primitives Summary

```
+-----------------------------------------------------------------------+
|                        Extension ("my-app")                            |
|                 /opt/extensions/my-app/main.py                        |
|                                                                       |
|  +------------------+  +-------------------+  +---------------------+ |
|  |  Tools           |  |  Signals          |  |  Schedules          | |
|  |  @ext.tool()     |  |  @ext.signal()    |  |  @ext.schedule()    | |
|  |                  |  |                   |  |                     | |
|  |  Called by LLM   |  |  Called by events  |  |  Called by cron     | |
|  |  Receives message |  |  Returns None     |  |  Returns None       | |
|  |  Returns ActionResult (chat.function) / string (ext.tool)      | |
|  +------------------+  +-------------------+  +---------------------+ |
|                                                                       |
|  +------------------------------------------------------------------+ |
|  |                     Context (ctx)                                 | |
|  |                  Created by ContextFactory                        | |
|  |                                                                   | |
|  |  .user           Authenticated user identity                     | |
|  |  .history        Pre-loaded conversation history (read-only)     | |
|  |  .config         Resolved platform config (read-only)            | |
|  |  .store          Tier 1: document store                          | |
|  |  .db             Tier 2: dedicated database                      | |
|  |  .ai             AI completions (metered)                        | |
|  |  .skeleton       v1.6.0: LLM-only read-only; forbidden elsewhere | |
|  |  .cache          v1.6.0: Pydantic-typed runtime cache (5-300s)   | |
|  |  .billing        Subscription and usage (read-only)              | |
|  |  .notify         Push notifications                              | |
|  |  .storage        File storage (S3-compatible)                    | |
|  |  .http           Outbound HTTP (logged)                          | |
|  |  .tools          Inter-extension IPC                             | |
|  |  .time           Kernel TimeContext (timezone, hours, biz hrs)  | |
|  |  ._user_language      Detected language ISO code (kernel-set)    | |
|  |  ._user_language_name Human-readable language name (kernel-set) | |
|  |  ._confirmation_required  2-Step Confirmation flag (kernel-set) | |
|  +------------------------------------------------------------------+ |
|                                                                       |
|  Executed via: execute_sdk_tool (ICNLI OS kernel)                    |
|  Loaded by:    ExtensionLoader (mtime-based cache)                   |
+-----------------------------------------------------------------------+
```

---

## Next Steps

| What | Where |
|------|-------|
| Build your first extension in 5 minutes | [Quickstart](quickstart.md) |
| Full Context object reference | [Context Object](context-object.md) |
| Tools: scopes, parameters, error handling | [Tools](tools.md) |
| Skeleton: TTL, change detection, proactive alerts | [Skeleton](skeleton.md) |
| Registry and Auth Gateway API | [API Reference](api-reference.md) |
| Platform architecture overview | [Platform Overview](../overview.md) |
