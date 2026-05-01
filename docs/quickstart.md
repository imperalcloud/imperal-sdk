# Quickstart — Build Your First Extension

**Last updated:** 2026-05-01 (SDK v3.7.0 — anti-hallucination I-AH-1 guard active in chat handler)
**SDK version:** imperal-sdk 1.5.7 (PEP 563 validator V5/V6 fix — resolves forward references via `typing.get_type_hints`)
**PyPI:** [pypi.org/project/imperal-sdk](https://pypi.org/project/imperal-sdk/)
**GitHub:** [github.com/imperalcloud/imperal-sdk](https://github.com/imperalcloud/imperal-sdk)
**License:** AGPL-3.0-or-later
**Time to complete:** 5 minutes
**Prerequisites:** Python 3.11+, pip

---

## Overview

By the end of this guide you will have a working ChatExtension — the standard production extension pattern — installed on the ICNLI OS, validated, and tested locally.

When you deploy an extension, its code lives at `/opt/extensions/{app_id}/main.py`. The ICNLI OS kernel loads it automatically — no per-extension workers, no restarts, no manual configuration. The kernel injects ICNLI Integrity rules into every LLM call automatically. You write business logic; the platform handles everything else.

---

## 1. Install

```bash
pip install 'imperal-sdk>=3.0.0,<4.0.0'
imperal --version
# imperal-sdk 1.5.7
```

---

## 2. Init

```bash
imperal init my-notes --template chat
cd my-notes
```

Generated structure:

```
my-notes/
  main.py              # ChatExtension scaffold
  requirements.txt     # imperal-sdk pinned to 1.5.7
  tests/
    test_main.py       # MockContext tests
  .gitignore
```

The `chat` template generates a `ChatExtension` with one example `@chat.function`. This is the correct starting point for all production extensions.

---

## 3. Build

Open `main.py` and replace the scaffold with your extension logic. All `@chat.function` handlers must accept a Pydantic `BaseModel` as the second argument and return `ActionResult`.

```python
"""
my-notes — Imperal Cloud Extension
"""

from pydantic import BaseModel
from imperal_sdk import Extension, ChatExtension, ActionResult

# Declare scopes at the Extension level — this is the granted capability set
# the kernel enforces at dispatch time. Per-@chat.function(scopes=[...]) can
# tighten further. See extension-guidelines.md §8b.
ext = Extension(
    "my-notes",
    version="1.0.0",
    capabilities=["store:read", "store:write"],
)
chat = ChatExtension(ext, tool_name="notes", description="Manage user notes")


# --- List notes (read) ---

class ListNotesParams(BaseModel):
    folder: str = ""

@chat.function("list_notes", description="List saved notes", action_type="read")
async def fn_list_notes(ctx, params: ListNotesParams) -> ActionResult:
    filters = {"folder": params.folder} if params.folder else {}
    notes = await ctx.store.query("notes", filters=filters, limit=20)
    return ActionResult.success(
        data={"notes": notes, "total": len(notes)},
        summary=f"{len(notes)} note(s) found",
    )


# --- Create note (write) ---

class CreateNoteParams(BaseModel):
    title: str
    content: str = ""

@chat.function("create_note", description="Create a note", action_type="write", event="note.created")
async def fn_create_note(ctx, params: CreateNoteParams) -> ActionResult:
    doc = await ctx.store.create("notes", {
        "title": params.title,
        "content": params.content,
        "author": ctx.user.email,
    })
    return ActionResult.success(
        data={"note_id": doc.id, "title": params.title},
        summary=f"Created note '{params.title}'",
    )


# --- Delete note (destructive) ---

class DeleteNoteParams(BaseModel):
    note_id: str

@chat.function("delete_note", description="Delete a note", action_type="destructive", event="note.deleted")
async def fn_delete_note(ctx, params: DeleteNoteParams) -> ActionResult:
    await ctx.store.delete("notes", params.note_id)
    return ActionResult.success(
        data={"note_id": params.note_id},
        summary=f"Deleted note {params.note_id}",
    )
```

### Key patterns

| Pattern | What it does |
|---------|--------------|
| `ChatExtension(ext, ...)` | Registers ONE tool in the Registry (one embedding, correct routing) |
| `Pydantic BaseModel params` | Type-safe input — required by kernel v1.0.0 |
| `action_type="write"` | Triggers 2-Step Confirmation for write/destructive actions per user settings |
| `event="note.created"` | Publishes `my-notes.note.created` for Automation Rules |
| `ActionResult.success(data, summary)` | Universal return type — `data` is available as `{{steps.N.data.*}}` in automations |
| `ActionResult.error(msg, retryable)` | Honest error — kernel formats it for the user |

`@chat.function` handlers contain business logic only — no LLM calls, no routing. ChatExtension's internal LLM formats the response. ICNLI Integrity rules are auto-injected.

> **Narration honesty (v1.5.24+) is automatic** — final user-facing prose is bound to `_functions_called` via a language-agnostic system-prompt postamble. If your function returns `status=error`, the narration will honestly report that. See Rule 21 in [extension-guidelines.md](extension-guidelines.md).

---

## 4. Validate

```bash
imperal validate
```

Expected output:

```
── Imperal Extension Validator v1.0 ────────────────────────────────────

Extension: my-notes v1.0.0
Tools: 1, Functions: 3, Events: 2

✅ No issues found!
```

`imperal validate` checks that all `@chat.function` handlers use Pydantic params, return `ActionResult`, and have explicit `action_type`. Fix any errors before deploying.

Run a syntax check alongside it:

```bash
python3 -m py_compile main.py && imperal validate
```

---

## 5. Test

`tests/test_main.py` uses `MockContext` to test functions without a running platform:

```python
import pytest
from imperal_sdk.testing import MockContext
from main import fn_list_notes, fn_create_note, ListNotesParams, CreateNoteParams

@pytest.mark.asyncio
async def test_list_notes_empty():
    ctx = MockContext()
    result = await fn_list_notes(ctx, ListNotesParams())
    assert result.status == "success"
    assert result.data["total"] == 0

@pytest.mark.asyncio
async def test_create_note():
    ctx = MockContext(user_email="alice@example.com")
    params = CreateNoteParams(title="Hello", content="World")
    result = await fn_create_note(ctx, params)
    assert result.status == "success"
    assert result.data["title"] == "Hello"
    # Verify it was stored
    notes = await ctx.store.query("notes")
    assert len(notes) == 1
```

Run tests:

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

`MockContext` provides in-memory backends for `ctx.store`, `ctx.skeleton`, `ctx.notify`, and `ctx.user`. All `ctx.*` calls work identically to production — no mocking of internals needed.

---

## 6. Deploy

Place `main.py` at `/opt/extensions/my-notes/main.py` on the platform. The kernel's `ExtensionLoader` detects the file change by mtime and picks it up on the next request — no restarts, no downtime.

```bash
# On the platform host:
cp main.py /opt/extensions/my-notes/main.py
```

Verify it loaded:

```bash
imperal dev
# Extension: my-notes  v1.0.0
# Functions: list_notes, create_note, delete_note
```

> **Token billing:** Every extension action consumes tokens from the user's plan. By default, pricing is automatic based on `action_type` (read=1, write=5, destructive=10 tokens) plus a platform fee based on LLM tier. System extensions can set all actions to 0 tokens. See [Extension Guidelines -- Pricing Your Extension](extension-guidelines.md#pricing-your-extension-token-economy) for details on pricing modes and how to check billing in your code.

---

## 7. Declarative UI (v1.5.0)

Extensions can provide Panel UI using Python — zero React code:

```python
from imperal_sdk import ui

@chat.function("get_panel_data", action_type="read",
               description="Panel UI data for this extension")
async def fn_get_panel_data(ctx) -> ActionResult:
    items = await fetch_data(ctx)
    return ActionResult.success(data={
        "left": ui.Stack([
            ui.Button("+ New", variant="primary",
                      on_click=ui.Call("create_item")),
            ui.List(
                items=[
                    ui.ListItem(
                        id=i["id"],
                        title=i["name"],
                        subtitle=f"{i['count']} items",
                        icon="Package",
                        draggable=True,
                        on_click=ui.Navigate(f"/ext/myapp/{i['id']}"),
                        actions=[{"icon": "Trash2",
                                  "on_click": ui.Call("delete", item_id=i["id"]),
                                  "confirm": f"Delete {i['name']}?"}],
                    )
                    for i in items
                ],
                searchable=True,
                page_size=20,  # system pagination
            ),
        ]).to_dict(),
    })
```

**Components:** **55 components** across 7 domain modules. Import: `from imperal_sdk import ui`

**Actions:** `ui.Call(fn, **params)`, `ui.Navigate(path)`, `ui.Send(message)`

**ListItem features:** `draggable`, `droppable` + `on_drop`, `icon` (Lucide name), `actions` (hover buttons)

**System pagination:** `ui.List(page_size=20)` — auto-paginator, pinned at bottom

## Next Steps

| Topic | Document |
|-------|----------|
| **UI Components Reference** — ALL ui.* components, props, actions, patterns | [ui-components.md](ui-components.md) |
| **Extension Guidelines** — ChatExtension rules, scopes, skeleton tools | [extension-guidelines.md](extension-guidelines.md) |
| **SDK Clients** — ctx.store, ctx.ai, ctx.notify, ctx.storage, ctx.billing | [clients.md](clients.md) |
| **Skeleton** — background state, TTL, proactive alerts | [skeleton.md](skeleton.md) |
| **Auth SDK** — JWT verification, scopes, FastAPI middleware | [auth.md](auth.md) |
| **CLI Reference** — init, validate, dev, test, deploy | [cli.md](cli.md) |
