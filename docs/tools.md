# Tools -- Extension Business Logic

**SDK version:** imperal-sdk 1.5.7
**Last updated:** 2026-04-18
**Audience:** Extension developers building on Imperal Cloud

---

## Overview

Tools are the core primitive of an Imperal Cloud extension. A tool is a Python async function decorated with `@ext.tool()` that the AI assistant can invoke to perform real actions -- query databases, call APIs, generate reports, update state.

The platform's Tool Discovery Engine classifies each user message, selects the appropriate tool, and dispatches the call via `execute_sdk_tool` -- the ICNLI OS kernel's single execution entry point. Every tool invocation goes through this path. Authentication and scope-based authorization (RBAC) are enforced at the **API layer** (Auth Gateway) before requests reach the kernel. The kernel itself is a trusted execution environment -- it loads your extension, injects Context, captures metrics, and runs your function.

```
User: "Analyze case 42"
       |
       v
Auth Gateway (RBAC: user.scopes >= tool.scopes)
       |
       v
Tool Discovery Engine (classifies message)
       |
       v
Selects: analyze (activity_name is source of truth for dispatch)
       |
       v
resolve_kernel_context (parallel: identity + config + settings → KernelContext)
       |
       v
execute_sdk_tool (ICNLI OS kernel -- requires pre-resolved _kernel_ctx)
  1. _execute_extension: Enforces required_scopes vs kctx.scopes (RBAC)
  2. ContextFactory.create_from_kctx builds Context (no HTTP calls)
  3. Calls your function with ctx + message as kwarg
       |
       v
Your tool runs: async def analyze(ctx, message: str) -> str
       |
       v
Platform delivers result to user
```

> **Key point:** `execute_sdk_tool` is the only way extensions execute. It requires a pre-resolved `_kernel_ctx` (KernelContext) — identity, config, and settings are resolved ONCE per message by `resolve_kernel_context` activity, not inside execute_sdk_tool. The kernel enforces RBAC via `_execute_extension` (required_scopes vs kctx.scopes) before dispatching — two-layer defense with Auth Gateway at the API layer and kernel at the dispatch layer. Hub calls `_execute_extension` directly for routed dispatches (no re-resolution). For ABAC, extensions can perform additional checks in their tool code.

---

## `@chat.function` -- The Production Pattern

For production extensions with multiple capabilities, **always use `ChatExtension` with `@chat.function`** instead of multiple `@ext.tool` decorators. This registers ONE tool in the Registry (one embedding, correct routing) and lets the LLM route user intent internally.

### Decorator Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | `str` | Yes (first arg) | Function name used in tool schema |
| `description` | `str` | Yes | Describes what the function does (LLM reads this) |
| `action_type` | `str` | No | `"read"` (default), `"write"`, or `"destructive"`. Controls 2-Step Confirmation and KAV. |
| `event` | `str` | No | Event name to publish on success (auto-prefixed: `"created"` → `"notes.created"`). Write/destructive only. |
| `params` | `dict` | No | JSON Schema parameter definitions. Each key maps to a parameter name with `type`, `description`, optional `default`. |

### `action_type` Values

| Value | Meaning | Confirmation |
|-------|---------|-------------|
| `"read"` (default) | Listing, searching, reading data | Never triggers confirmation |
| `"write"` | Creating, updating, sending | Triggers when user has confirmation enabled |
| `"destructive"` | Deleting, revoking, purging | Always triggers when confirmation is enabled |

The `action_type` on the decorator is **authoritative** — it is the source of truth for KAV and 2-Step Confirmation. The Hub's intent classification is only a routing hint.

**2-Step Confirmation exact-category matching (2026-04-08):** The kernel loads confirmation settings at the start of EVERY message (skipped only for system tasks and skeleton tools). `ChatExtension` checks the REAL function `action_type` from `@chat.function` against the user's per-category settings (`{"destructive": True, "write": False}`). The Hub intent type is irrelevant — only the decorator's `action_type` matters. Automations (`_is_automation=True`) always bypass confirmation — there is no user to confirm.

```python
# Executor passes ctx._confirmation_actions = {"destructive": True, "write": False}
# ChatExtension: intercept call only if function's action_type matches enabled category
@chat.function("delete_note", action_type="destructive")  # intercepted if {"destructive": True}
@chat.function("create_note", action_type="write")        # not intercepted if {"write": False}
```

### `event` Publishing

Declare `event=` on write/destructive functions. The platform auto-publishes `{app_id}.{event}` (e.g., `event="created"` on the `notes` extension → `notes.created`) when `ActionResult.status == "success"`. Automation rules subscribe to these events.

```python
@chat.function("send_email", action_type="write", event="sent",
    description="Send an email", params={
    "to": {"type": "string", "description": "Recipient email"},
    "subject": {"type": "string", "description": "Subject line"},
    "body": {"type": "string", "description": "Email body"}})
async def fn_send_email(self, to: str, subject: str, body: str):
    result = await self._api.send(to=to, subject=subject, body=body)
    return ActionResult.success(
        data={"message_id": result["id"], "to": to},
        summary=f"Email sent to {to}"
    )
# On success → publishes event: {"event_type": "gmail.sent", "data": {"message_id": ..., "to": ...}}
```

### `ActionResult` Return Type (Mandatory)

Every `@chat.function` **MUST** return `ActionResult`. No other return type is accepted.

```python
from imperal_sdk.chat.action_result import ActionResult

# Success
return ActionResult.success(
    data={"note_id": doc.id, "title": title},   # dict — used in automation templates
    summary=f"Note created: {title}"              # one-line human-readable description
)

# Error
return ActionResult.error("Rate limited by provider", retryable=True)
return ActionResult.error("Account disconnected", retryable=False)
```

| Rule | Detail |
|------|--------|
| `data` dict | Accessible in automation templates via `{{steps.N.data.key}}` |
| `summary` | Shown in the action ledger and to the LLM for formatting |
| `retryable=True` | Transient errors (rate limit, timeout, network) |
| `retryable=False` | Permanent errors (auth, not found, invalid input) |
| Missing `ActionResult` | SDK logs a warning and blocks event publishing |

### `_handled` Flag

ChatExtension sets `_handled=True` only when at least one `@chat.function` was called. If the LLM responds with a clarifying question (no function called), `_handled=False` is returned — that request is not recorded as an action. This prevents clarifying questions from appearing as ledger entries.

### Narration guardrail (v1.5.24+)

Final narration — the prose ChatExtension returns to the user after all tool calls — is automatically bound to `_functions_called` via a system-prompt postamble. This is handled inside `handle_message` and `_build_factual_response`; **extension authors do not call anything to enable it, but must not bypass it either**.

What this means:
- If your `@chat.function` returns `status=error`, the narration will say the operation failed. The LLM cannot soften it to a success claim.
- If the LLM considered calling a function but didn't, it will NOT describe it as "done" in the final narration.
- The postamble is language-agnostic — users in any language get the same honesty guarantee.

If you need custom narration logic (very rare), build on top of `ChatExtension` rather than replacing its narration path. See Rule 21 in `extension-guidelines.md`.

Implementation: `imperal_sdk.chat.narration_guard` module; `STRICT_NARRATION_POSTAMBLE` + `augment_system_with_narration_rule(system, fc_list)` helpers.

### Full Example

```python
from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension, chat
from imperal_sdk.chat.action_result import ActionResult

ext = Extension("notes", version="1.0.0")

chat_ext = ChatExtension(
    ext=ext,
    tool_name="tool_notes_chat",
    description="Notes management — create, list, update, delete notes",
    system_prompt="You manage the user's notes. Call functions for all note operations.",
    model="claude-haiku-4-5-20251001",
)

@chat_ext.function("list_notes", action_type="read",
    description="List all notes", params={"folder": {"type": "string", "description": "Filter by folder", "default": None}})
async def fn_list_notes(self, folder=None):
    notes = await self.ctx.store.query("notes", where={"folder": folder} if folder else {})
    return ActionResult.success(
        data={"notes": [n.data for n in notes], "total": len(notes)},
        summary=f"{len(notes)} notes found"
    )

@chat_ext.function("create_note", action_type="write", event="created",
    description="Create a new note", params={
    "title": {"type": "string", "description": "Note title"},
    "content": {"type": "string", "description": "Note content"}})
async def fn_create_note(self, title: str, content: str):
    doc = await self.ctx.store.create("notes", {"title": title, "content": content})
    return ActionResult.success(
        data={"note_id": doc.id, "title": title},
        summary=f"Note created: {title}"
    )

@chat_ext.function("delete_note", action_type="destructive", event="deleted",
    description="Delete a note permanently", params={
    "note_id": {"type": "string", "description": "Note ID to delete"}})
async def fn_delete_note(self, note_id: str):
    await self.ctx.store.delete("notes", note_id)
    return ActionResult.success(data={"note_id": note_id}, summary=f"Note {note_id} deleted")
```

> **Skeleton tools remain `@ext.tool`** — they are called by the platform skeleton workflow, not by users. See the [Skeleton Reference](skeleton.md).

---

## `@ext.tool` -- Low-Level Tool Registration

`@ext.tool` is used for: (1) skeleton refresh/alert tools (platform-called, not user-facing), (2) simple single-function extensions where ChatExtension is overkill.

A tool is registered with the `@ext.tool()` decorator on an async function.

```python
from imperal_sdk import Extension, Context

ext = Extension("my-app")

@ext.tool("analyze", scopes=["cases:write"], description="Analyze a case")
async def analyze(ctx: Context, message: str) -> str:
    case = await ctx.store.get("cases", message)
    result = await ctx.ai.complete(f"Analyze: {case['title']}")
    return result.text
```

### Decorator Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tool_name` | `str` | *required* (first argument) | Unique tool name within the extension. Used by the assistant to invoke the tool. Maps to `activity_name` in the Registry, which is the source of truth for tool dispatch. |
| `scopes` | `list[str]` | `[]` | Required permission scopes. The platform enforces these before calling your tool. |
| `description` | `str` | `""` | Human-readable description. Sent to the LLM as part of the tool schema. Write clear, specific descriptions -- the LLM relies on them to decide when to use the tool. |

### Function Signature

The first parameter must always be `ctx: Context`. The user's message is passed as the `message: str` keyword argument. Additional parameters become the tool's input schema, automatically inferred from type hints.

```python
@ext.tool("search", description="Search documents by keyword")
async def search(ctx: Context, message: str, limit: int = 10) -> str:
    # message: the user's input, passed as a kwarg by the platform
    # limit: optional integer parameter with default 10
    docs = await ctx.store.query("documents", filter={"text": message}, limit=limit)
    return format_results(docs)
```

### Accessing History and Skeleton Data

Tools have instant access to pre-loaded conversation history and skeleton data via the Context object. These are loaded by the ContextFactory before your function runs -- no network calls required.

```python
@ext.tool("context_aware_search", description="Search with conversation context")
async def context_aware_search(ctx: Context, message: str) -> str:
    # Conversation history -- pre-loaded, read-only, instant
    recent_messages = ctx.history[-5:] if ctx.history else []
    context_summary = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages)

    # Skeleton data -- pre-loaded snapshot, read-only, instant
    active_cases = ctx.skeleton_data.get("active_cases", {})
    current_case = active_cases.get("latest", {}).get("title", "none")

    result = await ctx.ai.complete(
        f"User is working on case: {current_case}\n"
        f"Recent conversation:\n{context_summary}\n"
        f"New query: {message}"
    )
    return result.text
```

### ABAC Authorization in Tool Code

Beyond scope-based RBAC (enforced at the Auth Gateway before the request reaches the kernel), you can perform fine-grained attribute-based access control (ABAC) checks within your tool using `ctx.user.can()`:

```python
@ext.tool("view_case", scopes=["cases:read"], description="View a case by ID")
async def view_case(ctx: Context, message: str) -> str:
    case = await ctx.store.get("cases", message)

    # ABAC check: user must have access to this department
    if not ctx.user.can("cases:read", {"department": case.get("department")}):
        return "You do not have access to cases in this department."

    return f"**{case['title']}**\nStatus: {case['status']}\n\n{case['description']}"
```

### Supported Parameter Types

| Python Type | JSON Schema Type | Notes |
|-------------|-----------------|-------|
| `str` | `string` | Required unless default is provided |
| `int` | `integer` | |
| `float` | `number` | |
| `bool` | `boolean` | |
| `list[str]` | `array` of strings | |
| `dict` | `object` | |
| `Optional[str]` | `string` or `null` | Treated as optional |

Parameters with default values become optional in the generated schema. Parameters without defaults are required.

---

## Scopes

Scopes are permission strings that control who can invoke a tool. The Auth Gateway checks the user's granted scopes against the tool's required scopes at the API layer, **before** the request reaches the kernel and your function is called. The kernel enforces a second check at dispatch time (`tool.required_scopes ⊆ extension.declared_scopes`).

```python
@ext.tool("delete_case", scopes=["cases:delete"], description="Permanently delete a case")
async def delete_case(ctx: Context, case_id: str) -> str:
    await ctx.store.delete("cases", case_id)
    return f"Case {case_id} deleted."
```

### Two declaration sites (session 27+)

The kernel ExtensionLoader takes the **union** of extension-level capabilities and per-tool scopes as the extension's declared set:

```python
ext = Extension(
    "my-ext",
    version="1.0.0",
    capabilities=["cases:read", "cases:write"],  # extension-level (broad)
)

@ext.tool("close_case", scopes=["cases:write"], description="Close a case")
async def close_case(ctx, case_id: str): ...

@ext.tool("view_case", scopes=["cases:read"], description="View a case")
async def view_case(ctx, case_id: str): ...
```

If the extension declares **neither** `capabilities=[...]` nor any per-tool `scopes=`, the loader logs a `[SCOPES]` WARN and falls back to wildcard `["*"]` for legacy compat. Fix it.

### How scope enforcement works

1. The user sends a message that triggers the `delete_case` tool.
2. The platform checks `ctx.user.scopes` for `"cases:delete"`.
3. If the scope is present, the tool is called normally.
4. If the scope is missing, the platform returns an error to the user: *"You do not have permission to perform this action."* Your tool is never invoked.

### Scope naming conventions

```python
# Pattern: {resource}:{action} — colon is canonical
"cases:read"         # Read case data
"cases:write"        # Create or update cases
"cases:delete"       # Delete cases
"reports:export"     # Export reports
"settings:admin"     # Modify extension settings
```

Dot format (`cases.read`) is still accepted for backwards compat but new code should use colon. See [auth.md — Scopes & Permissions](auth.md#scopes--permissions) for the full list of common namespaces.

### Tools without scopes

If `scopes=[]` (the default), the tool has no per-tool scope requirement — it inherits from the extension's `capabilities=[...]`. For a fully unrestricted read-only helper, leave both empty (and the loader's wildcard fallback kicks in with a WARN; prefer declaring the minimum scope explicitly).

```python
@ext.tool("help", description="Show available commands")
async def help_tool(ctx: Context) -> str:
    return "Available commands: analyze, search, export..."
```

> **Session 27 note:** The auto-registered ChatExtension entry tool now uses `scopes=[]` (was `["*"]`). Declare scopes at `Extension(capabilities=[...])` or per-`@chat.function(scopes=[...])`.

---

## Returning Responses

**`@chat.function` tools MUST return `ActionResult`** — see the `@chat.function` section above.

**`@ext.tool` tools must return a `str`.** This string is delivered to the user as the assistant's response (or to the kernel for dispatch).

**Skeleton refresh tools** are an exception: they return `{"response": data_dict}` (a dict with a `"response"` key) so that the `execute_sdk_tool` kernel can process the data for skeleton storage. See the [Skeleton Reference](skeleton.md) for details.

```python
# Simple text
return "Case analysis complete. Risk score: 78/100."

# Markdown formatting
return (
    "## Case Summary\n\n"
    "- **Status:** Analysis complete\n"
    "- **Files:** 50\n"
    "- **Risk Score:** 78/100\n\n"
    "Ask me about the findings."
)

# Error response (still a string -- handle errors gracefully)
return "Could not retrieve case data. Please verify the case ID and try again."
```

### What NOT to return

| Return Value | Problem | Solution |
|--------------|---------|----------|
| `None` | Platform error | Always return a string |
| `dict` or `list` | Platform expects string (except skeleton refresh tools) | Serialize with `json.dumps()` or format as text. Skeleton refresh tools return `{"response": dict}`. |
| Empty string `""` | User sees nothing | Return a meaningful message |

---

## Calling Other Context Services

Tools have full access to all `Context` attributes. Common patterns:

### Store operations (persistent document storage)

The store backend is fully operational. Documents are persisted in the tenant's database with soft deletes and audit trail. No setup required -- collections are created on first write.

```python
@ext.tool("save_note", scopes=["notes:write"], description="Save a note to the user's notebook")
async def save_note(ctx: Context, text: str, priority: str = "medium") -> str:
    note = await ctx.store.create("notes", {"text": text, "priority": priority})
    return f"Note saved (id: {note})."
```

```python
@ext.tool("create_case", scopes=["cases:write"], description="Create a new investigation case")
async def create_case(ctx: Context, title: str, description: str) -> str:
    doc_id = await ctx.store.create("cases", {
        "title": title,
        "description": description,
        "status": "open",
        "created_by": ctx.user.id,
    })

    # Update skeleton so the assistant has immediate context
    await ctx.skeleton.update("active_cases", {
        "latest": {"id": doc_id, "title": title},
    })

    return f"Case created: {doc_id}"
```

### AI completions

```python
@ext.tool("summarize", description="Summarize a document")
async def summarize(ctx: Context, doc_id: str) -> str:
    doc = await ctx.store.get("documents", doc_id)
    result = await ctx.ai.complete(
        prompt=f"Summarize in 3 bullet points:\n\n{doc['content']}",
        max_tokens=512,
        temperature=0.3,
    )
    return result.text
```

### External API calls

```python
@ext.tool("enrich_indicator", description="Enrich a threat indicator via external API")
async def enrich_indicator(ctx: Context, indicator: str) -> str:
    resp = await ctx.http.get(
        f"https://api.threatintel.example.com/v1/indicators/{indicator}",
        headers={"X-API-Key": "YOUR_THREAT_INTEL_KEY"},
    )
    if resp.status != 200:
        return f"Could not enrich indicator: HTTP {resp.status}"

    data = resp.json
    return (
        f"**Indicator:** {indicator}\n"
        f"**Type:** {data.get('type', 'unknown')}\n"
        f"**Severity:** {data.get('severity', 'N/A')}\n"
        f"**First seen:** {data.get('first_seen', 'N/A')}"
    )
```

### Billing checks

```python
@ext.tool("deep_analysis", scopes=["analysis:run"], description="Run premium AI analysis")
async def deep_analysis(ctx: Context, case_id: str) -> str:
    within_limit = await ctx.billing.check_limit("ai_tokens")
    if not within_limit:
        return "AI token limit reached. Please upgrade your plan to continue."

    case = await ctx.store.get("cases", case_id)
    result = await ctx.ai.chat(
        messages=[
            {"role": "system", "content": "Perform deep forensic analysis."},
            {"role": "user", "content": case["description"]},
        ],
        max_tokens=4096,
    )
    return result.text
```

---

## Multi-Tool Extensions

An extension can register multiple tools. The Tool Discovery Engine selects the best match for each user message based on the tool descriptions.

```python
ext = Extension("case-manager")

@ext.tool("analyze_case", scopes=["cases:read"], description="Analyze a case and provide findings")
async def analyze_case(ctx: Context, case_id: str) -> str:
    case = await ctx.store.get("cases", case_id)
    result = await ctx.ai.complete(f"Analyze: {case['description']}")
    return result.text


@ext.tool("list_cases", scopes=["cases:read"], description="List all open cases")
async def list_cases(ctx: Context) -> str:
    cases = await ctx.store.query("cases", filter={"status": "open"}, limit=20)
    if not cases:
        return "No open cases."
    lines = [f"- [{c['_id']}] {c['title']} ({c['status']})" for c in cases]
    return "Open cases:\n" + "\n".join(lines)


@ext.tool("close_case", scopes=["cases:write"], description="Close a case by ID")
async def close_case(ctx: Context, case_id: str, resolution: str) -> str:
    case = await ctx.store.get("cases", case_id)
    case["status"] = "closed"
    case["resolution"] = resolution
    await ctx.store.create("cases", case)
    return f"Case {case_id} closed. Resolution: {resolution}"


@ext.tool("export_case", scopes=["cases:read", "reports:export"], description="Export a case as PDF")
async def export_case(ctx: Context, case_id: str) -> str:
    case = await ctx.store.get("cases", case_id)
    pdf = generate_case_pdf(case)
    url = await ctx.storage.upload(f"exports/{case_id}.pdf", pdf, "application/pdf")
    return f"Case exported: {url}"
```

### Routing examples

| User Message | Selected Tool | Why |
|-------------|---------------|-----|
| "Analyze case 42" | `analyze_case` | Matches "analyze" + "case" in description |
| "Show me all open cases" | `list_cases` | Matches "list" + "open cases" |
| "Close case 42, resolved as false positive" | `close_case` | Matches "close" + "case" |
| "Export case 42 as PDF" | `export_case` | Matches "export" + "PDF" |

### Tool description best practices

- **Be specific.** "Analyze a case and provide findings" is better than "Analyze something".
- **Include key verbs.** The assistant matches user intent to tool descriptions. Include the verbs users naturally use.
- **Avoid overlap.** If two tools have similar descriptions, the router may choose incorrectly. Make descriptions distinct.
- **Keep it short.** One sentence is ideal. Two sentences maximum.

---

## Error Handling

The platform wraps tool execution in a try/except. If your tool raises an unhandled exception, the platform catches it, logs the full traceback, and returns a generic error to the user.

### Best practice: handle errors explicitly

```python
@ext.tool("fetch_data", description="Fetch data from external source")
async def fetch_data(ctx: Context, source_id: str) -> str:
    try:
        resp = await ctx.http.get(f"https://api.example.com/sources/{source_id}")
        if resp.status == 404:
            return f"Source {source_id} not found."
        if resp.status != 200:
            return f"External API returned an error (HTTP {resp.status}). Please try again."
        return format_source_data(resp.json)

    except TimeoutError:
        return "The external service is not responding. Please try again in a moment."

    except Exception:
        return "An unexpected error occurred. Our team has been notified."
```

### Error response guidelines

| Situation | Response Pattern |
|-----------|-----------------|
| Resource not found | "Case 42 not found. Please verify the ID." |
| Permission denied (RBAC) | Handled by Auth Gateway (scope enforcement). No need to check in tool. For ABAC, implement in your tool code. |
| External API error | "The service is temporarily unavailable. Please try again." |
| Invalid input | "Invalid date format. Please use YYYY-MM-DD." |
| Quota exceeded | "Your plan limit has been reached. Please upgrade." |

---

## Timeouts

Tools have a default execution timeout of **60 seconds**. If your tool needs more time, configure it in the extension settings:

```python
ext = Extension("my-app", tool_timeout=120)  # 120 seconds for all tools
```

For long-running operations (report generation, large file processing), consider returning a status message and processing in the background via a signal or scheduled task:

```python
@ext.tool("generate_report", description="Generate a comprehensive report (may take a few minutes)")
async def generate_report(ctx: Context, case_id: str) -> str:
    # Start background processing
    await ctx.store.create("report_jobs", {
        "case_id": case_id,
        "status": "processing",
        "started_by": ctx.user.id,
    })
    return "Report generation started. I will notify you when it is ready."
```

---

## Statelessness

Tools must be stateless. Do not store data in module-level variables or class attributes between invocations.

```python
# WRONG -- module-level state does not persist across invocations
cache = {}

@ext.tool("lookup", description="Look up a record")
async def lookup(ctx: Context, record_id: str) -> str:
    cache[record_id] = "data"  # Lost between invocations
    ...


# CORRECT -- use ctx.store or ctx.skeleton for persistent state
@ext.tool("lookup", description="Look up a record")
async def lookup(ctx: Context, record_id: str) -> str:
    record = await ctx.store.get("records", record_id)  # Platform-managed persistence
    ...
```

---

## Complete Example: Threat Intelligence Extension

> This example follows the same architecture as the production [Sharelock](../sharelock.md) extension (forensic document analysis), which runs as an SDK extension at `/opt/extensions/sharelock-v2/main.py`. It demonstrates all major patterns: store CRUD, AI completions, skeleton updates, notifications, storage uploads, and scheduled tasks.

```python
from imperal_sdk import Extension, Context

ext = Extension("threat-intel")


@ext.tool("search_threats", description="Search the threat database by keyword or indicator")
async def search_threats(ctx: Context, query: str, limit: int = 10) -> str:
    threats = await ctx.store.query("threats", filter={"text": query}, limit=limit)
    if not threats:
        return f"No threats found matching '{query}'."
    lines = [f"- [{t['_id']}] {t['name']} (severity: {t['severity']})" for t in threats]
    return f"Found {len(threats)} threat(s):\n" + "\n".join(lines)


@ext.tool("get_threat", description="Get detailed information about a specific threat")
async def get_threat(ctx: Context, threat_id: str) -> str:
    threat = await ctx.store.get("threats", threat_id)
    return (
        f"## {threat['name']}\n\n"
        f"**Severity:** {threat['severity']}\n"
        f"**Type:** {threat['type']}\n"
        f"**First seen:** {threat['first_seen']}\n"
        f"**Indicators:** {', '.join(threat.get('indicators', []))}\n\n"
        f"{threat.get('description', 'No description available.')}"
    )


@ext.tool(
    "block_indicator",
    scopes=["threats:write"],
    description="Add an indicator of compromise to the blocklist",
)
async def block_indicator(ctx: Context, indicator: str, reason: str) -> str:
    await ctx.store.create("blocklist", {
        "indicator": indicator,
        "reason": reason,
        "blocked_by": ctx.user.id,
    })

    # Update skeleton for real-time dashboard
    blocklist = await ctx.store.query("blocklist")
    await ctx.skeleton.update("blocklist_stats", {
        "total": len(blocklist),
        "last_added": indicator,
    })

    return f"Indicator `{indicator}` added to blocklist. Reason: {reason}"


@ext.tool("generate_report", scopes=["reports:export"], description="Generate a threat report")
async def generate_report(ctx: Context, days: int = 7) -> str:
    threats = await ctx.store.query("threats", sort="-created_at", limit=50)
    recent = [t for t in threats if is_within_days(t["created_at"], days)]

    result = await ctx.ai.complete(
        prompt=(
            f"Generate a threat intelligence summary for the last {days} days. "
            f"Threats:\n{format_for_llm(recent)}"
        ),
        max_tokens=2048,
    )

    # Save report to storage
    url = await ctx.storage.upload(
        f"reports/threat-report-{days}d.md",
        result.text.encode(),
        "text/markdown",
    )

    return f"{result.text}\n\n---\nReport saved: {url}"


@ext.signal("on_new_threat")
async def on_new_threat(ctx: Context, threat: dict) -> None:
    """React to new threat ingestion."""
    await ctx.skeleton.update("active_threats", {
        "latest": threat["name"],
        "count": await ctx.store.count("threats"),
    })
    if threat.get("severity") in ("high", "critical"):
        await ctx.notify(
            title=f"New {threat['severity']} threat detected",
            body=f"{threat['name']}: {threat.get('description', '')[:200]}",
            priority="high",
        )


@ext.schedule("threat_digest", cron="0 8 * * 1")
async def weekly_digest(ctx: Context) -> None:
    """Weekly threat digest every Monday at 08:00 UTC."""
    threats = await ctx.store.query("threats", sort="-created_at", limit=20)
    if threats:
        result = await ctx.ai.complete(
            f"Summarize these threats for a weekly digest:\n{format_for_llm(threats)}"
        )
        await ctx.notify(
            title="Weekly Threat Digest",
            body=result.text,
        )
```

---

## Related Documentation

- [Context Object](context-object.md) -- Complete reference for the `Context` dataclass
- [Skeleton](skeleton.md) -- Background state management via `ctx.skeleton`
- [Concepts](concepts.md) -- Extension lifecycle, storage tiers, billing
- [API Reference](api-reference.md) -- Registry and Auth Gateway endpoints
