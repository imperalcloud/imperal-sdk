# Skeleton -- LLM-Only Application Memory (v1.6.0)

**SDK version:** imperal-sdk 1.6.0
**Last updated:** 2026-04-24 (v1.6.0 breaking release — skeleton is LLM-only, read-only from non-skeleton code; `ctx.cache` replaces skeleton for panel-side runtime state)
**Audience:** Extension developers building on Imperal Cloud

---

## Overview

The Skeleton is Imperal Cloud's persistent, auto-refreshing data layer for **the AI classifier / routing LLM**. It is the AI's view of your extension's state: small structured snapshots the platform keeps warm so the LLM can classify intent and route to the right extension without paying a cold-fetch tax on every user turn.

**Skeleton is LLM-only in v1.6.0.** Panels, `@chat.function` tools, webhooks, and regular `@ext.tool` handlers **cannot** read or write skeleton. They will get a `SkeletonAccessForbidden` exception the moment they touch `ctx.skeleton`.

For panel-side runtime data (pages of mail, API responses, throttled counters), use **[`ctx.cache`](context-object.md#ctxcache)** — Pydantic-typed, TTL 5-300s, 64 KB cap, per-extension namespace. That is the v1.6.0 replacement for "skeleton as a general-purpose cache."

### What the kernel guarantees

```
  AI routing turn
         |
         v
  [skeleton-refresh tool] --runs on TTL, returns new state--> kernel persists via
                                                              privileged activity
         |
         v
  Redis: imperal:skeleton:{app}:{user}:{section}
         |
         v
  Classifier envelope: "[SKELETON] mail.mail: unread=3, total=17 (cached ~17s ago)"
         |
         v
  Routing LLM picks target_apps based on fresh-vs-stale signal
```

### Who can touch skeleton

| Actor | Read `ctx.skeleton.get(...)` | Write skeleton |
|---|---|---|
| `@ext.skeleton` tool | Allowed (returns previous snapshot for diff) | Return new state — kernel persists |
| `@ext.panel`, `@chat.function`, `@ext.tool` | **Forbidden** — raises `SkeletonAccessForbidden` | **Forbidden** |
| Kernel (skeleton_save_section activity) | Allowed (sole writer) | Allowed (sole writer) |

### What changed from v1.5.x

- **`ctx.skeleton.update(section, data)` is gone.** `SkeletonProtocol` is read-only. Skeleton tools RETURN new state via `ActionResult.success(data=...)` and the kernel persists via `skeleton_save_section` activity (single writer, audit-logged).
- **`ctx.skeleton_data` attribute is gone.** Non-skeleton tools no longer receive a pre-loaded snapshot in their context. If you need prior state for a diff, call `await ctx.skeleton.get(section)` from inside your `@ext.skeleton` tool — it is legal in that context.
- **`ctx.skeleton` from non-skeleton code raises `SkeletonAccessForbidden`.** This is a `PermissionError` subclass — catch it explicitly or let it surface as a 403.
- **`@ext.tool("skeleton_refresh_<X>")` naming convention deprecated** in favour of the canonical `@ext.skeleton("section_name", ttl=..., alert=True)` decorator (v1.5.22+). The old naming convention still works but the validator flags it as `MANIFEST-SKELETON-1`.
- **HMAC call-token auth on `/v1/internal/skeleton`.** The kernel signs each call; Auth GW verifies with `IMPERAL_CALL_TOKEN_HMAC_SECRET` + Redis SETNX jti replay protection. The skeleton PUT endpoint is removed — only the kernel's privileged save path writes.

---

## Writing a skeleton tool

Use `@ext.skeleton(section_name, ttl=..., alert=True, description=...)`. The decorator:

1. Registers a tool named `skeleton_refresh_<section_name>` on the extension's skeleton plane.
2. Stashes metadata on the `ToolDef` so the portal replay hook and kernel auto-derive pick it up.
3. Marks the tool as a "skeleton tool type" — `ctx.skeleton` is unlocked inside it.

```python
from pydantic import BaseModel
from imperal_sdk import Extension, ActionResult

ext = Extension("mail", version="1.6.0")


class MailSection(BaseModel):
    unread: int
    total: int
    inbox: list[dict]


@ext.skeleton("mail", ttl=525, alert=True,
              description="Mail unread/total counts for classifier")
async def skeleton_refresh_mail(ctx) -> ActionResult:
    # Optional: diff against previous state.
    # This is legal inside an @ext.skeleton tool.
    prev = await ctx.skeleton.get("mail")

    # Fetch fresh state from the upstream provider.
    inbox = await _fetch_gmail_inbox(ctx)
    unread = sum(1 for m in inbox if "UNREAD" in m.get("labelIds", []))

    section = MailSection(unread=unread, total=len(inbox), inbox=inbox[:20])

    # RETURN the new state. The kernel's skeleton_save_section activity
    # persists it. Do NOT call ctx.skeleton.update(...) — the method
    # does not exist in v1.6.0.
    return ActionResult.success(
        data=section.model_dump(),
        summary=f"{unread} unread of {len(inbox)}",
    )
```

### `@ext.skeleton` decorator signature

```python
Extension.skeleton(
    section_name: str,          # "mail", "recent_cases", etc. Must be [a-zA-Z0-9_-]+
    *,
    ttl: int = 300,             # Seconds. Classifier envelope uses this for
                                # "cached ~Xs ago" hinting.
    alert: bool = False,        # If True, kernel emits skeleton_alert_<section>
                                # when the section crosses a threshold.
    description: str = "",      # Human-readable summary for docs + portal.
)
```

### Alert tools

If you pass `alert=True`, the kernel also expects a sibling tool named `skeleton_alert_<section>` that returns a truthy `ActionResult` when the section warrants pushing a user-facing notification. This keeps alerting logic next to the state that triggers it.

```python
@ext.skeleton("mail", ttl=525, alert=True)
async def skeleton_refresh_mail(ctx) -> ActionResult: ...

@ext.tool("skeleton_alert_mail", action_type="read",
          description="Alert condition for mail skeleton")
async def alert_mail(ctx) -> ActionResult:
    # Read from the classifier-visible snapshot via ctx.cache or by calling
    # skeleton_refresh_mail directly — NOT via ctx.skeleton.get() outside
    # an @ext.skeleton tool.
    ...
```

---

## Reading skeleton state

### From a skeleton tool — legal

Inside an `@ext.skeleton` function, `ctx.skeleton.get(section)` is allowed and returns the previous snapshot (or `None` on first run).

```python
@ext.skeleton("recent_cases", ttl=60)
async def skeleton_refresh_cases(ctx) -> ActionResult:
    prev = await ctx.skeleton.get("recent_cases") or {}
    current_ids = {c["id"] for c in prev.get("cases", [])}
    fresh = await ctx.store.query("cases", where={"status": "open"}, limit=5)
    # ... detect deltas, emit events, return fresh state ...
    return ActionResult.success(data=...)
```

### From a panel / chat function / regular tool — forbidden

```python
@ext.panel("inbox", slot="center", title="Inbox")  # middle content area (master-detail)
async def panel_inbox(ctx, **kwargs):
    # BAD — raises SkeletonAccessForbidden in v1.6.0.
    mail = await ctx.skeleton.get("mail")

    # GOOD — use ctx.cache or call an ExtensionsClient method on your own
    # extension that pulls the data from its authoritative source.
    ...
```

### From a `@chat.function` — forbidden

```python
@chat.function("what_is_unread", action_type="read")
async def fn_unread(ctx, params) -> ActionResult:
    # BAD — SkeletonAccessForbidden.
    mail = await ctx.skeleton.get("mail")
    # GOOD — either fetch via ctx.store / ctx.http / ctx.cache, or expose
    # a dedicated @ext.tool that runs in the same isolation bucket.
    ...
```

The classifier envelope already sees skeleton — the LLM does not need your function to re-expose it. Chat functions are for acting on user requests, not for leaking skeleton state back into the conversation (that is the classifier's job, not yours).

---

## The classifier envelope

Every classifier turn receives a structured `[SKELETON]` block derived from Redis. v1.6.0 adds a strict authority header + per-section freshness tag:

```
[SKELETON] -- AUTHORITATIVE for availability/presence/0-vs-nonzero,
           STALE for specific numbers/metrics (route via target_apps for fresh fetch).

- mail.mail (cached ~17s ago): unread=3, total=17
- analytics.visitors (cached ~2m05s ago): today=1143
- sharelock.cases (cached ~1h02m ago): open=14, closed=8
- (other sections ... freshness unknown)
```

Key contract (I-SKELETON-STALENESS-ENVELOPE):
- `(cached ~Xs ago)` tag is derived from `_refreshed_at` in the stored section.
- Header tokens `AUTHORITATIVE` + `STALE` are load-bearing — the routing LLM uses them to decide when to force a fresh fetch via a skeleton refresh.
- Dict sections are flattened to scalar key/value pairs (`_*` internal fields skipped).
- Non-dict sections render without a freshness tag.

---

## Freshness + staleness

Every skeleton section carries:
- `_refreshed_at` — unix timestamp of last successful refresh.
- `_ttl` — the `ttl` argument from `@ext.skeleton`.

The kernel's `skeleton_check_stale` activity compares `now - _refreshed_at` against the section's own `_ttl` (not the workflow-level app_id — I-SKEL-CHECK-STALE-PER-SECTION-APPID). When age > TTL, the workflow enqueues `skeleton_refresh_<section>` for that app+user.

This means a mail section with `ttl=525` and an analytics section with `ttl=60` are refreshed on **independent** cadences on the same user, with no cross-section over-fetching.

---

## Migration from v1.5.x

### Pattern 1 — tool that used `ctx.skeleton_data["X"]`

```python
# v1.5.x
@chat.function("summarise_inbox", action_type="read")
async def summarise(ctx, params) -> ActionResult:
    mail = ctx.skeleton_data.get("mail", {})
    return ActionResult.success(data=mail)

# v1.6.0 — skeleton is LLM-only; move to ctx.cache or a dedicated fetch.
from pydantic import BaseModel

class MailSnapshot(BaseModel):
    unread: int
    total: int

@ext.cache_model("mail_snapshot")
class _MailSnapshotCache(MailSnapshot):
    pass

@chat.function("summarise_inbox", action_type="read")
async def summarise(ctx, params) -> ActionResult:
    snap = await ctx.cache.get_or_fetch(
        key="latest",
        model=MailSnapshot,
        ttl_seconds=60,
        fetcher=lambda: _count_mail(ctx),
    )
    return ActionResult.success(data=snap.model_dump())
```

### Pattern 2 — tool that called `ctx.skeleton.update(...)`

```python
# v1.5.x
@ext.signal("on_case_closed")
async def on_close(ctx, case_id: str) -> None:
    await ctx.skeleton.update("recent_cases", {"count": 0, "cases": []})

# v1.6.0 — either emit a platform event and let your @ext.skeleton tool
# re-derive state next tick, OR promote the logic into an @ext.skeleton
# handler.
@ext.skeleton("recent_cases", ttl=60)
async def skeleton_refresh_cases(ctx) -> ActionResult:
    cases = await ctx.store.query("cases", where={"status": "open"}, limit=5)
    return ActionResult.success(
        data={"count": len(cases),
              "cases": [{"id": c["id"], "title": c["data"]["title"]} for c in cases]},
        summary=f"{len(cases)} open cases",
    )
```

### Pattern 3 — `@ext.tool("skeleton_refresh_X")` naming convention

```python
# v1.5.x — still works but triggers MANIFEST-SKELETON-1
@ext.tool("skeleton_refresh_mail", action_type="read", description="...")
async def refresh_mail(ctx) -> ActionResult: ...

# v1.6.0 — canonical form
@ext.skeleton("mail", ttl=525, alert=True, description="...")
async def skeleton_refresh_mail(ctx) -> ActionResult: ...
```

---

## Validator rules (v1.6.0 additions)

Run `imperal validate` or `python -m imperal_sdk.validator_v1_6_0` — the v1.6.0 ruleset adds:

| Rule | Meaning |
|---|---|
| **SKEL-GUARD-1** | Panel / chat function / regular tool reads `ctx.skeleton.get(...)` — will raise `SkeletonAccessForbidden` at runtime. |
| **SKEL-GUARD-2** | Code references removed `ctx.skeleton_data` attribute. |
| **SKEL-GUARD-3** | Code calls removed `ctx.skeleton.update(...)` method. |
| **CACHE-MODEL-1** | `ctx.cache.get(..., model=X)` where `X` is not registered via `@ext.cache_model`. |
| **CACHE-TTL-1** | `ctx.cache.set(ttl_seconds=N)` with `N` outside `[5, 300]`. |
| **MANIFEST-SKELETON-1** | `@ext.tool("skeleton_refresh_*")` used in place of `@ext.skeleton`. |
| **SDK-VERSION-1** | Extension uses a v1.6.0 feature (`ctx.cache`, `@ext.skeleton`, `SkeletonAccessForbidden`) with `imperal-sdk<1.6.0` pinned. |

---

## Invariants (kernel + SDK contract)

- **I-SKELETON-LLM-ONLY** — `ctx.skeleton` is callable only from an `@ext.skeleton` tool. All other contexts raise `SkeletonAccessForbidden`.
- **I-SKELETON-PROTOCOL-READ-ONLY** — `SkeletonProtocol` has no `update(...)` method. The kernel's `skeleton_save_section` activity is the sole writer.
- **I-NO-CTX-SKELETON-DATA** — `Context` has no `skeleton_data` attribute. Tools that need prior state must call `ctx.skeleton.get(section)` from inside an `@ext.skeleton` tool.
- **I-KERNEL-EMPTY-SKELETON-ARG** — Non-skeleton tool dispatch no longer carries a skeleton snapshot in its args. The kernel passes an empty sentinel.
- **I-SKEL-AUTO-DERIVE-1** — If Registry has no `skeleton_sections` row for an app, the kernel derives sections from any `skeleton_refresh_<X>` tool (via the `@ext.skeleton` metadata).
- **I-SKEL-SUMMARY-VALUES-1** — Classifier envelope renders dict sections as `key=value` scalar pairs, skipping `_*` fields.
- **I-SKEL-FRESHNESS-1** — Every section stores `_refreshed_at`; staleness is computed per section, not per workflow.
- **I-SKEL-PER-USER-1** — Redis keyspace is `imperal:skeleton:{app}:{user}:{section}`; no cross-user bleed.
- **I-SKEL-LIVE-INVALIDATE** — Extension disable emits `imperal:config:invalidate`, kernel purges `imperal:skeleton:{app}:{user}:*` scoped keys in <2s.
- **I-PURGE-SKELETON-SCOPE** — Skeleton purge routines reject `*?[]:` in identifiers, re-verify every SCAN key against the literal prefix before DEL, and are physically unable to touch `imperal:hub:chat:*` (federal-grade safety).
- **I-SKEL-CHECK-STALE-PER-SECTION-APPID** — Staleness check honours per-section `app_id`, not the workflow-level `app_id`. Prevents 10-15× over-fetch of unrelated sections.
- **I-SKELETON-STALENESS-ENVELOPE** — Classifier envelope prepends AUTHORITATIVE/STALE header and tags each dict section with `(cached ~Xs ago)`.
- **I-CALL-TOKEN-HMAC** — Auth GW `/v1/internal/skeleton` accepts only HMAC-SHA256-signed call tokens with a tool_type="skeleton" scope; jti replay protection via Redis SETNX.
