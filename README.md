<div align="center">

# Imperal SDK

### Build AI agents. Ship to marketplace. Get paid.

**The SDK for the first AI Cloud OS.**

[![PyPI version](https://img.shields.io/pypi/v/imperal-sdk?color=blue&label=PyPI)](https://pypi.org/project/imperal-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/imperal-sdk)](https://pypi.org/project/imperal-sdk/)
[![Tests](https://github.com/imperalcloud/imperal-sdk/actions/workflows/test.yml/badge.svg)](https://github.com/imperalcloud/imperal-sdk/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[Getting Started](#-quickstart) | [Features](#-what-you-get) | [Docs](https://docs.imperal.io) ([source](docs/)) | [OpenAPI](docs/openapi/) | [Discord](https://discord.gg/imperal) | [Marketplace](https://imperal.io/marketplace)

</div>

---

## What is Imperal?

Imperal is an **AI Cloud Operating System** — a complete platform where developers build AI-powered extensions (agents, tools, workflows), users install and use them, and everyone benefits from a shared ecosystem.

Think **Shopify for AI agents**. You build it. Users install it. The platform handles auth, billing, LLM routing, real-time sync, and everything else.

**The SDK** is how you build for the platform. One `pip install`. Five minutes to your first working AI agent.

```bash
pip install imperal-sdk
```

### What's New in v4.0.0 — Federal Extension Contract (BREAKING)

```bash
pip install 'imperal-sdk>=4.0.0'
```

v4.0.0 closes the chain-planner BYOLLM-router gap that allowed silent
write failures (extension says "deleted" but nothing was deleted because
the router LLM summarised instead of calling the typed function). The
federal contract guarantees every extension that passes V14-V24 works
with the kernel's typed-dispatch chain pipeline — no LLM guessing.

**New Extension contract surface:**

```python
from pydantic import BaseModel, Field
from imperal_sdk import Extension, ChatExtension, ActionResult

ext = Extension(
    "my-agent",
    version="1.0.0",
    display_name="My Agent",                            # V15 — human-readable, ≥3 chars
    description=(                                       # V14 — ≥40 chars, what it does
        "Demo agent that greets users and echoes "
        "messages back, demonstrating federal v4 contract."
    ),
    icon="icon.svg",                                    # V21 — required SVG, ≤100KB, viewBox
    actions_explicit=True,                              # V19 — federal default
    capabilities=["my-agent:read", "my-agent:write"],
)
```

**New per-function fields:**

```python
class GreetParams(BaseModel):                            # V17 — explicit Pydantic params
    name: str = Field(default="World", description="Name to greet")


@chat.function(
    "create_note",
    action_type="write",
    description="Create a note in the user's notebook with optional folder.",
    chain_callable=True,                                # V19 — kernel typed dispatch (default True for write/destructive)
    effects=["create:note"],                            # V20 — declared side-effect surface
)
async def fn_create_note(ctx, params: NoteParams) -> ActionResult:   # V18 — typed return
    ...
```

**Manifest schema v3** — every typed `@chat.function` is now emitted as
a tool with full `params_schema`, `return_schema`, `chain_callable`,
`effects`. The kernel reads this directly and dispatches typed calls
without delegating to the ChatExtension LLM router.

**Federal validators V14-V24 (all ERROR severity):**

| Rule | Enforces |
|---|---|
| V14 | Extension `description` ≥40 chars, ≠ app_id |
| V15 | Extension `display_name` ≥3 chars, ≠ app_id (verbatim) |
| V16 | Per-tool `description` ≥20 chars (synthetic skipped) |
| V17 | Explicit Pydantic `BaseModel` params on every `@chat.function` |
| V18 | Typed return annotation (`ActionResult` or Pydantic model) |
| V19 | `actions_explicit=True` + `chain_callable=True` on writes/destructive |
| V20 | `effects=[...]` declared on writes/destructive (WARN v4, ERROR v5) |
| V21 | Required SVG icon — XML-validated `<svg>` root + `viewBox`, ≤100KB, no embedded raster |
| V22 | Lifecycle hook signatures match SDK contract (closes `on_refresh()` TypeError class) |
| V24 | Handlers must NOT read `ctx.skeleton.*` (AST walk — skeleton is LLM context only, use `ctx.api`) |

**Removed (BREAKING):**

- `ChatExtension(model=...)` parameter (deprecated since 3.3.0). LLM
  resolution lives in kernel ctx-injection (`ctx._llm_configs`).

**Migration:** if you maintain an extension and your next publish via
the Dev Portal fails one of V14-V24, the report tells you exactly which
field to add. Existing deployed extensions keep working at runtime
(kernel reads new manifest fields gracefully when present).

See [`CHANGELOG.md`](CHANGELOG.md) for the full release notes and the
v3.7.0 anti-hallucination guards (`I-AH-1` `FABRICATED_ID_SHAPE`) +
prior v3.5.x federal audit closure (`audit-chokepoint`, `llm-config-cascade`)
+ v3.0.0 identity contract (`UserContext`, `ctx.user.imperal_id`).

---

## 5-Minute Quickstart

```bash
imperal init my-agent --template chat
cd my-agent
```

That generates a complete AI agent:

```python
from pydantic import BaseModel
from imperal_sdk import Extension, ChatExtension, ActionResult

ext = Extension("my-agent", version="1.0.0")
chat = ChatExtension(ext, tool_name="my_agent", description="My first AI agent")


class GreetParams(BaseModel):
    name: str = "World"


@chat.function("greet", description="Greet someone", action_type="read")
async def fn_greet(ctx, params: GreetParams) -> ActionResult:
    """Say hello to someone."""
    return ActionResult.success(
        data={"message": f"Hello, {params.name}!"},
        summary=f"Greeted {params.name}",
    )
```

Validate it:

```bash
imperal validate
# Extension: my-agent v1.0.0
# Tools: 1, Functions: 1, Events: 0
# 0 errors, 0 warnings
```

Test it:

```python
from imperal_sdk.testing import MockContext

async def test_greet():
    ctx = MockContext(role="user")
    result = await fn_greet(ctx, GreetParams(name="World"))
    assert result.status == "success"
    assert result.data["message"] == "Hello, World!"
```

---

## What You Get

### For Extension Developers

| Feature | Description |
|---------|-------------|
| **Typed Everything** | Generic `ActionResult[T]`, `Page[T]`, typed Protocols, Pydantic params — full IDE autocomplete |
| **Machine-Validated Contracts** | JSON Schema for `imperal.json` (v1.5.9), `ActionResult` + `Event` payloads (v1.5.10), OpenAPI 3.x for Auth Gateway / Registry / Sharelock Cases (v1.5.11). See [`docs/openapi/`](docs/openapi/). |
| **11 SDK Clients** | `ctx.store`, `ctx.ai`, `ctx.billing`, `ctx.skeleton` (LLM-only, read-only), `ctx.cache` (Pydantic-typed, TTL 5-300s), `ctx.notify`, `ctx.storage`, `ctx.http`, `ctx.config`, `ctx.extensions`, `ctx.time` |
| **Error Hierarchy** | `ImperalError` > `APIError` > `NotFoundError`, `RateLimitError` — catch what you need |
| **MockContext** | Drop-in test replacement with 10 mock clients. Test without a server. |
| **CLI Tools** | `imperal init`, `imperal validate`, `imperal dev` — scaffold, validate, develop |
| **Lifecycle Hooks** | `@ext.on_install`, `@ext.on_upgrade("0.9.0")`, `@ext.on_uninstall`, `@ext.health_check` |
| **Events System** | `@ext.on_event("deal.created")` — subscribe to typed platform events |
| **Webhooks** | `@ext.webhook("/stripe", secret_header="Stripe-Signature")` — external HTTP ingestion |
| **Inter-Extension API** | `@ext.expose("get_deal")` + `ctx.extensions.call("crm", "get_deal")` — typed cross-extension calls |
| **UI Contributions** | Panels, Widgets, Commands, Context Menus, Settings, Themes — declare UI from Python |
| **Validator** | 19 rules (V1-V13 + v1.6.0 SKEL-GUARD-1/2/3, CACHE-MODEL-1, CACHE-TTL-1, MANIFEST-SKELETON-1, SDK-VERSION-1) catch issues before deployment. Claude-friendly fix reports. |
| **Pagination** | `Page[T]` with cursor, iteration, auto-pagination — built into every list operation |

### For the Platform

| Feature | What It Means |
|---------|---------------|
| **BYOLLM** | Users bring their own LLM keys. Anthropic, OpenAI, Google, Ollama, any OpenAI-compatible API. |
| **Multi-Model Routing** | Different models for routing (fast/cheap), execution (accurate), navigation (conversational) |
| **2-Step Confirmation** | Destructive actions require user approval. Kernel-enforced, not extension-optional. |
| **RBAC + Scopes** | Fine-grained permissions per user, per extension, per function |
| **Token Economy** | Built-in billing: token wallet, usage metering, subscription plans, marketplace payouts |
| **Automation Engine** | Event-driven rules with cron scheduling. Users create "if X then Y" without code. |
| **Self-Hosted** | Run on your servers. Your data never leaves. |

---

## Extension Architecture

```
@chat.function("create_deal", action_type="write", event="deal.created")
     |
     v
[ Kernel Pipeline ]
     |
     +-- Scope Check (RBAC)
     +-- 2-Step Confirmation (if destructive)
     +-- Execute Function
     +-- Truth Gate (ActionResult.status)
     +-- Event Publishing (automations)
     +-- Action Recording (audit trail)
     |
     v
ActionResult.success(data={"deal_id": "d1"}, summary="Deal created")
```

Every function call goes through the full kernel pipeline. Security, billing, events — all automatic. You just write the business logic.

---

## SDK Type System

```python
# Generic ActionResult — works with dict or Pydantic models
from pydantic import BaseModel

class Deal(BaseModel):
    id: str
    name: str
    value: float

result = ActionResult.success(data=Deal(id="d1", name="Acme", value=50000), summary="Created")
result.to_dict()  # {"status": "success", "data": {"id": "d1", "name": "Acme", "value": 50000}, ...}

# Cursor-based pagination
page = await ctx.store.query("deals", where={"status": "open"}, limit=20)
for deal in page:  # Page[Document] supports iteration
    print(deal.data["name"])
if page.has_more:
    next_page = await ctx.store.query("deals", cursor=page.cursor)

# Error hierarchy — catch what you need
from imperal_sdk.errors import NotFoundError, RateLimitError
try:
    deal = await ctx.store.get("deals", "nonexistent")
except NotFoundError as e:
    print(f"{e.resource} '{e.id}' not found")  # "deal 'nonexistent' not found"
```

---

## Multi-Model LLM

Extensions never import LLM libraries directly. The platform handles provider routing, failover, and per-user model preferences.

```python
# Extensions use ctx.ai — the platform routes to the right model
result = await ctx.ai.complete("Summarize this deal", model="")  # uses user's configured model

# Or use the LLM provider directly for advanced use cases
from imperal_sdk import get_llm_provider
provider = get_llm_provider()
resp = await provider.create_message(
    messages=[{"role": "user", "content": "Hello"}],
    purpose="execution",       # routing | execution | navigate
    user_id="imp_u_xxx",       # BYOLLM: uses the user's own API key
)
```

**Supported:** Anthropic (Claude), OpenAI (GPT), Google (Gemini), Ollama, vLLM, LM Studio, any OpenAI-compatible API.

---

## System Features

Extensions have access to platform-level capabilities through the SDK. No kernel SDK needed.

### Scheduled Tasks (Cron)

```python
@ext.schedule("daily_report", cron="0 9 * * *")
async def daily_report(ctx):
    """Runs every day at 9 AM UTC."""
    stats = await ctx.store.query("metrics", where={"date": "today"})
    await ctx.notify.push(title="Daily Report", body=f"{len(stats)} events today")
    return ActionResult.success(summary="Report sent")

@ext.schedule("hourly_sync", cron="0 * * * *")
async def hourly_sync(ctx):
    """Sync data every hour."""
    data = await ctx.http.get("https://api.example.com/data")
    await ctx.store.create("synced_data", data.json())
```

### Dynamic Scheduling (User-Created Intervals)

For user-driven schedules (e.g., monitors with custom intervals), use a **single cron + last_run_at check**:

```python
import time

@ext.schedule("monitor_runner", cron="0 * * * *")  # check every hour
async def monitor_runner(ctx):
    """Run monitors that are due based on user-configured intervals."""
    monitors = await ctx.store.query("monitors", where={"active": True})
    now = time.time()
    for m in monitors:
        interval_sec = m["interval_hours"] * 3600  # 1h, 6h, 12h, 24h
        if now - m.get("last_run_at", 0) >= interval_sec:
            await run_scan(ctx, m["id"])
            await ctx.store.update("monitors", m["id"], {"last_run_at": now})
```

This is the standard production pattern. No `ctx.scheduler` API needed — the cron trigger + per-record interval check handles any user-configured frequency.

**When to use which:**
| Pattern | Use Case |
|---------|----------|
| `@ext.schedule(cron=...)` | Fixed intervals: daily reports, hourly syncs, cleanup |
| Cron + `last_run_at` | Dynamic: user-created monitors, per-item schedules |
| `@ext.on_event(...)` | Reactive: trigger on events from other extensions |

### Push Notifications

```python
@chat.function("send_alert", description="Send push notification", action_type="write")
async def send_alert(ctx, params: AlertParams) -> ActionResult:
    await ctx.notify.push(
        title=params.title,
        body=params.message,
    )
    return ActionResult.success(summary=f"Alert sent: {params.title}")
```

### Event System (Cross-Extension)

```python
# Subscribe to events from other extensions
@ext.on_event("mail.received")
async def on_new_email(ctx, event):
    """Triggered when any email arrives."""
    subject = event.data.get("subject", "")
    if "urgent" in subject.lower():
        await ctx.notify.push(title="Urgent email!", body=subject)

# Publish events from your functions
@chat.function("create_deal", action_type="write", event="crm.deal_created")
async def create_deal(ctx, params: DealParams) -> ActionResult:
    deal = await ctx.store.create("deals", params.dict())
    return ActionResult.success(data=deal, summary="Deal created")
    # Platform auto-publishes crm.deal_created event — other extensions can subscribe
```

### System Tray (v1.5.4)

Inject icons, badges, and dropdown panels into the OS top bar:

```python
from imperal_sdk import ui

@ext.tray("unread", icon="Mail", tooltip="Unread messages")
async def tray_unread(ctx, **kwargs):
    count = await ctx.store.count("messages", where={"read": False})
    return ui.Stack([
        ui.Badge(str(count), color="red" if count > 0 else "gray"),
    ])

@ext.tray("alerts", icon="Bell", tooltip="Active alerts")
async def tray_alerts(ctx, **kwargs):
    alerts = await ctx.store.query("alerts", where={"active": True}, limit=5)
    return ui.Stack([
        ui.Badge(str(len(alerts)), color="red"),
        # Dropdown panel — shown when user clicks the tray icon
        ui.List(items=[
            ui.ListItem(id=a["id"], title=a["title"], subtitle=a["severity"])
            for a in alerts
        ]),
    ])
```

### Webhooks (External HTTP)

```python
@ext.webhook("/stripe", method="POST", secret_header="Stripe-Signature")
async def handle_stripe(ctx, headers, body, query_params):
    """Receive Stripe webhook at POST /v1/ext/{app_id}/webhook/stripe"""
    import json
    data = json.loads(body)
    if data["type"] == "payment_intent.succeeded":
        await ctx.store.create("payments", {"amount": data["data"]["object"]["amount"]})
    return {"received": True}
```

### Inter-Extension Calls (IPC)

```python
# Expose a method for other extensions to call
@ext.expose("get_deal", action_type="read")
async def api_get_deal(ctx, deal_id: str) -> ActionResult:
    deal = await ctx.store.get("deals", deal_id)
    return ActionResult.success(data=deal)

# Call another extension's exposed method
result = await ctx.extensions.call("crm", "get_deal", deal_id="d123")
```

---

## Skeleton (v1.6.0) — LLM-only, read-only

Skeleton is the AI's view of your extension's state. Only tools decorated with `@ext.skeleton` can read or produce it. Panels, chat functions, and regular tools that try `ctx.skeleton.get(...)` raise `SkeletonAccessForbidden`.

```python
from pydantic import BaseModel
from imperal_sdk import Extension, ActionResult

ext = Extension("mail", version="1.6.0")


class MailSection(BaseModel):
    unread: int
    total: int


@ext.skeleton("mail", ttl=525, alert=True,
              description="Mail unread/total counts")
async def skeleton_refresh_mail(ctx) -> ActionResult:
    # Skeleton tools RETURN new state — kernel persists via privileged activity.
    # No ctx.skeleton.update() in v1.6.0.
    unread, total = await _count_mail(ctx)
    return ActionResult.success(
        data=MailSection(unread=unread, total=total).model_dump(),
        summary=f"{unread} unread of {total}",
    )
```

For panel-side runtime data (API responses, paginated lists, throttled counters), use `ctx.cache`:

```python
from pydantic import BaseModel

class InboxPage(BaseModel):
    cursor: str
    items: list[dict]


@ext.cache_model("inbox_page")
class _InboxPageCacheModel(InboxPage):
    pass


@ext.panel("inbox", slot="center", title="Inbox")  # middle content area (master-detail)
async def panel_inbox(ctx, **kwargs):
    # TTL 5-300s, 64 KB value cap, per-extension namespace, Pydantic-validated.
    page = await ctx.cache.get_or_fetch(
        key="page:1",
        model=InboxPage,
        ttl_seconds=60,
        fetcher=lambda: _fetch_inbox(ctx, page=1),
    )
    return ui.List(items=[_row(m) for m in page.items])
```

---

## System Prompt Guidelines

**Important:** Extensions must NOT identify as a specific assistant. The platform injects OS identity automatically.

```python
# WRONG — deploy validation will fail (R10)
chat = ChatExtension(ext, tool_name="my_tool", description="...",
    system_prompt="You are a CRM assistant for Imperal Cloud.")

# CORRECT — describe what the module DOES, not what the AI IS
chat = ChatExtension(ext, tool_name="my_tool", description="...",
    system_prompt="CRM module — manage deals, contacts, and pipelines.")
```

The kernel injects the AI identity (`{assistant_name}`) and full platform capabilities into every LLM call. Your `system_prompt` should only contain module-specific rules and capabilities.

---

## Testing

Every extension is testable without a server:

```python
from imperal_sdk.testing import MockContext

async def test_full_workflow():
    ctx = MockContext(role="admin", config={"api_url": "https://example.com"})

    # MockStore — in-memory, full CRUD
    doc = await ctx.store.create("deals", {"name": "Big Deal", "value": 50000})
    assert doc.id is not None

    page = await ctx.store.query("deals", where={"name": "Big Deal"})
    assert len(page) == 1

    # MockAI — configurable responses
    ctx.ai.set_response("summarize", "This is a big deal worth $50K")
    result = await ctx.ai.complete("Summarize this deal")
    assert "50K" in result.text

    # MockHTTP — register mock endpoints
    ctx.http.mock_get("api.example.com", {"status": "ok"})
    resp = await ctx.http.get("https://api.example.com/health")
    assert resp.ok

    # MockNotify — verify notifications were sent
    await ctx.notify.send("Deal created!", channel="email")
    assert len(ctx.notify.sent) == 1
```

---

## Validation

```bash
$ imperal validate ./my-extension

── Imperal Extension Validator v1.0 ────────────────────

Extension: crm v1.0.0
Tools: 1, Functions: 12, Events: 5

RESULTS: 1 error, 2 warnings

  ERROR  [V5] @chat.function 'create_deal' must return ActionResult
         Fix: Add return type annotation: -> ActionResult

  WARN   [V10] @chat.function 'update_deal' (action_type="write") has no event=
         Fix: Add event='crm.update_deal' to the decorator

  WARN   [V9] No @ext.health_check registered
         Fix: Add @ext.health_check decorator to a health check function
```

19 rules (12 core V1-V13 + 7 v1.6.0: SKEL-GUARD-1/2/3, CACHE-MODEL-1, CACHE-TTL-1, MANIFEST-SKELETON-1, SDK-VERSION-1). Catches type issues, missing annotations, banned imports, missing events, skeleton-guard violations, cache-model misuse. Runs in CI, in CLI, and at kernel load time.

---

## Lifecycle & Events

```python
@ext.on_install
async def setup(ctx):
    """Called once when user installs your extension."""
    await ctx.store.create("settings", {"initialized": True})

@ext.on_upgrade("0.9.0")
async def migrate(ctx):
    """Called when upgrading from 0.9.x."""
    await ctx.store.query("deals")  # migrate data

@ext.health_check
async def health(ctx):
    """Called every 60s. Return health status."""
    return HealthStatus.ok({"connections": 5})

@ext.on_event("email.received")
async def on_email(ctx, event):
    """React to platform events from other extensions."""
    await ctx.notify.send(f"New email: {event.data['subject']}")

@ext.webhook("/stripe", method="POST", secret_header="Stripe-Signature")
async def handle_stripe(ctx, request):
    """Receive webhooks from external services."""
    data = request.json()
    return WebhookResponse.ok({"received": True})
```


---

## Declarative UI (v1.5.0)

Build full Panel UI from Python — zero React, zero rebuilds. **57 components** across 7 modules.

```python
from imperal_sdk import Extension, ui

ext = Extension("inventory", version="1.0.0")

@ext.panel("sidebar", slot="left", title="Inventory", icon="Package",
           default_width=300, refresh="on_event:item.created,item.deleted")
async def panel_sidebar(ctx, **kwargs):
    """Panel handler — returns UINode tree. Auto-discovered by the platform."""
    items = await ctx.store.query("items", limit=50)
    return ui.Stack([
        ui.Header("Inventory", level=3, subtitle=f"{len(items)} items"),
        ui.Button("+ New Item", variant="primary", on_click=ui.Call("create_item")),
        ui.List(
            items=[
                ui.ListItem(
                    id=i["id"], title=i["name"],
                    subtitle=f"Qty: {i['qty']}",
                    badge=ui.Badge("Low", color="red") if i["qty"] < 5 else None,
                    expandable=True,
                    expanded_content=[
                        ui.KeyValue(items=[
                            {"key": "SKU", "value": i["sku"]},
                            {"key": "Price", "value": f"${i['price']}"},
                        ], columns=2),
                        ui.Button("Delete", variant="danger",
                                  on_click=ui.Call("delete_item", item_id=i["id"])),
                    ],
                )
                for i in items
            ],
            searchable=True,
        ),
    ])
```

**55 components:**
- **Layout (8):** Stack, Grid, Tabs, Page, Section, Row, Column, Accordion
- **Display (9):** Text, Header, Icon, Image, Code, Markdown, Divider, Empty, Html
- **Interactive (7):** Button, Card, Menu, Dialog, Tooltip, Link, SlideOver
- **Input (11):** Input, TextArea, Toggle, Select, MultiSelect, Form, Slider, DatePicker, FileUpload, RichEditor, TagInput
- **Data (11):** List, ListItem, DataTable, DataColumn, Stat, Stats, Badge, Avatar, KeyValue, Timeline, Tree
- **Feedback (5):** Alert, Progress, Chart, Loading, Error
- **Actions (4):** Call, Navigate, Send, Open

**Zero-rebuild panel discovery:** `@ext.panel()` auto-publishes to the config store. New extensions show panels instantly — no frontend changes.

**v1.5.0 highlights:**
- `ui.Html(theme="light")` — white-bg email rendering with auto-resize iframe
- `ui.List(selectable=True, bulk_actions=[...])` — multi-select with checkbox hover, bulk action bar
- `ui.List(on_end_reached=action)` — infinite scroll with IntersectionObserver sentinel
- `ui.Stack(sticky=True)` — pin toolbars to top of scroll container
- System padding: horizontal Stacks get `px-3 py-1` by default

**System features:** Pagination, infinite scroll, multi-select, bulk actions, drag-drop, hover actions, search, expandable cards, inline editing, collapsible sections — all kernel-enforced

---

## Project Structure

```
my-extension/
  main.py              # Extension + ChatExtension + @chat.functions
  imperal.json         # Manifest (optional — auto-discovered from code)
  tests/
    test_main.py       # Tests using MockContext
  requirements.txt     # imperal-sdk>=1.0.0
```

---

## Links

- **Documentation:** [docs.imperal.io](https://docs.imperal.io) — source in [`docs/`](docs/)
- **OpenAPI Specs:** [`docs/openapi/`](docs/openapi/) — Auth Gateway, Registry, Sharelock Cases (229 endpoints)
- **Platform:** [imperal.io](https://imperal.io)
- **Discord:** [discord.gg/imperal](https://discord.gg/imperal)
- **PyPI:** [pypi.org/project/imperal-sdk](https://pypi.org/project/imperal-sdk/)
- **GitHub:** [github.com/imperalcloud](https://github.com/imperalcloud)
- **License:** [AGPL-3.0](LICENSE)

---

<div align="center">

**Built by [Imperal, Inc.](https://imperal.io)**

*The AI Cloud OS.*

</div>
