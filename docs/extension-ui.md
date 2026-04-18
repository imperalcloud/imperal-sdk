# Extension UI Standard — 3-Column Layout

Every Imperal Cloud extension renders in a standardized **3-column layout** in the Panel. This is not optional — it is the platform UI pattern. Users get a consistent experience across all extensions.

---

## The Layout

```
┌──────────────────────────────────────────────────────────────────┐
│                        GlobalNav (top bar)                       │
│  Logo | Assistant | Automations | Marketplace | Admin | SystemTray | User │
├────────────┬──────────────────────────┬──────────────────────────┤
│            │                          │                          │
│  Left      │       Center             │       Right              │
│  Sidebar   │       Chat               │       Panel              │
│            │                          │                          │
│  Navigation│  Messages + Input        │  Context-sensitive       │
│  & items   │  (Markdown rendering)    │  widgets & data          │
│            │                          │                          │
│  e.g.      │  User sends message →    │  e.g.                    │
│  - Cases   │  AI responds with        │  - Documents/Files       │
│  - Items   │  awareness of left +     │  - Analysis results      │
│  - Folders │  right panel context     │  - Metrics/KPIs          │
│  - Chats   │                          │  - Related items         │
│            │                          │                          │
├────────────┴──────────────────────────┴──────────────────────────┤
│  Each column scrolls independently — h-screen overflow-hidden    │
└──────────────────────────────────────────────────────────────────┘
```

**This is the standard.** Every extension has:

1. **Left sidebar** — navigation, item list, or section menu
2. **Center chat** — the AI conversation (always present, always Markdown-rendered)
3. **Right panel** — contextual data, files, analysis, widgets (tabs if multiple)

---

## Reference Implementations

### Sharelock (case management)

The first production extension. This is the pattern to follow.

| Column | Component | Content |
|--------|-----------|---------|
| Left | `CasesSidebar` | List of cases + create + delete |
| Center | `ChatArea` | Chat with 4-state machine (intake/intelligence/hub/report) |
| Right | `ExtensionRightPanel` | Tabs: Documents, Analysis, Summary |

**Route:** `/cases/[id]`

The left sidebar shows all user's cases. Clicking a case loads its chat history in the center and its files/analysis in the right panel. The AI has full context of what's in both panels.

### Admin (system management)

| Column | Component | Content |
|--------|-----------|---------|
| Left | `AdminSidebar` | Sections: Users, Roles, Extensions, System |
| Center | `AdminChat` | Chat with 41 functions via Claude Haiku native tool_use |
| Right | `AdminWidgets` | Context-sensitive: user lists, role tables, extension config |

**Route:** `/admin`

### Hub / Assistant (unified chat)

The hub is the default landing page with a simplified layout. **Note:** The Hub can be disabled per user via the `assistant_enabled` attribute (default true). When disabled, the user's landing page becomes their first extension or the marketplace.

| Column | Component | Content |
|--------|-----------|---------|
| Left | `ExtensionSidebar` | Active extensions icons + marketplace |
| Center | `AssistantClient` | Unified hub chat merging all extension tools |
| Right | _(expandable)_ | Extension-specific context when relevant |

**Route:** `/assistant`

---

## How Extensions Declare Their UI

Extensions declare their UI structure in the **Registry** (`/v1/apps/{app_id}/settings`). The Panel reads this config and renders the appropriate layout.

### Manifest UI Section

In your extension's registry config, the `ui` section declares the layout:

```json
{
  "ui": {
    "layout": "three-column",
    "sidebar": {
      "type": "item-list",
      "label": "Cases",
      "icon": "folder",
      "api": "/api/cases"
    },
    "right_panel": {
      "tabs": [
        {"id": "documents", "label": "Documents", "icon": "file"},
        {"id": "analysis", "label": "Analysis", "icon": "chart"},
        {"id": "summary", "label": "Summary", "icon": "list"}
      ]
    }
  }
}
```

### Sidebar Types

| Type | Description | Example |
|------|-------------|---------|
| `item-list` | Scrollable list of items with create/delete | Cases, tickets, projects |
| `section-menu` | Static navigation sections | Users, Roles, Extensions |
| `tree` | Hierarchical folder structure | File browser, org chart |
| `none` | No sidebar (center + right only) | Simple tools |

### Right Panel Types

| Type | Description | Example |
|------|-------------|---------|
| `tabs` | Tabbed panels with different content | Documents + Analysis + Summary |
| `widgets` | Grid of metric cards and data tables | Dashboard, system health |
| `detail` | Single detail view of selected item | User profile, config viewer |
| `none` | No right panel (sidebar + center only) | Simple chat |

---

## UI Principles

### 1. Chat is always the center

The chat is the primary interface. The left and right panels provide **context** to the conversation. The user talks to the AI; the panels show what the AI knows and what it produced.

### 2. Independent scrolling

Each column scrolls independently. The page itself never scrolls. This is enforced by `h-screen overflow-hidden` on the root container.

```
Root:     h-screen overflow-hidden
Sidebar:  overflow-y-auto
Chat:     flex flex-col, messages overflow-y-auto
Right:    overflow-y-auto
```

### 3. Markdown in all chats

All AI responses render as Markdown via `MarkdownMessage` component (`react-markdown` + `remark-gfm`). This is not optional — tables, code blocks, lists, and formatting must work in every extension chat.

### 4. Chat input UX

- Auto-focus input after sending a message
- Input stays active during AI response (user can type next message)
- Send button: fixed `min-w-[72px]` with SVG spinner while processing
- These behaviors are inherited from the shared chat components

### 5. Context flows both ways

The AI sees the context from both panels. When a user selects a case in the left sidebar, the chat and right panel update. When the AI produces analysis, the right panel shows it. The three columns are connected, not independent.

---

## Shared Components

The Panel provides these shared components that all extensions use:

| Component | Purpose |
|-----------|---------|
| `GlobalNav` | Top navigation bar (logo, nav items, System Tray, user menu) |
| `SystemTray` | SSEStatus (connection dot) + AutomationsBadge (active count) + SystemClock (live clock + timezone selector) |
| `ExtensionSidebar` | Left sidebar with extension icons (auto-rendered by layout.tsx) |
| `MarkdownMessage` | Markdown rendering for AI messages |
| `SubmitButton` | Login/submit with loading state |
| `Toast` | Notification toasts |
| `DataTable` | Sortable data tables |
| `SlideOver` | Slide-in panels |
| `Badge` | Status badges |
| `MetricCard` | KPI metric cards |
| `Modal` | Modal dialogs |
| `LoadingSkeleton` | Loading placeholders |
| `EmptyState` | Empty state with icon and action |
| `Tabs` | Tab navigation |

---

## Example: Building a New Extension UI

Say you're building a **Project Manager** extension. Here's how it maps:

```
Left Sidebar:          Center Chat:              Right Panel:
┌──────────────┐      ┌─────────────────────┐   ┌─────────────────┐
│ Projects     │      │ "What's the status  │   │ [Tasks] [Files] │
│              │      │  of Project Alpha?" │   │                 │
│ > Alpha  ●   │      │                     │   │ ☑ Design spec   │
│   Beta       │      │ "Project Alpha:     │   │ ☑ API endpoints │
│   Gamma      │      │  6/8 tasks done,    │   │ ☐ Frontend      │
│              │      │  2 blocked on API.  │   │ ☐ Testing       │
│ [+ New]      │      │  ETA: Thursday."    │   │                 │
│              │      │                     │   │ Blocked:        │
│              │      │ "Unblock the API    │   │ ⚠ API auth dep  │
│              │      │  tasks — assign to  │   │ ⚠ DB migration  │
│              │      │  backend team?"     │   │                 │
│              │      │ [YES] [NO]          │   │                 │
└──────────────┘      └─────────────────────┘   └─────────────────┘
```

Registry config:
```json
{
  "ui": {
    "layout": "three-column",
    "sidebar": {
      "type": "item-list",
      "label": "Projects",
      "icon": "folder"
    },
    "right_panel": {
      "tabs": [
        {"id": "tasks", "label": "Tasks", "icon": "check-square"},
        {"id": "files", "label": "Files", "icon": "file"}
      ]
    }
  }
}
```

---

## See Also

- [Quickstart](quickstart.md) — build your first extension
- [Panel Architecture](../imperal-panel.md) — full panel documentation
- [Skeleton](skeleton.md) — background state that powers the right panel
