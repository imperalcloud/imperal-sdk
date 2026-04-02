# Imperal SDK

The official Python SDK for building extensions on [Imperal Cloud](https://imperal.io) -- the world's first AI Cloud OS powered by [ICNLI](https://icnli.org).

## Installation

```bash
pip install imperal-sdk
```

With FastAPI authentication middleware:

```bash
pip install imperal-sdk[fastapi]
```

## Quick Start

```python
from imperal_sdk import Extension

ext = Extension("my-extension", version="1.0.0")

@ext.tool("greet", scopes=["*"], description="Greet a user")
async def greet(ctx, name: str = "World") -> dict:
    return {"response": f"Hello, {name}! You are {ctx.user.email}."}
```

## What's Included

| Module | Access | Purpose |
|--------|--------|---------|
| **Extension** | `Extension()` | Define tools, signals, schedules |
| **Context** | `ctx` | Request context with user, history, clients |
| **Auth SDK** | `ImperalAuth` | JWT verification, scopes, FastAPI middleware |
| **AI** | `ctx.ai` | LLM completions (Claude, GPT) with metering |
| **Store** | `ctx.store` | Document CRUD (schemaless JSON) |
| **Storage** | `ctx.storage` | File upload/download |
| **Database** | `ctx.db` | SQL access (PostgreSQL) |
| **Billing** | `ctx.billing` | Usage limits and subscription info |
| **Notify** | `ctx.notify` | Push notifications |
| **HTTP** | `ctx.http` | Outbound HTTP with logging |
| **Skeleton** | `ctx.skeleton` | Background state with TTL and alerts |
| **CLI** | `imperal` | init, dev, test, deploy, logs |

## Auth SDK

Verify JWT tokens from Imperal Auth Gateway:

```python
from imperal_sdk.auth import ImperalAuth

auth = ImperalAuth()
user = auth.verify(token)
print(user.id, user.role, user.scopes)
```

Protect FastAPI endpoints:

```python
from fastapi import FastAPI, Depends
from imperal_sdk.auth.middleware import require_auth, require_scope

app = FastAPI()

@app.get("/protected")
async def protected(user=Depends(require_auth())):
    return {"user": user.id}

@app.get("/admin")
async def admin(user=Depends(require_scope("admin.users"))):
    return {"admin": user.email}
```

## Extension UI Standard

Every extension renders in a standardized 3-column layout:

```
Left Sidebar  |  Center Chat  |  Right Panel
(navigation)  |  (AI chat)    |  (context data)
```

## Documentation

Full documentation: [docs/imperal-cloud/sdk/](https://github.com/imperalcloud/imperal-sdk/tree/main/docs)

| Document | Description |
|----------|-------------|
| [Quickstart](https://icnli.org) | Build your first extension in 5 minutes |
| [Auth SDK](https://icnli.org) | JWT, scopes, FastAPI middleware |
| [Extension UI](https://icnli.org) | 3-column layout standard |
| [Clients Reference](https://icnli.org) | All ctx.* APIs |
| [CLI Reference](https://icnli.org) | Command-line tools |

## License

**AGPL-3.0-or-later**

Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors

See [LICENSE](LICENSE) for the full license text.

## Links

- [Imperal Cloud](https://imperal.io) -- AI Cloud OS
- [ICNLI Protocol](https://icnli.org) -- The open protocol behind Imperal
- [Author](https://www.linkedin.com/in/valentin-scerbacov/) -- Valentin Scerbacov
