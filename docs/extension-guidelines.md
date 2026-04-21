# Extension Development Guidelines

**SDK version:** imperal-sdk 1.5.17
**Last updated:** 2026-04-21 (session 37 — Markdown rendering hygiene: Layer 1 `kernel_formatting_rule.txt` rewrite with DO / NEVER pair teaches the model well-formed Markdown; Layer 2 `imperal_sdk.chat.filters.normalize_markdown` (new) trims `** text **` → `**text**` glitches. Auto-applied at every `ChatExtension._handle` text return. Invariants I-MD-1, I-MD-2. Session 33 — Panel automatic visual styling: Tailwind `@theme` colour remap + container-level padding philosophy + ext-pane padding on ExtensionShell + horizontal Stack auto-wrap + element-level sizing tokens + ESLint wall blocking hardcoded Tailwind scales in Panel code. v1.5.16: `ui.Stack(wrap=...)` now tri-state — `wrap=False` on horizontal Stacks correctly opts out of Panel auto-wrap. Extension authors: see Rule 19 below. Emit semantic intent via `variant=`/`color=` — never hardcode colours or Tailwind classes. v1.5.15 ships `ui.theme(ctx)` accessor + `Context.agency_theme` + Auth GW `PUT /v1/agencies/{id}/theme` with Pydantic WCAG AA validation. Earlier: v1.5.8 session 30 `NotifyProtocol` + webhook URL + `@ext.schedule` dispatcher + fast-RPC Redis-Streams `/call` (388ms→3ms). v1.5.7 PEP 563 validator fix. v1.5.6 CRITICAL FC.result event-publishing fix. v1.5.5 `ui.Graph` Cytoscape. v1.5.4 `@ext.tray()` + OS identity. Session 20 baseline.)

> **v1.5.6 — critical event-publishing fix.** `@chat.function(action_type="write"|"destructive", event="X")` now actually publishes the event through the kernel. Pre-v1.5.6 `ChatExtension._make_chat_result` built `FunctionCall` without the `result` field, so the kernel's event-publishing check at `extension_runner.py` Step 10b never fired. Any extension relying on sidebar `refresh="on_event:X"` or automation rules triggered by `event_type` was silently broken. Upgrading to v1.5.6 requires a companion kernel patch (`extension_runner.py` must hydrate dict-form `ActionResult` via `ActionResult.from_dict()` after Temporal transport). Both fixes are already deployed on platform workers; third-party extension developers should pin `imperal-sdk>=1.5.6`.

### New decorators in v1.2.0

In addition to `@chat.function`, `@ext.tool`, and `@ext.health_check`, the following decorators are now available:

| Decorator | Purpose |
|-----------|---------|
| `@ext.panel()` | Register a Panel page component |
| `@ext.widget()` | Register a dashboard widget |
| `@ext.on_install` | Lifecycle hook — runs once on first install |
| `@ext.on_upgrade(version)` | Lifecycle hook — runs when extension upgrades to `version` |
| `@ext.on_uninstall` | Lifecycle hook — runs before extension is removed |
| `@ext.on_enable` | Lifecycle hook — runs when extension is enabled by admin |
| `@ext.on_disable` | Lifecycle hook — runs when extension is disabled |
| `@ext.health_check` | Health probe (existed since v1.0.0) |
| `@ext.webhook(path, method="POST", secret_header="")` | Register an inbound webhook at **`POST /v1/ext/{app_id}/webhook/{path}`**. Handler signature: `async def fn(ctx, headers: dict, body: str, query_params: dict)`. Optional `secret_header` names a header whose value the handler must verify (platform does not auto-verify). Also registers `__webhook__{path}` as a ToolDef so DirectCallWorkflow can dispatch it via `/call`. ctx is minimal (`user_id="__webhook__"`). |
| `@ext.on_event(event_type)` | React to platform events from other extensions. Handler signature: `async def fn(ctx, event: dict)` where `event` has `{type, scope, action, data, tenant_id, user_id, timestamp}`. See Event Model in [`realtime-action-propagation-design.md`](../../superpowers/specs/2026-04-03-realtime-action-propagation-design.md). |
| `@ext.expose(name, action_type="read")` | Expose a method for inter-extension IPC via `ctx.extensions.call(app_id, name, **kwargs)`. `action_type` is one of `"read"` / `"write"` / `"destructive"` and gates the call on the caller's scopes. Circular call detection via kernel call-stack guard. |
| `@ext.tray(tray_id, icon="Circle", tooltip="")` | Declare a system tray item in the OS top bar (SDK 1.5.4+). Handler returns a `UINode` tree with badge + optional dropdown. Called via `/call` as `__tray__{tray_id}`. See `TrayResponse`. |
| `@ext.schedule(name, cron)` | Cron-based background task. Dispatcher lives in `imperal_kernel/services/ext_scheduler.py` (live since 2026-04-18 session 30). Runs under synthetic `__system__` user (`scopes=["*"]`); iterate real users inside the handler if needed. 3-worker Redis-SETNX dedup guarantees exactly one worker fires per minute. Wall-clock cap `IMPERAL_EXT_SCHEDULE_TIMEOUT_S=600s` default. |

> **ChatExtension internals (v1.2.0):** `ChatExtension` is now split internally into 5 files — `extension.py`, `handler.py`, `guards.py`, `filters.py`, `prompt.py`. This is a kernel-internal refactor. Developer imports are unchanged: `from imperal_sdk.chat import ChatExtension` works as before.

## The Golden Rule: ONE Entry Point Per Extension

Every extension MUST have exactly ONE user-facing tool, powered by `ChatExtension`. This ensures:
- discover_tools always finds your extension correctly (one embedding, not nine)
- LLM routing inside your extension handles all user intents
- ICNLI Integrity rules are automatically enforced
- No routing conflicts between your functions

## Architecture Pattern

```python
from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension
from imperal_sdk.chat.action_result import ActionResult
from pydantic import BaseModel

ext = Extension("my-app", version="1.0.0")

chat = ChatExtension(
    ext=ext,
    tool_name="tool_myapp_chat",
    description="Clear description of ALL capabilities for embedding search",
    system_prompt="You are the My App assistant. You handle X, Y, Z.",
    model="claude-haiku-4-5-20251001",
)

class DoXParams(BaseModel):
    input: str

@chat.function("do_x", action_type="read", description="Does X")
async def do_x(ctx, params: DoXParams):
    # Business logic ONLY -- no LLM, no routing, no parsing
    page = await ctx.store.query("collection")
    return ActionResult.success(data={"items": page.items}, summary=f"{len(page.items)} items found")

@chat.function("do_y", action_type="write", event="done", description="Does Y")
async def do_y(ctx):
    return ActionResult.success(data={"status": "done"}, summary="Y completed")

# Skeleton tools are separate (internal, platform-called)
@ext.tool("skeleton_refresh_myapp", description="Skeleton refresh")
async def on_refresh(ctx, **kwargs):
    ...
```

## Rules

### 1. ONE Entry Point
Use `ChatExtension` for ALL user-facing functionality. Register only ONE tool in Registry.

Wrong:
```python
@ext.tool("app_connect", ...)    # 5 separate tools
@ext.tool("app_list", ...)       # discover_tools can't pick correctly
@ext.tool("app_read", ...)
@ext.tool("app_write", ...)
@ext.tool("app_delete", ...)
```

Right:
```python
chat = ChatExtension(ext, "tool_app_chat", "Manages connections, lists, reads, writes, and deletes")

@chat.function("connect", ...)   # LLM routes internally
@chat.function("list", ...)
@chat.function("read", ...)
@chat.function("write", ...)
@chat.function("delete", ...)
```

### 2. Business Logic Only in Functions
Functions contain ONLY business logic. No LLM calls, no message parsing, no routing decisions.

Wrong:
```python
async def inbox(ctx, message=""):
    if "read" in message:           # Manual routing -- fragile
        return await read_email(ctx, ...)
    if re.search(r'ID', message):   # Regex parsing -- unreliable
        ...
```

Right:
```python
async def inbox(ctx, max_results=20):
    messages = await fetch_inbox(ctx)
    return {"messages": messages}   # Just data. LLM decides next step.
```

### 3. Return Structured Data
Functions return dicts with structured data. ChatExtension's LLM formats the response for the user.

Wrong: `return {"response": "**Inbox:**\n1. Email from..."}`
Right: `return {"messages": [...], "count": 20, "account": "user@gmail.com"}`

### 4. Typed Parameters
Define parameters as a Pydantic `BaseModel`. ChatExtension auto-generates tool schemas for the LLM from the model's fields and type annotations. This is the v1.0.0 standard — JSON Schema dicts are still accepted for backwards compatibility but Pydantic is preferred.

```python
from pydantic import BaseModel, Field
from typing import Literal

class ReadEmailParams(BaseModel):
    message_id: str = Field(description="Email message ID")
    format: Literal["full", "summary"] = Field(default="full", description="Output format")

@chat.function("read_email", description="Read full email content by message ID")
async def read_email(ctx, params: ReadEmailParams):
    # params.message_id, params.format are type-safe and validated
    ...
```

Fields without a `default` are automatically required. `Field(description=...)` populates the LLM tool schema. Use `Literal[...]` for enum constraints, `Optional[T]` for nullable fields.

> **Migration from JSON Schema dicts:** Replace `params={...}` dict with a `BaseModel` subclass and a single `params:` argument. The SDK auto-detects which style is used based on the function signature.

### 5. Action Types (KAV)

Every `@chat.function` accepts an `action_type` parameter that controls Kernel Action Verification (KAV) and 2-Step Confirmation behavior:

| `action_type` | Use case | Confirmation |
|---------------|----------|-------------|
| `"read"` (default) | Listing, searching, reading data | Never |
| `"write"` | Creating, updating, sending | Only if user has confirmation enabled |
| `"destructive"` | Deleting, revoking, suspending | Always triggers if confirmation is enabled |

```python
from pydantic import BaseModel, Field

class CreateNoteParams(BaseModel):
    title: str = Field(description="Note title")
    content: str = Field(description="Note body")

class DeleteNoteParams(BaseModel):
    note_id: str = Field(description="Note ID to delete")

@chat.function("list_notes", action_type="read", description="List all notes")
async def fn_list_notes(ctx):
    page = await ctx.store.query("notes")
    return {"notes": page.items}

@chat.function("create_note", action_type="write", description="Create a new note")
async def fn_create_note(ctx, params: CreateNoteParams):
    ...

@chat.function("delete_note", action_type="destructive", description="Delete a note permanently")
async def fn_delete_note(ctx, params: DeleteNoteParams):
    ...
```

When confirmation is triggered, the kernel intercepts the call and presents a confirmation card to the user. The function only executes after the user explicitly confirms.

**2-Step Confirmation exact-category matching (2026-04-08):** The executor ALWAYS loads confirmation settings at the start of every message (skipped only for system/skeleton/automation tasks). The executor passes `ctx._confirmation_actions` as a dict (e.g. `{"destructive": True, "write": False}`). `ChatExtension` checks the REAL `action_type` from `@chat.function` against EXACT per-category settings. The Hub intent classification is **irrelevant** — only the decorator's `action_type` determines whether confirmation fires.

```python
# User setting: confirm destructive=yes, write=no
@chat.function("delete_note", action_type="destructive")  # INTERCEPTED → confirmation card
@chat.function("create_note", action_type="write")        # NOT intercepted (write=no)
@chat.function("list_notes",  action_type="read")         # NEVER intercepted
```

**Automation bypass:** Automations (`_is_automation=True`) ALWAYS skip confirmation — there is no user to confirm. The confirmation flow is user-only.

**Write blocking (single dispatch only):** When the kernel's Intent Classifier (session 41, ICNLI v7 P7) sets `intent.action_type="read"` in single dispatch mode, the kernel blocks functions with `action_type="write"` or `"destructive"`. The extension receives a KAV rejection. This prevents accidental destructive actions when the user is only browsing data.

**Intent guard bypass:** Chain mode (`_intent_type="chain"` on `ctx`) and automation mode (`_intent_type="automation"` on `ctx`) bypass the intent guard entirely. In these modes, the function's `action_type` from the `@chat.function` decorator is the authoritative source of truth -- the kernel trusts it without per-call LLM intent verification. The SDK-facing attribute `ctx._intent_type` is populated by the kernel from its authoritative `IntentClassification` record:

| Classifier signal | `ctx._intent_type` value | SDK guard behaviour |
|---|---|---|
| `is_system_actor=True` (automation / mcp / system) | `"automation"` | bypass, dispatch proceeds |
| `chain_mode=True` (kernel-side chain loop) | `"chain"` | bypass, dispatch proceeds |
| else -- user turn | `intent.action_type` in {`"read"`, `"write"`, `"destructive"`} | guard enforces contract match against `@chat.function(action_type=...)` |

**For extension authors -- nothing changes in your code.** Keep declaring `action_type` on each `@chat.function`; keep reading `ctx._intent_type` if you need to branch on it (rare). The session 41 rework is entirely kernel-side: it replaces the pre-session-41 trio of conflicting intent sources (keyword_router substring matching, `kctx.intent_type` default, dict-passed bypass flags) with a single upfront structured-output LLM call. Your `action_type` decorator remains the contract you own; the kernel now has a reliable signal to compare it against. See `docs/imperal-cloud/intent-classifier.md` in the platform docs for the kernel-side spec.

### 5b. ActionResult Return Pattern

Every `@chat.function` MUST return `ActionResult`. Use factory methods -- invalid states impossible.

```python
from imperal_sdk.chat.action_result import ActionResult
from pydantic import BaseModel, Field

class SendEmailParams(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body text")

@chat.function("send_email", action_type="write", event="sent", description="Send an email")
async def fn_send_email(ctx, params: SendEmailParams):
    try:
        result = await ctx._api.send(to=params.to, subject=params.subject, body=params.body)
        return ActionResult.success(
            data={"message_id": result["id"], "to": params.to, "subject": params.subject,
                  "thread_id": result.get("thread_id"), "account": ctx._current_account},
            summary=f"Email sent to {params.to}"
        )
    except RateLimitError:
        return ActionResult.error("Rate limited by provider", retryable=True)
    except AuthError:
        return ActionResult.error("Account disconnected", retryable=False)
```

**Rules:**
- `data` dict = variables accessible in automation templates via `{{steps.N.data.key}}`
- `summary` = one-line human-readable description
- `retryable=True` for transient errors (rate limit, timeout, network)
- `retryable=False` for permanent errors (auth, not found, invalid input)
- SDK validates: no `ActionResult` -> warning logged, no events published

### 5c. Event Publishing

Declare `event=` on `@chat.function` for write/destructive functions. Kernel auto-publishes.

```python
@chat.function("send_email", action_type="write", event="sent")       # -> mail.sent
@chat.function("delete_note", action_type="destructive", event="deleted")  # -> notes.deleted
@chat.function("list_notes", action_type="read")                        # no event (read)
```

- `event` is opt-in. No `event=` -> no event published.
- Only published when `ActionResult.status == "success"`.
- Event `data` = `ActionResult.data` (same dict, zero mapping).
- Automation rules trigger on these events: `"When mail.sent -> ..."`.

### 6. ID Field Naming Convention (CRITICAL)

When returning data that contains IDs, the field name **MUST match** the parameter name of the function that consumes it. This prevents LLM ID fabrication — the #1 source of API errors.

```python
from pydantic import BaseModel, Field

class DeleteNoteParams(BaseModel):
    note_id: str = Field(description="Note ID to delete")

# CORRECT: list returns "note_id" → delete expects params.note_id
@chat.function("list_notes", action_type="read")
async def fn_list(ctx):
    return ActionResult.success(data={
        "notes": [{"note_id": "abc123", "title": "My note"}]
    })

@chat.function("delete_note", action_type="destructive", description="Delete a note permanently")
async def fn_delete(ctx, params: DeleteNoteParams):
    # params.note_id is the exact field name — matches what list_notes returns
    ...

# WRONG: list returns "id" but delete expects params.note_id
# LLM invents IDs like "my_note_about_meeting" → API 400 error
```

**Apply to ALL extensions:** `message_id` (mail), `rule_id` (automations), `note_id` (notes), `case_id` (sharelock). The kernel injects `KERNEL ID INTEGRITY RULE` but correct naming makes it work reliably.

### 7. Check Before Act
For operations that might be unnecessary (connect, delete), check state first.

```python
@chat.function("connect", description="Connect account. Checks if already connected.")
async def connect(ctx):
    existing = await ctx.store.query("accounts")
    if existing:
        return {"already_connected": True, "email": existing[0].get("email")}
    # Only proceed if not connected
    url = build_auth_url(ctx)
    return {"auth_url": url}
```

### 7. Skeleton Tools Are Separate
Background refresh and alert tools use `@ext.tool` (not `@chat.function`). They're called by the platform skeleton workflow, not by users.

```python
@ext.tool("skeleton_refresh_myapp", description="Skeleton refresh")
async def on_refresh(ctx, **kwargs):
    # Fetch fresh data, return for skeleton cache
    return {"response": {"data": fresh_data}}
```

### 8. ICNLI Integrity Is Automatic
ChatExtension injects ICNLI Integrity rules into every LLM call. You cannot disable them. Your functions should:
- Return honest error messages when things fail
- Never fabricate data -- return what the API/DB actually gave you
- Use structured RESULT fields for action outcomes

### 8b. Scope Declaration (Info.plist / AndroidManifest pattern, session 27+)

The kernel ExtensionLoader extracts your extension's **granted capability set** as the union of two declaration sites. At dispatch time it enforces `tool.required_scopes ⊆ extension.declared_scopes` — defense-in-depth alongside Auth Gateway RBAC.

**Canonical pattern:**

```python
from imperal_sdk import Extension, ChatExtension

ext = Extension(
    "my-ext",
    version="1.0.0",
    capabilities=["mail:read", "mail:send"],  # extension-level surface
)

chat = ChatExtension(ext, tool_name="mail", description="Mail client")

@chat.function("send_mail", scopes=["mail:send"],  # per-tool (optional, tightening)
               description="Send an email", action_type="write")
async def send_mail(ctx, params): ...
```

Rules:
- Declare at **extension level** (`capabilities=[...]`) for the broad permission surface.
- Declare **per-tool** (`scopes=[...]` on `@chat.function` or `@ext.tool`) only when a specific tool needs less than the whole set (or for documentation clarity).
- The loader takes the **union** — missing one does not block the other.
- **Session 27 change:** the auto-registered ChatExtension entry tool now uses `scopes=[]` (previously `["*"]`). The granted set is derived from your declarations.
- **If you declare nothing at all**, the loader logs a `[SCOPES] Extension 'X' declared no scopes — using wildcard fallback` WARN and grants `["*"]` for backwards compat. This is the migration signal.
- **Colon is canonical:** `mail:send`. Dot format (`mail.send`) still accepted for legacy code.

Common scope namespaces: `mail:*`, `admin:*`, `store:*`, `config:*`, `storage:*`, `ai:complete`, `notify:push`, `sharelock:cases:*`, `reports:export`, `*` (superadmin).

See [auth.md — Scopes & Permissions](auth.md#scopes--permissions) for the full reference. Matching rules (wildcards, hierarchy) are owned by the kernel `scope_guard` — see `docs/imperal-cloud/conventions.md`.

### 9. Description Is Your Embedding
The `description` in ChatExtension constructor is what discover_tools searches against. Include ALL capability keywords:

Wrong: `description="Mail extension"`
Right: `description="Mail Client -- inbox, read emails, send, reply, forward, search, archive, delete, mark read/unread, star, browse folders, view threads, bulk operations. Connect Google, Microsoft, Yahoo, IMAP."`

### 10. System Prompt Guides the LLM
Your `system_prompt` tells the LLM HOW to use your functions. Be specific about multi-step flows:

```python
system_prompt = """
For "what's the latest email" -- call inbox() FIRST, then read_email(message_id=FIRST_ID).
For "connect" -- call status() FIRST. Only show auth URL if not connected.
"""
```

### 11. Action Completion and `_handled` Flag

ChatExtension sets `_handled=True` when at least one `@chat.function` was called during the request. It sets `_handled=False` when the LLM responded with only text (e.g., a clarifying question) without invoking any function. Only `_handled=True` requests are recorded as actions in the ledger.

This means clarifying questions ("Which note did you mean?") do not produce action records — correct behavior. Functions that return `ActionResult.success` with write/destructive `action_type` trigger event publishing automatically.

### 12. Chain Mode Behavior

When Hub executes a chain (multi-extension request), your extension receives `_chain_mode=True` in context. In chain mode:

- **`tool_choice: {"type": "any"}`** is forced on the first LLM round -- the kernel guarantees your extension calls a function (no text-only responses).
- **`_intent_type="chain"`** bypasses the intent guard -- write and destructive actions are allowed without LLM intent verification. The function's `action_type` from the `@chat.function` decorator is the source of truth.
- Your extension receives ONLY its portion of the user's request (per-step message from `_plan_chain_steps`).
- Previous chain step results may be injected into context for data continuity.
- Same extension can appear multiple times in a chain (e.g., mail read -> notes create -> mail send).
- Your extension does not need special handling -- chain mode is transparent. Just follow the ChatExtension pattern and return structured data.

### 13. Response Enforcement

The SDK automatically enforces response quality rules on every LLM response before delivery. The three public filter functions live in `imperal_sdk.chat.filters` and are invoked by `ChatExtension._handle()` after each LLM turn. Extensions do not need to call them manually:

- **`enforce_response_style(text)`** — strips Unicode emojis (all major ranges + keycap sequences), strips known filler / reassurance phrases (e.g. "let me know", "дайте знать"), and collapses excessive blank lines. Extensions produce clean, professional text.
- **`enforce_os_identity(text)`** — enforces OS identity: **66 total patterns** (14 redirect + 52 self-id). Strips any sentence where the LLM (a) redirects the user to another extension (e.g. "ask the Notes extension to...") or (b) self-identifies as a specific extension/app/assistant ("I'm the mail assistant", "я помощник по заметкам", ...). The Hub handles all cross-extension routing automatically; individual extensions must never attempt to redirect users or claim an extension-specific identity. If the full response is stripped, it falls back to a neutral `"How can I help?"` / `"Чем могу помочь?"` based on Cyrillic detection.
- **`trim_tool_result(content, max_tokens=3000, list_max=5, str_max=500)`** — kernel-applied on tool results that enter LLM context. Preserves ID-like fields (`id`, `message_id`, `thread_id`, `from`, `to`, `subject`, `status`, ...); truncates large free-text fields (`body`, `content`, `html`, `snippet`, `analysis`, ...). Lists over `list_max` are capped with a `"[...N more items]"` marker.
- **Language enforcement (automatic):** Kernel detects user language per-message via `_route_with_llm()` — Haiku returns `"app_id|INTENT|LANG"` (3 values, 1 call, zero regex). Detected ISO code persisted in Redis `imperal:user_lang:{user_id}` (TTL 24h). For short acks that skip Haiku routing, the kernel reads from this Redis cache. Executor injects `ctx._user_language` (ISO code) and `ctx._user_language_name` (e.g. "Russian"). `ChatExtension._build_system_prompt()` automatically injects `"KERNEL LANGUAGE RULE (NON-NEGOTIABLE): You MUST respond ONLY in {language}"` into every LLM call. Language switches instantly per-message. Extension developers do NOT need to implement language detection or add language rules to system prompts — it is fully automatic and non-overridable.

Extensions do not need to implement these rules -- they are applied automatically by ChatExtension. However, keep them in mind when writing system prompts: do not instruct the LLM to suggest other extensions, and do not hardcode a response language.

> **Note:** Markdown formatting is enforced at the kernel level. Your extension's responses will automatically be formatted with bold, lists, code spans, etc. You do NOT need to add formatting instructions to your system prompt — the kernel injects `KERNEL FORMATTING RULE` automatically.

### 14. Context Window Management (Automatic)

The platform manages LLM context size automatically. Extension developers do not need to worry about token limits or history truncation -- six kernel guards handle it:

**Tool result trimming:** Large tool results are automatically trimmed before entering LLM context. Fields like `id`, `email`, `status` are always preserved; large fields like `body`, `content`, `html` are truncated first. Lists are capped and strings shortened. This is kernel-level -- no developer action needed.

**Per-extension tool rounds:** The maximum number of LLM tool-calling rounds is configurable per extension via the Unified Config Store:

```python
# Reads from extension config (scope=app, key=context)
max_rounds = ctx.config.get("context.max_tool_rounds")  # mail=15, notes=5, default=10
```

Configure via the **Context tab** in the SettingsModal on the Panel (Admin > Extensions > Settings). Platform defaults apply when no extension-specific value is set.

**History window:** The number of messages visible to the LLM is controlled by the user's role (`context_window` column on roles table, default 20 for users, 40 for admin). Recent messages are kept verbatim; older messages are truncated. This ensures the LLM always sees recent context without exceeding token budgets.

**What this means for developers:**
- Return large datasets freely -- the kernel trims them for LLM context automatically.
- Functions that return lists of 100+ items work correctly -- the LLM sees a truncated preview with count metadata.
- No need to manually limit history or implement context windowing.

### 15. Task Cancellation

When a user cancels a running task, the extension receives a `TaskCancelled` exception. Extensions can catch it for cleanup:

```python
from imperal_sdk.chat import TaskCancelled
from pydantic import BaseModel, Field

class LongOpParams(BaseModel):
    dataset_id: str = Field(description="Dataset to process")

@chat.function("long_operation", action_type="write", description="Process large dataset")
async def fn_long_op(ctx, params: LongOpParams):
    try:
        await ctx.progress(10, "Starting...")
        # ... long work ...
        await ctx.progress(80, "Almost done...")
        return {"status": "completed"}
    except TaskCancelled:
        # cleanup if needed (close connections, rollback partial work)
        return {"status": "cancelled"}
```

If you do not catch `TaskCancelled`, the platform handles it gracefully -- the task is marked as cancelled and the user is notified. Only catch it if your function needs explicit cleanup (e.g., rolling back a partial database write).

### 16. Validation with `imperal validate`

Before publishing an extension, run `imperal validate` to check compliance against the V1-V12 rules:

```bash
imperal validate /opt/extensions/my-app/
```

The CLI checks:
- **V1** — Extension has exactly one `ChatExtension` entry point
- **V2** — All `@chat.function` handlers return `ActionResult`
- **V3** — No direct `anthropic` imports (use `ctx.ai` or LLM Provider)
- **V4** — All `@chat.function` params use Pydantic `BaseModel` (or JSON Schema for backwards compat)
- **V5** — Write/destructive functions declare `event=` or explicitly omit it
- **V6** — No hardcoded credentials (use env vars)
- **V7** — ID field names match between producer and consumer functions
- **V8** — `@ext.tool` skeleton tools return `{"response": dict}`
- **V9** — No files exceed 300 lines
- **V10** — Extension has a `__init__.py` or `main.py` entry point
- **V11** — All functions have descriptions (required for embedding search)
- **V12** — No circular `ctx.extensions.call()` chains

Validation failures are reported as errors (block publish) or warnings (advisory). Run `imperal validate --strict` to treat warnings as errors.

### 17. Health Check (`@ext.health_check`)

Recommended for all production extensions. The platform pings this endpoint periodically and reports status in the Admin panel.

```python
@ext.health_check
async def health(ctx) -> dict:
    """Return health status. Raise an exception to report unhealthy."""
    # Check critical dependencies
    accounts = await ctx.store.count("accounts")
    return {
        "status": "ok",
        "accounts_connected": accounts,
        "version": ext.version,
    }
```

If the health check raises an exception, the platform marks the extension as degraded and can alert the admin. Keep health checks fast (< 2 seconds) — they run on a frequent schedule.

### 18. Inter-Extension Communication (`ctx.extensions.call()`)

Use `ctx.extensions.call()` when your extension has a hard dependency on another extension's function result within the same tool round. For most cross-extension workflows, return structured data and let the Hub handle chaining automatically.

```python
from pydantic import BaseModel, Field

class SyncToNotesParams(BaseModel):
    title: str = Field(description="Item title")
    content: str = Field(description="Item content")

@chat.function("sync_to_notes", action_type="write", description="Save item and sync to Notes")
async def sync_to_notes(ctx, params: SyncToNotesParams):
    doc = await ctx.store.create("items", {"title": params.title, "content": params.content})
    # Direct call to notes extension (user must have notes access)
    result = await ctx.extensions.call("notes", "create_note",
                                       title=params.title, content=params.content)
    return ActionResult.success(
        data={"item_id": doc.id, "note_id": result.data.get("note_id")},
        summary="Saved and synced to Notes"
    )
```

See [SDK Clients — ctx.extensions](clients.md#12-ctxextensions----extensionsclient) for full API.

### 19. UI Styling — Emit Semantic Intent, NEVER Hardcode Visuals

**Rule, enforced platform-wide as of session 33 (2026-04-20):**
Your extension emits **semantic UI intent** via the `ui.*` API. The Panel handles every visual concern — colours, padding, spacing, borders, dark/light mode, agency-specific theming, responsive wrap. Your extension code should have **ZERO styling knowledge**.

```python
# ✅ Good — semantic intent
ui.Button("Save", on_click=ui.Call("save"), variant="primary")
ui.Pill(text="Active", color="success")
ui.Card(title="Report", content=ui.Text("Run complete."))
ui.Stack(direction="h", children=[btn1, btn2, btn3])   # auto-wraps on narrow panes

# ❌ Bad — styling in extension code
ui.Text("...", className="bg-blue-500 px-4 py-2 rounded-md")   # DON'T
ui.Card("...", style={"backgroundColor": "#2563eb"})            # DON'T
ui.Button("...", className="bg-red-600 text-white")             # DON'T — use variant="danger"
```

**What the Panel guarantees for every extension:**

| Guarantee | Driven by |
|-----------|-----------|
| Consistent outer padding around pane content | `ExtensionShell` `ext-pane` utility (token-driven) |
| Consistent vertical rhythm between siblings | `--imp-page-gap` cascade |
| Agency colour theming across every surface | `agencies.theme` JSON → `--imp-color-*` tokens → Tailwind remap → every class |
| Dark / light mode toggle | `data-theme="dark"` on `<html>` flips surface/text tokens |
| Auto-wrap for horizontal stacks on narrow panes | `flex-wrap` default on `ui.Stack(direction="h")` |
| No overflow bleeding outside pane | `min-width: 0 + max-width: 100%` on every pane child |

**Supported semantic variants** (use these — they cascade to agency theme):

- `ui.Button(variant=...)` → `primary`, `secondary`, `danger`, `ghost`
- `ui.Pill(color=...)` / `ui.Badge(color=...)` → `primary`, `accent`, `success`, `warning`, `danger`, `info`, `neutral`
- `ui.Progress(color=...)` → `blue`, `green`, `red`, `yellow`, `purple`
- `ui.Text(variant=...)` → `heading`, `subheading`, `body`, `caption`, `code`, `label`
- `ui.Surface(tier=...)` → `0` app / `1` panel / `2` card / `3` raised

**If you truly need a dynamic colour** (chart series beyond the 8 preset colours, an SVG brand graphic, a deterministic avatar hash palette), use `ui.theme(ctx)` to read the current agency's tokens:

```python
from imperal_sdk import ui
theme = ui.theme(ctx)
primary_light = theme.colors.get("primary", {}).get("light") or "#2563eb"
```

But this is rare. 99 % of extension UI should just emit variants.

**ESLint on the Panel side** blocks hardcoded Tailwind colour scales in new Panel code. If your extension also ships React components rendered directly in the Panel (e.g. via `ext_register_components.json` — not the DUI JSON path), those components must pass Panel's ESLint wall.

**Agency-visible proof:** the Panel's Playwright visual regression suite captures 8 critical surfaces under a `test-federal` agency fixture (deep-forest primary, yellow accent, red-800 danger — deliberately distant from Imperal defaults). Any surface that hardcoded a colour produces a diff. Federal customers get a canary for every agency-theme change.

See [`docs/imperal-cloud/design-system.md`](../../docs/imperal-cloud/design-system.md) for the full decision tree, element-level tokens reference, escape hatches, and Tailwind remap complete mapping.

---

## What ChatExtension Handles For You

| Concern | Handled by |
|---------|-----------|
| Tool routing | LLM tool_use (automatic) |
| ICNLI integrity | Auto-injected rules |
| Error handling | try/except with honest reporting |
| History management | Built from ctx.history |
| Capability boundary | Injected from kernel |
| Response formatting | LLM formats structured data |
| Registry registration | ONE tool via Extension |
| `_handled` flag | `True` when any function was called; `False` for clarifying-question-only responses (not recorded as actions) |
| Chain mode | Forced function calling on first round (`tool_choice="any"`), transparent to extension code |
| KAV / confirmation | Kernel loads confirmation settings ALWAYS (skip only: system/skeleton/automation). Executor passes `ctx._confirmation_actions` dict. ChatExtension checks REAL `action_type` vs exact per-category settings. Hub intent is irrelevant. Automations always bypass. |
| Response enforcement | Emoji stripping, identity enforcement (no cross-extension redirects), language rule injection |
| Context window | Automatic trimming, history windowing, per-extension rounds (kernel-level) |
| Task cancellation | `TaskCancelled` exception on user cancel |
| ActionResult validation | SDK warns on missing `ActionResult`, blocks event publishing |
| Event publishing | `event=` on `@chat.function` -> kernel auto-publishes `{app_id}.{event}` on success |

### 19. Declarative UI — Panels (v1.5.0)

Extensions provide Panel sidebar UI using `@ext.panel` (recommended) or the legacy `get_panel_data` pattern:

```python
# Modern: @ext.panel decorator (recommended)
@ext.panel("sidebar", slot="left", title="My Panel", icon="Layout")
async def my_sidebar(ctx, **kwargs):
    return ui.Stack([...])
```

Legacy pattern (still supported):

```python
@chat.function("get_panel_data", action_type="read",
               description="Panel UI data for this extension")
async def fn_get_panel_data(ctx) -> ActionResult:
    # Fetch live data (NOT from skeleton cache)
    data = await ctx.store.list("items")
    return ActionResult.success(data={
        "left": ui.List(items=[...], searchable=True, page_size=20).to_dict(),
        "right": ui.Stack([ui.Stat(...)]).to_dict(),
        "tray_value": len(data),  # raw number for tray badge
    })
```

**Rules:**
- `get_panel_data` has NO params (no Pydantic model)
- Returns `left`, `right` (Declarative UI JSON), `tray_value` (number)
- Fetches live data from APIs, NOT from skeleton cache
- Skeleton is for AI context ONLY, never for UI delivery
- Panel calls this via `/v1/extensions/{app_id}/call` → Temporal DirectCallWorkflow

**Available components (53 in v1.5.0):** `ui.List(page_size=)`, `ui.ListItem(actions=, draggable=, droppable=, icon=)`, `ui.Input(on_submit=)`, `ui.Button`, `ui.Stat`, `ui.Card`, `ui.Badge`, `ui.Tabs`, `ui.Stack`, `ui.Grid`, `ui.Alert`, `ui.Progress`, `ui.Chart`, `ui.Text`, `ui.Avatar`, `ui.Icon`, `ui.DataTable`, `ui.Page`, `ui.Section`, `ui.Row`, `ui.Column`, `ui.Accordion`, `ui.Stats`, `ui.Timeline`, `ui.Tree`, `ui.KeyValue`, `ui.Header`, `ui.Image`, `ui.Code`, `ui.Markdown`, `ui.Empty`, `ui.Divider`, `ui.Form`, `ui.Select`, `ui.MultiSelect`, `ui.Toggle`, `ui.Slider`, `ui.DatePicker`, `ui.FileUpload`, `ui.TextArea`, `ui.Menu`, `ui.Dialog`, `ui.Tooltip`, `ui.Link`, `ui.Loading`, `ui.Error`. See [ui-components.md](ui-components.md) for full reference.

## Pricing Your Extension (Token Economy)

Every extension action consumes tokens from the user's plan balance. The total cost per action is:

```
price = base_price + platform_fee
```

### Base Price (set by the developer)

Extensions choose one of three pricing modes:

| Mode | Description | Example |
|------|-------------|---------|
| **free** | All functions cost 0 tokens | System extensions (billing, admin) |
| **category** (default) | Price determined by `action_type` | Most extensions |
| **per_function** | Each `@chat.function` declares its own price | Premium extensions with varying costs |

**Category defaults** (used when mode is `category`):

| `action_type` | Default Base Price |
|----------------|--------------------|
| `read` | 1 token |
| `write` | 5 tokens |
| `destructive` | 10 tokens |

### Platform Fee (set by the platform, based on LLM tier)

| LLM Tier | Platform Fee | Use Case |
|----------|--------------|----------|
| economy | 2 tokens | Haiku, fast routing |
| standard | 10 tokens | Sonnet, general use |
| premium | 45 tokens | Opus, deep analysis |
| BYOLLM | 0 tokens | User provides their own key |

### Checking Billing in Extension Code

```python
@chat.function("expensive_analysis", action_type="write", description="Run deep analysis")
async def fn_expensive_analysis(ctx, params: AnalysisParams):
    # Check balance before expensive operation
    balance = await ctx.billing.get_balance()
    if balance.alert_level == "critical":
        return ActionResult.error("Token balance critically low. Please upgrade your plan.")

    # Check specific limits
    limits = await ctx.billing.check_limits()
    if limits.any_exceeded:
        return ActionResult.error(f"Usage limit exceeded on plan '{limits.plan}'")

    # Proceed with the operation
    result = await run_analysis(ctx, params)
    return ActionResult.success(data=result, summary="Analysis complete")
```

### Notes

- The kernel's `BillingResolver` performs Redis-only price lookups (<1ms overhead per action).
- System extensions (like `billing` itself) set all actions to 0 tokens.
- Usage tracking is automatic -- the kernel calls `ctx.billing.track_usage()` after each tool execution. Extensions do not need to track usage manually.
- See [clients.md -- ctx.billing](clients.md#5-ctxbilling----billingclient) for the full BillingClient API.

### Developer Revenue (2026-04-15)

Third-party developers earn revenue from paid extension usage. The Developer Portal (`/ext/developer` in Panel) manages the full lifecycle:

1. **Register** as developer (Explorer tier is free, 1 app max)
2. **Create app** with Git URL, set pricing model (free / per_action / subscription)
3. **Deploy** from Git — the platform pulls your repo, validates `main.py`, registers tools
4. **Submit for review** — auto-checks + admin approval
5. **Earn revenue** — when users call your paid functions, the billing consumer calculates your share

**Revenue split** is tier-dependent: Explorer 70%, Indie 80%, Studio 85%, Partner up to 95%. Formula: `developer_share = action_cost * split_pct / 100`.

**Reserved app IDs** (cannot be used by third-party devs): `admin`, `billing`, `mail`, `notes`, `automations`, `web-tools`, `hello-world`, `sharelock-v2`, `developer`.

**Full documentation:** `docs/imperal-cloud/developer-portal.md`

---

## Reference Implementation

The Mail Client extension (`/opt/extensions/mail/`) is the canonical reference for this pattern:
- 1 entry tool: `tool_mail_client_chat`
- 30 `@chat.function` handlers (Mail Client v4.3.0, 19 files, 4472 LOC): status, connect, connect_microsoft, connect_yahoo, connect_imap, inbox, read_email, send, reply, forward, search, folder, get_thread, archive, delete, mark_read, mark_unread, star, move, purge, bulk_archive, bulk_delete, bulk_mark_read, bulk_mark_unread, switch_account, disconnect, contacts, add_contact, sync_contacts, delete_contact
- 2 `@ext.tool` skeleton tools: `skeleton_refresh_mail`, `skeleton_alert_mail`
- All `@chat.function` params use Pydantic `BaseModel` (v4.2+)
- connect() checks status first -- no repeated OAuth URLs
- All functions return `ActionResult` with structured data dicts

## V1 File Structure (mandatory for all extensions)

Every extension MUST follow this unified split pattern:

```
extension/
├── app.py              # ext, chat, HTTP helpers, system prompt, @ext.health_check
├── main.py             # entry point — sys.modules cleanup + imports
├── handlers.py         # @chat.function handlers (Pydantic params)
├── handlers_*.py       # split by domain if handlers.py > 300 lines
├── skeleton.py         # @ext.tool skeleton tools (optional)
```

**main.py template** (CRITICAL — prevents cross-extension module collision):

```python
"""Extension Name v1.0.0 · Description."""
from __future__ import annotations

import sys, os
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
for _m in [k for k in sys.modules if k in ("app", "handlers", "skeleton")]:
    del sys.modules[_m]

from app import ext, chat  # noqa: F401
import handlers  # noqa: F401
import skeleton  # noqa: F401
```

The `sys.modules` cleanup is mandatory because ExtensionLoader shares `sys.path` — without it, the second extension loaded gets the first extension's `app.py` module from Python's import cache.

**Code style** (enforced across ALL extensions):
- `"""Name · Purpose."""` — module docstring with middle dot
- `from __future__ import annotations` — every file
- `# ─── Section ────────────────────────────────────────────────────────── #` — 78-char dividers
- Pydantic `BaseModel` with docstring on every model
- `-> ActionResult` return type on every handler
- Aligned `Field()` values

**Reference implementations:**
- admin (41 fn, 8 files): `/opt/extensions/admin/`
- mail (30 fn, 19 files — Mail Client v4.3.0, 4472 LOC): `/opt/extensions/mail/`
- notes (16 fn, 5 files — Notes v2.4.0): `/opt/extensions/notes/`
- automations (6 fn, 4 files): `/opt/extensions/automations/`
- hello-world (2 fn, 1 file): `/opt/extensions/hello-world/`

## Sub-Packages & Imports

Extensions can organize code into sub-packages (directories with `__init__.py`). The ExtensionLoader adds the extension directory to `sys.path` automatically, so relative imports work:

```
/opt/extensions/mail/
├── main.py              # from providers import get_provider  ← WORKS
├── providers/
│   ├── __init__.py      # exports get_provider
│   ├── google.py
│   ├── microsoft.py
│   └── imap.py
```

```python
# main.py — sub-package imports work because ExtensionLoader
# adds /opt/extensions/mail/ to sys.path before loading
from providers import get_provider
from providers.helpers import encrypt_password
```

No need for relative imports (`.providers`) — absolute imports from the extension root work.

## Database Access (ctx.db)

`ctx.db` provides direct SQL database access for Tier 2 extensions. Available when `DB_URL` or `EXTENSION_DB_URL` env var is configured on the platform worker.

```python
from pydantic import BaseModel, Field

class SearchOrdersParams(BaseModel):
    query: str = Field(default="", description="Search query")

@chat.function("search_orders", description="Search orders", action_type="read")
async def search_orders(ctx, params: SearchOrdersParams):
    if ctx.db is None:
        return {"error": "Database access not configured"}
    rows = await ctx.db.raw("SELECT * FROM orders WHERE status = %s LIMIT 10", ("active",))
    return {"orders": rows}
```

See [SDK Clients — ctx.db](clients.md#4-ctxdb----dbclient) for full API.

---

See also: [Quickstart](quickstart.md) | [SDK Clients](clients.md) | [Skeleton](skeleton.md)
