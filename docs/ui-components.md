# Imperal SDK — Declarative UI Components Reference

**Version:** v1.5.17 | **Components:** 57 across 8 modules
**Import:** `from imperal_sdk import ui`
**Serialization:** All components return `UINode` objects. Call `.to_dict()` to get JSON for Panel rendering.

> **Module breakdown:** `layout.py` (8), `display.py` (9), `interactive.py` (7), `input_components.py` (11), `data.py` (11), `feedback.py` (5), `graph.py` (1 — `ui.Graph`), actions (4 — `Call`, `Navigate`, `Send`, `Open`). All imported via `from imperal_sdk import ui` — module split is internal only.
>
> **v1.5.16 (2026-04-20) — Stack.wrap is now tri-state.** `ui.Stack(wrap=False)` on a horizontal Stack now correctly emits the prop so the Panel-side auto-wrap default can be opted out of. Default behaviour (no `wrap=` passed → Panel picks direction-specific default) is unchanged from the extension author's perspective. See CHANGELOG.md for the full rule. Test coverage: `tests/test_ui.py::TestStack::test_wrap_default_not_emitted` + `::test_wrap_false_explicit_emitted`.
>
> **⚡ Session 33 (2026-04-19 → 2026-04-20) — Panel automatic styling shipped.** Extension code is UNCHANGED, but the Panel now handles every visual concern automatically:
> - **Tailwind `@theme` colour remap** in `tokens.css` — every hardcoded `bg-gray-*` / `bg-blue-*` / `text-*` class across Panel + D*-components now routes through `--imp-color-*` agency-overridable tokens. Theme toggle + `PUT /v1/agencies/{id}/theme` cascade to entire Panel + extensions in one stroke. Zero extension changes required.
> - **Container-level padding philosophy.** `ExtensionShell` wraps pane content in `ext-pane` utility (token-driven padding + gap). Whether you emit `ui.Page(...)` or bare `ui.List(...)` / `ui.Text(...)`, you get Imperal-standard outer padding + vertical rhythm automatically — no flush-to-edges, no extension code.
> - **DPage / DSection / DCard / DText / DList / DHeader / DDivider refactored** — leaf components are naked (no inner `px-3`). Container components own spacing. Eliminates the old double-padding bug where Card + inner Text both added their own inset.
> - **Horizontal `ui.Stack(direction="h")` auto-wraps by default** — a toolbar with 6 buttons in a narrow pane now wraps to next row instead of overflowing. Opt out with `wrap=False` only when you know the layout stays narrow.
> - **`min-width: 0 + max-width: 100%` containment** on every pane child — long text/urls/codes truncate or wrap gracefully, never bleed outside pane.
> - **~40 element-level sizing tokens** in `tokens.css` (button/card/input/modal/pill/menu/tooltip/row/field/focus-ring) + matching `@utility` wrappers (`btn-pad-md`, `btn-shape`, `card-pad`, `modal-shape`, etc.). One file tunes every UI element across the whole platform.
> - **ESLint wall** (`no-restricted-syntax`) blocks hardcoded Tailwind colour scales in new Panel code. Extension SDK code (Python) unaffected — extensions never write Tailwind.
> - **Authority hierarchy enforced** — Level 4 Imperal team (full design system access) > Level 3 Agency owner (JSON theme, 26 whitelisted colour keys + density + radius) > Level 2 Extension developer (semantic variants only) > Level 1 End user (light/dark/auto toggle). See [`docs/imperal-cloud/design-system.md`](../../docs/imperal-cloud/design-system.md) for decision tree + Tailwind remap complete mapping + escape hatches.
>
> **v1.5.15 (2026-04-19, session 32/33) — per-agency theming + visual regression infrastructure:**
> - `ui.theme(ctx)` accessor — returns `AgencyTheme` frozen dataclass. Most extensions do NOT need to read theme directly; emit `variant="primary"` and Panel renders with correct agency colour. Use `ui.theme(ctx)` only for dynamic colour work (chart series beyond defaults, SVG brand graphics).
> - `Context.agency_id: str | None` + `Context.agency_theme: dict | None` fields.
> - Auth Gateway `PUT /v1/agencies/{id}/theme` endpoint + Pydantic validation (26 whitelisted colour keys, WCAG AA contrast enforcement on primary × surface-0 in both modes).
> - Panel SSR cascades agency theme via `<ThemeRoot>` — CSS custom properties on root element, Tailwind classes read them transparently.
> - Playwright visual regression suite: 8 surfaces × 3 theme conditions (default-light, default-dark, test-federal) = 24 baselines. Hardcoded colour regressions produce visible diffs under `test-federal` theme (deep-forest primary, yellow accent, red danger — deliberately high-contrast).
> - `IMPERAL_ALLOW_THEME_OVERRIDE` env flag + `imp_agency_override` cookie for controlled testing on non-prod environments.
>
> **v1.5.7 (2026-04-18, session 30) — DUI additions + live-update chain repaired:**
> - `ui.Progress(color=...)` — blue/green/red/yellow/purple for semantic status bars.
> - `ui.Chart(colors=..., y2_keys=...)` — per-series color override + optional secondary right-side Y-axis for mixed-scale metrics.
> - `ui.TagInput(delimiters=..., validate=..., validate_message=...)` — space/comma-style delimiters, regex validation with inline red caption, paste splits on delimiters.
> - `DToggle` / `DSelect` now register their `initValue` with `FormContext` on mount so unchanged inputs appear in submit payload (the real GAP-2 root cause — Form's Context propagates through arbitrary nesting fine; lazy registration was the bug).
> - Panel `refresh: "on_event:X"` + `refetchPanelData` chain wired end-to-end (was TODO-never-wired before).
> - Panel `/call` transport bypasses Temporal via Redis Streams when `IMPERAL_FAST_RPC_PANELS=true` on Auth GW — measured end-to-end p50 **388ms → 3ms**. Extension author code unchanged; same `direct_call_extension` activity. See [`fast-rpc.md`](../fast-rpc.md).
> - Kernel `@ext.schedule` dispatcher shipped (`ext_scheduler.py`). Previously declared schedules never fired — fixed in session 30.
>
> **v1.5.6 (2026-04-17) — CRITICAL event-publishing fix:** `ChatExtension._make_chat_result` now passes `result=fc_dict.get("result")` into `FunctionCall`. Without this, `@chat.function(event="X")` never fired — sidebar `refresh="on_event:X"` and automation rules were silently broken. Companion kernel fix hydrates dict→`ActionResult` post-Temporal transport.
>
> **v1.5.5 (2026-04-16) — new `ui.Graph` Cytoscape component.** See [Visualization Components](#visualization-components) below. Designed for forensic entity/relationship graphs (Sharelock v3). Performance target ~5,000 nodes.
>
> **v1.5.4:** `@ext.tray()` decorator + `TrayResponse` (System Tray). OS identity enforcement — `ChatExtension.__init__` warns when `system_prompt` contains "You are …".
>
> **v1.5.2:** `Video`, `Audio` display components. `Row` + `Column` registered in Panel (aliases for `Stack`).
>
> **v1.4.0+:** `SlideOver`, `RichEditor`, `TagInput`. `DataTable` inline editing (`on_cell_edit`, `DataColumn.editable`). `ListItem.expandable` + `expanded_content`. `Button.size` + `full_width`. `Chart` param is `type` (serialized as `chart_type`).
>
> **v1.5.0:** `Html`, `Open`, `Image` click support, `FileUpload` validation, `Button` icon prop. Panel Discovery: `@ext.panel()` auto-publishes `config.ui` to Auth GW — zero-rebuild panel registration.

---

## Actions

Actions are not visual components. They describe what happens when a user interacts with a component (clicks a button, submits a form, etc.). Pass them as `on_click`, `on_submit`, `on_change`, etc.

| Action | Signature | Description |
|--------|-----------|-------------|
| `ui.Call` | `Call(function: str, **params)` | Direct function call. Executes a `@chat.function` handler bypassing the chat LLM. Params are passed as keyword arguments to the handler. |
| `ui.Navigate` | `Navigate(path: str)` | Client-side navigation. The Extension Shell stays mounted, only the content area changes. |
| `ui.Send` | `Send(message: str)` | Send a message to the chat input as if the user typed it. Triggers LLM routing. |
| `ui.Open` | `Open(url: str)` | Open an external URL in a new browser tab. |

### `ui.Open(url)`
Open an external URL in a new browser tab.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | URL to open |

Returns `UIAction` with `action="open"`.

```python
# Call a handler directly with parameters
ui.Button("Delete", variant="danger", on_click=ui.Call("delete_note", note_id="abc123"))

# Navigate to another section
ui.Button("Settings", on_click=ui.Navigate("/settings"))

# Send a chat message
ui.Button("Help", variant="ghost", on_click=ui.Send("How do I create a note?"))

# Open external URL
ui.Button("Docs", variant="ghost", on_click=ui.Open("https://docs.imperal.io"))
```

---

## Layout Components

8 components for arranging child elements on screen.

### `ui.Stack`
Flex container -- vertical or horizontal.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[UINode]` | required | Child components |
| `direction` | `str` | `"v"` | `"v"` for vertical (column), `"h"` or `"horizontal"` for horizontal (row) |
| `gap` | `int` | `3` | Gap between children (Tailwind spacing scale) |
| `align` | `str` | `""` | Align items: `"start"`, `"center"`, `"end"`, `"stretch"` |
| `justify` | `str` | `""` | Justify content: `"start"`, `"center"`, `"end"`, `"between"`, `"around"` |
| `wrap` | `bool` | `False` | Allow flex wrapping |
| `sticky` | `bool` | `False` | Pin to top of scroll container (for toolbars/action bars) |
| `className` | `str` | `""` | Custom CSS classes (overrides default system padding) |

Horizontal stacks get system-level `px-3 py-1` padding by default for consistent alignment. Override with `className`.

```python
ui.Stack([ui.Button("Save"), ui.Button("Cancel", variant="ghost")], direction="h", gap=2)
ui.Stack([ui.Button("Back"), ui.Button("Reply")], direction="h", sticky=True)  # pinned toolbar
```

### `ui.Grid`
CSS Grid layout.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[UINode]` | required | Child components |
| `columns` | `int` | `2` | Number of columns |
| `gap` | `int` | `3` | Gap between cells (Tailwind spacing scale) |

```python
ui.Grid([ui.Stat(...), ui.Stat(...), ui.Stat(...), ui.Stat(...)], columns=2)
```

### `ui.Tabs`
Tabbed content container with a tab bar.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `tabs` | `list[dict]` | required | Each dict: `{"label": str, "content": list[UINode]}` |
| `default_tab` | `int` | `0` | Index of the active tab on load (0-based) |

**IMPORTANT:** Tabs use `{label, content}` -- NOT `{id, label, children}`. The `default_tab` is an integer index, not a string ID.

```python
ui.Tabs(tabs=[
    {"label": "All (31)", "content": [ui.List(items=[...])]},
    {"label": "Work (7)", "content": [ui.List(items=[...])]},
], default_tab=0)
```

### `ui.Page`
Top-level container for a full panel page.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[UINode]` | required | Page content |
| `title` | `str` | `""` | Page title (rendered as heading) |
| `subtitle` | `str` | `""` | Subtitle below title |

```python
ui.Page([
    ui.Stats([ui.Stat(label="Users", value=42)]),
    ui.List(items=[...]),
], title="Dashboard", subtitle="System overview")
```

### `ui.Section`
Grouped section with optional title.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[UINode]` | required | Section content |
| `title` | `str` | `""` | Section heading |
| `collapsible` | `bool` | `False` | Whether the section can be collapsed |

```python
ui.Section([ui.Text(content="Section body")], title="Details", collapsible=True)
```

### `ui.Row`
Horizontal flex container. Alias for `Stack(direction="h")`.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[UINode]` | required | Child components |
| `gap` | `int` | `3` | Gap between children |

```python
ui.Row([ui.Badge(label="Active", color="green"), ui.Text(content="server-1")])
```

### `ui.Column`
Vertical flex container. Alias for `Stack(direction="v")`.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[UINode]` | required | Child components |
| `gap` | `int` | `3` | Gap between children |

### `ui.Accordion`
Collapsible sections with expand/collapse behavior.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `sections` | `list[dict]` | required | Each dict: `{"id": str, "title": str, "children": list[UINode]}` |
| `allow_multiple` | `bool` | `False` | Allow multiple sections open simultaneously |

```python
ui.Accordion(sections=[
    {"id": "general", "title": "General", "children": [ui.Text(content="...")]},
    {"id": "advanced", "title": "Advanced", "children": [ui.Text(content="...")]},
], allow_multiple=False)
```

---

## Display Components

9 components for showing text, images, and other static content.

### `ui.Text`
Text block with variant styling.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `content` | `str` | `""` | Text content |
| `variant` | `str` | `"body"` | Style variant: `heading`, `subheading`, `body`, `caption`, `code`, `label` |

```python
ui.Text(content="System Status", variant="heading")
ui.Text(content="Last updated 5m ago", variant="caption")
```

### `ui.Header`
Heading element (h1-h4) with optional subtitle.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `text` | `str` | required | Heading text |
| `level` | `int` | `2` | Heading level: 1, 2, 3, or 4 |
| `subtitle` | `str` | `""` | Subtitle rendered below the heading |

```python
ui.Header(text="User Management", level=1, subtitle="Manage platform users and roles")
```

### `ui.Icon`
Lucide icon by name.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `name` | `str` | required | Lucide icon name (e.g., `"Folder"`, `"Trash2"`, `"Mail"`, `"Users"`) |
| `size` | `int` | `16` | Size in pixels |
| `color` | `str` | `""` | Color override (CSS color value or Tailwind class) |

```python
ui.Icon(name="Shield", size=20, color="text-blue-400")
```

### `ui.Image`
Image element.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `src` | `str` | required | Image URL |
| `alt` | `str` | `""` | Alt text for accessibility |
| `width` | `str` | `""` | CSS width (e.g., `"200px"`, `"50%"`, `""` = auto) |
| `height` | `str` | `""` | CSS height (e.g., `"200px"`, `"50%"`, `""` = auto) |
| `on_click` | `UIAction \| None` | `None` | Action when image is clicked |
| `object_fit` | `str` | `""` | CSS object-fit (`"cover"`, `"contain"`, etc.) |
| `caption` | `str` | `""` | Image caption text |

```python
ui.Image(src="https://example.com/photo.jpg", alt="Profile", width="200px", height="200px")
ui.Image(src=logo_url, on_click=ui.Open("https://imperal.io"), caption="Click to visit")
```

### `ui.Code`
Syntax-highlighted code block.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `content` | `str` | required | Code content |
| `language` | `str` | `""` | Language for syntax highlighting (e.g., `"python"`, `"json"`) |
| `line_numbers` | `bool` | `False` | Show line numbers |

```python
ui.Code(content='print("Hello")', language="python", line_numbers=True)
```

### `ui.Markdown`
Rendered markdown content.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `content` | `str` | required | Markdown string |

```python
ui.Markdown(content="**Bold** and *italic* with [links](https://example.com)")
```

### `ui.Divider`
Horizontal rule with optional centered label.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `label` | `str` | `""` | Centered label text (empty = plain line) |

```python
ui.Divider(label="or")
```

### `ui.Empty`
Empty state placeholder with optional icon and action.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `str` | `""` | Message to display |
| `icon` | `str` | `""` | Lucide icon name |
| `action` | `UIAction` | `None` | Optional action button (e.g., `ui.Call(...)`) |

```python
ui.Empty(message="No notes yet", icon="FileText", action=ui.Call("create_note"))
```

### `ui.Html`
Raw HTML block with DOMPurify sanitization and iframe sandbox.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `content` | `str` | required | HTML content (sanitized with DOMPurify) |
| `sandbox` | `bool` | `True` | Render in sandboxed iframe (`allow-same-origin allow-popups`) |
| `max_height` | `int` | `0` | Scroll container height. `0` = auto-resize via ResizeObserver |
| `theme` | `str` | `"dark"` | `"dark"` (transparent bg, gray text) or `"light"` (white bg, dark text — for email) |

**Light theme** uses `-apple-system` font, `#1a1a1a` text, `#ffffff` background — matches standard email rendering. Auto-resizes with `overflow: auto` and `maxHeight: 3000`.

```python
ui.Html(content=email_body, sandbox=True, theme="light")  # Email rendering
ui.Html(content="<b>Rich content</b>", sandbox=False)       # Inline HTML
```

---

## Interactive Components

7 components for user interaction beyond form inputs.

### `ui.Button`
Clickable button.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `label` | `str` | required | Button text |
| `variant` | `str` | `"primary"` | Style: `primary`, `secondary`, `ghost`, `danger` |
| `on_click` | `UIAction` | `None` | Click action |
| `disabled` | `bool` | `False` | Disabled state |
| `size` | `str` | `"md"` | Size: `sm`, `md`, `lg` |
| `full_width` | `bool` | `False` | Stretch to full container width |
| `icon` | `str` | `""` | Lucide icon name (e.g., `"Plus"`, `"Trash2"`, `"ArrowLeft"`) |

**NOTE:** `icon_left` and `icon_right` props do NOT exist on Button. Use the `icon` prop for a single icon rendered alongside the label. For more complex icon+button layouts, use a `ui.Row` with `ui.Icon` and `ui.Button` side by side.

```python
ui.Button("Save Changes", variant="primary", size="md", on_click=ui.Call("save"))
ui.Button("Delete", variant="danger", disabled=True, icon="Trash2")
ui.Button("Expand", variant="ghost", size="sm", full_width=True)
ui.Button("Add Note", icon="Plus", on_click=ui.Call("create_note"))
```

### `ui.Card`
Container card with title, body content, and footer.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | `str` | `""` | Card title |
| `subtitle` | `str` | `""` | Card subtitle |
| `content` | `UINode` | `None` | Card body (single UINode or list) |
| `footer` | `UINode` | `None` | Card footer |
| `on_click` | `UIAction` | `None` | Card click action |

```python
ui.Card(
    title="web-server1",
    subtitle="203.0.113.42",
    content=ui.Stack([ui.Text(content="Load: 0.42"), ui.Text(content="Uptime: 47d")]),
    footer=ui.Button("Details", variant="ghost", on_click=ui.Navigate("/server/1")),
)
```

### `ui.Menu`
Dropdown menu triggered by a button or custom trigger.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `items` | `list[dict]` | required | Each dict: `{"label": str, "icon": str, "on_click": UIAction}` |
| `trigger` | `UINode` | `None` | Custom trigger element (defaults to a "..." button) |

```python
ui.Menu(items=[
    {"label": "Edit", "icon": "Pencil", "on_click": ui.Call("edit_role", role_id="admin")},
    {"label": "Delete", "icon": "Trash2", "on_click": ui.Call("delete_role", role_id="admin")},
])
```

### `ui.Dialog`
Modal dialog with confirm/cancel actions.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | `str` | required | Dialog title |
| `content` | `UINode` | `None` | Dialog body content |
| `confirm_label` | `str` | `"Confirm"` | Confirm button text |
| `cancel_label` | `str` | `"Cancel"` | Cancel button text |
| `on_confirm` | `UIAction` | `None` | Action on confirm |

```python
ui.Dialog(
    title="Delete user?",
    content=ui.Text(content="This action cannot be undone."),
    confirm_label="Delete",
    on_confirm=ui.Call("delete_user", user_id="abc"),
)
```

### `ui.Tooltip`
Hover tooltip that wraps a child element.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `content` | `str` | required | Tooltip text |
| `children` | `UINode` | `None` | Element to wrap |

```python
ui.Tooltip(content="Click to copy", children=ui.Icon(name="Copy", size=14))
```

### `ui.Link`
Hyperlink, either navigating to a URL or triggering an action.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `label` | `str` | required | Link text |
| `href` | `str` | `""` | URL (opens in new tab) |
| `on_click` | `UIAction` | `None` | Click action (overrides href) |

```python
ui.Link(label="View docs", href="https://docs.imperal.io")
ui.Link(label="Open profile", on_click=ui.Navigate("/users/abc"))
```

### `ui.SlideOver`
Side panel that slides in from the right edge.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | `str` | required | Panel title |
| `subtitle` | `str` | `""` | Panel subtitle |
| `children` | `UINode` | `None` | Panel content |
| `open` | `bool` | `True` | Whether the panel is open |
| `width` | `str` | `"md"` | Width: `sm`, `md`, `lg`, `xl` |
| `on_close` | `UIAction` | `None` | Action when panel is closed |

```python
ui.SlideOver(
    title="User Details",
    subtitle="john@example.com",
    width="lg",
    open=True,
    children=ui.Stack([ui.Text(content="..."), ui.Button("Save")]),
    on_close=ui.Call("close_detail"),
)
```

---

## Input Components

11 components for capturing user input. Several of these integrate with `ui.Form` for grouped submissions.

### `ui.Input`
Single-line text input.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `placeholder` | `str` | `""` | Placeholder text |
| `value` | `str` | `""` | Initial/controlled value |
| `param_name` | `str` | `"value"` | Key name for the value in action params |
| `on_submit` | `UIAction` | `None` | Action on Enter. The typed value is merged into params under `param_name` |

```python
ui.Input(
    placeholder="New folder name...",
    param_name="name",
    on_submit=ui.Call("create_folder"),
)
# User types "Work" and presses Enter -> Call("create_folder", name="Work")
```

### `ui.TextArea`
Multi-line text input.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `placeholder` | `str` | `""` | Placeholder text |
| `value` | `str` | `""` | Initial/controlled value |
| `rows` | `int` | `4` | Visible rows |
| `param_name` | `str` | `"text"` | Key name for the value in action params |
| `on_submit` | `UIAction` | `None` | Action on submit |

```python
ui.TextArea(placeholder="Write your note...", rows=8, param_name="body")
```

### `ui.Toggle`
Boolean switch.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `label` | `str` | `""` | Label text next to the toggle |
| `value` | `bool` | `False` | Current state |
| `on_change` | `UIAction` | `None` | Action on toggle. Value merged under `param_name` |
| `param_name` | `str` | `"enabled"` | Key name for the boolean value in action params |

```python
ui.Toggle(label="Enable notifications", value=True, param_name="notifications",
          on_change=ui.Call("update_settings"))
# Toggle off -> Call("update_settings", notifications=False)
```

### `ui.Select`
Single-value dropdown select.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `options` | `list[dict]` | required | Each dict: `{"value": str, "label": str}` |
| `value` | `str` | `""` | Currently selected value |
| `placeholder` | `str` | `""` | Placeholder when no value selected |
| `param_name` | `str` | `"value"` | Key name for the selected value in action params |
| `on_change` | `UIAction` | `None` | Action on selection change |

**NOTE:** `ui.Select` does NOT have a `label` prop. To add a label, place a `ui.Text(variant="label")` above it.

```python
ui.Text(content="Role", variant="label")
ui.Select(
    options=[{"value": "admin", "label": "Admin"}, {"value": "user", "label": "User"}],
    value="user",
    param_name="role",
    on_change=ui.Call("set_role"),
)
```

### `ui.MultiSelect`
Multi-value select (checkboxes or tags).

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `options` | `list[dict]` | required | Each dict: `{"value": str, "label": str}` |
| `values` | `list[str]` | `[]` | Currently selected values |
| `placeholder` | `str` | `""` | Placeholder text |
| `param_name` | `str` | `"values"` | Key name for the selected values list in action params |

```python
ui.MultiSelect(
    options=[{"value": "read", "label": "Read"}, {"value": "write", "label": "Write"}],
    values=["read"],
    param_name="permissions",
)
```

### `ui.Slider`
Range slider input.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `min` | `int` | `0` | Minimum value |
| `max` | `int` | `100` | Maximum value |
| `value` | `int` | `50` | Current value |
| `step` | `int` | `1` | Step increment |
| `label` | `str` | `""` | Label text |
| `param_name` | `str` | `"value"` | Key name for the value in action params |

```python
ui.Slider(min=0, max=1000, value=100, step=10, label="Monthly action limit", param_name="limit")
```

### `ui.DatePicker`
Date input.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `value` | `str` | `""` | Current date value (ISO format) |
| `placeholder` | `str` | `""` | Placeholder text |
| `param_name` | `str` | `"date"` | Key name for the date value in action params |
| `on_change` | `UIAction` | `None` | Action on date change |

```python
ui.DatePicker(placeholder="Select start date", param_name="start_date",
              on_change=ui.Call("filter_by_date"))
```

### `ui.FileUpload`
File upload dropzone.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `accept` | `str` | `"*"` | Accepted file types (e.g., `".pdf,.doc"`, `"image/*"`) |
| `max_size_mb` | `int` | `10` | Maximum file size per file in MB |
| `multiple` | `bool` | `False` | Allow multiple files |
| `param_name` | `str` | `"files"` | Key name for files in action params |
| `on_upload` | `UIAction` | `None` | Action after upload |
| `blocked_extensions` | `list[str]` | `[]` | Blocked file extensions (e.g., `[".exe", ".bat"]`) |
| `max_total_mb` | `int` | `0` | Maximum total upload size in MB (`0` = no limit) |
| `max_files` | `int` | `0` | Maximum number of files (`0` = no limit) |

```python
ui.FileUpload(accept="image/*", max_size_mb=5, multiple=True, on_upload=ui.Call("attach_images"))
ui.FileUpload(
    accept=".pdf,.doc,.docx",
    max_size_mb=25,
    max_total_mb=100,
    max_files=10,
    multiple=True,
    blocked_extensions=[".exe", ".bat", ".sh"],
    on_upload=ui.Call("upload_documents"),
)
```

### `ui.Form`
Form container that groups input children and submits them together.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[UINode]` | required | Form fields (Input, Select, Toggle, TextArea, etc.) |
| `action` | `str` | `""` | Function name to call on submit (equivalent to `ui.Call(action)`) |
| `submit_label` | `str` | `"Submit"` | Submit button text |
| `defaults` | `dict` | `{}` | Default values keyed by `param_name` |

Children inside a Form automatically get FormContext. Each child's `param_name` becomes a key in the submitted params dict. The Form collects all values and submits them as a single `ui.Call`.

> **Context propagation (session 30 correction).** FormContext propagates through React context down the ENTIRE render tree, not only direct children. Inputs wrapped inside `ui.Stack`, `ui.Row`, `ui.Grid`, `ui.Section`, etc. still report their values — the earlier-documented "only direct children" behaviour was a misdiagnosis. The real bug was that `ui.Toggle` and `ui.Select` only registered their value with the Form when the user interacted with them, so unchanged inputs never appeared in the submit payload. `DToggle` and `DSelect` now register `initValue` on mount (session 30, GAP-2) — every declared field with a `param_name` is guaranteed to be present in the submitted params, even when the user does not touch it. Put `defaults` on `ui.Form` to pre-fill values cleanly.

```python
ui.Form(
    children=[
        ui.Text("Username", variant="caption"),
        ui.Input(placeholder="Username", param_name="username"),
        ui.Select(
            options=[{"value": "admin", "label": "Admin"}, {"value": "user", "label": "User"}],
            param_name="role",
        ),
        ui.Toggle(label="Active", param_name="active"),
    ],
    action="create_user",
    submit_label="Create User",
    defaults={"role": "user", "active": True},
)
# On submit -> Call("create_user", username="john", role="admin", active=True)
```

### `ui.RichEditor`
TipTap-based rich text editor with toolbar.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `content` | `str` | `""` | Initial HTML content |
| `placeholder` | `str` | `"Start writing..."` | Placeholder text |
| `param_name` | `str` | `"content"` | Key name for the content in action params |
| `toolbar` | `bool` | `True` | Show/hide toolbar |
| `on_save` | `UIAction` | `None` | Action on save (Ctrl+S) |
| `on_change` | `UIAction` | `None` | Action on content change (debounced 500ms on frontend) |

```python
ui.RichEditor(
    content="<p>Hello world</p>",
    placeholder="Start writing...",
    param_name="body",
    on_save=ui.Call("save_note"),
)
```

### `ui.TagInput`
Tag/chip input with autocomplete suggestions.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `values` | `list[str]` | `[]` | Current tag values |
| `suggestions` | `list[str]` | `[]` | Autocomplete suggestions |
| `placeholder` | `str` | `"Add..."` | Placeholder text |
| `param_name` | `str` | `"tags"` | Key name for the tag list in action params |
| `on_change` | `UIAction` | `None` | Action when tags change |
| `grouped_by` | `str` | `""` | Delimiter to group suggestions (e.g., `":"` groups `"audit:read"` under `"audit"`) |
| `delimiters` | `list[str] \| None` | `None` | Extra keys that create a tag in addition to Enter. Accept single chars (e.g. `[" ", ",", ";"]`). Paste is also split on these delimiters (paste `"a.com, b.com"` → 2 tags). Default = Enter-only (backwards-compatible). *(SDK 1.5.7, session 30)* |
| `validate` | `str` | `""` | Optional regex pattern. Tags failing the regex are refused; input highlighted red for 1.8s with `validate_message` tooltip. Anchor explicitly — use `^...$` for full-string match. *(SDK 1.5.7, session 30)* |
| `validate_message` | `str` | `""` | Human-readable hint shown on rejected tags. Empty = generic message. *(SDK 1.5.7, session 30)* |

```python
# Scope chip picker with grouped suggestions
ui.TagInput(
    values=["audit:read", "audit:write"],
    suggestions=["audit:read", "audit:write", "mail:read", "mail:send"],
    placeholder="Add scope...",
    param_name="scopes",
    on_change=ui.Call("update_scopes"),
    grouped_by=":",
)

# Domain list with space/comma separators + regex validation
ui.TagInput(
    values=["google.com"],
    placeholder="domain.com — press Enter, Space or comma to add",
    param_name="domains",
    delimiters=[" ", ","],
    validate=r"^[a-zA-Z0-9][a-zA-Z0-9\-]*\.[a-zA-Z0-9]+$",
    validate_message="Enter a valid domain: example.com",
)
```

---

## Data Display Components

11 components for rendering structured data: lists, tables, stats, and more.

### `ui.List`
Scrollable list with search, pagination, infinite scroll, and multi-select.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `items` | `list[UINode]` | required | `ListItem` nodes |
| `searchable` | `bool` | `False` | Show search bar |
| `grouped_by` | `str` | `""` | Group items by this field |
| `page_size` | `int` | `0` | Items per page. `0` = no pagination |
| `on_end_reached` | `UIAction` | `None` | Action fired when user scrolls to bottom (infinite scroll) |
| `selectable` | `bool` | `False` | Enable multi-select with checkboxes on hover |
| `bulk_actions` | `list[dict]` | `None` | Bulk action buttons: `[{"label", "icon", "action": Call(...)}]`. Selected IDs injected as `message_ids` param |
| `total_items` | `int` | `0` | Total count for footer Paginator display |
| `extra_info` | `str` | `""` | Extra text in Paginator footer (e.g. `"3 unread"`) |

**System pagination:** When `page_size > 0`, System Paginator pinned at bottom. When `total_items > 0`, footer Paginator shown (for infinite scroll lists). Both use `sticky bottom-0`.

**Multi-select:** When `selectable=True`, checkboxes appear on hover. Clicking row with active selection toggles checkbox. BulkActionBar (`sticky top-0`) shows action buttons when items selected. Selected IDs auto-injected into bulk action params.

```python
ui.List(
    items=[ui.ListItem(id="1", title="Item 1"), ui.ListItem(id="2", title="Item 2")],
    searchable=True,
    selectable=True,
    bulk_actions=[
        {"label": "Archive", "icon": "Archive", "action": ui.Call("archive")},
        {"label": "Delete", "icon": "Trash2", "action": ui.Call("delete")},
    ],
    on_end_reached=ui.Call("__panel__inbox", cursor="next_page_token"),
    total_items=150,
    extra_info="3 unread",
)
```

### `ui.ListItem`
Individual list entry, always used inside `ui.List`.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `id` | `str` | required | Unique identifier |
| `title` | `str` | required | Primary text |
| `subtitle` | `str` | `""` | Secondary text below title |
| `meta` | `str` | `""` | Right-aligned metadata (hidden on hover when actions exist) |
| `avatar` | `UINode` | `None` | Avatar component on the left |
| `badge` | `UINode` | `None` | Badge inline with title |
| `selected` | `bool` | `False` | Highlighted state (blue left border + bold) |
| `icon` | `str` | `""` | Lucide icon name displayed left of content |
| `on_click` | `UIAction` | `None` | Click action |
| `actions` | `list[dict]` | `[]` | Hover action buttons. Each: `{"icon": str, "on_click": UIAction, "confirm": str, "label": str}` |
| `draggable` | `bool` | `False` | HTML5 drag source (cursor-grab) |
| `droppable` | `bool` | `False` | HTML5 drop target (blue highlight on dragover) |
| `on_drop` | `UIAction` | `None` | Drop action. Receives `dragged_id` + `target_id` in params |
| `expandable` | `bool` | `False` | Enable collapsible inline content |
| `expanded_content` | `list[UINode] \| None` | `None` | Content shown when expanded (requires `expandable=True`) |

```python
ui.ListItem(
    id="note_123",
    title="My Note",
    subtitle="190 words",
    icon="FileText",
    badge=ui.Badge(label="pinned", color="yellow"),
    on_click=ui.Navigate("/notes/note_123"),
    draggable=True,
    expandable=True,
    expanded_content=ui.Text(content="Preview of note content..."),
    actions=[
        {"icon": "Trash2", "label": "Delete", "on_click": ui.Call("delete_note", note_id="note_123"),
         "confirm": "Delete 'My Note'?"}
    ],
)
```

### `ui.DataTable`
Sortable data table with optional inline cell editing.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `columns` | `list[DataColumn]` | required | Column definitions (use `ui.DataColumn()`) |
| `rows` | `list[dict]` | required | Row data dicts. Each dict key must match a column `key` |
| `on_row_click` | `UIAction` | `None` | Row click action |
| `on_cell_edit` | `UIAction` | `None` | Action when an editable cell is changed. Receives `row_id`, `column_key`, `value` |

```python
ui.DataTable(
    columns=[
        ui.DataColumn(key="name", label="Name", sortable=True),
        ui.DataColumn(key="role", label="Role", sortable=True, width="120px"),
        ui.DataColumn(key="active", label="Active", editable=True, edit_type="toggle", width="80px"),
    ],
    rows=[
        {"name": "Alice", "role": "Admin", "active": True},
        {"name": "Bob", "role": "User", "active": False},
    ],
    on_row_click=ui.Call("view_user"),
    on_cell_edit=ui.Call("toggle_user_active"),
)
```

### `ui.DataColumn`
Column definition helper for `ui.DataTable`.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `key` | `str` | required | Key in row data dict |
| `label` | `str` | required | Column header text |
| `sortable` | `bool` | `True` | Enable column sorting |
| `width` | `str` | `""` | Column width (CSS value, e.g., `"120px"`, `"20%"`) |
| `editable` | `bool` | `False` | Enable inline editing for this column |
| `edit_type` | `str` | `"text"` | Edit input type: `"text"` or `"toggle"` |

### `ui.Stat`
Single metric card showing a label, value, and optional trend.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `label` | `str` | required | Metric name |
| `value` | `Any` | required | Metric value (string or number) |
| `trend` | `str` | `""` | Trend indicator text (e.g., `"+12%"`, `"-3"`) |
| `icon` | `str` | `""` | Lucide icon name rendered in the card |
| `color` | `str` | `"blue"` | Color applied to the value text |

```python
ui.Stat(label="Active Users", value="1,247", trend="+12%", icon="Users", color="green")
```

### `ui.Stats`
Grid container for multiple `ui.Stat` components.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `children` | `list[Stat]` | required | `Stat` components |
| `columns` | `int` | `0` | Number of columns. `0` = auto-fit |

```python
ui.Stats([
    ui.Stat(label="Users", value=42, icon="Users"),
    ui.Stat(label="Extensions", value=6, icon="Puzzle"),
    ui.Stat(label="Actions Today", value=1583, icon="Zap"),
    ui.Stat(label="Uptime", value="99.9%", icon="Activity"),
], columns=4)
```

### `ui.Badge`
Colored pill/badge.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `label` | `str` | `""` | Badge text |
| `value` | `Any` | `None` | Badge value (used in system tray counters) |
| `color` | `str` | `"gray"` | Color: `blue`, `red`, `green`, `yellow`, `orange`, `cyan`, `purple`, `gray` |

```python
ui.Badge(label="Active", color="green")
ui.Badge(label="Error", color="red")
ui.Badge(label="3 pending", color="yellow")
```

### `ui.Avatar`
User avatar with image or fallback initials.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `fallback` | `str` | `"?"` | Fallback text when no image (typically initials) |
| `src` | `str` | `""` | Image URL |
| `size` | `str` | `"md"` | Size: `sm`, `md`, `lg` |

```python
ui.Avatar(fallback="VS", size="lg")
ui.Avatar(src="https://example.com/photo.jpg", size="md")
```

### `ui.Timeline`
Vertical timeline of events.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `items` | `list[dict]` | required | Each dict: `{"title": str, "description": str, "time": str, "icon": str, "color": str}` |

```python
ui.Timeline(items=[
    {"title": "User created", "description": "Account registered", "time": "2h ago",
     "icon": "UserPlus", "color": "green"},
    {"title": "Role changed", "description": "Promoted to admin", "time": "1h ago",
     "icon": "Shield", "color": "blue"},
])
```

### `ui.Tree`
Hierarchical tree view with expand/collapse.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `nodes` | `list[dict]` | required | Each dict: `{"id": str, "label": str, "children": list[dict], "icon": str}` |

```python
ui.Tree(nodes=[
    {"id": "root", "label": "Extensions", "icon": "Folder", "children": [
        {"id": "admin", "label": "Admin", "icon": "Shield", "children": []},
        {"id": "mail", "label": "Mail", "icon": "Mail", "children": []},
    ]},
])
```

### `ui.KeyValue`
Key-value pairs displayed in a grid layout.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `items` | `list[dict]` | required | Each dict: `{"key": str, "value": str}` |
| `columns` | `int` | `1` | Number of columns |

```python
ui.KeyValue(items=[
    {"key": "Email", "value": "user@example.com"},
    {"key": "Role", "value": "Admin"},
    {"key": "Created", "value": "2026-04-01"},
], columns=2)
```

---

## Visualization Components

### `ui.Graph`

Cytoscape-backed interactive graph. New in **v1.5.5**. Designed for forensic entity/relationship visualization (Sharelock v3), org charts, dependency graphs, knowledge graphs. Performance target: ~5,000 nodes.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `nodes` | `list[dict]` | required | Each: `{"id": str, "label": str, "type": str, "importance"?: float, "meta"?: dict}` |
| `edges` | `list[dict]` | required | Each: `{"source": str, "target": str, "rel_type"?: str, "strength"?: float, "label"?: str}` |
| `layout` | `"cose-bilkent"` \| `"circle"` \| `"grid"` \| `"breadthfirst"` \| `"concentric"` | `"cose-bilkent"` | Cytoscape layout algorithm |
| `height` | `int` (px) | `600` | Canvas height |
| `min_node_size` | `int` | `20` | Minimum rendered node radius |
| `max_node_size` | `int` | `80` | Maximum rendered node radius (scaled by `importance`) |
| `edge_label_visible` | `bool` | `True` | Show `rel_type` / `label` on edges |
| `color_by` | `str` | `"type"` | Node property that drives color palette |
| `on_node_click` | `UIAction` \| `None` | `None` | Executed on node click; `node_id` auto-injected as param |

Accepts Cases API `/cases/{id}/graph` JSON payload directly — Panel unwraps Cytoscape `{data: {...}}` wrapper server-side.

**Panel:** rendered by `DGraph.tsx` (registered as `graph`). Toolbar: search, type filter (entity + rel_type), layout switcher, PNG export, node-detail drawer.

```python
# Sharelock Intelligence Graph tab (right panel)
graph = await queries.fetch_graph(case_id)   # {"nodes": [...], "edges": [...]}

ui.Graph(
    nodes=graph["nodes"],
    edges=graph["edges"],
    layout="cose-bilkent",
    height=720,
    color_by="type",
    on_node_click=ui.Call("entity_detail", entity_id=...),
)
```

**Recommended caps for large graphs:** fetch up to 200 nodes + 1,500 edges at a time and paginate via toolbar. Cytoscape stays responsive up to ~5,000 nodes but UX degrades past ~1,500.

**Example node payload:**
```json
{
  "id": "E42",
  "label": "Nicholas Mitchell",
  "type": "person",
  "importance": 0.87,
  "meta": {"category": "suspect", "mentions": 34}
}
```

**Example edge payload:**
```json
{
  "source": "E42",
  "target": "E17",
  "rel_type": "wired_funds",
  "strength": 0.65,
  "label": "2023-03-14 · $185k"
}
```

---

## Feedback Components

5 components for status indicators, loading states, and charts.

### `ui.Alert`
Alert banner for messages, warnings, and errors.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `str` | required | Alert message |
| `title` | `str` | `""` | Alert title (bold, above message) |
| `type` | `str` | `"info"` | Type: `info`, `success`, `warn`, `error` |

```python
ui.Alert(message="Extension deployed successfully", title="Deployed", type="success")
ui.Alert(message="Rate limit exceeded. Retry in 60s.", type="warn")
```

### `ui.Progress`
Progress indicator (bar or circular).

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `value` | `int` | `0` | Progress percentage (0-100) |
| `label` | `str` | `""` | Label text |
| `variant` | `str` | `"bar"` | Style: `bar`, `circular` |
| `color` | `str` | `""` | Bar color. One of `blue` (default), `green`, `red`, `yellow`, `purple`. Empty string keeps default blue. Use semantic colors for status bars (red for over-budget, green for healthy). *(SDK 1.5.7, session 30)* |

```python
# Static bar
ui.Progress(value=73, label="Uploading...", variant="bar")

# Semantic budget bar — red ≥ 90%, orange 70-90%, green < 70%
pct = round(spend / budget * 100)
ui.Progress(
    value=pct,
    label=f"${spend:.2f} / ${budget:.2f} today — {pct}%",
    color="red" if pct >= 90 else "yellow" if pct >= 70 else "green",
)
```

### `ui.Chart`
Chart component powered by Recharts.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `data` | `list[dict]` | `[]` | Data points |
| `type` | `str` | `"line"` | Chart type: `line`, `bar`, `pie`. Serialized as `chart_type` in JSON. |
| `x_key` | `str` | `"name"` | Key in data dicts for the X-axis |
| `height` | `int` | `200` | Chart height in pixels |
| `colors` | `dict[str,str] \| None` | `None` | Per-series color override, e.g. `{"OK":"#22c55e","Critical":"#ef4444"}`. Keys not listed fall through to default PALETTE. When provided, SDK emits `series=[{key,label,color}]` that the React renderer honours. *(SDK 1.5.7, session 30)* |
| `y2_keys` | `list[str] \| None` | `None` | Keys that render on a secondary right-side Y-axis. Use for mixed-scale metrics (spend $ on left axis, clicks count on right). Pie charts are unaffected. *(SDK 1.5.7, session 30)* |

**NOTE:** The Python parameter is `type`. It is serialized as `chart_type` in JSON to avoid shadowing Python's built-in `type`.

```python
# Basic bar chart
ui.Chart(
    data=[
        {"date": "Mon", "calls": 120, "tokens": 45000},
        {"date": "Tue", "calls": 185, "tokens": 62000},
        {"date": "Wed", "calls": 97, "tokens": 31000},
    ],
    type="bar",
    x_key="date",
    height=250,
)

# Semantic health dashboard — each series gets a meaningful color
ui.Chart(
    data=[{"host": m, "OK": ok, "Warning": warn, "Critical": crit, "Unknown": unk}
          for m, ok, warn, crit, unk in rows],
    type="bar",
    x_key="host",
    colors={
        "OK": "#22c55e", "Warning": "#eab308",
        "Critical": "#ef4444", "Unknown": "#6b7280",
    },
    height=220,
)

# Dual-axis line chart — spend (left, $) + clicks (right, count)
ui.Chart(
    data=[{"day": d, "spend": s, "clicks": c} for d, s, c in series],
    type="line",
    x_key="day",
    colors={"spend": "#3b82f6", "clicks": "#22c55e"},
    y2_keys=["clicks"],
    height=240,
)
```

### `ui.Loading`
Loading state indicator.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `str` | `"Loading..."` | Loading message |
| `variant` | `str` | `"spinner"` | Style: `spinner`, `skeleton`, `dots` |

```python
ui.Loading(message="Fetching user data...", variant="spinner")
```

### `ui.Error`
Error state with optional retry action.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `message` | `str` | required | Error message |
| `title` | `str` | `"Error"` | Error title |
| `retry` | `UIAction` | `None` | Retry action (e.g., `ui.Call("reload_data")`) |

```python
ui.Error(
    message="Failed to load extension data. Server returned 503.",
    title="Connection Error",
    retry=ui.Call("get_panel_data"),
)
```

---

## Panel Discovery

Extensions expose their Panel UI via the `@ext.panel()` decorator. The Imperal Panel discovers and renders these automatically.

> **Panel wiring is automatic (session 30, 2026-04-18).** Previously third-party extensions deployed through the Developer Portal rendered a blank page until an administrator manually PUT `ui.panels` into `unified_config`. Since session 30 this is fixed in two independent places (GAP-9): Developer Portal's `deploy_app` calls `_sync_panel_config_to_unified_config()` after every successful validation, AND the kernel's `direct_call_extension` activity calls `maybe_publish_panels()` on the first `__panel__*` dispatch. Both paths are hash-dedup idempotent. A one-shot backfill on 2026-04-18 primed the 15 pre-existing extensions. **Invariant CONFIG-I1.**
>
> **Live updates via SSE (session 30).** Panel's `refresh: "on_event:X,Y,Z"` declaration now actually fires the `refetchPanelData` callback. Matcher compares `${event.scope}.${event.action}`, bare action, or bare scope against the declared set. Kernel `signals.py` publishes `{scope=<app_id>, action=<stripped_fn_name>}` for every `@chat.function` invocation; extensions can also publish semantic events via `ctx.publish_event(scope=, action=, data=)` (wired through `imperal:events:{tenant}` Redis channel → Auth GW SSE hub → Panel `use-events.ts` multiplexed stream).
>
> **Fast-RPC transport (session 30).** `/call` and `/batch` endpoints bypass Temporal via Redis Streams when `IMPERAL_FAST_RPC_PANELS=true` is set on Auth GW. Extension authors do NOT need to change anything — same `direct_call_extension` activity runs the handler, identical request/response shape. Measured end-to-end `/call` p50 = 3ms (was 388ms). See [`fast-rpc.md`](../fast-rpc.md).

### `@ext.panel()` Decorator

Registers a panel handler that returns `UINode` trees for the Panel sidebar.

```python
from imperal_sdk import Extension, ui

ext = Extension("my-ext")

@ext.panel()
async def panel(ctx, section: str = "", **params):
    """Main panel entry point. Called by the Panel shell via /call endpoint."""
    if section == "settings":
        return build_settings_panel(ctx)
    return build_default_panel(ctx)
```

**Decorator kwargs:**

| Kwarg | Type | Default | Description |
|-------|------|---------|-------------|
| `default_width` | `str` | `"md"` | Default panel width: `sm` (320px), `md` (400px), `lg` (520px), `xl` (640px) |
| `min_width` | `str` | `""` | Minimum panel width (same scale as `default_width`) |
| `max_width` | `str` | `""` | Maximum panel width (same scale as `default_width`) |

```python
@ext.panel(default_width="lg", min_width="md", max_width="xl")
async def panel(ctx, section: str = "", **params):
    ...
```

### `config.ui` in Extension Config

Extensions declare their UI presence in the extension config:

```python
ext = Extension(
    "my-ext",
    config={
        "ui": {
            "icon": "Puzzle",           # Lucide icon for the GlobalNav
            "label": "My Extension",    # Display name in the shell
            "sections": [               # Sidebar navigation sections
                {"id": "dashboard", "label": "Dashboard", "icon": "LayoutDashboard"},
                {"id": "settings", "label": "Settings", "icon": "Settings"},
            ],
        }
    }
)
```

### Panel Data Flow

1. User clicks extension icon in GlobalNav
2. Panel shell calls `/call` endpoint with `function="get_panel_data"` (or the `@ext.panel` handler)
3. Handler returns a `UINode` tree via `ActionResult.success(data={...})`
4. Panel shell renders the UINode JSON into React components
5. User interactions (clicks, form submits) trigger `ui.Call`, `ui.Navigate`, or `ui.Send` actions
6. Actions are dispatched back through `/call` to the appropriate `@chat.function` handler

### Section-Based Routing

The `section` parameter enables multi-page panels from a single entry point:

```python
@ext.panel()
async def panel(ctx, section: str = "", **params):
    router = {
        "": build_dashboard,
        "users": build_users_panel,
        "roles": build_roles_panel,
        "settings": build_settings_panel,
    }
    handler = router.get(section, build_dashboard)
    return await handler(ctx, **params)
```

The Panel shell passes the current section based on sidebar navigation clicks. Each section handler returns its own `UINode` tree.

---

## Best Practices

### Component Composition

Build complex UIs by composing small components. Prefer many small functions over monolithic builders:

```python
def build_user_card(user: dict) -> UINode:
    return ui.Card(
        title=user["name"],
        subtitle=user["email"],
        content=ui.Row([
            ui.Badge(label=user["role"], color="blue"),
            ui.Text(content=f"Last seen: {user['last_seen']}", variant="caption"),
        ]),
        on_click=ui.Navigate(f"/users/{user['id']}"),
    )

def build_user_list(users: list[dict]) -> UINode:
    return ui.List(
        items=[build_user_card(u) for u in users],
        searchable=True,
        page_size=20,
    )
```

### Action Patterns

- **Read-only views:** Use `ui.Navigate` for section navigation, no server calls needed
- **Mutations:** Use `ui.Call` to invoke `@chat.function` handlers directly
- **Confirmations:** Use `actions[].confirm` on ListItem, or `ui.Dialog` for complex confirmations
- **Chat fallback:** Use `ui.Send` when the action is better handled by the LLM (natural language queries)

### Form vs Individual Inputs

- Use `ui.Form` when multiple fields should submit together (user creation, settings update)
- Use individual inputs with `on_submit`/`on_change` for immediate, single-field actions (search, toggle)
- Inside a Form, each input's `param_name` becomes a key in the submitted params dict

### Performance

- Fetch data with `asyncio.gather` when a panel needs multiple API calls
- Use TTL caching for data that changes infrequently (system stats, config)
- Keep panel handlers under 100ms for perceived instant rendering
- Use `page_size` on Lists to avoid rendering thousands of items
- Use `page_size` for pagination when total item count is large

### File Size

Panel handler files must stay under 300 lines. Split into modules by section:

```
my-ext/
  panels.py              # Router (section dispatch)
  panels_dashboard.py    # Dashboard section builder
  panels_users.py        # Users section builder
  panels_settings.py     # Settings section builder
```
