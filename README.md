<div align="center">

# Imperal SDK

### Build extensions for Webbee 🐝 — the agent of Imperal Cloud, the world's first AI Cloud OS.

**Write a small Python function. Webbee calls it when a user asks for it — in their own words. Ship it to the Marketplace and get paid.**

[![PyPI](https://img.shields.io/pypi/v/imperal-sdk?color=blue&label=PyPI)](https://pypi.org/project/imperal-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/imperal-sdk)](https://pypi.org/project/imperal-sdk/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

[Documentation](https://docs.imperal.io) · [Quickstart](https://docs.imperal.io/en/getting-started/quick-start/) · [PyPI](https://pypi.org/project/imperal-sdk/) · [imperal.io](https://imperal.io)

</div>

---

## What this is

**Imperal Cloud** is the world's first AI Cloud OS — a cloud you connect the contexts of your life into (mail, money, projects, servers, notes, anything) and then run entirely in your own native language. **Webbee 🐝** is the AI agent that lives inside it and does the work for you, safely.

**The Imperal SDK is how you give Webbee a new skill.** You write a small, typed Python *extension*; Webbee picks it up and calls it whenever a user asks for what it does — in plain language. The platform handles the hard parts — authentication, billing, multi-tenancy, audit, recovery, LLM routing — so your code stays small.

```bash
pip install imperal-sdk
```

> Python 3.11+ · AGPL-3.0-or-later

## Why build here

- **Webbee calls your function directly.** Typed, structured calls — no LLM guessing your arguments, no silent write failures.
- **The platform does the plumbing.** Auth, per-user isolation, billing, audit, retries and recovery, multi-tenant safety — handled for you.
- **You get paid.** Publish to the Imperal Marketplace, price your extension, earn on every use.
- **Bring any LLM.** Users connect their own model keys — Anthropic, OpenAI, Google, Ollama, any OpenAI-compatible API.

## A 60-second extension

```python
from imperal_sdk import Extension, ChatExtension, ActionResult
from pydantic import BaseModel, Field

ext = Extension(
    "hello-world",
    version="1.0.0",
    display_name="Hello World",
    description="Greets people by name with a friendly message.",
    icon="icon.svg",
    actions_explicit=True,
)

chat = ChatExtension(ext, tool_name="hello_world", description="Friendly greetings.")


class GreetParams(BaseModel):
    name: str = Field(..., description="Person to greet")


@chat.function("greet", description="Greet someone by name.", action_type="read")
async def greet(ctx, params: GreetParams) -> ActionResult:
    return ActionResult.success(
        data={"message": f"Hello, {params.name}! 🐝"},
        summary=f"Greeted {params.name}",
    )
```

That's a real, working extension. When a user types *"say hi to Alex"*, Webbee calls `greet(name="Alex")`.

→ Full walkthrough, from zero to published: **[docs.imperal.io](https://docs.imperal.io/en/getting-started/quick-start/)**

## What you can build

- **Chat tools** — typed `@chat.function`s Webbee calls straight from natural language.
- **Panels** — UI surfaces rendered inside the Imperal Panel.
- **Skeletons** — live data feeds that keep Webbee aware of a user's state.
- **Scheduled jobs & webhooks** — act on a timer, or react to outside events.
- **Typed entities (SDL)** — return `sdl.Entity` objects and the platform reads their meaning (id, title, kind, …) directly instead of guessing field names. Live in production.

Every published extension passes the **federal contract** — the validators that let Webbee call your code safely. The SDK checks it locally before you ship.

## Test without a server

```python
from imperal_sdk.testing import MockContext

async def test_greet():
    ctx = MockContext()
    result = await greet(ctx, GreetParams(name="Alex"))
    assert result.status == "success"
```

## Documentation

The full API, the manifest schema, every validator, recipes, and the federal contract live at **[docs.imperal.io](https://docs.imperal.io)** — that's the source of truth; this README is just the doorway.

| | |
|---|---|
| Documentation | [docs.imperal.io](https://docs.imperal.io) |
| Quickstart | [docs.imperal.io/en/getting-started/quick-start](https://docs.imperal.io/en/getting-started/quick-start/) |
| PyPI | [pypi.org/project/imperal-sdk](https://pypi.org/project/imperal-sdk/) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| License | [AGPL-3.0-or-later](LICENSE) |

---

<div align="center">

**Built by [Imperal, Inc.](https://imperal.io) — Webbee 🐝 is its agent.**

</div>
