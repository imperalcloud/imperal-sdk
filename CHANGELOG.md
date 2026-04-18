# Changelog

All notable changes to `imperal-sdk` are documented here.

## 1.5.8 (2026-04-18)

### DUI additions (SDK-side, backward compatible)
- **`ui.Progress(color=...)`** — semantic colors for status bars. One of `blue` (default), `green`, `red`, `yellow`, `purple`. Empty string keeps the default. Use for budget bars, compliance progress, any state that benefits from at-a-glance semantics. Panel React component already supported `color` via `BAR_COLOR_CLASSES`; SDK now passes it through.
- **`ui.Chart(colors=..., y2_keys=...)`**. `colors: dict[str,str]` maps series key → hex/CSS color; SDK emits `series=[{key,label,color}]` that the Recharts renderer honors. `y2_keys: list[str]` adds a secondary right-side Y-axis and routes the named series to it — use for mixed-scale metrics (spend $ on left, clicks count on right). Pie charts unaffected.
- **`ui.TagInput(delimiters=..., validate=..., validate_message=...)`**. `delimiters: list[str]` — extra keys that create a tag in addition to Enter (e.g. `[" ", ",", ";"]`); paste is also split on these. `validate: str` — regex pattern; tags failing it are refused with a red caption for 1.8s. `validate_message: str` — human hint shown on rejection. Defaults preserve prior Enter-only behaviour.

### `NotifyProtocol` drift fix — CRITICAL for test code
- `NotifyClient` now implements BOTH `__call__(message, **kwargs)` (preferred — matches every production extension that uses `await ctx.notify("msg")`) AND `send(message, channel="in_app", **kwargs)` (alias forwarding to `__call__`). `NotifyProtocol` declares both. `MockNotify` supports both — each call path writes to `self.sent` with identical shape. Prior versions declared `send` only in the Protocol but implemented only `__call__` in the concrete client — `ctx.notify.send(...)` crashed at runtime in production despite being shown in the testing docs.

### Form child-input initial-value registration (Panel-side, ships with SDK compatibility)
- `DToggle` + `DSelect` Panel components now register their `initValue` with `FormContext` on mount if `form.values[param_name]` is still `undefined`. Before this, unchanged toggles / selects never appeared in the submit payload — the server saw "field missing" instead of their actual initial value. This fixes the long-standing "unticked toggles silently dropped" class of bugs. The SDK side (Python) is unchanged; the fix lives in the Panel DUI runtime. No extension code change needed.

### Accumulated from v1.5.7 (not in the tagged release)
- **`User.agency_id: str | None = None`** field (session 28, 2026-04-18) — added for agency multi-tenancy rollout. Extensions SHOULD forward `X-Imperal-Agency-ID: {ctx.user.agency_id or 'default'}` to downstream services (Cases API and similar).
- **`ChatExtension` scope tightening** (session 27) — auto-registered chat entry tool now uses `scopes=[]` instead of `scopes=["*"]`. Granted capability set = union(`Extension.capabilities`, per-tool `scopes=`). Loader falls back to `["*"]` with a WARN log when an extension declares neither — that's the migration signal to add explicit capabilities.
- **`enforce_os_identity()` fallback** (session 29) — when ALL sentences in the LLM output match an identity-leak pattern, the filter now returns a neutral acknowledgement (`"Чем могу помочь?"` for Cyrillic-containing input, `"How can I help?"` otherwise) instead of leaking the original text. Previously the all-stripped case fell through to the original string verbatim, defeating the filter.

### Platform-side notes (consumers of this SDK benefit automatically)
- **Kernel `@ext.schedule` dispatcher shipped** (platform session 30, 2026-04-18). The decorator has existed for a long time in this SDK, but the kernel silently ignored it until 2026-04-18. Extensions declaring `@ext.schedule("name", cron="...")` now actually fire on schedule — exactly once per (app, schedule, minute) across the 3-worker cluster via Redis-SETNX dedup. Runs under a synthetic `__system__` user (`scopes=["*"]`). Wall-clock cap `IMPERAL_EXT_SCHEDULE_TIMEOUT_S=600`. See platform docs `conventions.md` invariants SCHED-EXT-I1/I2.
- **Panel `/call` transport moved to Redis Streams** on platform for `__panel__*` calls (Phase 2 of Fast-RPC rollout). End-to-end latency dropped 388ms → 3ms. Extension code is untouched — same `direct_call_extension` activity runs handlers. See platform `fast-rpc.md`.
- **Webhook URL clarified** — `@ext.webhook(path)` registers at `POST /v1/ext/{app_id}/webhook/{path}` (not `/webhooks/{app_id}/{path}` as older guidelines said). Handler receives `(ctx, headers, body, query_params)`.

### Docs
- `docs/imperal-cloud/sdk/ui-components.md` — v1.5.8 changelog entry, Progress/Chart/TagInput prop tables updated with session 30 additions, examples rewritten for semantic colors + domain TagInput + dual Y-axis chart, Form section clarifies Context propagation through arbitrary nesting depth.
- `docs/imperal-cloud/sdk/context-object.md` — `ctx.notify` Methods table declares both `__call__` (preferred) and `send` (alias) with the drift history.
- `docs/imperal-cloud/sdk/testing.md` — MockNotify example shows both call-styles.
- `docs/imperal-cloud/sdk/extension-guidelines.md` — webhook URL fixed, `on_event` / `expose` / `tray` / `schedule` handler signatures expanded.
- `docs/imperal-cloud/sdk/concepts.md` — added availability note for `@ext.schedule` dispatcher.

## 1.5.7 (2026-04-17)

### CRITICAL BUGFIX
- **`imperal validate` V5/V6 false positives under `from __future__ import annotations` (PEP 563) are FIXED.** The validator previously read raw `__annotations__` / `inspect.signature` parameter annotations, which are STRINGS — not classes — when the source module opts into PEP 563. Every `@chat.function(ctx, params: MyPydanticModel)` in extensions that use the modern annotation style raised a V6 false positive (`params should be a Pydantic BaseModel subclass`), and V5 would similarly miss aliased `ActionResult` imports. **Fix:** validator now uses `typing.get_type_hints(func)` to resolve forward references via the function's `__globals__` before `isinstance` / `issubclass` checks, with graceful fallback to raw annotation substring match when resolution fails (e.g. circular imports). Shared helpers `_resolve_hints`, `_looks_like_action_result`, `_is_basemodel_subclass` ensure every future type-annotation check reuses the same resolution path. 9 regression tests cover `from __future__` + BaseModel + ActionResult + subclass + unresolvable hints.

## 1.5.6 (2026-04-17)

### CRITICAL BUGFIX
- **`@chat.function(event=...)` events now publish correctly**. Previously `ChatExtension._make_chat_result` constructed `FunctionCall` without passing the `result` field — so `FC.result` stayed `None`, `FC.to_dict()` omitted `result`, and the kernel's event-publishing check at `extension_runner.py` never fired. **Impact pre-fix**: sidebar `refresh="on_event:..."` never triggered (notes, sql-db, mail, billing, developer); automation rules filtering by `event_type` never stirred; extensions had no way to publish specific events (only generic `scope.action` fallbacks). **Fix**: one-line addition `result=fc_dict.get("result")` in the FC constructor. Companion fix in platform kernel (`extension_runner.py`): accept either `ActionResult` object (in-process) or dict (post-transport) via `ActionResult.from_dict()` hydration.

## 1.5.5 (2026-04-16)

### UI Components
- **`ui.Graph`** — new Cytoscape-backed interactive graph component. Accepts Cases API `/graph` payload directly (unwraps Cytoscape `{data: {...}}` format server-side). Layouts: `cose-bilkent` (default), `circle`, `grid`, `breadthfirst`, `concentric`. Props: `nodes`, `edges`, `layout`, `height`, `min_node_size`, `max_node_size`, `edge_label_visible`, `color_by`, `on_node_click`. Rendered by new Panel `DGraph` component (registered as `graph`). Designed for forensic entity/relationship visualisation (Sharelock v3 Intelligence Graph); performance target ~5000 nodes.

## 1.5.4 (2026-04-16)

### System Tray SDK
- **`@ext.tray()`** — new decorator for System Tray items in the OS top bar. Extensions can publish icon + badge + dropdown panel directly into the system tray (next to clock). Props: `tray_id`, `icon` (Lucide name), `tooltip`. Handler returns UINode (badge/panel). Registers `__tray__{id}` ToolDef for /call dispatch.
- **`TrayDef`** — new dataclass exported from SDK. Stored in `ext.tray_items` dict.

### OS Identity Enforcement
- **SDK Identity Guard** — `ChatExtension.__init__` now warns if `system_prompt` contains "You are [a/an/the]". Developers see `[SDK] ChatExtension 'tool': system_prompt contains 'You are ...'` warning in logs. Extensions must describe MODULE capabilities, not AI identity — the kernel injects `{assistant_name}` identity automatically.
- **`enforce_os_identity()` expanded** — `filters.py` now catches ~50 self-identification patterns (EN + RU) in addition to redirect patterns. Strips sentences like "I'm the Notes assistant" from LLM output.

### Deploy Pipeline
- **Registry auto-sync** — `deploy_app` now calls `_sync_tools_to_registry()` after successful validation. Loads extension, reads tools + skeleton, calls `PUT /v1/apps/{app_id}/tools`. Auto-creates app in Registry if missing (`_ensure_app_in_registry()`, 409=OK). Extensions appear in AI catalog immediately after deploy.
- **R10: `check_system_prompt_identity`** — new validation check. Scans `system_prompt.txt` AND inline `system_prompt=` keyword args in `main.py` via AST analysis. Catches "You are [a/an/the]" patterns. Critical severity — deploy fails.
- **R11: `check_registry_sync`** — new post-deploy verification. Confirms tools registered in Registry catalog. Falls back to direct API check if sync returned 0. Critical severity.
- **`validate_checks_deploy.py`** — new validation script (R10 + R11). Separate from R4-R9 to stay under 300L per file.

### Prompt System
- **`kernel_capability_boundary.txt`** — rewritten to use `{assistant_name}` placeholder. "You are {assistant_name} — the AI of Imperal Cloud AI OS."
- **`prompt.py` IDENTITY section** — replaces old CAPABILITY BOUNDARY. Injects assistant_name + full catalog capabilities into every LLM call.
- **`_build_all_capabilities()`** — new function in `system_handlers.py`. Builds compact summary of ALL extensions from catalog, injected into every extension LLM call.
- **`state.assistant_name`** — new field cached from Redis `imperal:platform:assistant`. Resolved by `navigator.py:_resolve_assistant_name()`.
- **All 13 extension system prompts fixed** — removed "You are X" identity from 8 `.txt` files + 5 inline `main.py`/`app.py` prompts (notes, mail, admin, developer, web-tools, automations, microsoft-ads, sql-db, video-creator, ocr-tool, hello-world, sharelock-v2, billing).
### UI Component Fixes (Panel)
- **`renderChildren()` normalized** — now accepts `UINode | UINode[] | undefined | null`, always normalizes to array. Fixes `e.map is not a function` crash when children is a single node. Affects **DSection**, **DSlideOver**, and any component using `renderChildren`.
- **DTagInput** — `values`, `suggestions` from Form context normalized to array before `.map()`. Single string values wrapped in `[string]`.
- **DMultiSelect** — `options`, `values` normalized to array. Same Form context fix.
- **DTimeline** — `items` normalized to array. `undefined` → `[]`.
- **Root cause:** SDK serializes props as JSON. Form context and skeleton can return single values instead of arrays (especially with one element). All array-consuming components now defensively normalize inputs.

### Scheduler Patterns (Documentation)
- **Static cron** — `@ext.schedule("name", cron="0 9 * * *")` runs at fixed intervals. Set at deploy time. Best for: daily reports, hourly syncs, periodic cleanup.
- **Dynamic scheduling pattern** — for user-created schedules (e.g. monitors with custom intervals), use a single hourly cron + `last_run_at` check:
  ```python
  @ext.schedule("scan_runner", cron="0 * * * *")
  async def scan_runner(ctx):
      monitors = await ctx.store.query("monitors", where={"active": True})
      now = time.time()
      for m in monitors:
          if now - m.get("last_run_at", 0) >= m["interval_hours"] * 3600:
              await run_scan(ctx, m["id"])
              await ctx.store.update("monitors", m["id"], {"last_run_at": now})
  ```
- **No `ctx.scheduler` needed** — the cron + last_run_at pattern is the standard production approach. Avoids kernel complexity while supporting arbitrary per-user intervals.


## 1.5.0 (2026-04-13)

### New UI Components & Enhancements
- **`ui.Html`** — raw HTML block with DOMPurify sanitization. `sandbox=True` renders in isolated iframe with ResizeObserver auto-height. Props: `content`, `sandbox`, `max_height`, `theme` (`"dark"` or `"light"` for email rendering with white bg).
- **`ui.Open`** — action type for opening URLs in new tab/popup. Used by Button `on_click` for downloads and OAuth.
- **`ui.Image(on_click=)`** — click handler for image gallery / lightbox patterns.
- **`ui.FileUpload`** — file upload with drag-and-drop, base64 encoding. Props: `accept`, `max_size_mb`, `max_total_mb`, `max_files`, `multiple`, `blocked_extensions`.
- **`ui.Button(icon=)`** — Lucide icon rendering in buttons via `(LucideIcons as any)[name]` lookup.
- **`ui.List()` multi-select** — `selectable=True` enables checkbox selection on hover. `bulk_actions=[{label, icon, action}]` renders sticky BulkActionBar. Selected IDs auto-injected as `message_ids` param.
- **`ui.List(on_end_reached=)`** — infinite scroll support via IntersectionObserver sentinel. `total_items` and `extra_info` for footer Paginator.
- **`ui.Stack(sticky=)`** — `sticky=True` pins element to top of scroll container. For toolbars and action bars.
- **`ui.Stack(className=)`** — custom CSS classes, overrides default system padding.
- **`ui.Stack` direction** — frontend accepts both `"h"` and `"horizontal"`.
- **System padding** — horizontal Stacks get default `px-3 py-2.5` (sticky) / `py-1.5` (non-sticky) for consistent alignment.

### Frontend DUI
- **DHtml.tsx** — DOMPurify sanitization + iframe sandbox + `theme="light"` with white bg for email + `overflow: auto` (was hidden) + 600px initial height.
- **DList.tsx** — BulkActionBar (sticky top), footer Paginator (sticky bottom), multi-select with checkboxes on hover, infinite scroll sentinel.
- **DButton.tsx** — Lucide icon resolution with PascalCase fallback.
- **DImage.tsx** — click action support, object-fit, caption.
- **DFileUpload.tsx** — drag-and-drop zone, base64 encoding, file type/size validation.
- **Stack.tsx** — direction "horizontal" + sticky prop + system padding.
- **usePanelDiscovery** — `get_oauth_url` excluded from chat echo. Compose as centerOverlay. `mergeListItems` for any container.
- **ExtensionPage** — ChatClient persists via CSS show/hide (reduces reload on email open/close).

### Mail DUI — Full Panel Migration
- 5 DUI panels: inbox (selectable, bulk actions, infinite scroll), email_viewer (sticky toolbar, Reply All, Gmail-style header), accounts, compose (BCC, Back button, Reply All CC pre-fill), add_account (3-step OAuth/IMAP wizard).
- 6 panel action handlers: mail_action, folder_counts, get_oauth_url, add_imap, compose_send, switch_account.
- Center overlay: email viewer and compose open in CENTER (chat moves right).
- **`_decode_body_with_type()`** — preserves raw HTML for panel viewer. Old `_decode_body()` kept for chat/LLM.
- **Full email body** — removed `body[:4000]` truncation in Google/Microsoft `read_email()`.
- **Image proxy** — `_proxy_images()` base64url-encodes URLs correctly.
- God file split: imap.py (839 to 4 files), helpers.py (500 to 4 files).

### Kernel Fix
- **`_serialize_result`** in `direct_call.py` — UINode returns in `ui` field (was `data`). Affects ALL extensions.

### Notes DUI — Full Panel Migration (v2.4.0)
- 2 DUI panels: sidebar (left — folders with counts, searchable note list, drag-drop, trash), editor (center overlay — TipTap RichEditor with auto-save).
- 1 panel handler: `note_save` (title/content/pin with targeted `refresh_panels`).
- Auto-open: sidebar returns `auto_action` on first load — frontend auto-opens most recent note.
- Markdown support: `_prepare_content()` detects plain text vs HTML, converts markdown via Python `markdown` library (extra, nl2br, sane_lists).
- Drag & drop: notes `draggable=True`, folders `droppable=True` with `on_drop=move_note`.
- Metadata: KeyValue display with Words, Created, Modified, Tags, ID.

### Generic Platform Improvements
- **`isCenterOverlay()` / `shouldClearOverlay()`** — extracted as generic functions in usePanelDiscovery (supports mail + notes + future extensions).
- **`auto_action`** — left panel root UINode can include `auto_action` prop; frontend auto-executes on first load via useEffect.
- **`overlayKey`** — counter in usePanelDiscovery, forces React remount of stateful components (TipTap) on overlay change.
- **`refresh_panels` from `ActionResult.data`** — usePanelDiscovery checks `result.data.refresh_panels` (was only checking top-level). Empty array = skip refresh.
- **Active item highlight** — usePanelDiscovery refreshes left panel with `active_note_id`/`active_message_id` context after opening centerOverlay.
- **ExtensionShell right panel** — shows when `rightSlot` provided even without `rightPanelCfg` (sensible defaults: 22% width).
- **DList paginator** — `mt-auto` ensures paginator always sticks to bottom even with few items.
- **Component count** — corrected from 53 to **55** (Html + Open were added in v1.5.0 but count wasn't updated).


## 1.4.0 (2026-04-13)

### Panel Discovery — Zero-Rebuild Registration
- **`config.ui` auto-publish** — kernel publishes `ext._panels` metadata to Auth GW config store after `loader.load()`. New extensions show panels automatically without Panel rebuild.
- **`panel_publish.py`** — new kernel module: `_build_ui_config()` groups panels by slot, merges refresh events; `maybe_publish_panels()` PUTs to Auth GW with MD5 hash dedup; `invalidate_publish_cache()` on hot-reload.
- **Dynamic frontend config** — `ExtensionPage.tsx` reads `config.ui` from Auth GW, builds `ShellConfig` dynamically. Hardcoded `CONFIGS` dict, `DISCOVERY_PANELS` list, and `LEFT_PANELS` set removed.
- **`@ext.panel()` kwargs** — `default_width`, `min_width`, `max_width` stored in `ext._panels` and published to `config.ui.panels.{slot}`.

### UI Test Suite
- **`test_ui.py`** — 50 tests covering all 55 UI components: serialization, props, defaults, actions, negative tests (TypeError on nonexistent props).
- **`test_panels.py`** — 10 tests for `@ext.panel()` decorator: tool registration, metadata storage, wrapper returns `{ui, panel_id}`, param passthrough, kwargs preservation.
- **Total: 309 tests** (was 249).

### DUI Component Polish
- **DToggle** — rewritten 1:1 with React standard (`w-9 h-5`, `translate-x-4`, `toBool()` for string boolean coercion in form defaults).
- **DStat** — renders Lucide icons properly via `icons[name]` import (was rendering icon name as text).
- **DSection** — added `py-1 px-0.5` spacing on title.
- **DList expanded content** — opens fully (removed `max-h-96` internal scroll).
- **ExtensionShell** — `overflow-x-hidden` on both panels, `p-4 overflow-y-auto` on right panel.

### Documentation
- **`ui-components.md` rewritten** — all 53 components with exact prop tables matching Python function signatures.
- Corrected: `Chart` param is `type` (serialized as `chart_type` in JSON), `Button` has no `icon_left`/`icon_right`, `Tabs` uses `{label, content}` with int `default_tab`.

## 1.3.0 (2026-04-11)

### New UI Components
- **`ui.SlideOver`** — side panel (title, subtitle, children, width sm/md/lg/xl, on_close)
- **`ui.RichEditor`** — TipTap rich text editor (content, placeholder, toolbar, on_save, on_change)
- **`ui.TagInput`** — tag/chip input with autocomplete and `grouped_by` for prefix grouping

### Enhanced Components
- **`ui.DataTable`** — `on_cell_edit` action for inline cell editing
- **`ui.DataColumn`** — `editable` and `edit_type` ("text"/"toggle") props
- **`ui.ListItem`** — `expandable` + `expanded_content` for collapsible inline content
- **`ui.Button`** — `size` (sm/md/lg) and `full_width` props

### Build & Marketplace
- **`imperal build`** — generates manifests with marketplace metadata merge

## 1.2.0 (2026-04-11)

### ChatExtension Split (6 files, all <300L)
- `chat/extension.py` — core ChatExtension class
- `chat/handler.py` — message handling loop
- `chat/guards.py` — KAV, intent guard, confirmation
- `chat/prompt.py` — system prompt builder
- `chat/filters.py` — context window management
- `chat/action_result.py` — ActionResult type

### Declarative UI — 43 Components
- **Layout (8):** Stack, Grid, Tabs, Page, Section, Row, Column, Accordion
- **Display (8):** Text, Icon, Header, Image, Code, Markdown, Empty, Divider
- **Interactive (6):** Button, Card, Menu, Dialog, Tooltip, Link
- **Input (9):** Input, Form, Select, MultiSelect, Toggle, Slider, DatePicker, FileUpload, TextArea
- **Data (11):** ListItem, List, DataColumn, DataTable, Stat, Stats, Badge, Avatar, Timeline, Tree, KeyValue
- **Feedback (5):** Alert, Progress, Chart, Loading, Error
- **Actions (3):** Call, Navigate, Send

### Extension Decorators
- **`@ext.panel()`** — registers `__panel__{id}` ToolDef + stores panel metadata
- **`@ext.widget()`** — registers `__widget__{id}` ToolDef
- **`@ext.webhook()`** — registers `__webhook__{path}` ToolDef
- **`ActionResult.ui`** — inline Declarative UI in chat responses

### Inter-Extension IPC
- **`ctx.extensions.call(app_id, method, **params)`** — direct in-process, kernel-mediated
- **`ctx.extensions.emit(event_type, data)`** — event broadcasting
- `ContextFactory.create_child()` — fork() semantics for child contexts

### Kernel Package Separation
- Runtime files moved to `imperal-kernel` package (internal, not on PyPI)

## 1.1.0 (2026-04-11)

### Declarative UI Module (Initial)
- **`from imperal_sdk import ui`** — first 16 components (Stack, Grid, Tabs, List, ListItem, Stat, Badge, Text, Avatar, DataTable, Button, Input, Icon, Card, Alert, Progress, Chart)
- **UINode** base class with `.to_dict()` serialization
- **UIAction** base class for Call, Navigate, Send

### Pydantic Fix
- **DirectCallWorkflow** — `func_def._pydantic_model` for PEP 563 compatibility
- Auto-detect Pydantic BaseModel params in `@chat.function` signatures

## 1.0.0 (2026-04-10)

### Typed Everything
- **Context** — typed `User`, `Tenant` dataclasses with `has_scope()`, `has_role()`
- **Client returns** — `Store→Document`, `AI→CompletionResult`, `Billing→LimitsResult`, `Storage→FileInfo`, `HTTP→HTTPResponse`
- **ChatResult + FunctionCall** — typed returns for ChatExtension._handle()
- **Page[T]** — cursor-based pagination with iteration support

### Extension Protocol & Validation
- **ExtensionProtocol** — formal interface for extensions
- **Validator** — 12 rules (V1 app_id, V2 version, V3 tools, V5 ActionResult return, V6 Pydantic params, V7 no direct LLM imports, V9 health check, etc.)
- **`imperal validate`** — CLI command for extension validation

### Extension Lifecycle
- **`@ext.on_install`**, **`@ext.on_upgrade(version)`**, **`@ext.on_uninstall`**, **`@ext.on_enable`**, **`@ext.on_disable`**
- **`@ext.health_check`** — health check endpoint
- **`@ext.on_event(event_type)`** — event handler registration
- **`@ext.expose(name, action_type)`** — inter-extension IPC method

### Testing
- **MockContext** — 10 mock clients for extension unit testing
- **`imperal init`** — project template updated to v1.0.0 pattern (ChatExtension + ActionResult)

### Error Hierarchy
- `ImperalError` → `AuthError`, `RateLimitError`, `StoreError`, `ConfigError`, `ExtensionError`

## 0.4.0 (2026-04-08)

### Multi-Model LLM Abstraction
- **LLMProvider** — unified multi-model provider with config resolution, client pool, automatic failover, per-call usage tracking
- **MessageAdapter** — Anthropic ↔ OpenAI message format translation
- **BYOLLM** — users bring their own LLM API keys (stored encrypted in ext_store)
- **Per-purpose routing** — different models for routing/execution/navigate
- **Per-extension override** — admin configures specific model per extension
- **Usage tracking** — Redis `imperal:llm_usage:{user_id}:{date}`
- **Zero direct anthropic imports** — all LLM calls through `get_llm_provider()`

## 0.3.0 (2026-04-08)

### ActionResult + Event Publishing
- **ActionResult** — universal return type with `.success()` / `.error()` factories
- **Event Publisher** — automatic kernel event publishing for write/destructive actions
- **Deterministic Truth Gate** — ActionResult.status as ground truth
- **Template Resolver** — `{{steps.N.data.*}}` variable passing for automation chains

## 0.2.0 (2026-04-03)

### ChatExtension + Hub Routing
- **ChatExtension** — single entry point with LLM routing for extensions
- **Hub LLM Routing** — embeddings optimize, LLM decides (multilingual)
- **Context Window Management** — 6 configurable guards
- **KAV** — Kernel Action Verification for write/destructive actions
- **2-Step Confirmation** — user approval for sensitive actions

## 0.1.0 (2026-04-02)

- Initial release: Extension, Context, Auth, Tool registration, SDK CLI stubs
