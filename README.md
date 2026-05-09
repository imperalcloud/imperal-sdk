<div align="center">

# Imperal SDK

### The SDK for Webbee 🐝 — agent of Imperal Cloud, the world's first AI Cloud OS.

**Build extensions in Python. Webbee picks them up. Users install them. You get paid.**

[![PyPI](https://img.shields.io/pypi/v/imperal-sdk?color=blue&label=PyPI)](https://pypi.org/project/imperal-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/imperal-sdk)](https://pypi.org/project/imperal-sdk/)
[![Tests](https://github.com/imperalcloud/imperal-sdk/actions/workflows/test.yml/badge.svg)](https://github.com/imperalcloud/imperal-sdk/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[Quickstart](#5-minute-quickstart) · [Documentation](https://docs.imperal.io) · [PyPI](https://pypi.org/project/imperal-sdk/) · [imperal.io](https://imperal.io)

</div>

---

## What is this?

**Imperal Cloud** is the world's first AI Cloud Operating System. **Webbee 🐝** is its agent — Web 3.0-native, cloud-modular, persistent across surfaces. First of its kind. There is no precedent.

Users live in natural language. Webbee runs the rest:

> *"send the Q3 report to Sarah"* — Webbee sends it.
>
> *"what was our biggest customer last month?"* — Webbee answers from your real data.
>
> *"book me a flight to Berlin Friday morning, cheapest under $400, aisle"* — Webbee books it across mail, calendar, payment, and travel APIs in one move.

It works because of three things: the **agent** (Webbee), the **kernel** (the OS layer that orchestrates intent, action, audit, and recovery), and **extensions** — Python packages that hand Webbee new superpowers.

This SDK is how you build extensions.

```bash
pip install imperal-sdk
```

---

## 5-minute quickstart

### Scaffold

```bash
mkdir hello-world && cd hello-world
touch main.py icon.svg
```

### Write a typed extension

```python
# main.py
from imperal_sdk import Extension, ChatExtension, ActionResult
from pydantic import BaseModel, Field

ext = Extension(
    "hello-world",
    version="1.0.0",
    display_name="Hello World",
    description="Demo extension that greets people by name with a friendly message.",
    icon="icon.svg",
    actions_explicit=True,
    capabilities=["hello-world:read"],
)

chat = ChatExtension(
    ext,
    tool_name="hello_world",
    description="Hello World — friendly greetings.",
)


class GreetParams(BaseModel):
    name: str = Field(..., description="Person to greet")


@chat.function(
    "greet",
    description="Greet someone by name with a friendly message.",
    action_type="read",
)
async def fn_greet(ctx, params: GreetParams) -> ActionResult:
    return ActionResult.success(
        data={"message": f"Hello, {params.name}! 🐝"},
        summary=f"Greeted {params.name}",
    )
```

That's the entire extension.

### Validate, run, ship

```bash
imperal validate           # 0 errors, 0 warnings — ready to publish
imperal dev                # local sandbox
imperal build              # generate imperal.json manifest
imperal deploy             # upload to panel.imperal.io/developer
```

Once accepted in the Developer Portal, your extension appears in the Marketplace. Users install it with one click and Webbee starts calling it on their behalf.

→ Full walkthrough: [docs.imperal.io/getting-started/quick-start](https://docs.imperal.io/en/getting-started/quick-start/)

---

## How extensions plug into Webbee

```
You: "send the Q3 report to Sarah"
       │
       ▼
  Imperal Panel (panel.imperal.io)
       │ HTTPS
       ▼
  Auth Gateway (auth.imperal.io)        — checks who you are
       │
       ▼
  Webbee 🐝                              — picks the extension(s) to call
       │ typed dispatch
       ▼
  mail extension → sends the email
       │
       ▼
  Webbee replies in chat: "Sent. ✅"
```

You write the extension. The platform handles auth, billing, LLM routing, multi-tenancy, audit, and recovery — for free.

---

## The Federal Extension Contract

Every extension that ships through the Developer Portal must satisfy 11 federal validators (V14–V22 + V24, all ERROR severity). They guarantee the kernel can dispatch your typed functions directly — no LLM in the middle paraphrasing arguments, no silent write failures.

| Validator | Requires |
|---|---|
| V14 | `Extension(description=...)` ≥ 40 chars, ≠ app_id |
| V15 | `Extension(display_name=...)` ≥ 3 chars, ≠ app_id |
| V16 | Per-function `description=...` ≥ 20 chars |
| V17 | Pydantic `BaseModel` params on every `@chat.function` |
| V18 | Typed return — `ActionResult` or Pydantic model |
| V19 | `actions_explicit=True` + `chain_callable=True` on writes/destructive |
| V20 | `effects=[...]` declared on writes/destructive |
| V21 | XML-validated `<svg>` icon, ≤ 100 KB, `viewBox` required, no embedded raster |
| V22 | Lifecycle hook signatures match SDK contract |
| V24 | Handlers MUST NOT read `ctx.skeleton.*` — skeleton is LLM context only; use `ctx.api` |

→ Full reference: [docs.imperal.io/sdk/validators-reference](https://docs.imperal.io/en/sdk/validators-reference/)

---

## What you get

| Capability | What it does |
|---|---|
| **Typed functions** | `@chat.function` with Pydantic params + `ActionResult` returns. Webbee dispatches typed calls — no LLM guessing, no silent write failures. |
| **Pydantic feedback loop** | If the LLM produces bad arguments, the SDK retries (max 2) with structured prose feedback. The next round usually fixes it. |
| **Declarative UI** | 55+ components — Stacks, Lists, Forms, Charts, DataTables. Build full Panel UI from Python. Zero React, zero rebuilds. |
| **11 SDK clients** | `ctx.store`, `ctx.ai`, `ctx.cache`, `ctx.http`, `ctx.config`, `ctx.notify`, `ctx.storage`, `ctx.extensions`, `ctx.skeleton` (LLM-only), `ctx.api`, `ctx.time` |
| **Lifecycle & events** | `@ext.on_install`, `@ext.on_event("mail.received")`, `@ext.schedule(cron=...)`, `@ext.webhook(...)` |
| **Inter-extension calls** | `@ext.expose()` + `ctx.extensions.call("crm", "get_deal", id="d1")` — typed cross-extension calls. |
| **MockContext** | Drop-in test replacement with 10 mock clients. Real assertions, no kernel required. |
| **CLI** | `imperal init`, `imperal validate`, `imperal dev`, `imperal build`, `imperal deploy` |
| **BYOLLM** | Users bring their own LLM keys. Anthropic, OpenAI, Google, Ollama — any OpenAI-compatible API. |
| **Federal-grade by default** | Tenant isolation, audit chokepoint, anti-hallucination guards, 117+ named runtime invariants — enforced by the kernel. |

---

## Project structure

```
my-extension/
  main.py            Extension + @chat.function definitions
  icon.svg           Required (V21 — XML <svg> root + viewBox, ≤ 100 KB)
  imperal.json       Manifest (auto-generated by `imperal build`)
  pyproject.toml     imperal-sdk >= 4.0.0
  tests/
    test_main.py     Tests using MockContext
```

---

## Testing without a server

```python
from imperal_sdk.testing import MockContext

async def test_greet():
    ctx = MockContext()
    result = await fn_greet(ctx, GreetParams(name="Alex"))
    assert result.status == "success"
    assert "Alex" in result.data["message"]
```

`MockContext` ships drop-in replacements for `ctx.store`, `ctx.http`, `ctx.ai`, `ctx.notify`, `ctx.cache`, `ctx.config`, `ctx.storage`, `ctx.skeleton`, `ctx.extensions`, and `ctx.time`. Real assertions, no kernel.

---

## Where to go next

- **Build something real** → [Your First Real Extension](https://docs.imperal.io/en/getting-started/your-first-extension/) — typed params, panels, audit, secrets.
- **Master the contract** → [Federal Extension Contract](https://docs.imperal.io/en/sdk/federal-contract/) — what every extension MUST satisfy.
- **Copy-paste recipes** → [Recipes](https://docs.imperal.io/en/recipes/) — sending mail, querying DBs, multi-step chains, BYOLLM.
- **Reference** → [SDK reference](https://docs.imperal.io/en/sdk/) — every decorator, every client, every component.

---

## Links

| | |
|---|---|
| **Website** | [imperal.io](https://imperal.io) |
| **Documentation** | [docs.imperal.io](https://docs.imperal.io) |
| **PyPI** | [pypi.org/project/imperal-sdk](https://pypi.org/project/imperal-sdk/) |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) |
| **Source** | [github.com/imperalcloud/imperal-sdk](https://github.com/imperalcloud/imperal-sdk) |
| **License** | [AGPL-3.0](LICENSE) |

---

<div align="center">

**Built by [Imperal, Inc.](https://imperal.io) · Webbee 🐝 is its agent.**

</div>
