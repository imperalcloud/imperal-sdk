# Testing Extensions — imperal-sdk 1.0.0

> Last updated: 2026-04-11

## Overview

`MockContext` provides a complete in-memory testing environment for extensions without a running
Imperal server. All clients are replaced with mock implementations that record calls, return
configurable responses, and raise predictable errors.

---

## MockContext

```python
from imperal_sdk.testing import MockContext

ctx = MockContext(
    user_id="test_user",
    role="admin",
    config={"api_url": "https://api.example.com"},
)
```

**Constructor kwargs** (all optional):

| Kwarg | Default | Description |
|-------|---------|-------------|
| `user_id` | `"test_user"` | Injected into `ctx.user_id` |
| `role` | `"user"` | `"admin"` or `"user"` |
| `config` | `{}` | Merged into `ctx.config` |
| `language` | `"en"` | Kernel language for the session |
| `tenant_id` | `"default"` | Multi-tenant identifier |

---

## Mock Clients

### MockStore

In-memory document store. Supports `create`, `get`, `update`, `delete`, `list` with `where`
filtering. Returns `Document` / `Page[Document]` matching the real client contract.

```python
ctx.store.seed("contacts", {"id": "c1", "name": "Alice", "status": "active"})

docs = await ctx.store.list("contacts", where={"status": "active"})
assert docs.items[0].data["name"] == "Alice"
assert ctx.store.call_log == [("list", "contacts", {"where": {"status": "active"}})]
```

### MockAI

Returns pre-configured text responses matched by substring pattern.

```python
ctx.ai.set_response("summarize", "Here is your summary.")
ctx.ai.set_response("*", "Default fallback response.")   # catch-all

result = await ctx.ai.complete("Please summarize this text.")
assert result.text == "Here is your summary."
```

### MockBilling

Configurable token balance; tracks deductions and raises `InsufficientBalanceError` on overdraft.

```python
ctx.billing.set_balance(500)
await ctx.billing.charge(100, reason="test action")
assert ctx.billing.balance == 400
assert ctx.billing.charges == [{"amount": 100, "reason": "test action"}]
```

### MockSkeleton

Returns a configurable context dict; records all `get` and `set` calls.

```python
ctx.skeleton.set_data({"inbox_count": 3, "notes_count": 12})
data = await ctx.skeleton.get()
assert data["inbox_count"] == 3
```

### MockNotify

Captures all notifications sent during the test; never delivers to real channels. Both invocation styles — `await ctx.notify(...)` (preferred, matches `NotifyClient.__call__` used by every production extension) and `await ctx.notify.send(...)` (alias kept for historical test code) — write to the same `ctx.notify.sent` list. Prior SDK versions had `NotifyProtocol.send` only but `NotifyClient.__call__` only, so the documented test pattern crashed in production; fixed in **SDK 1.5.8 (session 30, 2026-04-18)**.

```python
# Preferred style (matches production extension code)
await ctx.notify("Hello", channel="email", subject="Hello", body="Test")
assert ctx.notify.sent[0]["channel"] == "email"

# Equivalent alias
await ctx.notify.send("Hello", channel="email", subject="Hello", body="Test")
assert ctx.notify.sent[-1]["channel"] == "email"
```

### MockStorage

In-memory blob store keyed by path; supports `upload`, `download`, `delete`, `exists`.

```python
ctx.storage.seed("reports/q1.pdf", b"PDF bytes")
data = await ctx.storage.download("reports/q1.pdf")
assert data == b"PDF bytes"
```

### MockHTTP

Returns pre-configured JSON responses matched by URL prefix; records all requests.

```python
ctx.http.add_response("https://crm.example.com/contacts", {"id": "x1", "name": "Bob"})
resp = await ctx.http.get("https://crm.example.com/contacts/x1")
assert resp.json()["name"] == "Bob"
assert ctx.http.requests[0].method == "GET"
```

### MockConfig

Returns a flat dict; useful for testing config-driven branching logic.

```python
ctx.config_client.set({"feature_flag_x": True, "max_results": 10})
val = await ctx.config_client.get("max_results")
assert val == 10
```

### MockExtensions

Simulates cross-extension calls via `ctx.extensions.call(ext_id, fn, params)`.

```python
ctx.extensions.set_response("notes", "create_note", {"id": "n1", "title": "Test"})
result = await ctx.extensions.call("notes", "create_note", {"title": "Test"})
assert result["id"] == "n1"
assert ctx.extensions.calls[0] == ("notes", "create_note", {"title": "Test"})
```

---

## Complete Example

```python
# tests/test_crm.py
import pytest
from pydantic import BaseModel
from imperal_sdk.testing import MockContext
from imperal_sdk import ActionResult
from my_crm_extension.main import create_contact, list_contacts


class CreateContactParams(BaseModel):
    name: str
    email: str
    status: str = "active"


@pytest.fixture
def ctx():
    mock = MockContext(user_id="imp_u_test123", role="user")
    mock.store.seed("contacts", {"id": "c0", "name": "Existing", "status": "active"})
    return mock


@pytest.mark.asyncio
async def test_create_contact_success(ctx):
    params = CreateContactParams(name="Alice", email="alice@example.com")
    result: ActionResult = await create_contact(ctx, params)

    assert result.status == "success"
    assert result.data["name"] == "Alice"
    assert result.summary == "Contact Alice created."
    assert ctx.store.call_log[-1][0] == "create"


@pytest.mark.asyncio
async def test_list_contacts_with_filter(ctx):
    result: ActionResult = await list_contacts(ctx, status="active")

    assert result.status == "success"
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["name"] == "Existing"


@pytest.mark.asyncio
async def test_create_contact_duplicate_email(ctx):
    ctx.store.seed("contacts", {"id": "c1", "email": "dup@example.com"})
    params = CreateContactParams(name="Bob", email="dup@example.com")
    result: ActionResult = await create_contact(ctx, params)

    assert result.status == "error"
    assert "already exists" in result.message
    assert result.retryable is False
```

---

## Running Tests

**Via Imperal CLI (recommended):**

```bash
imperal test                   # discover and run all tests/
imperal test tests/test_crm.py # single file
imperal test --coverage        # with HTML coverage report
```

The CLI sets `IMPERAL_TEST_MODE=1`, suppresses SSE/event publishing, and injects
`MockContext` automatically for extensions declared with `@ext.test_context`.

**Via pytest directly:**

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
pytest tests/ -v --tb=short -k "test_create"
```

`pytest.ini` (recommended):

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

**Coverage threshold** (enforced by `imperal test --ci`): 80% line coverage required.
