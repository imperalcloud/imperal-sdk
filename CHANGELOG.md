# Changelog

All notable changes to `imperal-sdk` are documented here.

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
- **System padding** — horizontal Stacks get default `px-3 py-1` for consistent alignment.

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

## 1.4.0 (2026-04-13)

### Panel Discovery — Zero-Rebuild Registration
- **`config.ui` auto-publish** — kernel publishes `ext._panels` metadata to Auth GW config store after `loader.load()`. New extensions show panels automatically without Panel rebuild.
- **`panel_publish.py`** — new kernel module: `_build_ui_config()` groups panels by slot, merges refresh events; `maybe_publish_panels()` PUTs to Auth GW with MD5 hash dedup; `invalidate_publish_cache()` on hot-reload.
- **Dynamic frontend config** — `ExtensionPage.tsx` reads `config.ui` from Auth GW, builds `ShellConfig` dynamically. Hardcoded `CONFIGS` dict, `DISCOVERY_PANELS` list, and `LEFT_PANELS` set removed.
- **`@ext.panel()` kwargs** — `default_width`, `min_width`, `max_width` stored in `ext._panels` and published to `config.ui.panels.{slot}`.

### UI Test Suite
- **`test_ui.py`** — 50 tests covering all 53 UI components: serialization, props, defaults, actions, negative tests (TypeError on nonexistent props).
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
