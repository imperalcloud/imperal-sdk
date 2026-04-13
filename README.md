<div align="center">

# Imperal SDK

### Build AI agents. Ship to marketplace. Get paid.

**The SDK for the first AI Cloud OS.**

[![PyPI version](https://img.shields.io/pypi/v/imperal-sdk?color=blue&label=PyPI)](https://pypi.org/project/imperal-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/imperal-sdk)](https://pypi.org/project/imperal-sdk/)
[![Tests](https://img.shields.io/badge/tests-309%20passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[Getting Started](#-quickstart) | [Features](#-what-you-get) | [Docs](https://docs.imperal.io) | [Discord](https://discord.gg/imperal) | [Marketplace](https://imperal.io/marketplace)

</div>

---

## What is Imperal?

Imperal is an **AI Cloud Operating System** — a complete platform where developers build AI-powered extensions (agents, tools, workflows), users install and use them, and everyone benefits from a shared ecosystem.

Think **Shopify for AI agents**. You build it. Users install it. The platform handles auth, billing, LLM routing, real-time sync, and everything else.

**The SDK** is how you build for the platform. One `pip install`. Five minutes to your first working AI agent.

```bash
pip install imperal-sdk
```

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
| **10 SDK Clients** | `ctx.store`, `ctx.ai`, `ctx.billing`, `ctx.skeleton`, `ctx.notify`, `ctx.storage`, `ctx.http`, `ctx.config`, `ctx.extensions`, `ctx.time` |
| **Error Hierarchy** | `ImperalError` > `APIError` > `NotFoundError`, `RateLimitError` — catch what you need |
| **MockContext** | Drop-in test replacement with 10 mock clients. Test without a server. |
| **CLI Tools** | `imperal init`, `imperal validate`, `imperal dev` — scaffold, validate, develop |
| **Lifecycle Hooks** | `@ext.on_install`, `@ext.on_upgrade("0.9.0")`, `@ext.on_uninstall`, `@ext.health_check` |
| **Events System** | `@ext.on_event("deal.created")` — subscribe to typed platform events |
| **Webhooks** | `@ext.webhook("/stripe", secret_header="Stripe-Signature")` — external HTTP ingestion |
| **Inter-Extension API** | `@ext.expose("get_deal")` + `ctx.extensions.call("crm", "get_deal")` — typed cross-extension calls |
| **UI Contributions** | Panels, Widgets, Commands, Context Menus, Settings, Themes — declare UI from Python |
| **Validator** | 12 rules (V1-V12) catch issues before deployment. Claude-friendly fix reports. |
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

12 rules. Catches type issues, missing annotations, banned imports, missing events. Runs in CI, in CLI, and at kernel load time.

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

## Declarative UI (v1.4.0)

Build full Panel UI from Python — zero React, zero rebuilds. **53 components** across 7 modules.

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

**53 components:**
- **Layout (8):** Stack, Grid, Tabs, Page, Section, Row, Column, Accordion
- **Display (8):** Text, Header, Icon, Image, Code, Markdown, Divider, Empty
- **Interactive (7):** Button, Card, Menu, Dialog, Tooltip, Link, SlideOver
- **Input (11):** Input, TextArea, Toggle, Select, MultiSelect, Form, Slider, DatePicker, FileUpload, RichEditor, TagInput
- **Data (11):** List, ListItem, DataTable, DataColumn, Stat, Stats, Badge, Avatar, KeyValue, Timeline, Tree
- **Feedback (5):** Alert, Progress, Chart, Loading, Error
- **Actions (3):** Call, Navigate, Send

**Zero-rebuild panel discovery:** `@ext.panel()` auto-publishes to the config store. New extensions show panels instantly — no frontend changes.

**System features:** Pagination, drag-drop, hover actions, search, expandable cards, inline editing, collapsible sections — all kernel-enforced

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

- **Documentation:** [docs.imperal.io](https://docs.imperal.io)
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
