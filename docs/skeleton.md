# Skeleton -- Live Application Memory

**SDK version:** imperal-sdk 1.5.6
**Last updated:** 2026-04-17 (v1.5.6: FC.result event-publishing fix — `@chat.function(event="X")` now correctly fires sidebar `refresh="on_event:X"`; v1.5.5: `ui.Graph` Cytoscape; v1.5.4: `@ext.tray()` + `TrayResponse`; v1.5.0: billing_status skeleton section)
**Audience:** Extension developers building on Imperal Cloud

---

## Overview

The Skeleton is Imperal Cloud's persistent, auto-refreshing data layer for extensions. Think of it as application memory -- structured data that the platform keeps warm so your tools never need to make blocking API calls during user interactions.

Every extension defines zero or more **skeleton sections**. Each section is a named block of data (a Python dict) that either:

1. **Refreshes on a schedule** (TTL-based), or
2. **Updates on demand** when your tools, signals, or schedules write to it via `ctx.skeleton.update()`.

When a user sends a message, the platform loads all skeleton sections into the context *before* dispatching to your tool. Your tool reads skeleton data instantly -- zero latency, zero API calls.

```
User sends message
       |
       v
Platform loads skeleton from Redis
       |
       v
ctx.skeleton_data is pre-loaded (dict snapshot)
       |
       v
Your tool reads: data = ctx.skeleton_data.get("case_status", {})
       |
       v
Instant data -- no API call needed
```

### Reading vs. writing skeleton data

| Operation | API | Performance | Use case |
|-----------|-----|-------------|----------|
| **Read** (in tools) | `ctx.skeleton_data["section"]` | Instant (pre-loaded) | Access cached state during tool execution |
| **Write** | `await ctx.skeleton.update(section, data)` | Network call | Update state in signals/schedules/tools |
| **Read** (after write) | `await ctx.skeleton.get(section)` | Network call | Read latest value after a recent write |

> **Prefer `ctx.skeleton_data` for reading in tools.** It is pre-loaded by the ContextFactory before your function runs -- zero latency, zero network calls. Use `ctx.skeleton.get()` only when you need the absolute latest value after a write within the same execution.

> **Skeleton v2 (2026-04-04):** Skeleton is now tick-only. The skeleton signal has been removed from executor step 6. DB writes + SSE events handle real-time updates. The skeleton engine is a periodic background context aggregator on its tick interval only. The rule engine is a separate, independent background task.

> **Freshness validation (2026-04-06):** Every skeleton section now carries `_refreshed_at` (unix timestamp) and `_freshness` metadata (`refreshed_at` + `ttl_remaining`). The kernel scans sections on load: if TTL remaining < 10% of original OR age > 2x TTL, the context gets `_stale_sections` warnings. This tells the LLM to prefer function calls over stale skeleton cache. Extensions can check freshness via `ctx.skeleton_data["section"]["_freshness"]["ttl_remaining"]`.

---

## Writing Skeleton Data

### From a signal handler

The most common pattern: update skeleton data when an event occurs.

```python
from imperal_sdk import Extension, Context

ext = Extension("my-app")

@ext.signal("on_user_login")
async def on_login(ctx: Context, user: dict) -> None:
    cases = await ctx.store.query("cases", filter={"status": "open"}, limit=5)
    await ctx.skeleton.update("recent_cases", {
        "count": len(cases),
        "cases": [{"id": c["_id"], "title": c["title"]} for c in cases],
    })
```

### From a tool

Update skeleton after a state change so subsequent tool calls have fresh data.

```python
@ext.tool("close_case", scopes=["cases:write"], description="Close a case")
async def close_case(ctx: Context, case_id: str) -> str:
    case = await ctx.store.get("cases", case_id)
    case["status"] = "closed"
    await ctx.store.create("cases", case)

    # Update skeleton immediately
    open_cases = await ctx.store.query("cases", filter={"status": "open"}, limit=5)
    await ctx.skeleton.update("recent_cases", {
        "count": len(open_cases),
        "cases": [{"id": c["_id"], "title": c["title"]} for c in open_cases],
    })

    return f"Case {case_id} closed."
```

### From a scheduled task

Periodically refresh skeleton data in the background.

```python
@ext.schedule("refresh_dashboard", cron="*/5 * * * *")
async def refresh_dashboard(ctx: Context) -> None:
    """Refresh dashboard metrics every 5 minutes."""
    open_count = await ctx.store.count("cases", filter={"status": "open"})
    critical_count = await ctx.store.count("cases", filter={"priority": "critical"})

    await ctx.skeleton.update("dashboard", {
        "open_cases": open_count,
        "critical_cases": critical_count,
        "last_refreshed": datetime.now(timezone.utc).isoformat(),
    })
```

---

## Reading Skeleton Data

### In a tool (use ctx.skeleton_data -- instant, pre-loaded)

```python
@ext.tool("quick_status", description="Show a quick status summary")
async def quick_status(ctx: Context) -> str:
    # Use ctx.skeleton_data for reads in tools -- instant, no network call
    data = ctx.skeleton_data.get("recent_cases", {})
    if not data:
        return "No cached data available."

    count = data.get("count", 0)
    cases = data.get("cases", [])
    lines = [f"- {c['title']}" for c in cases]
    return f"You have {count} open case(s):\n" + "\n".join(lines)
```

### In a signal handler (use ctx.skeleton.get() if you need freshest value after a write)

```python
@ext.signal("on_new_case")
async def on_new_case(ctx: Context, case: dict) -> None:
    existing = await ctx.skeleton.get("recent_cases")
    cases = existing.get("cases", []) if existing else []
    cases.insert(0, {"id": case["_id"], "title": case["title"]})
    cases = cases[:5]  # Keep only 5 most recent

    await ctx.skeleton.update("recent_cases", {
        "count": len(cases),
        "cases": cases,
    })
```

---

## Skeleton Refresh Tools

When the platform calls a skeleton refresh (via the `refresh_activity` configured in the Registry), it invokes your tool through `execute_sdk_tool`. Skeleton refresh tools are an exception to the `_kernel_ctx` requirement — the SkeletonWorkflow calls execute_sdk_tool without `_kernel_ctx`, and the kernel builds a minimal fallback KernelContext from user_info. Skeleton refresh tools are registered with `@ext.tool()` (not `@ext.signal()`) and must return `{"response": data_dict}` instead of a plain string. This format allows the kernel to extract the data and store it in the skeleton.

> **V6 (Pydantic params) applies to `@chat.function` only.** The Pydantic `BaseModel` parameter convention (V6 in `imperal validate`) is for `@chat.function` handlers only. `@ext.tool`, `@ext.signal`, and `@ext.schedule` use plain `**kwargs` or named parameters as before — they are called by the platform with keyword arguments, not by an LLM tool-use schema.

```python
@ext.tool("refresh_case_status", description="Refresh case status for skeleton")
async def refresh_case_status(ctx: Context) -> dict:
    """Called by the skeleton engine on TTL expiry."""
    open_cases = await ctx.store.query("cases", filter={"status": "open"}, limit=10)
    return {"response": {
        "count": len(open_cases),
        "cases": [{"id": c["_id"], "title": c["title"]} for c in open_cases],
    }}
```

> **Return format:** Skeleton refresh tools return `{"response": dict}`, not a string. The `execute_sdk_tool` kernel reads the `"response"` key and writes the data to the skeleton section in Redis.

---

## Extension Activation and Suspension

When an extension is activated or suspended (via the Registry API), the platform sends an `update_config` signal to the running skeleton workflow **immediately**. This means:

- **Activation:** The skeleton starts refreshing the new extension's sections on the next tick. No restart needed.
- **Suspension:** The skeleton stops refreshing the suspended extension's sections immediately.

The `hub_mode` and `extensions_info` fields are injected into `skeleton_data._context` so that tools can read which extensions are active and whether the session is running in hub mode.

```python
@ext.tool("check_context", description="Check runtime context")
async def check_context(ctx: Context) -> str:
    context_info = ctx.skeleton_data.get("_context", {})
    hub_mode = context_info.get("hub_mode", False)
    extensions = context_info.get("extensions_info", [])
    return f"Hub mode: {hub_mode}, Active extensions: {len(extensions)}"
```

---

## Change Detection and Proactive Alerts

When you call `ctx.skeleton.update()`, the platform compares the new data with the previous value. If the data differs and `alert_on_change` is enabled for the section, the platform can send a proactive notification to the user.

### Configuring change detection

Change detection is configured in the Registry when you register skeleton sections:

```bash
curl -X PUT https://api.imperal.io/v1/apps/my-app/tools \
  -H "Content-Type: application/json" \
  -H "x-api-key: imp_reg_key_xxx" \
  -d '{
    "tools": [...],
    "skeleton_sections": [
        {
            "name": "case_status",
            "refresh_activity": "refresh_case_status",
            "alert_activity": "alert_case_status",
            "ttl": 60,
            "alert_on_change": true
        }
    ]
  }'
```

Or with the SDK manifest, skeleton sections referenced in your code are auto-detected by `imperal build` (which generates the manifest). Use `imperal validate` to check compliance before deploying.

### How comparison works

The platform performs a deep equality check on the dict:

```
Previous: {"status": "processing", "file_count": 30}
Current:  {"status": "completed", "file_count": 50}
Result:   CHANGED --> alert handler is called
```

### What triggers a change

- Any value in the dict changes (including nested values).
- A key is added or removed.
- List ordering changes.

### What does NOT trigger a change

- Writing identical data (same keys and values as before).
- Redis key expiry and re-creation with the same data.

### Tip: avoid noisy diffs

Do not include volatile fields like timestamps or counters that change on every update unless they are meaningful to the user.

```python
# Noisy -- triggers change every refresh because of timestamp
await ctx.skeleton.update("status", {
    "value": "processing",
    "checked_at": datetime.now().isoformat(),
})

# Clean -- only triggers when the actual status changes
await ctx.skeleton.update("status", {
    "value": "processing",
    "file_count": 50,
})
```

---

## TTL and Auto-Refresh

Each skeleton section has a configurable TTL (time-to-live) that determines how often the platform refreshes the data.

### How the refresh cycle works

The skeleton engine uses the section's configured TTL as the **tick interval** -- if you set `ttl: 60`, the section refreshes every 60 seconds. The Redis key is stored with a TTL of `section_ttl * 2` (twice the refresh interval) to ensure data survives one missed refresh cycle before expiring.

```
t=0s    Section created/updated via ctx.skeleton.update()
        Data stored in Redis with TTL = section_ttl * 2 (e.g., 120s for a 60s TTL)

t=60s   Platform calls refresh_activity (tick = TTL)
        New data compared with previous
        If changed: alert_activity is called

t=120s  Next refresh cycle
...
```

### TTL guidelines

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Rapidly changing (live metrics, active processing) | 15-30s | Near-real-time visibility |
| Moderate (case status, file lists) | 60-120s | Balance between freshness and load |
| Slow-changing (user profile, subscription) | 300-600s | Rarely changes mid-session |
| Near-static (app config, feature flags) | 900-1800s | Changes only on deploy |

### Redis storage

| Property | Value |
|----------|-------|
| Key format | `imperal:skeleton:{app_id}:{user_id}:{section_name}` |
| Serialization | JSON |
| Redis TTL | `section_ttl * 2` (auto-expires if refresh stops) |
| Max payload | 64 KB per section |

---

## Cold Start Handling

When a user sends their first message (or after a restart), skeleton data may not be populated yet. The platform does not block the tool call waiting for skeleton data -- your tool receives an empty dict from `ctx.skeleton_data` and must handle the empty case.

### Recommended pattern: fallback to direct query

```python
@ext.tool("case_info", description="Show case details")
async def case_info(ctx: Context, case_id: str) -> str:
    # Try skeleton first (pre-loaded, instant)
    data = ctx.skeleton_data.get("case_status", {})

    if not data:
        # Cold start -- skeleton not populated yet, query directly
        case = await ctx.store.get("cases", case_id)
        data = {
            "title": case["title"],
            "status": case["status"],
            "file_count": case.get("file_count", 0),
        }
        # Populate skeleton for next time
        await ctx.skeleton.update("case_status", data)

    return (
        f"**{data.get('title', 'Unknown')}**\n"
        f"Status: {data.get('status', 'unknown')}\n"
        f"Files: {data.get('file_count', 0)}"
    )
```

### Why not wait for skeleton?

Blocking the tool call until skeleton loads would add latency to the user's first message. The fallback pattern provides an instant response on cold start. Subsequent messages benefit from the pre-populated skeleton.

---

## Cross-Extension Context

When a user has multiple active extensions, the platform loads skeleton data from all extensions the user has access to. This means your tool can read data produced by other extensions the user has installed, and vice versa.

> **Per-user access filtering (2026-04-09):** The skeleton engine only refreshes extensions the user actually has access to (RBAC-filtered via Auth Gateway). Previously it refreshed all registered extensions for every user. This means `ctx.skeleton_data` contains only data from extensions in the user's enabled set -- no leaked cross-user data from extensions the user cannot access.

For example, if a user has both `case-manager` (with a `case_status` section) and `compliance-checker` (with a `compliance_score` section) active, a tool in either extension can read both sections.

### How it works

The platform's skeleton loader reads Redis keys across all `app_id` values for the user and merges them into a single context. No configuration is needed on your part -- the platform handles cross-extension loading automatically.

### Important: section name uniqueness

If two extensions define a section with the same name, each extension's data is stored separately (keyed by `app_id`). There is no conflict. However, when reading via `ctx.skeleton.get()`, your extension sees its own section by default. To read another extension's section, use the fully qualified form:

```python
# Read your own section
my_data = await ctx.skeleton.get("status")

# Read another extension's section (if the user has it active)
compliance = await ctx.skeleton.get("compliance-checker:compliance_score")
```

---

## Best Practices

### What to put in skeleton

Skeleton is for **extension application data only** — data your extension produces and the assistant needs for instant access. It is NOT a place for platform configuration, system settings, or feature flags that belong in the Unified Config Store.

- **Status flags:** `analysis_status`, `account_state`, `connection_status`
- **Counters:** `open_cases`, `pending_tasks`, `unread_messages`
- **Summaries:** Top-level case info, recent activity, key metrics
- **Extension caches:** Inbox cache, notes stats, recent document list

### What NOT to put in skeleton

- **Platform configuration:** Extension settings, AI model choices, feature flags, user preferences. Use the Unified Config Store (read via `ctx.config`).
- **Large blobs:** Full reports, raw file contents, base64-encoded images. Store a reference and fetch on demand.
- **Volatile timestamps:** Fields that change every refresh but carry no user-facing meaning.
- **Credentials:** API keys, passwords, tokens. Use secure environment variables.
- **Easily computed data:** If your tool can cheaply derive it from other skeleton data, do not store it separately.

### Section design guidelines

| Guideline | Rationale |
|-----------|-----------|
| One concern per section | Independent TTLs, independent change detection |
| Prefer flat structures | Change detection is more predictable |
| Keep payloads under 16 KB | 64 KB is the hard limit, but smaller is faster |
| Use stable keys | Do not dynamically generate top-level keys |
| Avoid arrays of unbounded length | Cap lists (e.g., `[:20]`) to prevent payload growth |

---

## Complete Example: Case Monitoring

```python
from imperal_sdk import Extension, Context
from datetime import datetime, timezone

ext = Extension("case-monitor")


# ---------------------------------------------------------------------------
# Signal: update skeleton when a case is created or modified
# ---------------------------------------------------------------------------

@ext.signal("on_case_update")
async def on_case_update(ctx: Context, case: dict) -> None:
    """React to case creation or modification."""
    open_cases = await ctx.store.query(
        "cases",
        filter={"status": "open"},
        sort="-updated_at",
        limit=10,
    )

    await ctx.skeleton.update("case_dashboard", {
        "open_count": len(open_cases),
        "cases": [
            {
                "id": c["_id"],
                "title": c["title"],
                "priority": c.get("priority", "normal"),
                "updated": c.get("updated_at"),
            }
            for c in open_cases
        ],
    })

    # Notify on critical cases
    if case.get("priority") == "critical":
        await ctx.notify(
            title="Critical Case Update",
            body=f"Case '{case['title']}' has been updated.",
            priority="high",
        )


# ---------------------------------------------------------------------------
# Schedule: periodic refresh
# ---------------------------------------------------------------------------

@ext.schedule("refresh_stats", cron="*/2 * * * *")
async def refresh_stats(ctx: Context) -> None:
    """Refresh aggregate statistics every 2 minutes."""
    total = await ctx.store.count("cases")
    open_count = await ctx.store.count("cases", filter={"status": "open"})
    closed_count = await ctx.store.count("cases", filter={"status": "closed"})

    await ctx.skeleton.update("case_stats", {
        "total": total,
        "open": open_count,
        "closed": closed_count,
        "close_rate": round(closed_count / total * 100, 1) if total > 0 else 0,
    })


# ---------------------------------------------------------------------------
# Tool: read skeleton data instantly
# ---------------------------------------------------------------------------

@ext.tool("dashboard", description="Show case dashboard summary")
async def dashboard(ctx: Context) -> str:
    # Use ctx.skeleton_data for instant reads in tools (pre-loaded, no network call)
    dash = ctx.skeleton_data.get("case_dashboard", {})
    stats = ctx.skeleton_data.get("case_stats", {})

    if not dash and not stats:
        return "No data available yet. Try again in a moment."

    lines = []

    if stats:
        lines.append(
            f"**Overview:** {stats.get('open', 0)} open / "
            f"{stats.get('closed', 0)} closed / "
            f"{stats.get('total', 0)} total "
            f"({stats.get('close_rate', 0)}% close rate)"
        )

    if dash and dash.get("cases"):
        lines.append("\n**Recent open cases:**")
        for c in dash["cases"][:5]:
            priority = f" [{c['priority'].upper()}]" if c.get("priority") == "critical" else ""
            lines.append(f"- {c['title']}{priority}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: case details with skeleton fallback
# ---------------------------------------------------------------------------

@ext.tool("case_detail", description="Show detailed info for a specific case")
async def case_detail(ctx: Context, case_id: str) -> str:
    # Try skeleton for quick summary (pre-loaded, instant)
    dash = ctx.skeleton_data.get("case_dashboard", {})
    cached = None
    if dash:
        for c in dash.get("cases", []):
            if c["id"] == case_id:
                cached = c
                break

    # Always fetch full data from store for accuracy
    case = await ctx.store.get("cases", case_id)

    return (
        f"## {case['title']}\n\n"
        f"**Status:** {case['status']}\n"
        f"**Priority:** {case.get('priority', 'normal')}\n"
        f"**Created:** {case.get('created_at', 'N/A')}\n"
        f"**Files:** {case.get('file_count', 0)}\n\n"
        f"{case.get('description', 'No description.')}"
    )
```

---

## Architecture

```
+-----------------------+       +----------------------------------+
|  Your Extension       |       |  Imperal Cloud Platform          |
|                       |       |                                  |
|  @ext.signal          |       |  Skeleton Engine                 |
|  @ext.schedule        |------>|  - Stores data in Redis          |
|  @ext.tool            |       |  - Runs change detection         |
|  ctx.skeleton.update()|       |  - Sends proactive alerts        |
|  ctx.skeleton.get()   |<------|  - Loads data for tool calls     |
|                       |       |                                  |
+-----------------------+       |         +--------+               |
                                |         | Redis  |               |
                                |         +--------+               |
                                +----------------------------------+
```

---

## Billing Status Skeleton Section

The `billing` system extension registers a skeleton section `billing_status` that provides real-time billing context to the assistant. This section is refreshed by the `refresh_billing_status` tool with a TTL of 60 seconds.

### Data returned

| Field | Type | Description |
|-------|------|-------------|
| `balance` | `int` | Tokens remaining in the current billing period |
| `plan` | `str` | Active plan name (micro, starter, pro, business, enterprise) |
| `cap` | `int` | Plan token cap |
| `alert_level` | `str` | `"ok"`, `"warning"` (< 20% remaining), or `"critical"` (< 5% remaining) |

### How it works

The billing extension (`/opt/extensions/billing/`) registers `refresh_billing_status` as a skeleton refresh tool. The skeleton engine calls it every 60 seconds per user. The assistant receives `billing_status` in `ctx.skeleton_data` automatically, enabling proactive warnings when the user's balance is low.

```python
# Reading billing status from skeleton (in any extension)
billing = ctx.skeleton_data.get("billing_status", {})
if billing.get("alert_level") == "critical":
    # User is nearly out of tokens -- inform them proactively
    ...
```

This is a platform-provided skeleton section. Extension developers do not need to register or refresh it -- it is always available for users with the billing extension active.

---

## Related Documentation

- [Context Object](context-object.md) -- `ctx.skeleton` methods and usage
- [Tools](tools.md) -- Tools that consume skeleton data
- [Concepts](concepts.md) -- Background state in the ICNLI OS model
- [API Reference](api-reference.md) -- Skeleton section registration via Registry
